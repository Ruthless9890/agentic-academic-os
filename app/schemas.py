import datetime
from pydantic import BaseModel, ConfigDict
from typing import Optional
from app.models import AlertType, AssignmentStatus, MessageRole


class CourseBase(BaseModel):
    name: str
    professor: Optional[str] = None
    late_policy: Optional[str] = None


class CourseCreate(CourseBase):
    pass


class CourseRead(CourseBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class AssignmentBase(BaseModel):
    name: str
    due_date: Optional[datetime.date] = None
    weight: Optional[float] = None
    score: Optional[float] = None
    status: AssignmentStatus = AssignmentStatus.pending


class AssignmentCreate(AssignmentBase):
    course_id: int


class AssignmentRead(AssignmentBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    course_id: int


class ExamBase(BaseModel):
    name: str
    date: Optional[datetime.date] = None  # use datetime.date to avoid shadowing the field name
    weight: Optional[float] = None


class ExamCreate(ExamBase):
    course_id: int


class ExamRead(ExamBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    course_id: int


# Shape expected from the OpenAI extraction response
class ExtractedAssignment(BaseModel):
    name: str
    due_date: Optional[datetime.date] = None
    weight_percent: Optional[float] = None


class ExtractedExam(BaseModel):
    name: str
    date: Optional[datetime.date] = None
    weight_percent: Optional[float] = None


class SyllabusExtraction(BaseModel):
    course_name: str
    professor: Optional[str] = None
    late_policy: Optional[str] = None
    total_course_points: Optional[float] = None
    assignments: list[ExtractedAssignment] = []
    exams: list[ExtractedExam] = []


class SyllabusUploadResponse(BaseModel):
    course: CourseRead
    assignments_created: int
    exams_created: int
    message: Optional[str] = None


class AssignmentWithPriority(AssignmentRead):
    priority_score: float


class AssignmentStatusUpdate(BaseModel):
    status: AssignmentStatus


class AssignmentScoreUpdate(BaseModel):
    score: float


class AssignmentUpdate(BaseModel):
    name: Optional[str] = None
    due_date: Optional[datetime.date] = None
    weight: Optional[float] = None
    status: Optional[AssignmentStatus] = None
    score: Optional[float] = None


class CourseDetail(CourseRead):
    assignments: list[AssignmentRead] = []
    exams: list[ExamRead] = []


class ConversationMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: MessageRole
    content: str
    intent: Optional[str] = None
    created_at: datetime.datetime


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    course_id: Optional[int] = None
    alert_type: AlertType
    message: str
    created_at: datetime.datetime
    is_read: bool
