from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from icalendar import Calendar, Event

from app.database import get_db
from app.models import Course

router = APIRouter(tags=["calendar"])


def _build_calendar(courses: list[Course]) -> Calendar:
    cal = Calendar()
    cal.add("prodid", "-//Academic OS//Calendar Export//EN")
    cal.add("version", "2.0")

    for course in courses:
        late_policy = course.late_policy or "No late policy specified"
        for a in course.assignments:
            if not a.due_date:
                continue
            event = Event()
            event.add("summary", f"{a.name} ({course.name})")
            event.add("dtstart", a.due_date)
            event.add("dtend", a.due_date)
            event.add("description", (
                f"Weight: {a.weight if a.weight is not None else 'n/a'}%\n"
                f"Status: {a.status.value}\n"
                f"Late policy: {late_policy}"
            ))
            event.add("uid", f"assignment-{a.id}@academic-os")
            cal.add_component(event)

        for e in course.exams:
            if not e.date:
                continue
            event = Event()
            event.add("summary", f"{e.name} ({course.name})")
            event.add("dtstart", e.date)
            event.add("dtend", e.date)
            event.add("description", f"Weight: {e.weight if e.weight is not None else 'n/a'}%")
            event.add("uid", f"exam-{e.id}@academic-os")
            cal.add_component(event)

    return cal


def _ics_response(cal: Calendar, filename: str) -> Response:
    return Response(
        content=bytes(cal.to_ical()),
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/courses/all/export/ical")
async def export_all_courses_ical(db: AsyncSession = Depends(get_db)):
    stmt = select(Course).options(selectinload(Course.assignments), selectinload(Course.exams))
    result = await db.execute(stmt)
    courses = list(result.scalars().all())
    cal = _build_calendar(courses)
    return _ics_response(cal, "academic_os_all_courses.ics")


@router.get("/courses/{course_id}/export/ical")
async def export_course_ical(course_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Course)
        .where(Course.id == course_id)
        .options(selectinload(Course.assignments), selectinload(Course.exams))
    )
    result = await db.execute(stmt)
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    cal = _build_calendar([course])
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in course.name).strip() or "course"
    return _ics_response(cal, f"{safe_name}.ics")
