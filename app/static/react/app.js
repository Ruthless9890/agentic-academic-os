const { useState, useEffect, useRef, useMemo, useCallback } = React;

// ---------------------------------------------------------------------------
// API helper
// ---------------------------------------------------------------------------

async function apiFetch(path, options = {}) {
  const opts = { method: options.method || "GET", headers: {} };
  if (options.body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(options.body);
  }
  const res = await fetch(path, opts);
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (e) {
      data = text;
    }
  }
  if (!res.ok) {
    const message = data && data.detail ? data.detail : `Request failed (${res.status})`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return data;
}

// ---------------------------------------------------------------------------
// Date / formatting helpers
// ---------------------------------------------------------------------------

function parseDateOnly(s) {
  if (!s) return null;
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function todayLocal() {
  const t = new Date();
  return new Date(t.getFullYear(), t.getMonth(), t.getDate());
}

function daysUntil(s) {
  const d = parseDateOnly(s);
  if (!d) return null;
  return Math.round((d - todayLocal()) / 86400000);
}

function formatDate(s) {
  const d = parseDateOnly(s);
  if (!d) return "No due date";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function timeAgo(iso) {
  if (!iso) return "";
  const then = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  const seconds = Math.max(0, Math.floor((Date.now() - then.getTime()) / 1000));
  if (seconds < 60) return "just now";
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const days = Math.floor(h / 24);
  return `${days}d ago`;
}

function calcGrade(assignments) {
  const scored = assignments.filter(
    (a) => a.score !== null && a.score !== undefined && a.weight
  );
  const totalWeight = scored.reduce((s, a) => s + a.weight, 0);
  if (totalWeight <= 0) return null;
  const weighted = scored.reduce((s, a) => s + a.score * a.weight, 0);
  return weighted / totalWeight;
}

function gradeColors(pct) {
  if (pct === null) return { text: "text-gray-400", bar: "bg-gray-600" };
  if (pct >= 80) return { text: "text-green-400", bar: "bg-green-500" };
  if (pct >= 60) return { text: "text-yellow-400", bar: "bg-yellow-500" };
  return { text: "text-red-400", bar: "bg-red-500" };
}

function courseDotColor(courseId, assignments) {
  const list = assignments.filter((a) => a.course_id === courseId && a.status !== "completed" && a.due_date);
  let overdue = false;
  let soon = false;
  list.forEach((a) => {
    const d = daysUntil(a.due_date);
    if (d < 0) overdue = true;
    else if (d <= 3) soon = true;
  });
  if (overdue) return "bg-red-500";
  if (soon) return "bg-yellow-500";
  return "bg-green-500";
}

// ---------------------------------------------------------------------------
// Style maps
// ---------------------------------------------------------------------------

const STATUS_STYLES = {
  pending: "bg-base-700 text-gray-300 border-base-600",
  in_progress: "bg-blue-900/40 text-blue-300 border-blue-800",
  completed: "bg-green-900/40 text-green-300 border-green-800",
};

const INTENT_STYLES = {
  WHAT: "bg-base-700 text-gray-300 border-base-600",
  HOW_BAD: "bg-red-900/40 text-red-300 border-red-800",
  PLAN: "bg-blue-900/40 text-blue-300 border-blue-800",
  UPDATE: "bg-green-900/40 text-green-300 border-green-800",
  CRISIS: "bg-orange-900/40 text-orange-300 border-orange-800",
  MULTI_COURSE: "bg-purple-900/40 text-purple-300 border-purple-800",
  MULTI: "bg-purple-900/40 text-purple-300 border-purple-800",
};

const ALERT_GROUP_OF = {
  overdue: "Overdue",
  due_tomorrow: "Due Soon",
  due_in_3_days: "Due Soon",
  exam_proximity: "Exams",
  heavy_week: "Info",
  inactivity: "Info",
};

const ALERT_GROUP_STYLES = {
  Overdue: { bar: "bg-red-500", label: "text-red-400" },
  "Due Soon": { bar: "bg-yellow-500", label: "text-yellow-400" },
  Exams: { bar: "bg-blue-500", label: "text-blue-400" },
  Info: { bar: "bg-gray-500", label: "text-gray-400" },
};

const ALERT_GROUP_ORDER = ["Overdue", "Due Soon", "Exams", "Info"];

// ---------------------------------------------------------------------------
// Small shared components
// ---------------------------------------------------------------------------

function RobotIcon({ className }) {
  return (
    <div className={className}>
      <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full">
        <rect x="4" y="8" width="16" height="12" rx="3" fill="url(#g)" />
        <circle cx="9" cy="14" r="1.4" fill="#0d0f17" />
        <circle cx="15" cy="14" r="1.4" fill="#0d0f17" />
        <rect x="10.2" y="17" width="3.6" height="1.3" rx="0.6" fill="#0d0f17" />
        <rect x="11" y="3" width="2" height="4" rx="1" fill="#8b7bff" />
        <circle cx="12" cy="3" r="1.4" fill="#8b7bff" />
        <defs>
          <linearGradient id="g" x1="4" y1="8" x2="20" y2="20" gradientUnits="userSpaceOnUse">
            <stop stopColor="#6d5dfc" />
            <stop offset="1" stopColor="#8b7bff" />
          </linearGradient>
        </defs>
      </svg>
    </div>
  );
}

function Toast({ toast }) {
  if (!toast) return null;
  const styles =
    toast.type === "error"
      ? "bg-red-900/90 border-red-700 text-red-100"
      : "bg-green-900/90 border-green-700 text-green-100";
  return (
    <div className="fixed top-5 right-5 z-[100] fade-in-up">
      <div className={`border rounded-xl px-4 py-3 text-sm shadow-2xl max-w-sm ${styles}`}>
        {toast.msg}
      </div>
    </div>
  );
}

function Spinner({ className }) {
  return (
    <span
      className={`inline-block border-2 border-white/25 border-t-white rounded-full spin ${className || "w-3.5 h-3.5"}`}
    />
  );
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

function Sidebar({ courses, assignments, activeCourseId, onSelectCourse, onOpenUpload, alertCount, onToggleAlerts }) {
  return (
    <div className="w-[260px] flex-shrink-0 bg-base-900 border-r border-base-700 flex flex-col h-full">
      <div className="px-5 py-5 flex items-center gap-3 border-b border-base-700">
        <RobotIcon className="w-8 h-8 flex-shrink-0" />
        <div>
          <div className="text-[15px] font-semibold text-gray-100 leading-tight">AcademicOS</div>
          <div className="text-[11px] text-gray-500 leading-tight">Agentic course assistant</div>
        </div>
      </div>

      <div className="px-4 pt-4">
        <button
          onClick={onOpenUpload}
          className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-indigo-600 to-purple-600 hover:opacity-90 text-white text-[13px] font-medium rounded-lg py-2.5 transition"
        >
          <span>📄</span>
          <span>Upload Syllabus</span>
        </button>
      </div>

      <div className="px-3 pt-5 pb-2 text-[11px] font-semibold tracking-wide text-gray-500 uppercase">
        Courses
      </div>

      <div className="flex-1 overflow-y-auto px-2 space-y-1 pb-2">
        <button
          onClick={() => onSelectCourse("all")}
          className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left text-[13.5px] transition ${
            activeCourseId === "all"
              ? "bg-base-800 text-gray-100"
              : "text-gray-400 hover:bg-base-800/60 hover:text-gray-200"
          }`}
        >
          <span className="text-base">📚</span>
          <span className="truncate">All Courses</span>
        </button>

        {courses.map((c) => {
          const active = activeCourseId === c.id;
          const dot = courseDotColor(c.id, assignments);
          return (
            <button
              key={c.id}
              onClick={() => onSelectCourse(c.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left text-[13.5px] transition ${
                active ? "bg-base-800 text-gray-100" : "text-gray-400 hover:bg-base-800/60 hover:text-gray-200"
              }`}
            >
              <span className={`w-2 h-2 rounded-full flex-shrink-0 ${dot}`} />
              <span className="truncate flex-1">{c.name}</span>
            </button>
          );
        })}

        {courses.length === 0 && (
          <div className="text-[12px] text-gray-500 px-3 py-4 text-center">
            No courses yet. Upload a syllabus to get started.
          </div>
        )}
      </div>

      <div className="border-t border-base-700 p-3">
        <button
          onClick={onToggleAlerts}
          className="relative w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-gray-300 hover:bg-base-800 transition"
        >
          <span className={`text-lg ${alertCount > 0 ? "ring-pulse rounded-full" : ""}`}>🔔</span>
          <span className="text-[13px]">Alerts</span>
          {alertCount > 0 && (
            <span className="absolute right-3 top-1.5 bg-red-500 text-white text-[10px] font-bold rounded-full min-w-[18px] h-[18px] flex items-center justify-center px-1">
              {alertCount > 99 ? "99+" : alertCount}
            </span>
          )}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Top bar
