// IA/frontend/src/components/DebugContext.jsx
// Debug: question → POST /ai/debug/context. Auth via login (no API secret).

import { useState } from "react";
import { debugContext } from "../api";

export default function DebugContext() {
  const [question, setQuestion] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setData(null);
    setLoading(true);
    try {
      const res = await debugContext(question, null);
      setData(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="section section--debug">
      <h2 className="app-panel__title">Debug context</h2>
      <p className="card-desc">Inspect which context (your notes) the AI would get for a question.</p>
      <form onSubmit={handleSubmit} className={`card app-panel form--compact ${loading ? "loading" : ""}`}>
        <label htmlFor="debugQuestion">Question</label>
        <input
          id="debugQuestion"
          type="text"
          placeholder="e.g. find note about FAISS"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={loading}
        />
        <button type="submit" disabled={loading}>
          {loading ? "…" : "Get context"}
        </button>
      </form>
      {error && <div className="out err">{error}</div>}
      {data && (
        <div className="out">
          <pre>{JSON.stringify(data, null, 2)}</pre>
        </div>
      )}
    </section>
  );
}
