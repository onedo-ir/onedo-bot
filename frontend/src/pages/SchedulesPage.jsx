import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

function formatWhen(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString("fa-IR");
  } catch {
    return String(value);
  }
}

function formatInterval(minutes) {
  const m = Number(minutes) || 0;
  if (m >= 1440 && m % 1440 === 0) {
    const days = m / 1440;
    return days === 1 ? "هر روز" : `هر ${days} روز`;
  }
  if (m >= 60 && m % 60 === 0) {
    const hours = m / 60;
    return hours === 1 ? "هر ساعت" : `هر ${hours} ساعت`;
  }
  return `هر ${m} دقیقه`;
}

export default function SchedulesPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState(null);
  const [expandedId, setExpandedId] = useState(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const data = await api.scheduledTasks();
      setItems(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || "خطا در بارگذاری");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onDelete = async (id) => {
    if (deletingId) return;
    if (!window.confirm("این کار دوره‌ای حذف شود؟")) return;
    setDeletingId(id);
    setError("");
    try {
      await api.deleteScheduledTask(id);
      setItems((prev) => prev.filter((row) => row.id !== id));
      if (expandedId === id) setExpandedId(null);
    } catch (err) {
      setError(err.message || "حذف نشد");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="schedules-page">
      <div className="panel schedules-panel">
        <div className="panel-header" style={{ margin: "-20px -20px 0", padding: "14px 16px" }}>
          <div>
            <strong>کارهای دوره‌ای</strong>
            <div className="muted" style={{ fontSize: "0.86rem", marginTop: 4 }}>
              از چت بخواهید کار را دوره‌ای کند؛ اینجا فقط مشاهده و حذف است.
            </div>
          </div>
          <div className="panel-header-actions">
            <Link className="btn soft" to="/app">
              بازگشت به چت
            </Link>
            <button className="btn ghost" type="button" onClick={load} disabled={loading}>
              تازه‌سازی
            </button>
          </div>
        </div>

        {error ? <div className="error-box">{error}</div> : null}

        {loading ? (
          <div className="muted">در حال بارگذاری…</div>
        ) : items.length === 0 ? (
          <div className="muted schedules-empty">
            هنوز کار دوره‌ای ثبت نشده. در چت بگویید مثلاً «این کار را هر ۲ ساعت تکرار کن».
          </div>
        ) : (
          <div className="schedules-list">
            {items.map((row) => {
              const open = expandedId === row.id;
              return (
                <div className="schedule-row" key={row.id}>
                  <div className="schedule-row-main">
                    <div className="schedule-row-text">
                      <strong>{row.title}</strong>
                      <div className="muted schedule-meta">
                        {formatInterval(row.interval_minutes)}
                        {" · "}
                        بعدی: {formatWhen(row.next_run_at)}
                        {row.last_run_at ? ` · آخرین: ${formatWhen(row.last_run_at)}` : ""}
                        {row.enabled ? "" : " · غیرفعال"}
                      </div>
                    </div>
                    <div className="schedule-row-actions">
                      <button
                        className="btn soft"
                        type="button"
                        onClick={() => setExpandedId(open ? null : row.id)}
                      >
                        {open ? "بستن مراحل" : "مراحل"}
                      </button>
                      <button
                        className="btn ghost danger-text"
                        type="button"
                        disabled={deletingId === row.id}
                        onClick={() => onDelete(row.id)}
                      >
                        {deletingId === row.id ? "…" : "حذف"}
                      </button>
                    </div>
                  </div>
                  {open ? (
                    <pre className="schedule-steps">{row.steps_preview || "(خالی)"}</pre>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
