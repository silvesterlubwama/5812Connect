import { secureStorage } from '../services/secureStorage';
import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
export default function AuthCallback() {
  const navigate = useNavigate();
  const { setUser: setAuthUser } = useAuth();
  const hasProcessed = useRef(false);
  const [problem, setProblem] = useState('');

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const hash = window.location.hash;
    const sessionId = new URLSearchParams(hash.substring(1)).get('session_id');

    if (!sessionId) {
      navigate('/login', { replace: true });
      return;
    }

    (async () => {
      try {
        const res = await api.post('/auth/google-session', { session_id: sessionId });
        const { token, user, pending_approval: pendingApproval } = res.data;
        window.history.replaceState(null, '', window.location.pathname);
        if (pendingApproval) {
          // A first-time Google visitor: the account exists but nobody has let
          // them in yet. Silently bouncing to the login page looked broken.
          setProblem('Your account has been created and is waiting for an administrator to approve it.');
          return;
        }
        secureStorage.setToken(token);
        if (setAuthUser) setAuthUser(user);
        navigate('/dashboard', { replace: true });
      } catch (err) {
        // Say why. This used to drop people back on the login page with no
        // explanation, which read as "Google sign-in is broken".
        setProblem(err.response?.data?.detail || 'Google sign-in could not be completed. Please try again.');
      }
    })();
  }, [navigate, setAuthUser]);

  if (problem) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background px-4">
        <div className="max-w-md text-center space-y-4" data-testid="google-signin-problem">
          <p className="text-sm text-foreground">{problem}</p>
          <button
            type="button"
            onClick={() => navigate('/login', { replace: true })}
            className="text-sm font-medium text-primary underline underline-offset-4"
            data-testid="google-signin-back"
          >
            Back to sign-in
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center">
        <div className="h-8 w-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        <p className="text-sm text-muted-foreground">Completing Google sign-in...</p>
      </div>
    </div>
  );
}
