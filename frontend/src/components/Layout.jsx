import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../AuthContext";
import BrandLogo from "./BrandLogo";

export default function Layout() {
  const { user, logout, setTheme } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const theme = user?.theme_preference || "dark";
  const onSchedules = location.pathname.startsWith("/app/schedules");

  return (
    <div className="app-shell">
      <div className="main">
        <div className="topbar">
          <div className="topbar-start">
            <Link to="/app" className="brand-mark brand-link" style={{ marginBottom: 0 }}>
              <BrandLogo size={40} />
              <div>
                <strong>Onedo bot</strong>
                <div className="muted topbar-subtitle">
                  به ایجنت بگو چه می‌خواهی؛ خودش وقتی لازم باشد مرورگر را کنترل می‌کند.
                </div>
              </div>
            </Link>
          </div>
          <div className="topbar-actions">
            <Link className={`btn soft${onSchedules ? " active-nav" : ""}`} to="/app/schedules">
              کارهای دوره‌ای
            </Link>
            <button
              className="btn soft"
              type="button"
              onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            >
              {theme === "light" ? "تاریک" : "روشن"}
            </button>
            <button
              className="btn ghost"
              type="button"
              onClick={() => {
                logout();
                navigate("/");
              }}
            >
              خروج
            </button>
          </div>
        </div>
        <div className="content">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
