import { Link } from "react-router-dom";
import { useAuth } from "../AuthContext";

export default function LandingPage() {
  const { user } = useAuth();

  return (
    <div className="auth-shell">
      <div className="auth-card" style={{ width: "min(720px, 100%)" }}>
        <div className="brand-mark">
          <div className="brand-dot" />
          <h1>Onedo bot</h1>
        </div>
        <p className="muted" style={{ fontSize: "1.05rem", lineHeight: 1.9, marginTop: 0 }}>
          دستیار گرم و خودمانی شما برای کارهای مرورگر: پر کردن فرم، خرید آنلاین، جمع‌آوری اطلاعات،
          کارهای تکراری روزانه و مدیریت پنل‌ها — با چت متنی و تماشای زندهٔ کروم.
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {user ? (
            <Link className="btn" to="/app">
              برو به میز کار
            </Link>
          ) : (
            <>
              <Link className="btn" to="/login">
                ورود
              </Link>
              <Link className="btn ghost" to="/register">
                ثبت‌نام با ایمیل
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
