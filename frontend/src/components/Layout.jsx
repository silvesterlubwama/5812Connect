import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  LayoutDashboard, Users, Calendar, CheckSquare, CalendarDays,
  UserCheck, Settings, LogOut, Menu, X, Bell, ChevronDown,
  DollarSign, ShoppingCart, Heart, MapPin, Shield, Search,
  User, ExternalLink, CheckCheck, BarChart3, Megaphone,
  Globe, Building2, TrendingUp, Sun, Moon, ScanLine, FileText, Wifi, WifiOff, CircleUser, Sliders,
  PieChart, FileSpreadsheet, Clock, Mail, CreditCard, Lock, Phone, PhoneCall, Voicemail, Server
} from 'lucide-react';
import { Button } from './ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from './ui/dropdown-menu';
import { Avatar, AvatarFallback } from './ui/avatar';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Dialog, DialogContent } from './ui/dialog';
import { notificationsApi, searchApi } from '../services/api';
import { useWebSocket } from '../context/WebSocketContext';
import { useI18n } from '../context/I18nContext';
import { LANGUAGES } from '../i18n';
import { toast } from 'sonner';
import Dialer from './Dialer';
import { useCall } from '../context/CallContext';

const NAV_SECTIONS = [
  {
    label: null,
    items: [
      { to: '/dashboard', icon: LayoutDashboard, labelKey: 'nav.dashboard' },
      { to: '/portal', icon: CircleUser, labelKey: 'nav.portal' },
    ]
  },
  {
    labelKey: 'people.title',
    items: [
      { to: '/members', icon: Users, labelKey: 'nav.people' },
    ]
  },
  {
    label: 'Ministry',
    items: [
      { to: '/events', icon: Calendar, labelKey: 'nav.events' },
      { to: '/calendar', icon: CalendarDays, labelKey: 'nav.calendar' },
      { to: '/tasks', icon: CheckSquare, labelKey: 'nav.tasks' },
      { to: '/check-ins', icon: UserCheck, labelKey: 'nav.checkIns' },
      { to: '/outreach', icon: Globe, labelKey: 'nav.outreach' },
      { to: '/comms', icon: Megaphone, labelKey: 'nav.comms' },
      { to: '/resources', icon: Building2, labelKey: 'nav.resources' },
      { to: '/access', icon: ScanLine, labelKey: 'nav.accessControl', roles: ['admin', 'system_admin', 'Executive Director', 'Director', 'Manager', 'Coordinator'] },
    ]
  },
  {
    label: 'Finance',
    items: [
      { to: '/financial', icon: DollarSign, labelKey: 'nav.financial', roles: ['admin', 'system_admin', 'Executive Director', 'Director', 'Manager'] },
      { to: '/sales', icon: ShoppingCart, labelKey: 'nav.sales' },
    ]
  },
  {
    label: 'Analytics',
    items: [
      { to: '/attendance', icon: UserCheck, labelKey: 'nav.attendance' },
      { to: '/sales-analytics', icon: TrendingUp, labelKey: 'nav.salesAnalytics', roles: ['admin', 'system_admin', 'Executive Director', 'Director', 'Manager'] },
      { to: '/location-analytics', icon: BarChart3, labelKey: 'nav.locationStats', roles: ['admin', 'system_admin', 'Executive Director', 'Director', 'Manager'] },
      { to: '/analytics', icon: PieChart, label: 'Advanced Analytics', roles: ['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director', 'Manager'] },
      { to: '/reports', icon: FileText, labelKey: 'nav.reports', roles: ['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director', 'Manager'] },
      { to: '/report-builder', icon: FileSpreadsheet, label: 'Report Builder', roles: ['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director', 'Manager'] },
      { to: '/campus-reports', icon: Building2, labelKey: 'nav.campusReports', roles: ['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director', 'Manager'] },
    ]
  },
  {
    label: 'Operations',
    items: [
      { to: '/volunteer-scheduling', icon: Clock, label: 'Volunteer Scheduling', roles: ['admin', 'system_admin', 'Executive Director', 'Director', 'Manager', 'Coordinator'] },
      { to: '/email-templates', icon: Mail, label: 'Email Templates', roles: ['admin', 'system_admin', 'Executive Director', 'Director', 'Manager'] },
    ]
  },
  {
    label: 'Calling',
    items: [
      { to: '/call-history', icon: PhoneCall, label: 'Call History' },
      { to: '/extensions', icon: Phone, label: 'Extensions', adminOnly: true },
      { to: '/pbx-settings', icon: Server, label: 'PBX Settings', adminOnly: true },
    ]
  },
  {
    label: 'Admin',
    items: [
      { to: '/admin', icon: Shield, labelKey: 'nav.admin', adminOnly: true },
      { to: '/locations', icon: MapPin, labelKey: 'nav.campuses', adminOnly: true },
      { to: '/financial-apis', icon: CreditCard, label: 'Financial APIs', adminOnly: true },
      { to: '/app-settings', icon: Sliders, labelKey: 'nav.appSettings', adminOnly: true },
      { to: '/audit', icon: Shield, labelKey: 'nav.audit', adminOnly: true },
      { to: '/gdpr', icon: Lock, label: 'Privacy & GDPR', adminOnly: true },
      { to: '/settings', icon: Settings, labelKey: 'nav.settings' },
    ]
  },
];

