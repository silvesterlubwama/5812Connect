import React from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { LayoutDashboard, ListTodo, MessageSquare, Receipt, Calendar, User, FileText, ShoppingBag, LogOut, ArrowLeft, Heart, ExternalLink } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { Button } from './ui/button';

const NAV = [
  { to: '/portal', icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/portal/tasks', icon: ListTodo, label: 'My Tasks' },
  { to: '/portal/chat', icon: MessageSquare, label: 'Chat' },
  { to: '/portal/events', icon: Calendar, label: 'Events & RSVP' },
  { to: '/portal/expenses', icon: Receipt, label: 'Expenses' },
  { to: '/portal/sales', icon: ShoppingBag, label: 'My Sales' },
  { to: '/portal/documents', icon: FileText, label: 'Documents' },
  { to: '/portal/family', icon: Heart, label: 'My Family' },
  { to: '/portal/profile', icon: User, label: 'Profile' },
];

export default function PortalLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user?.role === 'admin' || user?.role === 'system_admin';

  return (
    <div className="flex h-screen bg-background" data-testid="portal-layout">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 border-r border-border bg-card hidden md:flex flex-col">
        <div className="px-4 py-5 border-b border-border">
          <h1 className="text-base font-bold font-heading tracking-tight">58:12 Connect</h1>
          <p className="text-xs text-muted-foreground mt-0.5 truncate">User Portal - {user?.name}</p>
        </div>
        <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
          {NAV.map(n => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                }`
              }
              data-testid={`portal-nav-${n.label.toLowerCase().replace(/\s/g, '-')}`}
            >
              <n.icon size={16} />
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-border space-y-1.5">
          {isAdmin && (
            <Button variant="ghost" size="sm" className="w-full justify-start gap-2 text-xs" onClick={() => navigate('/dashboard')}>
              <ArrowLeft size={14} /> Admin Panel
            </Button>
          )}
          {['admin','system_admin','Executive Director','Adviser','Director','Manager','Coordinator','Staff','HR','Volunteer'].includes(user?.role) && (
            <NavLink to="/dashboard" className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-primary hover:bg-primary/10 transition-colors w-full">
              <ExternalLink size={14} /> Staff Portal
            </NavLink>
          )}
          <Button variant="ghost" size="sm" className="w-full justify-start gap-2 text-xs text-destructive" onClick={() => { logout(); navigate('/login'); }}>
            <LogOut size={14} /> Sign Out
          </Button>
        </div>
      </aside>

      {/* Mobile header */}
      <div className="flex flex-col flex-1 min-w-0">
        <header className="md:hidden flex items-center justify-between px-4 py-3 border-b border-border bg-card">
          <h1 className="text-sm font-bold font-heading">58:12 Portal</h1>
          <div className="flex gap-1">
            {NAV.slice(0, 5).map(n => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) =>
                  `p-2 rounded-lg ${isActive ? 'bg-primary/10 text-primary' : 'text-muted-foreground'}`
                }
              >
                <n.icon size={16} />
              </NavLink>
            ))}
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
