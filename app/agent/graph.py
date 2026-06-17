import datetime
import json
import os
import re
from typing import Optional, TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assignment, AssignmentStatus, Course, DocumentChunk, Exam

EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o-mini"

VALID_INTENTS = ["WHAT", "HOW_BAD", "PLAN", "UPDATE", "CRISIS", "MULTI_COURSE"]

MULTI_COURSE_KEYWORDS = [
    "which course",
    "which of my courses",
    "all my courses",
    "all courses",
    "every course",
    "across my courses",
    "compare my courses",
    "compare all",
    "rank my courses",
    "total workload",
    "all my deadlines",
    "everything i have due",
    "most behind",
    "most attention",
]

_llm = ChatOpenAI(model=CHAT_MODEL, temperature=0, api_key=os.environ.get("OPENAI_API_KEY"))
_openai = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


class AgentState(TypedDict):
    message: str
    course_id: Optional[int]
    all_courses: list
    resolved_course_id: Optional[int]
    is_multi_course: bool
    intent: Optional[str]
    db_context: Optional[dict]
    rag_context: Optional[str]
    conversation_history: list
    response: Optional[str]
    pending_update: Optional[int]
    resolved_entity: Optional[str]


INTENT_PROMPT = """Classify the user's message into exactly one of these intents:

- WHAT: pure information retrieval — what is due, when is an exam, late policy, grade breakdown, how much something is worth, who teaches it, exam topics
- HOW_BAD: damage assessment — am I cooked, how behind am I, can I still pass, impact of skipping something, current grade, highest grade still possible, what if I fail something
- PLAN: future action — what should I study, available time mentioned, schedule requests, prioritizing work, how to prepare for something
- UPDATE: state change — I finished/started/submitted something, mark something as done or in progress
- CRISIS: overwhelmed or situational distress — sick for a stretch of time, don't know where to start, haven't done anything all semester, thinking of dropping, missed an exam, everything due at once
- MULTI_COURSE: spans more than one course — which course needs attention, all deadlines across courses, total workload, comparing/ranking courses

{history_block}The message may be a short follow-up that only makes sense in light of the conversation above
(e.g. "what about the exam?" after a grade question is probably HOW_BAD, not WHAT; "when is it due?" after
naming an assignment is WHAT). Use the conversation to resolve what "it"/"that"/"the same thing" refers to
before picking the intent.

{hint}
Message: {message}

Respond with only the intent label (WHAT, HOW_BAD, PLAN, UPDATE, CRISIS, or MULTI_COURSE), nothing else."""


# ---- shared helpers ---------------------------------------------------------

async def _fetch_all_courses(db: AsyncSession) -> list[Course]:
    result = await db.execute(select(Course))
    return list(result.scalars().all())


async def _fetch_assignments(db: AsyncSession, course_id: int) -> list[Assignment]:
    result = await db.execute(select(Assignment).where(Assignment.course_id == course_id))
    return list(result.scalars().all())


async def _fetch_exams(db: AsyncSession, course_id: int) -> list[Exam]:
    result = await db.execute(select(Exam).where(Exam.course_id == course_id))
    return list(result.scalars().all())


def _assignment_to_dict(a: Assignment) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "due_date": a.due_date.isoformat() if a.due_date else None,
        "weight": a.weight,
        "score": a.score,
        "status": a.status.value,
    }


def _exam_to_dict(e: Exam) -> dict:
    return {
        "id": e.id,
        "name": e.name,
        "date": e.date.isoformat() if e.date else None,
        "weight": e.weight,
    }


async def _rag_chunks(db: AsyncSession, course_id: int, question: str, k: int = 3) -> list[DocumentChunk]:
    q_embed = await _openai.embeddings.create(model=EMBED_MODEL, input=question)
    q_vector = q_embed.data[0].embedding
    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.course_id == course_id)
        .order_by(DocumentChunk.embedding.cosine_distance(q_vector))
        .limit(k)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _format_recent_history(history: Optional[list], max_exchanges: int = 3) -> str:
    """Render the last `max_exchanges` user/assistant turns for inclusion in a prompt."""
    if not history:
        return ""
    recent = history[-(max_exchanges * 2):]
    lines = []
    for m in recent:
        speaker = "Student" if m.get("role") == "user" else "Assistant"
        lines.append(f"{speaker}: {m.get('content', '')}")
    return "\n".join(lines)


