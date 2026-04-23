// Navigation configuration — static campus isolation, no per-page switchers
import {
  LayoutDashboard, Users, Calendar, CheckSquare, CalendarDays,
  UserCheck, Settings, LogOut, Menu, X, Bell, ChevronDown, ChevronRight,
  DollarSign, ShoppingCart, Heart, MapPin, Shield, Search,
  User, ExternalLink, CheckCheck, BarChart3, Megaphone,
  Globe, Building2, TrendingUp, Sun, Moon, ScanLine, FileText, Wifi, WifiOff, CircleUser, Sliders,
  PieChart, FileSpreadsheet, Clock, Mail, CreditCard, Lock, Phone, PhoneCall, Voicemail, Server,
  MessageSquare
} from 'lucide-react';

// Role groups
export const ADMIN_ROLES = ['admin', 'system_admin'];
export const ED_PLUS = ['admin', 'system_admin', 'Executive Director'];
export const DIRECTOR_PLUS = [...ED_PLUS, 'Adviser', 'Director'];
export const MANAGER_PLUS = [...DIRECTOR_PLUS, 'Manager'];
export const COORDINATOR_PLUS = [...MANAGER_PLUS, 'Leader', 'Coordinator'];
export const STAFF_PLUS = [...COORDINATOR_PLUS, 'Staff', 'HR'];
export const ALL_STAFF = [...STAFF_PLUS, 'Volunteer'];

export const NAV_SECTIONS = [
  {
    label: null,
    items: [
      { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
    ]
  },
  {
    label: 'Ministry',
    collapsible: true,
    items: [
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
      { to: '/members', icon: Users, label: 'Staff & People', roles: STAFF_PLUS },
      { to: '/volunteer-scheduling', icon: Clock, label: 'Scheduling', roles: COORDINATOR_PLUS },
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
    roles: MANAGER_PLUS,
    items: [
      { to: '/financial', icon: DollarSign, label: 'Financial' },
      { to: '/sales', icon: ShoppingCart, label: 'Marketplace' },
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
      { to: '/locations', icon: MapPin, label: 'Campuses' },
      { to: '/financial-apis', icon: CreditCard, label: 'Financial APIs', roles: ADMIN_ROLES },
      { to: '/email-templates', icon: Mail, label: 'Email Templates' },
      { to: '/settings', icon: Settings, label: 'Settings' },
      { to: '/audit', icon: Shield, label: 'Audit Trail' },
      { to: '/gdpr', icon: Lock, label: 'Privacy & GDPR' },
    ]
  },
];
