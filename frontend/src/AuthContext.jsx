import { createContext, useContext, useEffect, useState } from "react";
import { api, clearToken, getToken, setToken } from "./api";

const AuthContext = createContext(null);
const DEFAULT_THEME = "dark";
const THEME_KEY = "onedo_theme";

function readStoredTheme() {
  return localStorage.getItem(THEME_KEY) || DEFAULT_THEME;
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme || DEFAULT_THEME);
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [theme, setThemeState] = useState(readStoredTheme);

  async function refresh() {
    if (!getToken()) {
      setUser(null);
      applyTheme(readStoredTheme());
      setLoading(false);
      return;
    }
    try {
      const me = await api.me();
      setUser({ ...me, theme_preference: readStoredTheme() });
      applyTheme(readStoredTheme());
    } catch {
      clearToken();
      setUser(null);
      applyTheme(readStoredTheme());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    applyTheme(readStoredTheme());
    refresh();
  }, []);

  async function login(email, password) {
    const token = await api.login({ email, password });
    setToken(token.access_token);
    await refresh();
  }

  function logout() {
    clearToken();
    setUser(null);
    applyTheme(readStoredTheme());
  }

  function setTheme(next) {
    const value = next === "light" ? "light" : "dark";
    localStorage.setItem(THEME_KEY, value);
    setThemeState(value);
    applyTheme(value);
    setUser((prev) => (prev ? { ...prev, theme_preference: value } : prev));
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, setTheme, theme, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
