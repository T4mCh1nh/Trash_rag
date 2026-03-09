from pydantic import BaseModel
from datetime import datetime


class RAGQueryRequest(BaseModel):
    query: str
    chat_id: int


class MessageResponse(BaseModel):
    id: int
    chat_id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class RAGQueryResponse(BaseModel):
    answer: MessageResponse
    sources: list[dict]
