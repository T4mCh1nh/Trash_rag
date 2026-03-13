import os
import tempfile

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from database import get_db
from models import Document, DocumentChunk
from schemas import (
    DocumentResponse,
    DocumentListResponse,
    DocumentUploadResponse,
    DocumentStatusResponse,
    SearchRequest,
    SearchResponse,
    ChunkResult,
)
from service import save_uploaded_files, get_embedding
from workers.tasks import process_document_task

router = APIRouter(tags=["Documents"])


@router.post("/documents/upload", response_model=DocumentUploadResponse, status_code=202)
def upload_documents(
    files: list[UploadFile] = File(...),
    chat_id: int = Form(...),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(status_code=400, detail="Ko tìm thấy file")

    file_infos = []
    temp_paths = []

    try:
        for file in files:
            suffix = os.path.splitext(file.filename or "unknown")[1]
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            content = file.file.read()
            tmp.write(content)
            tmp.close()
            temp_paths.append(tmp.name)
            file_infos.append((file.filename or "unknown", tmp.name, file.content_type))

        documents = save_uploaded_files(file_infos, chat_id, db)
        db.commit()

        for doc in documents:
            process_document_task.delay(doc.id)

        doc_responses = [
            DocumentResponse(
                id=doc.id,
                filename=doc.filename,
                content_type=doc.content_type,
                chat_id=doc.chat_id,
                processing_status=doc.processing_status,
                created_at=doc.created_at,
            )
            for doc in documents
        ]

        return DocumentUploadResponse(
            documents=doc_responses,
            chat_id=chat_id,
        )

    except Exception:
        db.rollback()
        raise
    finally:
        for path in temp_paths:
            try:
                os.unlink(path)
            except OSError:
                pass


@router.get("/documents/{chat_id}", response_model=DocumentListResponse)
def list_documents(chat_id: int, db: Session = Depends(get_db)):
    stmt = select(Document).where(Document.chat_id == chat_id).order_by(Document.created_at)
    result = db.execute(stmt)
    documents = result.scalars().all()

    return DocumentListResponse(
        documents=[
            DocumentResponse(
                id=doc.id,
                filename=doc.filename,
                content_type=doc.content_type,
                chat_id=doc.chat_id,
                processing_status=doc.processing_status,
                created_at=doc.created_at,
            )
            for doc in documents
        ]
    )


@router.get("/documents/{doc_id}/status", response_model=DocumentStatusResponse)
def get_document_status(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Ko tìm thấy doc")

    chunks_count = db.execute(
        select(func.count()).where(DocumentChunk.document_id == doc_id)
    ).scalar()

    return DocumentStatusResponse(
        id=doc.id,
        filename=doc.filename,
        processing_status=doc.processing_status,
        processing_error=doc.processing_error,
        chunks_created=chunks_count or 0,
        created_at=doc.created_at,
    )


@router.delete("/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Ko tìm thấy doc")

    db.delete(doc)
    db.commit()
    return {"message": "Xóa doc thành công", "id": document_id}


@router.post("/documents/{doc_id}/retry", response_model=DocumentStatusResponse)
def retry_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Ko tìm thấy doc")

    if doc.processing_status not in ("failed", "pending"):
        raise HTTPException(
            status_code=400,
            detail=f"Chỉ có thể retry doc ở trạng thái 'failed' hoặc 'pending', hiện tại: '{doc.processing_status}'"
        )

    # Delete old chunks if any
    old_chunks = db.execute(select(DocumentChunk).where(DocumentChunk.document_id == doc_id)).scalars().all()
    for chunk in old_chunks:
        db.delete(chunk)

    doc.processing_status = "pending"
    doc.processing_error = None
    db.commit()

    process_document_task.delay(doc.id)

    chunks_count = db.execute(
        select(func.count()).where(DocumentChunk.document_id == doc_id)
    ).scalar()

    return DocumentStatusResponse(
        id=doc.id,
        filename=doc.filename,
        processing_status=doc.processing_status,
        processing_error=doc.processing_error,
        chunks_created=chunks_count or 0,
        created_at=doc.created_at,
    )


@router.post("/internal/search", response_model=SearchResponse)
def search_chunks(data: SearchRequest, db: Session = Depends(get_db)):
    query_embedding = get_embedding(data.query)

    distance_expr = DocumentChunk.embedding.cosine_distance(query_embedding)

    stmt = (
        select(DocumentChunk, distance_expr.label("distance"))
        .join(DocumentChunk.document)
        .where(Document.chat_id == data.chat_id)
        .where(DocumentChunk.embedding.isnot(None))
        .order_by(distance_expr)
        .limit(data.top_k)
    )

    results = db.execute(stmt).all()

    max_distance = 0.7
    filtered = [(chunk, dist) for chunk, dist in results if dist < max_distance]

    return SearchResponse(
        chunks=[
            ChunkResult(
                text=chunk.text,
                metadata=chunk.chunk_metadata or {},
                document_id=chunk.document_id,
                score=round(1.0 - dist, 4),
            )
            for chunk, dist in filtered
        ]
    )


@router.delete("/internal/by-chat/{chat_id}")
def delete_documents_by_chat(chat_id: int, db: Session = Depends(get_db)):
    stmt = select(Document).where(Document.chat_id == chat_id)
    documents = db.execute(stmt).scalars().all()

    count = len(documents)
    for doc in documents:
        db.delete(doc)

    db.commit()
    return {"message": f"Xóa {count} docs của chat {chat_id}", "deleted": count}
