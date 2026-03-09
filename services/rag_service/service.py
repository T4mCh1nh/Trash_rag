import logging

import httpx
import google.generativeai as genai

from config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

genai.configure(api_key=settings.gemini_api_key)
gemini_model = genai.GenerativeModel(settings.gemini_model)


def search_relevant_chunks(query: str, chat_id: int, top_k: int | None = None) -> list[dict]:
    if top_k is None:
        top_k = settings.retrieval_top_k

    try:
        response = httpx.post(
            f"{settings.document_service_url}/internal/search",
            json={"query": query, "chat_id": chat_id, "top_k": top_k},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("chunks", [])
    except httpx.RequestError as e:
        logger.error(f"Document Service unreachable: {e}")
        return []
    except httpx.HTTPStatusError as e:
        logger.error(f"Document Service error: {e.response.text}")
        return []


def build_rag_prompt(query: str, context_chunks: list[dict]) -> str:
    context_parts = []
    for i, chunk in enumerate(context_chunks, 1):
        meta = chunk.get("metadata", {})
        source_info = ""
        if meta.get("headings"):
            source_info = f" (Section: {' > '.join(meta['headings'])})"
        if meta.get("page"):
            source_info += f" (Page {meta['page']})"
        context_parts.append(f"[{i}]{source_info}\n{chunk['text']}")

    context = "\n\n---\n\n".join(context_parts)

    prompt = f"""You are a helpful assistant that answers questions based on the provided document context.
Use ONLY the information from the context below to answer the question.
If the context doesn't contain enough information to answer, say so clearly.
When relevant, cite the source numbers in square brackets like [1], [2], etc.
Answer in the same language as the question.

CONTEXT:
{context}

QUESTION: {query}

ANSWER:"""

    return prompt


def generate_rag_response(query: str, chat_id: int) -> tuple[str, list[dict]]:
    chunks = search_relevant_chunks(query, chat_id)

    if not chunks:
        return (
            "Ko có tài liệu liên quan. Up file lên trước.",
            [],
        )

    prompt = build_rag_prompt(query, chunks)

    response = gemini_model.generate_content(prompt)
    answer = response.text

    sources = []
    for chunk in chunks:
        text = chunk["text"]
        sources.append(
            {
                "text": text[:200] + "..." if len(text) > 200 else text,
                "metadata": chunk.get("metadata", {}),
                "document_id": chunk.get("document_id"),
            }
        )

    return answer, sources
