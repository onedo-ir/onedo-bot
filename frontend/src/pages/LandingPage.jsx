import { Link } from "react-router-dom";
import { useAuth } from "../AuthContext";

export default function LandingPage() {
  const { user } = useAuth();

  return (
    <div className="auth-shell">
      <div className="auth-card" style={{ width: "min(720px, 100%)" }}>
        <div className="brand-mark">
          <div className="brand-dot" aria-hidden="true" />
          <div>
            <h1 className="hero-title">Onedo</h1>
            <div className="muted" style={{ fontSize: "0.9rem", fontWeight: 500 }}>browser agent</div>
          </div>
        </div>
        <p className="hero-copy">
          ایجنت هوش مصنوعی که وقتی لازم باشد مرورگر را به دست می‌گیرد؛ چت کن، تماشا کن، نتیجه را
          خلاصه بگیر.
        </p>
        <div className="hero-actions">
          {user ? (
            <Link className="btn" to="/app">
              ادامه در میز کار
            </Link>
          ) : (
            <>
              <Link className="btn" to="/login">
                ورود
              </Link>
              <Link className="btn ghost" to="/register">
                ساخت حساب
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
