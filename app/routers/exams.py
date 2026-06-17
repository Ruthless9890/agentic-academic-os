from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Course, Exam
from app.schemas import ExamCreate, ExamRead

router = APIRouter(tags=["exams"])


@router.post("/exams/add", response_model=ExamRead, status_code=201)
async def add_exam(body: ExamCreate, db: AsyncSession = Depends(get_db)):
    course_result = await db.execute(select(Course).where(Course.id == body.course_id))
    if course_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Course not found")

    exam = Exam(
        course_id=body.course_id,
        name=body.name,
        date=body.date,
        weight=body.weight,
    )
    db.add(exam)
    await db.commit()
    await db.refresh(exam)
    return exam
