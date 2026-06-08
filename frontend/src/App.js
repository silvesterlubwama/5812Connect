import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { WebSocketProvider } from './context/WebSocketContext';
import { I18nProvider } from './context/I18nContext';
import { BrandingProvider } from './context/BrandingContext';
import { Toaster } from './components/ui/sonner';
import OfflineBanner from './components/OfflineBanner';
import './App.css';

import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import KioskPage from './pages/KioskPage';
import PublicBookingsPage from './pages/PublicBookingsPage';
import DashboardPage from './pages/DashboardPage';
import MembersPage from './pages/MembersPage';
// Lazy-load heavy pages — code-split per route so first load is small.
const UnifiedPeoplePage = lazy(() => import('./pages/UnifiedPeoplePage'));
const ProductsPage = lazy(() => import('./pages/ProductsPage'));
const FinancialPage = lazy(() => import('./pages/FinancialPage'));
const AccountingPage = lazy(() => import('./pages/AccountingPage'));
const SocialWorkPage = lazy(() => import('./pages/SocialWorkPage'));
import EventsPage from './pages/EventsPage';
import TasksPage from './pages/TasksPage';
import CalendarPage from './pages/CalendarPage';
import CheckInsPage from './pages/CheckInsPage';
import SettingsPage from './pages/SettingsPage';
import ApprovalsPage from './pages/ApprovalsPage';
import FundsPage from './pages/FundsPage';
import SchoolPortalPage from './pages/SchoolPortalPage';
import SponsorPortalPage from './pages/SponsorPortalPage';
import BankPage from './pages/BankPage';
import PeoplePage from './pages/PeoplePage';
import AuditPage from './pages/AuditPage';
import LocationsPage from './pages/LocationsPage';
import AttendancePage from './pages/AttendancePage';
import SalesAnalyticsPage from './pages/SalesAnalyticsPage';
import LocationAnalyticsPage from './pages/LocationAnalyticsPage';
import CommsPage from './pages/CommsPage';
import OutreachPage from './pages/OutreachPage';
import ResourcesPage from './pages/ResourcesPage';
import AccessPage from './pages/AccessPage';
import ReportsPage from './pages/ReportsPage';
import CampusReportsPage from './pages/CampusReportsPage';
import AdminPage from './pages/AdminPage';
import AppSettingsPage from './pages/AppSettingsPage';
import AuthCallback from './pages/AuthCallback';
import Layout from './components/Layout';
import PortalLayout from './components/PortalLayout';
import PortalDashboard from './pages/PortalDashboard';
import PortalTasks from './pages/PortalTasks';
import PortalExpenses from './pages/PortalExpenses';
import PortalEvents from './pages/PortalEvents';
import PortalProfile from './pages/PortalProfile';
import PortalDocuments from './pages/PortalDocuments';
import SharedBoardPage from './pages/SharedBoardPage';
import PortalSales from './pages/PortalSales';
import PortalFamily from './pages/PortalFamily';
// New Feature Pages
import AnalyticsPage from './pages/AnalyticsPage';
import ReportBuilderPage from './pages/ReportBuilderPage';
import VolunteerSchedulingPage from './pages/VolunteerSchedulingPage';
import EmailTemplatesPage from './pages/EmailTemplatesPage';
import FinancialApisPage from './pages/FinancialApisPage';
import GdprSettingsPage from './pages/GdprSettingsPage';
// Calling Feature Pages
import CallHistoryPage from './pages/CallHistoryPage';
import PbxSettingsPage from './pages/PbxSettingsPage';
// ExtensionsPage removed — PBX page handles extensions
// Calling Components
import { CallProvider } from './context/CallContext';
import CallInterface from './components/CallInterface';
import IncomingCallModal from './components/IncomingCallModal';
import WalletBadgePage from './pages/WalletBadgePage';
import ReceiptViewPage from './pages/ReceiptViewPage';
import ResourceViewPage from './pages/ResourceViewPage';
import PosKioskPage from './pages/PosKioskPage';
import PosKioskSetupPage from './pages/PosKioskSetupPage';
import QuoteAcceptPage from './pages/QuoteAcceptPage';
import AccountsReceivablePage from './pages/AccountsReceivablePage';
import BarcodeReissuePage from './pages/BarcodeReissuePage';
import ReconciliationReportsPage from './pages/ReconciliationReportsPage';
import CustomerStatementsPage from './pages/CustomerStatementsPage';
import HRPage from './pages/HRPage';
import SalesPortalPage from './pages/SalesPortalPage';
import SecurityCheckpointPage from './pages/SecurityCheckpointPage';
import { ErrorBoundary } from './components/ErrorBoundary';
import { StaffRoute } from './components/RouteGuards';

const KIOSK_ONLY_ROLES = new Set(['Security Contractor', 'security_contractor']);

const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent"></div>
    </div>
  );
  if (!user) return <Navigate to="/login" replace />;
  // Security Contractors are pinned to the checkpoint terminal — never the main app or portal.
  if (KIOSK_ONLY_ROLES.has(user.role)) return <Navigate to="/security-checkpoint" replace />;
  return children;
};

