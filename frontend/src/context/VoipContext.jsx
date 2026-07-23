/**
 * VoIP context — the browser-based SIP softphone.
 *
 * Runs one JsSIP UserAgent per authenticated session. It REGISTERs the
 * user's extension against the tenant's Grandstream UCM over WSS, so the
 * UCM sees this browser tab as another endpoint on that extension (right
 * next to the user's desk phone, mobile Wave app, etc.).
 *
 * Everything else — outbound routes, trunks, DID, IVR, voicemail — lives
 * on the UCM. We only own the browser softphone UX.
 *
 * Exposes via `useVoip()`:
 *   • status                    'unconfigured'|'registering'|'registered'|'failed'|'offline'
 *   • statusReason              human-readable text ('WSS handshake failed', etc)
 *   • extension                 the user's SIP extension (or '')
 *   • callState                 'idle'|'outgoing'|'incoming'|'in-call'|'held'
 *   • remotePeer                'sip:+15551234@ucm' or a colleague name
 *   • isMuted, isOnHold, callDurationSec
 *   • dial(number)              place an outbound call
 *   • answer(), hangup()        for the current session
 *   • toggleMute(), toggleHold()
 *   • sendDtmf(digit)           for IVR navigation
 *   • blindTransfer(target)
 */
import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import JsSIP from 'jssip';
import { toast } from 'sonner';
import { useAuth } from './AuthContext';
import api from '../services/api';

const VoipContext = createContext(null);
export const useVoip = () => useContext(VoipContext) || _EMPTY_CTX;

const _EMPTY_CTX = {
  status: 'offline', statusReason: '', extension: '',
  callState: 'idle', remotePeer: '', isMuted: false, isOnHold: false, callDurationSec: 0,
  dial: () => {}, answer: () => {}, hangup: () => {},
  toggleMute: () => {}, toggleHold: () => {}, sendDtmf: () => {}, blindTransfer: () => {},
};

// Suppress JsSIP's verbose console spam in production builds.
if (process.env.NODE_ENV === 'production') {
  try { JsSIP.debug.disable(); } catch {}
}

