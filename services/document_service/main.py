import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from database import engine, Base
from models import Document, DocumentChunk
from router import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

with engine.connect() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    conn.commit()

Base.metadata.create_all(bind=engine)
logger.info("Document Service: Database tables created")

app = FastAPI(title="Document Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root():
    return {"service": "Document Service", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "healthy"}
