import React, { useState, useEffect } from 'react';
import { User, Phone, Mail, MapPin, AlertTriangle, Save, Receipt, Clock, Send, Download, Camera } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Textarea } from '../components/ui/textarea';
import { portalApi, holidaysApi } from '../services/api';
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
  const [form, setForm] = useState({ name: '', phone: '', address: '', emergency_contact: '', notes: '', date_of_birth: '', gender: '' });
  const [checkins, setCheckins] = useState({ checkins: [], access_logs: [] });
  const [payslips, setPayslips] = useState([]);
  const [timesheets, setTimesheets] = useState([]);
  const [ptoRequests, setPtoRequests] = useState([]);
  const [showTimesheet, setShowTimesheet] = useState(false);
  const [showPto, setShowPto] = useState(false);
  const [ptoForm, setPtoForm] = useState({ start_date: new Date().toISOString().slice(0, 10), end_date: new Date().toISOString().slice(0, 10), reason: '' });
  const [viewingPayslip, setViewingPayslip] = useState(null);
  const [myBadge, setMyBadge] = useState(null);   // { token } once issued
  const [badgeLoading, setBadgeLoading] = useState(false);

  // ISO week helpers — timesheet period is Mon–Sun weeks (server accepts YYYY-Www).
  const isoWeekOf = (d = new Date()) => {
    const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    const day = t.getUTCDay() || 7;
    t.setUTCDate(t.getUTCDate() + 4 - day);
    const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
    const week = Math.ceil((((t - yearStart) / 86400000) + 1) / 7);
    return { period: `${t.getUTCFullYear()}-W${String(week).padStart(2, '0')}`, monday: (() => { const m = new Date(d); const dow = (m.getDay() + 6) % 7; m.setDate(m.getDate() - dow); return m.toISOString().slice(0, 10); })() };
  };
  const _initWeek = isoWeekOf();
  const [tsWeek, setTsWeek] = useState({ period: _initWeek.period, monday: _initWeek.monday, days: [false, false, false, false, false, false, false], pto: 0, notes: '' });
  // Paid / optional-paid public holidays land in this week's grid so staff can
  // see what payroll credits them automatically (iter 316).
  const [payHolidays, setPayHolidays] = useState({});
  const tsYear = new Date(tsWeek.monday).getFullYear();
  useEffect(() => {
    holidaysApi.list({ year: tsYear, country: 'all' })
      .then(r => {
        const map = {};
        for (const h of (r.data || [])) {
          if (h.policy === 'paid' || h.policy === 'optional_paid') map[h.date] = h;
        }
        setPayHolidays(map);
      })
      .catch(() => setPayHolidays({}));
  }, [tsYear]);

  const openMyBadge = async () => {
    setBadgeLoading(true);
    try {
      const r = await api.post('/portal/my-wallet-badge');
      if (r.data?.token) {
        setMyBadge(r.data);
        window.open(`/badge/${r.data.token}`, '_blank');
      }
    } catch (e) { toast.error(e?.response?.data?.detail || 'Badge issuance failed'); }
    setBadgeLoading(false);
  };

  const loadHR = async () => {
    try {
      const [ps, ts, pto] = await Promise.all([
        api.get('/hr/payslips/mine'),
        api.get('/hr/timesheets'),
        api.get('/hr/time-off'),
      ]);
      setPayslips(ps.data || []);
      setTimesheets(ts.data || []);
      setPtoRequests(pto.data || []);
    } catch { /* not an employee */ }
  };

  const submitPto = async () => {
    if (!ptoForm.start_date) return toast.error('Start date required');
    try {
      await api.post('/hr/time-off', {
        start_date: ptoForm.start_date,
        end_date: ptoForm.end_date || ptoForm.start_date,
        reason: ptoForm.reason,
      });
      toast.success('Time-off request submitted');
      setShowPto(false);
      setPtoForm({ start_date: new Date().toISOString().slice(0, 10), end_date: new Date().toISOString().slice(0, 10), reason: '' });
      loadHR();
    } catch (e) { toast.error(e.response?.data?.detail || 'Request failed'); }
  };

  const withdrawPto = async (p) => {
    if (p.status === 'approved') return toast.error('Approved requests cannot be withdrawn — contact HR');
    if (!window.confirm('Withdraw this time-off request?')) return;
    try {
      await api.delete(`/hr/time-off/${p.id}`);
      toast.success('Withdrawn');
      loadHR();
    } catch (e) { toast.error(e.response?.data?.detail || 'Withdraw failed'); }
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
          date_of_birth: m?.date_of_birth || u?.date_of_birth || '',
          gender: m?.gender || u?.gender || '',
        });
      } catch { toast.error('Failed to load profile'); }
      finally { setLoading(false); }
    };
    load();
    loadHR();
  }, []);

  const submitTimesheet = async () => {
    // iter298 — weekly Mon–Sun grid. `entries[]` carries the exact dates worked
    // so payroll can spot short weeks and daily-wage staff get accurate gross.
    const daysWorked = tsWeek.days.filter(Boolean).length;
    if (daysWorked === 0 && !tsWeek.pto) return toast.error('Check at least one day worked or PTO');
    const monday = new Date(tsWeek.monday);
    const entries = tsWeek.days
      .map((worked, i) => {
        const d = new Date(monday); d.setDate(monday.getDate() + i);
        return worked ? { date: d.toISOString().slice(0, 10), day_worked: true } : null;
      })
      .filter(Boolean);
    try {
      await api.post('/hr/timesheets', {
        period: tsWeek.period,
        days_worked: daysWorked,
        pto_days: parseFloat(tsWeek.pto) || 0,
        entries,
        notes: tsWeek.notes,
      });
      toast.success(`Timesheet for ${tsWeek.period} submitted (${daysWorked} day${daysWorked === 1 ? '' : 's'})`);
      setShowTimesheet(false);
      const nxt = isoWeekOf();
      setTsWeek({ period: nxt.period, monday: nxt.monday, days: [false, false, false, false, false, false, false], pto: 0, notes: '' });
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

      {/* My Wallet Badge — iter298 self-service: opens /badge/<token> in a new
          tab where the user can Add-to-Wallet / save the image on their phone. */}
      <Card className="shadow-soft rounded-xl border-primary/30" data-testid="my-badge-card">
        <CardContent className="p-4 flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold">My Wallet Badge</p>
            <p className="text-xs text-muted-foreground">Open a printable, wallet-ready badge. Save Image to your phone or Print from the badge page.</p>
          </div>
          <Button size="sm" className="gap-1.5" onClick={openMyBadge} disabled={badgeLoading} data-testid="portal-open-my-badge">
            <Download size={14} /> {badgeLoading ? 'Preparing…' : 'View & Download'}
          </Button>
        </CardContent>
      </Card>

      {/* Scan Receipt — iter299: mobile-camera capture that POSTs the image to
          /api/finance/receipts/scan; server OCRs it and drafts a JE in the
          Finance Review Queue. */}
      <Card className="shadow-soft rounded-xl" data-testid="portal-scan-receipt-card">
        <CardContent className="p-4 flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold">Scan a receipt</p>
            <p className="text-xs text-muted-foreground">Snap a photo — finance reviews it before posting.</p>
          </div>
          <label className="inline-flex items-center gap-1.5 h-9 rounded-md bg-primary text-primary-foreground px-3 text-sm font-medium cursor-pointer">
            <Camera size={14} />
            <span>Scan</span>
            <input
              type="file"
              accept="image/*,application/pdf"
              capture="environment"
              className="hidden"
              data-testid="portal-scan-receipt-input"
              onChange={async e => {
                const file = e.target.files?.[0];
                if (!file) return;
                const fd = new FormData();
                fd.append('file', file);
                try {
                  const r = await api.post('/finance/receipts/scan', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
                  toast.success(`Receipt sent to finance · ${r.data?.vendor || 'draft'} ${r.data?.total ? '· ' + r.data.total : ''}`);
                } catch (err) {
                  toast.error(err?.response?.data?.detail || 'Scan failed');
                }
                e.target.value = '';
              }}
            />
          </label>
        </CardContent>
      </Card>

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
            <div className="space-y-2">
              <Label className="flex items-center gap-1.5">Date of birth</Label>
              {editing ? (
                <Input type="date" value={form.date_of_birth} onChange={e => setForm({ ...form, date_of_birth: e.target.value })} data-testid="profile-dob-input" />
              ) : (
                <p className="text-sm">{form.date_of_birth || member?.date_of_birth || profile?.date_of_birth || '—'}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label className="flex items-center gap-1.5">Gender</Label>
              {editing ? (
                <select value={form.gender} onChange={e => setForm({ ...form, gender: e.target.value })} data-testid="profile-gender-input" className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm">
                  <option value="">—</option>
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                  <option value="other">Other</option>
                </select>
              ) : (
                <p className="text-sm capitalize">{form.gender || member?.gender || profile?.gender || '—'}</p>
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
                    <div className="text-[11px] text-muted-foreground">
                      <Badge variant={p.status === 'paid' ? 'default' : 'secondary'} className="text-[10px] mr-1">{p.status}</Badge>
                      Gross {(p.gross_salary || 0).toLocaleString()} · Allowances {(p.allowances || 0).toLocaleString()} · Deductions {(p.deductions || 0).toLocaleString()}
                      {p.days_worked != null && ` · ${p.days_worked} day(s)`}
                      {p.holiday_credit?.note && ` · ${p.holiday_credit.note}`}
                    </div>
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
                    <div className="text-[11px] text-muted-foreground">
                      <Badge variant={t.status === 'approved' ? 'default' : t.status === 'rejected' ? 'destructive' : 'secondary'} className="text-[10px] mr-1">{t.status}</Badge>
                      {t.review_notes || t.notes || 'Awaiting review'}
                    </div>
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

      {/* MY TIME-OFF (PTO) REQUESTS */}
      <Card data-testid="my-timeoff-card">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="text-base flex items-center gap-2"><Clock size={16} /> Time Off</CardTitle>
            <CardDescription className="text-xs">Request PTO within &plusmn;7 days of the date. Contact an admin for emergency overrides.</CardDescription>
          </div>
          <Button size="sm" onClick={() => setShowPto(true)} data-testid="request-pto-btn"><Send size={12} className="mr-1" /> Request</Button>
        </CardHeader>
        <CardContent>
          {ptoRequests.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-3">No time-off requests yet.</p>
          ) : (
            <div className="divide-y">
              {ptoRequests.map(p => (
                <div key={p.id} className="py-2 flex items-center justify-between gap-2" data-testid={`pto-row-${p.id}`}>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{p.start_date}{p.end_date && p.end_date !== p.start_date ? ` → ${p.end_date}` : ''} · {p.days || 1} day{(p.days || 1) > 1 ? 's' : ''}</p>
                    <div className="text-[11px] text-muted-foreground">
                      <Badge variant={p.status === 'approved' ? 'default' : p.status === 'rejected' ? 'destructive' : 'secondary'} className="text-[10px] mr-1">{p.status}</Badge>
                      {p.review_notes || p.reason || 'Awaiting review'}
                    </div>
                  </div>
                  {p.status === 'pending' && (
                    <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive" onClick={() => withdrawPto(p)}>Withdraw</Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* REQUEST TIME OFF DIALOG */}
      <Dialog open={showPto} onOpenChange={setShowPto}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Request Time Off</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5"><Label className="text-xs">Start Date</Label>
                <Input type="date" value={ptoForm.start_date} onChange={e => setPtoForm({...ptoForm, start_date: e.target.value})} data-testid="pto-start-date" />
              </div>
              <div className="space-y-1.5"><Label className="text-xs">End Date</Label>
                <Input type="date" value={ptoForm.end_date} onChange={e => setPtoForm({...ptoForm, end_date: e.target.value})} data-testid="pto-end-date" />
              </div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Reason (optional)</Label>
              <Textarea rows={2} value={ptoForm.reason} onChange={e => setPtoForm({...ptoForm, reason: e.target.value})} placeholder="Personal / medical / bereavement…" data-testid="pto-reason" />
            </div>
            <p className="text-[11px] text-muted-foreground">Note: dates must be within &plusmn;7 days of today. For anything further out, contact an admin.</p>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowPto(false)}>Cancel</Button>
              <Button className="flex-1" onClick={submitPto} data-testid="pto-submit-btn"><Send size={12} className="mr-1" /> Submit</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* SUBMIT TIMESHEET DIALOG — weekly Mon–Sun grid (iter298) */}
      <Dialog open={showTimesheet} onOpenChange={setShowTimesheet}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Log this week</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex-1 space-y-1.5">
                <Label className="text-xs">Week starting (Mon)</Label>
                <Input type="date" value={tsWeek.monday} onChange={e => {
                  const d = new Date(e.target.value); const w = isoWeekOf(d);
                  setTsWeek({ ...tsWeek, monday: w.monday, period: w.period });
                }} data-testid="ts-week-monday" />
              </div>
              <div className="text-xs text-muted-foreground bg-muted/40 rounded-md px-2 py-1 font-mono" data-testid="ts-week-period">{tsWeek.period}</div>
            </div>
            <div>
              <Label className="text-xs">Days worked</Label>
              <div className="grid grid-cols-7 gap-1 mt-1.5" data-testid="ts-week-days">
                {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((ltr, i) => {
                  const d = new Date(tsWeek.monday); d.setDate(d.getDate() + i);
                  const label = d.toLocaleDateString(undefined, { day: 'numeric' });
                  const on = tsWeek.days[i];
                  const hol = payHolidays[`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`];
                  return (
                    <button key={i} type="button" onClick={() => { const nd = [...tsWeek.days]; nd[i] = !nd[i]; setTsWeek({ ...tsWeek, days: nd }); }}
                      data-testid={`ts-day-${i}`} title={hol ? `${hol.name} — ${hol.policy === 'paid' ? 'paid holiday' : 'optional paid day off'}` : undefined}
                      className={`relative flex flex-col items-center justify-center h-14 rounded-md border text-xs transition-colors ${on ? 'bg-primary text-primary-foreground border-primary' : hol ? 'bg-amber-50 border-amber-300 hover:bg-amber-100' : 'bg-background hover:bg-muted/40'}`}>
                      <span className="font-semibold">{ltr}</span>
                      <span className="text-[10px] opacity-70">{label}</span>
                      {hol && <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-amber-500" data-testid={`ts-day-holiday-${i}`} />}
                    </button>
                  );
                })}
              </div>
              <p className="text-[11px] text-muted-foreground mt-1">Total: <b>{tsWeek.days.filter(Boolean).length}</b> day(s) worked</p>
              {Object.entries(payHolidays).filter(([date]) => {
                const m = new Date(tsWeek.monday); const s2 = m.toISOString().slice(0, 10);
                const e2 = new Date(m.getTime() + 6 * 86400000).toISOString().slice(0, 10);
                return date >= s2 && date <= e2;
              }).map(([date, h]) => (
                <p key={date} className="text-[11px] text-amber-700 mt-1" data-testid="ts-holiday-note">
                  {h.name} ({date.slice(5)}) — {h.policy === 'paid'
                    ? 'paid holiday, credited automatically. Check it too if you actually worked.'
                    : 'optional paid day off — leave it unchecked to be paid for it.'}
                </p>
              ))}
            </div>
            <div className="space-y-1.5"><Label className="text-xs">PTO days (optional)</Label>
              <Input type="number" step="0.5" min="0" value={tsWeek.pto} onChange={e => setTsWeek({ ...tsWeek, pto: e.target.value })} data-testid="ts-pto" />
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Notes</Label>
              <Textarea rows={2} value={tsWeek.notes} onChange={e => setTsWeek({ ...tsWeek, notes: e.target.value })} placeholder="Optional summary" data-testid="ts-notes" />
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
