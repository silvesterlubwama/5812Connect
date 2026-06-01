import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import useIdleTimeout from '../utils/kioskMode';
import {
  LayoutDashboard, Users, Calendar, CheckSquare, CalendarDays,
  UserCheck, Settings, LogOut, Menu, X, Bell, ChevronDown, ChevronRight,
  DollarSign, ShoppingCart, Heart, MapPin, Shield, Search,
  User, ExternalLink, CheckCheck, BarChart3, Megaphone,
  Globe, Building2, TrendingUp, Sun, Moon, ScanLine, FileText, Wifi, WifiOff, CircleUser, Sliders,
  PieChart, FileSpreadsheet, Clock, Mail, CreditCard, Lock, Phone, PhoneCall, Voicemail, Server,
  MessageSquare, BookOpen, Workflow, HeartHandshake, Landmark
} from 'lucide-react';
import { Button } from './ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from './ui/dropdown-menu';
import { Avatar, AvatarFallback } from './ui/avatar';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Dialog, DialogContent } from './ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { notificationsApi, searchApi, locationsApi } from '../services/api';
import api from '../services/api';
import { useWebSocket } from '../context/WebSocketContext';
import { useI18n } from '../context/I18nContext';
import { LANGUAGES } from '../i18n';
import { toast } from 'sonner';
import Dialer from './Dialer';
import { useCall } from '../context/CallContext';

// Role helpers
const ADMIN_ROLES = ['admin', 'system_admin'];
const ED_PLUS = ['admin', 'system_admin', 'Executive Director'];
const DIRECTOR_PLUS = [...ED_PLUS, 'Adviser', 'Director'];
const MANAGER_PLUS = [...DIRECTOR_PLUS, 'Manager'];
const COORDINATOR_PLUS = [...MANAGER_PLUS, 'Leader', 'Coordinator'];
const STAFF_PLUS = [...COORDINATOR_PLUS, 'Staff', 'HR'];

