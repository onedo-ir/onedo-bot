import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../AuthContext";

export default function AdminPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [config, setConfig] = useState({ base_url: "", model: "", api_key: "" });
  const [newUser, setNewUser] = useState({ email: "", password: "", full_name: "", role: "user" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load() {
    const [s, u, t, c] = await Promise.all([
      api.adminStats(),
      api.adminUsers(),
      api.adminTasks(),
      api.agentConfig(),
    ]);
    setStats(s);
    setUsers(u);
    setTasks(t);
    setConfig({ base_url: c.base_url, model: c.model, api_key: "" });
  }

  useEffect(() => {
    if (user?.role === "admin") {
      load().catch((err) => setError(err.message));
    }
  }, [user]);

  if (user?.role !== "admin") return <Navigate to="/app" replace />;

  async function saveConfig(e) {
    e.preventDefault();
    setError("");
    try {
      const body = { base_url: config.base_url, model: config.model };
      if (config.api_key) body.api_key = config.api_key;
      await api.updateAgentConfig(body);
      setMessage("تنظیمات AI ذخیره شد");
      setConfig((prev) => ({ ...prev, api_key: "" }));
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function createUser(e) {
    e.preventDefault();
    setError("");
    try {
      await api.adminCreateUser(newUser);
      setNewUser({ email: "", password: "", full_name: "", role: "user" });
      setMessage("کاربر ساخته شد");
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="panel">
      <div>
        <h2 style={{ margin: 0 }}>پنل مدیریت</h2>
        <p className="muted" style={{ marginTop: 6 }}>
          همان اکشن‌ها از REST API با توکن ADMIN_API_TOKEN هم در دسترس‌اند.
        </p>
      </div>

      {error && <div className="error-box">{error}</div>}
      {message && <div className="badge">{message}</div>}

      {stats && (
        <div className="stats">
          <div className="stat">
            کاربران<strong>{stats.users_count}</strong>
          </div>
          <div className="stat">
            گفتگوها<strong>{stats.conversations_count}</strong>
          </div>
          <div className="stat">
            کارها<strong>{stats.tasks_count}</strong>
          </div>
          <div className="stat">
            در حال اجرا<strong>{stats.running_tasks}</strong>
          </div>
          <div className="stat">
            تکمیل‌شده<strong>{stats.completed_tasks}</strong>
          </div>
        </div>
      )}

      <form className="stack" onSubmit={saveConfig} style={{ maxWidth: 560 }}>
        <h3 style={{ marginBottom: 0 }}>اتصال AI سازگار با OpenAI</h3>
        <label>
          Base URL
          <input
            value={config.base_url}
            onChange={(e) => setConfig({ ...config, base_url: e.target.value })}
          />
        </label>
        <label>
          Model
          <input
            value={config.model}
            onChange={(e) => setConfig({ ...config, model: e.target.value })}
          />
        </label>
        <label>
          API Key (خالی بگذار اگر تغییر ندهد)
          <input
            type="password"
            value={config.api_key}
            onChange={(e) => setConfig({ ...config, api_key: e.target.value })}
            placeholder="sk-..."
          />
        </label>
        <button className="btn" type="submit">
          ذخیره تنظیمات AI
        </button>
      </form>

      <form className="stack" onSubmit={createUser} style={{ maxWidth: 560 }}>
        <h3 style={{ marginBottom: 0 }}>کاربر جدید</h3>
        <label>
          نام
          <input
            value={newUser.full_name}
            onChange={(e) => setNewUser({ ...newUser, full_name: e.target.value })}
          />
        </label>
        <label>
          ایمیل
          <input
            type="email"
            value={newUser.email}
            onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
            required
          />
        </label>
        <label>
          رمز
          <input
            type="password"
            value={newUser.password}
            onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
            required
          />
        </label>
        <label>
          نقش
          <select
            value={newUser.role}
            onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
          >
            <option value="user">user</option>
            <option value="admin">admin</option>
          </select>
        </label>
        <button className="btn" type="submit">
          ساخت کاربر
        </button>
      </form>

      <h3>کاربران</h3>
      <div style={{ overflowX: "auto" }}>
      <table className="table">
        <thead>
          <tr>
            <th>ایمیل</th>
            <th>نقش</th>
            <th>فعال</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.email}</td>
              <td>{u.role}</td>
              <td>{u.is_active ? "بله" : "خیر"}</td>
              <td>
                <button
                  className="btn ghost"
                  type="button"
                  onClick={() =>
                    api.adminUpdateUser(u.id, { is_active: !u.is_active }).then(load)
                  }
                >
                  {u.is_active ? "غیرفعال" : "فعال"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>

      <h3>آخرین کارها</h3>
      <div style={{ overflowX: "auto" }}>
      <table className="table">
        <thead>
          <tr>
            <th>#</th>
            <th>دستور</th>
            <th>وضعیت</th>
          </tr>
        </thead>
        <tbody>
          {tasks.slice(0, 20).map((t) => (
            <tr key={t.id}>
              <td>{t.id}</td>
              <td>{t.instruction.slice(0, 100)}</td>
              <td>{t.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}
