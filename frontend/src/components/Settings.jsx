// IA/frontend/src/components/Settings.jsx
// Per-user settings: GET/PUT /settings. Auth via login (no API secret).

import { useEffect, useState } from "react";
import { getSettings, putSettings } from "../api";
import AskContextIcon from "./AskContextIcon";
import {
  ASK_CONTEXT_SOURCES,
  DEFAULT_VISIBLE_CONTEXT_SOURCES,
  normalizeVisibleContextSources,
} from "../askContextSources";

export default function Settings() {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [sourceSaving, setSourceSaving] = useState(false);
  const [error, setError] = useState(null);
  const [prefs, setPrefs] = useState({ theme: "dark", default_model: "" });
  const [visibleSources, setVisibleSources] = useState(DEFAULT_VISIBLE_CONTEXT_SOURCES);

  const load = async () => {
    setError(null);
    setLoading(true);
    try {
      const data = await getSettings();
      const loaded = data && typeof data === "object" && !Array.isArray(data) ? data : {};
      const sources = normalizeVisibleContextSources(loaded.ask_context_sources);
      setSettings(loaded);
      setVisibleSources(sources);
      setPrefs((p) => ({ ...p, ...loaded, ask_context_sources: sources }));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const changeSourceVisibility = async (sourceId, isVisible) => {
    if (sourceId === "conversation") return;
    const previousSources = visibleSources;
    const nextSources = isVisible
      ? normalizeVisibleContextSources([...visibleSources, sourceId])
      : normalizeVisibleContextSources(visibleSources.filter((id) => id !== sourceId));

    setVisibleSources(nextSources);
    setPrefs((current) => ({ ...current, ask_context_sources: nextSources }));
    setError(null);
    setSourceSaving(true);
    try {
      const updated = await putSettings({ ask_context_sources: nextSources });
      setSettings(updated);
      setPrefs((current) => ({ ...current, ask_context_sources: nextSources }));
    } catch (e) {
      setVisibleSources(previousSources);
      setPrefs((current) => ({ ...current, ask_context_sources: previousSources }));
      setError(e.message);
    } finally {
      setSourceSaving(false);
    }
  };

  const save = async (e) => {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const updated = await putSettings({ ...prefs, ask_context_sources: visibleSources });
      setSettings(updated);
      setVisibleSources(normalizeVisibleContextSources(updated.ask_context_sources));
      setPrefs({ ...updated, ask_context_sources: normalizeVisibleContextSources(updated.ask_context_sources) });
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="section section--settings">
      <p className="card-desc">Per-user preferences. Stored with your account.</p>
      <div className="card app-panel ask-context-settings">
        <p className="card-title" id="ask-context-sources-title">Ask Context Sources</p>
        <p className="card-desc">Choose which source controls appear in the Ask toolbar. Changes save automatically.</p>
        <div className="ask-context-settings__list" role="group" aria-labelledby="ask-context-sources-title">
          {ASK_CONTEXT_SOURCES.map((source) => {
            const alwaysVisible = source.id === "conversation";
            return (
              <label
                className={`ask-context-settings__option${alwaysVisible ? " ask-context-settings__option--locked" : ""}`}
                key={source.id}
              >
                <input
                  type="checkbox"
                  checked={visibleSources.includes(source.id) || alwaysVisible}
                  disabled={loading || sourceSaving || saving || alwaysVisible}
                  onChange={(event) => changeSourceVisibility(source.id, event.target.checked)}
                />
                <span className="ask-context-settings__icon"><AskContextIcon name={source.id} /></span>
                <span className="ask-context-settings__copy">
                  <span className="ask-context-settings__name">{source.label}</span>
                  <span className="ask-context-settings__description">{source.description}</span>
                  {alwaysVisible && <span className="ask-context-settings__locked">Always visible to access conversation history.</span>}
                </span>
              </label>
            );
          })}
        </div>
        <p className="ask-context-settings__status" role="status">
          {loading ? "Loading saved sources…" : sourceSaving ? "Saving…" : ""}
        </p>
      </div>
      <div className="card app-panel">
        <button type="button" className="button-secondary" onClick={load} aria-label={loading ? "Loading settings" : "Load settings"} disabled={loading}>
          {loading ? "…" : "Load settings"}
        </button>
      </div>
      {error && <div className="out err">{error}</div>}
      {(settings !== null || prefs.theme || prefs.default_model) && (
        <form onSubmit={save} className={`card app-panel form--compact ${saving || sourceSaving ? "loading" : ""}`}>
          <p className="card-title">Preferences</p>
          <label htmlFor="prefTheme">Theme</label>
          <input
            id="prefTheme"
            type="text"
            placeholder="e.g. dark"
            value={prefs.theme ?? ""}
            onChange={(e) => setPrefs((p) => ({ ...p, theme: e.target.value }))}
            disabled={saving || sourceSaving || loading}
          />
          <label htmlFor="prefModel">Default model (optional)</label>
          <input
            id="prefModel"
            type="text"
            placeholder="e.g. groq"
            value={prefs.default_model ?? ""}
            onChange={(e) => setPrefs((p) => ({ ...p, default_model: e.target.value }))}
            disabled={saving || sourceSaving || loading}
          />
          <button type="submit" className="button-primary" aria-label={saving ? "Saving settings" : "Save settings"} disabled={saving || sourceSaving}>
            {saving ? "…" : "Save"}
          </button>
        </form>
      )}
    </section>
  );
}
