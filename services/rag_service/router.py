import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import ChatMessage
from schemas import RAGQueryRequest, RAGQueryResponse, MessageResponse
from service import generate_rag_response, save_message_to_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["RAG"])


@router.post("/query", response_model=RAGQueryResponse)
def rag_query(data: RAGQueryRequest, db: Session = Depends(get_db)):
    # User message is already saved by chat_service, only cache to Redis
    save_message_to_redis(data.chat_id, "user", data.query)

    answer, sources = generate_rag_response(data.query, data.chat_id)

    assistant_message = ChatMessage(
        chat_id=data.chat_id,
        role="assistant",
        content=answer,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    save_message_to_redis(data.chat_id, "assistant", answer)

    return RAGQueryResponse(
        answer=MessageResponse(
            id=assistant_message.id,
            chat_id=assistant_message.chat_id,
            role=assistant_message.role,
            content=assistant_message.content,
            created_at=assistant_message.created_at,
        ),
        sources=sources,
    )
