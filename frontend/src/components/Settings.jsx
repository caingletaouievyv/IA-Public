// IA/frontend/src/components/Settings.jsx
// Per-user settings: GET/PUT /settings. Auth via login (no API secret).

import { useState } from "react";
import { getSettings, putSettings } from "../api";

export default function Settings() {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [prefs, setPrefs] = useState({ theme: "dark", default_model: "" });

  const load = async () => {
    setError(null);
    setLoading(true);
    try {
      const data = await getSettings();
      setSettings(data);
      setPrefs((p) => ({ ...p, ...data }));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const save = async (e) => {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const updated = await putSettings(prefs);
      setSettings(updated);
      setPrefs(updated);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="section section--settings">
      <p className="card-desc">Per-user preferences. Stored with your account.</p>
      <div className="card app-panel">
        <button type="button" className="button-secondary" onClick={load} aria-label={loading ? "Loading settings" : "Load settings"} disabled={loading}>
          {loading ? "…" : "Load settings"}
        </button>
      </div>
      {error && <div className="out err">{error}</div>}
      {(settings !== null || prefs.theme || prefs.default_model) && (
        <form onSubmit={save} className={`card app-panel form--compact ${saving ? "loading" : ""}`}>
          <p className="card-title">Preferences</p>
          <label htmlFor="prefTheme">Theme</label>
          <input
            id="prefTheme"
            type="text"
            placeholder="e.g. dark"
            value={prefs.theme ?? ""}
            onChange={(e) => setPrefs((p) => ({ ...p, theme: e.target.value }))}
            disabled={saving}
          />
          <label htmlFor="prefModel">Default model (optional)</label>
          <input
            id="prefModel"
            type="text"
            placeholder="e.g. groq"
            value={prefs.default_model ?? ""}
            onChange={(e) => setPrefs((p) => ({ ...p, default_model: e.target.value }))}
            disabled={saving}
          />
          <button type="submit" className="button-primary" aria-label={saving ? "Saving settings" : "Save settings"} disabled={saving}>
            {saving ? "…" : "Save"}
          </button>
        </form>
      )}
    </section>
  );
}
