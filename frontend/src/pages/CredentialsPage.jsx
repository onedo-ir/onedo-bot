import { useEffect, useState } from "react";
import { api } from "../api";

export default function CredentialsPage() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ label: "", site_url: "", username: "", secret_note: "" });
  const [error, setError] = useState("");

  async function load() {
    setItems(await api.credentials());
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    try {
      await api.createCredential(form);
      setForm({ label: "", site_url: "", username: "", secret_note: "" });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="panel">
      <div>
        <h2 style={{ margin: 0 }}>حساب‌ها و رمزها</h2>
        <p className="muted" style={{ marginTop: 6 }}>
          هنوز سیاست نهایی ذخیره رمز مشخص نشده؛ فعلاً برچسب و یادداشت امن محلی نگه داشته می‌شود.
        </p>
      </div>
      {error && <div className="error-box">{error}</div>}
      <form className="stack" onSubmit={onSubmit} style={{ maxWidth: 520 }}>
        <label>
          برچسب
          <input
            value={form.label}
            onChange={(e) => setForm({ ...form, label: e.target.value })}
            required
          />
        </label>
        <label>
          آدرس سایت
          <input
            value={form.site_url}
            onChange={(e) => setForm({ ...form, site_url: e.target.value })}
          />
        </label>
        <label>
          نام کاربری
          <input
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
          />
        </label>
        <label>
          یادداشت
          <textarea
            value={form.secret_note}
            onChange={(e) => setForm({ ...form, secret_note: e.target.value })}
          />
        </label>
        <button className="btn" type="submit">
          ذخیره
        </button>
      </form>

      <div style={{ overflowX: "auto" }}>
        <table className="table">
          <thead>
            <tr>
              <th>برچسب</th>
              <th>سایت</th>
              <th>کاربر</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.label}</td>
                <td>{item.site_url || "—"}</td>
                <td>{item.username || "—"}</td>
                <td>
                  <button
                    className="btn ghost"
                    type="button"
                    onClick={() => api.deleteCredential(item.id).then(load)}
                  >
                    حذف
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