export function VoipProvider({ children }) {
  const { user } = useAuth();
  const [status, setStatus] = useState('offline');
  const [statusReason, setStatusReason] = useState('');
  const [extension, setExtension] = useState('');
  const [callState, setCallState] = useState('idle');
  const [remotePeer, setRemotePeer] = useState('');
  const [isMuted, setIsMuted] = useState(false);
  const [isOnHold, setIsOnHold] = useState(false);
  const [callDurationSec, setCallDurationSec] = useState(0);

  const uaRef = useRef(null);
  const sessionRef = useRef(null);
  const audioRef = useRef(null);
  const timerRef = useRef(null);

  // ── audio element ───────────────────────────────────────────
  useEffect(() => {
    if (!audioRef.current) {
      const a = document.createElement('audio');
      a.autoplay = true;
      a.id = 'voip-remote-audio';
      a.style.display = 'none';
      document.body.appendChild(a);
      audioRef.current = a;
    }
    return () => { if (audioRef.current) { audioRef.current.remove(); audioRef.current = null; } };
  }, []);

  // ── build & register the UserAgent when the user has SIP creds ──
  useEffect(() => {
    if (!user?.id) return;
    let cancelled = false;

    (async () => {
      try {
        const r = await api.get('/voip/me/sip-config');
        if (r.status === 204 || !r.data) { setStatus('unconfigured'); setStatusReason('No SIP extension assigned to your account.'); return; }
        if (cancelled) return;
        const cfg = r.data;
        setExtension(cfg.extension);

        const socket = new JsSIP.WebSocketInterface(cfg.ws_url);
        const ua = new JsSIP.UA({
          sockets: [socket],
          uri: `sip:${cfg.extension}@${cfg.sip_domain}`,
          authorization_user: cfg.extension,
          password: cfg.sip_password,
          display_name: cfg.display_name || cfg.extension,
          session_timers: false,
          register: true,
          register_expires: 300,
        });

        ua.on('connecting', () => { setStatus('registering'); setStatusReason('Connecting to PBX…'); });
        ua.on('connected', () => { setStatusReason('WebSocket connected'); });
        ua.on('disconnected', (e) => {
          setStatus('offline');
          setStatusReason(e?.error ? `Disconnected: ${e.reason || e.code || 'network'}` : 'Disconnected');
        });
        ua.on('registered', () => { setStatus('registered'); setStatusReason('Registered'); });
        ua.on('unregistered', () => { setStatus('offline'); setStatusReason('Unregistered'); });
        ua.on('registrationFailed', (e) => {
          setStatus('failed');
          setStatusReason(e?.cause || 'Registration failed');
          console.warn('[VoIP] registration failed:', e);
        });

        // ── inbound + session events ────────────────────────
        const iceServers = [
          ...(cfg.stun_urls || []).map(u => ({ urls: u })),
          ...(cfg.turn_urls || []).map(u => ({ urls: u, username: cfg.turn_username, credential: cfg.turn_password })),
        ];

        ua.on('newRTCSession', ({ session, request }) => {
          if (sessionRef.current) {
            // Second call arrives while we're already on one — reject busy.
            try { session.terminate({ status_code: 486, reason_phrase: 'Busy Here' }); } catch {}
            return;
          }
          sessionRef.current = session;
          const isIncoming = session.direction === 'incoming';
          const peer = (isIncoming ? (request?.from?.display_name || request?.from?.uri?.user) : (session.remote_identity?.uri?.user)) || '';
          setRemotePeer(peer);
          setCallState(isIncoming ? 'incoming' : 'outgoing');

          if (isIncoming) toast.info(`Incoming call from ${peer}`, { duration: 15000 });

          session.on('confirmed', () => {
            setCallState('in-call');
            setCallDurationSec(0);
            if (timerRef.current) clearInterval(timerRef.current);
            timerRef.current = setInterval(() => setCallDurationSec(s => s + 1), 1000);
          });
          session.on('ended', () => teardown());
          session.on('failed', (e) => { teardown(); toast.error(`Call ended: ${e?.cause || 'failed'}`); });
          session.on('peerconnection', ({ peerconnection }) => {
            peerconnection.addEventListener('track', (ev) => {
              if (audioRef.current && ev.streams?.[0]) audioRef.current.srcObject = ev.streams[0];
            });
          });
          if (isIncoming) {
            // Show incoming toast — user answers via context.answer()
            session.on('accepted', () => setCallState('in-call'));
          }
        });

        // Store options we'll pass into ua.call() so ICE servers apply.
        ua._sipConnectOptions = {
          mediaConstraints: { audio: true, video: false },
          pcConfig: { iceServers },
        };

        uaRef.current = ua;
        ua.start();
      } catch (e) {
        console.error('[VoIP] init failed', e);
        setStatus('failed');
        setStatusReason(e?.response?.data?.detail || e?.message || 'VoIP init failed');
      }
    })();

    return () => {
      cancelled = true;
      try { uaRef.current?.stop(); } catch {}
      uaRef.current = null;
    };
  }, [user?.id]);

  // ── helpers ─────────────────────────────────────────────────
  const teardown = useCallback(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    if (audioRef.current) audioRef.current.srcObject = null;
    sessionRef.current = null;
    setCallState('idle');
    setRemotePeer('');
    setIsMuted(false);
    setIsOnHold(false);
    setCallDurationSec(0);
  }, []);

  const dial = useCallback((number) => {
    const ua = uaRef.current;
    if (!ua || status !== 'registered') { toast.error('Softphone not registered'); return; }
    if (sessionRef.current) { toast.error('Already on a call'); return; }
    const target = String(number || '').trim();
    if (!target) return;
    // Strip visual formatting except '+' and digits.
    const clean = target.replace(/[^\d+*#]/g, '');
    const cfg = ua._sipConnectOptions || {};
    ua.call(`sip:${clean}@${ua.configuration.uri.host}`, cfg);
    setRemotePeer(clean);
    setCallState('outgoing');
  }, [status]);

  const answer = useCallback(() => {
    const s = sessionRef.current;
    if (!s || s.direction !== 'incoming') return;
    s.answer(uaRef.current?._sipConnectOptions || { mediaConstraints: { audio: true, video: false } });
  }, []);

  const hangup = useCallback(() => {
    const s = sessionRef.current;
    if (!s) return;
    try { s.terminate(); } catch {}
    teardown();
  }, [teardown]);

  const toggleMute = useCallback(() => {
    const s = sessionRef.current;
    if (!s) return;
    if (isMuted) { s.unmute({ audio: true }); setIsMuted(false); }
    else { s.mute({ audio: true }); setIsMuted(true); }
  }, [isMuted]);

  const toggleHold = useCallback(() => {
    const s = sessionRef.current;
    if (!s) return;
    if (isOnHold) { s.unhold(); setIsOnHold(false); setCallState('in-call'); }
    else { s.hold(); setIsOnHold(true); setCallState('held'); }
  }, [isOnHold]);

  const sendDtmf = useCallback((digit) => {
    const s = sessionRef.current;
    if (!s) return;
    try { s.sendDTMF(String(digit)); } catch {}
  }, []);

  const blindTransfer = useCallback((target) => {
    const s = sessionRef.current;
    if (!s) return;
    const clean = String(target || '').replace(/[^\d+*#]/g, '');
    try { s.refer(`sip:${clean}@${uaRef.current?.configuration.uri.host}`); toast.success(`Transferring to ${clean}…`); } catch (e) { toast.error('Transfer failed'); }
  }, []);

  return (
    <VoipContext.Provider value={{
      status, statusReason, extension,
      callState, remotePeer, isMuted, isOnHold, callDurationSec,
      dial, answer, hangup, toggleMute, toggleHold, sendDtmf, blindTransfer,
    }}>
      {children}
    </VoipContext.Provider>
  );
}
