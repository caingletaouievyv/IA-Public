// IA/frontend/src/components/Settings.jsx
// Per-user settings: GET/PUT /settings. Auth via login (no API secret).

import { useEffect, useState } from "react";
import { getSettings, putSettings } from "../api";
import AskContextIcon from "./AskContextIcon";
import {
  ASK_CONTEXT_SOURCES,
  DEFAULT_VISIBLE_CONTEXT_SOURCES,
  normalizeShowContextSourceLabels,
  normalizeVisibleContextSources,
} from "../askContextSources";

export default function Settings() {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [sourceSaving, setSourceSaving] = useState(false);
  const [labelSaving, setLabelSaving] = useState(false);
  const [error, setError] = useState(null);
  const [prefs, setPrefs] = useState({ theme: "dark", default_model: "" });
  const [visibleSources, setVisibleSources] = useState(DEFAULT_VISIBLE_CONTEXT_SOURCES);
  const [showContextSourceLabels, setShowContextSourceLabels] = useState(
    normalizeShowContextSourceLabels(undefined),
  );

  const load = async () => {
    setError(null);
    setLoading(true);
    try {
      const data = await getSettings();
      const loaded = data && typeof data === "object" && !Array.isArray(data) ? data : {};
      const sources = normalizeVisibleContextSources(loaded.ask_context_sources);
      const showLabels = normalizeShowContextSourceLabels(loaded.show_context_source_labels);
      setSettings(loaded);
      setVisibleSources(sources);
      setShowContextSourceLabels(showLabels);
      setPrefs((p) => ({
        ...p,
        ...loaded,
        ask_context_sources: sources,
        show_context_source_labels: showLabels,
      }));
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

  const changeContextSourceLabels = async (showLabels) => {
    const previousValue = showContextSourceLabels;
    setShowContextSourceLabels(showLabels);
    setPrefs((current) => ({ ...current, show_context_source_labels: showLabels }));
    setError(null);
    setLabelSaving(true);
    try {
      const updated = await putSettings({ show_context_source_labels: showLabels });
      setSettings(updated);
    } catch (e) {
      setShowContextSourceLabels(previousValue);
      setPrefs((current) => ({ ...current, show_context_source_labels: previousValue }));
      setError(e.message);
    } finally {
      setLabelSaving(false);
    }
  };

  const save = async (e) => {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const updated = await putSettings({
        ...prefs,
        ask_context_sources: visibleSources,
        show_context_source_labels: showContextSourceLabels,
      });
      setSettings(updated);
      setVisibleSources(normalizeVisibleContextSources(updated.ask_context_sources));
      setShowContextSourceLabels(normalizeShowContextSourceLabels(updated.show_context_source_labels));
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
        <p className="card-title" id="ask-context-sources-title">Ask</p>
        <p className="card-desc">Choose which context sources appear in Ask and whether their labels are shown.</p>
        {settings === null ? (
          <p className="ask-context-settings__status" role="status">
            {loading ? "Loading saved sources…" : "Saved source preferences are unavailable."}
          </p>
        ) : (
          <>
            <label className="ask-context-settings__option" htmlFor="show-ask-labels">
              <input
                id="show-ask-labels"
                type="checkbox"
                checked={showContextSourceLabels}
                disabled={loading || sourceSaving || labelSaving || saving}
                onChange={(event) => changeContextSourceLabels(event.target.checked)}
              />
              <span className="ask-context-settings__copy">
                <span className="ask-context-settings__name">Show Ask labels</span>
                <span className="ask-context-settings__description">Show text labels beside Ask context-source icons.</span>
              </span>
            </label>
            <p className="card-title" id="ask-context-sources-subtitle">Ask Context Sources</p>
            <div className="ask-context-settings__list" role="group" aria-labelledby="ask-context-sources-subtitle">
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
                      disabled={loading || sourceSaving || labelSaving || saving || alwaysVisible}
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
          </>
        )}
        <p className="ask-context-settings__status" role="status">
          {loading && settings !== null ? "Refreshing saved sources…" : sourceSaving || labelSaving ? "Saving…" : ""}
        </p>
      </div>
      <div className="card app-panel">
        <button type="button" className="button-secondary" onClick={load} aria-label={loading ? "Loading settings" : "Load settings"} disabled={loading}>
          {loading ? "…" : "Load settings"}
        </button>
      </div>
      {error && <div className="out err">{error}</div>}
      {settings !== null && (
        <form onSubmit={save} className={`card app-panel form--compact ${saving || sourceSaving || labelSaving ? "loading" : ""}`}>
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
          <button type="submit" className="button-primary" aria-label={saving ? "Saving settings" : "Save settings"} disabled={saving || sourceSaving || labelSaving}>
            {saving ? "…" : "Save"}
          </button>
        </form>
      )}
    </section>
  );
}
