import React, { useState, useEffect, useCallback } from 'react';
import { CalendarDays, Plus, Trash2, RefreshCw, Check, X, Clock, Info, UserCheck } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Textarea } from '../components/ui/textarea';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

const STATUS_COLORS = {
  pending: 'bg-amber-100 text-amber-700 border-amber-200',
  approved: 'bg-green-100 text-green-700 border-green-200',
  declined: 'bg-red-100 text-red-700 border-red-200',
  cancelled: 'bg-slate-100 text-slate-500 border-slate-200',
};

export default function PortalTimeOff() {
  const { user } = useAuth();
  const [types, setTypes] = useState([]);
  const [balance, setBalance] = useState(null);
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showNew, setShowNew] = useState(false);
  const [form, setForm] = useState({ leave_type: '', start_date: '', end_date: '', half_day: false, start_time: '', end_time: '', notes: '', approval_delegate_to: '' });
  const [saving, setSaving] = useState(false);
  // Approval delegation — only show for users who are themselves approvers
  const APPROVER_ROLES = new Set(['admin', 'system_admin', 'Executive Director', 'Adviser',
    'Director', 'Regional Director', 'Manager', 'Coordinator', 'HR']);
  const isApprover = APPROVER_ROLES.has(user?.role || '');
  const [colleagues, setColleagues] = useState([]);
  useEffect(() => {
    if (!isApprover) return;
    api.get('/admin/users').then(r => setColleagues((r.data || []).filter(u => u.id !== user?.id && APPROVER_ROLES.has(u.role)))).catch(() => setColleagues([]));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isApprover]);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [tRes, bRes, rRes] = await Promise.all([
        api.get('/hr/leave/types').catch(() => ({ data: [] })),
        api.get('/hr/leave/balance').catch(() => ({ data: null })),
        api.get('/hr/leave/requests').catch(() => ({ data: [] })),
      ]);
      setTypes(tRes.data || []);
      setBalance(bRes.data);
      setRequests(rRes.data || []);
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const submit = async () => {
    if (!form.leave_type || !form.start_date || !form.end_date) {
      toast.error('Pick a type and date range'); return;
    }
    if (form.end_date < form.start_date) {
      toast.error('End date must be on or after start date'); return;
    }
    setSaving(true);
    try {
      // Compose an ISO note so approvers see partial-day windows even though
      // the schema tracks half_day as a single bit.
      const timeNote = form.half_day && (form.start_time || form.end_time)
        ? `Partial-day window: ${form.start_time || '—'} to ${form.end_time || '—'}\n` : '';
      const payload = {
        leave_type: form.leave_type,
        start_date: form.start_date,
        end_date: form.end_date,
        half_day: !!form.half_day,
        notes: (timeNote + (form.notes || '')).trim(),
      };
      if (isApprover && form.approval_delegate_to) {
        payload.approval_delegate_to = form.approval_delegate_to;
      }
      await api.post('/hr/leave/requests', payload);
      toast.success('Time-off request submitted — manager notified');
      setShowNew(false);
      setForm({ leave_type: '', start_date: '', end_date: '', half_day: false, start_time: '', end_time: '', notes: '' });
      reload();
    } catch (err) { toast.error(err.response?.data?.detail || 'Submission failed'); }
    finally { setSaving(false); }
  };

  const cancel = async (id) => {
    if (!window.confirm('Cancel this request?')) return;
    try {
      await api.put(`/hr/leave/requests/${id}`, { status: 'cancelled' });
      toast.success('Cancelled'); reload();
    } catch (err) { toast.error(err.response?.data?.detail || 'Cancel failed'); }
  };

  const remove = async (id) => {
    if (!window.confirm('Delete this pending request?')) return;
    try {
      await api.delete(`/hr/leave/requests/${id}`);
      toast.success('Removed'); reload();
    } catch (err) { toast.error(err.response?.data?.detail || 'Delete failed'); }
  };

  const mine = requests.filter(r => r.staff_id === user?.id);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        <div className="h-40 bg-muted animate-pulse rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="portal-timeoff-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Time Off</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Submit and track your leave requests</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={reload} data-testid="timeoff-refresh"><RefreshCw size={14} /></Button>
          <Button size="sm" className="gap-1.5" onClick={() => setShowNew(true)} data-testid="timeoff-new-btn"><Plus size={14} /> New request</Button>
        </div>
      </div>

      {/* Balance cards */}
      {balance?.balances?.length > 0 && (
        <Card className="shadow-soft rounded-xl" data-testid="timeoff-balance-card">
          <CardHeader className="pb-3"><CardTitle className="text-base flex items-center gap-2"><CalendarDays size={16} /> {balance.year} balance</CardTitle></CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {balance.balances.map(b => (
                <div key={b.type} className="rounded-lg border border-border p-3" data-testid={`balance-${b.type}`}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="w-2.5 h-2.5 rounded-full" style={{ background: b.color }} />
                    <p className="text-xs font-medium truncate">{b.name}</p>
                  </div>
                  <p className="text-lg font-bold font-heading">{b.remaining} <span className="text-xs font-normal text-muted-foreground">/ {b.allocated} days</span></p>
                  <p className="text-[10px] text-muted-foreground">{b.used} used · {b.paid ? 'Paid' : 'Unpaid'}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* My requests */}
      <Card className="shadow-soft rounded-xl">
        <CardHeader className="pb-3"><CardTitle className="text-base">My requests</CardTitle></CardHeader>
        <CardContent>
          {mine.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">No requests yet. Tap &quot;New request&quot; to submit one.</p>
          ) : (
            <div className="space-y-2">
              {mine.map(r => {
                const t = types.find(x => x.id === r.leave_type);
                return (
                  <div key={r.id} className="flex items-center justify-between border rounded-lg p-3 gap-3 flex-wrap" data-testid={`timeoff-row-${r.id}`}>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="w-2 h-2 rounded-full" style={{ background: t?.color || '#6b7280' }} />
                        <p className="text-sm font-medium truncate">{t?.name || r.leave_type}</p>
                        <Badge className={`${STATUS_COLORS[r.status] || ''} text-[10px]`}>{r.status}</Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {r.start_date}{r.end_date !== r.start_date ? ` → ${r.end_date}` : ''}
                        {r.half_day ? ' · half-day' : ''}
                        {r.days ? ` · ${r.days} day${r.days === 1 ? '' : 's'}` : ''}
                      </p>
                      {r.notes && <p className="text-[11px] text-muted-foreground mt-1 whitespace-pre-line">{r.notes}</p>}
                      {r.decision_note && <p className="text-[11px] mt-1"><strong>Manager:</strong> {r.decision_note}</p>}
                    </div>
                    <div className="flex items-center gap-1">
                      {r.status === 'pending' && (
                        <>
                          <Button size="sm" variant="ghost" className="h-8 gap-1 text-xs" onClick={() => cancel(r.id)} data-testid={`timeoff-cancel-${r.id}`}><X size={12} /> Cancel</Button>
                          <Button size="sm" variant="ghost" className="h-8 text-destructive" onClick={() => remove(r.id)} data-testid={`timeoff-delete-${r.id}`}><Trash2 size={12} /></Button>
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* New request dialog */}
      <Dialog open={showNew} onOpenChange={setShowNew}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>New time-off request</DialogTitle>
            <DialogDescription>Your manager will be notified as soon as you submit.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Type *</Label>
              <Select value={form.leave_type} onValueChange={v => setForm(f => ({ ...f, leave_type: v }))}>
                <SelectTrigger data-testid="timeoff-type-select"><SelectValue placeholder="Pick a leave type" /></SelectTrigger>
                <SelectContent>
                  {types.map(t => (
                    <SelectItem key={t.id} value={t.id}>
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full" style={{ background: t.color }} />
                        <span>{t.name}</span>
                        <span className="text-[10px] text-muted-foreground">({t.paid ? 'paid' : 'unpaid'})</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Start date *</Label><Input type="date" value={form.start_date} onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))} data-testid="timeoff-start" /></div>
              <div className="space-y-1.5"><Label className="text-xs">End date *</Label><Input type="date" value={form.end_date || form.start_date} onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))} data-testid="timeoff-end" /></div>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.half_day} onChange={e => setForm(f => ({ ...f, half_day: e.target.checked }))} data-testid="timeoff-halfday" />
              Half-day / partial-day only
            </label>
            {form.half_day && (
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label className="text-xs flex items-center gap-1"><Clock size={11} /> From</Label><Input type="time" value={form.start_time} onChange={e => setForm(f => ({ ...f, start_time: e.target.value }))} data-testid="timeoff-start-time" /></div>
                <div className="space-y-1.5"><Label className="text-xs flex items-center gap-1"><Clock size={11} /> To</Label><Input type="time" value={form.end_time} onChange={e => setForm(f => ({ ...f, end_time: e.target.value }))} data-testid="timeoff-end-time" /></div>
              </div>
            )}
            <div className="space-y-1.5"><Label className="text-xs">Notes (visible to approver)</Label><Textarea rows={3} value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} placeholder="Reason, coverage plan, contact number…" data-testid="timeoff-notes" /></div>
            {isApprover && (
              <div className="space-y-1.5" data-testid="delegate-picker">
                <Label className="text-xs flex items-center gap-1"><UserCheck size={11} /> Delegate my approvals to (optional)</Label>
                <Select value={form.approval_delegate_to} onValueChange={v => setForm(f => ({ ...f, approval_delegate_to: v }))}>
                  <SelectTrigger data-testid="delegate-select"><SelectValue placeholder="Pick a backup approver…" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">No delegate — leave the queue as-is</SelectItem>
                    {colleagues.map(c => (
                      <SelectItem key={c.id} value={c.id}>{c.name} <span className="text-[10px] text-muted-foreground">· {c.role}</span></SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[10px] text-muted-foreground">Kicks in automatically the day your leave starts and clears the day after it ends.</p>
              </div>
            )}
            <div className="flex items-start gap-2 text-[11px] text-muted-foreground bg-muted/40 rounded p-2">
              <Info size={12} className="mt-0.5 shrink-0" />
              <span>Business-day math is applied automatically. Weekends and holidays are excluded.</span>
            </div>
            <div className="flex gap-3 pt-1">
              <Button variant="outline" className="flex-1" onClick={() => setShowNew(false)}>Cancel</Button>
              <Button className="flex-1 gap-1.5" onClick={submit} disabled={saving} data-testid="timeoff-submit">{saving ? 'Submitting…' : (<><Check size={14} /> Submit</>)}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
