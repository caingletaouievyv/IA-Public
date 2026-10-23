// IA/frontend/src/authRoles.js
// Role helpers for navigation; backend authorization remains authoritative.

export const ROLE_USER = "user";
export const ROLE_ADMIN = "admin";
export const ROLE_MAIN_ADMIN = "main_admin";

export function canShowDiagnosticsNav(role) {
  return role === ROLE_ADMIN || role === ROLE_MAIN_ADMIN;
}

export function canShowUserManagementNav(role) {
  return role === ROLE_MAIN_ADMIN;
}
