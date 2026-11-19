import { useEffect, useRef, useState } from "react";
import { api } from "../api";

const DEFAULT_VIEWPORT = { width: 1280, height: 800 };

function mapPointerToViewport(event, img, viewport) {
  if (!img || !viewport?.width || !viewport?.height) return null;
  const rect = img.getBoundingClientRect();
  const scale = Math.min(rect.width / viewport.width, rect.height / viewport.height);
  if (!scale) return null;
  const dispW = viewport.width * scale;
  const dispH = viewport.height * scale;
  const offsetX = (rect.width - dispW) / 2;
  const offsetY = (rect.height - dispH) / 2;
  const x = (event.clientX - rect.left - offsetX) / scale;
  const y = (event.clientY - rect.top - offsetY) / scale;
  if (x < 0 || y < 0 || x >= viewport.width || y >= viewport.height) return null;
  return { x: Math.round(x), y: Math.round(y) };
}

function playwrightKey(event) {
  const special = {
    Enter: "Enter",
    Backspace: "Backspace",
    Delete: "Delete",
    Tab: "Tab",
    Escape: "Escape",
    ArrowLeft: "ArrowLeft",
    ArrowRight: "ArrowRight",
    ArrowUp: "ArrowUp",
    ArrowDown: "ArrowDown",
    Home: "Home",
    End: "End",
    PageUp: "PageUp",
    PageDown: "PageDown",
  };
  const base = special[event.key] || (event.key.length === 1 ? event.key : null);
  if (!base) return null;
  if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
    return { type: "type", value: event.key };
  }
  const parts = [];
  if (event.ctrlKey) parts.push("Control");
  if (event.metaKey) parts.push("Meta");
  if (event.altKey) parts.push("Alt");
  if (event.shiftKey && event.key.length !== 1) parts.push("Shift");
  if (event.key.length === 1) {
    parts.push(event.key);
  } else {
    parts.push(base);
  }
  return { type: "press", value: parts.join("+") };
}

