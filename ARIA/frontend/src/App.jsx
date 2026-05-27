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

export default function App() {
  const [messages, setMessages] = useState([
    {
      role: "aria",
      content: "Merhaba Meric. Ben ARIA. Ne yapmami istersin?",
      agent: "chat",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeAgent, setActiveAgent] = useState("chat");
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    const userMsg = { role: "user", content: input, agent: activeAgent };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: input, agent: activeAgent }),
      });
      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          role: "aria",
          content: data.response,
          agent: data.agent || activeAgent,
        },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          role: "aria",
          content:
            "Backend baglantisi yok. API ayakta mi? (aria serve)",
          agent: "chat",
        },
      ]);
    } finally {
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
            <span className="dot online" />
            <span>Ollama aktif</span>
          </div>
          <div className="system-row muted">qwen2.5:7b</div>
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
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`row ${msg.role === "user" ? "row-user" : "row-aria"}`}
            >
              {msg.role === "aria" && <div className="avatar">A</div>}
              <div className={`bubble ${msg.role === "user" ? "user" : "aria"}`}>
                <div className="bubble-meta">
                  {msg.role === "user" ? "Sen" : "ARIA"}
                  <span className="bubble-agent">{msg.agent}</span>
                </div>
                <div className="bubble-text">{msg.content}</div>
              </div>
            </div>
          ))}
          {loading && (
            <div className="row row-aria">
              <div className="avatar">A</div>
              <div className="bubble aria">
                <div className="typing">• • •</div>
              </div>
            </div>
          )}
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