import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../AuthContext";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password);
      navigate("/app");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-shell">
      <form className="auth-card stack" onSubmit={onSubmit}>
        <div className="brand-mark">
          <div className="brand-dot" aria-hidden="true" />
          <h1>ورود</h1>
        </div>
        <p className="muted" style={{ marginTop: 0 }}>
          با همان حساب تعریف‌شده در فایل .env وارد شوید.
        </p>
        {error && <div className="error-box">{error}</div>}
        <label>
          ایمیل
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            type="text"
            autoComplete="username"
            required
          />
        </label>
        <label>
          رمز عبور
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            autoComplete="current-password"
            required
          />
        </label>
        <button className="btn" disabled={busy} type="submit">
          {busy ? "در حال ورود…" : "ورود"}
        </button>
        <div className="muted">
          <Link to="/">بازگشت</Link>
        </div>
      </form>
    </div>
  );
}
