/**
 * Security Checkpoint Kiosk — public-facing lockable terminal.
 *
 * Single route `/security-checkpoint` with three view-states:
 *   1. PAIR     — enter 6-digit PIN + pick mode (guest|security)
 *   2. GUEST    — large-format approval display; auto-resets after 15s
 *   3. SECURITY — operator console: live event, scan history, one-time-grant flow
 *
 * Session token persists in localStorage so the device can be locked + power-cycled
 * without re-pairing (TTL = 12h on the backend).
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ShieldCheck, ShieldX, ScanLine, KeyRound, LogOut, Lock, Unlock, Clock, Camera, X, AlertTriangle, CheckCircle, History, UserPlus, Receipt, Search, Users as UsersIcon } from 'lucide-react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { securityCheckpointApi, badgesApi, locationsApi } from '../services/api';
import { toast } from 'sonner';
import PeripheralPermissionBanner from '../components/PeripheralPermissionBanner';

const POLL_MS = 1500;

const decisionStyles = {
  approved: { bg: 'bg-emerald-500', text: 'text-white', icon: ShieldCheck, label: 'APPROVED' },
  denied:   { bg: 'bg-rose-600',    text: 'text-white', icon: ShieldX,    label: 'DENIED'   },
  unknown:  { bg: 'bg-amber-500',   text: 'text-white', icon: AlertTriangle, label: 'UNKNOWN' },
  pending:  { bg: 'bg-slate-500',   text: 'text-white', icon: Clock,      label: 'PENDING'  },
};

const _loadSession = () => {
  try {
    return {
      token: localStorage.getItem('checkpoint_session') || '',
      mode: localStorage.getItem('checkpoint_mode') || '',
      checkpoint: JSON.parse(localStorage.getItem('checkpoint_meta') || 'null'),
    };
  } catch { return { token: '', mode: '', checkpoint: null }; }
};

const _saveSession = (token, mode, checkpoint) => {
  localStorage.setItem('checkpoint_session', token);
  localStorage.setItem('checkpoint_mode', mode);
  localStorage.setItem('checkpoint_meta', JSON.stringify(checkpoint));
};

const _clearSession = () => {
  localStorage.removeItem('checkpoint_session');
  localStorage.removeItem('checkpoint_mode');
  localStorage.removeItem('checkpoint_meta');
};

export default function SecurityCheckpointPage() {
  const [{ token, mode, checkpoint }, setSession] = useState(_loadSession());
  const [locked, setLocked] = useState(false);

  if (!token) return <PairView onPaired={(t, m, cp) => { _saveSession(t, m, cp); setSession({ token: t, mode: m, checkpoint: cp }); }} />;
  if (locked) return <LockScreen onUnlock={() => setLocked(false)} />;
  const unpair = async () => {
    try { await securityCheckpointApi.unpair(); } catch { /* ignore */ }
    _clearSession();
    setSession({ token: '', mode: '', checkpoint: null });
  };
  if (mode === 'guest') return <GuestView checkpoint={checkpoint} onUnpair={unpair} onLock={() => setLocked(true)} />;
  return <SecurityView checkpoint={checkpoint} onUnpair={unpair} onLock={() => setLocked(true)} />;
}

