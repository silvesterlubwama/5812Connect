/**
 * Browser softphone — WebRTC SIP UA using JsSIP.
 *
 * Self-contained component: drop `<BrowserSoftphone />` into any page and it
 * will register the calling user's WebRTC extension (from /api/pbx/me/softphone)
 * to the appliance Asterisk over WSS.
 *
 * Renders nothing when the user has no WebRTC extension assigned (returns
 * a 204 from the backend). Otherwise shows a draggable floating widget with:
 *   • registration status pill
 *   • dial pad (full DTMF + paste-from-clipboard for numbers)
 *   • mute / hold / hangup / DTMF buttons during a call
 *   • answer / decline for incoming calls
 *
 * To trigger from elsewhere (e.g. click-to-call buttons on member records):
 *   window.dispatchEvent(new CustomEvent('softphone-dial', { detail: { number: '+15551234567' } }))
 *
 * Notes
 * ─────
 * • JsSIP is dynamically imported so the bundle stays small for non-call users.
 * • Stripped-down UI vs commercial softphones — this is meant for internal
 *   helpdesk + occasional outbound, not a contact center.
 */
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Phone, PhoneOff, PhoneIncoming, PhoneCall, Mic, MicOff, Pause, Play, X, Hash, Delete } from 'lucide-react';
import api from '../services/api';
import { toast } from 'sonner';

const DTMF_KEYS = [
  ['1', '2', '3'],
  ['4', '5', '6'],
  ['7', '8', '9'],
  ['*', '0', '#'],
];