async def _answer_with_context(question: str, context: str, instructions: str, history: str = "") -> str:
    history_block = f"Recent conversation:\n{history}\n\n" if history else ""
    prompt = (
        f"{instructions}\n\n{history_block}Data:\n{context}\n\n"
        f'Student\'s question: "{question}"\n\n'
        "Answer naturally and concisely using only the data given. If the question refers back to "
        "something from the recent conversation above (e.g. \"it\", \"that one\", \"what about...\"), "
        "resolve the reference using that conversation history."
    )
    result = await _llm.ainvoke(prompt)
    return result.content


def _format_db_context(db_ctx: Optional[dict]) -> str:
    if not db_ctx:
        return "No course context available."
    lines = [f"Today's date: {datetime.date.today().isoformat()}"]
    course = db_ctx.get("course")
    if course:
        lines.append(f"Course: {course['name']}")
        lines.append(f"Professor: {course['professor'] or 'Not specified'}")
        lines.append(f"Late policy: {course['late_policy'] or 'No late policy specified'}")
    lines.append("Assignments:")
    for a in db_ctx.get("assignments", []):
        score_part = f", score {a['score']}/100" if a.get("score") is not None else ", not yet graded"
        lines.append(f"- {a['name']}: weight {a['weight']}%, status {a['status']}{score_part}, due {a['due_date'] or 'no due date'}")
    lines.append("Exams:")
    for e in db_ctx.get("exams", []):
        lines.append(f"- {e['name']}: weight {e['weight']}%, date {e['date'] or 'no date'}")
    return "\n".join(lines)


def _filter_db_context_to_entity(db_ctx: Optional[dict], entity_name: str) -> Optional[dict]:
    """Narrow a db_context to just the named assignment/exam, if it's actually in there."""
    if not db_ctx:
        return db_ctx
    name_l = entity_name.lower()
    assignments = [a for a in db_ctx.get("assignments", []) if a["name"].lower() == name_l]
    exams = [e for e in db_ctx.get("exams", []) if e["name"].lower() == name_l]
    if not assignments and not exams:
        return db_ctx
    return {**db_ctx, "assignments": assignments, "exams": exams}


def _extract_entity_from_text(text: Optional[str], db_ctx: Optional[dict]) -> Optional[str]:
    """Return the single assignment/exam name mentioned in text, or None if zero or several match."""
    if not text or not db_ctx:
        return None
    text_l = text.lower()
    names = [a["name"] for a in db_ctx.get("assignments", [])] + [e["name"] for e in db_ctx.get("exams", [])]
    candidates = {n for n in names if n and n.lower() in text_l}
    # drop names that are just a substring of another candidate (e.g. "Final" inside "Final Project")
    # so a short, generic name doesn't create false ambiguity against a more specific match
    candidates = {c for c in candidates if not any(c != other and c.lower() in other.lower() for other in candidates)}
    return next(iter(candidates)) if len(candidates) == 1 else None


def _resolve_entity(message: str, history: Optional[list], db_ctx: Optional[dict]) -> Optional[str]:
    """The entity currently under discussion: an explicit mention in this message wins; otherwise
    fall back to the most recent assistant message that named exactly one assignment/exam."""
    direct = _extract_entity_from_text(message, db_ctx)
    if direct:
        return direct
    for m in reversed(history or []):
        if m.get("role") != "assistant":
            continue
        found = _extract_entity_from_text(m.get("content"), db_ctx)
        if found:
            return found
    return None


def _focus_hint(resolved_entity: Optional[str]) -> str:
    if not resolved_entity:
        return ""
    return (
        f'The student is currently discussing "{resolved_entity}" — prioritize it in your answer '
        "unless they've clearly moved on to something else.\n\n"
    )


def _normalize_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def _is_close_match(name: str, message: str) -> bool:
    """Whether the student's wording closely matches the assignment name (vs. a fuzzy LLM guess)."""
    name_l = name.lower()
    msg_l = message.lower()
    if name_l in msg_l:
        return True
    name_tokens = _normalize_tokens(name)
    if not name_tokens:
        return False
    overlap = name_tokens & _normalize_tokens(message)
    return len(overlap) / len(name_tokens) >= 0.6


_CONFIRM_WORDS = {"yes", "yeah", "yep", "yup", "correct", "confirm", "confirmed", "sure", "right", "that's right", "y"}
_REJECT_WORDS = {"no", "nope", "incorrect", "wrong", "not that one"}


