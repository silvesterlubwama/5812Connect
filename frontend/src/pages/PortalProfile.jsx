import React, { useState, useEffect } from 'react';
import { User, Phone, Mail, MapPin, AlertTriangle, Save, Receipt, Clock, Send, Download } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Textarea } from '../components/ui/textarea';
import { portalApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import api from '../services/api';

export default function PortalProfile() {
  const { user } = useAuth();
  const [profile, setProfile] = useState(null);
  const [member, setMember] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: '', phone: '', address: '', emergency_contact: '', notes: '' });
  const [checkins, setCheckins] = useState({ checkins: [], access_logs: [] });
  const [payslips, setPayslips] = useState([]);
  const [timesheets, setTimesheets] = useState([]);
  const [showTimesheet, setShowTimesheet] = useState(false);
  const [tsForm, setTsForm] = useState({ period: new Date().toISOString().slice(0, 7), days_worked: '', pto_days: '', notes: '' });
  const [viewingPayslip, setViewingPayslip] = useState(null);

  const loadHR = async () => {
    try {
      const [ps, ts] = await Promise.all([
        api.get('/hr/payslips/mine'),
        api.get('/hr/timesheets'),
      ]);
      setPayslips(ps.data || []);
      setTimesheets(ts.data || []);
    } catch { /* not an employee */ }
  };

  useEffect(() => {
    const load = async () => {
      try {
        const [profileRes, checkinsRes] = await Promise.all([
          portalApi.profile(),
          portalApi.checkins(),
        ]);
        setProfile(profileRes.data.user);
        setMember(profileRes.data.member);
        setCheckins(checkinsRes.data);
        const u = profileRes.data.user;
        const m = profileRes.data.member;
        setForm({
          name: m?.name || u?.name || '',
          phone: m?.phone || u?.phone || '',
          address: m?.address || '',
          emergency_contact: m?.emergency_contact || '',
          notes: m?.notes || '',
        });
      } catch { toast.error('Failed to load profile'); }
      finally { setLoading(false); }
    };
    load();
    loadHR();
  }, []);

  const submitTimesheet = async () => {
    if (!tsForm.period || !tsForm.days_worked) return toast.error('Period and days_worked required');
    try {
      await api.post('/hr/timesheets', {
        period: tsForm.period,
        days_worked: parseFloat(tsForm.days_worked),
        pto_days: parseFloat(tsForm.pto_days) || 0,
        notes: tsForm.notes,
      });
      toast.success('Timesheet submitted for approval');
      setShowTimesheet(false);
      setTsForm({ period: new Date().toISOString().slice(0, 7), days_worked: '', pto_days: '', notes: '' });
      loadHR();
    } catch (e) { toast.error(e.response?.data?.detail || 'Submission failed'); }
  };

  const withdrawTimesheet = async (t) => {
    if (t.status === 'approved') return toast.error('Approved timesheets cannot be withdrawn');
    if (!window.confirm('Withdraw this timesheet?')) return;
    try {
      await api.delete(`/hr/timesheets/${t.id}`);
      toast.success('Withdrawn');
      loadHR();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const downloadPayslipPdf = async (p) => {
    try {
      const res = await api.get(`/hr/payslips/${p.id}/pdf`, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `payslip-${(p.staff_name || 'staff').replace(/\s+/g, '_')}-${p.period}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (e) { toast.error(e.response?.data?.detail || 'PDF download failed'); }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await portalApi.updateProfile(form);
      toast.success('Profile updated');
      setEditing(false);
    } catch (err) { toast.error(err.response?.data?.detail || 'Update failed'); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" /></div>;

  return (
    <div className="space-y-6 max-w-3xl" data-testid="portal-profile">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold font-heading">My Profile</h1>
          <p className="text-sm text-muted-foreground mt-1">Manage your personal information</p>
        </div>
        <Button variant={editing ? 'default' : 'outline'} className="gap-1.5" onClick={() => editing ? handleSave() : setEditing(true)} disabled={saving} data-testid="portal-edit-profile-btn">
          {editing ? <><Save size={14} /> {saving ? 'Saving...' : 'Save'}</> : 'Edit Profile'}
        </Button>
      </div>

      {/* Profile Card */}
      <Card className="shadow-soft rounded-xl">
        <CardHeader>
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-lg">
              {(profile?.name || '?').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase()}
            </div>
            <div>
              <CardTitle className="text-lg">{profile?.name}</CardTitle>
              <div className="flex gap-2 mt-1">
                <Badge variant="outline" className="text-xs">{profile?.role}</Badge>
                <Badge className={`text-xs ${profile?.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>{profile?.status}</Badge>
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="flex items-center gap-1.5"><User size={12} /> Name</Label>
              {editing ? (
                <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} data-testid="profile-name-input" />
              ) : (
                <p className="text-sm">{profile?.name || '—'}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label className="flex items-center gap-1.5"><Mail size={12} /> Email</Label>
              <p className="text-sm">{profile?.email || '—'}</p>
            </div>
            <div className="space-y-2">
              <Label className="flex items-center gap-1.5"><Phone size={12} /> Phone</Label>
              {editing ? (
                <Input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} data-testid="profile-phone-input" />
              ) : (
                <p className="text-sm">{profile?.phone || member?.phone || '—'}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label className="flex items-center gap-1.5"><MapPin size={12} /> Address</Label>
              {editing ? (
                <Input value={form.address} onChange={e => setForm({ ...form, address: e.target.value })} data-testid="profile-address-input" />
              ) : (
                <p className="text-sm">{member?.address || '—'}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label className="flex items-center gap-1.5"><AlertTriangle size={12} /> Emergency Contact</Label>
              {editing ? (
                <Input value={form.emergency_contact} onChange={e => setForm({ ...form, emergency_contact: e.target.value })} data-testid="profile-emergency-input" />
              ) : (
                <p className="text-sm">{member?.emergency_contact || '—'}</p>
              )}
            </div>
          </div>
          {member && (
            <div className="mt-4 pt-4 border-t border-border">
              <p className="text-xs text-muted-foreground mb-2">Member Details</p>
              <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                {member.group && <span>Group: <strong>{member.group}</strong></span>}
                {member.department && <span>Dept: <strong>{member.department}</strong></span>}
                {member.join_date && <span>Joined: <strong>{member.join_date}</strong></span>}
              </div>
              {(member.badges || []).length > 0 && (
                <div className="flex gap-1.5 mt-2">
                  {member.badges.map((b, i) => (
                    <Badge key={b.badge_name || b.id || i} style={{ backgroundColor: b.badge_color + '20', color: b.badge_color }} className="text-xs">{b.badge_name}</Badge>
                  ))}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Check-in History */}
      <Card className="shadow-soft rounded-xl">
        <CardHeader>
          <CardTitle className="text-sm">Check-in History</CardTitle>
          <CardDescription className="text-xs">Your recent access and attendance records</CardDescription>
        </CardHeader>
        <CardContent>
          {(checkins.checkins || []).length === 0 && (checkins.access_logs || []).length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">No check-in records yet</p>
          ) : (
            <div className="divide-y">
              {(checkins.checkins || []).slice(0, 10).map((c, i) => (
                <div key={c.id || c.check_in_time || `c-${i}`} className="flex items-center justify-between py-2.5">
                  <div>
                    <p className="text-sm">{c.event_name || c.type || 'Check-in'}</p>
                    <p className="text-xs text-muted-foreground">{c.method || 'manual'}</p>
                  </div>
                  <span className="text-xs text-muted-foreground">{new Date(c.check_in_time || c.timestamp).toLocaleString()}</span>
                </div>
              ))}
              {(checkins.access_logs || []).slice(0, 10).map((a, i) => (
                <div key={`a${i}`} className="flex items-center justify-between py-2.5">
                  <div>
                    <p className="text-sm">Access — {a.action || 'scan'}</p>
                    <p className="text-xs text-muted-foreground">{a.access_type || 'access'}</p>
                  </div>
                  <span className="text-xs text-muted-foreground">{new Date(a.timestamp).toLocaleString()}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Statement download for purchasing customers */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">📄 My Account Statement</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <p className="text-xs text-muted-foreground">Download a PDF statement of your purchases.</p>
          <div className="grid grid-cols-2 gap-2">
            <Button variant="outline" size="sm" onClick={async () => {
              try {
                const today = new Date();
                const first = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().slice(0, 10);
                const last = today.toISOString().slice(0, 10);
                const res = await api.get(`/customer-statements/${encodeURIComponent(user?.id || user?.name)}`, { params: { period_from: first, period_to: last }, responseType: 'blob' });
                const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
                const a = document.createElement('a'); a.href = url; a.download = `statement-${first}-${last}.pdf`; a.click(); URL.revokeObjectURL(url);
              } catch (e) { toast.error('Statement unavailable'); }
            }} data-testid="my-statement-month">This Month</Button>
            <Button variant="outline" size="sm" onClick={async () => {
              try {
                const today = new Date();
                const start = new Date(today.getTime() - 90 * 86400000).toISOString().slice(0, 10);
                const end = today.toISOString().slice(0, 10);
                const res = await api.get(`/customer-statements/${encodeURIComponent(user?.id || user?.name)}`, { params: { period_from: start, period_to: end }, responseType: 'blob' });
                const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
                const a = document.createElement('a'); a.href = url; a.download = `statement-${start}-${end}.pdf`; a.click(); URL.revokeObjectURL(url);
              } catch (e) { toast.error('Statement unavailable'); }
            }} data-testid="my-statement-90d">Last 90 Days</Button>
          </div>
        </CardContent>
      </Card>
      {/* MY PAYSLIPS — visible only for staff */}
      {payslips.length > 0 && (
        <Card data-testid="my-payslips-card">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2"><Receipt size={16} /> My Payslips</CardTitle>
            <CardDescription className="text-xs">Payslips issued to you — click to review or download.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="divide-y">
              {payslips.map(p => (
                <div key={p.id} className="py-2 flex items-center justify-between gap-2" data-testid={`payslip-row-${p.id}`}>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium truncate">{p.period} · {p.currency} {(p.net_salary || 0).toLocaleString()}</p>
                    <p className="text-[11px] text-muted-foreground">
                      <Badge variant={p.status === 'paid' ? 'default' : 'secondary'} className="text-[10px] mr-1">{p.status}</Badge>
                      Gross {(p.gross_salary || 0).toLocaleString()} · Allowances {(p.allowances || 0).toLocaleString()} · Deductions {(p.deductions || 0).toLocaleString()}
                      {p.days_worked != null && ` · ${p.days_worked} day(s)`}
                    </p>
                  </div>
                  <div className="flex gap-1">
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setViewingPayslip(p)} data-testid={`payslip-view-${p.id}`}>Review</Button>
                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0" title="Download PDF" onClick={() => downloadPayslipPdf(p)} data-testid={`payslip-pdf-${p.id}`}><Download size={12} /></Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* MY TIMESHEETS */}
      <Card data-testid="my-timesheets-card">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="text-base flex items-center gap-2"><Clock size={16} /> My Timesheets</CardTitle>
            <CardDescription className="text-xs">Log days worked so your manager can approve and roll them into your next payslip.</CardDescription>
          </div>
          <Button size="sm" onClick={() => setShowTimesheet(true)} data-testid="submit-timesheet-btn"><Send size={12} className="mr-1" /> Submit</Button>
        </CardHeader>
        <CardContent>
          {timesheets.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-3">No timesheets yet.</p>
          ) : (
            <div className="divide-y">
              {timesheets.map(t => (
                <div key={t.id} className="py-2 flex items-center justify-between gap-2" data-testid={`timesheet-row-${t.id}`}>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{t.period} · {t.days_worked} day(s){t.pto_days ? ` + ${t.pto_days} PTO` : ''}</p>
                    <p className="text-[11px] text-muted-foreground">
                      <Badge variant={t.status === 'approved' ? 'default' : t.status === 'rejected' ? 'destructive' : 'secondary'} className="text-[10px] mr-1">{t.status}</Badge>
                      {t.review_notes || t.notes || 'Awaiting review'}
                    </p>
                  </div>
                  {(t.status !== 'approved') && (
                    <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive" onClick={() => withdrawTimesheet(t)}>Withdraw</Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* SUBMIT TIMESHEET DIALOG */}
      <Dialog open={showTimesheet} onOpenChange={setShowTimesheet}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Submit Timesheet</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5"><Label className="text-xs">Pay Period</Label>
              <Input type="month" value={tsForm.period} onChange={e => setTsForm({...tsForm, period: e.target.value})} data-testid="ts-period" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5"><Label className="text-xs">Days Worked *</Label>
                <Input type="number" step="0.5" min="0" value={tsForm.days_worked} onChange={e => setTsForm({...tsForm, days_worked: e.target.value})} placeholder="e.g. 20" data-testid="ts-days" />
              </div>
              <div className="space-y-1.5"><Label className="text-xs">PTO Days</Label>
                <Input type="number" step="0.5" min="0" value={tsForm.pto_days} onChange={e => setTsForm({...tsForm, pto_days: e.target.value})} placeholder="e.g. 2" data-testid="ts-pto" />
              </div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Notes / activity summary</Label>
              <Textarea rows={3} value={tsForm.notes} onChange={e => setTsForm({...tsForm, notes: e.target.value})} placeholder="What did you get done this period?" data-testid="ts-notes" />
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowTimesheet(false)}>Cancel</Button>
              <Button className="flex-1" onClick={submitTimesheet} data-testid="ts-submit-btn">Submit for approval</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* PAYSLIP REVIEW DIALOG */}
      <Dialog open={!!viewingPayslip} onOpenChange={(o) => { if (!o) setViewingPayslip(null); }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>Payslip · {viewingPayslip?.period}</DialogTitle></DialogHeader>
          {viewingPayslip && (
            <div className="space-y-3 text-sm" id="payslip-print-area">
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div><span className="text-muted-foreground">Staff:</span> {viewingPayslip.staff_name}</div>
                <div><span className="text-muted-foreground">Department:</span> {viewingPayslip.department || '—'}</div>
                <div><span className="text-muted-foreground">Period:</span> {viewingPayslip.period}</div>
                <div><span className="text-muted-foreground">Status:</span> <Badge className="text-[10px]">{viewingPayslip.status}</Badge></div>
                <div><span className="text-muted-foreground">Working days:</span> {viewingPayslip.working_days || '—'}</div>
                <div><span className="text-muted-foreground">Days worked:</span> {viewingPayslip.days_worked ?? '—'}</div>
                <div><span className="text-muted-foreground">Unpaid leave days:</span> {viewingPayslip.unpaid_leave_days || 0}</div>
                <div><span className="text-muted-foreground">PTO days:</span> {viewingPayslip.pto_days || 0}</div>
              </div>
              <div className="border rounded p-3 space-y-1">
                <div className="flex justify-between text-sm"><span>Gross salary</span><span className="font-mono">{viewingPayslip.currency} {(viewingPayslip.gross_salary || 0).toLocaleString()}</span></div>
                <div className="flex justify-between text-sm text-green-700"><span>+ Allowances</span><span className="font-mono">{(viewingPayslip.allowances || 0).toLocaleString()}</span></div>
                <div className="flex justify-between text-sm text-red-700"><span>− Deductions</span><span className="font-mono">{(viewingPayslip.deductions || 0).toLocaleString()}</span></div>
                {(viewingPayslip.line_items || []).length > 0 && (
                  <div className="text-[11px] text-muted-foreground pl-3 space-y-0.5 pt-1 border-t">
                    {viewingPayslip.line_items.map((li, i) => (
                      <div key={i} className="flex justify-between"><span>· {li.name}{li.details ? ` (${li.details})` : ''}</span><span className="font-mono">{li.type === 'deduction' ? '−' : '+'}{(li.calculated_amount || li.amount || 0).toLocaleString()}</span></div>
                    ))}
                  </div>
                )}
                <div className="flex justify-between text-lg font-bold border-t pt-2 mt-2"><span>Net Pay</span><span className="font-mono">{viewingPayslip.currency} {(viewingPayslip.net_salary || 0).toLocaleString()}</span></div>
              </div>
              {viewingPayslip.paid_at && <p className="text-xs text-muted-foreground">Paid on {viewingPayslip.paid_at.slice(0, 10)}</p>}
              <div className="flex gap-2 pt-2 print:hidden">
                <Button variant="outline" className="flex-1" onClick={() => setViewingPayslip(null)}>Close</Button>
                <Button className="flex-1" onClick={() => downloadPayslipPdf(viewingPayslip)} data-testid="payslip-print-btn"><Download size={12} className="mr-1" /> Download PDF</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

    </div>
  );
}
