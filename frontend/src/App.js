import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { WebSocketProvider } from './context/WebSocketContext';
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
import AuthCallback from './pages/AuthCallback';
import Layout from './components/Layout';

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
      <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="members" element={<UnifiedPeoplePage />} />
        <Route path="events" element={<EventsPage />} />
        <Route path="tasks" element={<TasksPage />} />
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
      </Route>
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <AuthProvider>
      <WebSocketProvider>
        <BrowserRouter>
          <AppRoutes />
          <Toaster />
        </BrowserRouter>
      </WebSocketProvider>
    </AuthProvider>
  );
}

export default App;