// ============================================================
// PAIR — entry screen
// ============================================================
function PairView({ onPaired }) {
  const [pin, setPin] = useState('');
  const [mode, setMode] = useState('');
  const [label, setLabel] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e?.preventDefault?.();
    if (pin.length !== 6 || !mode) { toast.error('Enter the 6-digit PIN and pick a mode'); return; }
    setSubmitting(true);
    try {
      const r = await securityCheckpointApi.pair({ pin, mode, device_label: label });
      toast.success(`Paired as ${mode === 'guest' ? 'Guest display' : 'Security console'}`);
      onPaired(r.data.session_token, r.data.mode, r.data.checkpoint);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Pairing failed');
    } finally { setSubmitting(false); }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-slate-100 flex items-center justify-center p-6">
      <Card className="w-full max-w-md rounded-2xl shadow-2xl border-slate-700/40 bg-slate-900/70 backdrop-blur">
        <CardContent className="p-7 space-y-5">
          <div className="text-center space-y-1">
            <div className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-500/15 text-emerald-400 mb-2">
              <ShieldCheck size={28} />
            </div>
            <h1 className="text-xl font-bold">Security Checkpoint</h1>
            <p className="text-xs text-slate-400">Enter the 6-digit pairing PIN provided by your administrator.</p>
          </div>
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs text-slate-300">Pairing PIN</Label>
              <Input
                inputMode="numeric"
                maxLength={6}
                autoFocus
                value={pin}
                onChange={e => setPin(e.target.value.replace(/\D/g, '').slice(0, 6))}
                className="text-center text-2xl tracking-[0.6em] font-mono h-14 bg-slate-800 border-slate-700 text-slate-100"
                data-testid="cp-pair-pin"
                placeholder="••••••"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-slate-300">This device is</Label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  className={`p-3 rounded-xl border text-left transition-colors ${mode === 'guest' ? 'border-emerald-500 bg-emerald-500/10 text-emerald-300' : 'border-slate-700 bg-slate-800/50 text-slate-300 hover:border-slate-600'}`}
                  onClick={() => setMode('guest')}
                  data-testid="cp-pair-mode-guest"
                >
                  <p className="font-semibold text-sm">Guest Display</p>
                  <p className="text-[10px] opacity-75 mt-0.5">Faces the visitor</p>
                </button>
                <button
                  type="button"
                  className={`p-3 rounded-xl border text-left transition-colors ${mode === 'security' ? 'border-emerald-500 bg-emerald-500/10 text-emerald-300' : 'border-slate-700 bg-slate-800/50 text-slate-300 hover:border-slate-600'}`}
                  onClick={() => setMode('security')}
                  data-testid="cp-pair-mode-security"
                >
                  <p className="font-semibold text-sm">Security Console</p>
                  <p className="text-[10px] opacity-75 mt-0.5">Contractor operator</p>
                </button>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-slate-300">Device label <span className="text-slate-500">(optional)</span></Label>
              <Input
                value={label}
                onChange={e => setLabel(e.target.value)}
                className="bg-slate-800 border-slate-700 text-slate-100"
                placeholder="e.g. North Gate Tablet"
              />
            </div>
            <Button type="submit" disabled={submitting || pin.length !== 6 || !mode} className="w-full h-11 bg-emerald-600 hover:bg-emerald-500" data-testid="cp-pair-submit">
              {submitting ? 'Pairing…' : 'Pair Device'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

// ============================================================
// LOCK — temporary lock screen (re-uses pairing PIN)
// ============================================================
function LockScreen({ onUnlock }) {
  const [pin, setPin] = useState('');
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-6" data-testid="cp-lock-screen">
      <Card className="w-full max-w-sm rounded-2xl border-slate-700/40 bg-slate-900/80">
        <CardContent className="p-6 space-y-4 text-center">
          <Lock size={36} className="mx-auto text-slate-400" />
          <h2 className="font-semibold">Device Locked</h2>
          <Input
            inputMode="numeric"
            maxLength={6}
            value={pin}
            onChange={e => setPin(e.target.value.replace(/\D/g, '').slice(0, 6))}
            placeholder="Pairing PIN"
            className="text-center text-2xl tracking-[0.6em] font-mono h-12 bg-slate-800 border-slate-700"
            autoFocus
            data-testid="cp-lock-pin"
          />
          <Button
            className="w-full bg-emerald-600 hover:bg-emerald-500"
            disabled={pin.length !== 6}
            onClick={async () => {
              try {
                // Verify by attempting to call /state — but we don't actually rotate session here.
                // The lock is local-only; PIN check happens against the active checkpoint via re-pair.
                const r = await securityCheckpointApi.pair({ pin, mode: 'guest', device_label: 'lock-test' });
                if (r.data.checkpoint?.id) { onUnlock(); }
              } catch (e) {
                toast.error(e.response?.data?.detail || 'Wrong PIN');
              }
            }}
            data-testid="cp-lock-unlock"
          >
            <Unlock size={14} className="mr-2" /> Unlock
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

// ============================================================
// GUEST — large display facing the visitor
// ============================================================
function GuestView({ checkpoint, onUnpair, onLock }) {
  const [current, setCurrent] = useState(null);
  const [serverNow, setServerNow] = useState(null);
  const nfcRef = useRef(null);
  const keystrokeBuffer = useRef('');
  const keystrokeTimer = useRef(null);

  // Poll backend state (fallback when WebSocket isn't available)
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const r = await securityCheckpointApi.state();
        if (!alive) return;
        setCurrent(r.data.current);
        setServerNow(r.data.now);
      } catch { /* tolerate transient errors */ }
    };
    tick();
    const iv = setInterval(tick, POLL_MS);
    return () => { alive = false; clearInterval(iv); };
  }, []);

  // Real-time WebSocket push (instant) — falls back to polling above if it fails.
  useEffect(() => {
    const token = localStorage.getItem('checkpoint_session');
    if (!token || typeof WebSocket === 'undefined') return;
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const base = process.env.REACT_APP_BACKEND_URL || window.location.origin;
    const wsUrl = `${base.replace(/^https?:/, proto)}/api/security/checkpoint/ws?session=${encodeURIComponent(token)}`;
    let ws;
    try {
      ws = new WebSocket(wsUrl);
      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          if (msg.type === 'event' && msg.event) {
            setCurrent(msg.event);
            setServerNow(new Date().toISOString());
          } else if (msg.type === 'clear') {
            setCurrent(null);
          }
        } catch { /* ignore */ }
      };
      ws.onerror = () => { /* fall back to polling silently */ };
    } catch { /* ignore */ }
    return () => { try { ws?.close(); } catch { /* ignore */ } };
  }, []);

  // Keyboard-emulating barcode scanner: capture rapid keystrokes ending in Enter
  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Enter') {
        const payload = keystrokeBuffer.current.trim();
        keystrokeBuffer.current = '';
        if (payload.length >= 3) submitScan('qr', payload);
        return;
      }
      if (e.key.length === 1) {
        keystrokeBuffer.current += e.key;
        clearTimeout(keystrokeTimer.current);
        keystrokeTimer.current = setTimeout(() => { keystrokeBuffer.current = ''; }, 250);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  // Web NFC — best-effort (Android Chrome only)
  useEffect(() => {
    if (typeof window === 'undefined' || !('NDEFReader' in window)) return;
    let reader;
    (async () => {
      try {
        reader = new window.NDEFReader();
        await reader.scan();
        reader.onreading = (ev) => {
          const dec = new TextDecoder();
          for (const rec of ev.message.records || []) {
            try {
              const data = dec.decode(rec.data);
              if (data) { submitScan('nfc', data); break; }
            } catch { /* ignore */ }
          }
        };
        nfcRef.current = reader;
      } catch (e) { console.warn('NFC unavailable:', e.message || e); }
    })();
    return () => { /* NDEFReader auto-cleans */ };
  }, []);

  const submitScan = async (scan_type, payload) => {
    try {
      const r = await securityCheckpointApi.scan({ scan_type, payload });
      setCurrent(r.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Scan failed');
    }
  };

  const tap = () => {
    securityCheckpointApi.finish().catch(() => {});
    setCurrent(null);
  };

  // Auto-clear on the client when clear_at expires (in case backend hasn't been polled yet)
  useEffect(() => {
    if (!current?.clear_at || !serverNow) return;
    const remain = new Date(current.clear_at).getTime() - new Date(serverNow).getTime();
    if (remain <= 0) { setCurrent(null); return; }
    const t = setTimeout(() => setCurrent(null), remain);
    return () => clearTimeout(t);
  }, [current?.clear_at, serverNow]);

  const decision = current?.decision || 'pending';
  const style = decisionStyles[decision] || decisionStyles.pending;
  const Icon = style.icon;
  const subject = current?.subject || {};

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col" data-testid="cp-guest-view">
      <header className="flex items-center justify-between px-6 py-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <ShieldCheck size={18} className="text-emerald-400" />
          <span className="text-sm font-semibold">{checkpoint?.name}</span>
          <span className="text-[11px] text-slate-500">· {checkpoint?.location_name}</span>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" className="text-slate-300 hover:text-slate-100" onClick={onLock} data-testid="cp-lock-btn"><Lock size={14} /></Button>
          <Button size="sm" variant="ghost" className="text-slate-400" onClick={onUnpair} data-testid="cp-unpair"><LogOut size={14} /></Button>
        </div>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center p-8 cursor-pointer" onClick={current ? tap : undefined}>
        {/* Peripheral permission banner — silent probe on mount + explicit Enable buttons */}
        <div className="w-full max-w-xl mb-4" onClick={e => e.stopPropagation()}>
          <PeripheralPermissionBanner needs={['camera', 'nfc', 'scanner']} context="this checkpoint" testid="cp-guest-perm-banner" />
        </div>
        {!current ? (
          <div className="text-center space-y-5">
            <div className="inline-flex h-32 w-32 items-center justify-center rounded-full bg-slate-800/70 border-2 border-dashed border-slate-700">
              <ScanLine size={56} className="text-slate-400" />
            </div>
            <h2 className="text-3xl font-bold">Tap your badge or scan your QR</h2>
            <p className="text-sm text-slate-400 max-w-md">Hold your NFC badge to the reader, or scan your QR code with the barcode scanner. The system will identify you automatically.</p>
          </div>
        ) : (
          <div className="text-center space-y-6 w-full max-w-2xl">
            <div className={`inline-flex h-36 w-36 items-center justify-center rounded-full ${style.bg} ${style.text} shadow-2xl`} data-testid="cp-decision-badge">
              <Icon size={72} />
            </div>
            <h2 className={`text-5xl font-extrabold ${decision === 'approved' ? 'text-emerald-400' : decision === 'denied' ? 'text-rose-400' : 'text-amber-400'}`}>
              {style.label}
            </h2>
            {subject?.photo_url && (
              <img src={subject.photo_url.startsWith('http') ? subject.photo_url : `${process.env.REACT_APP_BACKEND_URL}${subject.photo_url}`}
                   alt="" className="h-32 w-32 rounded-full object-cover mx-auto border-4 border-slate-700" />
            )}
            <div className="space-y-1">
              <p className="text-3xl font-bold" data-testid="cp-subject-name">{subject.name || 'Unknown'}</p>
              {subject.role && <p className="text-sm text-slate-400">{subject.role}</p>}
            </div>
            <p className="text-sm text-slate-300 italic">{current.reason}</p>
            <p className="text-[11px] text-slate-500">Tap anywhere to finish, or auto-clears in {Math.max(0, Math.ceil((new Date(current.clear_at).getTime() - Date.now()) / 1000))}s</p>
          </div>
        )}
      </main>
    </div>
  );
}

