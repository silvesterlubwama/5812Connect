/**
 * Persistent softphone UI mounted from Layout.jsx.
 *
 *  • Green/amber/red registration dot in the header (click to open).
 *  • Floating dial-pad + call controls when a session is active.
 *  • Incoming call toast with Accept / Reject buttons.
 *
 * Design: modelled on a physical desk-phone LED stack — the visible surface
 * shrinks to a tiny status pill when idle, and expands into a full call panel
 * during a session so the operator can keep working without losing context.
 */
import React, { useState } from 'react';
import { Phone, PhoneOff, PhoneIncoming, Mic, MicOff, Pause, Play, Grid3x3, ArrowRightLeft, X, Video, VideoOff } from 'lucide-react';
import { useVoip } from '../../context/VoipContext';
import { Button } from '../ui/button';
import { Input } from '../ui/input';

const statusColor = (s) => ({ registered: 'bg-emerald-500', registering: 'bg-amber-400 animate-pulse',
  failed: 'bg-red-500', unconfigured: 'bg-slate-400', offline: 'bg-slate-400' }[s] || 'bg-slate-400');

const fmtDur = (sec) => `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;

export default function SoftphonePanel() {
  const v = useVoip();
  const [dialerOpen, setDialerOpen] = useState(false);
  const [dialString, setDialString] = useState('');
  const [showKeypad, setShowKeypad] = useState(false);
  const [xferTarget, setXferTarget] = useState('');

  const showIncoming = v.callState === 'incoming';
  const inSession = ['outgoing', 'in-call', 'held'].includes(v.callState);

  // ── the persistent tiny registration pill ───────────────────
  const pill = (
    <button
      type="button"
      onClick={() => setDialerOpen(x => !x)}
      data-testid="softphone-status-pill"
      title={v.statusReason || v.status}
      className="fixed right-4 bottom-4 z-40 flex items-center gap-2 rounded-full bg-slate-900/90 text-white text-xs px-3 py-2 shadow-lg backdrop-blur hover:bg-slate-800 transition"
    >
      <span className={`inline-block w-2 h-2 rounded-full ${statusColor(v.status)}`} />
      <Phone size={13} />
      <span className="hidden sm:inline">{v.extension ? `Ext ${v.extension}` : 'No softphone'}</span>
    </button>
  );

  return (
    <>
      {pill}

      {/* ── incoming call toast ────────────────────────────── */}
      {showIncoming && (
        <div className="fixed right-4 bottom-20 z-50 w-80 rounded-xl bg-white shadow-2xl border border-slate-200 p-4" data-testid="incoming-call-toast">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-full bg-emerald-100 flex items-center justify-center animate-pulse">
              <PhoneIncoming className="text-emerald-600" size={20} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[11px] uppercase tracking-wide text-slate-500">Incoming call</div>
              <div className="font-medium truncate">{v.remotePeer || 'Unknown'}</div>
            </div>
          </div>
          <div className="flex gap-2">
            <Button size="sm" className="flex-1 bg-emerald-600 hover:bg-emerald-700" onClick={() => v.answer()} data-testid="answer-call-btn">
              <Phone size={14} className="mr-1" /> Answer
            </Button>
            <Button size="sm" variant="outline" onClick={() => v.answer({ video: true })} title="Answer with video"
                    data-testid="answer-video-btn">
              <Video size={14} />
            </Button>
            <Button size="sm" variant="outline" className="flex-1" onClick={v.hangup} data-testid="reject-call-btn">
              <PhoneOff size={14} className="mr-1" /> Decline
            </Button>
          </div>
        </div>
      )}

      {/* ── in-call panel ─────────────────────────────────── */}
      {inSession && !showIncoming && (
        <div className="fixed right-4 bottom-20 z-40 w-80 rounded-xl bg-slate-900 text-white shadow-2xl p-4" data-testid="in-call-panel">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="text-[11px] uppercase tracking-wide text-slate-400">
                {v.callState === 'outgoing' ? 'Calling' : v.callState === 'held' ? 'On hold' : 'On call'}
              </div>
              <div className="font-medium truncate">{v.remotePeer || '—'}</div>
              <div className="text-[11px] text-slate-400 mt-0.5">{fmtDur(v.callDurationSec)}</div>
            </div>
            <button onClick={() => setShowKeypad(k => !k)} className="p-1.5 hover:bg-slate-800 rounded" title="Keypad">
              <Grid3x3 size={16} />
            </button>
          </div>

          {/* Video PIP — only when at least one side has video */}
          {(v.isVideoEnabled || v.hasRemoteVideo) && (
            <div className="relative mb-3 rounded-lg overflow-hidden bg-black" data-testid="video-panel">
              <video ref={v._videoRefRemote} autoPlay playsInline className="w-full aspect-video object-cover" />
              {v.isVideoEnabled && (
                <video ref={v._videoRefLocal} autoPlay playsInline muted
                       className="absolute bottom-2 right-2 w-20 aspect-video rounded border border-white/40 object-cover"
                       data-testid="local-video-preview" />
              )}
              {!v.hasRemoteVideo && (
                <div className="absolute inset-0 flex items-center justify-center text-[11px] text-slate-400">
                  Waiting for remote video…
                </div>
              )}
            </div>
          )}

          {showKeypad && (
            <div className="grid grid-cols-3 gap-1.5 mb-3">
              {['1','2','3','4','5','6','7','8','9','*','0','#'].map(k => (
                <button key={k} onClick={() => v.sendDtmf(k)} className="h-10 rounded bg-slate-800 hover:bg-slate-700 text-lg font-medium">
                  {k}
                </button>
              ))}
            </div>
          )}

          <div className="grid grid-cols-4 gap-2 mb-2">
            <Button variant="secondary" size="sm" onClick={v.toggleMute} data-testid="mute-btn"
                    className={`${v.isMuted ? 'bg-amber-500 hover:bg-amber-600 text-white' : ''}`}>
              {v.isMuted ? <MicOff size={14} /> : <Mic size={14} />}
            </Button>
            <Button variant="secondary" size="sm" onClick={v.toggleHold} data-testid="hold-btn"
                    className={`${v.isOnHold ? 'bg-amber-500 hover:bg-amber-600 text-white' : ''}`}>
              {v.isOnHold ? <Play size={14} /> : <Pause size={14} />}
            </Button>
            <Button variant="secondary" size="sm" onClick={v.toggleVideo} data-testid="video-toggle-btn"
                    className={`${v.isVideoEnabled ? 'bg-blue-500 hover:bg-blue-600 text-white' : ''}`}>
              {v.isVideoEnabled ? <Video size={14} /> : <VideoOff size={14} />}
            </Button>
            <Button variant="destructive" size="sm" onClick={v.hangup} data-testid="hangup-btn">
              <PhoneOff size={14} />
            </Button>
          </div>

          <div className="flex gap-1.5 mt-2">
            <Input value={xferTarget} onChange={e => setXferTarget(e.target.value)} placeholder="Transfer to…"
                   className="h-8 text-slate-900 text-xs" data-testid="transfer-input" />
            <Button size="sm" variant="secondary" disabled={!xferTarget}
                    onClick={() => { v.blindTransfer(xferTarget); setXferTarget(''); }}
                    data-testid="transfer-btn">
              <ArrowRightLeft size={13} />
            </Button>
          </div>
        </div>
      )}

      {/* ── dialer popover (opens on pill click when idle) ───── */}
      {dialerOpen && !inSession && !showIncoming && (
        <div className="fixed right-4 bottom-20 z-40 w-72 rounded-xl bg-white shadow-2xl border border-slate-200 p-4" data-testid="dialer-popover">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="text-[11px] uppercase tracking-wide text-slate-500">Softphone</div>
              <div className="font-medium text-sm">
                {v.extension ? `Extension ${v.extension}` : 'Not configured'}
              </div>
              <div className="text-[10px] text-slate-500">{v.statusReason}</div>
            </div>
            <button onClick={() => setDialerOpen(false)} className="p-1 hover:bg-slate-100 rounded">
              <X size={14} />
            </button>
          </div>
          <Input
            value={dialString}
            onChange={e => setDialString(e.target.value)}
            placeholder="Enter number or extension"
            className="mb-3 tabular-nums"
            data-testid="dialer-input"
            onKeyDown={(e) => { if (e.key === 'Enter' && dialString) { v.dial(dialString); setDialString(''); setDialerOpen(false); } }}
          />
          <div className="grid grid-cols-3 gap-1.5 mb-3">
            {['1','2','3','4','5','6','7','8','9','*','0','#'].map(k => (
              <button key={k} onClick={() => setDialString(s => s + k)}
                      className="h-10 rounded bg-slate-100 hover:bg-slate-200 text-lg font-medium">
                {k}
              </button>
            ))}
          </div>
          <Button
            className="w-full bg-emerald-600 hover:bg-emerald-700"
            disabled={!dialString || v.status !== 'registered'}
            onClick={() => { v.dial(dialString); setDialString(''); setDialerOpen(false); }}
            data-testid="dial-btn"
          >
            <Phone size={14} className="mr-1.5" /> Call
          </Button>
        </div>
      )}
    </>
  );
}
