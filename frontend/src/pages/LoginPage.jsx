import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../AuthContext";
import BrandLogo from "../components/BrandLogo";

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (loading) return <div className="auth-shell muted">در حال بارگذاری…</div>;
  if (user) return <Navigate to="/app" replace />;

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
          <BrandLogo size={52} />
          <div>
            <div className="brand-titling">Onedo bot</div>
            <h1>ورود</h1>
          </div>
        </div>
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
      </form>
    </div>
  );
}
