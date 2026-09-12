/**
 * Phone room — mounted inside CommsPage when the "Phone" pinned sidebar item
 * is selected. Consolidates dialer + recent calls + colleague directory with
 * live BLF (Busy Lamp Field) presence into one surface so staff don't need
 * to bounce across pages to make/receive calls.
 *
 * BLF state comes from `useVoip().blfStates` — the browser subscribes to each
 * colleague's SIP dialog event on the UCM. Registered-only state comes from
 * `registrationMap` (polled every 30 s via /api/voip/blf).
 */
import React, { useEffect, useState, useMemo } from 'react';
import { Phone, Video, PhoneIncoming, PhoneOutgoing, PhoneMissed, RefreshCw, Search, User } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { useVoip } from '../../context/VoipContext';
import api from '../../services/api';

const fmtDur = (sec) => `${Math.floor((sec || 0) / 60)}:${String((sec || 0) % 60).padStart(2, '0')}`;

const relTime = (iso) => {
  if (!iso) return '';
  try {
    const d = new Date(iso.length === 10 ? iso : iso.replace(' ', 'T'));
    const diffMs = Date.now() - d.getTime();
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return d.toLocaleDateString();
  } catch { return iso; }
};

// BLF dot color per state. `undefined` means we have no SIP presence data
// (e.g. UCM Presence not enabled) — fall back to the coarse registration flag.
const blfDot = (state, registeredCoarse) => {
  if (state === 'ringing') return 'bg-amber-400 animate-pulse';
  if (state === 'on-call') return 'bg-red-500';
  if (state === 'idle') return 'bg-emerald-500';
  return registeredCoarse ? 'bg-emerald-500' : 'bg-slate-300';
};

const blfLabel = (state, registeredCoarse) => {
  if (state === 'ringing') return 'Ringing';
  if (state === 'on-call') return 'On a call';
  if (state === 'idle') return 'Available';
  return registeredCoarse ? 'Registered' : 'Offline';
};