function AppRoutes() {
  const location = useLocation();
  // Check URL fragment for session_id from Google Auth callback
  if (location.hash?.includes('session_id=')) {
    return <AuthCallback />;
  }
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center bg-background"><div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" /></div>}>
      <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/kiosk" element={<KioskPage />} />
      <Route path="/public-bookings" element={<PublicBookingsPage />} />
      <Route path="/marketplace" element={<PublicBookingsPage />} />
      <Route path="/shared/:shareToken" element={<SharedBoardPage />} />
      <Route path="/badge/:token" element={<WalletBadgePage />} />
      <Route path="/receipt/:receiptNumber" element={<ReceiptViewPage />} />
      <Route path="/resource/:serial" element={<ResourceViewPage />} />
      <Route path="/quote/:quoteNumber/accept" element={<QuoteAcceptPage />} />
      <Route path="/school-portal/:portalToken" element={<SchoolPortalPage />} />
      <Route path="/sponsor-portal/:portalToken" element={<SponsorPortalPage />} />
      <Route path="/pos/:storeId" element={<PosKioskPage />} />
      <Route path="/sales-portal" element={<SalesPortalPage />} />
      <Route path="/security-checkpoint" element={<SecurityCheckpointPage />} />
      <Route path="/" element={<ProtectedRoute><StaffRoute><Layout /></StaffRoute></ProtectedRoute>}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="members" element={<UnifiedPeoplePage />} />
        <Route path="events" element={<EventsPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="boards" element={<TasksPage />} />
        <Route path="calendar" element={<CalendarPage />} />
        <Route path="check-ins" element={<CheckInsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="financial" element={<FinancialPage />} />
        <Route path="accounting" element={<AccountingPage />} />
        <Route path="approvals" element={<ApprovalsPage />} />
        <Route path="funds" element={<FundsPage />} />
        <Route path="social-work" element={<SocialWorkPage />} />
        <Route path="banking" element={<BankPage />} />
        <Route path="sales" element={<ProductsPage />} />
        <Route path="pos-setup" element={<PosKioskSetupPage />} />
        <Route path="accounts-receivable" element={<AccountsReceivablePage />} />
        <Route path="barcode-reissue" element={<BarcodeReissuePage />} />
        <Route path="reconciliation" element={<ReconciliationReportsPage />} />
        <Route path="customer-statements" element={<CustomerStatementsPage />} />
        <Route path="profile" element={<PortalProfile />} />
        <Route path="people" element={<UnifiedPeoplePage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="locations" element={<LocationsPage />} />
        <Route path="attendance" element={<AttendancePage />} />
        <Route path="sales-analytics" element={<SalesAnalyticsPage />} />
        <Route path="location-analytics" element={<LocationAnalyticsPage />} />
        <Route path="comms" element={<CommsPage />} />
        <Route path="outreach" element={<OutreachPage />} />
        <Route path="resources" element={<ResourcesPage />} />
        <Route path="access" element={<AccessPage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="campus-reports" element={<CampusReportsPage />} />
        <Route path="admin" element={<AdminPage />} />
        <Route path="app-settings" element={<AppSettingsPage />} />
        {/* New Feature Routes */}
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="report-builder" element={<ReportBuilderPage />} />
        <Route path="volunteer-scheduling" element={<VolunteerSchedulingPage />} />
        <Route path="email-templates" element={<EmailTemplatesPage />} />
        <Route path="financial-apis" element={<FinancialApisPage />} />
        <Route path="hr" element={<HRPage />} />
        <Route path="gdpr" element={<GdprSettingsPage />} />
        {/* Calling Feature Routes */}
        <Route path="call-history" element={<CallHistoryPage />} />
      </Route>
      {/* Staff/Member Self-Service Portal */}
      <Route path="/portal" element={<ProtectedRoute><PortalLayout /></ProtectedRoute>}>
        <Route index element={<PortalDashboard />} />
        <Route path="tasks" element={<PortalTasks />} />
        <Route path="chat" element={<CommsPage />} />
        <Route path="expenses" element={<PortalExpenses />} />
        <Route path="events" element={<PortalEvents />} />
        <Route path="sales" element={<PortalSales />} />
        <Route path="documents" element={<PortalDocuments />} />
        <Route path="family" element={<PortalFamily />} />
        <Route path="profile" element={<PortalProfile />} />
      </Route>
      <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </Suspense>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <I18nProvider>
        <BrandingProvider>
        <AuthProvider>
          <WebSocketProvider>
            <CallProvider>
              <BrowserRouter>
                <OfflineBanner />
                <ErrorBoundary>
                  <AppRoutes />
                </ErrorBoundary>
                <CallInterface />
                <IncomingCallModal />
                <Toaster />
              </BrowserRouter>
            </CallProvider>
          </WebSocketProvider>
        </AuthProvider>
        </BrandingProvider>
      </I18nProvider>
    </ErrorBoundary>
  );
}

export default App;
