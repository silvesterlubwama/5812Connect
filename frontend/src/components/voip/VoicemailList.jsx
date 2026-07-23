/**
 * Voicemail inbox — pulls voicemails straight from the UCM for the logged-in
 * user's extension. Playing a voicemail auto-marks it as read on the UCM.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { toast } from 'sonner';
import { Play, Trash2, Mail, MailOpen, RefreshCw, Voicemail } from 'lucide-react';
import { Button } from '../ui/button';
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
    const days = Math.floor(hrs / 24);
    if (days < 30) return `${days}d ago`;
    return d.toLocaleDateString();
  } catch { return iso; }
};

export default function VoicemailList() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [playing, setPlaying] = useState(null); // {id, url}
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const r = await api.get('/voip/me/voicemails');
      setItems(Array.isArray(r.data) ? r.data : []);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not load voicemails');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const play = async (vm) => {
    if (playing?.id === vm.id) { setPlaying(null); return; }
    try {
      // Fetch as blob so we can inject an auth-token'd URL and revoke later
      const r = await api.get(`/voip/me/voicemails/${vm.id}/audio`, { responseType: 'blob' });
      const url = URL.createObjectURL(r.data);
      setPlaying({ id: vm.id, url });
      // Optimistically mark as read locally
      setItems(prev => prev.map(x => x.id === vm.id ? { ...x, is_read: true, folder: 'Old' } : x));
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not play voicemail');
    }
  };

  const del = async (vm) => {
    if (!window.confirm(`Delete voicemail from ${vm.from_number || vm.from_name || 'Unknown'}?`)) return;
    try {
      await api.delete(`/voip/me/voicemails/${vm.id}`);
      setItems(prev => prev.filter(x => x.id !== vm.id));
      if (playing?.id === vm.id) setPlaying(null);
      toast.success('Voicemail deleted');
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Delete failed');
    }
  };

  const markRead = async (vm) => {
    try {
      await api.post(`/voip/me/voicemails/${vm.id}/mark-read`);
      setItems(prev => prev.map(x => x.id === vm.id ? { ...x, is_read: true } : x));
    } catch (e) {
      toast.error('Could not mark as read');
    }
  };

  const unreadCount = items.filter(v => !v.is_read).length;

  return (
    <div className="rounded-lg border border-slate-200 bg-white" data-testid="voicemail-list">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <Voicemail size={16} className="text-slate-600" />
          <div>
            <div className="font-medium text-sm">Voicemail</div>
            <div className="text-[11px] text-slate-500">
              {unreadCount > 0 ? `${unreadCount} new · ${items.length} total` : `${items.length} messages`}
            </div>
          </div>
        </div>
        <Button size="sm" variant="ghost" onClick={load} data-testid="refresh-voicemails-btn">
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
        </Button>
      </div>

      {error && <div className="p-4 text-sm text-red-600" data-testid="voicemail-error">{error}</div>}
      {!error && loading && <div className="p-6 text-center text-sm text-slate-500">Loading voicemails…</div>}
      {!loading && !error && items.length === 0 && (
        <div className="p-8 text-center" data-testid="voicemail-empty-state">
          <Voicemail size={32} className="mx-auto text-slate-300 mb-2" />
          <div className="text-sm text-slate-500">No voicemails yet.</div>
          <div className="text-[11px] text-slate-400 mt-1">
            When someone leaves you a message, it will show up here.
          </div>
        </div>
      )}

      <ul className="divide-y divide-slate-100">
        {items.map(vm => (
          <li key={vm.id} className="p-3 hover:bg-slate-50 transition" data-testid={`voicemail-item-${vm.id}`}>
            <div className="flex items-start gap-3">
              <div className={`mt-1 w-2 h-2 rounded-full ${vm.is_read ? 'bg-slate-300' : 'bg-emerald-500'}`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  {vm.is_read
                    ? <MailOpen size={13} className="text-slate-400" />
                    : <Mail size={13} className="text-emerald-600" />}
                  <span className={`text-sm truncate ${vm.is_read ? 'text-slate-600' : 'font-medium text-slate-900'}`}>
                    {vm.from_name || vm.from_number || 'Unknown caller'}
                  </span>
                  {vm.from_name && vm.from_number && (
                    <span className="text-[11px] text-slate-400">{vm.from_number}</span>
                  )}
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  {relTime(vm.received_at)} · {fmtDur(vm.duration_sec)}
                </div>
                {playing?.id === vm.id && (
                  <audio autoPlay controls src={playing.url} className="w-full mt-2" data-testid={`voicemail-player-${vm.id}`}
                         onEnded={() => setPlaying(null)} />
                )}
              </div>
              <div className="flex gap-1">
                <Button size="sm" variant="ghost" onClick={() => play(vm)} title={playing?.id === vm.id ? 'Stop' : 'Play'}
                        data-testid={`voicemail-play-btn-${vm.id}`}>
                  <Play size={14} />
                </Button>
                {!vm.is_read && (
                  <Button size="sm" variant="ghost" onClick={() => markRead(vm)} title="Mark as read"
                          data-testid={`voicemail-mark-read-btn-${vm.id}`}>
                    <MailOpen size={14} />
                  </Button>
                )}
                <Button size="sm" variant="ghost" onClick={() => del(vm)} title="Delete"
                        data-testid={`voicemail-delete-btn-${vm.id}`}
                        className="text-red-600 hover:text-red-700 hover:bg-red-50">
                  <Trash2 size={14} />
                </Button>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