// ---------------------------------------------------------------------------

function downloadUrl(url) {
  const a = document.createElement("a");
  a.href = url;
  a.click();
}

function TopBar({ courseName, view, onChangeView, onNewChat, onOpenExport }) {
  return (
    <div className="h-16 flex-shrink-0 border-b border-base-700 bg-base-900/60 flex items-center justify-between px-6">
      <div className="text-[15px] font-semibold text-gray-100 truncate max-w-[260px]">{courseName}</div>

      <div className="flex items-center gap-1 bg-base-800 border border-base-700 rounded-lg p-1">
        {["chat", "dashboard", "calendar"].map((v) => (
          <button
            key={v}
            onClick={() => onChangeView(v)}
            className={`px-4 py-1.5 rounded-md text-[13px] font-medium capitalize transition ${
              view === v ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {v}
          </button>
        ))}
      </div>

      {view === "dashboard" ? (
        <button
          onClick={onOpenExport}
          className="flex items-center gap-2 bg-base-800 border border-base-700 hover:border-indigo-500 text-gray-200 text-[13px] rounded-lg px-3.5 py-2 transition"
        >
          <span>📅</span>
          <span>Export to Calendar</span>
        </button>
      ) : (
        <button
          onClick={onNewChat}
          className="flex items-center gap-2 bg-base-800 border border-base-700 hover:border-indigo-500 text-gray-200 text-[13px] rounded-lg px-3.5 py-2 transition"
        >
          <span>🆕</span>
          <span>New Chat</span>
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Export modal
// ---------------------------------------------------------------------------

function extractVEvents(icsText) {
  const matches = icsText.match(/BEGIN:VEVENT[\s\S]*?END:VEVENT/g);
  return matches || [];
}

async function downloadMergedIcal(courseIds) {
  const texts = await Promise.all(
    courseIds.map(async (id) => {
      const res = await fetch(`/courses/${id}/export/ical`);
      if (!res.ok) throw new Error(`Failed to export course ${id} (${res.status})`);
      return res.text();
    })
  );
  const events = texts.flatMap(extractVEvents);
  const merged = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Academic OS//Calendar Export//EN", ...events, "END:VCALENDAR"].join(
    "\r\n"
  );

  const blob = new Blob([merged], { type: "text/calendar" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "academic_os_selected_courses.ics";
  a.click();
  URL.revokeObjectURL(url);
}

function ExportModal({ open, onClose, courses, activeCourseId, pushToast }) {
  const [selected, setSelected] = useState(() => new Set());
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (activeCourseId !== "all" && courses.some((c) => c.id === activeCourseId)) {
      setSelected(new Set([activeCourseId]));
    } else {
      setSelected(new Set(courses.map((c) => c.id)));
    }
  }, [open, activeCourseId, courses]);

  function toggle(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected((prev) => (prev.size === courses.length ? new Set() : new Set(courses.map((c) => c.id))));
  }

  async function exportSelected() {
    if (selected.size === 0) {
      pushToast("error", "Select at least one course.");
      return;
    }
    setExporting(true);
    try {
      if (selected.size === courses.length) {
        downloadUrl("/courses/all/export/ical");
      } else if (selected.size === 1) {
        downloadUrl(`/courses/${[...selected][0]}/export/ical`);
      } else {
        await downloadMergedIcal([...selected]);
      }
      onClose();
    } catch (e) {
      pushToast("error", e.message);
    } finally {
      setExporting(false);
    }
  }

  if (!open) return null;

  const allChecked = courses.length > 0 && selected.size === courses.length;

  return (
    <div
      className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center fade-in-up"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-base-900 border border-base-700 rounded-2xl w-[340px] max-w-[90vw] p-5 shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <div className="text-[15px] font-semibold text-gray-100">Export to Calendar</div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-lg leading-none">
            ✕
          </button>
        </div>

        <label className="flex items-center gap-2.5 px-2 py-2 rounded-lg hover:bg-base-800 cursor-pointer border-b border-base-700 mb-1 transition">
          <input type="checkbox" checked={allChecked} onChange={toggleAll} className="accent-indigo-500 w-3.5 h-3.5" />
          <span className="text-[13px] text-gray-200 font-medium">Select All</span>
        </label>

        <div className="max-h-64 overflow-y-auto space-y-0.5">
          {courses.map((c) => (
            <label
              key={c.id}
              className="flex items-center gap-2.5 px-2 py-2 rounded-lg hover:bg-base-800 cursor-pointer transition"
            >
              <input
                type="checkbox"
                checked={selected.has(c.id)}
                onChange={() => toggle(c.id)}
                className="accent-indigo-500 w-3.5 h-3.5"
              />
              <span className="text-[13px] text-gray-300 truncate">{c.name}</span>
            </label>
          ))}
          {courses.length === 0 && (
            <div className="text-[12px] text-gray-500 px-2 py-3 text-center">No courses yet.</div>
          )}
        </div>

        <button
          onClick={exportSelected}
          disabled={exporting || selected.size === 0}
          className="w-full mt-4 flex items-center justify-center gap-2 bg-gradient-to-r from-indigo-600 to-purple-600 hover:opacity-90 disabled:opacity-40 text-white text-[13px] font-medium rounded-lg py-2.5 transition"
        >
          {exporting && <Spinner />}
          <span>Export Selected (.ics)</span>
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chat view
// ---------------------------------------------------------------------------

const SUGGESTIONS = ["Am I cooked?", "What's due this week?", "Make me a study plan", "How's my grade?"];

function IntentBadge({ intent }) {
  if (!intent) return null;
  const cls = INTENT_STYLES[intent] || INTENT_STYLES.WHAT;
  const label = intent.replace("_COURSE", "").replace("_", " ");
  return (
    <span className={`inline-flex items-center text-[10px] font-bold uppercase tracking-wide border rounded-full px-2.5 py-0.5 ${cls}`}>
      {label}
    </span>
  );
}

function TypingDots() {
  return (
    <div className="inline-flex items-center gap-1.5 bg-base-800 border border-base-700 rounded-2xl rounded-bl-md px-4 py-3.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-gray-500 dot-bounce"
          style={{ animationDelay: `${i * 0.18}s` }}
        />
      ))}
    </div>
  );
}

function ChatView({ courseId, courses, pushToast }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, sending]);

  async function send(text) {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    setSending(true);
    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setInput("");

    try {
      const data = await apiFetch("/chat", {
        method: "POST",
        body: {
          message: trimmed,
          course_id: courseId === "all" ? null : courseId,
          session_id: sessionId,
        },
      });
      setSessionId(data.session_id);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.response, intent: data.intent, course: data.course },
      ]);
    } catch (e) {
      setMessages((prev) => [...prev, { role: "assistant", content: `⚠️ ${e.message}`, error: true }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center gap-3">
            <div className="text-4xl mb-1">🎓</div>
            <h2 className="text-lg font-semibold text-gray-100">Ask me anything about your courses</h2>
            <p className="text-[13px] text-gray-500 max-w-sm">
              Deadlines, grades, study plans, or just tell me how behind you are. I'll route it to the right place.
            </p>
            <div className="flex flex-wrap justify-center gap-2 mt-3 max-w-md">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="bg-base-800 border border-base-700 hover:border-indigo-500 text-gray-300 text-[12.5px] rounded-full px-4 py-2 transition"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4 max-w-3xl mx-auto">
            {messages.map((m, i) => (
              <div key={i} className={`flex fade-in-up ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`flex flex-col gap-1.5 max-w-[75%] ${m.role === "user" ? "items-end" : "items-start"}`}>
                  {m.role === "assistant" && !m.error && (
                    <div className="flex items-center gap-2 px-1">
                      <IntentBadge intent={m.intent} />
                      {m.course && <span className="text-[11px] text-gray-500">· {m.course}</span>}
                    </div>
                  )}
                  <div
                    className={`px-4 py-3 rounded-2xl text-[14px] leading-relaxed whitespace-pre-wrap break-words ${
                      m.role === "user"
                        ? "bg-gradient-to-br from-indigo-600 to-purple-600 text-white rounded-br-md"
                        : m.error
                        ? "bg-red-950/40 border border-red-800 text-red-200 rounded-bl-md"
                        : "bg-base-800 border border-base-700 text-gray-100 rounded-bl-md"
                    }`}
                  >
                    {m.content}
                  </div>
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex justify-start">
                <TypingDots />
              </div>
            )}
          </div>
        )}
      </div>

      <div className="border-t border-base-700 px-6 py-4">
        <div className="max-w-3xl mx-auto flex items-center gap-3">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            placeholder="Ask about deadlines, grades, or what to study next…"
            className="flex-1 bg-base-800 border border-base-700 focus:border-indigo-500 outline-none text-gray-100 placeholder-gray-500 rounded-xl px-4 py-3 text-[14px] transition"
          />
          <button
            onClick={() => send(input)}
            disabled={sending || !input.trim()}
            className="bg-gradient-to-br from-indigo-600 to-purple-600 disabled:opacity-40 text-white font-medium rounded-xl px-5 py-3 text-[13.5px] flex items-center gap-2 transition"
          >
            {sending && <Spinner />}
            <span>Send</span>
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard view
// ---------------------------------------------------------------------------

function ScoreInput({ assignment, onSaved, pushToast }) {
  const [value, setValue] = useState(assignment.score ?? "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setValue(assignment.score ?? "");
  }, [assignment.score, assignment.id]);

  async function commit() {
    if (value === "" || value === null) return;
    let v = parseFloat(value);
    if (isNaN(v)) return;
    v = Math.max(0, Math.min(100, v));
    if (v === assignment.score) return;
    setSaving(true);
    try {
      const updated = await apiFetch(`/assignments/${assignment.id}/score`, {
        method: "PATCH",
        body: { score: v },
      });
      onSaved(updated);
    } catch (e) {
      pushToast("error", e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex items-center gap-1.5">
      <input
        type="number"
        min="0"
        max="100"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
        placeholder="—"
        className="w-16 bg-base-900 border border-base-600 focus:border-indigo-500 outline-none text-gray-100 text-center text-[13px] rounded-md py-1.5 transition"
      />
      <span className="text-[11px] text-gray-500">/100</span>
      {saving && <Spinner className="w-3 h-3" />}
    </div>
  );
}

function AssignmentRow({ assignment, onSaved, pushToast, onGlobalRefresh }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(assignment.name);
  const [due, setDue] = useState(assignment.due_date || "");
  const [saving, setSaving] = useState(false);

  const overdue = assignment.due_date && assignment.status !== "completed" && daysUntil(assignment.due_date) < 0;

  async function save() {
    if (!name.trim()) return;
    setSaving(true);
    try {
      const updated = await apiFetch(`/assignments/${assignment.id}`, {
        method: "PATCH",
        body: { name: name.trim(), due_date: due || null },
      });
      onSaved(updated);
      onGlobalRefresh();
      setEditing(false);
    } catch (e) {
      pushToast("error", e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className={`flex items-center gap-3 px-4 py-3 rounded-lg border transition ${
        overdue ? "bg-red-950/25 border-red-900/60" : "bg-base-850 border-base-700"
      }`}
    >
      <div className="flex-1 min-w-0">
        {editing ? (
          <div className="flex items-center gap-2 flex-wrap">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="bg-base-900 border border-indigo-500 outline-none text-gray-100 text-[13px] rounded-md px-2 py-1.5 flex-1 min-w-[140px]"
              autoFocus
            />
            <input
              type="date"
              value={due}
              onChange={(e) => setDue(e.target.value)}
              className="bg-base-900 border border-base-600 outline-none text-gray-100 text-[12px] rounded-md px-2 py-1.5"
            />
            <button
              onClick={save}
              disabled={saving}
              className="bg-indigo-600 hover:opacity-90 text-white text-[12px] rounded-md px-3 py-1.5"
            >
              {saving ? <Spinner /> : "Save"}
            </button>
            <button
              onClick={() => {
                setEditing(false);
                setName(assignment.name);
                setDue(assignment.due_date || "");
              }}
              className="bg-base-700 hover:bg-base-600 text-gray-300 text-[12px] rounded-md px-3 py-1.5"
            >
              Cancel
            </button>
          </div>
        ) : (
          <div
            onClick={() => setEditing(true)}
            title="Click to edit"
            className="text-[13.5px] text-gray-100 truncate cursor-pointer hover:underline underline-offset-2"
          >
            {assignment.name}
          </div>
        )}
        {!editing && (
          <div className={`text-[11.5px] mt-0.5 ${overdue ? "text-red-400" : "text-gray-500"}`}>
            {formatDate(assignment.due_date)}
            {overdue ? " · overdue" : ""}
          </div>
        )}
      </div>

      <div className="text-[12px] text-gray-400 w-14 text-right flex-shrink-0">
        {assignment.weight != null ? `${assignment.weight.toFixed ? assignment.weight.toFixed(1) : assignment.weight}%` : "—"}
      </div>

      <span
        className={`text-[10.5px] font-semibold uppercase tracking-wide border rounded-full px-2.5 py-1 flex-shrink-0 ${
          STATUS_STYLES[assignment.status] || STATUS_STYLES.pending
        }`}
      >
        {assignment.status.replace("_", " ")}
      </span>

      <div className="flex-shrink-0">
        <ScoreInput assignment={assignment} onSaved={onSaved} pushToast={pushToast} />
      </div>
    </div>
  );
}

function AddAssignmentForm({ courseId, onAdded, pushToast }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [due, setDue] = useState("");
  const [weight, setWeight] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit() {
    if (!name.trim()) return;
    setSaving(true);
    try {
      const created = await apiFetch("/assignments/add", {
        method: "POST",
        body: {
          course_id: courseId,
          name: name.trim(),
          due_date: due || null,
          weight: weight ? parseFloat(weight) : null,
          status: "pending",
        },
      });
      onAdded(created);
      setName("");
      setDue("");
      setWeight("");
      setOpen(false);
    } catch (e) {
      pushToast("error", e.message);
    } finally {
      setSaving(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="w-full border border-dashed border-base-600 hover:border-indigo-500 text-gray-400 hover:text-gray-200 text-[13px] rounded-lg py-3 transition"
      >
        + Add Assignment
      </button>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2 bg-base-850 border border-base-700 rounded-lg p-3">
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Assignment name"
        autoFocus
        className="flex-1 min-w-[160px] bg-base-900 border border-base-600 focus:border-indigo-500 outline-none text-gray-100 text-[13px] rounded-md px-3 py-2"
      />
      <input
        type="date"
        value={due}
        onChange={(e) => setDue(e.target.value)}
        className="bg-base-900 border border-base-600 outline-none text-gray-100 text-[12.5px] rounded-md px-3 py-2"
      />
      <input
        type="number"
        value={weight}
        onChange={(e) => setWeight(e.target.value)}
        placeholder="Weight %"
        min="0"
        max="100"
        className="w-24 bg-base-900 border border-base-600 outline-none text-gray-100 text-[13px] rounded-md px-3 py-2"
      />
      <button
        onClick={submit}
        disabled={saving}
        className="bg-indigo-600 hover:opacity-90 text-white text-[12.5px] rounded-md px-4 py-2"
      >
        {saving ? <Spinner /> : "Add"}
      </button>
      <button
        onClick={() => setOpen(false)}
        className="bg-base-700 hover:bg-base-600 text-gray-300 text-[12.5px] rounded-md px-4 py-2"
      >
        Cancel
      </button>
    </div>
  );
}

function examProximity(dateStr) {
  const d = daysUntil(dateStr);
  if (d === null) return { label: "No date", text: "text-gray-500", badge: "bg-base-700 text-gray-400 border-base-600" };
  if (d < 0) return { label: "Past", text: "text-gray-500", badge: "bg-base-700 text-gray-400 border-base-600" };
  if (d === 0) return { label: "Today", text: "text-red-400", badge: "bg-red-900/40 text-red-300 border-red-800" };
  if (d < 3) return { label: `${d}d`, text: "text-red-400", badge: "bg-red-900/40 text-red-300 border-red-800" };
  if (d < 7) return { label: `${d}d`, text: "text-yellow-400", badge: "bg-yellow-900/40 text-yellow-300 border-yellow-800" };
  return { label: `${d}d`, text: "text-green-400", badge: "bg-green-900/40 text-green-300 border-green-800" };
}

function ExamRow({ exam }) {
  const prox = examProximity(exam.date);
  return (
    <div className="flex items-center gap-3 px-4 py-3 rounded-lg border bg-base-850 border-base-700">
      <div className="flex-1 min-w-0">
        <div className="text-[13.5px] text-gray-100 truncate">{exam.name}</div>
        <div className="text-[11.5px] text-gray-500 mt-0.5">{formatDate(exam.date)}</div>
      </div>
      <div className="text-[12px] text-gray-400 w-14 text-right flex-shrink-0">
        {exam.weight != null ? `${exam.weight}%` : "—"}
      </div>
      <span className={`text-[10.5px] font-semibold uppercase tracking-wide border rounded-full px-2.5 py-1 flex-shrink-0 ${prox.badge}`}>
        {prox.label}
      </span>
    </div>
  );
}

function DocumentRow({ doc, courseId, onDeleted, pushToast }) {
  const [deleting, setDeleting] = useState(false);

  async function del() {
    if (!window.confirm(`Delete "${doc.filename}"? It will no longer be searchable in chat.`)) return;
    setDeleting(true);
    try {
      await apiFetch(`/courses/${courseId}/documents/${doc.id}`, { method: "DELETE" });
      onDeleted(doc.id);
    } catch (e) {
      pushToast("error", e.message);
      setDeleting(false);
    }
  }

  return (
    <div className="flex items-center gap-3 px-4 py-3 rounded-lg border bg-base-850 border-base-700">
      <span className="text-base flex-shrink-0">{doc.doc_type === "syllabus" ? "📝" : "📄"}</span>
      <div className="flex-1 min-w-0">
        <div className="text-[13.5px] text-gray-100 truncate">{doc.filename}</div>
        <div className="text-[11.5px] text-gray-500 mt-0.5">{doc.chunk_count} chunk(s) indexed</div>
      </div>
      <button
        onClick={del}
        disabled={deleting}
        className="text-gray-500 hover:text-red-400 text-[13px] px-1.5 flex-shrink-0"
      >
        {deleting ? <Spinner className="w-3 h-3" /> : "🗑️"}
      </button>
    </div>
  );
}

function DocumentsSection({ courseId, pushToast }) {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch(`/courses/${courseId}/documents`);
      setDocuments(data);
    } catch (e) {
      pushToast("error", e.message);
    } finally {
      setLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleFile(file) {
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      pushToast("error", "Please select a PDF file.");
      return;
    }
    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch(`/courses/${courseId}/upload-document`, { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Upload failed (${res.status})`);
      pushToast("success", `${data.filename}: ${data.chunks_created} chunk(s) indexed.`);
      load();
    } catch (e) {
      pushToast("error", e.message);
    } finally {
      setUploading(false);
    }
  }

  function removeDoc(id) {
    setDocuments((prev) => prev.filter((d) => d.id !== id));
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="text-[13px] font-semibold text-gray-300 uppercase tracking-wide">Course Materials</div>
        <button
          onClick={() => fileInputRef.current && fileInputRef.current.click()}
          disabled={uploading}
          className="flex items-center gap-1.5 bg-base-800 border border-base-700 hover:border-indigo-500 text-gray-200 text-[12px] rounded-lg px-3 py-1.5 transition disabled:opacity-50"
        >
          {uploading ? <Spinner className="w-3 h-3" /> : <span>📤</span>}
          <span>Upload Document</span>
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            handleFile(e.target.files[0]);
            e.target.value = "";
          }}
        />
      </div>
      <div className="space-y-2">
        {!loading && documents.length === 0 && (
          <div className="text-[13px] text-gray-500 py-4 text-center">No course materials uploaded yet.</div>
        )}
        {documents.map((d) => (
          <DocumentRow key={d.id} doc={d} courseId={courseId} onDeleted={removeDoc} pushToast={pushToast} />
        ))}
      </div>
    </div>
  );
}

function DashboardView({ courseId, exams, pushToast, onGlobalRefresh, onCourseDeleted }) {
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch(`/assignments?course_id=${courseId}`);
      setAssignments(data);
    } catch (e) {
      pushToast("error", e.message);
    } finally {
      setLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    load();
  }, [load]);

  function patchAssignment(updated) {
    setAssignments((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
    onGlobalRefresh();
  }

  function addAssignment(created) {
    setAssignments((prev) => [...prev, created]);
    onGlobalRefresh();
  }

  async function deleteCourse() {
    if (!window.confirm("Delete this course and all its assignments, exams, and documents? This cannot be undone.")) {
      return;
    }
    setDeleting(true);
    try {
      await apiFetch(`/courses/${courseId}`, { method: "DELETE" });
      pushToast("success", "Course deleted.");
      onCourseDeleted();
    } catch (e) {
      pushToast("error", e.message);
      setDeleting(false);
    }
  }

  const grade = calcGrade(assignments);
  const colors = gradeColors(grade);
  const sortedAssignments = useMemo(
    () =>
      [...assignments].sort((a, b) => {
        if (!a.due_date) return 1;
        if (!b.due_date) return -1;
        return a.due_date.localeCompare(b.due_date);
      }),
    [assignments]
  );
  const sortedExams = useMemo(() => [...exams].sort((a, b) => (a.date || "").localeCompare(b.date || "")), [exams]);

  if (loading) {
    return <div className="h-full flex items-center justify-center text-gray-500 text-sm">Loading…</div>;
  }

  return (
    <div className="h-full overflow-y-auto px-8 py-7">
      <div className="max-w-3xl mx-auto space-y-8">
        <div className="bg-base-850 border border-base-700 rounded-2xl p-6">
          <div className="flex items-end justify-between mb-3">
            <div>
              <div className="text-[12px] text-gray-500 uppercase tracking-wide mb-1">Current Grade</div>
              <div className={`text-4xl font-bold ${colors.text}`}>{grade !== null ? `${grade.toFixed(1)}%` : "—"}</div>
            </div>
            {grade === null && <div className="text-[12px] text-gray-500 pb-1.5">No scores recorded yet</div>}
          </div>
          <div className="w-full h-2.5 bg-base-700 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${colors.bar}`}
              style={{ width: `${grade !== null ? Math.min(100, grade) : 0}%` }}
            />
          </div>
        </div>

        <div>
          <div className="text-[13px] font-semibold text-gray-300 uppercase tracking-wide mb-3">Assignments</div>
          <div className="space-y-2">
            {sortedAssignments.length === 0 && (
              <div className="text-[13px] text-gray-500 py-4 text-center">No assignments for this course yet.</div>
            )}
            {sortedAssignments.map((a) => (
              <AssignmentRow key={a.id} assignment={a} onSaved={patchAssignment} pushToast={pushToast} onGlobalRefresh={onGlobalRefresh} />
            ))}
            <AddAssignmentForm courseId={courseId} onAdded={addAssignment} pushToast={pushToast} />
          </div>
        </div>

        <div>
          <div className="text-[13px] font-semibold text-gray-300 uppercase tracking-wide mb-3">Exams</div>
          <div className="space-y-2">
            {sortedExams.length === 0 && (
              <div className="text-[13px] text-gray-500 py-4 text-center">No exams recorded for this course yet.</div>
            )}
            {sortedExams.map((e) => (
              <ExamRow key={e.id} exam={e} />
            ))}
          </div>
        </div>

        <DocumentsSection courseId={courseId} pushToast={pushToast} />

        <div className="pt-2 pb-6">
          <button
            onClick={deleteCourse}
            disabled={deleting}
            className="flex items-center gap-2 text-red-400 hover:text-red-300 border border-red-900/60 hover:border-red-700 bg-red-950/20 rounded-lg px-4 py-2.5 text-[13px] transition"
          >
            {deleting ? <Spinner /> : "🗑️"}
            <span>Delete Course</span>
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Multi-course view
// ---------------------------------------------------------------------------

function CourseCard({ course, assignments, exams, onSelect }) {
  const courseAssignments = assignments.filter((a) => a.course_id === course.id);
  const grade = calcGrade(courseAssignments);
  const colors = gradeColors(grade);

  const overdueCount = courseAssignments.filter(
    (a) => a.due_date && a.status !== "completed" && daysUntil(a.due_date) < 0
  ).length;

  const upcoming = [
    ...courseAssignments
      .filter((a) => a.due_date && a.status !== "completed" && daysUntil(a.due_date) >= 0)
      .map((a) => ({ date: a.due_date, name: a.name })),
    ...exams.filter((e) => e.course_id === course.id && e.date && daysUntil(e.date) >= 0).map((e) => ({ date: e.date, name: e.name })),
  ].sort((a, b) => a.date.localeCompare(b.date));

  const next = upcoming[0] || null;
  const nextDays = next ? daysUntil(next.date) : null;

  let border = "border-base-700";
  if (overdueCount > 0) border = "border-red-700/70";
  else if (nextDays !== null && nextDays <= 3) border = "border-yellow-700/70";
  else if (next) border = "border-green-700/60";

  return (
    <button
      onClick={() => onSelect(course.id)}
      className={`text-left bg-base-850 border ${border} rounded-2xl p-5 hover:-translate-y-0.5 hover:shadow-xl transition`}
    >
      <div className="text-[15px] font-semibold text-gray-100 truncate mb-3">{course.name}</div>
      <div className={`text-3xl font-bold mb-3 ${colors.text}`}>{grade !== null ? `${grade.toFixed(1)}%` : "—"}</div>
      <div className="flex items-center justify-between text-[12px]">
        <span className={overdueCount > 0 ? "text-red-400" : "text-gray-500"}>
          {overdueCount > 0 ? `🚨 ${overdueCount} overdue` : "✓ no overdue items"}
        </span>
      </div>
      <div className="text-[12px] text-gray-500 mt-1.5">
        {next ? `Next: ${next.name} · ${formatDate(next.date)}` : "No upcoming deadlines"}
      </div>
    </button>
  );
}

function MultiCourseView({ courses, assignments, exams, onSelectCourse }) {
  if (courses.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center gap-2 text-gray-500">
        <div className="text-4xl mb-1">🎓</div>
        <div className="text-gray-200 font-semibold">No courses yet</div>
        <div className="text-[13px]">Upload a syllabus from the sidebar to get started.</div>
      </div>
    );
  }
  return (
    <div className="h-full overflow-y-auto px-8 py-7">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 max-w-5xl mx-auto">
        {courses.map((c) => (
          <CourseCard key={c.id} course={c} assignments={assignments} exams={exams} onSelect={onSelectCourse} />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Calendar view
// ---------------------------------------------------------------------------

function dateKey(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function CalendarView({ assignments, exams, courses }) {
  const [cursor, setCursor] = useState(() => {
    const t = todayLocal();
    return new Date(t.getFullYear(), t.getMonth(), 1);
  });
  const [selectedDay, setSelectedDay] = useState(null);

  const itemsByDay = useMemo(() => {
    const map = {};
    assignments.forEach((a) => {
      if (!a.due_date) return;
      (map[a.due_date] = map[a.due_date] || []).push({ type: "assignment", ...a });
    });
    exams.forEach((e) => {
      if (!e.date) return;
      (map[e.date] = map[e.date] || []).push({ type: "exam", ...e, due_date: e.date });
    });
    return map;
  }, [assignments, exams]);

  const year = cursor.getFullYear();
  const month = cursor.getMonth();
  const firstDow = new Date(year, month, 1).getDay();
  const totalDays = new Date(year, month + 1, 0).getDate();
  const todayStr = dateKey(todayLocal());

  const cells = [];
  for (let i = 0; i < firstDow; i++) cells.push(null);
  for (let d = 1; d <= totalDays; d++) cells.push(d);

  function courseNameOf(id) {
    return (courses.find((c) => c.id === id) || {}).name || "";
  }

  function dotColor(item) {
    if (item.type === "exam") return "bg-red-500";
    if (item.status === "completed") return "bg-gray-500";
    return "bg-blue-500";
  }

  const selectedItems = selectedDay ? itemsByDay[selectedDay] || [] : [];

  const hasItemsThisMonth = cells.some(
    (d) => d !== null && (itemsByDay[dateKey(new Date(year, month, d))] || []).length > 0
  );

  return (
    <div className="h-full overflow-y-auto px-8 py-7">
      <div className="max-w-5xl mx-auto flex gap-6 items-start">
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-5">
            <button
              onClick={() => setCursor(new Date(year, month - 1, 1))}
              className="w-8 h-8 flex items-center justify-center bg-base-800 border border-base-700 hover:border-indigo-500 text-gray-300 rounded-lg transition"
            >
              ‹
            </button>
            <div className="text-[15px] font-semibold text-gray-100">
              {cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
            </div>
            <button
              onClick={() => setCursor(new Date(year, month + 1, 1))}
              className="w-8 h-8 flex items-center justify-center bg-base-800 border border-base-700 hover:border-indigo-500 text-gray-300 rounded-lg transition"
            >
              ›
            </button>
          </div>

          <div className="grid grid-cols-7 gap-2 mb-2">
            {WEEKDAY_LABELS.map((d) => (
              <div key={d} className="text-center text-[11px] text-gray-500 uppercase tracking-wide">
                {d}
              </div>
            ))}
          </div>

          {hasItemsThisMonth ? (
            <div className="grid grid-cols-7 gap-2">
              {cells.map((d, i) => {
                if (d === null) return <div key={i} />;
                const key = dateKey(new Date(year, month, d));
                const items = itemsByDay[key] || [];
                const isToday = key === todayStr;
                const isSelected = key === selectedDay;
                return (
                  <button
                    key={i}
                    onClick={() => setSelectedDay(key)}
                    className={`h-20 rounded-lg border p-1.5 flex flex-col items-start text-left transition ${
                      isSelected
                        ? "border-indigo-500 bg-indigo-950/20"
                        : "border-base-700 bg-base-850 hover:border-base-600"
                    }`}
                  >
                    <span className={`text-[12px] ${isToday ? "text-indigo-400 font-bold" : "text-gray-400"}`}>
                      {d}
                    </span>
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {items.slice(0, 5).map((it, idx) => (
                        <span key={idx} className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dotColor(it)}`} />
                      ))}
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="bg-base-850 border border-base-700 rounded-2xl py-12 px-6 flex flex-col items-center gap-2 text-center">
              <div className="text-2xl mb-1">🗓️</div>
              <div className="text-[13.5px] text-gray-300">No dated items this month</div>
              <div className="text-[12px] text-gray-500 max-w-xs">
                Upload a syllabus with specific due dates to see them here.
              </div>
            </div>
          )}
        </div>

        <div className="w-[280px] flex-shrink-0">
          <div className="bg-base-850 border border-base-700 rounded-2xl p-4">
            <div className="text-[13px] font-semibold text-gray-300 mb-3">
              {selectedDay
                ? new Date(selectedDay + "T00:00:00").toLocaleDateString(undefined, {
                    weekday: "long",
                    month: "short",
                    day: "numeric",
                  })
                : "Select a day"}
            </div>
            {selectedDay && selectedItems.length === 0 && (
              <div className="text-[12px] text-gray-500">Nothing due this day.</div>
            )}
            {!selectedDay && (
              <div className="text-[12px] text-gray-500">Click any day to see what's due.</div>
            )}
            <div className="space-y-2">
              {selectedItems.map((it, idx) => (
                <div key={idx} className="bg-base-900 border border-base-700 rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dotColor(it)}`} />
                    <span className="text-[12.5px] text-gray-100 truncate">{it.name}</span>
                  </div>
                  <div className="text-[11px] text-gray-500">
                    {courseNameOf(it.course_id)}
                    {it.weight != null ? ` · ${it.weight}%` : ""}
                    {it.type === "exam" ? " · exam" : ""}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Upload modal
// ---------------------------------------------------------------------------

function UploadModal({ open, onClose, onUploaded, pushToast }) {
  const [status, setStatus] = useState("idle"); // idle | uploading | success | error
  const [progress, setProgress] = useState(0);
  const [errorMsg, setErrorMsg] = useState("");
  const [successData, setSuccessData] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  function reset() {
    setStatus("idle");
    setProgress(0);
    setErrorMsg("");
    setSuccessData(null);
    setDragOver(false);
  }

  function handleClose() {
    reset();
    onClose();
  }

  function handleFile(file) {
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setStatus("error");
      setErrorMsg("Please select a PDF file.");
      return;
    }
    upload(file);
  }

  function upload(file) {
    setStatus("uploading");
    setProgress(0);

    const formData = new FormData();
    formData.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/syllabus/upload-syllabus");

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        setProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.onload = () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch (e) {
        // ignore parse failure
      }
      if (xhr.status >= 200 && xhr.status < 300 && data) {
        setStatus("success");
        setSuccessData(data);
        setTimeout(() => {
          onUploaded(data.course.id);
          reset();
        }, 1400);
      } else {
        setStatus("error");
        setErrorMsg((data && data.detail) || `Upload failed (${xhr.status})`);
      }
    };

    xhr.onerror = () => {
      setStatus("error");
      setErrorMsg("Could not reach the server.");
    };

    xhr.send(formData);
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center fade-in-up"
      onClick={(e) => {
        if (e.target === e.currentTarget && status !== "uploading") handleClose();
      }}
    >
      <div className="bg-base-900 border border-base-700 rounded-2xl w-[460px] max-w-[90vw] p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-5">
          <div className="text-[15px] font-semibold text-gray-100">Upload Syllabus</div>
          {status !== "uploading" && (
            <button onClick={handleClose} className="text-gray-500 hover:text-gray-300 text-lg leading-none">
              ✕
            </button>
          )}
        </div>

        {status === "idle" && (
          <div
            onClick={() => fileInputRef.current && fileInputRef.current.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              handleFile(e.dataTransfer.files[0]);
            }}
            className={`border-2 border-dashed rounded-xl py-12 px-6 flex flex-col items-center gap-3 text-center cursor-pointer transition ${
              dragOver ? "border-indigo-500 bg-indigo-950/20" : "border-base-600 hover:border-base-500"
            }`}
          >
            <div className="text-3xl">📄</div>
            <div className="text-[13.5px] text-gray-300">Drop your syllabus PDF here</div>
            <div className="text-[12px] text-gray-500">or click to browse</div>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={(e) => handleFile(e.target.files[0])}
            />
          </div>
        )}

        {status === "uploading" && (
          <div className="py-10 px-2 flex flex-col items-center gap-4">
            <Spinner className="w-6 h-6" />
            <div className="text-[13.5px] text-gray-300">Uploading and extracting syllabus…</div>
            <div className="w-full h-2 bg-base-700 rounded-full overflow-hidden">
              <div className="h-full bg-gradient-to-r from-indigo-600 to-purple-600 transition-all" style={{ width: `${progress}%` }} />
            </div>
            <div className="text-[11px] text-gray-500">{progress}%</div>
          </div>
        )}

        {status === "success" && successData && (
          <div className="py-8 px-2 flex flex-col items-center gap-2 text-center">
            <div className="text-3xl mb-1">✅</div>
            <div className="text-[14px] font-semibold text-gray-100">{successData.course.name}</div>
            {successData.message ? (
              <div className="text-[13px] text-yellow-400">{successData.message}</div>
            ) : (
              <div className="text-[13px] text-gray-400">
                {successData.assignments_created} assignment(s) · {successData.exams_created} exam(s) found
              </div>
            )}
            <div className="text-[11.5px] text-gray-500 mt-1">Switching to this course…</div>
          </div>
        )}

        {status === "error" && (
          <div className="py-8 px-2 flex flex-col items-center gap-3 text-center">
            <div className="text-3xl mb-1">⚠️</div>
            <div className="text-[13.5px] text-red-300">{errorMsg}</div>
            <button onClick={reset} className="bg-indigo-600 hover:opacity-90 text-white text-[12.5px] rounded-lg px-4 py-2 mt-1">
              Try again
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Alerts panel
// ---------------------------------------------------------------------------

function AlertItem({ alert, courseName, onMarkRead, onDismiss }) {
  const group = ALERT_GROUP_OF[alert.alert_type] || "Info";
  const style = ALERT_GROUP_STYLES[group];
  return (
    <div
      onClick={() => onMarkRead(alert.id)}
      className="group flex items-start gap-3 px-4 py-3 border-b border-base-700 hover:bg-base-800/60 cursor-pointer transition"
    >
      <span className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${style.bar}`} />
      <div className="flex-1 min-w-0">
        <div className="text-[13px] text-gray-200 leading-snug">{alert.message}</div>
        <div className="flex items-center gap-2 mt-1 text-[11px] text-gray-500">
          <span>{courseName}</span>
          <span>·</span>
          <span>{timeAgo(alert.created_at)}</span>
        </div>
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDismiss(alert.id);
        }}
        className="text-gray-600 hover:text-gray-300 opacity-0 group-hover:opacity-100 transition flex-shrink-0 px-1"
      >
        ✕
      </button>
    </div>
  );
}

function AlertsPanel({ open, alerts, courses, onClose, onMarkAllRead, onMarkRead, onDismiss }) {
  const courseName = (id) => (id ? (courses.find((c) => c.id === id) || {}).name || "Course" : "General");

  const grouped = ALERT_GROUP_ORDER.map((group) => ({
    group,
    items: alerts.filter((a) => (ALERT_GROUP_OF[a.alert_type] || "Info") === group),
  })).filter((g) => g.items.length > 0);

  return (
    <React.Fragment>
      <div
        onClick={onClose}
        className={`fixed inset-0 bg-black/40 z-40 transition-opacity ${open ? "opacity-100" : "opacity-0 pointer-events-none"}`}
      />
      <div
        className={`fixed top-0 right-0 h-full w-[380px] bg-base-900 border-l border-base-700 z-50 flex flex-col transition-transform duration-300 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-base-700 flex-shrink-0">
          <div className="text-[14px] font-semibold text-gray-100">Alerts</div>
          <div className="flex items-center gap-3">
            <button onClick={onMarkAllRead} className="text-[12px] text-indigo-400 hover:text-indigo-300">
              Mark all read
            </button>
            <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-lg leading-none">
              ✕
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {alerts.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center gap-2 text-gray-500 px-6">
              <div className="text-3xl">🎉</div>
              <div className="text-[13.5px]">You're all caught up 🎉</div>
            </div>
          ) : (
            grouped.map(({ group, items }) => (
              <div key={group}>
                <div className={`px-5 pt-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wide ${ALERT_GROUP_STYLES[group].label}`}>
                  {group}
                </div>
                {items.map((a) => (
                  <AlertItem key={a.id} alert={a} courseName={courseName(a.course_id)} onMarkRead={onMarkRead} onDismiss={onDismiss} />
                ))}
              </div>
            ))
          )}
        </div>
      </div>
    </React.Fragment>
  );
}

// ---------------------------------------------------------------------------
// Root App
// ---------------------------------------------------------------------------

function App() {
  const [courses, setCourses] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [exams, setExams] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [activeCourseId, setActiveCourseId] = useState("all");
  const [view, setView] = useState("chat");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [chatResetToken, setChatResetToken] = useState(0);
  const [toast, setToast] = useState(null);

  const pushToast = useCallback((type, msg) => {
    setToast({ type, msg });
    clearTimeout(window.__toastTimer);
    window.__toastTimer = setTimeout(() => setToast(null), 3500);
  }, []);

  const refreshExamsForCourses = useCallback(async (courseList) => {
    if (!courseList.length) {
      setExams([]);
      return;
    }
    try {
      const details = await Promise.all(courseList.map((c) => apiFetch(`/courses/${c.id}`).catch(() => null)));
      const all = [];
      details.forEach((d) => {
        if (d && d.exams) all.push(...d.exams);
      });
      setExams(all);
    } catch (e) {
      // best-effort
    }
  }, []);

  const refreshCourses = useCallback(async () => {
    try {
      const data = await apiFetch("/courses");
      // dedupe by name (case insensitive), keeping the highest id of each group
      const byName = new Map();
      data.forEach((c) => {
        const key = c.name.trim().toLowerCase();
        const existing = byName.get(key);
        if (!existing || c.id > existing.id) byName.set(key, c);
      });
      const deduped = Array.from(byName.values()).sort((a, b) => a.id - b.id);
      setCourses(deduped);
      refreshExamsForCourses(deduped);
      return deduped;
    } catch (e) {
      pushToast("error", e.message);
      return [];
    }
  }, [refreshExamsForCourses, pushToast]);

  const refreshAssignments = useCallback(async () => {
    try {
      const data = await apiFetch("/assignments");
      setAssignments(data);
    } catch (e) {
      // best-effort
    }
  }, []);

  const refreshAlerts = useCallback(async () => {
    try {
      const data = await apiFetch("/alerts");
      setAlerts(data);
    } catch (e) {
      // best-effort
    }
  }, []);

  useEffect(() => {
    refreshCourses();
    refreshAssignments();
    refreshAlerts();
    const interval = setInterval(refreshAlerts, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  function selectCourse(id) {
    setActiveCourseId(id);
  }

  async function handleUploaded(courseId) {
    setUploadOpen(false);
    const cs = await refreshCourses();
    await refreshAssignments();
    setActiveCourseId(courseId);
    setView("dashboard");
    pushToast("success", "Syllabus uploaded successfully.");
  }

  async function handleCourseDeleted() {
    const cs = await refreshCourses();
    await refreshAssignments();
    setActiveCourseId(cs.length ? cs[0].id : "all");
  }

  async function handleMarkRead(id) {
    setAlerts((prev) => prev.filter((a) => a.id !== id));
    try {
      await apiFetch(`/alerts/${id}/read`, { method: "PATCH" });
    } catch (e) {
      pushToast("error", e.message);
    }
  }

  async function handleDismiss(id) {
    setAlerts((prev) => prev.filter((a) => a.id !== id));
    try {
      await apiFetch(`/alerts/${id}`, { method: "DELETE" });
    } catch (e) {
      pushToast("error", e.message);
    }
  }

  async function handleMarkAllRead() {
    setAlerts([]);
    try {
      await apiFetch("/alerts/read-all", { method: "PATCH" });
    } catch (e) {
      pushToast("error", e.message);
    }
  }

  const courseName =
    activeCourseId === "all" ? "All Courses" : (courses.find((c) => c.id === activeCourseId) || {}).name || "Loading…";

  const showMultiCourse = view === "dashboard" && activeCourseId === "all";

  return (
    <div className="flex h-screen w-screen bg-base-950 text-gray-100 overflow-hidden">
      <Sidebar
        courses={courses}
        assignments={assignments}
        activeCourseId={activeCourseId}
        onSelectCourse={selectCourse}
        onOpenUpload={() => setUploadOpen(true)}
        alertCount={alerts.length}
        onToggleAlerts={() => setAlertsOpen((o) => !o)}
      />

      <div className="flex-1 flex flex-col min-w-0">
        <TopBar
          courseName={courseName}
          view={view}
          onChangeView={setView}
          onNewChat={() => setChatResetToken((t) => t + 1)}
          onOpenExport={() => setExportOpen(true)}
        />

        <div className="flex-1 overflow-hidden relative">
          {view === "chat" && (
            <ChatView key={`${activeCourseId}-${chatResetToken}`} courseId={activeCourseId} courses={courses} pushToast={pushToast} />
          )}

          {showMultiCourse && (
            <MultiCourseView courses={courses} assignments={assignments} exams={exams} onSelectCourse={(id) => { setActiveCourseId(id); }} />
          )}

          {view === "dashboard" && activeCourseId !== "all" && (
            <DashboardView
              key={activeCourseId}
              courseId={activeCourseId}
              exams={exams.filter((e) => e.course_id === activeCourseId)}
              pushToast={pushToast}
              onGlobalRefresh={refreshAssignments}
              onCourseDeleted={handleCourseDeleted}
            />
          )}

          {view === "calendar" && (
            <CalendarView
              key={activeCourseId}
              assignments={activeCourseId === "all" ? assignments : assignments.filter((a) => a.course_id === activeCourseId)}
              exams={activeCourseId === "all" ? exams : exams.filter((e) => e.course_id === activeCourseId)}
              courses={courses}
            />
          )}
        </div>
      </div>

      <AlertsPanel
        open={alertsOpen}
        alerts={alerts}
        courses={courses}
        onClose={() => setAlertsOpen(false)}
        onMarkAllRead={handleMarkAllRead}
        onMarkRead={handleMarkRead}
        onDismiss={handleDismiss}
      />

      <UploadModal open={uploadOpen} onClose={() => setUploadOpen(false)} onUploaded={handleUploaded} pushToast={pushToast} />

      <ExportModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        courses={courses}
        activeCourseId={activeCourseId}
        pushToast={pushToast}
      />

      <Toast toast={toast} />
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