// ============================================================
// SECURITY — operator console
// ============================================================
function SecurityView({ checkpoint, onUnpair, onLock }) {
  const [state, setState] = useState({ current: null, history: [], now: null });
  const [showGrant, setShowGrant] = useState(false);
  const [showReceipt, setShowReceipt] = useState(false);
  const [showLogbook, setShowLogbook] = useState(false);
  const [showLookup, setShowLookup] = useState(false);
  const [openOneTime, setOpenOneTime] = useState([]);
  const isSingleDevice = checkpoint?.device_mode === 'single_device';

  // Poll (fallback)
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const [s, ot] = await Promise.all([
          securityCheckpointApi.state(),
          securityCheckpointApi.openOneTime().catch(() => ({ data: [] })),
        ]);
        if (!alive) return;
        setState(s.data);
        setOpenOneTime(ot.data || []);
      } catch { /* ignore */ }
    };
    tick();
    const iv = setInterval(tick, POLL_MS);
    return () => { alive = false; clearInterval(iv); };
  }, []);

  // Real-time WebSocket push (instant) — keeps polling alive as a safety net.
  useEffect(() => {
    const token = localStorage.getItem('checkpoint_session');
    if (!token || typeof WebSocket === 'undefined') return;
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const base = process.env.REACT_APP_BACKEND_URL || window.location.origin;
    const wsUrl = `${base.replace(/^https?:/, proto)}/api/security/checkpoint/ws?session=${encodeURIComponent(token)}`;
    let ws;
    try {
      ws = new WebSocket(wsUrl);
      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          if (msg.type === 'event' && msg.event) {
            setState(prev => ({
              ...prev,
              current: msg.event,
              history: [msg.event, ...(prev.history || []).slice(0, 19)],
            }));
          } else if (msg.type === 'clear') {
            setState(prev => ({ ...prev, current: null }));
          }
        } catch { /* ignore */ }
      };
      ws.onerror = () => { /* polling will cover */ };
    } catch { /* ignore */ }
    return () => { try { ws?.close(); } catch { /* ignore */ } };
  }, []);

  const finish = async () => {
    try { await securityCheckpointApi.finish(); setState(prev => ({ ...prev, current: null })); }
    catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  // Issue a wallet badge for the current subject if they don't have one, then open
  // the printable badge in a popup and trigger window.print().
  const [issuing, setIssuing] = useState(false);
  const issueAndPrintBadge = async () => {
    const subject = cur?.subject;
    if (!subject?.id || !subject?.kind) return;
    setIssuing(true);
    try {
      const r = await badgesApi.autoIssue(subject.kind, subject.id);
      const badge = r.data;
      toast.success(badge.was_created ? `Badge issued + queued for print: ${badge.name}` : `Existing badge re-printed: ${badge.name}`);
      const base = process.env.REACT_APP_BACKEND_URL || window.location.origin;
      // Open in a new window so the popup print doesn't blow away the security console
      const url = `${base}/badge/${badge.token}?print=1`;
      const popup = window.open(url, 'badge_print', 'width=420,height=640');
      if (popup) {
        // Best effort — the badge page itself reads ?print=1 and auto-fires window.print()
        setTimeout(() => { try { popup.focus(); } catch { /* ignore */ } }, 500);
      } else {
        toast.info('Pop-up blocked — open it manually from the link in the dialog');
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to issue badge');
    } finally { setIssuing(false); }
  };

  const returnId = async (grantId) => {
    try {
      await securityCheckpointApi.returnId(grantId);
      toast.success('ID marked returned');
      setOpenOneTime(prev => prev.filter(o => o.id !== grantId));
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const cur = state.current;
  const decision = cur?.decision;
  const style = cur ? (decisionStyles[decision] || decisionStyles.pending) : null;
  const Icon = style?.icon || ScanLine;
  const subject = cur?.subject || {};

  return (
    <div className="min-h-screen bg-slate-100 dark:bg-slate-900 text-slate-900 dark:text-slate-100" data-testid="cp-security-view">
      <header className="bg-slate-900 text-slate-100 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck size={18} className="text-emerald-400" />
          <div>
            <p className="text-sm font-semibold">{checkpoint?.name} — Security Console</p>
            <p className="text-[11px] text-slate-400">{checkpoint?.location_name}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" className="bg-slate-800 border-slate-700 text-slate-100 hover:bg-slate-700" onClick={() => setShowLookup(true)} data-testid="cp-lookup-open"><Search size={14} className="mr-1" /> Lookup / Household</Button>
          <Button size="sm" variant="outline" className="bg-slate-800 border-slate-700 text-slate-100 hover:bg-slate-700" onClick={() => setShowLogbook(true)} data-testid="cp-logbook-open"><History size={14} className="mr-1" /> Logbook</Button>
          <Button size="sm" variant="outline" className="bg-slate-800 border-slate-700 text-slate-100 hover:bg-slate-700" onClick={() => setShowGrant(true)} data-testid="cp-grant-open"><UserPlus size={14} className="mr-1" /> One-Time Entry</Button>
          <Button size="sm" variant="outline" className="bg-slate-800 border-slate-700 text-slate-100 hover:bg-slate-700" onClick={() => setShowReceipt(true)} data-testid="cp-receipt-open"><Receipt size={14} className="mr-1" /> Receipt Exit-Scan</Button>
          <Button size="sm" variant="ghost" className="text-slate-300" onClick={onLock}><Lock size={14} /></Button>
          <Button size="sm" variant="ghost" className="text-slate-400" onClick={onUnpair}><LogOut size={14} /></Button>
        </div>
      </header>

      <div className="grid lg:grid-cols-3 gap-4 p-4">
        {/* CURRENT SCAN */}
        <div className="lg:col-span-2 space-y-4">
          <PeripheralPermissionBanner needs={['camera']} context="the security console" testid="cp-security-perm-banner" />
          <Card className="rounded-xl">
            <CardContent className="p-5">
              <h3 className="font-semibold text-sm mb-3 flex items-center gap-2"><ScanLine size={14} /> Live Scan</h3>
              {!cur ? (
                <div className="py-16 text-center text-slate-500 dark:text-slate-400">
                  <ScanLine size={48} className="mx-auto opacity-30 mb-3" />
                  <p className="text-sm">Waiting for the next scan…</p>
                  <p className="text-[11px] mt-1">
                    {isSingleDevice
                      ? 'Scan a visitor\'s badge, QR, event ticket, or receipt via the reader attached to this device.'
                      : 'Guest device handles NFC/QR pickup. Scans appear here within a second.'}
                  </p>
                </div>
              ) : (
                <div className="flex items-start gap-5">
                  <div className={`h-24 w-24 shrink-0 rounded-full flex items-center justify-center ${style.bg} ${style.text}`}>
                    <Icon size={42} />
                  </div>
                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex items-center gap-2">
                      <Badge className={`${style.bg} ${style.text} text-[10px]`}>{style.label}</Badge>
                      <Badge variant="outline" className="text-[10px] capitalize">{cur.kind?.replace('_', ' ')}</Badge>
                      <span className="text-[10px] text-slate-500">{cur.scan_type}</span>
                    </div>
                    <p className="text-lg font-bold">{subject.name || 'Unknown subject'}</p>
                    {subject.role && <p className="text-xs text-slate-500">{subject.role}{subject.email ? ` · ${subject.email}` : ''}</p>}
                    {subject.phone && <p className="text-xs text-slate-500">📞 {subject.phone}</p>}
                    <p className="text-sm italic text-slate-700 dark:text-slate-300 mt-2">{cur.reason}</p>
                    <div className="flex gap-2 pt-2 flex-wrap">
                      <Button size="sm" variant="outline" onClick={finish} data-testid="cp-finish-btn"><X size={13} className="mr-1" /> Clear</Button>
                      {decision === 'approved' && ['member', 'child', 'guest', 'user'].includes(subject.kind) && (
                        <Button size="sm" variant="outline" disabled={issuing} onClick={issueAndPrintBadge} data-testid="cp-issue-badge-btn">
                          {issuing ? 'Printing…' : '🖨️ Issue + Print Badge'}
                        </Button>
                      )}
                      {decision === 'denied' && (
                        <Button size="sm" className="bg-amber-500 hover:bg-amber-400 text-slate-900" onClick={() => setShowGrant(true)} data-testid="cp-grant-from-denied">
                          <UserPlus size={13} className="mr-1" /> Grant one-time entry instead
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* HISTORY */}
          <Card className="rounded-xl">
            <CardContent className="p-5">
              <h3 className="font-semibold text-sm mb-3 flex items-center gap-2"><History size={14} /> Recent activity</h3>
              {state.history.length === 0 ? (
                <p className="text-xs text-slate-500 text-center py-6">No events yet today.</p>
              ) : (
                <div className="space-y-1.5 max-h-96 overflow-y-auto">
                  {state.history.map(ev => {
                    const sty = decisionStyles[ev.decision] || decisionStyles.pending;
                    return (
                      <div key={ev.id} className="flex items-center gap-3 text-xs p-2 rounded border bg-slate-50 dark:bg-slate-800/50">
                        <Badge className={`${sty.bg} ${sty.text} text-[10px]`}>{sty.label}</Badge>
                        <span className="flex-1 min-w-0 truncate">
                          <span className="font-medium">{ev.subject?.name || ev.payload || 'Unknown'}</span>
                          <span className="text-slate-500"> · {ev.reason}</span>
                        </span>
                        <span className="text-[10px] text-slate-500 shrink-0">{ev.created_at?.slice(11, 16)}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* OPEN ONE-TIME ENTRIES */}
        <Card className="rounded-xl h-fit">
          <CardContent className="p-5">
            <h3 className="font-semibold text-sm mb-3 flex items-center gap-2">
              <Clock size={14} className="text-amber-500" /> Holding {openOneTime.length} ID{openOneTime.length === 1 ? '' : 's'}
            </h3>
            {openOneTime.length === 0 ? (
              <p className="text-xs text-slate-500 text-center py-6">No physical IDs currently held.</p>
            ) : (
              <div className="space-y-2">
                {openOneTime.map(o => (
                  <div key={o.id} className="p-2 rounded border bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900/40" data-testid={`cp-otg-${o.id}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium">{o.name}</p>
                        <p className="text-[10px] text-slate-500">{o.phone || '—'}</p>
                        <p className="text-[10px] text-slate-500 italic">{o.reason}</p>
                        {o.id_image_url && (
                          <a href={o.id_image_url.startsWith('http') ? o.id_image_url : `${process.env.REACT_APP_BACKEND_URL}${o.id_image_url}`}
                             target="_blank" rel="noopener noreferrer"
                             className="text-[10px] text-emerald-700 dark:text-emerald-400 hover:underline inline-flex items-center gap-1 mt-1">
                            <Camera size={10} /> ID photo
                          </a>
                        )}
                      </div>
                      <Button size="sm" className="h-7 text-[11px]" onClick={() => returnId(o.id)} data-testid={`cp-return-${o.id}`}>
                        <CheckCircle size={11} className="mr-1" /> Return ID
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ONE-TIME GRANT DIALOG */}
      <OneTimeGrantDialog open={showGrant} onClose={() => setShowGrant(false)} requireId={checkpoint?.requires_id_for_one_time !== false} />

      {/* RECEIPT EXIT SCAN DIALOG */}
      <ReceiptScanDialog open={showReceipt} onClose={() => setShowReceipt(false)} />

      {/* VISITOR LOGBOOK (today's entries + exits) */}
      <LogbookDialog open={showLogbook} onClose={() => setShowLogbook(false)} />

      {/* HOUSEHOLD LOOKUP — phone / first name → multi-select household members */}
      <LookupDialog open={showLookup} onClose={() => setShowLookup(false)} singleDevice={isSingleDevice} />
    </div>
  );
}

// ----- one-time grant dialog -----
function OneTimeGrantDialog({ open, onClose, requireId }) {
  const [form, setForm] = useState({ name: '', phone: '', reason: '' });
  const [file, setFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [ocring, setOcring] = useState(false);
  const [ocrResult, setOcrResult] = useState(null);
  const camRef = useRef(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const [streaming, setStreaming] = useState(false);

  // Reset on close
  useEffect(() => { if (!open) { setForm({ name: '', phone: '', reason: '' }); setFile(null); setOcrResult(null); stopCam(); } }, [open]);

  const runOcr = async (blob) => {
    setOcring(true); setOcrResult(null);
    try {
      const fd = new FormData();
      fd.append('image', blob);
      const r = await securityCheckpointApi.ocrId(fd);
      const d = r.data || {};
      setOcrResult(d);
      // Soft auto-fill — only populate empty fields, never overwrite typed values
      setForm(prev => ({
        name: prev.name || d.name || '',
        phone: prev.phone,
        reason: prev.reason,
      }));
      if (d.name) toast.success(`OCR: detected "${d.name}" (${d.confidence})`);
      else toast.info('OCR could not extract a name — please type it manually');
    } catch (e) {
      // OCR failure is non-blocking; operator can still type manually
      toast.error(e.response?.data?.detail || 'OCR unavailable — type details manually');
    } finally { setOcring(false); }
  };

  const startCam = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
      camRef.current = stream;
      if (videoRef.current) { videoRef.current.srcObject = stream; videoRef.current.play(); }
      setStreaming(true);
    } catch (e) { toast.error(e.message || 'Camera unavailable'); }
  }, []);

  const stopCam = () => {
    if (camRef.current) {
      camRef.current.getTracks().forEach(t => t.stop());
      camRef.current = null;
    }
    setStreaming(false);
  };

  const snapPhoto = () => {
    const v = videoRef.current; const c = canvasRef.current;
    if (!v || !c) return;
    c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext('2d').drawImage(v, 0, 0);
    c.toBlob((blob) => {
      if (blob) {
        const f = new File([blob], `id_${Date.now()}.jpg`, { type: 'image/jpeg' });
        setFile(f);
        runOcr(f);
      }
      stopCam();
    }, 'image/jpeg', 0.85);
  };

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!form.name.trim()) { toast.error('Guest name is required'); return; }
    if (requireId && !file) { toast.error('Capture or attach an ID photo'); return; }
    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append('name', form.name);
      fd.append('phone', form.phone);
      fd.append('reason', form.reason);
      if (file) fd.append('id_image', file);
      await securityCheckpointApi.grantOneTime(fd);
      toast.success(`One-time entry granted to ${form.name}`);
      onClose();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed');
    } finally { setSubmitting(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="cp-grant-dialog">
        <DialogHeader>
          <DialogTitle>Grant one-time entry</DialogTitle>
          <DialogDescription>Hold the physical ID until the guest leaves. The system logs every step.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3 mt-2">
          <div className="space-y-1.5"><Label className="text-xs">Guest name *</Label><Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required autoFocus data-testid="cp-otg-name" /></div>
          <div className="space-y-1.5"><Label className="text-xs">Phone</Label><Input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} data-testid="cp-otg-phone" /></div>
          <div className="space-y-1.5"><Label className="text-xs">Reason / Visiting</Label><Input value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })} placeholder="e.g. Family visit / Delivery" /></div>

          <div className="space-y-1.5">
            <Label className="text-xs">ID Photo {requireId ? '*' : '(optional)'}</Label>
            {file ? (
              <div className="flex items-center gap-2 text-xs p-2 rounded border bg-emerald-50 dark:bg-emerald-950/20">
                <CheckCircle size={14} className="text-emerald-600" />
                <span className="flex-1">{file.name} · {(file.size / 1024).toFixed(0)} KB</span>
                <button type="button" className="text-rose-600" onClick={() => setFile(null)}><X size={12} /></button>
              </div>
            ) : streaming ? (
              <div className="space-y-2">
                <video ref={videoRef} aria-label="ID camera preview" className="w-full rounded bg-black aspect-video" playsInline>
                  <track kind="captions" />
                </video>
                <div className="flex gap-2">
                  <Button type="button" size="sm" className="flex-1" onClick={snapPhoto} data-testid="cp-otg-snap"><Camera size={13} className="mr-1" /> Snap</Button>
                  <Button type="button" size="sm" variant="outline" onClick={stopCam}>Cancel</Button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2">
                <Button type="button" size="sm" variant="outline" className="flex-1" onClick={startCam} data-testid="cp-otg-camera">
                  <Camera size={13} className="mr-1" /> Use camera
                </Button>
                <label className="flex-1">
                  <input type="file" accept="image/*" className="hidden" onChange={e => {
                    const f = e.target.files?.[0];
                    if (f) { setFile(f); runOcr(f); }
                  }} data-testid="cp-otg-file" />
                  <Button type="button" size="sm" variant="outline" className="w-full" onClick={(e) => e.currentTarget.previousSibling.click()}>Upload</Button>
                </label>
              </div>
            )}
            <canvas ref={canvasRef} className="hidden" />
          </div>

          {/* OCR feedback */}
          {ocring && (
            <p className="text-[11px] text-blue-600 dark:text-blue-400 italic" data-testid="cp-ocr-loading">
              Reading ID… extracting name + DOB + ID number via AI
            </p>
          )}
          {ocrResult && !ocring && (
            <div className="text-[11px] p-2 rounded border bg-blue-50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-900/40" data-testid="cp-ocr-result">
              <p className="font-semibold flex items-center gap-1 mb-0.5">
                <Camera size={11} /> OCR result — <span className={`capitalize ${ocrResult.confidence === 'high' ? 'text-emerald-600' : ocrResult.confidence === 'medium' ? 'text-amber-600' : 'text-rose-600'}`}>{ocrResult.confidence} confidence</span>
              </p>
              {ocrResult.name && <p>Name: <strong>{ocrResult.name}</strong></p>}
              {ocrResult.date_of_birth && <p>DOB: <strong>{ocrResult.date_of_birth}</strong></p>}
              {ocrResult.id_number && <p>ID#: <strong>{ocrResult.id_number}</strong></p>}
              {!ocrResult.name && !ocrResult.id_number && <p className="text-muted-foreground italic">No fields extracted — type manually</p>}
              <p className="text-[10px] text-muted-foreground italic mt-1">Auto-fill only writes to empty fields — your typing always wins.</p>
            </div>
          )}

          <div className="flex gap-2 pt-2">
            <Button type="button" variant="outline" className="flex-1" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={submitting} className="flex-1" data-testid="cp-otg-submit">{submitting ? 'Granting…' : 'Grant Entry'}</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ----- receipt exit-scan dialog -----
function ReceiptScanDialog({ open, onClose }) {
  const [receipt, setReceipt] = useState('');
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [showOverride, setShowOverride] = useState(false);
  const [overrideForm, setOverrideForm] = useState({ supervisor_pin: '', reason: '' });
  const [overriding, setOverriding] = useState(false);

  useEffect(() => {
    if (!open) {
      setReceipt(''); setResult(null);
      setShowOverride(false); setOverrideForm({ supervisor_pin: '', reason: '' });
    }
  }, [open]);

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!receipt.trim()) return;
    setSubmitting(true);
    try {
      const r = await securityCheckpointApi.scanReceipt({ receipt_number: receipt.trim() });
      setResult(r.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Receipt not found');
    } finally { setSubmitting(false); }
  };

  const submitOverride = async (e) => {
    e?.preventDefault?.();
    if (!result?.id || !overrideForm.supervisor_pin) return;
    setOverriding(true);
    try {
      const r = await securityCheckpointApi.receiptOverride({
        event_id: result.id,
        supervisor_pin: overrideForm.supervisor_pin,
        reason: overrideForm.reason,
      });
      setResult(r.data);
      setShowOverride(false);
      setOverrideForm({ supervisor_pin: '', reason: '' });
      toast.success('Override applied — exit cleared');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Override failed');
    } finally { setOverriding(false); }
  };

  const flagged = (result?.subject?.items || []).some(i => i.is_exit_restricted);
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="cp-receipt-dialog">
        <DialogHeader>
          <DialogTitle>Receipt Exit-Scan</DialogTitle>
          <DialogDescription>Scan or type the receipt number to verify items leaving the premises.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3 mt-2">
          <Input
            autoFocus
            value={receipt}
            onChange={e => setReceipt(e.target.value)}
            placeholder="INV-20260530-0001 or sale id"
            data-testid="cp-receipt-input"
          />
          <Button type="submit" className="w-full" disabled={submitting || !receipt.trim()}>{submitting ? 'Looking up…' : 'Look up receipt'}</Button>
        </form>
        {result && (
          <div className="mt-3 p-3 rounded border" data-testid="cp-receipt-result">
            <div className="flex items-center gap-2 mb-2">
              <Badge className={result.decision === 'denied' ? 'bg-rose-600 text-white' : 'bg-emerald-600 text-white'}>
                {result.decision === 'denied' ? 'BLOCKED — restricted item' : 'CLEARED'}
              </Badge>
              <span className="text-xs text-slate-500">{result.subject?.customer_name || 'Walk-in'}</span>
            </div>
            <p className="text-xs italic text-slate-500 mb-2">{result.reason}</p>
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {(result.subject?.items || []).map((it, i) => (
                <div key={i} className={`text-xs flex justify-between p-1.5 rounded ${it.is_exit_restricted ? 'bg-rose-50 dark:bg-rose-950/20' : 'bg-slate-50 dark:bg-slate-800/50'}`}>
                  <span>{it.qty}× {it.name}{it.is_exit_restricted && <span className="ml-1 text-[9px] text-rose-700 font-bold">RESTRICTED</span>}</span>
                  <span>{it.unit_price?.toLocaleString()}</span>
                </div>
              ))}
            </div>
            <p className="text-xs font-bold text-right mt-2">Total: {result.subject?.currency} {result.subject?.total?.toLocaleString()}</p>

            {/* Supervisor override appears only when this scan is currently denied */}
            {flagged && result.decision === 'denied' && (
              <div className="mt-3 pt-3 border-t border-rose-200 dark:border-rose-900/40">
                {!showOverride ? (
                  <Button
                    size="sm"
                    variant="outline"
                    className="w-full border-amber-300 text-amber-700 dark:text-amber-300 hover:bg-amber-50 dark:hover:bg-amber-950/30"
                    onClick={() => setShowOverride(true)}
                    data-testid="cp-receipt-override-open"
                  >
                    Supervisor override
                  </Button>
                ) : (
                  <form onSubmit={submitOverride} className="space-y-2" data-testid="cp-receipt-override-form">
                    <p className="text-[11px] text-muted-foreground">A Manager+ user must enter their PIN to clear this exit.</p>
                    <Input
                      type="password"
                      inputMode="numeric"
                      maxLength={8}
                      autoFocus
                      placeholder="Supervisor PIN"
                      value={overrideForm.supervisor_pin}
                      onChange={e => setOverrideForm({ ...overrideForm, supervisor_pin: e.target.value.replace(/\D/g, '') })}
                      data-testid="cp-receipt-override-pin"
                    />
                    <Input
                      placeholder="Reason (logged)"
                      value={overrideForm.reason}
                      onChange={e => setOverrideForm({ ...overrideForm, reason: e.target.value })}
                      data-testid="cp-receipt-override-reason"
                    />
                    <div className="flex gap-2">
                      <Button type="button" size="sm" variant="ghost" className="flex-1" onClick={() => setShowOverride(false)}>Cancel</Button>
                      <Button type="submit" size="sm" disabled={overriding || overrideForm.supervisor_pin.length < 4} className="flex-1" data-testid="cp-receipt-override-submit">
                        {overriding ? 'Verifying…' : 'Approve override'}
                      </Button>
                    </div>
                  </form>
                )}
              </div>
            )}
            {result.supervisor_override && (
              <div className="mt-3 pt-3 border-t border-emerald-200 dark:border-emerald-900/40 text-[11px] text-emerald-800 dark:text-emerald-300">
                ✓ Cleared by {result.supervisor_override.supervisor_name} ({result.supervisor_override.supervisor_role})
                {result.supervisor_override.reason && <span className="block italic mt-0.5">"{result.supervisor_override.reason}"</span>}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ============================================================
// LOGBOOK DIALOG — today's entries with entry/exit times
// ============================================================
function LogbookDialog({ open, onClose }) {
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await securityCheckpointApi.visitorLog(date);
      setRows(r.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed to load logbook'); }
    finally { setLoading(false); }
  }, [date]);
  useEffect(() => { if (open) load(); }, [open, load]);

  const insideCount = rows.filter(r => r.still_inside).length;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto" data-testid="cp-logbook-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><History size={16} /> Visitor Logbook</DialogTitle>
          <DialogDescription className="text-xs">Entry / exit times per person, per day. Same scan or badge again counts as the exit.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 mt-2">
          <div className="flex items-center gap-2">
            <Label className="text-xs">Date</Label>
            <Input type="date" value={date} onChange={e => setDate(e.target.value)} className="h-8 w-44" data-testid="cp-logbook-date" />
            <Badge variant="outline" className="text-[10px] ml-auto">{rows.length} total · {insideCount} inside</Badge>
          </div>
          {loading ? <div className="space-y-2">{[1, 2, 3].map(i => <div key={i} className="h-10 bg-muted animate-pulse rounded" />)}</div>
            : rows.length === 0 ? <p className="text-xs text-muted-foreground text-center py-6">No entries logged for this date.</p>
              : (
                <table className="w-full text-xs">
                  <thead className="text-[10px] uppercase text-muted-foreground border-b">
                    <tr><th className="text-left py-2">Visitor</th><th className="text-left">Type</th><th className="text-left">In</th><th className="text-left">Out</th><th className="text-left">Status</th></tr>
                  </thead>
                  <tbody>
                    {rows.map(r => (
                      <tr key={r.entry_event_id} className="border-b last:border-b-0" data-testid={`cp-logbook-row-${r.entry_event_id}`}>
                        <td className="py-1.5">
                          <div className="font-medium">{r.name}</div>
                          {(r.role || r.phone) && <div className="text-[10px] text-muted-foreground">{[r.role, r.phone].filter(Boolean).join(' · ')}</div>}
                          {r.event_title && <div className="text-[10px] text-blue-700 dark:text-blue-400">🎟 {r.event_title}</div>}
                        </td>
                        <td className="capitalize text-[10px]">{r.subject_kind?.replace('_', ' ') || '—'}</td>
                        <td className="font-mono text-[10px]">{r.entry_at?.slice(11, 16) || '—'}</td>
                        <td className="font-mono text-[10px]">{r.exit_at?.slice(11, 16) || '—'}</td>
                        <td>{r.still_inside ? <Badge className="bg-emerald-100 text-emerald-700 text-[9px]">Inside</Badge> : <Badge variant="outline" className="text-[9px]">Departed</Badge>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================
// LOOKUP DIALOG — phone / name search → household multi-select check-in
// ============================================================
function LookupDialog({ open, onClose, singleDevice }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selectedFor, setSelectedFor] = useState(null); // which household is expanded
  const [picks, setPicks] = useState({});               // {personId: true}
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => { if (!open) { setQ(''); setResults([]); setSelectedFor(null); setPicks({}); } }, [open]);

  const runSearch = async (e) => {
    e?.preventDefault?.();
    if (q.trim().length < 2) { toast.error('Type at least 2 characters'); return; }
    setSearching(true);
    try {
      const r = await securityCheckpointApi.lookup(q.trim());
      setResults(r.data?.results || []);
      if ((r.data?.results || []).length === 0) toast.info('No matches');
    } catch (e) { toast.error(e.response?.data?.detail || 'Search failed'); }
    finally { setSearching(false); }
  };

  const togglePick = (kind, id) => setPicks(prev => ({ ...prev, [`${kind}:${id}`]: !prev[`${kind}:${id}`] }));

  const checkIn = async () => {
    const members = Object.entries(picks).filter(([, v]) => v).map(([k]) => {
      const [kind, id] = k.split(':');
      return { kind, id };
    });
    if (!members.length) { toast.error('Tick at least one person'); return; }
    setSubmitting(true);
    try {
      const r = await securityCheckpointApi.checkInBatch(members);
      toast.success(`Checked in ${r.data?.checked_in || 0} member${r.data?.checked_in === 1 ? '' : 's'}`);
      onClose();
    } catch (e) { toast.error(e.response?.data?.detail || 'Check-in failed'); }
    finally { setSubmitting(false); }
  };

  const selectedCount = Object.values(picks).filter(Boolean).length;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl max-h-[88vh] overflow-y-auto" data-testid="cp-lookup-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><UsersIcon size={16} /> Lookup &amp; Household Check-in</DialogTitle>
          <DialogDescription className="text-xs">
            {singleDevice
              ? 'Type a visitor\'s phone or first name. Pick the right match — their household will appear with checkboxes so you can tick everyone present.'
              : 'Phone or first-name search. Pick the right match — their household appears below for multi-select check-in.'}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={runSearch} className="flex gap-2 mt-2">
          <Input autoFocus placeholder="Phone, first name, last name, or email…" value={q} onChange={e => setQ(e.target.value)} data-testid="cp-lookup-input" />
          <Button type="submit" disabled={searching || q.trim().length < 2} data-testid="cp-lookup-submit">{searching ? 'Searching…' : 'Search'}</Button>
        </form>
        {results.length > 0 && (
          <div className="space-y-2 mt-3 max-h-96 overflow-y-auto">
            {results.map(r => {
              const expanded = selectedFor === r.id;
              return (
                <div key={`${r.kind}:${r.id}`} className="border rounded-lg" data-testid={`cp-lookup-result-${r.id}`}>
                  <button
                    type="button"
                    className="w-full p-2.5 text-left hover:bg-accent/30 flex items-center gap-2"
                    onClick={() => { setSelectedFor(expanded ? null : r.id); setPicks(prev => ({ ...prev, [`${r.kind}:${r.id}`]: !expanded ? true : prev[`${r.kind}:${r.id}`] })); }}
                  >
                    <Badge variant="outline" className="text-[9px] capitalize">{r.kind}</Badge>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium">{r.name}</p>
                      <p className="text-[10px] text-muted-foreground">{[r.phone, r.email, r.role].filter(Boolean).join(' · ')}{r.family_name ? ` · 🏠 ${r.family_name}` : ''}</p>
                    </div>
                    <span className="text-[10px] text-muted-foreground">{(r.household || []).length} household</span>
                  </button>
                  {expanded && (
                    <div className="p-2.5 border-t bg-muted/30 space-y-1" data-testid={`cp-lookup-household-${r.id}`}>
                      <label className="flex items-center gap-2 text-sm cursor-pointer">
                        <input
                          type="checkbox"
                          checked={!!picks[`${r.kind}:${r.id}`]}
                          onChange={() => togglePick(r.kind, r.id)}
                          data-testid={`cp-pick-${r.id}`}
                        />
                        <span className="font-medium">{r.name}</span>
                        <span className="text-[10px] text-muted-foreground">({r.kind})</span>
                      </label>
                      {(r.household || []).map(h => (
                        <label key={h.id} className="flex items-center gap-2 text-sm cursor-pointer pl-4">
                          <input
                            type="checkbox"
                            checked={!!picks[`${h.kind}:${h.id}`]}
                            onChange={() => togglePick(h.kind, h.id)}
                            data-testid={`cp-pick-${h.id}`}
                          />
                          <span>{h.name}</span>
                          <span className="text-[10px] text-muted-foreground">{h.kind === 'child' ? (h.grade || 'child') : (h.role || 'member')}</span>
                        </label>
                      ))}
                      {(r.household || []).length === 0 && <p className="text-[11px] text-muted-foreground italic pl-4">No household siblings on file.</p>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
        {selectedCount > 0 && (
          <div className="flex gap-2 pt-3 border-t mt-3">
            <Button variant="ghost" className="flex-1" onClick={() => { setPicks({}); setSelectedFor(null); }}>Clear</Button>
            <Button className="flex-1" disabled={submitting} onClick={checkIn} data-testid="cp-lookup-checkin-submit">
              {submitting ? 'Checking in…' : `Check in ${selectedCount} person${selectedCount === 1 ? '' : 's'}`}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

