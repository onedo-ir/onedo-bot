import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../AuthContext";

export default function Layout() {
  const { user, logout, setTheme } = useAuth();
  const navigate = useNavigate();
  const theme = user?.theme_preference || "light";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-top">
          <div className="brand-mark" style={{ marginBottom: 0 }}>
            <div className="brand-dot" />
            <div>
              <strong>Onedo bot</strong>
              <div className="muted" style={{ fontSize: "0.78rem" }}>
                دستیار مرورگر شما
              </div>
            </div>
          </div>
        </div>

        <nav className="nav-list">
          <NavLink className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`} to="/app" end>
            گفتگو و مرورگر
          </NavLink>
          <NavLink className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`} to="/app/tasks">
            تاریخچه کارها
          </NavLink>
          <NavLink
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
            to="/app/credentials"
          >
            حساب‌ها و رمزها
          </NavLink>
          {user?.role === "admin" && (
            <NavLink
              className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
              to="/app/admin"
            >
              پنل مدیریت
            </NavLink>
          )}
        </nav>

        <div style={{ marginTop: "auto" }} className="stack">
          <button
            className="btn soft"
            type="button"
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
          >
            {theme === "light" ? "حالت تاریک" : "حالت روشن"}
          </button>
          <div className="muted" style={{ fontSize: "0.85rem" }}>
            {user?.full_name || user?.email}
          </div>
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
      </aside>

      <div className="main">
        <div className="topbar">
          <div>
            <strong>سلام {user?.full_name || "دوست عزیز"}</strong>
            <div className="muted" style={{ fontSize: "0.9rem" }}>
              کار را مثل چت بگو؛ من در کروم انجامش می‌دهم.
            </div>
          </div>
        </div>
        <div className="content">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
