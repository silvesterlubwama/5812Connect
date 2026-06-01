/**
 * SponsorPortalPage — public-facing view for child sponsors. Mirrors the
 * SchoolPortal pattern: portal_token URL + expiring one-time password.
 *
 * Lives at /sponsor-portal/:portalToken
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Heart, Lock, Clock, LogOut, AlertCircle, BookOpen, Camera, Award } from 'lucide-react';
import { toast } from 'sonner';
import EmptyState from '../components/EmptyState';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function SponsorPortalPage() {
  const { portalToken } = useParams();
  const [session, setSession] = useState(null);
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [loginError, setLoginError] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(null);

  useEffect(() => {
    if (!session) return;
    const tick = () => {
      const remaining = Math.max(0, Math.floor((new Date(session.expires_at).getTime() - Date.now()) / 1000));
      setSecondsLeft(remaining);
      if (remaining <= 0) {
        toast.error('Session expired — please log in again.');
        setSession(null);
      }
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [session]);

  const login = async (e) => {
    e?.preventDefault?.();
    if (!password.trim()) return;
    setSubmitting(true); setLoginError('');
    try {
      const r = await axios.post(`${API}/sponsor-portal/login`, {
        portal_token: portalToken, password: password.trim(),
      });
      setSession(r.data); setPassword('');
    } catch (err) {
      setLoginError(err.response?.data?.detail || 'Login failed');
    } finally { setSubmitting(false); }
  };

  const loadMe = useCallback(async () => {
    if (!session) return;
    setLoading(true);
    try {
      const r = await axios.get(`${API}/sponsor-portal/me`, {
        headers: { Authorization: `Bearer ${session.session_token}` },
      });
      setData(r.data);
    } catch (err) {
      if (err.response?.status === 401) setSession(null);
      else toast.error('Failed to load updates');
    } finally { setLoading(false); }
  }, [session]);
  useEffect(() => { loadMe(); }, [loadMe]);

  const logout = async () => {
    try {
      await axios.post(`${API}/sponsor-portal/logout`, {}, {
        headers: { Authorization: `Bearer ${session?.session_token}` },
      });
    } catch { /* ignore */ }
    setSession(null); setData(null);
  };

  const fmtSeconds = (s) => {
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  };

  // ---- LOGIN VIEW ----
  if (!session) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-gradient-to-br from-rose-50 to-amber-50 dark:from-slate-900 dark:to-slate-950">
        <Card className="w-full max-w-md rounded-2xl shadow-lg" data-testid="sponsor-portal-login">
          <CardHeader className="text-center">
            <div className="mx-auto h-12 w-12 rounded-full bg-rose-100 flex items-center justify-center mb-2">
              <Heart size={24} className="text-rose-600" />
            </div>
            <CardTitle>Sponsor Portal</CardTitle>
            <CardDescription>
              Enter the password your 58:12 social worker shared with you.
              <br />
              <span className="text-[10px] text-muted-foreground font-mono break-all mt-1 inline-block">{portalToken}</span>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={login} className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="password" className="text-xs">One-time Password</Label>
                <Input id="password" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="paste password here" autoFocus required data-testid="sponsor-pw-input" />
              </div>
              {loginError && (
                <div className="text-xs text-red-600 flex items-center gap-1.5 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/30 rounded p-2">
                  <AlertCircle size={12} /> {loginError}
                </div>
              )}
              <Button type="submit" className="w-full" disabled={submitting || !password.trim()} data-testid="sponsor-login-btn">
                <Lock size={14} className="mr-1.5" />
                {submitting ? 'Logging in...' : 'View Updates'}
              </Button>
              <p className="text-[10px] text-muted-foreground text-center pt-2">
                If your password has expired, please contact the 58:12 social work team.
              </p>
            </form>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ---- LOGGED IN ----
  if (loading || !data) {
    return <div className="min-h-screen p-6 space-y-3"><div className="h-32 bg-muted animate-pulse rounded-xl max-w-3xl mx-auto" />{[1,2,3].map(i=><div key={i} className="h-24 bg-muted animate-pulse rounded-xl max-w-3xl mx-auto" />)}</div>;
  }

  const { child, updates, sponsorship_ytd, sponsorship_history } = data;
  const dob = child.date_of_birth ? new Date(child.date_of_birth) : null;
  const age = dob ? Math.floor((Date.now() - dob.getTime()) / (1000 * 60 * 60 * 24 * 365.25)) : null;

  return (
    <div className="min-h-screen p-4 sm:p-6 bg-slate-50 dark:bg-slate-950">
      <div className="max-w-3xl mx-auto space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h1 className="text-xl font-bold flex items-center gap-2"><Heart size={20} className="text-rose-600" /> Sponsor Portal</h1>
          <div className="flex items-center gap-2">
            {secondsLeft !== null && <Badge variant="outline" className="gap-1 text-xs"><Clock size={11} /> {fmtSeconds(secondsLeft)} left</Badge>}
            <Button variant="outline" size="sm" onClick={logout} data-testid="sponsor-logout-btn"><LogOut size={13} className="mr-1" />Log out</Button>
          </div>
        </div>

        {/* Child summary card */}
        <Card className="rounded-2xl">
          <CardHeader className="flex flex-row items-center gap-4 space-y-0">
            {child.photo_url
              ? <img src={child.photo_url.startsWith('http') ? child.photo_url : `${BACKEND_URL}${child.photo_url}`} alt={child.name} className="h-20 w-20 rounded-full object-cover" />
              : <div className="h-20 w-20 rounded-full bg-rose-100 flex items-center justify-center text-3xl font-bold text-rose-600">{(child.name || '?').slice(0, 1)}</div>}
            <div className="flex-1">
              <CardTitle className="text-2xl" data-testid="sponsor-child-name">{child.name}</CardTitle>
              <CardDescription className="text-sm">
                {age != null && `${age} years old`}
                {child.grade && ` · Grade ${child.grade}`}
                {child.school_name && ` · ${child.school_name}`}
              </CardDescription>
              {child.case_summary && <p className="text-xs italic mt-1 text-muted-foreground">"{child.case_summary}"</p>}
            </div>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3">
            <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-900/30">
              <p className="text-[10px] uppercase text-emerald-700">Sponsorship YTD</p>
              <p className="text-xl font-bold text-emerald-700">{sponsorship_ytd?.toLocaleString() || 0}</p>
              <p className="text-[10px] text-muted-foreground">{sponsorship_history?.length || 0} payment(s) recorded</p>
            </div>
            {child.case_goals?.length > 0 && (
              <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/30">
                <p className="text-[10px] uppercase text-amber-700 flex items-center gap-1"><Award size={11} />Goals</p>
                {child.case_goals.slice(0, 2).map((g, i) => (
                  <div key={i} className="mt-1">
                    <p className="text-xs font-medium truncate">{g.goal}</p>
                    <div className="bg-muted rounded-full h-1 overflow-hidden mt-0.5">
                      <div className="bg-amber-500 h-1" style={{ width: `${Math.min(100, g.progress_pct || 0)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Updates feed */}
        <Card className="rounded-2xl">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2"><BookOpen size={16} />Recent Updates ({updates?.length || 0})</CardTitle>
            <CardDescription className="text-xs">Posts from our social workers and school partners about {child.name}.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {!updates || updates.length === 0 ? (
              <EmptyState compact icon={BookOpen} title="No updates yet" description="Our social workers will share photos and progress notes about your sponsored child here. Check back soon." testid="sponsor-updates-empty" />
            ) : updates.map(u => (
              <div key={u.id} className="border rounded-lg p-3" data-testid={`sponsor-update-${u.id}`}>
                <div className="flex items-center gap-2 mb-1">
                  <Badge variant="outline" className="text-[10px] capitalize">{u.kind?.replace('_', ' ')}</Badge>
                  <span className="text-[10px] text-muted-foreground">{u.created_at?.slice(0, 10)}</span>
                </div>
                {u.caption && <p className="text-sm whitespace-pre-wrap">{u.caption}</p>}
                {u.file_url && /\.(jpg|jpeg|png|gif|webp)$/i.test(u.file_url) ? (
                  <img src={u.file_url.startsWith('http') ? u.file_url : `${BACKEND_URL}${u.file_url}`} alt="" className="mt-2 rounded max-h-64" />
                ) : u.file_url && (
                  <a href={u.file_url.startsWith('http') ? u.file_url : `${BACKEND_URL}${u.file_url}`} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline mt-1 inline-block">
                    <Camera size={11} className="inline mr-1" />{u.file_name || 'Attachment'}
                  </a>
                )}
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Footer disclaimer */}
        <p className="text-[10px] text-muted-foreground text-center">
          Confidential — please don't share this URL or password. Contact the 58:12 social work team with any questions.
        </p>
      </div>
    </div>
  );
}