export default function PhoneRoom() {
  const v = useVoip();
  const [dialString, setDialString] = useState('');
  const [directory, setDirectory] = useState([]);
  const [history, setHistory] = useState([]);
  const [missed, setMissed] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');

  // A "Call back" notification lands here as /comms?room=phone&call=0700…
  useEffect(() => {
    const n = new URLSearchParams(window.location.search).get('call');
    if (n) setDialString(n);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const [d, h, m] = await Promise.all([
          api.get('/voip/me/directory'),
          api.get('/voip/me/call-history?limit=30').catch(() => ({ data: [] })),
          api.get('/voip/me/missed-calls?limit=20').catch(() => ({ data: [] })),
        ]);
        if (!cancelled) {
          setDirectory(d.data || []);
          setHistory(h.data || []);
          setMissed(m.data || []);
        }
      } catch { /* ignore */ } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    const id = setInterval(load, 60000);   // gentle refresh
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  const callBack = async (m) => {
    call(m.peer);
    try {
      await api.put(`/voip/me/missed-calls/${m.id}/handled`);
      setMissed(prev => prev.filter(x => x.id !== m.id));
    } catch { /* keep it listed if the mark fails */ }
  };

  const dismissMissed = async (m) => {
    setMissed(prev => prev.filter(x => x.id !== m.id));
    try { await api.put(`/voip/me/missed-calls/${m.id}/handled`); } catch { /* ignore */ }
  };

  const filteredDirectory = useMemo(() => {
    if (!filter.trim()) return directory;
    const q = filter.toLowerCase();
    return directory.filter(u =>
      (u.name || '').toLowerCase().includes(q) ||
      (u.extension || '').includes(q) ||
      (u.role || '').toLowerCase().includes(q)
    );
  }, [directory, filter]);

  const call = (target, opts) => {
    if (v.status !== 'registered') {
      toast.error(v.statusReason || 'Softphone not registered');
      return;
    }
    v.dial(target, opts);
  };

  return (
    <div className="flex-1 grid grid-cols-1 lg:grid-cols-[minmax(0,320px)_1fr] gap-4 p-4 overflow-y-auto" data-testid="phone-room">
      {/* ── dial pad ────────────────────────────────────── */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 h-fit">
        <div className="text-[11px] uppercase tracking-wide text-slate-500 mb-2">Dial pad</div>
        <div className="text-sm mb-1">
          {v.extension ? (
            <span className="text-slate-700">Extension <span className="font-mono font-medium">{v.extension}</span></span>
          ) : (
            <span className="text-red-600">No SIP extension assigned</span>
          )}
        </div>
        <div className="text-[11px] text-slate-500 mb-3">{v.statusReason}</div>
        <Input
          value={dialString}
          onChange={e => setDialString(e.target.value)}
          placeholder="Enter number or extension"
          className="mb-3 tabular-nums"
          data-testid="phone-room-dial-input"
          onKeyDown={(e) => { if (e.key === 'Enter' && dialString) { call(dialString); setDialString(''); } }}
        />
        <div className="grid grid-cols-3 gap-1.5 mb-3">
          {['1','2','3','4','5','6','7','8','9','*','0','#'].map(k => (
            <button key={k} onClick={() => setDialString(s => s + k)} data-testid={`phone-room-key-${k}`}
                    className="h-11 rounded bg-slate-100 hover:bg-slate-200 text-lg font-medium transition">
              {k}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Button className="bg-emerald-600 hover:bg-emerald-700" onClick={() => { call(dialString); setDialString(''); }}
                  disabled={!dialString || v.status !== 'registered'} data-testid="phone-room-call-btn">
            <Phone size={13} className="mr-1.5" /> Call
          </Button>
          <Button variant="outline" onClick={() => { call(dialString, { video: true }); setDialString(''); }}
                  disabled={!dialString || v.status !== 'registered'} data-testid="phone-room-video-call-btn">
            <Video size={13} className="mr-1.5" /> Video
          </Button>
        </div>
      </div>

      {/* ── directory + history stacked ────────────────── */}
      <div className="space-y-4 min-w-0">
        {/* Missed calls — rings nobody picked up, with one-tap call-back */}
        {missed.length > 0 && (
          <div className="rounded-lg border border-amber-300 bg-amber-50/60" data-testid="missed-calls-card">
            <div className="flex items-center justify-between px-4 py-3 border-b border-amber-200">
              <div className="flex items-center gap-2">
                <PhoneMissed size={15} className="text-red-500" />
                <div>
                  <div className="font-medium text-sm">Missed calls</div>
                  <div className="text-[11px] text-slate-600">{missed.length} waiting on a call-back</div>
                </div>
              </div>
            </div>
            <ul className="divide-y divide-amber-200/70 max-h-56 overflow-y-auto">
              {missed.map(m => (
                <li key={m.id} className="flex items-center gap-3 px-4 py-2" data-testid={`missed-call-row-${m.id}`}>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm truncate">{m.caller_name || m.peer}</div>
                    <div className="text-[11px] text-slate-600">
                      {m.caller_name ? `${m.peer} · ` : ''}
                      {m.reason === 'declined' ? 'Declined' : m.reason === 'busy' ? 'You were busy' : 'No answer'}
                      {' · '}{relTime(m.created_at)}
                    </div>
                  </div>
                  <Button size="sm" className="h-7 bg-emerald-600 hover:bg-emerald-700 text-[11px]"
                          onClick={() => callBack(m)} data-testid={`missed-call-back-btn-${m.id}`}>
                    <Phone size={11} className="mr-1" /> Call back
                  </Button>
                  <Button size="sm" variant="ghost" className="h-7 text-[11px]"
                          onClick={() => dismissMissed(m)} data-testid={`missed-call-dismiss-btn-${m.id}`}>
                    Dismiss
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Directory */}
        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
            <div>
              <div className="font-medium text-sm">Colleagues</div>
              <div className="text-[11px] text-slate-500">{directory.length} extensions · live BLF</div>
            </div>
            <div className="relative">
              <Search size={13} className="absolute left-2.5 top-2.5 text-slate-400" />
              <Input value={filter} onChange={e => setFilter(e.target.value)}
                     placeholder="Search…" className="pl-8 h-9 w-48" data-testid="phone-directory-filter" />
            </div>
          </div>
          {loading ? (
            <div className="p-6 text-center text-sm text-slate-500">Loading directory…</div>
          ) : filteredDirectory.length === 0 ? (
            <div className="p-8 text-center text-sm text-slate-500" data-testid="phone-directory-empty">
              No colleagues with SIP extensions yet.
            </div>
          ) : (
            <ul className="divide-y divide-slate-100 max-h-72 overflow-y-auto">
              {filteredDirectory.map(u => {
                const state = v.blfStates?.[u.extension];
                const coarse = !!v.registrationMap?.[u.extension];
                return (
                  <li key={u.user_id} className="flex items-center gap-3 px-4 py-2 hover:bg-slate-50"
                      data-testid={`phone-directory-row-${u.user_id}`}>
                    <span className={`w-2 h-2 rounded-full shrink-0 ${blfDot(state, coarse)}`}
                          title={blfLabel(state, coarse)} data-testid={`blf-dot-${u.extension}`} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm truncate">{u.name || u.display_name}</div>
                      <div className="text-[11px] text-slate-500">
                        Ext {u.extension} · {u.role || '—'} · {blfLabel(state, coarse)}
                      </div>
                    </div>
                    <Button size="sm" variant="ghost" onClick={() => call(u.extension)}
                            title={`Call ${u.name}`} data-testid={`call-colleague-btn-${u.extension}`}>
                      <Phone size={13} />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => call(u.extension, { video: true })}
                            title="Video call" data-testid={`video-colleague-btn-${u.extension}`}>
                      <Video size={13} />
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Recent calls */}
        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
            <div>
              <div className="font-medium text-sm">Recent calls</div>
              <div className="text-[11px] text-slate-500">From your UCM CDR</div>
            </div>
            <Button size="sm" variant="ghost" onClick={() => window.location.reload()} title="Refresh">
              <RefreshCw size={13} />
            </Button>
          </div>
          {history.length === 0 ? (
            <div className="p-8 text-center" data-testid="phone-history-empty">
              <Phone size={28} className="mx-auto text-slate-300 mb-2" />
              <div className="text-sm text-slate-500">No recent calls yet.</div>
            </div>
          ) : (
            <ul className="divide-y divide-slate-100 max-h-72 overflow-y-auto">
              {history.map(h => (
                <li key={h.id} className="flex items-center gap-3 px-4 py-2 hover:bg-slate-50"
                    data-testid={`phone-history-row-${h.id}`}>
                  {h.status === 'ANSWERED' || h.status === 'answered'
                    ? (h.direction === 'outgoing'
                        ? <PhoneOutgoing size={14} className="text-slate-500" />
                        : <PhoneIncoming size={14} className="text-emerald-600" />)
                    : <PhoneMissed size={14} className="text-red-500" />}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm truncate">{h.peer || 'Unknown'}</div>
                    <div className="text-[11px] text-slate-500">
                      {relTime(h.started_at)} · {fmtDur(h.duration_sec)}
                    </div>
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => call(h.peer)} title={`Call ${h.peer}`}
                          data-testid={`redial-btn-${h.id}`}>
                    <Phone size={12} />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