def _is_confirmation(message: str) -> bool:
    m = message.strip().lower().rstrip("!.")
    return m in _CONFIRM_WORDS or m.startswith("yes")


def _is_rejection(message: str) -> bool:
    m = message.strip().lower().rstrip("!.")
    return m in _REJECT_WORDS


async def _extract_update(message: str, assignments: list, history_block: str) -> dict:
    listing = "\n".join(f"{a['id']}: {a['name']} (current status: {a['status']})" for a in assignments)
    extraction_prompt = (
        "Given this list of assignments (id: name (current status)):\n"
        f"{listing}\n\n"
        f"{history_block}"
        f'The message says: "{message}"\n\n'
        "Identify ALL assignment ids that could plausibly match what the student is referring to "
        "(use the recent conversation above to resolve vague references like \"it\" or \"that one\"), "
        'and the new status implied ("in_progress" or "completed"). Respond ONLY with JSON: '
        '{"matches": [<int ids>], "new_status": "<in_progress|completed|null>"}'
    )
    extraction = await _openai.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": extraction_prompt}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    try:
        return json.loads(extraction.choices[0].message.content)
    except (json.JSONDecodeError, TypeError):
        return {}


def _grade_stats(db_ctx: Optional[dict], today: datetime.date) -> dict:
    """Grade math is driven by the actual `score` field, not assignment status.
    An item only counts toward the current grade once it has a real score —
    being marked "completed" with no score yet still counts as ungraded."""
    assignments = db_ctx.get("assignments", []) if db_ctx else []
    exams = db_ctx.get("exams", []) if db_ctx else []

    total_weight = sum((a["weight"] or 0) for a in assignments) + sum((e["weight"] or 0) for e in exams)

    graded_weight = 0.0
    current_grade = 0.0
    for a in assignments:
        if a.get("score") is not None:
            w = a["weight"] or 0
            graded_weight += w
            current_grade += w * (a["score"] / 100.0)

    remaining_weight = total_weight - graded_weight

    overdue = []
    for a in assignments:
        if a["due_date"] and a["status"] != "completed":
            due = datetime.date.fromisoformat(a["due_date"])
            if due < today:
                overdue.append({"name": a["name"], "days": (today - due).days, "weight": a["weight"]})

    return {
        "total_weight": total_weight,
        "graded_weight": graded_weight,
        "current_grade": current_grade,
        "remaining_weight": remaining_weight,
        "max_possible": current_grade + remaining_weight,
        "overdue": overdue,
    }


def _is_multi_course_message(message_lower: str) -> bool:
    if any(k in message_lower for k in MULTI_COURSE_KEYWORDS):
        return True
    mentions_courses = "course" in message_lower or "courses" in message_lower or "class" in message_lower or "classes" in message_lower
    comparison_words = ["which", "all", "every", "compare", "rank", "most", "total", "across"]
    return mentions_courses and any(w in message_lower for w in comparison_words)


# ---- graph -------------------------------------------------------------------

