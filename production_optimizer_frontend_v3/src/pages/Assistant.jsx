import { useMemo, useState } from "react";
import { Bot, Send, Sparkles, AlertTriangle, Factory, PackageSearch, Clock3 } from "lucide-react";
import { askAssistant } from "../api";

const suggestions = [
  "Why is ORD104 late?",
  "Which orders have the highest risk?",
  "Which machines are most loaded?",
  "Which materials are critical?",
  "Explain the current production plan",
];

export default function Assistant({ runId }) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  const canAsk = useMemo(() => question.trim().length > 2 && !loading, [question, loading]);

  const submit = async (text = question) => {
    const value = text.trim();
    if (!value || loading) return;
    setMessages((prev) => [...prev, { role: "user", text: value }]);
    setQuestion("");
    setLoading(true);
    try {
      const result = await askAssistant(value, runId);
      setMessages((prev) => [...prev, { role: "assistant", text: result.answer, facts: result.facts || [] }]);
    } catch (error) {
      const detail = error?.response?.data?.detail || error?.message || "Unable to contact the planning assistant.";
      setMessages((prev) => [...prev, { role: "assistant", text: detail, error: true }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="assistant-page">
      <section className="assistant-hero">
        <div className="assistant-hero-icon"><Bot size={28} /></div>
        <div>
          <div className="eyebrow">DECISION SUPPORT</div>
          <h1>Planning Assistant</h1>
          <p>Ask questions about the active production plan, orders, machines and material risks.</p>
        </div>
        <div className="assistant-status"><span /> {runId ? "Active run connected" : "No optimization run selected"}</div>
      </section>

      <section className="assistant-grid">
        <aside className="assistant-side panel-card">
          <div className="assistant-side-title"><Sparkles size={17} /> Suggested questions</div>
          {suggestions.map((item) => (
            <button key={item} className="assistant-suggestion" onClick={() => submit(item)} disabled={loading}>
              {item}
            </button>
          ))}
          <div className="assistant-capabilities">
            <div><Clock3 size={16} /><span>Late orders & risk</span></div>
            <div><Factory size={16} /><span>Machine capacity</span></div>
            <div><PackageSearch size={16} /><span>Material availability</span></div>
          </div>
        </aside>

        <section className="assistant-chat panel-card">
          <div className="assistant-chat-header">
            <div><strong>Production decision assistant</strong><span>Answers are based on data available in the system.</span></div>
          </div>
          <div className="assistant-messages">
            {messages.length === 0 && (
              <div className="assistant-empty">
                <Bot size={34} />
                <h3>How can I help?</h3>
                <p>Try <b>“Why is ORD104 late?”</b> or ask for the most critical machines or materials.</p>
              </div>
            )}
            {messages.map((message, index) => (
              <div key={`${message.role}-${index}`} className={`assistant-message ${message.role} ${message.error ? "error" : ""}`}>
                <div className="assistant-avatar">{message.role === "user" ? "You" : <Bot size={16} />}</div>
                <div className="assistant-bubble">
                  <div className="assistant-text">{message.text}</div>
                  {message.facts?.length > 0 && (
                    <div className="assistant-facts">
                      {message.facts.map((fact, i) => <span key={i}>{fact}</span>)}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {loading && <div className="assistant-message assistant"><div className="assistant-avatar"><Bot size={16} /></div><div className="assistant-bubble typing">Analyzing the production data…</div></div>}
          </div>
          <form className="assistant-input" onSubmit={(e) => { e.preventDefault(); submit(); }}>
            <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask something about the production plan…" />
            <button type="submit" disabled={!canAsk}><Send size={17} /> Ask</button>
          </form>
        </section>
      </section>
    </div>
  );
}
