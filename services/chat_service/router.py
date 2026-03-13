import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from database import get_db
from config import get_settings
from models import Chat, ChatMessage
from schemas import (
    ChatCreate,
    ChatUpdate,
    ChatResponse,
    ChatListResponse,
    MessageCreate,
    MessageResponse,
    MessageListResponse,
    RAGResponse,
)

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/chats", tags=["Chats"])


@router.post("", response_model=ChatResponse)
def create_chat(data: ChatCreate, db: Session = Depends(get_db)):
    chat = Chat(title=data.title)
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return ChatResponse(id=chat.id, title=chat.title, created_at=chat.created_at)


@router.get("", response_model=ChatListResponse)
def list_chats(db: Session = Depends(get_db)):
    stmt = select(Chat).order_by(Chat.created_at.desc())
    result = db.execute(stmt)
    chats = result.scalars().all()
    return ChatListResponse(
        chats=[
            ChatResponse(id=c.id, title=c.title, created_at=c.created_at) for c in chats
        ]
    )


@router.get("/{chat_id}", response_model=ChatResponse)
def get_chat(chat_id: int, db: Session = Depends(get_db)):
    chat = db.get(Chat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Ko tìm thấy chat")
    return ChatResponse(id=chat.id, title=chat.title, created_at=chat.created_at)


@router.post("/{chat_id}/message", response_model=RAGResponse)
def send_message(chat_id: int, data: MessageCreate, db: Session = Depends(get_db)):
    chat = db.get(Chat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Ko tìm thấy chat")

    # Save user message to DB first to avoid data loss if RAG fails
    user_msg = ChatMessage(chat_id=chat_id, role="user", content=data.content)
    db.add(user_msg)
    db.commit()

    try:
        response = httpx.post(
            f"{settings.rag_service_url}/rag/query",
            json={"query": data.content, "chat_id": chat_id},
            timeout=120.0,
        )
        response.raise_for_status()
        rag_data = response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"RAG lỗi : {e.response.text}")
        raise HTTPException(status_code=502, detail="RAG lỗi")
    except httpx.RequestError as e:
        logger.error(f"RAG không thể kết nối: {e}")
        raise HTTPException(status_code=503, detail="RAG cant kết nối")

    # Get the latest assistant message created by rag_service
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.chat_id == chat_id)
        .where(ChatMessage.role == "assistant")
        .order_by(ChatMessage.created_at.desc())
        .limit(1)
    )
    assistant_message = db.execute(stmt).scalar()

    if not assistant_message:
        raise HTTPException(status_code=502, detail="RAG không trả về kết quả")

    return RAGResponse(
        answer=MessageResponse(
            id=assistant_message.id,
            chat_id=assistant_message.chat_id,
            role=assistant_message.role,
            content=assistant_message.content,
            created_at=assistant_message.created_at,
        ),
        sources=rag_data.get("sources", []),
    )


@router.get("/{chat_id}/messages", response_model=MessageListResponse)
def get_messages(chat_id: int, db: Session = Depends(get_db)):
    chat = db.get(Chat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Ko tìm thấy chat")

    stmt = (
        select(ChatMessage)
        .where(ChatMessage.chat_id == chat_id)
        .order_by(ChatMessage.created_at)
    )
    result = db.execute(stmt)
    messages = result.scalars().all()

    return MessageListResponse(
        messages=[
            MessageResponse(
                id=m.id,
                chat_id=m.chat_id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
            )
            for m in messages
        ]
    )


@router.put("/{chat_id}", response_model=ChatResponse)
def update_chat(chat_id: int, data: ChatUpdate, db: Session = Depends(get_db)):
    chat = db.get(Chat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Ko tìm thấy chat")

    if data.title is not None:
        chat.title = data.title

    db.commit()
    db.refresh(chat)
    return ChatResponse(id=chat.id, title=chat.title, created_at=chat.created_at)


@router.delete("/{chat_id}")
def delete_chat(chat_id: int, db: Session = Depends(get_db)):
    chat = db.get(Chat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Ko tìm thấy chat")

    try:
        httpx.delete(
            f"{settings.document_service_url}/internal/by-chat/{chat_id}",
            timeout=30.0,
        )
    except Exception as e:
        logger.warning(f"Không xóa được docs của chat {chat_id}: {e}")

    db.delete(chat)
    db.commit()
    return {"message": "Xóa chat thành công", "id": chat_id}
