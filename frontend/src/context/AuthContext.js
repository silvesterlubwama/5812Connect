import React, { createContext, useContext, useState, useEffect } from 'react';
import { authApi } from '../services/api';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // CRITICAL: If returning from OAuth callback, skip the /me check.
    // AuthCallback will exchange the session_id and establish the session first.
    if (window.location.hash?.includes('session_id=')) {
      setLoading(false);
      return;
    }
    const token = localStorage.getItem('5812_token');
    if (token) {
      authApi.me()
        .then(res => setUser(res.data))
        .catch(() => {
          localStorage.removeItem('5812_token');
          localStorage.removeItem('5812_auth_user');
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (identifier, password) => {
    const res = await authApi.login(identifier, password);
    const { token, user: userData } = res.data;
    localStorage.setItem('5812_token', token);
    localStorage.setItem('5812_auth_user', JSON.stringify(userData));
    setUser(userData);
    return { success: true };
  };

  const logout = async () => {
    try { await authApi.logout(); } catch (e) { console.warn(e.message || e); }
    localStorage.removeItem('5812_token');
    localStorage.removeItem('5812_auth_user');
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, setUser, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
};
