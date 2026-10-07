// IA/frontend/src/components/Login.jsx
// Login/register page. On success stores token and calls onLogin(token).

import { useEffect, useState } from "react";
import { login, register } from "../api";

export default function Login({ onLogin, initialIsRegister = false, onModeChange = null }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isRegister, setIsRegister] = useState(initialIsRegister);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setIsRegister(initialIsRegister);
  }, [initialIsRegister]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    const u = username.trim();
    const p = password;
    if (!u || !p) {
      setError("Enter username and password.");
      return;
    }
    setLoading(true);
    try {
      if (isRegister) {
        await register(u, p);
      }
      const data = await login(u, p);
      onLogin(data.token);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <header className="app-header app-header--login">
        <h1>IA</h1>
      </header>
      <section className="login-card card app-panel">
        <h2 className="app-panel__title">{isRegister ? "Create account" : "Sign in"}</h2>
        <p className="card-desc">
          {isRegister ? "Register a new account to access AI." : "Use your account to access AI."}
        </p>
        <form onSubmit={handleSubmit} className={`form--compact ${loading ? "loading" : ""}`}>
          <label htmlFor="login-username">Username</label>
          <input
            id="login-username"
            type="text"
            autoComplete="username"
            placeholder="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={loading}
          />
          <label htmlFor="login-password">Password</label>
          <input
            id="login-password"
            type="password"
            autoComplete={isRegister ? "new-password" : "current-password"}
            placeholder="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
          />
          {error && <div className="out err">{error}</div>}
          <button type="submit" className="button-primary" aria-label={loading ? isRegister ? "Creating account" : "Signing in" : isRegister ? "Register and sign in" : "Sign in"} disabled={loading}>
            {loading ? "…" : isRegister ? "Register and sign in" : "Sign in"}
          </button>
        </form>
        <div className="auth-switch">
          <span>{isRegister ? "Already have an account?" : "Don't have an account?"}</span>
          <button
            type="button"
            className="auth-switch__action"
            onClick={() => {
              const nextIsRegister = !isRegister;
              setIsRegister(nextIsRegister);
              setError(null);
              onModeChange?.(nextIsRegister);
            }}
          >
            {isRegister ? "Sign in" : "Create one"}
          </button>
        </div>
      </section>
    </div>
  );
}
