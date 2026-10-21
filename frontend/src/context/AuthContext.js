import React, { createContext, useContext, useState, useEffect } from 'react';
import api, { authApi } from '../services/api';
import { secureStorage } from '../services/secureStorage';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (window.location.hash?.includes('session_id=')) {
      setLoading(false);
      return;
    }
    const token = secureStorage.getToken();
    if (token) {
      authApi.me()
        .then(res => setUser(res.data))
        .catch(() => secureStorage.clearAll())
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (identifier, password, totpCode = null) => {
    const payload = { identifier, password };
    if (totpCode) payload.totp_code = totpCode;
    const res = await authApi.login(identifier, password, totpCode);
    if (res.data.requires_2fa) {
      return { requires_2fa: true };
    }
    // A super admin signs in without being inside any organisation yet. The
    // token only unlocks the organisation picker until one is entered.
    if (res.data.requires_org_selection) {
      secureStorage.setToken(res.data.token);
      return { requires_org_selection: true, organizations: res.data.organizations || [] };
    }
    const { token, user: userData } = res.data;
    if (!token) throw new Error('Login failed');
    secureStorage.setToken(token);
    secureStorage.setUser(userData);
    setUser(userData);
    // Branding is per organisation, so re-read it for whoever just signed in.
    window.dispatchEvent(new Event('branding-refresh'));
    return { success: true, user: userData };
  };

  // Entering an organisation swaps the session for one scoped to that tenant.
  // Never additive: whatever was open before is left behind.
  const enterOrganization = async (orgId) => {
    const res = await api.post(`/organizations/${orgId}/enter`);
    secureStorage.setToken(res.data.token);
    const me = await authApi.me();
    secureStorage.setUser(me.data);
    setUser(me.data);
    window.dispatchEvent(new Event('branding-refresh'));
    return me.data;
  };

  const logout = async () => {
    try { await authApi.logout(); } catch (e) { console.warn(e.message || e); }
    secureStorage.clearAll();
    // Notify subscribers (softphone, click-to-call cache, etc.) that the
    // identity context has changed and they should refetch / clear.
    try { window.dispatchEvent(new Event('auth-changed')); } catch (_) {/* SSR safety */}
    setUser(null);
    window.dispatchEvent(new Event('branding-refresh'));
  };

  return (
    <AuthContext.Provider value={{ user, setUser, loading, login, logout, enterOrganization }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
};
