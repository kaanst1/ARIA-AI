import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { atomDark } from "react-syntax-highlighter/dist/esm/styles/prism";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

let _msgId = 0;
const newId = () => ++_msgId;

// ── Markdown render bileşeni ──────────────────────────────────────────────────

function MarkdownContent({ content }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code({ node, inline, className, children, ...props }) {
          const match = /language-(\w+)/.exec(className || "");
          if (!inline && match) {
            return (
              <SyntaxHighlighter
                style={atomDark}
                language={match[1]}
                PreTag="div"
                customStyle={{
                  margin: "10px 0",
                  borderRadius: "8px",
                  fontSize: "13px",
                  border: "1px solid rgba(255,255,255,0.08)",
                }}
                {...props}
              >
                {String(children).replace(/\n$/, "")}
              </SyntaxHighlighter>
            );
          }
          return (
            <code className="inline-code" {...props}>
              {children}
            </code>
          );
        },
        pre({ children }) {
          return <div className="pre-wrapper">{children}</div>;
        },
        table({ children }) {
          return (
            <div className="table-wrapper">
              <table>{children}</table>
            </div>
          );
        },
        a({ href, children }) {
          return (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          );
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

// ── Tek mesaj bileşeni ────────────────────────────────────────────────────────

function MessageBubble({ message }) {
  const isUser = message.role === "user";
  const agentLabel = message.agent && message.agent !== "chat" ? message.agent : null;

  return (
    <div className={`message-row ${isUser ? "message-row--user" : "message-row--aria"}`}>
      {!isUser && (
        <div className="avatar" aria-label="ARIA">
          A
        </div>
      )}
      <div className={`bubble ${isUser ? "bubble--user" : "bubble--aria"}`}>
        <div className="bubble-header">
          <span className="bubble-sender">{isUser ? "Sen" : "ARIA"}</span>
          {agentLabel && (
            <span className="bubble-agent-tag">{agentLabel}</span>
          )}
        </div>
        <div className="bubble-content">
          {message.streaming && !message.content ? (
            <span className="typing-dots">
              <span /><span /><span />
            </span>
          ) : isUser ? (
            <span className="user-text">{message.content}</span>
          ) : (
            <MarkdownContent content={message.content} />
          )}
          {message.streaming && message.content && (
            <span className="stream-cursor">▌</span>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Hızlı komut butonları ─────────────────────────────────────────────────────

const QUICK_COMMANDS = [
  { label: "📋 Panoyu Analiz Et", action: "clipboard_analyze" },
  { label: "📊 Sistem Durumu", action: "system_status" },
  { label: "📅 Bugün Ne Var", action: "calendar_today" },
  { label: "🌅 Sabah Briefi", action: "morning_brief" },
];

function QuickCommands({ onCommand }) {
  return (
    <div className="quick-commands">
      {QUICK_COMMANDS.map((cmd) => (
        <button
          key={cmd.action}
          className="quick-cmd-btn"
          onClick={() => onCommand(cmd.action, cmd.label)}
          title={cmd.label}
        >
          {cmd.label}
        </button>
      ))}
    </div>
  );
}

// ── Sidebar bileşeni ──────────────────────────────────────────────────────────

function Sidebar({ sessions, activeSessionId, onNewSession, onSelectSession, sidebarOpen, onToggle, onQuickCommand }) {
  const grouped = groupSessionsByDate(sessions);

  return (
    <>
      {sidebarOpen && (
        <div className="sidebar-overlay" onClick={onToggle} />
      )}
      <aside className={`sidebar ${sidebarOpen ? "sidebar--open" : ""}`}>
        <div className="sidebar-header">
          <div className="brand">
            <span className="brand-name">ARIA</span>
            <span className="brand-badge">LOCAL AI</span>
          </div>
        </div>

        <button className="new-chat-btn" onClick={onNewSession}>
          <span className="new-chat-icon">＋</span>
          Yeni Sohbet
        </button>

        {/* Hızlı komutlar */}
        <QuickCommands onCommand={onQuickCommand} />

        <nav className="session-list">
          {grouped.length === 0 && (
            <div className="session-empty">Henüz sohbet yok</div>
          )}
          {grouped.map(({ label, items }) => (
            <div key={label} className="session-group">
              <div className="session-group-label">{label}</div>
              {items.map((session) => (
                <button
                  key={session.id}
                  className={`session-item ${session.id === activeSessionId ? "session-item--active" : ""}`}
                  onClick={() => onSelectSession(session.id)}
                  title={session.title}
                >
                  <span className="session-title">{session.title}</span>
                  {session.message_count > 0 && (
                    <span className="session-count">{session.message_count}</span>
                  )}
                </button>
              ))}
            </div>
          ))}
        </nav>
      </aside>
    </>
  );
}

// ── Status Bar bileşeni ───────────────────────────────────────────────────────

function StatusBar({ stats }) {
  if (!stats) return null;
  const cpu = stats?.system?.cpu_percent;
  const ram = stats?.system?.ram_percent;

  const cpuColor = cpu > 80 ? "#ff4444" : cpu > 60 ? "#ffaa00" : "#44ff88";
  const ramColor = ram > 80 ? "#ff4444" : ram > 60 ? "#ffaa00" : "#44ff88";

  return (
    <div className="status-bar">
      {cpu !== undefined && (
        <span className="status-item" style={{ color: cpuColor }}>
          CPU: {Math.round(cpu)}%
        </span>
      )}
      {ram !== undefined && (
        <span className="status-item" style={{ color: ramColor }}>
          RAM: {Math.round(ram)}%
        </span>
      )}
      <span className="status-item status-ollama" style={{ color: stats?.ollama_running ? "#44ff88" : "#ff4444" }}>
        {stats?.ollama_running ? "● Ollama" : "○ Ollama"}
      </span>
    </div>
  );
}

// ── Chat Panel bileşeni ───────────────────────────────────────────────────────

function ChatPanel({ messages, input, setInput, onSend, loading, onToggleSidebar, onFileDropped, stats, onMicClick, micRecording }) {
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);
  const [isDragOver, setIsDragOver] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  }, [input]);

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  // Drag & Drop handlers
  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragOver(true);
  };
  const handleDragLeave = () => setIsDragOver(false);
  const handleDrop = async (e) => {
    e.preventDefault();
    setIsDragOver(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      onFileDropped(files[0]);
    }
  };

  return (
    <main
      className={`chat-panel ${isDragOver ? "chat-panel--dragover" : ""}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Top bar */}
      <header className="chat-topbar">
        <button className="sidebar-toggle" onClick={onToggleSidebar} aria-label="Sidebar aç/kapat">
          ☰
        </button>
        <div className="chat-title">ARIA</div>
        <div className="topbar-right">
          <StatusBar stats={stats} />
          <div className="zero-cloud-badge">zero-cloud</div>
        </div>
      </header>

      {/* Drag overlay */}
      {isDragOver && (
        <div className="drag-overlay">
          <div className="drag-overlay-text">Dosyayı bırak — analiz edilecek</div>
        </div>
      )}

      {/* Mesajlar */}
      <section className="messages-area">
        {messages.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">◈</div>
            <div className="empty-title">Merhaba, Meriç.</div>
            <div className="empty-sub">Ne yapmamı istersin?</div>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <div ref={bottomRef} />
      </section>

      {/* Input alanı */}
      <section className="composer">
        <div className="composer-inner">
          <textarea
            ref={textareaRef}
            className="composer-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Bir şey sor... (veya dosya sürükle-bırak)"
            rows={1}
            disabled={loading}
          />
          <div className="composer-actions">
            <button
              className={`btn-mic ${micRecording ? "btn-mic--active" : ""}`}
              onClick={onMicClick}
              title={micRecording ? "Kaydediliyor... (durdurmak için tıkla)" : "Ses girişi"}
              aria-label="Mikrofon"
              type="button"
            >
              {micRecording ? "⏹" : "🎤"}
            </button>
            <button
              className="btn-send"
              onClick={onSend}
              disabled={loading || !input.trim()}
              aria-label="Gönder"
              type="button"
            >
              {loading ? (
                <span className="send-spinner" />
              ) : (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              )}
            </button>
          </div>
        </div>
        <div className="composer-hint">
          Enter: gönder &nbsp;·&nbsp; Shift+Enter: satır atla &nbsp;·&nbsp; Dosya sürükleyebilirsin
        </div>
      </section>
    </main>
  );
}

// ── Ana uygulama ──────────────────────────────────────────────────────────────

export default function App() {
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [systemStats, setSystemStats] = useState(null);
  const [micRecording, setMicRecording] = useState(false);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  // ── Oturumları yükle ────────────────────────────────────────────────────────
  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/sessions`);
      if (!res.ok) return;
      const data = await res.json();
      setSessions(Array.isArray(data) ? data : []);
    } catch {
      // API henüz hazır değil — sessizce geç
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  // ── Sistem istatistikleri — 5 saniyede bir çek ──────────────────────────────
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch(`${API_URL}/status`);
        if (res.ok) {
          const data = await res.json();
          setSystemStats(data);
        }
      } catch {
        // sessizce geç
      }
    };
    fetchStats();
    const interval = setInterval(fetchStats, 5000);
    return () => clearInterval(interval);
  }, []);

  // ── Yeni sohbet ─────────────────────────────────────────────────────────────
  const handleNewSession = async () => {
    try {
      const res = await fetch(`${API_URL}/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "Yeni Sohbet" }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const session = await res.json();
      setSessions((prev) => [{ ...session, message_count: 0 }, ...prev]);
      setActiveSessionId(session.id);
      setMessages([]);
    } catch (err) {
      console.error("Oturum oluşturulamadı:", err);
      const localId = -Date.now();
      setActiveSessionId(localId);
      setMessages([]);
    }
  };

  // ── Oturum seç ──────────────────────────────────────────────────────────────
  const handleSelectSession = async (sessionId) => {
    setActiveSessionId(sessionId);
    try {
      const res = await fetch(`${API_URL}/sessions/${sessionId}`);
      if (!res.ok) return;
      const data = await res.json();
      const msgs = (data.messages || []).map((m) => ({
        id: newId(),
        role: m.role === "assistant" ? "aria" : m.role,
        content: m.content,
        agent: m.agent || "chat",
      }));
      setMessages(msgs);
    } catch {
      setMessages([]);
    }
  };

  // ── Hızlı komutlar ───────────────────────────────────────────────────────────
  const handleQuickCommand = async (action, label) => {
    const ariaId = newId();

    // Kullanıcı mesajı göster
    setMessages((prev) => [
      ...prev,
      { id: newId(), role: "user", content: label, agent: "chat" },
      { id: ariaId, role: "aria", content: "", agent: "chat", streaming: true },
    ]);
    setLoading(true);

    try {
      let result = "";
      switch (action) {
        case "clipboard_analyze": {
          const res = await fetch(`${API_URL}/clipboard/analyze`, { method: "POST" });
          const data = await res.json();
          result = data.analysis || "Pano boş veya okunamadı.";
          break;
        }
        case "system_status": {
          const res = await fetch(`${API_URL}/system/stats`);
          const data = await res.json();
          const cpu = data?.cpu?.percent ?? "?";
          const ram = data?.memory?.percent ?? "?";
          const disk = data?.disk?.percent ?? "?";
          result = `**Sistem Durumu**\n- CPU: %${cpu}\n- RAM: %${ram}\n- Disk: %${disk}`;
          break;
        }
        case "calendar_today": {
          const res = await fetch(`${API_URL}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: "Bugünkü takvim etkinliklerimi göster", agent: "chat" }),
          });
          const data = await res.json();
          result = data.response || "Takvim bilgisi alınamadı.";
          break;
        }
        case "morning_brief": {
          const res = await fetch(`${API_URL}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: "sabah briefi", agent: "brief" }),
          });
          const data = await res.json();
          result = data.response || "Brief alınamadı.";
          break;
        }
        default:
          result = "Bilinmeyen komut.";
      }

      setMessages((prev) =>
        prev.map((m) =>
          m.id === ariaId ? { ...m, content: result, streaming: false } : m
        )
      );
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === ariaId
            ? { ...m, content: `Hata: ${err.message}`, streaming: false }
            : m
        )
      );
    } finally {
      setLoading(false);
    }
  };

  // ── Mikrofon (ses kaydı) ─────────────────────────────────────────────────────
  const handleMicClick = async () => {
    if (micRecording) {
      // Kaydı durdur
      if (mediaRecorderRef.current) {
        mediaRecorderRef.current.stop();
      }
      setMicRecording(false);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // WKWebView (macOS/Tauri) WebM desteklemez — mp4 veya ogg kullan
      const mimeType = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/mp4",
        "audio/ogg;codecs=opus",
        "audio/ogg",
      ].find((t) => MediaRecorder.isTypeSupported(t)) || "";
      const ext = mimeType.includes("mp4") ? "mp4" : mimeType.includes("ogg") ? "ogg" : "webm";

      const mediaRecorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(audioChunksRef.current, { type: mimeType || "audio/webm" });
        const formData = new FormData();
        formData.append("file", blob, `recording.${ext}`);

        try {
          const res = await fetch(`${API_URL}/speech/transcribe`, {
            method: "POST",
            body: formData,
          });
          if (res.ok) {
            const data = await res.json();
            if (data.transcript) {
              setInput((prev) => prev + (prev ? " " : "") + data.transcript);
            }
          } else {
            // faster-whisper yoksa bilgi ver
            setInput((prev) => prev + " [Ses transkripti: faster-whisper kurulu değil]");
          }
        } catch {
          // sessizce geç
        }
      };

      mediaRecorder.start();
      setMicRecording(true);
    } catch {
      alert("Mikrofon erişimi reddedildi veya kullanılamıyor.");
    }
  };

  // ── Dosya drag & drop ────────────────────────────────────────────────────────
  const handleFileDropped = async (file) => {
    const ariaId = newId();
    setMessages((prev) => [
      ...prev,
      { id: newId(), role: "user", content: `📎 Dosya: ${file.name}`, agent: "chat" },
      { id: ariaId, role: "aria", content: "", agent: "analyst", streaming: true },
    ]);
    setLoading(true);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`${API_URL}/file/analyze`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const result = data.analysis || "Dosya analiz edilemedi.";

      setMessages((prev) =>
        prev.map((m) =>
          m.id === ariaId ? { ...m, content: result, streaming: false } : m
        )
      );
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === ariaId
            ? { ...m, content: `Dosya analiz hatası: ${err.message}`, streaming: false }
            : m
        )
      );
    } finally {
      setLoading(false);
    }
  };

  // ── Mesaj gönder ─────────────────────────────────────────────────────────────
  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    const text = input.trim();
    const ariaId = newId();

    setMessages((prev) => [
      ...prev,
      { id: newId(), role: "user", content: text, agent: "chat" },
    ]);
    setInput("");
    setLoading(true);

    setMessages((prev) => [
      ...prev,
      { id: ariaId, role: "aria", content: "", agent: "chat", streaming: true },
    ]);

    let sessionId = activeSessionId;
    if (!sessionId || sessionId < 0) {
      try {
        const res = await fetch(`${API_URL}/sessions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: text.slice(0, 60) }),
        });
        if (res.ok) {
          const session = await res.json();
          sessionId = session.id;
          setActiveSessionId(sessionId);
          setSessions((prev) => [{ ...session, message_count: 0 }, ...prev]);
        }
      } catch {
        // offline mod
      }
    }

    try {
      const res = await fetch(`${API_URL}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          agent: "chat",
          session_id: sessionId || undefined,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const agentName = res.headers.get("X-ARIA-Agent") || "chat";
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const token = line.slice(6);

          if (token.startsWith("[error]")) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === ariaId
                  ? { ...m, content: `⚠️ ${token.slice(8)}`, streaming: false }
                  : m
              )
            );
            return;
          }

          setMessages((prev) =>
            prev.map((m) =>
              m.id === ariaId
                ? { ...m, content: m.content + token, agent: agentName }
                : m
            )
          );
        }
      }

      fetchSessions();
    } catch {
      setMessages((prev) => {
        const target = prev.find((m) => m.id === ariaId);
        if (target) {
          return prev.map((m) =>
            m.id === ariaId
              ? {
                  ...m,
                  content: "⚠️ Backend bağlantısı yok. API ayakta mı? (`aria serve`)",
                  streaming: false,
                }
              : m
          );
        }
        return [
          ...prev,
          {
            id: newId(),
            role: "aria",
            content: "⚠️ Backend bağlantısı yok. API ayakta mı? (`aria serve`)",
            agent: "chat",
          },
        ];
      });
    } finally {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === ariaId && m.streaming ? { ...m, streaming: false } : m
        )
      );
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onNewSession={handleNewSession}
        onSelectSession={handleSelectSession}
        sidebarOpen={sidebarOpen}
        onToggle={() => setSidebarOpen((v) => !v)}
        onQuickCommand={handleQuickCommand}
      />
      <ChatPanel
        messages={messages}
        input={input}
        setInput={setInput}
        onSend={sendMessage}
        loading={loading}
        onToggleSidebar={() => setSidebarOpen((v) => !v)}
        onFileDropped={handleFileDropped}
        stats={systemStats}
        onMicClick={handleMicClick}
        micRecording={micRecording}
      />
    </div>
  );
}

// ── Yardımcı: oturumları tarihe göre grupla ───────────────────────────────────

function groupSessionsByDate(sessions) {
  if (!sessions.length) return [];

  const now = new Date();
  const todayStr = dateStr(now);
  const yesterdayStr = dateStr(new Date(now - 86_400_000));
  const weekAgo = new Date(now - 7 * 86_400_000);

  const groups = {};

  for (const s of sessions) {
    const d = new Date(s.updated_at + "Z");
    const ds = dateStr(d);

    let label;
    if (ds === todayStr) label = "Bugün";
    else if (ds === yesterdayStr) label = "Dün";
    else if (d >= weekAgo) label = "Bu Hafta";
    else label = d.toLocaleDateString("tr-TR", { month: "long", year: "numeric" });

    if (!groups[label]) groups[label] = [];
    groups[label].push(s);
  }

  const order = ["Bugün", "Dün", "Bu Hafta"];
  const keys = [
    ...order.filter((k) => groups[k]),
    ...Object.keys(groups).filter((k) => !order.includes(k)),
  ];

  return keys.map((label) => ({ label, items: groups[label] }));
}

function dateStr(date) {
  return date.toISOString().slice(0, 10);
}
