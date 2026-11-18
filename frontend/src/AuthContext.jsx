import { createContext, useContext, useEffect, useState } from "react";
import { api, clearToken, getToken, setToken } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.me();
      setUser(me);
      document.documentElement.setAttribute("data-theme", me.theme_preference || "light");
    } catch {
      clearToken();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function login(email, password) {
    const token = await api.login({ email, password });
    setToken(token.access_token);
    await refresh();
  }

  async function register(payload) {
    await api.register(payload);
    await login(payload.email, payload.password);
  }

  function logout() {
    clearToken();
    setUser(null);
  }

  async function setTheme(theme) {
    const updated = await api.updateMe({ theme_preference: theme });
    setUser(updated);
    document.documentElement.setAttribute("data-theme", theme);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, setTheme, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