export default function BrowserSoftphone() {
  const [config, setConfig] = useState(null);   // {extension, secret, ws_url, sip_uri, sip_domain, stun_url}
  const [regState, setRegState] = useState('idle');   // idle|registering|registered|failed|disconnected
  const [open, setOpen] = useState(false);
  const [dialed, setDialed] = useState('');
  const [activeCall, setActiveCall] = useState(null); // {direction:'out'|'in', peer:'...', duration_sec:0, muted, held}
  const [incomingCall, setIncomingCall] = useState(null);
  const uaRef = useRef(null);
  const sessionRef = useRef(null);
  const remoteAudioRef = useRef(null);
  const tickRef = useRef(null);

  // ── Fetch SIP credentials on mount ────────────────────────────
  useEffect(() => {
    let cancelled = false;
    api.get('/pbx/me/softphone').then(r => {
      if (cancelled) return;
      if (r.status === 204 || !r.data) { setConfig(null); return; }
      setConfig(r.data);
    }).catch(() => setConfig(null));
    return () => { cancelled = true; };
  }, []);

  // ── Register to Asterisk via JsSIP ────────────────────────────
  useEffect(() => {
    if (!config?.ws_url) return;
    let cancelled = false;
    setRegState('registering');
    (async () => {
      let JsSIP;
      try {
        const mod = await import('jssip');
        JsSIP = mod.default || mod;
      } catch (e) {
        toast.error('Softphone library failed to load'); setRegState('failed');
        return;
      }
      if (cancelled) return;
      const socket = new JsSIP.WebSocketInterface(config.ws_url);
      const ua = new JsSIP.UA({
        sockets: [socket],
        uri: config.sip_uri,
        password: config.secret,
        display_name: config.display_name,
        session_timers: false,
        register: true,
      });
      ua.on('registered', () => setRegState('registered'));
      ua.on('unregistered', () => setRegState('disconnected'));
      ua.on('registrationFailed', () => setRegState('failed'));
      ua.on('disconnected', () => setRegState('disconnected'));
      ua.on('newRTCSession', (data) => {
        const session = data.session;
        if (data.originator === 'remote') {
          // Incoming call
          setIncomingCall({
            peer: session.remote_identity.display_name || session.remote_identity.uri.user,
            session,
          });
        }
        bindSession(session);
      });
      ua.start();
      uaRef.current = ua;
    })();
    return () => {
      cancelled = true;
      if (uaRef.current) {
        try { uaRef.current.stop(); } catch (_) {/* noop */}
        uaRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config?.ws_url]);

  // ── Bind events on an in-progress RTCSession ──────────────────
  const bindSession = (session) => {
    session.on('accepted', () => {
      setIncomingCall(null);
      setActiveCall({
        direction: session.direction,
        peer: session.remote_identity.display_name || session.remote_identity.uri.user,
        started_at: Date.now(),
        duration_sec: 0,
        muted: false,
        held: false,
      });
      // Attach remote audio
      const stream = new MediaStream();
      session.connection.getReceivers().forEach(r => r.track && stream.addTrack(r.track));
      if (remoteAudioRef.current) {
        remoteAudioRef.current.srcObject = stream;
        remoteAudioRef.current.play().catch(() => {/* user-gesture needed; ignore */});
      }
      // Tick duration every second
      tickRef.current = setInterval(() => {
        setActiveCall(c => c ? { ...c, duration_sec: Math.floor((Date.now() - c.started_at) / 1000) } : c);
      }, 1000);
    });
    session.on('ended', () => endCall(false));
    session.on('failed', () => endCall(false));
    sessionRef.current = session;
  };

  // ── External dial event (from click-to-call buttons) ──────────
  useEffect(() => {
    const handler = (ev) => {
      const number = ev?.detail?.number;
      if (!number) return;
      if (regState !== 'registered') { toast.error('Softphone not registered yet'); return; }
      setOpen(true);
      setDialed(number);
      placeCall(number);
    };
    window.addEventListener('softphone-dial', handler);
    return () => window.removeEventListener('softphone-dial', handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [regState]);

  const placeCall = useCallback((target) => {
    const ua = uaRef.current;
    if (!ua || regState !== 'registered') { toast.error('Not registered'); return; }
    const dest = `sip:${target}@${config.sip_domain}`;
    const options = {
      mediaConstraints: { audio: true, video: false },
      pcConfig: { iceServers: [{ urls: config.stun_url || 'stun:stun.l.google.com:19302' }] },
    };
    try {
      const session = ua.call(dest, options);
      bindSession(session);
      setActiveCall({ direction: 'outgoing', peer: target, started_at: Date.now(), duration_sec: 0, muted: false, held: false });
    } catch (e) { toast.error(`Call failed: ${e.message || e}`); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config, regState]);

  const endCall = (terminate = true) => {
    if (terminate && sessionRef.current) {
      try { sessionRef.current.terminate(); } catch (_) {/* noop */}
    }
    sessionRef.current = null;
    setActiveCall(null);
    setIncomingCall(null);
    if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
  };
  const answer = () => {
    if (incomingCall?.session) {
      incomingCall.session.answer({ mediaConstraints: { audio: true, video: false } });
    }
  };
  const decline = () => {
    if (incomingCall?.session) { try { incomingCall.session.terminate({ status_code: 486 }); } catch (_) {/* noop */} }
    setIncomingCall(null);
  };
  const toggleMute = () => {
    const s = sessionRef.current; if (!s) return;
    if (activeCall.muted) s.unmute({ audio: true }); else s.mute({ audio: true });
    setActiveCall(c => c ? { ...c, muted: !c.muted } : c);
  };
  const toggleHold = () => {
    const s = sessionRef.current; if (!s) return;
    if (activeCall.held) s.unhold(); else s.hold();
    setActiveCall(c => c ? { ...c, held: !c.held } : c);
  };
  const sendDTMF = (k) => {
    const s = sessionRef.current;
    if (s && activeCall) s.sendDTMF(k);
    else setDialed(d => d + k);
  };

  // Don't render the widget at all if the user has no WebRTC extension
  if (!config) return null;

  const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  const stateColor = {
    registered: 'bg-emerald-100 text-emerald-700',
    registering: 'bg-amber-100 text-amber-700',
    failed: 'bg-rose-100 text-rose-700',
    disconnected: 'bg-muted text-muted-foreground',
    idle: 'bg-muted text-muted-foreground',
  }[regState];

  return (
    <>
      <audio ref={remoteAudioRef} autoPlay playsInline />
      {/* Floating launcher button */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-4 right-4 z-50 h-12 w-12 rounded-full bg-primary text-primary-foreground shadow-xl hover:bg-primary/90 flex items-center justify-center"
          title={`Softphone — ext ${config.extension} (${regState})`}
          data-testid="softphone-launcher"
        >
          <Phone size={18} />
          {(activeCall || incomingCall) && <span className="absolute top-0 right-0 h-3 w-3 rounded-full bg-rose-500 animate-pulse" />}
        </button>
      )}

      {/* Main panel */}
      {open && (
        <div className="fixed bottom-4 right-4 z-50 w-80 rounded-xl border bg-card shadow-2xl" data-testid="softphone-panel">
          {/* Header */}
          <div className="flex items-center justify-between p-2.5 border-b">
            <div className="flex items-center gap-2">
              <Phone size={14} />
              <span className="text-xs font-semibold">Ext {config.extension}</span>
              <Badge className={`text-[10px] ${stateColor}`} data-testid="softphone-reg-state">{regState}</Badge>
            </div>
            <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setOpen(false)} data-testid="softphone-close"><X size={12} /></Button>
          </div>

          {/* Incoming call ringer */}
          {incomingCall && !activeCall && (
            <div className="p-4 text-center space-y-3" data-testid="softphone-incoming">
              <PhoneIncoming size={28} className="mx-auto text-emerald-600 animate-pulse" />
              <p className="text-sm font-semibold">{incomingCall.peer}</p>
              <p className="text-xs text-muted-foreground">Incoming call…</p>
              <div className="flex gap-2 justify-center">
                <Button size="sm" variant="destructive" onClick={decline} data-testid="softphone-decline"><PhoneOff size={12} className="mr-1" /> Decline</Button>
                <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700" onClick={answer} data-testid="softphone-answer"><Phone size={12} className="mr-1" /> Answer</Button>
              </div>
            </div>
          )}

          {/* Active call panel */}
          {activeCall && (
            <div className="p-3 space-y-2 text-center" data-testid="softphone-active-call">
              <PhoneCall size={22} className="mx-auto text-primary" />
              <p className="text-sm font-semibold truncate">{activeCall.peer}</p>
              <p className="text-xs text-muted-foreground">
                {activeCall.held ? 'On hold' : 'In call'} · {fmt(activeCall.duration_sec)}
              </p>
              <div className="grid grid-cols-3 gap-1">
                <Button size="sm" variant={activeCall.muted ? 'default' : 'outline'} onClick={toggleMute} data-testid="softphone-mute">
                  {activeCall.muted ? <MicOff size={12} /> : <Mic size={12} />}
                </Button>
                <Button size="sm" variant={activeCall.held ? 'default' : 'outline'} onClick={toggleHold} data-testid="softphone-hold">
                  {activeCall.held ? <Play size={12} /> : <Pause size={12} />}
                </Button>
                <Button size="sm" variant="destructive" onClick={() => endCall(true)} data-testid="softphone-hangup">
                  <PhoneOff size={12} />
                </Button>
              </div>
            </div>
          )}

          {/* Dial pad (always visible when no incoming, no active) */}
          {!incomingCall && !activeCall && (
            <div className="p-3 space-y-2" data-testid="softphone-dialpad">
              <div className="flex gap-1">
                <input
                  type="tel"
                  value={dialed}
                  onChange={e => setDialed(e.target.value.replace(/[^\d+*#]/g, ''))}
                  placeholder="Number to dial"
                  className="flex-1 px-2 py-1.5 text-sm rounded border bg-background"
                  data-testid="softphone-number-input"
                />
                <Button size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={() => setDialed(d => d.slice(0, -1))} title="Backspace"><Delete size={12} /></Button>
              </div>
              <div className="grid grid-cols-3 gap-1">
                {DTMF_KEYS.flat().map(k => (
                  <Button key={k} size="sm" variant="outline" className="h-9 font-mono" onClick={() => sendDTMF(k)} data-testid={`softphone-key-${k === '*' ? 'star' : k === '#' ? 'hash' : k}`}>
                    {k}
                  </Button>
                ))}
              </div>
              <Button
                className="w-full bg-emerald-600 hover:bg-emerald-700"
                onClick={() => placeCall(dialed)}
                disabled={!dialed || regState !== 'registered'}
                data-testid="softphone-call-btn"
              >
                <Phone size={12} className="mr-1" /> Call {dialed && `→ ${dialed}`}
              </Button>
              {regState !== 'registered' && (
                <p className="text-[10px] text-center text-muted-foreground">
                  {regState === 'registering' && 'Connecting to PBX…'}
                  {regState === 'failed' && 'Registration failed — check WSS URL / credentials.'}
                  {regState === 'disconnected' && 'Disconnected from PBX.'}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </>
  );
}
