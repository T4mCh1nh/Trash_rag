import os
import uuid
import logging
from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from vietocr.tool.predictor import Predictor
from vietocr.tool.config import Cfg
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from openai import OpenAI

from config import get_settings
from models import Document, DocumentChunk

logger = logging.getLogger(__name__)

settings = get_settings()

openai_client = OpenAI(api_key=settings.openai_api_key)

vietocr_predictor = None


def get_vietocr_predictor() -> Predictor:
    global vietocr_predictor
    if vietocr_predictor is None:
        config = Cfg.load_config_from_name("vgg_transformer")
        config["cnn"]["pretrained"] = True
        config["device"] = "cuda"
        vietocr_predictor = Predictor(config)
    return vietocr_predictor


def ensure_upload_dir() -> Path:
    upload_path = Path(settings.upload_dir)
    upload_path.mkdir(parents=True, exist_ok=True)
    return upload_path


def get_embedding(text: str) -> list[float]:
    response = openai_client.embeddings.create(
        input=text,
        model=settings.embedding_model,
    )
    return response.data[0].embedding


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    batch_size = 100
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = openai_client.embeddings.create(
            input=batch,
            model=settings.embedding_model,
        )
        all_embeddings.extend([item.embedding for item in response.data])
    return all_embeddings


def process_document(file_path: str) -> list[dict]:
    converter = DocumentConverter()
    result = converter.convert(file_path)
    doc = result.document

    chunker = HybridChunker(tokenizer="sentence-transformers/all-MiniLM-L6-v2")
    chunks = list(chunker.chunk(doc))

    chunk_data = []
    for i, chunk in enumerate(chunks):
        chunk_text = chunk.text if hasattr(chunk, "text") else str(chunk)
        meta = {}
        if hasattr(chunk, "meta"):
            meta = {
                "headings": chunk.meta.headings if hasattr(chunk.meta, "headings") else [],
                "page": chunk.meta.doc_items[0].prov[0].page_no
                if hasattr(chunk.meta, "doc_items")
                and chunk.meta.doc_items
                and chunk.meta.doc_items[0].prov
                else None,
            }
        chunk_data.append({"text": chunk_text, "metadata": meta, "index": i})

    return chunk_data


def run_vietocr(image_path: str) -> str:
    predictor = get_vietocr_predictor()
    img = Image.open(image_path)
    text = predictor.predict(img)
    return text


def process_image(file_path: str) -> list[dict]:
    text = run_vietocr(file_path)
    if text.strip():
        return [{"text": text, "metadata": {"source": "vietocr", "file": file_path}, "index": 0}]
    return []


def save_uploaded_files(files: list[tuple[str, str, str | None]], chat_id: int, db: Session) -> list[Document]:
    upload_dir = ensure_upload_dir()
    documents = []

    for filename, file_content_path, content_type in files:
        file_ext = os.path.splitext(filename)[1].lower()
        stored_filename = f"{uuid.uuid4()}{file_ext}"
        stored_path = upload_dir / stored_filename

        with open(file_content_path, "rb") as src, open(stored_path, "wb") as dst:
            dst.write(src.read())

        doc = Document(
            filename=filename,
            content_type=content_type,
            chat_id=chat_id,
            processing_status="pending",
            stored_path=str(stored_path),
        )
        db.add(doc)
        db.flush()
        documents.append(doc)

    return documents