export default function ChatPage() {
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [agentWorking, setAgentWorking] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [frame, setFrame] = useState({
    image: null,
    url: "about:blank",
    title: "",
    width: DEFAULT_VIEWPORT.width,
    height: DEFAULT_VIEWPORT.height,
  });
  const [urlDraft, setUrlDraft] = useState("about:blank");
  const [browserFocused, setBrowserFocused] = useState(false);
  const [error, setError] = useState("");
  const [showConvs, setShowConvs] = useState(false);
  const frameImgRef = useRef(null);
  const browserSurfaceRef = useRef(null);
  const urlInputRef = useRef(null);
  const scrollBusy = useRef(false);
  const urlSynced = useRef("");
  const activeTaskIdRef = useRef(null);

  function isActiveAgentStatus(status) {
    return status === "pending" || status === "running";
  }

  async function syncAgentWorking(conversationId) {
    if (!conversationId) {
      activeTaskIdRef.current = null;
      setAgentWorking(false);
      return;
    }
    try {
      if (activeTaskIdRef.current) {
        const task = await api.getTask(activeTaskIdRef.current);
        if (task.conversation_id === conversationId && isActiveAgentStatus(task.status)) {
          setAgentWorking(true);
          return;
        }
        activeTaskIdRef.current = null;
      }
      const tasks = await api.tasks();
      const active = (tasks || []).find(
        (t) => t.conversation_id === conversationId && isActiveAgentStatus(t.status),
      );
      if (active) {
        activeTaskIdRef.current = active.id;
        setAgentWorking(true);
      } else {
        setAgentWorking(false);
      }
    } catch {
      /* ignore polling errors */
    }
  }

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
          const nextUrl = data.url || "";
          setFrame({
            image: data.image,
            url: nextUrl,
            title: data.title || "",
            width: data.width || DEFAULT_VIEWPORT.width,
            height: data.height || DEFAULT_VIEWPORT.height,
          });
          if (
            nextUrl &&
            nextUrl !== urlSynced.current &&
            document.activeElement !== urlInputRef.current
          ) {
            urlSynced.current = nextUrl;
            setUrlDraft(nextUrl);
          }
        }
      } catch {
        /* ignore */
      }
    };
    return () => ws.close();
  }, []);

  useEffect(() => {
    if (!activeId) {
      activeTaskIdRef.current = null;
      setAgentWorking(false);
      return undefined;
    }
    syncAgentWorking(activeId);
    const timer = setInterval(async () => {
      try {
        const detail = await api.getConversation(activeId);
        setMessages(detail.messages || []);
        await syncAgentWorking(activeId);
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
    if (!content || busy || agentWorking) return;
    setBusy(true);
    setError("");
    try {
      const id = await ensureConversation();
      setText("");
      const result = await api.sendMessage(id, content);
      if (result?.task?.id) {
        activeTaskIdRef.current = result.task.id;
      }
      setAgentWorking(true);
      const detail = await api.getConversation(id);
      setMessages(detail.messages || []);
      const list = await api.conversations();
      setConversations(list);
    } catch (err) {
      setError(err.message);
      setAgentWorking(false);
      activeTaskIdRef.current = null;
    } finally {
      setBusy(false);
    }
  }

  async function cancelAgent() {
    const taskId = activeTaskIdRef.current;
    if (!taskId || cancelling) return;
    setCancelling(true);
    setError("");
    try {
      await api.cancelTask(taskId);
      activeTaskIdRef.current = null;
      setAgentWorking(false);
      if (activeId) {
        const detail = await api.getConversation(activeId);
        setMessages(detail.messages || []);
      }
    } catch (err) {
      setError(err.message);
      if (activeId) {
        await syncAgentWorking(activeId);
      }
    } finally {
      setCancelling(false);
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
    activeTaskIdRef.current = null;
    const detail = await api.getConversation(id);
    setMessages(detail.messages || []);
    await syncAgentWorking(id);
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

  async function goUrl(event) {
    event?.preventDefault?.();
    const raw = (urlDraft || "").trim();
    if (!raw) return;
    setError("");
    try {
      const result = await api.browserNavigate(raw);
      const next = result?.url || raw;
      urlSynced.current = next;
      setUrlDraft(next);
    } catch (err) {
      setError(err.message);
    }
  }

  async function resetBrowser() {
    setError("");
    try {
      await api.browserReset();
      urlSynced.current = "about:blank";
      setUrlDraft("about:blank");
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleBrowserClick(event) {
    if (event.detail > 1) return;
    const point = mapPointerToViewport(event, frameImgRef.current, frame);
    if (!point) return;
    browserSurfaceRef.current?.focus();
    try {
      await api.browserClick(point.x, point.y, "left");
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleBrowserContextMenu(event) {
    event.preventDefault();
    const point = mapPointerToViewport(event, frameImgRef.current, frame);
    if (!point) return;
    browserSurfaceRef.current?.focus();
    try {
      await api.browserClick(point.x, point.y, "right");
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleBrowserDblClick(event) {
    const point = mapPointerToViewport(event, frameImgRef.current, frame);
    if (!point) return;
    try {
      await api.browserDblClick(point.x, point.y);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleBrowserWheel(event) {
    event.preventDefault();
    if (scrollBusy.current) return;
    const point = mapPointerToViewport(event, frameImgRef.current, frame);
    scrollBusy.current = true;
    try {
      await api.browserScroll({
        x: point?.x,
        y: point?.y,
        delta_x: event.deltaX,
        delta_y: event.deltaY,
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setTimeout(() => {
        scrollBusy.current = false;
      }, 60);
    }
  }

  async function handleBrowserKeyDown(event) {
    if (event.target.closest?.("input, textarea, button")) return;
    const mapped = playwrightKey(event);
    if (!mapped) return;
    event.preventDefault();
    try {
      if (mapped.type === "type") {
        await api.browserType(mapped.value);
      } else {
        await api.browserPress(mapped.value);
      }
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
              {messages.length === 0 && !agentWorking && (
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
              {agentWorking && (
                <div
                  className="bubble agent-loading"
                  role="status"
                  aria-live="polite"
                  aria-label="ایجنت در حال کار است"
                >
                  <span className="agent-loading-dots" aria-hidden="true">
                    <span />
                    <span />
                    <span />
                  </span>
                  <span className="agent-loading-label">در حال انجام…</span>
                  <button
                    className="btn ghost danger agent-cancel-btn"
                    type="button"
                    onClick={cancelAgent}
                    disabled={cancelling}
                    aria-label="لغو کار ایجنت"
                    title="لغو"
                  >
                    {cancelling ? "در حال لغو…" : "لغو"}
                  </button>
                </div>
              )}
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
              <button
                className="btn composer-send"
                type="button"
                disabled={busy || agentWorking}
                onClick={send}
                aria-label="ارسال"
                title="ارسال"
              >
                {busy || agentWorking ? (
                  <svg className="composer-send-icon is-busy" viewBox="0 0 24 24" aria-hidden="true">
                    <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" opacity="0.25" />
                    <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                ) : (
                  <svg className="composer-send-icon" viewBox="0 0 24 24" aria-hidden="true">
                    <path
                      fill="currentColor"
                      d="M3.4 20.6 21 12 3.4 3.4l.1 6.8L14 12l-10.5 1.8z"
                    />
                  </svg>
                )}
              </button>
            </div>
          </div>
        </div>
      </section>

      <section className="browser-panel">
        <div className="panel-header">
          <div>
            <strong>مرورگر</strong>
            <div className="muted" style={{ fontSize: "0.78rem" }}>
              {browserFocused ? "فعال — کلیک، تایپ و اسکرول کنید" : "برای کار، روی تصویر کلیک کنید"}
            </div>
          </div>
          <button className="btn ghost" type="button" onClick={resetBrowser}>
            ریست
          </button>
        </div>
        <form className="browser-toolbar" onSubmit={goUrl}>
          <input
            ref={urlInputRef}
            className="browser-url-input"
            value={urlDraft}
            onChange={(e) => setUrlDraft(e.target.value)}
            placeholder="https://…"
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
            dir="ltr"
          />
          <button className="btn soft" type="submit">
            برو
          </button>
        </form>
        <div
          className={`browser-frame interactive ${browserFocused ? "focused" : ""}`}
          ref={browserSurfaceRef}
          tabIndex={0}
          role="application"
          aria-label="مرورگر تعاملی"
          onFocus={() => setBrowserFocused(true)}
          onBlur={() => setBrowserFocused(false)}
          onKeyDown={handleBrowserKeyDown}
          onContextMenu={handleBrowserContextMenu}
        >
          {frame.image ? (
            <img
              ref={frameImgRef}
              src={frame.image}
              alt="live browser"
              draggable={false}
              onClick={handleBrowserClick}
              onDoubleClick={handleBrowserDblClick}
              onWheel={handleBrowserWheel}
            />
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
