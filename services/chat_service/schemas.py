from pydantic import BaseModel
from datetime import datetime


class ChatCreate(BaseModel):
    title: str


class ChatUpdate(BaseModel):
    title: str | None = None


class ChatResponse(BaseModel):
    id: int
    title: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatListResponse(BaseModel):
    chats: list[ChatResponse]


class MessageCreate(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: int
    chat_id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]


class RAGResponse(BaseModel):
    answer: MessageResponse
    sources: list[dict]
