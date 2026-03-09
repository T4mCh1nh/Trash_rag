from pydantic import BaseModel
from datetime import datetime


class DocumentResponse(BaseModel):
    id: int
    filename: str
    content_type: str | None
    chat_id: int
    processing_status: str
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]


class DocumentUploadResponse(BaseModel):
    documents: list[DocumentResponse]
    chat_id: int


class DocumentStatusResponse(BaseModel):
    id: int
    filename: str
    processing_status: str
    processing_error: str | None
    chunks_created: int
    created_at: datetime

    class Config:
        from_attributes = True


class SearchRequest(BaseModel):
    query: str
    chat_id: int
    top_k: int = 5


class ChunkResult(BaseModel):
    text: str
    metadata: dict
    document_id: int


class SearchResponse(BaseModel):
    chunks: list[ChunkResult]
