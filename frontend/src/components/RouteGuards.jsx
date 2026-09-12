import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import PendingApprovalScreen from '../pages/PendingApprovalScreen';

const GUEST_ROLES = new Set(['Guest', 'guest', 'Visitor', 'visitor']);
const ADMIN_ROLES = new Set(['admin', 'system_admin', 'Executive Director', 'Adviser']);
// Roles that always land on the STAFF app — never bounced to the portal even
// if `is_parent` happens to be true. Fixes iter343 regression where an
// approved staff member was redirected to /portal by StaffRoute.
const STAFF_ROLES = new Set([
  'admin', 'system_admin', 'Executive Director', 'Adviser', 'Director',
  'Regional Director', 'Manager', 'Coordinator', 'Leader', 'Staff', 'HR',
  'Volunteer', 'volunteer',
]);
// Security Contractors are private-contractor users who must NEVER reach the main app.
// They are pinned to the /security-checkpoint terminal — both /login and direct URLs bounce.
const KIOSK_ONLY_ROLES = new Set(['Security Contractor', 'security_contractor']);

/**
 * Route guard that redirects guests/pending users to the portal, and
 * Security Contractors to the dedicated checkpoint terminal.
 * Staff+ users see the full app layout.
 */
export function StaffRoute({ children }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (KIOSK_ONLY_ROLES.has(user.role)) return <Navigate to="/security-checkpoint" replace />;
  // Pending accounts see the approval-gate screen only — no portal data,
  // no staff canvas. They can browse public events + logout from there.
  if (user.status === 'pending') return <PendingApprovalScreen />;
  // Explicit staff roles win over any guest heuristics.
  if (STAFF_ROLES.has(user.role)) return children;
  // Non-staff guests (with or without is_parent) live in /portal.
  if (GUEST_ROLES.has(user.role)) return <Navigate to="/portal" replace />;
  return children;
}

/**
 * Route guard for admin-only pages.
 */
export function AdminRoute({ children }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (KIOSK_ONLY_ROLES.has(user.role)) return <Navigate to="/security-checkpoint" replace />;
  if (!ADMIN_ROLES.has(user.role)) return <Navigate to="/dashboard" replace />;
  return children;
}

/**
 * Route guard for /portal — approved guests only. Pending accounts fall
 * through to the same pending-approval screen so unapproved users never
 * see family/tasks/expenses etc.
 */
/**
 * Route guard for staff-only pages INSIDE the member portal (chat, tasks,
 * expenses, time-off, documents). iter345 — members/parents were able to
 * reach these by URL even though the nav hid them.
 */
export function StaffOnlyPortalRoute({ children }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (!STAFF_ROLES.has(user.role)) return <Navigate to="/portal" replace />;
  return children;
}

export function PortalRoute({ children }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (KIOSK_ONLY_ROLES.has(user.role)) return <Navigate to="/security-checkpoint" replace />;
  if (user.status === 'pending') return <PendingApprovalScreen />;
  return children;
}

