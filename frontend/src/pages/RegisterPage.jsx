import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../AuthContext";

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await register({ email, password, full_name: fullName });
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
          <div className="brand-dot" />
          <h1>ثبت‌نام</h1>
        </div>
        <p className="muted" style={{ marginTop: 0 }}>
          فقط با ایمیل یک حساب بساز و از همین‌جا به ایجنت بگو چه کار کند.
        </p>
        {error && <div className="error-box">{error}</div>}
        <label>
          نام
          <input value={fullName} onChange={(e) => setFullName(e.target.value)} required />
        </label>
        <label>
          ایمیل
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
        </label>
        <label>
          رمز عبور
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            minLength={6}
            required
          />
        </label>
        <button className="btn" disabled={busy} type="submit">
          {busy ? "در حال ثبت…" : "ساخت حساب"}
        </button>
        <div className="muted">
          قبلاً ثبت‌نام کردی؟ <Link to="/login">ورود</Link>
        </div>
      </form>
    </div>
  );
}
