const TOKEN_KEY = "onedo_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function request(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(path, { ...options, headers });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = data?.detail || data?.message || "خطایی رخ داد";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

export const api = {
  health: () => request("/api/health"),
  login: (body) => request("/api/auth/login", { method: "POST", body: JSON.stringify(body) }),
  me: () => request("/api/auth/me"),
  conversations: () => request("/api/chat/conversations"),
  createConversation: (title = "گفتگوی جدید") =>
    request("/api/chat/conversations", { method: "POST", body: JSON.stringify({ title }) }),
  getConversation: (id) => request(`/api/chat/conversations/${id}`),
  deleteConversation: (id) => request(`/api/chat/conversations/${id}`, { method: "DELETE" }),
  sendMessage: (id, content) =>
    request(`/api/chat/conversations/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  browserStatus: () => request("/api/browser/status"),
  browserReset: () => request("/api/browser/reset", { method: "POST" }),
  browserNavigate: (url) =>
    request("/api/browser/navigate", { method: "POST", body: JSON.stringify({ url }) }),
  browserClick: (x, y, button = "left") =>
    request("/api/browser/input/click", {
      method: "POST",
      body: JSON.stringify({ x, y, button }),
    }),
  browserDblClick: (x, y) =>
    request("/api/browser/input/dblclick", {
      method: "POST",
      body: JSON.stringify({ x, y }),
    }),
  browserType: (text) =>
    request("/api/browser/input/type", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  browserPress: (key) =>
    request("/api/browser/input/press", {
      method: "POST",
      body: JSON.stringify({ key }),
    }),
  browserScroll: (payload) =>
    request("/api/browser/input/scroll", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
