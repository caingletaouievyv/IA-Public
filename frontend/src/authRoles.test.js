// IA/frontend/src/authRoles.test.js
// Role navigation helpers.

import assert from "node:assert/strict";
import test from "node:test";
import {
  canShowDiagnosticsNav,
  canShowUserManagementNav,
  ROLE_ADMIN,
  ROLE_MAIN_ADMIN,
  ROLE_USER,
} from "./authRoles.js";

test("shows diagnostics nav for admin and main_admin only", () => {
  assert.equal(canShowDiagnosticsNav(ROLE_USER), false);
  assert.equal(canShowDiagnosticsNav(ROLE_ADMIN), true);
  assert.equal(canShowDiagnosticsNav(ROLE_MAIN_ADMIN), true);
  assert.equal(canShowDiagnosticsNav(undefined), false);
});

test("shows user management nav for main_admin only", () => {
  assert.equal(canShowUserManagementNav(ROLE_USER), false);
  assert.equal(canShowUserManagementNav(ROLE_ADMIN), false);
  assert.equal(canShowUserManagementNav(ROLE_MAIN_ADMIN), true);
});
