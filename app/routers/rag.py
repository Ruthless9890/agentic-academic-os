import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI

from app.database import get_db
from app.models import Course, DocumentChunk

router = APIRouter(prefix="/rag", tags=["rag"])

_openai = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
EMBED_MODEL = "text-embedding-3-small"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def _build_syllabus_text(course: Course) -> str:
    lines = [
        f"Course: {course.name}",
        f"Professor: {course.professor or 'Not specified'}",
        f"Late Policy: {course.late_policy or 'No late policy specified'}",
        "",
        "Assignments:",
    ]
    for a in course.assignments:
        lines.append(f"  - {a.name}, due: {a.due_date}, weight: {a.weight}%")
    lines += ["", "Exams:"]
    for e in course.exams:
        lines.append(f"  - {e.name}, date: {e.date}, weight: {e.weight}%")
    return "\n".join(lines)


def _chunk_text(text: str) -> list[str]:
    step = CHUNK_SIZE - CHUNK_OVERLAP
    return [
        chunk
        for i in range(0, len(text), step)
        if (chunk := text[i : i + CHUNK_SIZE].strip())
    ]


@router.post("/embed-syllabus/{course_id}")
async def embed_syllabus(course_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Course)
        .where(Course.id == course_id)
        .options(selectinload(Course.assignments), selectinload(Course.exams))
    )
    result = await db.execute(stmt)
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    text = _build_syllabus_text(course)
    chunks = _chunk_text(text)
    if not chunks:
        raise HTTPException(status_code=422, detail="No text content to embed for this course.")

    # replace any existing chunks for this course
    await db.execute(delete(DocumentChunk).where(DocumentChunk.course_id == course_id))

    # batch embed all chunks in one API call
    embed_response = await _openai.embeddings.create(model=EMBED_MODEL, input=chunks)
    embeddings = [item.embedding for item in embed_response.data]

    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        db.add(DocumentChunk(
            course_id=course_id,
            content=chunk,
            embedding=embedding,
            chunk_index=i,
        ))

    await db.commit()
    return {"course_id": course_id, "chunks_stored": len(chunks)}


class AskRequest(BaseModel):
    course_id: int
    question: str


@router.post("/ask")
async def ask(body: AskRequest, db: AsyncSession = Depends(get_db)):
    # embed the question
    q_embed = await _openai.embeddings.create(model=EMBED_MODEL, input=body.question)
    q_vector = q_embed.data[0].embedding

    # cosine similarity search via pgvector <=> operator
    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.course_id == body.course_id)
        .order_by(DocumentChunk.embedding.cosine_distance(q_vector))
        .limit(3)
    )
    result = await db.execute(stmt)
    chunks = result.scalars().all()

    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="No document chunks found for this course. Call POST /rag/embed-syllabus/{course_id} first.",
        )

    context = "\n\n---\n\n".join(c.content for c in chunks)

    chat = await _openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful academic assistant. Answer the student's question "
                    "using only the provided course document context. Be concise and accurate."
                ),
            },
            {
                "role": "user",
                "content": f"Context from course documents:\n\n{context}\n\nQuestion: {body.question}",
            },
        ],
        temperature=0,
    )

    return {
        "answer": chat.choices[0].message.content,
        "chunks_used": len(chunks),
    }
