import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const GUEST_ROLES = new Set(['Guest', 'guest', 'Visitor', 'visitor']);
const ADMIN_ROLES = new Set(['admin', 'system_admin', 'Executive Director', 'Adviser']);

/**
 * Route guard that redirects guests/pending users to the portal.
 * Staff+ users see the full app layout.
 */
export function StaffRoute({ children }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
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
  if (!ADMIN_ROLES.has(user.role)) return <Navigate to="/dashboard" replace />;
  return children;
}
