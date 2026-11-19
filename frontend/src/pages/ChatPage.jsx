import { useEffect, useState } from "react";
import { api } from "../api";

export default function ChatPage() {
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [frame, setFrame] = useState({ image: null, url: "about:blank", title: "" });
  const [error, setError] = useState("");
  const [showConvs, setShowConvs] = useState(false);

  async function loadConversations(selectId) {
    const list = await api.conversations();
    setConversations(list);
    const id = selectId || list[0]?.id;
    if (id) {
      setActiveId(id);
      const detail = await api.getConversation(id);
      setMessages(detail.messages || []);
    } else {
      setActiveId(null);
      setMessages([]);
    }
  }

  useEffect(() => {
    loadConversations().catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/browser`);
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "frame") {
          setFrame({ image: data.image, url: data.url || "", title: data.title || "" });
        }
      } catch {
        /* ignore */
      }
    };
    return () => ws.close();
  }, []);

  useEffect(() => {
    if (!activeId) return undefined;
    const timer = setInterval(async () => {
      try {
        const detail = await api.getConversation(activeId);
        setMessages(detail.messages || []);
      } catch {
        /* ignore polling errors */
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [activeId]);

  async function ensureConversation() {
    if (activeId) return activeId;
    const conv = await api.createConversation();
    await loadConversations(conv.id);
    return conv.id;
  }

  async function send() {
    const content = text.trim();
    if (!content) return;
    setBusy(true);
    setError("");
    try {
      const id = await ensureConversation();
      setText("");
      await api.sendMessage(id, content);
      const detail = await api.getConversation(id);
      setMessages(detail.messages || []);
      const list = await api.conversations();
      setConversations(list);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function newChat() {
    const conv = await api.createConversation();
    await loadConversations(conv.id);
    setShowConvs(false);
  }

  async function selectConversation(id) {
    setActiveId(id);
    setShowConvs(false);
    const detail = await api.getConversation(id);
    setMessages(detail.messages || []);
  }

  async function deleteChat(id) {
    if (!id) return;
    const ok = window.confirm("این گفتگو پاک شود؟");
    if (!ok) return;
    setError("");
    try {
      await api.deleteConversation(id);
      const nextId = activeId === id ? null : activeId;
      await loadConversations(nextId);
      setShowConvs(false);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="chat-layout">
      <section className="chat-panel">
        <div className="panel-header">
          <div>
            <strong>ایجنت Onedo</strong>
            <div className="muted" style={{ fontSize: "0.82rem" }}>
              پیام به AI می‌رود؛ خودش وقتی لازم باشد مرورگر را کنترل می‌کند.
            </div>
          </div>
          <div className="panel-header-actions">
            <button className="btn ghost conv-toggle" type="button" onClick={() => setShowConvs((v) => !v)}>
              {showConvs ? "بستن" : "گفتگوها"}
            </button>
            {activeId && (
              <button className="btn ghost danger" type="button" onClick={() => deleteChat(activeId)}>
                پاک کردن
              </button>
            )}
            <button className="btn soft" type="button" onClick={newChat}>
              جدید
            </button>
          </div>
        </div>

        <div className={`chat-body ${showConvs ? "convs-open" : ""}`}>
          <div className="conv-list">
            {conversations.length === 0 && (
              <div className="empty" style={{ padding: 12, fontSize: "0.85rem" }}>
                هنوز گفتگویی نیست
              </div>
            )}
            {conversations.map((c) => (
              <div key={c.id} className={`conv-row ${activeId === c.id ? "active" : ""}`}>
                <button
                  type="button"
                  className="conv-item"
                  onClick={() => selectConversation(c.id)}
                >
                  {c.title}
                </button>
                <button
                  type="button"
                  className="conv-delete"
                  title="پاک کردن"
                  aria-label="پاک کردن گفتگو"
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteChat(c.id);
                  }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>

          <div className="chat-main">
            <div className="messages">
              {messages.length === 0 && (
                <div className="empty">
                  مثلاً بگو: «برو دیجی‌کالا و یک هدفون بی‌سیم خوب پیدا کن»
                  <br />
                  ایجنت تصمیم می‌گیرد چه صفحه‌ای باز کند و چه کلیک/تایپی بزند.
                </div>
              )}
              {messages.map((m) => (
                <div key={m.id} className={`bubble ${m.role}`}>
                  {m.content}
                </div>
              ))}
            </div>
            {error && <div className="error-box" style={{ margin: "0 12px" }}>{error}</div>}
            <div className="composer">
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="به ایجنت بگو چه کاری انجام دهد…"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
              />
              <button className="btn composer-send" type="button" disabled={busy} onClick={send}>
                {busy ? "…" : "ارسال"}
              </button>
            </div>
          </div>
        </div>
      </section>

      <section className="browser-panel">
        <div className="panel-header">
          <div>
            <strong>مرورگر</strong>
          </div>
          <button className="btn ghost" type="button" onClick={() => api.browserReset()}>
            ریست
          </button>
        </div>
        <div className="browser-frame">
          {frame.url && <div className="browser-url">{frame.title || frame.url}</div>}
          {frame.image ? (
            <img src={frame.image} alt="live browser" />
          ) : (
            <div className="empty" style={{ color: "#aeaeb2" }}>
              در انتظار تصویر زنده…
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
