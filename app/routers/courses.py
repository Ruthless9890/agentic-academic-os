from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Assignment, Course, DocumentChunk, Exam
from app.schemas import CourseDetail

router = APIRouter(tags=["courses"])


@router.get("/courses/{course_id}", response_model=CourseDetail)
async def get_course(course_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Course)
        .where(Course.id == course_id)
        .options(selectinload(Course.assignments), selectinload(Course.exams))
    )
    result = await db.execute(stmt)
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.delete("/courses/{course_id}")
async def delete_course(course_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    course_name = course.name

    await db.execute(delete(DocumentChunk).where(DocumentChunk.course_id == course_id))
    await db.execute(delete(Assignment).where(Assignment.course_id == course_id))
    await db.execute(delete(Exam).where(Exam.course_id == course_id))
    await db.execute(delete(Course).where(Course.id == course_id))
    await db.commit()

    return {"message": f'Course "{course_name}" and all related assignments, exams, and document chunks were deleted.'}
