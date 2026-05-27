import { useState, useRef, useEffect } from "react";

const AGENTS = {
  chat: { icon: "💬", label: "Sohbet" },
  researcher: { icon: "🔬", label: "Arastirma" },
  coder: { icon: "💻", label: "Kod" },
  writer: { icon: "✍️", label: "Yazar" },
  analyst: { icon: "📊", label: "Analist" },
  brief: { icon: "📋", label: "Brief" },
  monitor: { icon: "📡", label: "Monitor" },
  memory: { icon: "🧠", label: "Hafiza" },
};

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

let _msgId = 0;
const newId = () => ++_msgId;

export default function App() {
  const [messages, setMessages] = useState([
    {
      id: newId(),
      role: "aria",
      content: "Merhaba Meric. Ben ARIA. Ne yapmami istersin?",
      agent: "chat",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeAgent, setActiveAgent] = useState("chat");
  const [sysStatus, setSysStatus] = useState({ model: "...", online: null });
  const bottomRef = useRef(null);

  // Gerçek Ollama durumunu /status'tan çek
  useEffect(() => {
    fetch(`${API_URL}/status`)
      .then((r) => r.json())
      .then((d) =>
        setSysStatus({ model: d.active_model ?? "?", online: d.ollama_running })
      )
      .catch(() => setSysStatus({ model: "—", online: false }));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    const text = input;
    const ariaId = newId();
    setMessages((prev) => [
      ...prev,
      { id: newId(), role: "user", content: text, agent: activeAgent },
    ]);
    setInput("");
    setLoading(true);

    // ARIA cevabı için boş placeholder ekle — stream token'ları buraya yazılacak
    setMessages((prev) => [
      ...prev,
      { id: ariaId, role: "aria", content: "", agent: activeAgent, streaming: true },
    ]);

    try {
      const res = await fetch(`${API_URL}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, agent: activeAgent }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE satırlarını ayır; son yarım satırı buffer'da tut
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;

          const token = line.slice(6); // "data: " prefixini at

          if (token.startsWith("[error]")) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === ariaId
                  ? { ...m, content: `⚠️ ${token.slice(8)}`, streaming: false }
                  : m
              )
            );
            return; // finally hala çalışır, streaming: false idempotent
          }

          // Token'ı id ile bul ve ekle — index değil
          setMessages((prev) =>
            prev.map((m) =>
              m.id === ariaId ? { ...m, content: m.content + token } : m
            )
          );
        }
      }
    } catch (e) {
      setMessages((prev) => {
        const target = prev.find((m) => m.id === ariaId);
        if (target) {
          return prev.map((m) =>
            m.id === ariaId
              ? { ...m, content: "⚠️ Backend baglantisi yok. API ayakta mi? (aria serve)", streaming: false }
              : m
          );
        }
        return [
          ...prev,
          { id: newId(), role: "aria", content: "⚠️ Backend baglantisi yok. API ayakta mi? (aria serve)", agent: "chat" },
        ];
      });
    } finally {
      // Stream bitti ya da hata oldu — streaming bayrağını kapat
      setMessages((prev) =>
        prev.map((m) =>
          m.id === ariaId && m.streaming ? { ...m, streaming: false } : m
        )
      );
      setLoading(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="app">
      <div className="bg-orbit" />
      <div className="bg-grid" />

      <aside className="side">
        <div className="brand">
          <div className="brand-mark">ARIA</div>
          <div className="brand-sub">Local AI Console</div>
        </div>
        <div className="agent-panel">
          {Object.entries(AGENTS).map(([key, { icon, label }]) => (
            <button
              key={key}
              className={`agent ${activeAgent === key ? "active" : ""}`}
              onClick={() => setActiveAgent(key)}
            >
              <span className="agent-icon">{icon}</span>
              <span className="agent-label">{label}</span>
            </button>
          ))}
        </div>
        <div className="system">
          <div className="system-row">
            <span className={`dot ${sysStatus.online === true ? "online" : sysStatus.online === false ? "offline" : "pending"}`} />
            <span>{sysStatus.online === true ? "Ollama aktif" : sysStatus.online === false ? "Ollama kapali" : "Kontrol ediliyor..."}</span>
          </div>
          <div className="system-row muted">{sysStatus.model}</div>
          <div className="system-row muted">API: {API_URL}</div>
        </div>
      </aside>

      <main className="stage">
        <header className="topbar">
          <div className="mode">
            <span className="mode-icon">{AGENTS[activeAgent]?.icon}</span>
            <span className="mode-label">{AGENTS[activeAgent]?.label} modu</span>
          </div>
          <div className="pill">Zero-cloud</div>
        </header>

        <section className="thread">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`row ${msg.role === "user" ? "row-user" : "row-aria"}`}
            >
              {msg.role === "aria" && <div className="avatar">A</div>}
              <div className={`bubble ${msg.role === "user" ? "user" : "aria"}`}>
                <div className="bubble-meta">
                  {msg.role === "user" ? "Sen" : "ARIA"}
                  <span className="bubble-agent">{msg.agent}</span>
                </div>
                <div className="bubble-text">
                  {msg.streaming && !msg.content
                    ? <span className="typing">• • •</span>
                    : msg.content}
                  {msg.streaming && msg.content && (
                    <span className="cursor">▌</span>
                  )}
                </div>
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </section>

        <section className="composer">
          <div className="composer-box">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder={`${AGENTS[activeAgent]?.icon} ${AGENTS[activeAgent]?.label} modunda yaz...`}
              rows={1}
            />
            <button onClick={sendMessage} disabled={loading}>
              Gonder
            </button>
          </div>
          <div className="composer-hint">
            Enter: gonder • Shift+Enter: satir
          </div>
        </section>
      </main>
    </div>
  );
}