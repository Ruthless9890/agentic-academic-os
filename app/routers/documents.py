import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
import fitz  # pymupdf
from openai import AsyncOpenAI

from app.database import get_db
from app.models import Course, DocumentChunk
from app.routers.rag import _chunk_text, EMBED_MODEL

router = APIRouter(tags=["documents"])

_openai = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


async def embed_and_store_document(db: AsyncSession, course_id: int, filename: str, doc_type: str, text: str) -> int:
    """Chunk + embed `text` and store it as document_chunks for course_id. Caller commits."""
    chunks = _chunk_text(text)
    if not chunks:
        return 0

    embed_response = await _openai.embeddings.create(model=EMBED_MODEL, input=chunks)
    embeddings = [item.embedding for item in embed_response.data]

    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        db.add(DocumentChunk(
            course_id=course_id,
            content=chunk,
            embedding=embedding,
            chunk_index=i,
            doc_type=doc_type,
            filename=filename,
        ))
    return len(chunks)


@router.post("/courses/{course_id}/upload-document")
async def upload_document(
    course_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    course_result = await db.execute(select(Course).where(Course.id == course_id))
    if course_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Course not found")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    contents = await file.read()

    try:
        doc = fitz.open(stream=contents, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse PDF: {exc}")

    if not text.strip():
        raise HTTPException(status_code=422, detail="PDF contains no extractable text.")

    chunks_created = await embed_and_store_document(db, course_id, file.filename, "document", text)
    if chunks_created == 0:
        raise HTTPException(status_code=422, detail="No text content to embed for this document.")

    await db.commit()
    return {"filename": file.filename, "chunks_created": chunks_created}


@router.get("/courses/{course_id}/documents")
async def list_documents(course_id: int, db: AsyncSession = Depends(get_db)):
    course_result = await db.execute(select(Course).where(Course.id == course_id))
    if course_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Course not found")

    stmt = (
        select(
            func.min(DocumentChunk.id).label("id"),
            DocumentChunk.filename,
            DocumentChunk.doc_type,
            func.count(DocumentChunk.id).label("chunk_count"),
            func.min(DocumentChunk.created_at).label("created_at"),
        )
        .where(DocumentChunk.course_id == course_id, DocumentChunk.filename.is_not(None))
        .group_by(DocumentChunk.filename, DocumentChunk.doc_type)
        .order_by(func.min(DocumentChunk.created_at).desc())
    )
    result = await db.execute(stmt)
    return [
        {
            "id": row.id,
            "filename": row.filename,
            "doc_type": row.doc_type,
            "chunk_count": row.chunk_count,
            "created_at": row.created_at,
        }
        for row in result.all()
    ]


@router.delete("/courses/{course_id}/documents/{doc_id}")
async def delete_document(course_id: int, doc_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DocumentChunk).where(DocumentChunk.id == doc_id, DocumentChunk.course_id == course_id)
    )
    chunk = result.scalar_one_or_none()
    if chunk is None:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.execute(
        delete(DocumentChunk).where(
            DocumentChunk.course_id == course_id, DocumentChunk.filename == chunk.filename
        )
    )
    await db.commit()
    return {"status": "deleted"}