const notifTypeIcon = { error: '🔴', warning: '🟡', info: '🔵', success: '🟢' };

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
  const [darkMode, setDarkMode] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('5812_dark_mode') === 'true' || document.documentElement.classList.contains('dark');
    }
    return false;
  });
  const searchRef = useRef(null);
  const searchTimeout = useRef(null);
  
  // Call context for missed call badge
  let missedCallCount = 0;
  try {
    const callCtx = useCall();
    missedCallCount = callCtx?.missedCallCount || 0;
  } catch (e) {
    // CallContext not available
  }

  const toggleDarkMode = () => {
    const next = !darkMode;
    setDarkMode(next);
    localStorage.setItem('5812_dark_mode', String(next));
    document.documentElement.classList.toggle('dark', next);
  };

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
  }, []);

  const handleLogout = () => { logout(); navigate('/login'); };

  const initials = user?.name
    ? user.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
    : 'AU';

  const isAdmin = ['admin', 'system_admin'].includes(user?.role);
  const userRole = user?.role || '';
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const { addListener } = useWebSocket();
  const { t, lang, changeLang, languages } = useI18n();

  // Online/offline detection
  useEffect(() => {
    const goOnline = () => setIsOnline(true);
    const goOffline = () => { setIsOnline(false); toast.warning('You are offline. Some features may be limited.'); };
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    return () => { window.removeEventListener('online', goOnline); window.removeEventListener('offline', goOffline); };
  }, []);

  // Real-time WS notifications for guest approvals etc
  useEffect(() => {
    const unsub = addListener('notification', (data) => {
      setUnreadCount(prev => prev + 1);
      toast.info(data.title || 'New notification');
    });
    return unsub;
  }, [addListener]);

  // ---- Fetch notifications ----
  const fetchUnreadCount = useCallback(async () => {
    try {
      const res = await notificationsApi.unreadCount();
      setUnreadCount(res.data.count);
    } catch {}
  }, []);

  const fetchNotifs = async () => {
    try {
      const res = await notificationsApi.list();
      setNotifs(res.data);
      setUnreadCount(res.data.filter(n => !n.read).length);
    } catch {}
  };

  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 30000);
    return () => clearInterval(interval);
  }, [fetchUnreadCount]);

  const handleNotifOpen = () => {
    setNotifOpen(true);
    fetchNotifs();
  };

  const markAllRead = async () => {
    try {
      await notificationsApi.markAllRead();
      setNotifs(prev => prev.map(n => ({ ...n, read: true })));
      setUnreadCount(0);
    } catch {}
  };

  const markRead = async (id) => {
    try {
      await notificationsApi.markRead(id);
      setNotifs(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
      setUnreadCount(prev => Math.max(0, prev - 1));
    } catch {}
  };

  // ---- Global Search ----
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setSearchOpen(true);
      }
      if (e.key === 'Escape') setSearchOpen(false);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const handleSearch = (q) => {
    setSearchQuery(q);
    clearTimeout(searchTimeout.current);
    if (q.length < 2) { setSearchResults([]); return; }
    setSearching(true);
    searchTimeout.current = setTimeout(async () => {
      try {
        const res = await searchApi.query(q);
        setSearchResults(res.data.results || []);
      } catch {}
      finally { setSearching(false); }
    }, 300);
  };

  const resultTypeIcon = { member: '👤', event: '📅', task: '✓', product: '📦' };

  const handleResultClick = (result) => {
    setSearchOpen(false);
    setSearchQuery('');
    setSearchResults([]);
    navigate(result.url);
  };

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {sidebarOpen && (
        <div className="fixed inset-0 bg-black/30 z-20 lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Sidebar */}
      <aside className={`fixed lg:static inset-y-0 left-0 z-30 flex flex-col w-60 bg-card border-r border-border transform transition-transform duration-200 ease-in-out ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}>
        <div className="flex items-center gap-2 px-4 py-3.5 border-b border-border">
          <img
            src="https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1"
            alt="58:12 Global"
            className="h-7 w-auto object-contain"
          />
          <button className="lg:hidden ml-auto text-muted-foreground" onClick={() => setSidebarOpen(false)}>
            <X size={18} />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto py-2 px-2 space-y-0">
          {NAV_SECTIONS.map((section, si) => (
            <div key={si} className={si > 0 ? 'mt-4' : ''}>
              {(section.label || section.labelKey) && (
                <p className="text-xs font-semibold text-muted-foreground/60 uppercase tracking-wider px-3 mb-1">{section.labelKey ? t(section.labelKey) : section.label}</p>
              )}
              {section.items
                .filter(item => {
                  if (item.adminOnly && !isAdmin) return false;
                  if (item.roles && !item.roles.includes(userRole) && !isAdmin) return false;
                  return true;
                })
                .map(({ to, icon: Icon, labelKey, label }) => (
                  <NavLink
                    key={to}
                    to={to}
                    onClick={() => setSidebarOpen(false)}
                    className={({ isActive }) =>
                      `flex items-center gap-3 px-3 py-2 rounded-lg text-sm cursor-pointer sidebar-link transition-colors ${isActive ? 'sidebar-active bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground'}`
                    }
                    data-testid={`nav-${to.replace('/', '')}`}
                  >
                    <Icon size={15} className="shrink-0" />
                    {labelKey ? t(labelKey) : label}
                  </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="px-2 py-3 border-t border-border">
          <div className="flex items-center gap-2.5 px-2 py-2 rounded-lg">
            <Avatar className="h-8 w-8">
              <AvatarFallback className="bg-primary text-primary-foreground text-xs font-semibold">{initials}</AvatarFallback>
            </Avatar>
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
          <button className="lg:hidden text-muted-foreground p-1" onClick={() => setSidebarOpen(true)} data-testid="mobile-menu-btn">
            <Menu size={20} />
          </button>

          {/* Search trigger — icon only on mobile */}
          <button
            className="flex items-center gap-2 px-2 sm:px-3 py-1.5 rounded-lg bg-secondary/60 text-sm text-muted-foreground hover:bg-secondary transition-colors sm:flex-1 sm:max-w-64"
            onClick={() => setSearchOpen(true)}
            data-testid="global-search-trigger"
          >
            <Search size={13} />
            <span className="text-xs hidden sm:inline">Search... (Ctrl+K)</span>
          </button>

          <div className="flex-1" />

          {/* Call Button */}
          <Button
            variant="ghost"
            size="sm"
            className="h-9 w-9 p-0 text-green-600 hover:bg-green-100 dark:hover:bg-green-950"
            onClick={() => setDialerOpen(true)}
            data-testid="call-button"
          >
            <Phone size={18} />
          </Button>

          {/* Language Switcher */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="h-9 gap-1.5 text-xs px-2" data-testid="language-switcher">
                <Globe size={14} /> {languages.find(l => l.code === lang)?.name?.slice(0, 3) || 'EN'}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {languages.map(l => (
                <DropdownMenuItem key={l.code} onClick={() => changeLang(l.code)} className={lang === l.code ? 'font-semibold bg-accent' : ''} data-testid={`lang-${l.code}`}>
                  {l.name}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Online/Offline indicator */}
          {!isOnline && (
            <Badge variant="destructive" className="text-[10px] gap-1 h-6 px-2">
              <WifiOff size={11} /> Offline
            </Badge>
          )}

          {/* Dark Mode Toggle */}
          <Button variant="ghost" size="icon" className="h-9 w-9" onClick={toggleDarkMode} data-testid="dark-mode-toggle">
            {darkMode ? <Sun size={17} /> : <Moon size={17} />}
          </Button>

          {/* Notifications Bell */}
          <DropdownMenu open={notifOpen} onOpenChange={(v) => { if (v) handleNotifOpen(); else setNotifOpen(v); }}>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="relative h-9 w-9" data-testid="notification-bell">
                <Bell size={17} />
                {unreadCount > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 h-4 w-4 rounded-full bg-primary text-primary-foreground text-[9px] flex items-center justify-center font-bold">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-80 p-0" data-testid="notification-dropdown">
              <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                <p className="font-semibold text-sm">Notifications</p>
                {unreadCount > 0 && (
                  <Button variant="ghost" size="sm" className="h-7 text-xs gap-1" onClick={markAllRead} data-testid="mark-all-read">
                    <CheckCheck size={12} /> Mark all read
                  </Button>
                )}
              </div>
              <div className="max-h-80 overflow-y-auto">
                {notifs.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-6">No notifications</p>
                ) : notifs.map(n => (
                  <div
                    key={n.id}
                    onClick={() => { markRead(n.id); if (n.link) navigate(n.link); setNotifOpen(false); }}
                    className={`flex items-start gap-3 px-4 py-3 hover:bg-secondary/50 cursor-pointer border-b border-border/50 last:border-0 transition-colors ${!n.read ? 'bg-primary/5' : ''}`}
                    data-testid="notification-item"
                  >
                    <span className="mt-0.5 text-sm">{notifTypeIcon[n.type] || '🔵'}</span>
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-medium leading-tight ${!n.read ? 'text-foreground' : 'text-muted-foreground'}`}>{n.title}</p>
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
                <Avatar className="h-7 w-7">
                  <AvatarFallback className="bg-primary text-primary-foreground text-xs font-semibold">{initials}</AvatarFallback>
                </Avatar>
                <span className="text-sm font-medium hidden sm:block">{user?.name}</span>
                <ChevronDown size={13} className="text-muted-foreground" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <div className="px-2 py-1.5">
                <p className="text-sm font-medium">{user?.name}</p>
                <p className="text-xs text-muted-foreground capitalize">{user?.role}</p>
              </div>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <NavLink to="/settings" className="flex items-center gap-2 cursor-pointer">
                  <Settings size={14} /> Settings
                </NavLink>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <a href="/kiosk" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 cursor-pointer">
                  <ExternalLink size={14} /> Open Kiosk
                </a>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={handleLogout} className="text-destructive focus:text-destructive cursor-pointer">
                <LogOut size={14} className="mr-2" /> Sign Out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </header>

        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>

      {/* Global Search Dialog */}
      <Dialog open={searchOpen} onOpenChange={setSearchOpen}>
        <DialogContent className="max-w-lg p-0 gap-0" data-testid="search-dialog">
          <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
            <Search size={16} className="text-muted-foreground shrink-0" />
            <input
              ref={searchRef}
              autoFocus
              className="flex-1 bg-transparent outline-none text-sm placeholder:text-muted-foreground"
              placeholder="Search members, events, tasks, products..."
              value={searchQuery}
              onChange={e => handleSearch(e.target.value)}
              data-testid="search-input"
            />
            {searchQuery && <button className="text-muted-foreground hover:text-foreground" onClick={() => { setSearchQuery(''); setSearchResults([]); }}><X size={14} /></button>}
          </div>
          <div className="max-h-80 overflow-y-auto py-2">
            {searching && (
              <div className="px-4 py-3 text-sm text-muted-foreground">Searching...</div>
            )}
            {!searching && searchQuery.length >= 2 && searchResults.length === 0 && (
              <div className="px-4 py-6 text-sm text-muted-foreground text-center">No results found for "{searchQuery}"</div>
            )}
            {searchResults.map((r, i) => (
              <button
                key={i}
                className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-secondary/60 transition-colors text-left"
                onClick={() => handleResultClick(r)}
                data-testid="search-result"
              >
                <span className="text-sm">{resultTypeIcon[r.type]}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{r.title}</p>
                  <p className="text-xs text-muted-foreground truncate">{r.subtitle}</p>
                </div>
                <Badge variant="outline" className="text-xs capitalize shrink-0">{r.type}</Badge>
              </button>
            ))}
            {!searchQuery && (
              <div className="px-4 py-4 text-xs text-muted-foreground space-y-1">
                <p className="font-medium text-foreground mb-2">Quick Navigation</p>
                {['/dashboard', '/members', '/events', '/financial', '/sales', '/tasks'].map(path => (
                  <button key={path} className="flex items-center gap-2 hover:text-foreground transition-colors w-full text-left" onClick={() => { navigate(path); setSearchOpen(false); }}>
                    <span>→</span> {path.replace('/', '').replace('-', ' ').replace(/\b\w/g, l => l.toUpperCase()) || 'Dashboard'}
                  </button>
                ))}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Dialer Modal */}
      <Dialer open={dialerOpen} onClose={() => setDialerOpen(false)} />
    </div>
  );
}
