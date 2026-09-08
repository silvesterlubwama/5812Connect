/**
 * IncomingCallModal — global ringing overlay.
 *
 * Mounted once at app-root by `Layout.jsx` so any inbound `incoming_call`
 * WebSocket event (broadcast by `backend/routers/websocket.py` when someone
 * fires `call_offer`) pops up over whatever page the user is on. Missed
 * calls are logged so a busy staffer sees them in Notifications later.
 *
 * The heavy lifting (RTCPeerConnection wiring, audio/video streams) still
 * happens on the Comms page — this modal just answers / rejects and then
 * navigates to `/comms?call=<call_id>` so the existing peer-connection
 * plumbing there takes over.
 */
import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Phone, PhoneOff, Video, Sparkles } from 'lucide-react';
import { useWebSocket } from '../context/WebSocketContext';
import { useAuth } from '../context/AuthContext';

const RING_TONE_URL =
  'data:audio/wav;base64,UklGRhAAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';

export default function IncomingCallModal() {
  const { addListener } = useWebSocket();
  const { user } = useAuth();
  const [call, setCall] = useState(null); // { call_id, caller_id, caller_name, call_type }
  const audioRef = useRef(null);

  // Listen for `incoming_call` broadcast on every open socket. The Comms page
  // has its own handler that manages the actual RTCPeerConnection; this
  // listener just fires a global overlay so nobody misses the ring.
  useEffect(() => {
    if (!user?.id) return;
    const off = addListener('incoming_call', (data) => {
      setCall({
        call_id: data.call_id,
        caller_id: data.caller_id,
        caller_name: data.caller_name || 'Unknown',
        caller_extension: data.caller_extension,
        call_type: data.call_type || 'audio',
      });
    });
    // Auto-hide when the call is answered / rejected / cancelled elsewhere.
    const clearHandlers = [
      addListener('call_answered', () => setCall(null)),
      addListener('call_rejected', () => setCall(null)),
      addListener('call_ended', () => setCall(null)),
      addListener('call_cancelled', () => setCall(null)),
    ];
    return () => { off(); clearHandlers.forEach(f => f && f()); };
  }, [addListener, user?.id]);

  // Play a soft ringtone loop while the modal is open. Users can silence it
  // via the browser tab mute — we deliberately don't auto-play at full
  // volume so open-plan offices aren't disrupted.
  useEffect(() => {
    if (!call || !audioRef.current) return;
    audioRef.current.volume = 0.5;
    audioRef.current.loop = true;
    audioRef.current.play().catch(() => {});
    return () => {
      try { audioRef.current?.pause(); } catch { /* ignore */ }
    };
  }, [call]);

  const answer = useCallback(() => {
    if (!call) return;
    // Hand off to the Comms page which owns the real peer connection.
    // The call_id + caller_id are carried in the URL so CommsPage can pick
    // the pending offer out of its own listener without re-negotiating.
    const q = new URLSearchParams({
      call: call.call_id,
      caller: call.caller_id,
      type: call.call_type,
      answer: '1',
    });
    window.location.href = `/comms?${q.toString()}`;
    setCall(null);
  }, [call]);

  const reject = useCallback(() => {
    if (!call) return;
    // Emit reject through the same socket the Comms page uses. We can send
    // through the shared context so the backend cleans up its active_calls
    // map + notifies the caller.
    try {
      const evt = new CustomEvent('app:reject-call', { detail: { call_id: call.call_id, caller_id: call.caller_id } });
      window.dispatchEvent(evt);
    } catch { /* ignore */ }
    setCall(null);
  }, [call]);

  if (!call) return null;

  const isVideo = call.call_type === 'video';

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm animate-in fade-in"
      data-testid="incoming-call-modal"
      role="alertdialog"
      aria-label="Incoming call"
    >
      <audio ref={audioRef} src={RING_TONE_URL} preload="auto" />
      <div className="bg-card border border-border rounded-2xl shadow-2xl p-6 w-[92vw] max-w-md text-center">
        <div className="flex items-center justify-center gap-2 mb-2">
          <Sparkles size={12} className="text-emerald-500 animate-pulse" />
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Incoming {isVideo ? 'video' : 'call'}</p>
          <Sparkles size={12} className="text-emerald-500 animate-pulse" />
        </div>
        <div className="mx-auto w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center mb-3 animate-pulse ring-4 ring-primary/20">
          {isVideo ? <Video size={32} className="text-primary" /> : <Phone size={32} className="text-primary" />}
        </div>
        <h3 className="text-lg font-semibold" data-testid="incoming-call-caller">{call.caller_name}</h3>
        {call.caller_extension && (
          <p className="text-xs text-muted-foreground">Extension {call.caller_extension}</p>
        )}
        <div className="flex items-center justify-center gap-4 mt-6">
          <button
            type="button"
            onClick={reject}
            className="w-14 h-14 rounded-full bg-red-500 hover:bg-red-600 text-white flex items-center justify-center shadow-lg transition-transform hover:scale-105"
            data-testid="incoming-call-reject"
            aria-label="Reject call"
          >
            <PhoneOff size={22} />
          </button>
          <button
            type="button"
            onClick={answer}
            className="w-14 h-14 rounded-full bg-emerald-500 hover:bg-emerald-600 text-white flex items-center justify-center shadow-lg transition-transform hover:scale-105 animate-pulse"
            data-testid="incoming-call-answer"
            aria-label="Answer call"
          >
            {isVideo ? <Video size={22} /> : <Phone size={22} />}
          </button>
        </div>
        <p className="text-[10px] text-muted-foreground mt-4">Answering will take you to the Comms page.</p>
      </div>
    </div>
  );
}
