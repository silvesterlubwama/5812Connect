import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const GUEST_ROLES = new Set(['Guest', 'guest', 'Visitor', 'visitor']);
const ADMIN_ROLES = new Set(['admin', 'system_admin', 'Executive Director', 'Adviser']);
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
  if (user.status === 'pending') return <Navigate to="/portal" replace />;
  if (GUEST_ROLES.has(user.role) && !user.is_parent) return <Navigate to="/portal" replace />;
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
