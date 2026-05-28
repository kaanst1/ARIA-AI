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
                  margin: "8px 0",
                  borderRadius: "4px",
                  fontSize: "12px",
                  border: "1px solid rgba(0, 212, 255, 0.15)",
                  background: "#050810",
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

// ── Dijital saat ──────────────────────────────────────────────────────────────

function DigitalClock() {
  const [time, setTime] = useState(() => {
    const now = new Date();
    return now.toLocaleTimeString("tr-TR", { hour12: false });
  });

  useEffect(() => {
    const interval = setInterval(() => {
      const now = new Date();
      setTime(now.toLocaleTimeString("tr-TR", { hour12: false }));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  return <span className="topbar-clock">{time}</span>;
}

// ── Hızlı komut butonları ─────────────────────────────────────────────────────

const QUICK_COMMANDS = [
  { label: "Sabah Briefi", action: "morning_brief" },
  { label: "Sistem Durumu", action: "system_status" },
  { label: "Bugün Ne Var", action: "calendar_today" },
  { label: "Panoyu Analiz Et", action: "clipboard_analyze" },
  { label: "Hava Durumu", action: "weather" },
  { label: "Smart Inbox", action: "smart_inbox" },
];

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

// ── Ana uygulama ──────────────────────────────────────────────────────────────

export default function App() {
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [systemStats, setSystemStats] = useState(null);
  const [micRecording, setMicRecording] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(() => {
    return localStorage.getItem("aria-voice") !== "false";
  });
  const [isDragOver, setIsDragOver] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [view, setView] = useState("chat"); // "chat" | "dashboard"
  const [analytics, setAnalytics] = useState(null);
  const [pinnedMessages, setPinnedMessages] = useState(() => {
    try { return JSON.parse(localStorage.getItem("aria-pins") || "[]"); } catch { return []; }
  });
  const [artifacts, setArtifacts] = useState([]); // {id, type, content, ts}
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  // Ses toggle — localStorage'a kaydet
  const toggleVoice = useCallback(() => {
    setVoiceEnabled((prev) => {
      const next = !prev;
      localStorage.setItem("aria-voice", String(next));
      if (!next) fetch(`${API_URL}/speak/stop`, { method: "POST" }).catch(() => {});
      return next;
    });
  }, []);

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Textarea auto-resize
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 120) + "px";
  }, [input]);

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

  // ── Analitik verisi çek (dashboard için) ────────────────────────────────────
  useEffect(() => {
    if (view !== "dashboard") return;
    const fetchAnalytics = async () => {
      try {
        const res = await fetch(`${API_URL}/analytics/usage`);
        if (res.ok) setAnalytics(await res.json());
      } catch { /* sessizce geç */ }
    };
    fetchAnalytics();
  }, [view]);

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
        case "weather": {
          const res = await fetch(`${API_URL}/weather`);
          const data = await res.json();
          if (data.success) {
            result = `**${data.city} Hava Durumu**\n- Sıcaklık: ${data.temp_c}°C (hissedilen ${data.feels_like_c}°C)\n- Durum: ${data.desc}\n- Nem: %${data.humidity} | Rüzgar: ${data.wind_kmh} km/s`;
          } else {
            result = "Hava durumu alınamadı.";
          }
          break;
        }
        case "smart_inbox": {
          const res = await fetch(`${API_URL}/email/smart-inbox?count=10`);
          const data = await res.json();
          if (data.success) {
            let txt = data.summary;
            if (data.urgent?.length) txt += `\n\n**⚠️ Acil (${data.urgent.length}):** ${data.urgent.map(e => e.subject).join(", ")}`;
            if (data.meetings?.length) txt += `\n\n**📅 Toplantı İçeren (${data.meetings.length}):** ${data.meetings.map(e => e.subject).join(", ")}`;
            result = txt;
          } else {
            result = "Inbox alınamadı.";
          }
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

  // ── Mikrofon ─────────────────────────────────────────────────────────────────
  const handleMicClick = async () => {
    if (micRecording) {
      setMicRecording(false);
      try {
        const res = await fetch(`${API_URL}/speech/record/stop`, { method: "POST" });
        if (res.ok) {
          const data = await res.json();
          if (data.transcript) {
            setInput((prev) => prev + (prev ? " " : "") + data.transcript);
          }
        }
      } catch {
        // sessizce geç
      }
      return;
    }

    try {
      const res = await fetch(`${API_URL}/speech/record/start`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          setMicRecording(true);
        } else {
          alert(`Mikrofon başlatılamadı: ${data.error}`);
        }
      }
    } catch {
      alert("API'ye ulaşılamıyor, mikrofon çalışmıyor.");
    }
  };

  // ── Dosya drag & drop ────────────────────────────────────────────────────────
  const handleFileDropped = async (file) => {
    const ariaId = newId();
    setMessages((prev) => [
      ...prev,
      { id: newId(), role: "user", content: `[FILE] ${file.name}`, agent: "chat" },
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

  // ── Drag & Drop handlers ──────────────────────────────────────────────────────
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
      handleFileDropped(files[0]);
    }
  };

  // ── Pin / Artifact yönetimi ───────────────────────────────────────────────────
  const togglePin = (msg) => {
    setPinnedMessages((prev) => {
      const exists = prev.some((p) => p.id === msg.id);
      const next = exists ? prev.filter((p) => p.id !== msg.id) : [...prev, msg];
      localStorage.setItem("aria-pins", JSON.stringify(next));
      return next;
    });
  };

  const isPinned = (msgId) => pinnedMessages.some((p) => p.id === msgId);

  const extractArtifacts = (content, msgId) => {
    const codeBlocks = [...content.matchAll(/```(\w+)?\n([\s\S]*?)```/g)];
    const links = [...content.matchAll(/https?:\/\/[^\s)]+/g)];
    const newArts = [];
    codeBlocks.forEach((m, i) => {
      newArts.push({ id: `${msgId}-code-${i}`, type: "code", lang: m[1] || "text", content: m[2].trim(), ts: Date.now() });
    });
    links.forEach((m, i) => {
      newArts.push({ id: `${msgId}-link-${i}`, type: "link", content: m[0], ts: Date.now() });
    });
    if (newArts.length > 0) {
      setArtifacts((prev) => [...prev.slice(-19), ...newArts]);
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
                  ? { ...m, content: `[ERR] ${token.slice(8)}`, streaming: false }
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

      // Stream bitti — cevabı seslendir
      if (voiceEnabled) {
        setMessages((prev) => {
          const ariaMsg = prev.find((m) => m.id === ariaId);
          if (ariaMsg?.content) {
            fetch(`${API_URL}/speak`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ text: ariaMsg.content }),
            }).catch(() => {});
          }
          return prev;
        });
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
                  content: "[ERR] Backend bağlantısı yok. API ayakta mı? (`aria serve`)",
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
            content: "[ERR] Backend bağlantısı yok. API ayakta mı? (`aria serve`)",
            agent: "chat",
          },
        ];
      });
    } finally {
      setMessages((prev) => {
        const updated = prev.map((m) =>
          m.id === ariaId && m.streaming ? { ...m, streaming: false } : m
        );
        const finalMsg = updated.find((m) => m.id === ariaId);
        if (finalMsg?.content) extractArtifacts(finalMsg.content, ariaId);
        return updated;
      });
      setLoading(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // ── Hesaplanan değerler ───────────────────────────────────────────────────────
  const cpu = systemStats?.system?.cpu_percent;
  const ram = systemStats?.system?.ram_percent;
  const disk = systemStats?.system?.disk_percent;
  const ollamaOnline = systemStats?.ollama_running ?? false;
  const modelName = systemStats?.model || "qwen2.5:7b";
  const activeSession = sessions.find((s) => s.id === activeSessionId);
  const activeAgent = messages.length > 0
    ? messages.filter((m) => m.role === "aria").slice(-1)[0]?.agent || "chat"
    : "chat";

  const filteredSessions = searchQuery.trim()
    ? sessions.filter((s) => s.title?.toLowerCase().includes(searchQuery.toLowerCase()))
    : sessions;
  const groupedSessions = groupSessionsByDate(filteredSessions);

  // ── Timestamp yardımcısı ──────────────────────────────────────────────────────
  const fmtTime = (msg) => {
    if (!msg.timestamp) return new Date().toLocaleTimeString("tr-TR", { hour12: false });
    return new Date(msg.timestamp).toLocaleTimeString("tr-TR", { hour12: false });
  };

  return (
    <div
      className={`hud-root${isDragOver ? " hud-root--dragover" : ""}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* ═══ TOP BAR ═══════════════════════════════════════════════════════════ */}
      <header className="topbar">
        <div className="topbar-left">
          <span className="topbar-logo">◈ ARIA</span>
        </div>
        <div className="topbar-center">
          <span className="topbar-model">⬡ {modelName}</span>
          {cpu !== undefined && (
            <span className={`topbar-stat${cpu > 80 ? " topbar-stat--warn" : ""}`}>
              CPU: {Math.round(cpu)}%
            </span>
          )}
          {ram !== undefined && (
            <span className={`topbar-stat${ram > 80 ? " topbar-stat--warn" : ""}`}>
              RAM: {Math.round(ram)}%
            </span>
          )}
          <span className={`topbar-ollama${ollamaOnline ? " topbar-ollama--on" : " topbar-ollama--off"}`}>
            {ollamaOnline ? "● OLLAMA" : "○ OLLAMA"}
          </span>
        </div>
        <div className="topbar-right">
          <DigitalClock />
        </div>
      </header>

      {/* ═══ MAIN GRID ══════════════════════════════════════════════════════════ */}
      <div className="hud-grid">

        {/* ─── LEFT PANEL ────────────────────────────────────────────────────── */}
        <aside className="panel panel-left">

          {/* SYSTEM STATUS */}
          <div className="panel-section">
            <div className="panel-header">
              <span className="panel-dot" />
              SYSTEM STATUS
            </div>

            <div className="stat-row">
              <span className="stat-label">CPU</span>
              <div className="stat-bar-wrap">
                <div
                  className={`stat-bar-fill${cpu > 80 ? " stat-bar-fill--warn" : ""}`}
                  style={{ width: `${Math.min(cpu || 0, 100)}%` }}
                />
              </div>
              <span className="stat-val">{cpu !== undefined ? `${Math.round(cpu)}%` : "--"}</span>
            </div>

            <div className="stat-row">
              <span className="stat-label">RAM</span>
              <div className="stat-bar-wrap">
                <div
                  className={`stat-bar-fill${ram > 80 ? " stat-bar-fill--warn" : ""}`}
                  style={{ width: `${Math.min(ram || 0, 100)}%` }}
                />
              </div>
              <span className="stat-val">{ram !== undefined ? `${Math.round(ram)}%` : "--"}</span>
            </div>

            <div className="stat-row">
              <span className="stat-label">DSK</span>
              <div className="stat-bar-wrap">
                <div
                  className={`stat-bar-fill${disk > 80 ? " stat-bar-fill--warn" : ""}`}
                  style={{ width: `${Math.min(disk || 0, 100)}%` }}
                />
              </div>
              <span className="stat-val">{disk !== undefined ? `${Math.round(disk)}%` : "--"}</span>
            </div>
          </div>

          {/* SESSION LOG */}
          <div className="panel-section panel-section--grow">
            <div className="panel-header">
              SESSION LOG
            </div>

            <button className="new-session-btn" onClick={handleNewSession}>
              + NEW SESSION
            </button>

            <input
              className="session-search"
              type="text"
              placeholder="Sohbet ara..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />

            <nav className="session-list">
              {groupedSessions.length === 0 && (
                <div className="session-empty">NO SESSIONS</div>
              )}
              {groupedSessions.map(({ label, items }) => (
                <div key={label} className="session-group">
                  <div className="session-group-label">{label.toUpperCase()}</div>
                  {items.map((session) => (
                    <button
                      key={session.id}
                      className={`session-item${session.id === activeSessionId ? " session-item--active" : ""}`}
                      onClick={() => handleSelectSession(session.id)}
                      title={session.title}
                    >
                      <span className="session-indicator">
                        {session.id === activeSessionId ? "▶" : "·"}
                      </span>
                      <span className="session-title">{session.title}</span>
                    </button>
                  ))}
                </div>
              ))}
            </nav>
          </div>
        </aside>

        {/* ─── CENTER PANEL ───────────────────────────────────────────────── */}
        <main className="panel panel-center">
          <div className="panel-header">
            <span className="panel-dot" />
            {view === "dashboard" ? "ANALYTICS DASHBOARD" : "COMMUNICATION FEED"}
            {loading && view === "chat" && <span className="feed-streaming">STREAMING</span>}
          </div>

          {/* ── DASHBOARD VIEW ── */}
          {view === "dashboard" && (
            <div className="dashboard-area">
              {!analytics ? (
                <div className="feed-empty"><div className="feed-empty-icon">◈</div><div className="feed-empty-sub">ANALYTICS LOADING...</div></div>
              ) : (
                <>
                  <div className="dash-grid">
                    <div className="dash-card">
                      <div className="dash-card-title">TOPLAM MESAJ</div>
                      <div className="dash-card-value">{analytics.total_messages ?? 0}</div>
                    </div>
                    <div className="dash-card">
                      <div className="dash-card-title">SON 7 GÜN</div>
                      <div className="dash-card-value">{analytics.last_7_days ?? 0}</div>
                    </div>
                    <div className="dash-card">
                      <div className="dash-card-title">EN AKTİF AJAN</div>
                      <div className="dash-card-value dash-card-value--sm">{(analytics.top_agent?.name || "—").toUpperCase()}</div>
                      <div className="dash-card-sub">{analytics.top_agent?.count ?? 0} kullanım</div>
                    </div>
                  </div>

                  <div className="dash-section-title">AJAN KULLANIMI</div>
                  <div className="dash-bars">
                    {Object.entries(analytics.agent_counts || {})
                      .sort((a, b) => b[1] - a[1])
                      .map(([agent, count]) => {
                        const max = Math.max(...Object.values(analytics.agent_counts));
                        return (
                          <div key={agent} className="dash-bar-row">
                            <span className="dash-bar-label">{agent.toUpperCase()}</span>
                            <div className="dash-bar-track">
                              <div className="dash-bar-fill" style={{ width: `${(count / max) * 100}%` }} />
                            </div>
                            <span className="dash-bar-count">{count}</span>
                          </div>
                        );
                      })}
                  </div>

                  <div className="dash-section-title">SAATLİK DAĞILIM</div>
                  <div className="dash-hourly">
                    {Array.from({ length: 24 }, (_, h) => {
                      const count = analytics.hourly_distribution?.[String(h)] || 0;
                      const max = Math.max(...Object.values(analytics.hourly_distribution || { 0: 1 }), 1);
                      return (
                        <div key={h} className="dash-hour-col" title={`${h}:00 — ${count} mesaj`}>
                          <div className="dash-hour-bar" style={{ height: `${(count / max) * 48}px` }} />
                          {h % 6 === 0 && <div className="dash-hour-label">{h}:00</div>}
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          )}

          {/* ── CHAT VIEW ── */}
          {view === "chat" && <div className="feed-area">
            {messages.length === 0 && (
              <div className="feed-empty">
                <div className="feed-empty-icon">◈</div>
                <div className="feed-empty-title">ARIA COMMAND INTERFACE</div>
                <div className="feed-empty-sub">AWAITING INPUT — SYSTEM READY</div>
              </div>
            )}

            {messages.map((msg) => {
              const isUser = msg.role === "user";
              const agentLabel = msg.agent && msg.agent !== "chat" ? msg.agent.toUpperCase() : null;
              const ts = new Date().toLocaleTimeString("tr-TR", { hour12: false });

              return (
                <div
                  key={msg.id}
                  className={`feed-entry${isUser ? " feed-entry--user" : " feed-entry--aria"}`}
                >
                  <div className="feed-entry-header">
                    <span className="feed-ts">[{ts}]</span>
                    <span className="feed-prefix">{isUser ? "▶" : "◈"}</span>
                    <span className="feed-sender">{isUser ? "YOU" : "ARIA"}</span>
                    {agentLabel && (
                      <span className="feed-agent-badge">{agentLabel}</span>
                    )}
                    <span className="feed-divider">────────────────────</span>
                    {!isUser && (
                      <button
                        className={`pin-btn${isPinned(msg.id) ? " pin-btn--active" : ""}`}
                        onClick={() => togglePin(msg)}
                        title={isPinned(msg.id) ? "Pinli — kaldır" : "Pinle"}
                      >
                        {isPinned(msg.id) ? "★" : "☆"}
                      </button>
                    )}
                  </div>
                  <div className="feed-content">
                    {msg.streaming && !msg.content ? (
                      <span className="feed-waiting">█</span>
                    ) : isUser ? (
                      <span className="feed-user-text">{msg.content}</span>
                    ) : (
                      <MarkdownContent content={msg.content} />
                    )}
                    {msg.streaming && msg.content && (
                      <span className="stream-cursor">█</span>
                    )}
                  </div>
                </div>
              );
            })}
            <div ref={bottomRef} />
          </div>}

          {/* Drag overlay */}
          {isDragOver && view === "chat" && (
            <div className="drag-overlay">
              <div className="drag-overlay-text">DROP FILE — ANALYSIS QUEUED</div>
            </div>
          )}
        </main>

        {/* ─── RIGHT PANEL ───────────────────────────────────────────────────── */}
        <aside className="panel panel-right">

          {/* AGENT STATUS */}
          <div className="panel-section">
            <div className="panel-header">
              AGENT STATUS
            </div>
            <div className="agent-status-box">
              <div className="agent-active-dot" />
              <div className="agent-active-name">{activeAgent.toUpperCase()}</div>
              <div className="agent-active-label">ACTIVE AGENT</div>
            </div>
          </div>

          {/* QUICK ACCESS */}
          <div className="panel-section">
            <div className="panel-header">
              QUICK ACCESS
            </div>
            <div className="quick-access-list">
              {QUICK_COMMANDS.map((cmd) => (
                <button
                  key={cmd.action}
                  className="quick-access-btn"
                  onClick={() => { setView("chat"); handleQuickCommand(cmd.action, cmd.label); }}
                  disabled={loading}
                >
                  {cmd.label.toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {/* VIEW TOGGLE */}
          <div className="panel-section">
            <div className="panel-header">VIEW</div>
            <div className="quick-access-list">
              <button
                className={`quick-access-btn${view === "chat" ? " quick-access-btn--active" : ""}`}
                onClick={() => setView("chat")}
              >
                CHAT
              </button>
              <button
                className={`quick-access-btn${view === "dashboard" ? " quick-access-btn--active" : ""}`}
                onClick={() => setView("dashboard")}
              >
                DASHBOARD
              </button>
            </div>
          </div>

          {/* PINNED */}
          {pinnedMessages.length > 0 && (
            <div className="panel-section panel-section--grow">
              <div className="panel-header">PINNED ({pinnedMessages.length})</div>
              <div className="pinned-list">
                {pinnedMessages.slice(-5).map((p) => (
                  <div key={p.id} className="pinned-item" title={p.content}>
                    <span className="pinned-text">{p.content.slice(0, 60)}…</span>
                    <button className="pinned-remove" onClick={() => togglePin(p)}>×</button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ARTIFACTS */}
          {artifacts.length > 0 && (
            <div className="panel-section panel-section--grow">
              <div className="panel-header">ARTIFACTS ({artifacts.length})</div>
              <div className="artifact-list">
                {artifacts.slice(-8).reverse().map((a) => (
                  <div key={a.id} className="artifact-item"
                    onClick={() => a.type === "link" && window.open(a.content, "_blank")}
                    title={a.content}
                  >
                    <span className="artifact-icon">{a.type === "code" ? "❮❯" : "🔗"}</span>
                    <span className="artifact-label">
                      {a.type === "code" ? (a.lang || "code") : a.content.slice(0, 30)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

        </aside>
      </div>

      {/* ═══ INPUT BAR ══════════════════════════════════════════════════════════ */}
      <footer className="input-bar">
        <div className="input-row">
          <span className="input-prefix">▶</span>
          <textarea
            ref={textareaRef}
            className="input-field"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="ENTER COMMAND — SHIFT+ENTER FOR NEWLINE — DRAG & DROP FILES"
            rows={1}
            disabled={loading}
          />
          <div className="input-actions">
            <button
              className={`btn-action btn-mic${micRecording ? " btn-mic--active" : ""}`}
              onClick={handleMicClick}
              title={micRecording ? "Kaydediliyor — durdurmak için tıkla" : "Ses girişi"}
              type="button"
            >
              {micRecording ? "⏹" : "🎤"}
            </button>
            <button
              className={`btn-action btn-voice${voiceEnabled ? " btn-voice--on" : " btn-voice--off"}`}
              onClick={toggleVoice}
              title={voiceEnabled ? "Ses açık — kapat" : "Ses kapalı — aç"}
              type="button"
            >
              {voiceEnabled ? "🔊" : "🔇"}
            </button>
            <button
              className="btn-execute"
              onClick={sendMessage}
              disabled={loading || !input.trim()}
              type="button"
            >
              {loading ? <span className="execute-spinner" /> : "EXECUTE"}
            </button>
          </div>
        </div>
        <div className="input-statusbar">
          <span className="input-protocol">◈ SECURE ARIA PROTOCOL</span>
          <span className="input-divider-line" />
          <span className={`input-ollama${ollamaOnline ? " input-ollama--on" : " input-ollama--off"}`}>
            OLLAMA: {ollamaOnline ? "ONLINE" : "OFFLINE"}
          </span>
        </div>
      </footer>
    </div>
  );
}
