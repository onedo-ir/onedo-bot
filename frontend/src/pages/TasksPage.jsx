import { useEffect, useState } from "react";
import { api } from "../api";

const statusLabel = {
  pending: "در صف",
  running: "در حال اجرا",
  waiting_user: "منتظر شما",
  completed: "تمام",
  failed: "ناموفق",
  cancelled: "لغو شده",
};

export default function TasksPage() {
  const [tasks, setTasks] = useState([]);
  const [error, setError] = useState("");

  async function load() {
    try {
      setTasks(await api.tasks());
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="panel">
      <div>
        <h2 style={{ margin: 0 }}>تاریخچه کارها</h2>
        <p className="muted" style={{ marginTop: 6 }}>
          خلاصه نتیجه بعد از هر کار اینجا هم می‌ماند.
        </p>
      </div>
      {error && <div className="error-box">{error}</div>}
      <div style={{ overflowX: "auto" }}>
        <table className="table">
          <thead>
            <tr>
              <th>#</th>
              <th>دستور</th>
              <th>وضعیت</th>
              <th>خلاصه</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((t) => (
              <tr key={t.id}>
                <td>{t.id}</td>
                <td>{t.instruction.slice(0, 80)}</td>
                <td>
                  <span className="badge">{statusLabel[t.status] || t.status}</span>
                </td>
                <td>{t.summary || t.waiting_question || "—"}</td>
                <td>
                  {["pending", "running", "waiting_user"].includes(t.status) && (
                    <button className="btn ghost" type="button" onClick={() => api.cancelTask(t.id).then(load)}>
                      لغو
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
