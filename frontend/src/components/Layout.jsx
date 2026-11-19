import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../AuthContext";

export default function Layout() {
  const { user, logout, setTheme } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const theme = user?.theme_preference || "dark";
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    document.body.style.overflow = menuOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [menuOpen]);

  return (
    <div className={`app-shell ${menuOpen ? "menu-open" : ""}`}>
      <button
        className={`sidebar-backdrop ${menuOpen ? "visible" : ""}`}
        type="button"
        aria-label="بستن منو"
        onClick={() => setMenuOpen(false)}
      />

      <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
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
          <button
            className="icon-btn sidebar-close"
            type="button"
            aria-label="بستن منو"
            onClick={() => setMenuOpen(false)}
          >
            ✕
          </button>
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

        <div className="sidebar-footer stack">
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
          <div className="topbar-start">
            <button
              className="icon-btn menu-toggle"
              type="button"
              aria-label="باز کردن منو"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen(true)}
            >
              ☰
            </button>
            <div>
              <strong>سلام {user?.full_name || "دوست عزیز"}</strong>
              <div className="muted topbar-subtitle">
                کار را مثل چت بگو؛ من در کروم انجامش می‌دهم.
              </div>
            </div>
          </div>
          <button
            className="btn soft theme-toggle-inline"
            type="button"
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
          >
            {theme === "light" ? "تاریک" : "روشن"}
          </button>
        </div>
        <div className="content">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