def build_graph(db: AsyncSession):
    async def context_resolver(state: AgentState) -> AgentState:
        courses = await _fetch_all_courses(db)
        all_courses_data = [
            {"id": c.id, "name": c.name, "professor": c.professor, "late_policy": c.late_policy}
            for c in courses
        ]

        message_lower = state["message"].lower()
        resolved_course_id = state.get("course_id")

        if resolved_course_id is None:
            for c in courses:
                tokens = [t for t in c.name.lower().split() if len(t) > 3]
                if c.name.lower() in message_lower or any(t in message_lower for t in tokens):
                    resolved_course_id = c.id
                    break

        if resolved_course_id is None and courses:
            resolved_course_id = courses[0].id

        is_multi = _is_multi_course_message(message_lower)

        db_context = None
        if resolved_course_id is not None:
            course = next((c for c in courses if c.id == resolved_course_id), None)
            assignments = await _fetch_assignments(db, resolved_course_id)
            exams = await _fetch_exams(db, resolved_course_id)
            db_context = {
                "course": (
                    {"id": course.id, "name": course.name, "professor": course.professor, "late_policy": course.late_policy}
                    if course else None
                ),
                "assignments": [_assignment_to_dict(a) for a in assignments],
                "exams": [_exam_to_dict(e) for e in exams],
            }

        resolved_entity = _resolve_entity(state["message"], state.get("conversation_history"), db_context)

        return {
            **state,
            "all_courses": all_courses_data,
            "resolved_course_id": resolved_course_id,
            "is_multi_course": is_multi,
            "db_context": db_context,
            "resolved_entity": resolved_entity,
        }

    async def intent_router(state: AgentState) -> AgentState:
        # a yes/no reply to update_node's pending fuzzy-match question must stay in UPDATE,
        # regardless of how the LLM would otherwise classify a bare "yes"
        if state.get("pending_update") is not None and (
            _is_confirmation(state["message"]) or _is_rejection(state["message"])
        ):
            return {**state, "intent": "UPDATE"}

        history_text = _format_recent_history(state.get("conversation_history"))
        history_block = f"Recent conversation:\n{history_text}\n\n" if history_text else ""
        hint = "Note: this message appears to reference multiple courses; strongly prefer MULTI_COURSE.\n" if state["is_multi_course"] else ""
        result = await _llm.ainvoke(INTENT_PROMPT.format(history_block=history_block, hint=hint, message=state["message"]))
        intent = result.content.strip().upper()
        if intent not in VALID_INTENTS:
            intent = "WHAT"
        if state["is_multi_course"]:
            intent = "MULTI_COURSE"
        # any pending fuzzy-match confirmation that isn't being answered right now is stale
        pending_update = state.get("pending_update") if intent == "UPDATE" else None
        return {**state, "intent": intent, "pending_update": pending_update}

    async def what_node(state: AgentState) -> AgentState:
        course_id = state["resolved_course_id"]
        chunks = await _rag_chunks(db, course_id, state["message"], k=3) if course_id else []
        rag_text = "\n\n---\n\n".join(c.content for c in chunks) if chunks else None

        resolved_entity = state.get("resolved_entity")
        db_ctx = _filter_db_context_to_entity(state["db_context"], resolved_entity) if resolved_entity else state["db_context"]
        context = _format_db_context(db_ctx)
        if rag_text:
            context += f"\n\nRelevant course document excerpts:\n{rag_text}"

        response = await _answer_with_context(
            state["message"],
            context,
            "You are an academic assistant. Answer factually and concisely using only the data given below. "
            "Use today's date to correctly filter any date-relative phrasing (e.g. \"this week\" means the "
            "next 7 days from today, not overdue items, unless the question is explicitly about overdue work).",
            history=_format_recent_history(state.get("conversation_history")),
        )
        return {**state, "rag_context": rag_text, "response": response}

    async def how_bad_node(state: AgentState) -> AgentState:
        course_id = state["resolved_course_id"]
        today = datetime.date.today()
        db_ctx = state["db_context"]
        stats = _grade_stats(db_ctx, today)

        chunks = await _rag_chunks(db, course_id, "late policy", k=2) if course_id else []
        late_policy = "\n".join(c.content for c in chunks) if chunks else (
            (db_ctx["course"]["late_policy"] if db_ctx and db_ctx["course"] else None) or "No late policy on file."
        )

        overdue_lines = "\n".join(
            f"- {o['name']}: {o['days']} day(s) overdue, {o['weight']}% weight" for o in stats["overdue"]
        ) or "  none"

        context = (
            f"{_focus_hint(state.get('resolved_entity'))}"
            f"Total course weight: {stats['total_weight']}%\n"
            f"Graded weight so far (items with a real score entered): {stats['graded_weight']}%\n"
            f"Current grade (weighted average of graded work only): {stats['current_grade']:.1f}%\n"
            f"Remaining weight (not yet graded — score is null, regardless of status): {stats['remaining_weight']}%\n"
            f"Max possible grade if everything remaining is scored perfectly: {stats['max_possible']:.1f}%\n"
            "Assume a passing grade is roughly 60% of total course weight unless stated otherwise.\n\n"
            f"Overdue items:\n{overdue_lines}\n\n"
            f"Late policy:\n{late_policy}"
        )

        response = await _answer_with_context(
            state["message"],
            context,
            "You are an academic assistant giving an honest, direct damage assessment. Do not sugarcoat — "
            "if the student is in serious trouble, say so plainly. But also clearly show what is still "
            "salvageable and what the realistic best case looks like. No filler, no generic encouragement.",
            history=_format_recent_history(state.get("conversation_history")),
        )
        return {**state, "rag_context": late_policy, "response": response}

    async def plan_node(state: AgentState) -> AgentState:
        today = datetime.date.today()
        db_ctx = state["db_context"]
        assignments = db_ctx.get("assignments", []) if db_ctx else []
        exams = db_ctx.get("exams", []) if db_ctx else []
        late_policy = (db_ctx["course"]["late_policy"] if db_ctx and db_ctx["course"] else None) or "No late policy on file."

        lines = ["Assignments:"]
        for a in assignments:
            if a["status"] == "completed":
                continue
            if a["due_date"]:
                due = datetime.date.fromisoformat(a["due_date"])
                days = (due - today).days
                timing = f"{abs(days)} day(s) overdue" if days < 0 else ("due today" if days == 0 else f"due in {days} day(s)")
            else:
                timing = "no due date"
            lines.append(f"- {a['name']}: weight {a['weight']}%, status {a['status']}, {timing}")

        lines.append("Exams:")
        for e in exams:
            if e["date"]:
                d = datetime.date.fromisoformat(e["date"])
                days = (d - today).days
                timing = f"{abs(days)} day(s) ago" if days < 0 else ("today" if days == 0 else f"in {days} day(s)")
            else:
                timing = "no date"
            lines.append(f"- {e['name']}: weight {e['weight']}%, {timing}")

        context = "\n".join(lines) + f"\n\nLate policy: {late_policy}"
        history_text = _format_recent_history(state.get("conversation_history"))
        history_block = f'Recent conversation:\n{history_text}\n\n' if history_text else ""

        prompt = (
            f'Today is {today.isoformat()}. A student asked: "{state["message"]}"\n\n'
            f"{history_block}"
            f"{_focus_hint(state.get('resolved_entity'))}"
            f"Their current workload:\n{context}\n\n"
            "Build a realistic, specific plan that respects any time constraint mentioned in their message "
            "(a number of hours or days; if none is mentioned, give a day-by-day plan for the week). If the "
            "question is a follow-up referring to something discussed above (e.g. \"it\", \"that exam\"), "
            "resolve the reference using the conversation history. "
            "Use this priority order: exams within 3 days > overdue high-weight items > due tomorrow > due "
            "this week > upcoming exams further out > everything else. If an item is overdue, mention "
            "whether it's still worth submitting late given the late policy (do the partial-credit math). "
            "Be concrete — give time blocks or a day-by-day breakdown — and concise. No generic filler."
        )
        result = await _llm.ainvoke(prompt)
        return {**state, "response": result.content}

    async def _apply_status_update(match: dict, assignments: list, new_status: Optional[str], state: AgentState) -> AgentState:
        if new_status not in ("in_progress", "completed"):
            return {**state, "pending_update": None, "response": "I couldn't tell what status to set — could you say whether you started or finished it?"}

        current = match["status"]
        valid_transitions = {("pending", "in_progress"), ("pending", "completed"), ("in_progress", "completed")}

        if current == new_status:
            return {**state, "pending_update": None, "response": f'"{match["name"]}" is already marked {current}.'}
        if (current, new_status) not in valid_transitions:
            return {**state, "pending_update": None, "response": f'"{match["name"]}" is currently {current} — I can\'t move it back to {new_status}.'}

        result = await db.execute(select(Assignment).where(Assignment.id == match["id"]))
        obj = result.scalar_one_or_none()
        if obj:
            obj.status = AssignmentStatus(new_status)
            await db.commit()

        remaining = sum(1 for a in assignments if a["id"] != match["id"] and a["status"] != "completed")
        remaining += 1 if new_status != "completed" else 0
        return {**state, "pending_update": None, "response": f'Got it! "{match["name"]}" marked as {new_status}. You have {remaining} assignment(s) left.'}

    async def update_node(state: AgentState) -> AgentState:
        db_ctx = state["db_context"]
        assignments = db_ctx.get("assignments", []) if db_ctx else []
        if not assignments:
            return {**state, "pending_update": None, "response": "There are no assignments recorded for this course yet."}

        # a confirmation/rejection reply to a previous fuzzy-match question
        pending_id = state.get("pending_update")
        if pending_id is not None:
            pending_match = next((a for a in assignments if a["id"] == pending_id), None)
            if pending_match and _is_confirmation(state["message"]):
                history = state.get("conversation_history") or []
                prior_user_msgs = [m["content"] for m in history if m.get("role") == "user"]
                original_message = prior_user_msgs[-1] if prior_user_msgs else state["message"]
                parsed = await _extract_update(original_message, [pending_match], "")
                new_status = parsed.get("new_status")
                return await _apply_status_update(pending_match, assignments, new_status, state)
            if pending_match and _is_rejection(state["message"]):
                return {**state, "pending_update": None, "response": "No problem — what's the exact assignment name?"}
            # message wasn't a yes/no reply (e.g. they just gave the real name) — drop the pending
            # question and fall through to treat this message as a fresh update request
            state = {**state, "pending_update": None}

        history_text = _format_recent_history(state.get("conversation_history"))
        history_block = f'Recent conversation:\n{history_text}\n\n' if history_text else ""
        parsed = await _extract_update(state["message"], assignments, history_block)

        matches = parsed.get("matches") or []
        new_status = parsed.get("new_status")

        if len(matches) == 0 or new_status not in ("in_progress", "completed"):
            return {**state, "pending_update": None, "response": "I couldn't tell which assignment you meant. Could you name it more specifically?"}

        if len(matches) > 1:
            names = [a["name"] for a in assignments if a["id"] in matches]
            return {**state, "pending_update": None, "response": f"I found multiple possible matches: {', '.join(names)}. Which one did you mean?"}

        assignment_id = matches[0]
        match = next((a for a in assignments if a["id"] == assignment_id), None)
        if not match:
            return {**state, "pending_update": None, "response": "I couldn't tell which assignment you meant. Could you name it more specifically?"}

        if not _is_close_match(match["name"], state["message"]):
            return {
                **state,
                "pending_update": assignment_id,
                "response": f'Did you mean "{match["name"]}"? Reply \'yes\' to confirm or let me know the exact assignment name.',
            }

        return await _apply_status_update(match, assignments, new_status, state)

    async def crisis_node(state: AgentState) -> AgentState:
        course_id = state["resolved_course_id"]
        today = datetime.date.today()
        db_ctx = state["db_context"]
        stats = _grade_stats(db_ctx, today)
        assignments = db_ctx.get("assignments", []) if db_ctx else []
        exams = db_ctx.get("exams", []) if db_ctx else []

        chunks = await _rag_chunks(db, course_id, "late policy resubmission attendance", k=3) if course_id else []
        rag_text = "\n".join(c.content for c in chunks) if chunks else ""
        late_policy = (db_ctx["course"]["late_policy"] if db_ctx and db_ctx["course"] else None) or "No late policy on file."

        assignment_lines = "\n".join(
            f"- {a['name']}: {a['weight']}%, status {a['status']}, due {a['due_date'] or 'n/a'}"
            + (f", score {a['score']}/100" if a.get("score") is not None else ", not yet graded")
            for a in assignments
        ) or "  none"
        exam_lines = "\n".join(
            f"- {e['name']}: {e['weight']}%, date {e['date'] or 'n/a'}" for e in exams
        ) or "  none"
        overdue_lines = "\n".join(
            f"- {o['name']}: {o['days']} day(s) overdue ({o['weight']}%)" for o in stats["overdue"]
        ) or "  none"

        context = (
            f"Course: {db_ctx['course']['name'] if db_ctx and db_ctx['course'] else 'Unknown'}\n"
            f"Total course weight: {stats['total_weight']}%\n"
            f"Current grade (weighted average of graded work only): {stats['current_grade']:.1f}%\n"
            f"Max possible remaining grade: {stats['max_possible']:.1f}%\n\n"
            f"Assignments:\n{assignment_lines}\n\n"
            f"Exams:\n{exam_lines}\n\n"
            f"Overdue:\n{overdue_lines}\n\n"
            f"Late policy / course rules:\n{late_policy}\n{rag_text}"
        )

        history_text = _format_recent_history(state.get("conversation_history"))
        history_block = f'Recent conversation:\n{history_text}\n\n' if history_text else ""

        prompt = (
            f'Today is {today.isoformat()}. The student is in distress and said: "{state["message"]}"\n\n'
            f"{history_block}"
            f"{_focus_hint(state.get('resolved_entity'))}"
            f"Full course context:\n{context}\n\n"
            "If the message is a follow-up referring to something discussed above, resolve it using the "
            "conversation history. "
            "Respond like a TA who actually cares: calm, honest, practical. Not cheerful, not doom. "
            "If they were sick or missed a stretch of time, show exactly what was missed and what's still "
            "submittable under the late policy, with a recovery priority order. If they're considering "
            "dropping, give the honest current/max-possible grade picture and what continuing would "
            "realistically take. If they're just overwhelmed and don't know where to start, break it down "
            "into the single smallest next step, then the step after that — not the whole list at once. "
            "If they missed an exam, check the policy, show the grade impact, and suggest contacting the "
            "professor if the policy doesn't cover it. Keep it grounded in the real numbers above."
        )
        result = await _llm.ainvoke(prompt)
        return {**state, "rag_context": rag_text or None, "response": result.content}

    async def multi_course_node(state: AgentState) -> AgentState:
        today = datetime.date.today()
        courses = await _fetch_all_courses(db)

        summaries = []
        for c in courses:
            assignments = await _fetch_assignments(db, c.id)
            exams = await _fetch_exams(db, c.id)

            overdue = [
                a for a in assignments
                if a.due_date and a.due_date < today and a.status != AssignmentStatus.completed
            ]
            overdue_weight = sum(a.weight or 0.0 for a in overdue)

            due_this_week = [
                a for a in assignments
                if a.due_date and today <= a.due_date <= today + datetime.timedelta(days=7)
            ]
            due_this_week_weight = sum(a.weight or 0.0 for a in due_this_week)

            future_exams = sorted((e for e in exams if e.date and e.date >= today), key=lambda e: e.date)
            next_exam = future_exams[0] if future_exams else None
            next_exam_days = (next_exam.date - today).days if next_exam else None

            urgency_score = overdue_weight + due_this_week_weight + (20 if next_exam_days is not None and next_exam_days <= 7 else 0)

            summaries.append({
                "course_name": c.name,
                "overdue_count": len(overdue),
                "overdue_weight": overdue_weight,
                "due_this_week_count": len(due_this_week),
                "due_this_week_weight": due_this_week_weight,
                "due_this_week_items": [a.name for a in due_this_week],
                "next_exam_name": next_exam.name if next_exam else None,
                "next_exam_days": next_exam_days,
                "urgency_score": urgency_score,
            })

        ranked = sorted(summaries, key=lambda s: s["urgency_score"], reverse=True)

        lines = []
        for s in ranked:
            exam_part = (
                f"{s['next_exam_name']} in {s['next_exam_days']} day(s)" if s["next_exam_name"] else "none"
            )
            lines.append(
                f"- {s['course_name']}: urgency score {s['urgency_score']:.1f} | "
                f"overdue: {s['overdue_count']} item(s) / {s['overdue_weight']}% | "
                f"due this week: {s['due_this_week_count']} item(s) / {s['due_this_week_weight']}% "
                f"({', '.join(s['due_this_week_items']) or 'none'}) | next exam: {exam_part}"
            )
        context = "\n".join(lines) if lines else "No courses found."

        response = await _answer_with_context(
            state["message"],
            context,
            "You are an academic assistant comparing the student's courses. The list below is already "
            "ranked by urgency (highest first). Answer the student's question clearly using this data — "
            "e.g. ranking, grouping deadlines by course, or aggregating totals as asked.",
            history=_format_recent_history(state.get("conversation_history")),
        )
        return {**state, "response": response}

    def route_intent(state: AgentState) -> str:
        return state["intent"]

    graph = StateGraph(AgentState)
    graph.add_node("context_resolver", context_resolver)
    graph.add_node("intent_router", intent_router)
    graph.add_node("what_node", what_node)
    graph.add_node("how_bad_node", how_bad_node)
    graph.add_node("plan_node", plan_node)
    graph.add_node("update_node", update_node)
    graph.add_node("crisis_node", crisis_node)
    graph.add_node("multi_course_node", multi_course_node)

    graph.add_edge(START, "context_resolver")
    graph.add_edge("context_resolver", "intent_router")
    graph.add_conditional_edges(
        "intent_router",
        route_intent,
        {
            "WHAT": "what_node",
            "HOW_BAD": "how_bad_node",
            "PLAN": "plan_node",
            "UPDATE": "update_node",
            "CRISIS": "crisis_node",
            "MULTI_COURSE": "multi_course_node",
        },
    )
    for node_name in [
        "what_node", "how_bad_node", "plan_node", "update_node", "crisis_node", "multi_course_node",
    ]:
        graph.add_edge(node_name, END)

    return graph.compile()
