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


@router.post("/internal/search", response_model=SearchResponse)
def search_chunks(data: SearchRequest, db: Session = Depends(get_db)):
    query_embedding = get_embedding(data.query)

    stmt = (
        select(DocumentChunk)
        .join(DocumentChunk.document)
        .where(Document.chat_id == data.chat_id)
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
        .limit(data.top_k)
    )

    result = db.execute(stmt)
    chunks = result.scalars().all()

    return SearchResponse(
        chunks=[
            ChunkResult(
                text=chunk.text,
                metadata=chunk.chunk_metadata or {},
                document_id=chunk.document_id,
            )
            for chunk in chunks
        ]
    )
