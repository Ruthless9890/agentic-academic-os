import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import build_graph
from app.database import get_db
from app.models import ConversationMessage, ConversationSession, MessageRole
from app.schemas import ConversationMessageRead

router = APIRouter(tags=["chat"])

HISTORY_LIMIT = 10


class ChatRequest(BaseModel):
    message: str
    course_id: Optional[int] = None
    session_id: Optional[int] = None


class ChatResponse(BaseModel):
    response: str
    intent: str
    course: Optional[str] = None
    session_id: int


async def _fetch_recent_history(db: AsyncSession, session_id: int, limit: int = HISTORY_LIMIT) -> list[dict]:
    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    messages = list(result.scalars().all())
    messages.reverse()  # oldest first, for natural reading order in prompts
    return [{"role": m.role.value, "content": m.content, "intent": m.intent} for m in messages]


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db)):
    if body.session_id is not None:
        result = await db.execute(
            select(ConversationSession).where(ConversationSession.id == body.session_id)
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        history = await _fetch_recent_history(db, session.id)
    else:
        session = ConversationSession(course_id=body.course_id)
        db.add(session)
        await db.flush()  # assign session.id before the graph runs
        history = []

    graph = build_graph(db)
    result = await graph.ainvoke({
        "message": body.message,
        "course_id": body.course_id,
        "all_courses": [],
        "resolved_course_id": None,
        "is_multi_course": False,
        "intent": None,
        "db_context": None,
        "rag_context": None,
        "conversation_history": history,
        "response": None,
        "pending_update": session.pending_update_assignment_id,
        "resolved_entity": None,
    })

    session.pending_update_assignment_id = result.get("pending_update")

    course_name = None
    if result.get("is_multi_course"):
        course_name = "multiple courses"
    elif result.get("db_context") and result["db_context"].get("course"):
        course_name = result["db_context"]["course"]["name"]

    db.add(ConversationMessage(session_id=session.id, role=MessageRole.user, content=body.message))
    db.add(ConversationMessage(
        session_id=session.id,
        role=MessageRole.assistant,
        content=result["response"],
        intent=result.get("intent"),
    ))
    session.updated_at = datetime.datetime.utcnow()
    await db.commit()

    return ChatResponse(
        response=result["response"],
        intent=result.get("intent") or "",
        course=course_name,
        session_id=session.id,
    )


@router.get("/chat/sessions/{session_id}/history", response_model=list[ConversationMessageRead])
async def get_session_history(session_id: int, db: AsyncSession = Depends(get_db)):
    session_result = await db.execute(
        select(ConversationSession).where(ConversationSession.id == session_id)
    )
    if session_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Session not found")

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
