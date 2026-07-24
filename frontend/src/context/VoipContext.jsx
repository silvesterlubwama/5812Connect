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
  callState: 'idle', remotePeer: '', isMuted: false, isOnHold: false, isVideoEnabled: false,
  hasRemoteVideo: false, localStream: null, remoteStream: null, callDurationSec: 0,
  blfStates: {}, registrationMap: {},
  dial: () => {}, answer: () => {}, hangup: () => {},
  toggleMute: () => {}, toggleHold: () => {}, toggleVideo: () => {},
  sendDtmf: () => {}, blindTransfer: () => {},
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
  const [isVideoEnabled, setIsVideoEnabled] = useState(false);
  const [hasRemoteVideo, setHasRemoteVideo] = useState(false);
  const [callDurationSec, setCallDurationSec] = useState(0);
  // BLF: extension → 'idle' | 'ringing' | 'on-call' | 'early' (from JsSIP dialog SUBSCRIBE)
  const [blfStates, setBlfStates] = useState({});
  // Coarse "registered anywhere" flag per extension, from UCM listAccount polling.
  const [registrationMap, setRegistrationMap] = useState({});

  const uaRef = useRef(null);
  const sessionRef = useRef(null);
  const audioRef = useRef(null);
  const videoRefLocal = useRef(null);
  const videoRefRemote = useRef(null);
  const timerRef = useRef(null);
  const blfSubsRef = useRef({});   // extension → JsSIP.Subscriber
  const localStreamRef = useRef(null);
  const remoteStreamRef = useRef(null);

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
          setHasRemoteVideo(false);

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
              const stream = ev.streams?.[0];
              if (!stream) return;
              remoteStreamRef.current = stream;
              if (ev.track.kind === 'audio' && audioRef.current) {
                audioRef.current.srcObject = stream;
              }
              if (ev.track.kind === 'video') {
                setHasRemoteVideo(true);
                if (videoRefRemote.current) videoRefRemote.current.srcObject = stream;
              }
            });
          });
          if (isIncoming) {
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
    if (videoRefRemote.current) videoRefRemote.current.srcObject = null;
    if (videoRefLocal.current) videoRefLocal.current.srcObject = null;
    try { localStreamRef.current?.getTracks().forEach(t => t.stop()); } catch {}
    localStreamRef.current = null;
    remoteStreamRef.current = null;
    sessionRef.current = null;
    setCallState('idle');
    setRemotePeer('');
    setIsMuted(false);
    setIsOnHold(false);
    setIsVideoEnabled(false);
    setHasRemoteVideo(false);
    setCallDurationSec(0);
  }, []);

  const dial = useCallback((number, opts = {}) => {
    const ua = uaRef.current;
    if (!ua || status !== 'registered') { toast.error('Softphone not registered'); return; }
    if (sessionRef.current) { toast.error('Already on a call'); return; }
    const target = String(number || '').trim();
    if (!target) return;
    const clean = target.replace(/[^\d+*#]/g, '');
    const withVideo = !!opts.video;
    const cfg = ua._sipConnectOptions || {};
    const mediaConstraints = { audio: true, video: withVideo };
    ua.call(`sip:${clean}@${ua.configuration.uri.host}`, { ...cfg, mediaConstraints });
    setRemotePeer(clean);
    setCallState('outgoing');
    setIsVideoEnabled(withVideo);
    // Wire the local stream to the preview element once JsSIP has fetched it.
    setTimeout(() => {
      try {
        const stream = sessionRef.current?.connection?.getLocalStreams?.()?.[0]
          || sessionRef.current?.connection?.getSenders?.()?.[0]?.streams?.[0];
        if (stream) {
          localStreamRef.current = stream;
          if (videoRefLocal.current && withVideo) videoRefLocal.current.srcObject = stream;
        }
      } catch {}
    }, 800);
  }, [status]);

  const answer = useCallback((opts = {}) => {
    const s = sessionRef.current;
    if (!s || s.direction !== 'incoming') return;
    const withVideo = !!opts.video;
    setIsVideoEnabled(withVideo);
    s.answer({
      ...(uaRef.current?._sipConnectOptions || {}),
      mediaConstraints: { audio: true, video: withVideo },
    });
  }, []);

  const toggleVideo = useCallback(async () => {
    const s = sessionRef.current;
    if (!s || !s.connection) return;
    const senders = s.connection.getSenders();
    const videoSender = senders.find(sd => sd.track?.kind === 'video');
    if (isVideoEnabled && videoSender) {
      // Stop the outgoing video track; ICE renegotiation not needed for pause.
      videoSender.track.enabled = false;
      setIsVideoEnabled(false);
    } else {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        const track = stream.getVideoTracks()[0];
        if (videoSender) {
          await videoSender.replaceTrack(track);
        } else {
          s.connection.addTrack(track, stream);
        }
        localStreamRef.current = stream;
        if (videoRefLocal.current) videoRefLocal.current.srcObject = stream;
        setIsVideoEnabled(true);
      } catch (e) {
        toast.error('Camera unavailable');
      }
    }
  }, [isVideoEnabled]);

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

  // ── BLF: SIP SUBSCRIBE dialog event package ────────────────────
  //
  // Once the UA is registered, subscribe to each colleague's extension on the
  // UCM's `dialog` event package. UCM must have Presence enabled
  // (SIP Settings → Advanced → Enable Presence). On each NOTIFY we parse the
  // XML body — the `<state>` inside `<dialog>` tells us whether the peer is
  // idle (`terminated`), ringing (`early`), or on-call (`confirmed`).
  const subscribeBlfList = useCallback((extensions) => {
    const ua = uaRef.current;
    if (!ua || status !== 'registered') return;
    const seen = new Set(extensions);
    // Tear down subs for extensions no longer in the list
    Object.entries(blfSubsRef.current).forEach(([ext, sub]) => {
      if (!seen.has(ext)) {
        try { sub.terminate(); } catch {}
        delete blfSubsRef.current[ext];
      }
    });
    // Add new subs. JsSIP v3 exposes `ua.subscribe(target, event, options)`.
    if (typeof ua.subscribe !== 'function') return;   // older JsSIP builds — skip BLF
    extensions.forEach(ext => {
      if (blfSubsRef.current[ext]) return;
      try {
        const target = `sip:${ext}@${ua.configuration.uri.host}`;
        const sub = ua.subscribe(target, 'dialog', {
          expires: 3600,
          contentType: 'application/dialog-info+xml',
          accept: 'application/dialog-info+xml',
        });
        sub.on('notify', (n) => {
          const body = n?.request?.body || '';
          // Cheap parse — full XML parser is overkill for this fragment.
          let state = 'idle';
          if (/state="early"/.test(body) || /<state>early<\/state>/.test(body)) state = 'ringing';
          else if (/state="confirmed"/.test(body) || /<state>confirmed<\/state>/.test(body)) state = 'on-call';
          else if (/state="terminated"/.test(body) || /<state>terminated<\/state>/.test(body)) state = 'idle';
          setBlfStates(prev => ({ ...prev, [ext]: state }));
        });
        sub.on('failed', () => {
          // Presence disabled on UCM — fall back to coarse registration polling only.
          delete blfSubsRef.current[ext];
        });
        sub.subscribe();
        blfSubsRef.current[ext] = sub;
      } catch (e) {
        // Best-effort — swallow to avoid a noisy loop.
      }
    });
  }, [status]);

  // ── Directory + coarse-registration polling ─────────────────────
  //
  // Every 30 s the FE hits /api/voip/blf to refresh the "registered anywhere"
  // dot. Also drives the initial BLF subscribe list — as new colleagues get
  // extensions provisioned, they auto-appear here.
  useEffect(() => {
    if (status !== 'registered') return;
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await api.get('/voip/blf');
        if (cancelled) return;
        const rows = r.data?.registrations || [];
        const map = {};
        rows.forEach(x => { map[x.extension] = !!x.registered; });
        setRegistrationMap(map);
        subscribeBlfList(rows.map(x => x.extension).filter(x => x && x !== extension));
      } catch { /* ignore */ }
    };
    tick();
    const id = setInterval(tick, 30000);
    return () => { cancelled = true; clearInterval(id); };
  }, [status, extension, subscribeBlfList]);

  return (
    <VoipContext.Provider value={{
      status, statusReason, extension,
      callState, remotePeer, isMuted, isOnHold, isVideoEnabled, hasRemoteVideo, callDurationSec,
      blfStates, registrationMap,
      dial, answer, hangup, toggleMute, toggleHold, toggleVideo, sendDtmf, blindTransfer,
      // Refs the SoftphonePanel / PhoneRoom bind their <video> elements to.
      _videoRefLocal: videoRefLocal, _videoRefRemote: videoRefRemote,
    }}>
      {children}
    </VoipContext.Provider>
  );
}
