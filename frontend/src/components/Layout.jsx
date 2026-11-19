import { Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../AuthContext";

export default function Layout() {
  const { user, logout, setTheme } = useAuth();
  const navigate = useNavigate();
  const theme = user?.theme_preference || "dark";

  return (
    <div className="app-shell">
      <div className="main">
        <div className="topbar">
          <div className="topbar-start">
            <div className="brand-mark" style={{ marginBottom: 0 }}>
              <div className="brand-dot" aria-hidden="true" />
              <div>
                <strong>Onedo</strong>
                <div className="muted topbar-subtitle">
                  به ایجنت بگو چه می‌خواهی؛ خودش وقتی لازم باشد مرورگر را کنترل می‌کند.
                </div>
              </div>
            </div>
          </div>
          <div className="topbar-actions">
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
