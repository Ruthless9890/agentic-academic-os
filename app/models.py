from datetime import date, datetime
from sqlalchemy import ForeignKey, String, Float, Date, DateTime, Text, Enum as SAEnum, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
import enum

from app.database import Base


class AssignmentStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class AlertType(str, enum.Enum):
    due_tomorrow = "due_tomorrow"
    due_in_3_days = "due_in_3_days"
    overdue = "overdue"
    exam_proximity = "exam_proximity"
    heavy_week = "heavy_week"
    inactivity = "inactivity"


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    professor: Mapped[str | None] = mapped_column(String(255))
    late_policy: Mapped[str | None] = mapped_column(String(1024))

    assignments: Mapped[list["Assignment"]] = relationship(back_populates="course", cascade="all, delete-orphan")
    exams: Mapped[list["Exam"]] = relationship(back_populates="course", cascade="all, delete-orphan")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="course", cascade="all, delete-orphan")


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    weight: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[AssignmentStatus] = mapped_column(
        SAEnum(AssignmentStatus), default=AssignmentStatus.pending, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    course: Mapped["Course"] = relationship(back_populates="assignments")


class Exam(Base):
    __tablename__ = "exams"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float)

    course: Mapped["Course"] = relationship(back_populates="exams")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = Column(Vector(1536), nullable=False)
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False, default="syllabus")
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    course: Mapped["Course"] = relationship(back_populates="chunks")


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True)
    pending_update_assignment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assignments.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("conversation_sessions.id"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(SAEnum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    session: Mapped["ConversationSession"] = relationship(back_populates="messages")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True)
    alert_type: Mapped[AlertType] = mapped_column(SAEnum(AlertType), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    is_read: Mapped[bool] = mapped_column(default=False, nullable=False)
