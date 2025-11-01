import React, { useState } from "react";

async function search(query) {
  const resp = await fetch("http://127.0.0.1:8000/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, use_gemini: false, top_k: 5 }),
  });
  return await resp.json();
}

export default function Chat() {
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  const send = async () => {
    if (!query.trim()) return;
    const userMsg = { who: "user", text: query };
    setMessages((m) => [...m, userMsg]);
    setLoading(true);
    try {
      const data = await search(query);
      const botMsg = { who: "bot", summary: data.summary, cards: data.cards || [] };
      setMessages((m) => [...m, botMsg]);
    } catch (err) {
      setMessages((m) => [...m, { who: "bot", summary: "Error: could not reach backend" }]);
    } finally {
      setLoading(false);
      setQuery("");
    }
  };

  const onKey = (e) => {
    if (e.key === "Enter") send();
  };

  return (
    <div className="chat">
      <div>
        {messages.map((m, i) =>
          m.who === "user" ? (
            <div key={i} className="message user">{m.text}</div>
          ) : (
            <div key={i} className="message bot">
              <div style={{ marginBottom: 8 }}>{m.summary}</div>
              {m.cards && m.cards.length > 0 && (
                <div>
                  {m.cards.map((c, idx) => (
                    <div className="card" key={idx}>
                      <div className="card-title">{c.title}</div>
                      <div className="card-meta">{c.project_name} • {c.city_locality}</div>
                      <div className="card-meta">{c.bhk}BHK • {c.price} • {c.possession}</div>
                      <div style={{ marginTop: 6 }}>
                        <a href={c.cta} target="_blank" rel="noreferrer">Open</a>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        )}
      </div>

      <div className="input-row">
        <input
          type="text"
          placeholder="Ask e.g. 3BHK in Pune under 1.2 Cr"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKey}
        />
        <button onClick={send} disabled={loading}>{loading ? "…" : "Send"}</button>
      </div>
    </div>
  );
}
