// IA/frontend/src/components/AdminUsers.jsx
// Main Admin user list and user→admin promotion.

import { useCallback, useEffect, useState } from "react";
import { listAdminUsers, promoteAdminUser } from "../api";
import { ROLE_USER } from "../authRoles";

export default function AdminUsers() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [promoteTarget, setPromoteTarget] = useState(null);
  const [promoting, setPromoting] = useState(false);

  const loadUsers = useCallback(async () => {
    setError(null);
    setSuccess(null);
    setLoading(true);
    try {
      const data = await listAdminUsers();
      setUsers(Array.isArray(data.users) ? data.users : []);
    } catch (err) {
      setUsers([]);
      setError(err.message || "Could not load users.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const confirmPromote = async () => {
    if (!promoteTarget || promoting) return;
    setPromoting(true);
    setError(null);
    setSuccess(null);
    const target = promoteTarget;
    try {
      await promoteAdminUser(target.user_id);
      setPromoteTarget(null);
      await loadUsers();
      setSuccess(`Promoted ${target.username} to admin.`);
    } catch (err) {
      setError(err.message || "Promotion failed.");
    } finally {
      setPromoting(false);
    }
  };

  return (
    <section className="section section--admin">
      <p className="card-desc">Promote trusted users to admin. Main Admin ownership cannot change here.</p>
      {loading ? <p role="status">Loading users…</p> : null}
      {error ? <div className="out err" role="alert">{error}</div> : null}
      {success ? <div className="out success-msg" role="status">{success}</div> : null}
      {!loading && !error && users.length === 0 ? (
        <p className="out" role="status">No users found.</p>
      ) : null}
      {!loading && users.length > 0 ? (
        <div className="card app-panel">
          <table className="admin-users-table">
            <thead>
              <tr>
                <th scope="col">Username</th>
                <th scope="col">Role</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.user_id}>
                  <td>{user.username}</td>
                  <td>{user.role}</td>
                  <td>
                    {user.role === ROLE_USER ? (
                      <button
                        type="button"
                        className="button-subtle"
                        onClick={() => setPromoteTarget(user)}
                      >
                        Promote to admin
                      </button>
                    ) : (
                      <span className="admin-users-table__muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {promoteTarget ? (
        <div className="notes-delete-confirm" role="dialog" aria-modal="true" aria-labelledby="admin-promote-title">
          <div className="notes-delete-confirm__backdrop" onClick={() => !promoting && setPromoteTarget(null)} aria-hidden />
          <div className="notes-delete-confirm__box">
            <p id="admin-promote-title" className="notes-delete-confirm__title">
              Promote {promoteTarget.username} to admin?
            </p>
            <p className="notes-delete-confirm__desc">
              Admins can view diagnostics and bypass AI credit limits. This cannot assign Main Admin.
            </p>
            <div className="notes-delete-confirm__actions">
              <button type="button" className="button-subtle" onClick={() => setPromoteTarget(null)} disabled={promoting}>
                Cancel
              </button>
              <button type="button" className="button-primary" onClick={confirmPromote} disabled={promoting}>
                {promoting ? "Promoting…" : "Promote"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
