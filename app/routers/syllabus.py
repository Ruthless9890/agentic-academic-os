import json
import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import fitz  # pymupdf
from openai import AsyncOpenAI

from app.database import get_db
from app.models import Course, Assignment, Exam
from app.routers.documents import embed_and_store_document
from app.schemas import SyllabusExtraction, SyllabusUploadResponse

router = APIRouter(prefix="/syllabus", tags=["syllabus"])

_openai = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

EXTRACTION_PROMPT = """You are an academic assistant extracting structured grading information from a syllabus.

Extraction rules:
- Extract INDIVIDUAL assignments by name with their specific due dates whenever the syllabus lists them
  individually (e.g. "Homework 1 - due Sept 10", "Lab 3 - due Oct 2"). Do not collapse multiple individual
  assignments into one category entry.
- If the syllabus only describes grade CATEGORIES rather than individual assignments (e.g. "Homework: 30%
  of grade" with no individual items listed), create exactly ONE entry per category using that category's
  name and weight, with due_date set to null.
- Extract INDIVIDUAL exams by name with their specific dates (e.g. "Midterm Exam - Oct 15", "Final Exam -
  Dec 12"). Do not group multiple exams into a single entry.
- Every weight you return must be a percentage that reflects the item's actual contribution to the final
  course grade, as stated or clearly implied by the syllabus (e.g. "worth 20% of your grade" -> 20).
- If the syllabus states a total point value for the entire course (e.g. "this course is worth 1000 points
  total"), include it in "total_course_points". Otherwise set it to null.

Return ONLY valid JSON with this exact shape:
{
  "course_name": "string",
  "professor": "string or null",
  "late_policy": "string or null",
  "total_course_points": number or null,
  "assignments": [
    {"name": "string", "due_date": "YYYY-MM-DD or null", "weight_percent": number or null}
  ],
  "exams": [
    {"name": "string", "date": "YYYY-MM-DD or null", "weight_percent": number or null}
  ]
}

Syllabus text:
"""


def _normalize_weights(extraction: SyllabusExtraction) -> None:
    """Rescale extracted weights so assignments + exams combined sum to exactly 100%."""
    total = sum((a.weight_percent or 0) for a in extraction.assignments) + sum(
        (e.weight_percent or 0) for e in extraction.exams
    )
    if total <= 0:
        return
    for a in extraction.assignments:
        if a.weight_percent is not None:
            a.weight_percent = (a.weight_percent / total) * 100
    for e in extraction.exams:
        if e.weight_percent is not None:
            e.weight_percent = (e.weight_percent / total) * 100


@router.post("/upload-syllabus", response_model=SyllabusUploadResponse)
async def upload_syllabus(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    contents = await file.read()

    # Extract text from PDF
    try:
        doc = fitz.open(stream=contents, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse PDF: {exc}")

    if not text.strip():
        raise HTTPException(status_code=422, detail="PDF contains no extractable text.")

    # Ask OpenAI to extract structured data
    try:
        response = await _openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": EXTRACTION_PROMPT + text[:12000]},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = response.choices[0].message.content
        extraction = SyllabusExtraction.model_validate(json.loads(raw))
        _normalize_weights(extraction)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI extraction failed: {exc}")

    # If a course with this name already exists, don't create a duplicate — just
    # re-index the syllabus text against it (useful for improving RAG on a re-upload)
    # and hand back the existing course untouched.
    existing_result = await db.execute(
        select(Course).where(func.lower(Course.name) == extraction.course_name.strip().lower())
    )
    existing_course = existing_result.scalar_one_or_none()

    if existing_course is not None:
        await embed_and_store_document(db, existing_course.id, file.filename, "syllabus", text)
        await db.commit()
        await db.refresh(existing_course)
        return SyllabusUploadResponse(
            course=existing_course,
            assignments_created=0,
            exams_created=0,
            message="Course already exists, returning existing course.",
        )

    # Persist course
    course = Course(
        name=extraction.course_name,
        professor=extraction.professor,
        late_policy=extraction.late_policy,
    )
    db.add(course)
    await db.flush()  # get course.id before adding children

    # Persist assignments
    for a in extraction.assignments:
        db.add(Assignment(
            course_id=course.id,
            name=a.name,
            due_date=a.due_date,
            weight=a.weight_percent,
        ))

    # Persist exams
    for e in extraction.exams:
        db.add(Exam(
            course_id=course.id,
            name=e.name,
            date=e.date,
            weight=e.weight_percent,
        ))

    # Index the raw syllabus text too, so it shows up in Course Materials and is searchable by RAG
    await embed_and_store_document(db, course.id, file.filename, "syllabus", text)

    await db.commit()
    await db.refresh(course)

    return SyllabusUploadResponse(
        course=course,
        assignments_created=len(extraction.assignments),
        exams_created=len(extraction.exams),
    )
