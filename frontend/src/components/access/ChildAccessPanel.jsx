import React, { useState, useEffect, useCallback } from 'react';
import { ShieldCheck, ShieldOff, Shield, RefreshCw, IdCard } from 'lucide-react';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Label } from '../ui/label';
import { Input } from '../ui/input';
import api from '../../services/api';
import { toast } from 'sonner';

const MODES = [
  { key: 'auto', label: 'Follow family', icon: Shield, hint: "Inherits every restricted site a parent or guardian is cleared for, until they turn 18" },
  { key: 'grant', label: 'Grant by hand', icon: ShieldCheck, hint: 'Pick the sites this child may enter regardless of family access' },
  { key: 'block', label: 'Block', icon: ShieldOff, hint: 'No access anywhere, even if a parent is cleared' },
];

/** Restricted-location access for one child — inherited, granted or blocked. */
export const ChildAccessPanel = ({ childId, childName }) => {
  const [info, setInfo] = useState(null);
  const [locations, setLocations] = useState([]);
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState([]);
  const [reason, setReason] = useState('');

  const load = useCallback(async () => {
    try {
      const [a, l] = await Promise.all([
        api.get(`/access/child-access/${childId}`),
        api.get('/locations'),
      ]);
      setInfo(a.data);
      setPicked(a.data?.override?.location_ids || []);
      setReason(a.data?.override?.reason || '');
      setLocations((l.data || []).filter(x => x.is_restricted));
    } catch { setInfo(null); }
  }, [childId]);

  useEffect(() => { load(); }, [load]);

  const setMode = async (mode) => {
    setBusy(true);
    try {
      await api.put(`/access/child-access/${childId}/override`, { mode, location_ids: picked, reason });
      toast.success(mode === 'auto' ? 'Back to following the family' : mode === 'block' ? 'Access blocked' : 'Access granted');
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not update access'); }
    setBusy(false);
  };

  const issueBadge = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/children/${childId}/wallet-badge`);
      toast.success('Access badge issued');
      if (r.data?.token) window.open(`/badge/${r.data.token}`, '_blank');
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not issue the badge'); }
    setBusy(false);
  };

  if (!info) return null;
  const mode = info.mode || 'auto';

  return (
    <div className="p-3 border border-border rounded-lg space-y-3" data-testid="child-access-panel">
      <div className="flex items-center justify-between gap-2">
        <Label className="flex items-center gap-1.5"><IdCard size={13} /> Restricted-location access</Label>
        <div className="flex gap-1.5">
          <Button size="sm" variant="ghost" className="h-7 w-7 p-0" disabled={busy} onClick={load} data-testid="child-access-refresh"><RefreshCw size={12} /></Button>
          <Button size="sm" variant="outline" className="h-7 text-xs gap-1" disabled={busy} onClick={issueBadge} data-testid="child-access-issue-badge">Issue badge</Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        {info.age != null && <Badge variant="outline" className="text-[10px]">Age {info.age}</Badge>}
        {info.expires_on && (
          <Badge variant="outline" className={`text-[10px] ${info.aged_out ? 'border-rose-300 text-rose-600' : 'border-emerald-200 text-emerald-700'}`}>
            {info.aged_out ? `Expired ${info.expires_on}` : `Valid to ${info.expires_on}`}
          </Badge>
        )}
        {mode !== 'auto' && <Badge variant="secondary" className="text-[10px] capitalize">{mode === 'grant' ? 'Granted by staff' : 'Blocked'}</Badge>}
      </div>

      {info.locations?.length > 0 ? (
        <div className="space-y-1" data-testid="child-access-locations">
          {info.locations.map(l => (
            <div key={l.location_id} className="flex items-center justify-between text-xs rounded bg-accent/30 px-2 py-1.5">
              <span className="truncate">{l.location_name || l.location_id}</span>
              <span className="text-muted-foreground shrink-0">
                {l.via_kind === 'manual' ? 'granted by staff' : `via ${l.via_name || 'family'}`}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground" data-testid="child-access-reason">{info.reason || 'No access'}</p>
      )}

      <div className="grid gap-1.5">
        {MODES.map(m => (
          <button key={m.key} type="button" disabled={busy}
            className={`text-left rounded-lg border p-2 text-xs transition-colors ${mode === m.key ? 'border-primary bg-primary/5' : 'hover:bg-accent/40'}`}
            onClick={() => setMode(m.key)} data-testid={`child-access-mode-${m.key}`}>
            <span className="font-medium flex items-center gap-1.5"><m.icon size={12} /> {m.label}</span>
            <span className="text-muted-foreground">{m.hint}</span>
          </button>
        ))}
      </div>

      {mode === 'grant' && (
        <div className="space-y-2" data-testid="child-access-grant-picker">
          <Label className="text-xs">Sites {childName || 'this child'} may enter</Label>
          {locations.length === 0 && <p className="text-[11px] text-muted-foreground">No restricted locations set up yet.</p>}
          {locations.map(l => (
            <label key={l.id} className="flex items-center gap-2 text-xs cursor-pointer">
              <input type="checkbox" className="accent-primary" checked={picked.includes(l.id)}
                data-testid={`child-access-loc-${l.id}`}
                onChange={e => setPicked(p => e.target.checked ? [...p, l.id] : p.filter(x => x !== l.id))} />
              {l.name}
            </label>
          ))}
          <Input className="h-8 text-xs" placeholder="Reason (optional)" value={reason} onChange={e => setReason(e.target.value)} data-testid="child-access-reason-input" />
          <Button size="sm" className="h-7 text-xs" disabled={busy} onClick={() => setMode('grant')} data-testid="child-access-save-grant">Save grant</Button>
        </div>
      )}
    </div>
  );
};

export default ChildAccessPanel;
