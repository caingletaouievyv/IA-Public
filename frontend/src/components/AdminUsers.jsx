// IA/frontend/src/components/AdminUsers.jsx
// Main Admin user list, promotion, and demotion.

import { useCallback, useEffect, useState } from "react";
import { demoteAdminUser, listAdminUsers, promoteAdminUser } from "../api";
import { ROLE_ADMIN, ROLE_USER } from "../authRoles";

export default function AdminUsers() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [pendingAction, setPendingAction] = useState(null);
  const [acting, setActing] = useState(false);

  const loadUsers = useCallback(async () => {
    setError(null);
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

  const confirmAction = async () => {
    if (!pendingAction || acting) return;
    setActing(true);
    setError(null);
    setSuccess(null);
    const { kind, user: target } = pendingAction;
    try {
      const updated =
        kind === "promote"
          ? await promoteAdminUser(target.user_id)
          : await demoteAdminUser(target.user_id);
      setUsers((previous) =>
        previous.map((item) =>
          item.user_id === updated.user_id ? { ...item, role: updated.role } : item
        )
      );
      setPendingAction(null);
      setSuccess(
        kind === "promote"
          ? `Promoted ${target.username} to admin.`
          : `Demoted ${target.username} to user.`
      );
    } catch (err) {
      setError(err.message || (kind === "promote" ? "Promotion failed." : "Demotion failed."));
    } finally {
      setActing(false);
    }
  };

  const dialogCopy =
    pendingAction?.kind === "demote"
      ? {
          title: `Demote ${pendingAction.user.username} to user?`,
          desc: "They will lose diagnostics access and unlimited AI credits. Main Admin ownership is unchanged.",
          confirm: acting ? "Demoting…" : "Demote",
        }
      : pendingAction
        ? {
            title: `Promote ${pendingAction.user.username} to admin?`,
            desc: "Admins can view diagnostics and bypass AI credit limits. This cannot assign Main Admin.",
            confirm: acting ? "Promoting…" : "Promote",
          }
        : null;

  return (
    <section className="section section--admin">
      <p className="card-desc">
        Promote trusted users to admin or demote admins to regular users. Main Admin ownership cannot change here.
      </p>
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
                        onClick={() => setPendingAction({ kind: "promote", user })}
                      >
                        Promote to Admin
                      </button>
                    ) : user.role === ROLE_ADMIN ? (
                      <button
                        type="button"
                        className="button-subtle"
                        onClick={() => setPendingAction({ kind: "demote", user })}
                      >
                        Demote to User
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
      {pendingAction && dialogCopy ? (
        <div className="notes-delete-confirm" role="dialog" aria-modal="true" aria-labelledby="admin-role-action-title">
          <div
            className="notes-delete-confirm__backdrop"
            onClick={() => !acting && setPendingAction(null)}
            aria-hidden
          />
          <div className="notes-delete-confirm__box">
            <p id="admin-role-action-title" className="notes-delete-confirm__title">
              {dialogCopy.title}
            </p>
            <p className="notes-delete-confirm__desc">{dialogCopy.desc}</p>
            <div className="notes-delete-confirm__actions">
              <button type="button" className="button-subtle" onClick={() => setPendingAction(null)} disabled={acting}>
                Cancel
              </button>
              <button type="button" className="button-primary" onClick={confirmAction} disabled={acting}>
                {dialogCopy.confirm}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
