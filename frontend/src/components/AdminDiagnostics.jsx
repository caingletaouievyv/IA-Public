// IA/frontend/src/components/AdminDiagnostics.jsx
// Privacy-safe diagnostic events for admin roles.

import { useCallback, useEffect, useState } from "react";
import { listDiagnosticEvents } from "../api";

const EVENT_FIELDS = [
  "timestamp",
  "kind",
  "feature",
  "code",
  "category",
  "fallback",
  "error_type",
  "feedback_reason",
  "operation_id",
  "user_key_prefix",
  "provider",
  "model",
  "ai_mode",
  "memory_status",
  "note_context_mode",
  "memory_enabled",
];

function formatEventValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

export default function AdminDiagnostics() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadEvents = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const data = await listDiagnosticEvents(50);
      setEvents(Array.isArray(data.events) ? data.events : []);
    } catch (err) {
      setEvents([]);
      setError(err.message || "Could not load diagnostic events.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadEvents();
  }, [loadEvents]);

  return (
    <section className="section section--admin">
      <p className="card-desc">Content-free metadata for failures and reported answers. No prompts or message text are stored.</p>
      <div className="admin-diagnostics-toolbar">
        <button type="button" className="button-subtle" onClick={loadEvents} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      {loading ? <p role="status">Loading diagnostic events…</p> : null}
      {error ? <div className="out err" role="alert">{error}</div> : null}
      {!loading && !error && events.length === 0 ? (
        <p className="out" role="status">No diagnostic events yet.</p>
      ) : null}
      {!loading && events.length > 0 ? (
        <div className="card app-panel admin-diagnostics-list">
          {events.map((event) => (
            <article key={event.event_id || `${event.timestamp}-${event.code}`} className="admin-diagnostics-event">
              <dl className="admin-diagnostics-event__meta">
                {EVENT_FIELDS.map((field) => (
                  event[field] !== undefined && event[field] !== null && event[field] !== "" ? (
                    <div key={field} className="admin-diagnostics-event__row">
                      <dt>{field}</dt>
                      <dd>{formatEventValue(event[field])}</dd>
                    </div>
                  ) : null
                ))}
              </dl>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}
