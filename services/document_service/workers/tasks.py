import logging

from sqlalchemy.orm import Session

from workers.celery_app import celery_app
from database import SessionLocal
from models import Document, DocumentChunk
from service import (
    process_document,
    process_image,
    get_embeddings_batch,
)

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="workers.tasks.process_document_task", max_retries=2)
def process_document_task(self, document_id: int):
    db: Session = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if not doc:
            logger.error(f"Document {document_id} not found")
            return {"status": "failed", "error": "Document not found"}

        doc.processing_status = "processing"
        db.commit()

        file_path = doc.stored_path
        file_ext = doc.filename.rsplit(".", 1)[-1].lower() if "." in doc.filename else ""

        chunks_data = []

        if file_ext in ["jpg", "jpeg", "png", "bmp", "tiff", "tif"]:
            try:
                vietocr_chunks = process_image(file_path)
                if vietocr_chunks:
                    chunks_data.extend(vietocr_chunks)
            except Exception as e:
                logger.warning(f"VietOCR failed for {doc.filename}: {e}")

        try:
            docling_chunks = process_document(file_path)
            if docling_chunks:
                if chunks_data:
                    offset = len(chunks_data)
                    for c in docling_chunks:
                        c["index"] += offset
                chunks_data.extend(docling_chunks)
        except Exception as e:
            logger.warning(f"Docling failed for {doc.filename}: {e}")
            if not chunks_data:
                chunks_data.append(
                    {
                        "text": f"[Document: {doc.filename} - could not extract text]",
                        "metadata": {"error": str(e)},
                        "index": 0,
                    }
                )

        if chunks_data:
            texts = [c["text"] for c in chunks_data]
            embeddings = get_embeddings_batch(texts)

            for chunk, embedding in zip(chunks_data, embeddings):
                db_chunk = DocumentChunk(
                    document_id=doc.id,
                    text=chunk["text"],
                    embedding=embedding,
                    chunk_metadata=chunk.get("metadata", {}),
                    chunk_index=chunk["index"],
                )
                db.add(db_chunk)

        doc.processing_status = "completed"
        db.commit()

        logger.info(f"Document {document_id} processed: {len(chunks_data)} chunks")
        return {"status": "completed", "chunks_created": len(chunks_data)}

    except Exception as e:
        db.rollback()
        logger.error(f"Document {document_id} processing failed: {e}")

        try:
            doc = db.get(Document, document_id)
            if doc:
                doc.processing_status = "failed"
                doc.processing_error = str(e)[:500]
                db.commit()
        except Exception:
            db.rollback()

        raise self.retry(exc=e, countdown=30)

    finally:
        db.close()
