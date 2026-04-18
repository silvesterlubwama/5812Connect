import React, { createContext, useContext, useState, useEffect } from 'react';
import { authApi } from '../services/api';
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

  const login = async (identifier, password) => {
    const res = await authApi.login(identifier, password);
    const { token, user: userData } = res.data;
    secureStorage.setToken(token);
    secureStorage.setUser(userData);
    setUser(userData);
    return { success: true };
  };

  const logout = async () => {
    try { await authApi.logout(); } catch (e) { console.warn(e.message || e); }
    secureStorage.clearAll();
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
