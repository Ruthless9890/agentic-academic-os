from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Alert
from app.schemas import AlertRead

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=list[AlertRead])
async def list_alerts(
    course_id: Optional[int] = Query(None),
    unread_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Alert)
    if course_id is not None:
        stmt = stmt.where(Alert.course_id == course_id)
    if unread_only:
        stmt = stmt.where(Alert.is_read.is_(False))
    stmt = stmt.order_by(Alert.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.patch("/alerts/read-all")
async def mark_all_read(course_id: Optional[int] = Query(None), db: AsyncSession = Depends(get_db)):
    stmt = update(Alert).where(Alert.is_read.is_(False))
    if course_id is not None:
        stmt = stmt.where(Alert.course_id == course_id)
    stmt = stmt.values(is_read=True)
    result = await db.execute(stmt)
    await db.commit()
    return {"updated": result.rowcount}


@router.patch("/alerts/{alert_id}/read", response_model=AlertRead)
async def mark_read(alert_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_read = True
    await db.commit()
    await db.refresh(alert)
    return alert


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.delete(alert)
    await db.commit()
    return {"message": "Alert dismissed."}
