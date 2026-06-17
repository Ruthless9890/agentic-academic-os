import datetime
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import Alert, AlertType, Assignment, AssignmentStatus, Course, Exam

logger = logging.getLogger("alerts")


async def _alert_exists(db: AsyncSession, course_id: int | None, alert_type: AlertType, message: str) -> bool:
    stmt = select(Alert).where(
        Alert.course_id == course_id,
        Alert.alert_type == alert_type,
        Alert.message == message,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _create_alert(db: AsyncSession, course_id: int | None, alert_type: AlertType, message: str) -> None:
    if await _alert_exists(db, course_id, alert_type, message):
        return
    db.add(Alert(course_id=course_id, alert_type=alert_type, message=message))
    logger.info("New alert [%s] course=%s: %s", alert_type.value, course_id, message)


async def check_due_tomorrow(db: AsyncSession) -> None:
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    stmt = select(Assignment).where(
        Assignment.due_date == tomorrow,
        Assignment.status != AssignmentStatus.completed,
    )
    result = await db.execute(stmt)
    for a in result.scalars().all():
        message = f"⚠️ Due tomorrow: {a.name} ({a.weight}% of grade)"
        await _create_alert(db, a.course_id, AlertType.due_tomorrow, message)


async def check_due_in_3_days(db: AsyncSession) -> None:
    target = datetime.date.today() + datetime.timedelta(days=3)
    stmt = select(Assignment).where(
        Assignment.due_date == target,
        Assignment.status != AssignmentStatus.completed,
    )
    result = await db.execute(stmt)
    for a in result.scalars().all():
        message = f"📅 Coming up in 3 days: {a.name} ({a.weight}%)"
        await _create_alert(db, a.course_id, AlertType.due_in_3_days, message)


async def check_overdue(db: AsyncSession) -> None:
    today = datetime.date.today()
    stmt = select(Assignment).where(
        Assignment.due_date < today,
        Assignment.status != AssignmentStatus.completed,
    )
    result = await db.execute(stmt)
    for a in result.scalars().all():
        days = (today - a.due_date).days
        message = f"🚨 Overdue: {a.name} is {days} days past due ({a.weight}%)"
        await _create_alert(db, a.course_id, AlertType.overdue, message)


async def check_exam_proximity(db: AsyncSession) -> None:
    today = datetime.date.today()
    cutoff = today + datetime.timedelta(days=7)
    stmt = select(Exam).where(Exam.date >= today, Exam.date <= cutoff)
    result = await db.execute(stmt)
    for e in result.scalars().all():
        days = (e.date - today).days
        message = f"📝 Exam in {days} days: {e.name} ({e.weight}% of grade)"
        await _create_alert(db, e.course_id, AlertType.exam_proximity, message)


async def check_heavy_week(db: AsyncSession) -> None:
    today = datetime.date.today()
    week_end = today + datetime.timedelta(days=7)

    courses_result = await db.execute(select(Course))
    for course in courses_result.scalars().all():
        a_result = await db.execute(
            select(Assignment).where(
                Assignment.course_id == course.id,
                Assignment.status != AssignmentStatus.completed,
                Assignment.due_date >= today,
                Assignment.due_date <= week_end,
            )
        )
        assignments = list(a_result.scalars().all())

        e_result = await db.execute(
            select(Exam).where(
                Exam.course_id == course.id,
                Exam.date >= today,
                Exam.date <= week_end,
            )
        )
        exams = list(e_result.scalars().all())

        total_weight = sum(a.weight or 0 for a in assignments) + sum(e.weight or 0 for e in exams)
        count = len(assignments) + len(exams)

        if total_weight > 30:
            message = f"🔥 Heavy week ahead: {total_weight:.1f}% of your grade is due this week across {count} items"
            await _create_alert(db, course.id, AlertType.heavy_week, message)


async def check_inactivity(db: AsyncSession) -> None:
    any_result = await db.execute(select(Assignment).limit(1))
    if any_result.scalar_one_or_none() is None:
        return  # nothing to be inactive about

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=5)
    recent_result = await db.execute(select(Assignment).where(Assignment.updated_at >= cutoff).limit(1))
    if recent_result.scalar_one_or_none() is not None:
        return  # there was activity within the last 5 days

    message = "👀 You haven't logged any progress in 5 days. Check in on your assignments!"
    await _create_alert(db, None, AlertType.inactivity, message)


async def run_all_checks() -> None:
    async with AsyncSessionLocal() as db:
        await check_due_tomorrow(db)
        await check_due_in_3_days(db)
        await check_overdue(db)
        await check_exam_proximity(db)
        await check_heavy_week(db)
        await check_inactivity(db)
        await db.commit()
    logger.info("Alert checks completed")
