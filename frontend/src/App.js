import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { WebSocketProvider } from './context/WebSocketContext';
import { I18nProvider } from './context/I18nContext';
import { Toaster } from './components/ui/sonner';
import './App.css';

import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import KioskPage from './pages/KioskPage';
import PublicBookingsPage from './pages/PublicBookingsPage';
import DashboardPage from './pages/DashboardPage';
import MembersPage from './pages/MembersPage';
import UnifiedPeoplePage from './pages/UnifiedPeoplePage';
import EventsPage from './pages/EventsPage';
import TasksPage from './pages/TasksPage';
import CalendarPage from './pages/CalendarPage';
import CheckInsPage from './pages/CheckInsPage';
import SettingsPage from './pages/SettingsPage';
import FinancialPage from './pages/FinancialPage';
import ProductsPage from './pages/ProductsPage';
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

const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent"></div>
    </div>
  );
  if (!user) return <Navigate to="/login" replace />;
  return children;
};

function AppRoutes() {
  const location = useLocation();
  // Check URL fragment for session_id from Google Auth callback
  if (location.hash?.includes('session_id=')) {
    return <AuthCallback />;
  }
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/kiosk" element={<KioskPage />} />
      <Route path="/public-bookings" element={<PublicBookingsPage />} />
      <Route path="/marketplace" element={<PublicBookingsPage />} />
      <Route path="/shared/:shareToken" element={<SharedBoardPage />} />
      <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
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
        <Route path="sales" element={<ProductsPage />} />
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
  );
}

function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <WebSocketProvider>
          <CallProvider>
            <BrowserRouter>
              <AppRoutes />
              <CallInterface />
              <IncomingCallModal />
              <Toaster />
            </BrowserRouter>
          </CallProvider>
        </WebSocketProvider>
      </AuthProvider>
    </I18nProvider>
  );
}

export default App;
