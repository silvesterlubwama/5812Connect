import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Badge } from '../components/ui/badge';
import api from '../services/api';
import { toast } from 'sonner';
import { FileText, Download, Mail, Calendar, Search, Clock } from 'lucide-react';

/**
 * CustomerStatementsPage — admin selects a customer + date range to generate
 * branded PDF statements (download or email).  Also configures auto-cadence (weekly/monthly).
 */
export default function CustomerStatementsPage() {
  const [customers, setCustomers] = useState([]);
  const [search, setSearch] = useState('');
  const [periodFrom, setPeriodFrom] = useState(new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10));
  const [periodTo, setPeriodTo] = useState(new Date().toISOString().slice(0, 10));
  const [busyId, setBusyId] = useState(null);
  const [scheduleDlg, setScheduleDlg] = useState(null);
  const [scheduleForm, setScheduleForm] = useState({ cadence: 'monthly', day_of_month: 1, day_of_week: 1, email: '' });
  const [schedules, setSchedules] = useState([]);

  useEffect(() => {
    api.get('/customers').then(r => setCustomers(r.data || [])).catch(() => {});
    api.get('/customer-statements/schedule/list').then(r => setSchedules(r.data || [])).catch(() => {});
  }, []);

  const downloadPdf = async (cust) => {
    setBusyId(cust.id);
    try {
      const res = await api.get(`/customer-statements/${encodeURIComponent(cust.id || cust.name)}`, {
        params: { period_from: periodFrom, period_to: periodTo, format: 'pdf' },
        responseType: 'blob',
      });
      const blob = new Blob([res.data], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `statement-${(cust.name || 'customer').replace(/\W/g, '_')}-${periodFrom}-${periodTo}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('Statement downloaded');
    } catch (e) { toast.error('Download failed'); }
    finally { setBusyId(null); }
  };

  const emailStatement = async (cust) => {
    const overrideEmail = window.prompt('Email to send the statement to:', cust.email || '');
    if (overrideEmail === null) return;
    setBusyId(cust.id);
    try {
      await api.post(`/customer-statements/${encodeURIComponent(cust.id || cust.name)}/email`, {
        period_from: periodFrom,
        period_to: periodTo,
        to_email: overrideEmail || undefined,
      });
      toast.success(`Statement emailed to ${overrideEmail || cust.email}`);
    } catch (e) { toast.error(e.response?.data?.detail || 'Email failed'); }
    finally { setBusyId(null); }
  };

  const saveSchedule = async () => {
    if (!scheduleDlg) return;
    try {
      const payload = {
        customer_id: scheduleDlg.id,
        cadence: scheduleForm.cadence,
        day_of_week: scheduleForm.cadence === 'weekly' ? Number(scheduleForm.day_of_week) : undefined,
        day_of_month: scheduleForm.cadence === 'monthly' ? Number(scheduleForm.day_of_month) : undefined,
        email: scheduleForm.email || undefined,
      };
      await api.post('/customer-statements/schedule', payload);
      toast.success(`Scheduled ${scheduleForm.cadence} statement for ${scheduleDlg.name}`);
      const list = await api.get('/customer-statements/schedule/list');
      setSchedules(list.data || []);
      setScheduleDlg(null);
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const filtered = customers.filter(c => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (c.name || '').toLowerCase().includes(s) || (c.email || '').toLowerCase().includes(s) || (c.phone || '').includes(s);
  });

  return (
    <div className="container mx-auto px-4 py-6 max-w-5xl space-y-5">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><FileText size={22} /> Customer Statements</h1>
        <p className="text-sm text-muted-foreground mt-1">Generate branded PDF statements per customer + period. Schedule auto-emails weekly or monthly.</p>
      </div>

      <Card className="rounded-xl">
        <CardContent className="p-4 grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
          <div>
            <Label className="text-xs">Period From</Label>
            <Input type="date" value={periodFrom} onChange={e => setPeriodFrom(e.target.value)} className="h-9" data-testid="period-from-input" />
          </div>
          <div>
            <Label className="text-xs">Period To</Label>
            <Input type="date" value={periodTo} onChange={e => setPeriodTo(e.target.value)} className="h-9" data-testid="period-to-input" />
          </div>
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input className="pl-9 h-9" placeholder="Search customer..." value={search} onChange={e => setSearch(e.target.value)} data-testid="customer-search" />
          </div>
        </CardContent>
      </Card>

      {schedules.length > 0 && (
        <Card className="rounded-xl">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2"><Clock size={14} /> Active Auto-Statement Schedules</CardTitle>
            <CardDescription className="text-xs">These customers receive automated statements at 08:00 UTC on the configured day.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1">
            {schedules.map((s, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <span><strong>{customers.find(c => c.id === s.customer_id)?.name || s.customer_id}</strong> · {s.cadence} {s.cadence === 'weekly' ? `(day ${s.day_of_week})` : `(day ${s.day_of_month})`}</span>
                <span className="text-muted-foreground">{s.email_override || customers.find(c => c.id === s.customer_id)?.email || '—'}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card className="rounded-xl">
        <CardHeader><CardTitle className="text-sm">Customers ({filtered.length})</CardTitle></CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/40">
              <tr><th className="text-left p-2">Customer</th><th className="text-left p-2">Email / Phone</th><th className="text-right p-2">Spent</th><th className="text-right p-2">Outstanding</th><th className="text-right p-2"></th></tr>
            </thead>
            <tbody className="divide-y">
              {filtered.map(c => (
                <tr key={c.id} data-testid={`customer-row-${c.id}`}>
                  <td className="p-2 font-medium">{c.name}</td>
                  <td className="p-2 text-muted-foreground">{c.email || c.phone || '—'}</td>
                  <td className="text-right p-2">{(c.total_spent || 0).toLocaleString()}</td>
                  <td className="text-right p-2">{c.outstanding ? <span className="text-amber-700 font-medium">{c.outstanding.toLocaleString()}</span> : '—'}</td>
                  <td className="p-2 flex gap-1 justify-end">
                    <Button size="sm" variant="outline" className="h-7 text-xs gap-1" disabled={busyId === c.id} onClick={() => downloadPdf(c)} data-testid={`download-${c.id}`}><Download size={11} /> PDF</Button>
                    <Button size="sm" variant="outline" className="h-7 text-xs gap-1" disabled={busyId === c.id} onClick={() => emailStatement(c)} data-testid={`email-${c.id}`}><Mail size={11} /> Email</Button>
                    <Button size="sm" variant="ghost" className="h-7 text-xs gap-1" onClick={() => { setScheduleDlg(c); setScheduleForm({ cadence: 'monthly', day_of_month: 1, day_of_week: 1, email: c.email || '' }); }} data-testid={`schedule-${c.id}`}><Calendar size={11} /> Auto</Button>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && <tr><td colSpan={5} className="p-6 text-center text-muted-foreground">No customers found.</td></tr>}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Schedule dialog (lightweight inline) */}
      {scheduleDlg && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setScheduleDlg(null)}>
          <Card className="max-w-md w-full" onClick={e => e.stopPropagation()}>
            <CardHeader>
              <CardTitle className="text-base">Auto-Statement for {scheduleDlg.name}</CardTitle>
              <CardDescription className="text-xs">Branded PDF emailed automatically each {scheduleForm.cadence}.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1">
                <Label className="text-xs">Cadence</Label>
                <Select value={scheduleForm.cadence} onValueChange={v => setScheduleForm({...scheduleForm, cadence: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="weekly">Weekly</SelectItem>
                    <SelectItem value="monthly">Monthly</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {scheduleForm.cadence === 'weekly' ? (
                <div className="space-y-1">
                  <Label className="text-xs">Day of week (0=Mon ... 6=Sun)</Label>
                  <Input type="number" min={0} max={6} value={scheduleForm.day_of_week} onChange={e => setScheduleForm({...scheduleForm, day_of_week: e.target.value})} />
                </div>
              ) : (
                <div className="space-y-1">
                  <Label className="text-xs">Day of month (1-28)</Label>
                  <Input type="number" min={1} max={28} value={scheduleForm.day_of_month} onChange={e => setScheduleForm({...scheduleForm, day_of_month: e.target.value})} />
                </div>
              )}
              <div className="space-y-1">
                <Label className="text-xs">Email override (leave blank to use customer's)</Label>
                <Input value={scheduleForm.email} onChange={e => setScheduleForm({...scheduleForm, email: e.target.value})} placeholder={scheduleDlg.email || 'you@example.com'} />
              </div>
              <div className="flex gap-2 pt-2">
                <Button variant="outline" className="flex-1" onClick={() => setScheduleDlg(null)}>Cancel</Button>
                <Button className="flex-1" onClick={saveSchedule} data-testid="save-schedule-btn">Save Schedule</Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
