import datetime
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Assignment, Course, AssignmentStatus
from app.schemas import (
    AssignmentCreate,
    AssignmentRead,
    AssignmentScoreUpdate,
    AssignmentStatusUpdate,
    AssignmentUpdate,
    AssignmentWithPriority,
    CourseRead,
)

router = APIRouter(tags=["assignments"])


def _priority_score(a: Assignment) -> float:
    score = a.weight or 0.0
    if a.due_date is not None:
        days = (a.due_date - datetime.date.today()).days
        if days < 0:
            score += 100
        elif days <= 3:
            score += 50
        elif days <= 7:
            score += 30
        elif days <= 14:
            score += 10
    return score


@router.post("/assignments/add", response_model=AssignmentRead, status_code=201)
async def add_assignment(body: AssignmentCreate, db: AsyncSession = Depends(get_db)):
    course_result = await db.execute(select(Course).where(Course.id == body.course_id))
    if course_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Course not found")

    assignment = Assignment(
        course_id=body.course_id,
        name=body.name,
        due_date=body.due_date,
        weight=body.weight,
        score=body.score,
        status=body.status,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    return assignment


@router.get("/assignments/due-this-week", response_model=list[AssignmentRead])
async def due_this_week(db: AsyncSession = Depends(get_db)):
    today = datetime.date.today()
    cutoff = today + timedelta(days=7)
    stmt = select(Assignment).where(
        Assignment.due_date >= today,
        Assignment.due_date <= cutoff,
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/assignments/overdue", response_model=list[AssignmentRead])
async def overdue(db: AsyncSession = Depends(get_db)):
    stmt = select(Assignment).where(
        Assignment.due_date < datetime.date.today(),
        Assignment.status != AssignmentStatus.completed,
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/assignments/priority", response_model=list[AssignmentWithPriority])
async def priority_list(db: AsyncSession = Depends(get_db)):
    stmt = select(Assignment).where(
        Assignment.status.in_([AssignmentStatus.pending, AssignmentStatus.in_progress])
    )
    result = await db.execute(stmt)
    assignments = result.scalars().all()
    scored = sorted(
        [{"assignment": a, "score": _priority_score(a)} for a in assignments],
        key=lambda x: x["score"],
        reverse=True,
    )
    out = []
    for item in scored:
        a = item["assignment"]
        out.append(AssignmentWithPriority(
            id=a.id,
            course_id=a.course_id,
            name=a.name,
            due_date=a.due_date,
            weight=a.weight,
            status=a.status,
            priority_score=item["score"],
        ))
    return out


@router.get("/assignments", response_model=list[AssignmentRead])
async def list_assignments(
    status: Optional[AssignmentStatus] = Query(None),
    course_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Assignment)
    if status is not None:
        stmt = stmt.where(Assignment.status == status)
    if course_id is not None:
        stmt = stmt.where(Assignment.course_id == course_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.patch("/assignments/{assignment_id}/status", response_model=AssignmentRead)
async def update_status(
    assignment_id: int,
    body: AssignmentStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Assignment).where(Assignment.id == assignment_id))
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    assignment.status = body.status
    await db.commit()
    await db.refresh(assignment)
    return assignment


@router.patch("/assignments/{assignment_id}/score", response_model=AssignmentRead)
async def update_score(
    assignment_id: int,
    body: AssignmentScoreUpdate,
    db: AsyncSession = Depends(get_db),
):
    if not (0 <= body.score <= 100):
        raise HTTPException(status_code=422, detail="Score must be between 0 and 100")
    result = await db.execute(select(Assignment).where(Assignment.id == assignment_id))
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    assignment.score = body.score
    await db.commit()
    await db.refresh(assignment)
    return assignment


@router.patch("/assignments/{assignment_id}", response_model=AssignmentRead)
async def edit_assignment(
    assignment_id: int,
    body: AssignmentUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Assignment).where(Assignment.id == assignment_id))
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")

    update_data = body.model_dump(exclude_unset=True)
    if "score" in update_data and update_data["score"] is not None:
        if not (0 <= update_data["score"] <= 100):
            raise HTTPException(status_code=422, detail="Score must be between 0 and 100")
    for field, value in update_data.items():
        setattr(assignment, field, value)

    await db.commit()
    await db.refresh(assignment)
    return assignment


@router.get("/courses", response_model=list[CourseRead])
async def list_courses(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Course))
    return result.scalars().all()
