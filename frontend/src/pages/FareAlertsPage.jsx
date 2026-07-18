/**
 * FareAlertsPage — CRUD for AI-powered fare-watch alerts. Once created, a
 * background loop (every 24h) checks each active alert and emails the
 * operator when the fare drops at/below the target.
 */
import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { Plus, Trash2, RefreshCw, Loader2, Bell, ExternalLink, Sparkles } from 'lucide-react';
import api from '../services/api';

export default function FareAlertsPage() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [checking, setChecking] = useState(null);

  const fetchAlerts = async () => {
    setLoading(true);
    try {
      const r = await api.get('/fare-alerts');
      setAlerts(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || 'Load failed'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchAlerts(); }, []);

  const del = async (a) => {
    if (!window.confirm(`Delete "${a.name}"?`)) return;
    try { await api.delete(`/fare-alerts/${a.id}`); toast.success('Deleted'); fetchAlerts(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const toggle = async (a) => {
    try {
      await api.put(`/fare-alerts/${a.id}`, { active: !a.active });
      fetchAlerts();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const checkNow = async (a) => {
    setChecking(a.id);
    try {
      const r = await api.post(`/fare-alerts/${a.id}/check-now`);
      if (r.data?.ok) {
        toast.success(r.data.triggered
          ? `Triggered! Price $${r.data.min_price_usd} ≤ target $${a.target_usd} — email sent`
          : `Currently $${r.data.min_price_usd} (target $${a.target_usd})`);
      } else {
        toast.warning(r.data?.error || 'Check returned no data');
      }
      fetchAlerts();
    } catch (e) { toast.error(e.response?.data?.detail || 'Check failed'); }
    finally { setChecking(null); }
  };

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-5xl mx-auto" data-testid="fare-alerts-page">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2"><Bell className="text-amber-500" size={22} /> Fare Alerts</h1>
          <p className="text-sm text-muted-foreground">AI watches selected routes daily and emails you when the fare drops to your target.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchAlerts}><RefreshCw size={14} /></Button>
          <Button size="sm" onClick={() => setCreating(true)} data-testid="fare-alert-new"><Plus size={14} className="mr-1" /> New alert</Button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground"><Loader2 className="animate-spin mr-2" /> Loading…</div>
      ) : alerts.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          <Bell size={28} className="mx-auto mb-2 text-slate-300" />
          <p>No fare alerts yet. Create one to have AI monitor prices daily.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {alerts.map(a => {
            const dropPct = a.last_min_price_usd && a.target_usd ? ((a.last_min_price_usd - a.target_usd) / a.target_usd) * 100 : null;
            return (
              <div key={a.id} className="rounded-lg border border-border p-3 bg-white flex items-center gap-3 flex-wrap" data-testid={`fare-alert-${a.id}`}>
                <Badge className={a.active ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-700'}>{a.active ? 'Active' : 'Paused'}</Badge>
                <div className="flex-1 min-w-[200px]">
                  <p className="font-semibold text-sm">{a.name}</p>
                  <p className="text-[11px] text-muted-foreground">
                    <span className="font-mono">{a.origin} → {a.destination}</span> · {a.date} · {a.passengers} pax · <span className="capitalize">{a.cabin}</span>
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-[10px] text-muted-foreground">Target</p>
                  <p className="text-lg font-bold text-emerald-700">${a.target_usd}</p>
                </div>
                {a.last_min_price_usd != null && (
                  <div className="text-right">
                    <p className="text-[10px] text-muted-foreground">Last found</p>
                    <p className={`text-base font-bold ${a.last_min_price_usd <= a.target_usd ? 'text-emerald-600' : 'text-slate-700'}`}>
                      ${a.last_min_price_usd}
                      {dropPct != null && (
                        <span className="text-[10px] font-normal ml-1">
                          {dropPct >= 0 ? '+' : ''}{dropPct.toFixed(0)}%
                        </span>
                      )}
                    </p>
                  </div>
                )}
                {a.notify_count > 0 && <Badge variant="outline" className="text-[10px]">{a.notify_count} alert{a.notify_count > 1 ? 's' : ''} sent</Badge>}
                {a.last_result?.cheapest?.booking_url && (
                  <a href={a.last_result.cheapest.booking_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-800" title="Book cheapest">
                    <ExternalLink size={14} />
                  </a>
                )}
                <div className="flex gap-1 ml-auto">
                  <Button size="sm" variant="outline" onClick={() => checkNow(a)} disabled={checking === a.id} className="h-7 text-[11px]" data-testid={`fare-check-${a.id}`}>
                    {checking === a.id ? <><Loader2 size={11} className="mr-1 animate-spin" />Checking…</> : <><Sparkles size={11} className="mr-1" />Check now</>}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => toggle(a)} className="h-7 text-[11px]" data-testid={`fare-toggle-${a.id}`}>
                    {a.active ? 'Pause' : 'Resume'}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => del(a)} className="h-7 w-7 p-0 text-rose-600" data-testid={`fare-del-${a.id}`}>
                    <Trash2 size={13} />
                  </Button>
                </div>
                {a.last_check_at && (
                  <p className="basis-full text-[10px] text-muted-foreground italic">Last checked {new Date(a.last_check_at).toLocaleString()}</p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {creating && <FareAlertDialog onClose={() => setCreating(false)} onSaved={() => { setCreating(false); fetchAlerts(); }} />}
    </div>
  );
}

function FareAlertDialog({ onClose, onSaved }) {
  const [form, setForm] = useState({
    name: '', origin: '', destination: '', date: '',
    target_usd: 800, cabin: 'economy', passengers: 1, alert_email: '',
  });
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      await api.post('/fare-alerts', form);
      toast.success('Fare alert created');
      onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={o => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="fare-alert-dialog">
        <DialogHeader><DialogTitle className="flex items-center gap-2"><Bell size={16} className="text-amber-500" /> New Fare Alert</DialogTitle></DialogHeader>
        <div className="space-y-2 text-sm">
          <div><Label className="text-xs">Alert name</Label><Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Uganda trip Sept 2026" data-testid="fa-name" /></div>
          <div className="grid grid-cols-2 gap-2">
            <div><Label className="text-xs">Origin *</Label><Input value={form.origin} onChange={e => setForm({ ...form, origin: e.target.value })} placeholder="JFK" data-testid="fa-origin" /></div>
            <div><Label className="text-xs">Destination *</Label><Input value={form.destination} onChange={e => setForm({ ...form, destination: e.target.value })} placeholder="EBB" data-testid="fa-dest" /></div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div><Label className="text-xs">Date *</Label><Input type="date" value={form.date} onChange={e => setForm({ ...form, date: e.target.value })} data-testid="fa-date" /></div>
            <div><Label className="text-xs">Target price (USD) *</Label><Input type="number" min="1" value={form.target_usd} onChange={e => setForm({ ...form, target_usd: parseFloat(e.target.value) || 0 })} data-testid="fa-target" /></div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div><Label className="text-xs">Passengers</Label><Input type="number" min="1" value={form.passengers} onChange={e => setForm({ ...form, passengers: parseInt(e.target.value, 10) || 1 })} data-testid="fa-pax" /></div>
            <div>
              <Label className="text-xs">Cabin</Label>
              <Select value={form.cabin} onValueChange={v => setForm({ ...form, cabin: v })}>
                <SelectTrigger data-testid="fa-cabin"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="economy">Economy</SelectItem>
                  <SelectItem value="premium_economy">Premium Economy</SelectItem>
                  <SelectItem value="business">Business</SelectItem>
                  <SelectItem value="first">First</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div><Label className="text-xs">Alert email (leave blank to use your account email)</Label><Input value={form.alert_email} onChange={e => setForm({ ...form, alert_email: e.target.value })} placeholder="ops@yourngo.org" data-testid="fa-email" /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={busy || !form.origin || !form.destination || !form.date || !form.target_usd} data-testid="fa-save">
            {busy ? 'Saving…' : 'Create alert'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
