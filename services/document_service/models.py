from sqlalchemy import Column, Integer, String, Text, ForeignKey, JSON, TIMESTAMP
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from sqlalchemy import text

from database import Base
from config import get_settings

settings = get_settings()


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, nullable=False)
    filename = Column(String(500), nullable=False)
    content_type = Column(String(100), nullable=True)
    chat_id = Column(Integer, nullable=False)
    processing_status = Column(String(20), nullable=False, default="pending")
    stored_path = Column(String(500), nullable=True)
    processing_error = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True),
                        nullable=False, server_default=text('now()'))

    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    embedding = Column(Vector(settings.embedding_dim), nullable=True)
    chunk_metadata = Column(JSON, nullable=True, default=dict)
    chunk_index = Column(Integer, nullable=False, default=0)

    document = relationship("Document", back_populates="chunks")