const NAV_SECTIONS = [
  {
    label: 'Ministry',
    collapsible: true,
    items: [
      { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
      { to: '/outreach', icon: Globe, label: 'Outreach', roles: STAFF_PLUS },
      { to: '/events', icon: Calendar, label: 'Events' },
      { to: '/check-ins', icon: UserCheck, label: 'Check-ins', roles: STAFF_PLUS },
    ]
  },
  {
    label: 'Operations',
    collapsible: true,
    items: [
      { to: '/boards', icon: CheckSquare, label: 'Boards' },
      { to: '/resources', icon: Building2, label: 'Resources', roles: STAFF_PLUS },
      { to: '/calendar', icon: CalendarDays, label: 'Calendar' },
      { to: '/members', icon: Users, label: 'People', roles: STAFF_PLUS },
      { to: '/volunteer-scheduling', icon: Clock, label: 'Scheduling', roles: COORDINATOR_PLUS },
      { to: '/social-work', icon: HeartHandshake, label: 'Social Work', roles: STAFF_PLUS, module: 'social_work' },
      { to: '/access', icon: ScanLine, label: 'Access Control', roles: COORDINATOR_PLUS },
    ]
  },
  {
    label: 'Comms',
    collapsible: true,
    items: [
      { to: '/comms', icon: MessageSquare, label: 'Chat' },
      { to: '/call-history', icon: PhoneCall, label: 'Call History', roles: STAFF_PLUS },
    ]
  },
  {
    label: 'Finance',
    collapsible: true,
    roles: STAFF_PLUS,  // visible to staff but each item is gated by module access
    items: [
      { to: '/financial', icon: DollarSign, label: 'Financial', module: 'finance' },
      { to: '/accounting', icon: BookOpen, label: 'Accounting', module: 'accounting' },
      { to: '/banking', icon: Landmark, label: 'Banking', module: 'banking' },
      { to: '/hr', icon: Users, label: 'HR & Payroll', module: 'hr' },
      { to: '/approvals', icon: Workflow, label: 'Approvals', module: 'finance' },
      { to: '/sales', icon: ShoppingCart, label: 'Marketplace', module: 'sales' },
    ]
  },
  {
    label: 'Reports',
    collapsible: true,
    roles: MANAGER_PLUS,
    items: [
      { to: '/reports', icon: FileText, label: 'Reports' },
      { to: '/report-builder', icon: FileSpreadsheet, label: 'Report Builder' },
    ]
  },
  {
    label: 'Admin',
    collapsible: true,
    roles: ADMIN_ROLES,
    items: [
      { to: '/admin', icon: User, label: 'Staff & Users' },
      { to: '/locations', icon: MapPin, label: 'Campuses' },
      { to: '/financial-apis', icon: CreditCard, label: 'Financial APIs', roles: ADMIN_ROLES },
      { to: '/email-templates', icon: Mail, label: 'Email Templates' },
      { to: '/settings', icon: Settings, label: 'Settings' },
      { to: '/audit', icon: Shield, label: 'Audit Trail' },
      { to: '/gdpr', icon: Lock, label: 'Privacy & GDPR' },
    ]
  },
];

const notifTypeIcon = { error: '!', warning: '!', info: 'i', success: '+' };
const notifTypeColor = { error: 'bg-red-500', warning: 'bg-yellow-500', info: 'bg-blue-500', success: 'bg-green-500' };

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifs, setNotifs] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifOpen, setNotifOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [dialerOpen, setDialerOpen] = useState(false);
  const [expandedSections, setExpandedSections] = useState({});
  const [campuses, setCampuses] = useState([]);
  const [activeCampus, setActiveCampus] = useState(() => localStorage.getItem('5812_active_campus') || '');

  // Inactivity logout — privileged roles get the strictest timeout; rank-and-file staff
  // get a generous default. Disabled for kiosk roles (they have their own lock screen).
  const _idleMs = (() => {
    if (!user) return 0;
    const role = user.role || '';
    if (['Security Contractor', 'Guest', 'guest'].includes(role)) return 0; // no idle logout on kiosks
    if (['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director'].includes(role)) {
      return 15 * 60 * 1000;   // 15 min for privileged
    }
    return 30 * 60 * 1000;     // 30 min for everyone else
  })();
  useIdleTimeout(() => {
    if (!user) return;
    toast.warning('Signed out due to inactivity', { duration: 8000 });
    logout();
    navigate('/login');
  }, _idleMs, _idleMs > 0);
  const [darkMode, setDarkMode] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('5812_dark_mode') === 'true' || document.documentElement.classList.contains('dark');
    }
    return false;
  });
  const searchRef = useRef(null);
  const searchTimeout = useRef(null);

  let missedCallCount = 0;
  try { const callCtx = useCall(); missedCallCount = callCtx?.missedCallCount || 0; } catch (e) {}

  const toggleDarkMode = () => {
    const next = !darkMode;
    setDarkMode(next);
    localStorage.setItem('5812_dark_mode', String(next));
    document.documentElement.classList.toggle('dark', next);
  };

  useEffect(() => { document.documentElement.classList.toggle('dark', darkMode); }, []);

  const handleLogout = () => { logout(); navigate('/login'); };

  const initials = user?.name ? user.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase() : 'AU';
  const isAdmin = ADMIN_ROLES.includes(user?.role);
  const isGlobalAdmin = ['admin', 'system_admin', 'Executive Director', 'Adviser'].includes(user?.role);
  const hasMultipleCampuses = (user?.location_ids || []).length > 1;
  const canSwitchCampus = isGlobalAdmin || hasMultipleCampuses;
  const userRole = user?.role || '';
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [campusFeatures, setCampusFeatures] = useState({ financial_enabled: true, marketplace_enabled: true, financial_apis_enabled: true, hr_enabled: true });
  const { addListener } = useWebSocket();
  const { t, lang, changeLang, languages } = useI18n();

  // Fetch campuses for switcher and check feature flags
  useEffect(() => {
    const loadCampuses = async () => {
      try {
        const res = await locationsApi.list();
        const locs = res.data || [];
        setCampuses(locs);
        const activeId = activeCampus || user?.location_id;
        if (activeId) {
          const loc = locs.find(l => l.id === activeId);
          if (loc) setCampusFeatures({ financial_enabled: loc.financial_enabled !== false, marketplace_enabled: loc.marketplace_enabled !== false, financial_apis_enabled: loc.financial_apis_enabled !== false, hr_enabled: loc.hr_enabled !== false });
        } else {
          // "All Locations" — check user's primary campus features
          const userLoc = locs.find(l => l.id === user?.location_id);
          if (userLoc) {
            setCampusFeatures({ financial_enabled: userLoc.financial_enabled !== false, marketplace_enabled: userLoc.marketplace_enabled !== false, financial_apis_enabled: userLoc.financial_apis_enabled !== false, hr_enabled: userLoc.hr_enabled !== false });
          }
        }
      } catch (e) { console.warn(e.message || e); }
    };
    loadCampuses();
  }, [activeCampus, user?.location_id]);

  // Auto-expand ONLY the section containing the active route, collapse all others
  useEffect(() => {
    const path = location.pathname;
    const newExpanded = {};
    NAV_SECTIONS.forEach((section, idx) => {
      if (section.items.some(item => path.startsWith(item.to))) {
        newExpanded[idx] = true;
      }
    });
    setExpandedSections(newExpanded);
  }, [location.pathname]);

  const toggleSection = (idx) => {
    setExpandedSections(prev => {
      const next = {};
      // Collapse all others, toggle this one
      Object.keys(prev).forEach(k => { if (parseInt(k) !== idx) next[k] = false; });
      next[idx] = !prev[idx];
      return next;
    });
  };

  const handleCampusChange = async (val) => {
    const campusId = val === '__all__' ? '' : val;
    setActiveCampus(campusId);
    localStorage.setItem('5812_active_campus', campusId);
    try {
      if (campusId) {
        await api.put('/user/active-campus', { campus_id: campusId });
      } else {
        await api.put('/user/active-campus/clear');
      }
      window.location.reload(); // Reload to apply new filter across all pages
    } catch (e) { console.warn(e.message || e); toast.error('Failed to switch campus'); }
  };

  // Online/offline detection
  useEffect(() => {
    const goOnline = () => setIsOnline(true);
    const goOffline = () => { setIsOnline(false); toast.warning('You are offline.'); };
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    return () => { window.removeEventListener('online', goOnline); window.removeEventListener('offline', goOffline); };
  }, []);

  useEffect(() => {
    const unsub = addListener('notification', (data) => {
      setUnreadCount(prev => prev + 1);
      toast.info(data.title || 'New notification');
    });
    return unsub;
  }, [addListener]);

  const fetchUnreadCount = useCallback(async () => {
    try { const res = await notificationsApi.unreadCount(); setUnreadCount(res.data.count); } catch (e) { console.warn(e.message || e); }
  }, []);

  const fetchNotifs = async () => {
    try { const res = await notificationsApi.list(); setNotifs(res.data); setUnreadCount(res.data.filter(n => !n.read).length); } catch (e) { console.warn(e.message || e); }
  };

  useEffect(() => { fetchUnreadCount(); const interval = setInterval(fetchUnreadCount, 30000); return () => clearInterval(interval); }, [fetchUnreadCount]);
  const handleNotifOpen = () => { setNotifOpen(true); fetchNotifs(); };
  const markAllRead = async () => { try { await notificationsApi.markAllRead(); setNotifs(prev => prev.map(n => ({ ...n, read: true }))); setUnreadCount(0); } catch (e) { console.warn(e.message || e); } };
  const markRead = async (id) => { try { await notificationsApi.markRead(id); setNotifs(prev => prev.map(n => n.id === id ? { ...n, read: true } : n)); setUnreadCount(prev => Math.max(0, prev - 1)); } catch (e) { console.warn(e.message || e); } };

  useEffect(() => {
    const handler = (e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); setSearchOpen(true); } if (e.key === 'Escape') setSearchOpen(false); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const handleSearch = (q) => {
    setSearchQuery(q);
    clearTimeout(searchTimeout.current);
    if (q.length < 2) { setSearchResults([]); return; }
    setSearching(true);
    searchTimeout.current = setTimeout(async () => {
      try { const res = await searchApi.query(q); setSearchResults(res.data.results || []); } catch (e) { console.warn(e.message || e); }
      finally { setSearching(false); }
    }, 300);
  };

  const resultTypeIcon = { member: 'U', event: 'E', task: 'T', product: 'P' };
  const handleResultClick = (result) => { setSearchOpen(false); setSearchQuery(''); setSearchResults([]); navigate(result.url); };

  // Finance feature gate (mirrors backend `has_finance_access`):
  //   • implicit for Director+/Admin/EDs (Manager and below now require explicit grant)
  //   • explicit per-user via `{module}_access: true` (with optional `{module}_access_expires_at`)
  const PRIVILEGED_ROLES = ['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director'];

  const _grantActive = (mod) => {
    if (!user?.[`${mod}_access`]) return false;
    const exp = user?.[`${mod}_access_expires_at`];
    if (exp) {
      try { if (new Date(exp).getTime() <= Date.now()) return false; } catch { /* ignore */ }
    }
    return true;
  };

  const hasModuleAccess = (mod) => {
    if (!mod) return true;
    if (PRIVILEGED_ROLES.includes(userRole) || isAdmin) return true;
    // HR also auto-granted to users with HR role or HR/Human Resources department
    if (mod === 'hr') {
      if (['HR', 'hr'].includes(userRole)) return true;
      const dept = (user?.department || '').toLowerCase();
      const depts = (user?.departments || []).map(d => (d || '').toLowerCase());
      if (dept === 'hr' || dept === 'human resources' || depts.includes('hr') || depts.includes('human resources')) return true;
    }
    return _grantActive(mod);
  };

  // Legacy alias used by a few places downstream.
  const userHasFinanceAccess = hasModuleAccess('finance');

  // Check if user can see a nav item
  const canAccess = (item) => {
    if (item.roles && !item.roles.includes(userRole) && !isAdmin) return false;
    if (item.adminOnly && !isAdmin) return false;
    // Per-module gate (new): each nav entry can declare a `module` key — Director+ implicit,
    // everyone else needs an explicit grant.
    if (item.module && !hasModuleAccess(item.module)) return false;
    // Campus feature toggles — show if the campus enables the feature.
    if (item.to === '/financial' && !campusFeatures.financial_enabled) return false;
    if (item.to === '/sales' && !campusFeatures.marketplace_enabled) return false;
    if (item.to === '/financial-apis' && !campusFeatures.financial_apis_enabled) return false;
    if (item.to === '/hr' && !campusFeatures.hr_enabled) return false;
    return true;
  };

  // Check if user can see a section
  const canSeeSection = (section) => {
    if (section.roles && !section.roles.includes(userRole) && !isAdmin) return false;
    // Section visible if at least one item passes its individual gate.
    return section.items.some(item => canAccess(item));
  };

  // -------- ROUTE-LEVEL ACCESS GUARD (closes the "type-the-URL bypass") --------
  // Build a flat path → rule map from NAV_SECTIONS so a user typing /financial in the
  // address bar can't escape the same gate that hides the sidebar entry.
  // Routes NOT in this map are treated as "any staff allowed" (since the parent <StaffRoute>
  // already keeps guests/security-contractors out of the main app).
  const routeRules = (() => {
    const out = {};
    for (const section of NAV_SECTIONS) {
      for (const item of section.items) {
        // Effective roles: item.roles wins; otherwise inherit section.roles.
        const effRoles = item.roles || section.roles || null;
        out[item.to] = { roles: effRoles, module: item.module || null };
      }
    }
    // Non-sidebar routes that still need a role gate
    Object.assign(out, {
      '/admin': { roles: ADMIN_ROLES, module: null },
      '/audit': { roles: ADMIN_ROLES, module: null },
      '/locations': { roles: ADMIN_ROLES, module: null },
      '/financial-apis': { roles: ADMIN_ROLES, module: null },
      '/email-templates': { roles: ADMIN_ROLES, module: null },
      '/settings': { roles: ADMIN_ROLES, module: null },
      '/gdpr': { roles: ADMIN_ROLES, module: null },
      '/hr': { roles: null, module: 'hr' },
      '/financial': { roles: null, module: 'finance' },
      '/accounting': { roles: null, module: 'accounting' },
      '/banking': { roles: null, module: 'banking' },
      '/approvals': { roles: null, module: 'finance' },
      '/sales': { roles: null, module: 'sales' },
      '/social-work': { roles: STAFF_PLUS, module: 'social_work' },
      // Sub-pages that piggy-back off finance/accounting/sales modules
      '/accounts-receivable': { roles: null, module: 'finance' },
      '/customer-statements': { roles: null, module: 'finance' },
      '/reconciliation': { roles: null, module: 'banking' },
      '/sales-analytics': { roles: null, module: 'sales' },
      '/pos-setup': { roles: null, module: 'sales' },
      '/barcode-reissue': { roles: null, module: 'sales' },
      '/location-analytics': { roles: MANAGER_PLUS, module: null },
      '/campus-reports': { roles: MANAGER_PLUS, module: null },
      '/reports': { roles: MANAGER_PLUS, module: null },
      '/report-builder': { roles: MANAGER_PLUS, module: null },
      '/analytics': { roles: MANAGER_PLUS, module: null },
      '/access': { roles: COORDINATOR_PLUS, module: null },
      '/volunteer-scheduling': { roles: COORDINATOR_PLUS, module: null },
      '/attendance': { roles: STAFF_PLUS, module: null },
      '/check-ins': { roles: STAFF_PLUS, module: null },
      '/members': { roles: STAFF_PLUS, module: null },
      '/people': { roles: STAFF_PLUS, module: null },
      '/outreach': { roles: STAFF_PLUS, module: null },
      '/resources': { roles: STAFF_PLUS, module: null },
      '/call-history': { roles: STAFF_PLUS, module: null },
      '/app-settings': { roles: ADMIN_ROLES, module: null },
    });
    return out;
  })();

  useEffect(() => {
    if (!user) return;
    // Normalize path (strip leading slash variants and query/hash)
    const path = location.pathname.replace(/\/$/, '') || '/';
    const rule = routeRules[path];
    if (!rule) return;  // No rule → fail open (staff default)
    // Role gate
    if (rule.roles && !rule.roles.includes(userRole) && !isAdmin) {
      toast.error('You do not have access to that page');
      navigate('/dashboard', { replace: true });
      return;
    }
    // Module gate
    if (rule.module && !hasModuleAccess(rule.module)) {
      toast.error(`This page requires ${rule.module.replace('_', ' ')} access — ask an admin to grant it.`);
      navigate('/dashboard', { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, user?.role, user?.finance_access, user?.hr_access, user?.sales_access, user?.banking_access, user?.accounting_access, user?.social_work_access, user?.restricted_access]);

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {sidebarOpen && <div className="fixed inset-0 bg-black/30 z-20 lg:hidden" onClick={() => setSidebarOpen(false)} />}

      {/* Sidebar */}
      <aside className={`fixed lg:static inset-y-0 left-0 z-30 flex flex-col w-60 bg-card border-r border-border transform transition-transform duration-200 ease-in-out ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}>
        <div className="flex items-center gap-2 px-4 py-3.5 border-b border-border">
          <img src="https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1" alt="58:12 Global" className="h-7 w-auto object-contain" />
          <button className="lg:hidden ml-auto text-muted-foreground" onClick={() => setSidebarOpen(false)}><X size={18} /></button>
        </div>

        {/* Campus Switcher */}
        {canSwitchCampus && campuses.length > 0 && (
          <div className="px-3 py-2 border-b border-border">
            <Select value={activeCampus || '__all__'} onValueChange={handleCampusChange}>
              <SelectTrigger className="h-8 text-xs" data-testid="campus-switcher">
                <div className="flex items-center gap-1.5">
                  <MapPin size={12} className="text-muted-foreground shrink-0" />
                  <SelectValue placeholder="My Campus" />
                </div>
              </SelectTrigger>
              <SelectContent>
                {isGlobalAdmin && <SelectItem value="__all__">All Locations</SelectItem>}
                {(() => {
                  // Build a sorted list: top-level campuses first, then their sub-locations indented underneath
                  const userLocs = user?.location_ids || [];
                  const userPrimaryLoc = user?.location_id;
                  const isVisible = (c) => {
                    if (isGlobalAdmin) return true;
                    if (userLocs.includes(c.id) || c.id === userPrimaryLoc) return true;
                    // Show sub-locations under user's campuses
                    if (c.parent_id && (userLocs.includes(c.parent_id) || c.parent_id === userPrimaryLoc)) return true;
                    // Show parent campus when user is in a sub-location
                    const userInSub = campuses.find(s => s.parent_id === c.id && (userLocs.includes(s.id) || s.id === userPrimaryLoc));
                    if (userInSub) return true;
                    return false;
                  };
                  const visible = campuses.filter(isVisible);
                  // Group by parent
                  const tops = visible.filter(c => c.type !== 'sub-location' || !c.parent_id);
                  const subsByParent = {};
                  visible.forEach(c => {
                    if (c.parent_id && c.type === 'sub-location') {
                      (subsByParent[c.parent_id] = subsByParent[c.parent_id] || []).push(c);
                    }
                  });
                  const ordered = [];
                  tops.forEach(top => {
                    ordered.push(top);
                    (subsByParent[top.id] || []).forEach(sub => ordered.push(sub));
                  });
                  // Append any orphan sub-locations whose parent isn't visible
                  visible.forEach(c => {
                    if (c.type === 'sub-location' && c.parent_id && !tops.find(t => t.id === c.parent_id)) {
                      if (!ordered.find(x => x.id === c.id)) ordered.push(c);
                    }
                  });
                  return ordered.map(c => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.type === 'sub-location' ? `   ↳ ${c.name}` : c.name}
                    </SelectItem>
                  ));
                })()}
              </SelectContent>
            </Select>
          </div>
        )}

        <nav className="flex-1 overflow-y-auto py-2 px-2 space-y-0.5">
          {NAV_SECTIONS.map((section, si) => {
            if (!canSeeSection(section)) return null;
            const isExpanded = expandedSections[si] === true;
            const hasActiveChild = section.items.some(item => location.pathname.startsWith(item.to));
            const shouldShow = isExpanded || hasActiveChild;
            const visibleItems = section.items.filter(canAccess);

            if (!section.label) {
              return (
                <div key={si}>
                  {visibleItems.map(({ to, icon: Icon, label }) => (
                    <NavLink key={to} to={to} onClick={() => setSidebarOpen(false)} data-testid={`nav-${to.replace('/', '')}`}
                      className={({ isActive }) => `flex items-center gap-3 px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors ${isActive ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground'}`}>
                      <Icon size={15} className="shrink-0" />{label}
                    </NavLink>
                  ))}
                </div>
              );
            }

            return (
              <div key={si} className="mt-2">
                {section.collapsible ? (
                  <button onClick={() => toggleSection(si)}
                    className={`flex items-center justify-between w-full text-xs font-semibold uppercase tracking-wider px-3 py-1.5 rounded-md transition-colors ${hasActiveChild ? 'text-primary' : 'text-muted-foreground/60 hover:text-muted-foreground'}`}
                    data-testid={`nav-section-${section.label.toLowerCase().replace(/\s/g, '-')}`}>
                    <span>{section.label}</span>
                    <ChevronRight size={12} className={`transition-transform duration-200 ${shouldShow ? 'rotate-90' : ''}`} />
                  </button>
                ) : (
                  <p className="text-xs font-semibold text-muted-foreground/60 uppercase tracking-wider px-3 mb-1">{section.label}</p>
                )}
                {(shouldShow || !section.collapsible) && (
                  <div className="space-y-0.5 mt-0.5">
                    {visibleItems.map(({ to, icon: Icon, label }) => (
                      <NavLink key={to} to={to} onClick={() => setSidebarOpen(false)} data-testid={`nav-${to.replace('/', '')}`}
                        className={({ isActive }) => `flex items-center gap-3 px-3 py-1.5 rounded-lg text-sm cursor-pointer transition-colors ${isActive ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground'}`}>
                        <Icon size={14} className="shrink-0" />{label}
                      </NavLink>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        <div className="px-2 py-3 border-t border-border">
          <div className="flex items-center gap-2.5 px-2 py-2 rounded-lg">
            <Avatar className="h-8 w-8"><AvatarFallback className="bg-primary text-primary-foreground text-xs font-semibold">{initials}</AvatarFallback></Avatar>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{user?.name}</p>
              <p className="text-xs text-muted-foreground truncate capitalize">{user?.role || 'Member'}</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="flex items-center gap-2 sm:gap-3 px-3 sm:px-4 py-2.5 sm:py-3 bg-card border-b border-border shrink-0">
          <button className="lg:hidden text-muted-foreground p-1" onClick={() => setSidebarOpen(true)} data-testid="mobile-menu-btn"><Menu size={20} /></button>
          <button className="flex items-center gap-2 px-2 sm:px-3 py-1.5 rounded-lg bg-secondary/60 text-sm text-muted-foreground hover:bg-secondary transition-colors sm:flex-1 sm:max-w-64"
            onClick={() => setSearchOpen(true)} data-testid="global-search-trigger">
            <Search size={13} /><span className="text-xs hidden sm:inline">Search... (Ctrl+K)</span>
          </button>
          <div className="flex-1" />

          <Button variant="ghost" size="sm" className="h-9 w-9 p-0 text-green-600 hover:bg-green-100 dark:hover:bg-green-950" onClick={() => setDialerOpen(true)} data-testid="call-button"><Phone size={18} /></Button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="h-9 gap-1.5 text-xs px-2" data-testid="language-switcher">
                <Globe size={14} /> {languages.find(l => l.code === lang)?.name?.slice(0, 3) || 'EN'}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {languages.map(l => (<DropdownMenuItem key={l.code} onClick={() => changeLang(l.code)} className={lang === l.code ? 'font-semibold bg-accent' : ''}>{l.name}</DropdownMenuItem>))}
            </DropdownMenuContent>
          </DropdownMenu>

          {!isOnline && <Badge variant="destructive" className="text-[10px] gap-1 h-6 px-2"><WifiOff size={11} /> Offline</Badge>}
          <Button variant="ghost" size="icon" className="h-9 w-9" onClick={toggleDarkMode} data-testid="dark-mode-toggle">{darkMode ? <Sun size={17} /> : <Moon size={17} />}</Button>

          {/* Notifications */}
          <DropdownMenu open={notifOpen} onOpenChange={(v) => { if (v) handleNotifOpen(); else setNotifOpen(v); }}>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="relative h-9 w-9" data-testid="notification-bell">
                <Bell size={17} />
                {unreadCount > 0 && <span className="absolute -top-0.5 -right-0.5 h-4 w-4 rounded-full bg-primary text-primary-foreground text-[9px] flex items-center justify-center font-bold">{unreadCount > 9 ? '9+' : unreadCount}</span>}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-80 p-0" data-testid="notification-dropdown">
              <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                <p className="font-semibold text-sm">Notifications</p>
                {unreadCount > 0 && <Button variant="ghost" size="sm" className="h-7 text-xs gap-1" onClick={markAllRead}><CheckCheck size={12} /> Mark all read</Button>}
              </div>
              <div className="max-h-80 overflow-y-auto">
                {notifs.length === 0 ? <p className="text-sm text-muted-foreground text-center py-6">No notifications</p> : notifs.map(n => (
                  <div key={n.id} onClick={() => { markRead(n.id); if (n.link) navigate(n.link); setNotifOpen(false); }}
                    className={`flex items-start gap-3 px-4 py-3 hover:bg-secondary/50 cursor-pointer border-b border-border/50 last:border-0 ${!n.read ? 'bg-primary/5' : ''}`}>
                    <span className={`mt-0.5 h-5 w-5 rounded-full ${notifTypeColor[n.type] || 'bg-blue-500'} text-white text-[10px] flex items-center justify-center font-bold shrink-0`}>{notifTypeIcon[n.type] || 'i'}</span>
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-medium leading-tight ${!n.read ? '' : 'text-muted-foreground'}`}>{n.title}</p>
                      <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{n.message}</p>
                    </div>
                    {!n.read && <span className="h-2 w-2 rounded-full bg-primary shrink-0 mt-1.5" />}
                  </div>
                ))}
              </div>
            </DropdownMenuContent>
          </DropdownMenu>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="flex items-center gap-2 px-2 h-9">
                <Avatar className="h-7 w-7"><AvatarFallback className="bg-primary text-primary-foreground text-xs font-semibold">{initials}</AvatarFallback></Avatar>
                <span className="text-sm font-medium hidden sm:block">{user?.name}</span>
                <ChevronDown size={13} className="text-muted-foreground" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <div className="px-2 py-1.5"><p className="text-sm font-medium">{user?.name}</p><p className="text-xs text-muted-foreground capitalize">{user?.role}</p></div>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild><NavLink to="/profile" className="flex items-center gap-2 cursor-pointer" data-testid="profile-menu-my-profile"><Settings size={14} /> My Profile &amp; Family</NavLink></DropdownMenuItem>
              <DropdownMenuItem asChild><a href="/kiosk" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 cursor-pointer"><ExternalLink size={14} /> Open Kiosk</a></DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={handleLogout} className="text-destructive focus:text-destructive cursor-pointer"><LogOut size={14} className="mr-2" /> Sign Out</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </header>

        <main className="flex-1 overflow-y-auto"><Outlet /></main>
      </div>

      {/* Global Search */}
      <Dialog open={searchOpen} onOpenChange={setSearchOpen}>
        <DialogContent className="max-w-lg p-0 gap-0" data-testid="search-dialog">
          <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
            <Search size={16} className="text-muted-foreground shrink-0" />
            <input ref={searchRef} autoFocus className="flex-1 bg-transparent outline-none text-sm placeholder:text-muted-foreground"
              placeholder="Search members, events, boards, products..." value={searchQuery} onChange={e => handleSearch(e.target.value)} data-testid="search-input" />
            {searchQuery && <button className="text-muted-foreground hover:text-foreground" onClick={() => { setSearchQuery(''); setSearchResults([]); }}><X size={14} /></button>}
          </div>
          <div className="max-h-80 overflow-y-auto py-2">
            {searching && <div className="px-4 py-3 text-sm text-muted-foreground">Searching...</div>}
            {!searching && searchQuery.length >= 2 && searchResults.length === 0 && <div className="px-4 py-6 text-sm text-muted-foreground text-center">No results for "{searchQuery}"</div>}
            {searchResults.map((r, i) => (
              <button key={r.url || r.title || i} className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-secondary/60 transition-colors text-left" onClick={() => handleResultClick(r)} data-testid="search-result">
                <Badge variant="outline" className="text-[10px] capitalize shrink-0 h-5 w-5 flex items-center justify-center p-0">{resultTypeIcon[r.type]}</Badge>
                <div className="flex-1 min-w-0"><p className="text-sm font-medium truncate">{r.title}</p><p className="text-xs text-muted-foreground truncate">{r.subtitle}</p></div>
              </button>
            ))}
            {!searchQuery && (
              <div className="px-4 py-4 text-xs text-muted-foreground space-y-1">
                <p className="font-medium text-foreground mb-2">Quick Navigation</p>
                {['/dashboard', '/members', '/events', '/financial', '/sales', '/boards'].map(path => (
                  <button key={path} className="flex items-center gap-2 hover:text-foreground transition-colors w-full text-left" onClick={() => { navigate(path); setSearchOpen(false); }}>
                    <span className="text-primary">-</span> {path.replace('/', '').replace('-', ' ').replace(/\b\w/g, l => l.toUpperCase()) || 'Dashboard'}
                  </button>
                ))}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Dialer open={dialerOpen} onClose={() => setDialerOpen(false)} />
    </div>
  );
}
