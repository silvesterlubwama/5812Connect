/**
 * SocialWorkPage — staff-facing module for tracking sponsored / restricted /
 * welfare cases. Wires payments to financials + accounting via the backend
 * helper. Lives at /social-work.
 *
 * Structure:
 *   • Header KPIs (cases by category, payments this month)
 *   • Tabs: Cases | Schools | Payments overview
 *   • Case detail dialog with sub-tabs (Overview, Education, Medical, Family,
 *     Goals, Payments, Notes)
 *   • Schools tab: school CRUD + portal-password issuance
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Textarea } from '../components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { HeartHandshake, Plus, RefreshCw, GraduationCap, FileText, DollarSign, Users, Trash2, KeyRound, Copy, Eye, AlertTriangle, BookOpen, Heart, Home, Target, ClipboardList, ClipboardCheck, Search, FileDown, Globe } from 'lucide-react';
import SocialReviewsPanel from '../components/SocialReviewsPanel';
import ReviewsDueWidget from '../components/ReviewsDueWidget';
import ExternalSponsorAutocomplete from '../components/ExternalSponsorAutocomplete';
import ChildDocumentsPanel from '../components/ChildDocumentsPanel';
import ProfileCompletenessWidget from '../components/ProfileCompletenessWidget';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import EmptyState from '../components/EmptyState';

const CATEGORY_LABELS = {
  sponsored: 'Sponsored',
  restricted_location: 'Restricted location',
  welfare_support: 'Welfare support',
  multiple: 'Multiple',
};
const CATEGORY_COLORS = {
  sponsored: 'bg-purple-100 text-purple-700 border-purple-200',
  restricted_location: 'bg-amber-100 text-amber-700 border-amber-200',
  welfare_support: 'bg-blue-100 text-blue-700 border-blue-200',
  multiple: 'bg-rose-100 text-rose-700 border-rose-200',
};
const RISK_COLORS = {
  low: 'bg-emerald-100 text-emerald-700',
  medium: 'bg-amber-100 text-amber-700',
  high: 'bg-red-100 text-red-700',
};
const PAYMENT_KIND_LABELS = {
  tuition: 'School tuition',
  resource: 'Resource / supplies',
  medical: 'Medical support',
  child_support: 'Sponsor payment received',
};

export default function SocialWorkPage() {
  const { user } = useAuth();
  const [cases, setCases] = useState([]);
  const [schools, setSchools] = useState([]);
  const [children, setChildren] = useState([]);
  const [members, setMembers] = useState([]);
  const [paymentsSummary, setPaymentsSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filterCategory, setFilterCategory] = useState('all');
  const [filterStatus, setFilterStatus] = useState('active');
  const [filterRisk, setFilterRisk] = useState('all');
  const [search, setSearch] = useState('');

  // New-case dialog
  const [showNewCase, setShowNewCase] = useState(false);
  const [caseForm, setCaseForm] = useState({
    subject_kind: 'child', subject_id: '', category: 'welfare_support',
    summary: '', risk_level: 'low',
  });

  // Case detail
  const [openCase, setOpenCase] = useState(null);

  // Schools dialog state
  const [showNewSchool, setShowNewSchool] = useState(false);
  const [schoolForm, setSchoolForm] = useState({ name: '', address: '', country: '', phone: '', email: '', head_teacher: '' });
  const [schoolPwModal, setSchoolPwModal] = useState(null);  // newly issued password
  const [showSchoolPasswords, setShowSchoolPasswords] = useState(null);  // school whose passwords we're listing

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [cRes, sRes, chRes, mRes, pSum] = await Promise.all([
        api.get('/social-work/cases', { params: {
          ...(filterCategory !== 'all' ? { category: filterCategory } : {}),
          ...(filterStatus !== 'all' ? { status: filterStatus } : {}),
          ...(filterRisk !== 'all' ? { risk_level: filterRisk } : {}),
          ...(search.trim() ? { search: search.trim() } : {}),
        } }).catch(() => ({ data: [] })),
        api.get('/social-work/schools').catch(() => ({ data: [] })),
        api.get('/children').catch(() => ({ data: [] })),
        api.get('/members', { params: { limit: 500 } }).catch(() => ({ data: [] })),
        api.get('/social-work/payments/summary').catch(() => ({ data: null })),
      ]);
      setCases(cRes.data || []);
      setSchools(sRes.data || []);
      setChildren(Array.isArray(chRes.data) ? chRes.data : []);
      setMembers(Array.isArray(mRes.data) ? mRes.data : (mRes.data?.members || []));
      setPaymentsSummary(pSum.data);
    } finally { setLoading(false); }
  }, [filterCategory, filterStatus, filterRisk, search]);
  useEffect(() => { reload(); }, [reload]);

  const submitCase = async () => {
    if (!caseForm.subject_id) { toast.error('Pick a subject (child/member)'); return; }
    try {
      const r = await api.post('/social-work/cases', caseForm);
      toast.success('Case opened');
      setShowNewCase(false);
      setCaseForm({ subject_kind: 'child', subject_id: '', category: 'welfare_support', summary: '', risk_level: 'low' });
      reload();
      setOpenCase(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const submitSchool = async () => {
    if (!schoolForm.name) { toast.error('Name required'); return; }
    try {
      await api.post('/social-work/schools', schoolForm);
      toast.success('School added');
      setShowNewSchool(false);
      setSchoolForm({ name: '', address: '', country: '', phone: '', email: '', head_teacher: '' });
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const issueSchoolPassword = async (school) => {
    try {
      const r = await api.post(`/social-work/schools/${school.id}/portal-passwords`, { ttl_days: 7 });
      setSchoolPwModal({ ...r.data, school_name: school.name });
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const kpis = (() => {
    const total = cases.length;
    const byCat = {};
    cases.forEach(c => { byCat[c.category] = (byCat[c.category] || 0) + 1; });
    const highRisk = cases.filter(c => c.risk_level === 'high').length;
    return { total, byCat, highRisk };
  })();

  if (loading) return <div className="p-6 space-y-2">{[1, 2, 3].map(i => <div key={i} className="h-20 bg-muted animate-pulse rounded" />)}</div>;

  return (
    <div className="p-6 space-y-5" data-testid="social-work-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold font-heading flex items-center gap-2">
            <HeartHandshake size={22} className="text-primary" /> Social Work & Welfare
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">Track sponsored children, welfare cases, school relationships, and welfare payments</p>
        </div>
        <Button variant="outline" size="sm" onClick={reload} data-testid="sw-refresh-btn"><RefreshCw size={14} className="mr-1" />Refresh</Button>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 sm:grid-cols-6 gap-3" data-testid="sw-kpis">
        <Card className="rounded-xl"><CardContent className="p-3">
          <p className="text-xs text-muted-foreground uppercase">Active cases</p>
          <p className="text-2xl font-bold">{kpis.total}</p>
        </CardContent></Card>
        <Card className="rounded-xl"><CardContent className="p-3">
          <p className="text-xs text-muted-foreground uppercase">High risk</p>
          <p className="text-2xl font-bold text-red-600">{kpis.highRisk}</p>
        </CardContent></Card>
        <Card className="rounded-xl"><CardContent className="p-3">
          <p className="text-xs text-muted-foreground uppercase">Sponsored</p>
          <p className="text-2xl font-bold text-purple-600">{kpis.byCat.sponsored || 0}</p>
        </CardContent></Card>
        <Card className="rounded-xl"><CardContent className="p-3">
          <p className="text-xs text-muted-foreground uppercase">Payments (this month)</p>
          <p className="text-2xl font-bold">{paymentsSummary?.count || 0}</p>
          {paymentsSummary && <p className="text-[10px] text-muted-foreground">in {(paymentsSummary.total_in || 0).toLocaleString()} / out {(paymentsSummary.total_out || 0).toLocaleString()}</p>}
        </CardContent></Card>
        <ReviewsDueWidget onOpenCase={(childId) => {
          const c = cases.find(x => x.subject_id === childId);
          if (c) setOpenCase(c);
        }} />
        <ProfileCompletenessWidget onOpenCase={(childId) => {
          const c = cases.find(x => x.subject_id === childId);
          if (c) setOpenCase(c);
        }} />
      </div>

      <Tabs defaultValue="cases" className="space-y-3">
        <TabsList>
          <TabsTrigger value="cases" data-testid="sw-tab-cases"><Users size={13} className="mr-1" />Cases</TabsTrigger>
          <TabsTrigger value="schools" data-testid="sw-tab-schools"><GraduationCap size={13} className="mr-1" />Schools ({schools.length})</TabsTrigger>
          <TabsTrigger value="payments" data-testid="sw-tab-payments"><DollarSign size={13} className="mr-1" />Payments overview</TabsTrigger>
        </TabsList>

        {/* CASES */}
        <TabsContent value="cases" className="space-y-3">
          <div className="flex flex-wrap gap-2 items-end">
            <div className="relative">
              <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input placeholder="Search name or summary..." className="h-8 pl-7 w-56 text-xs" value={search} onChange={e => setSearch(e.target.value)} data-testid="sw-case-search" />
            </div>
            <Select value={filterCategory} onValueChange={setFilterCategory}>
              <SelectTrigger className="h-8 w-40 text-xs" data-testid="sw-filter-category"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All categories</SelectItem>
                {Object.entries(CATEGORY_LABELS).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={filterStatus} onValueChange={setFilterStatus}>
              <SelectTrigger className="h-8 w-32 text-xs" data-testid="sw-filter-status"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="on_hold">On hold</SelectItem>
                <SelectItem value="discharged">Discharged</SelectItem>
              </SelectContent>
            </Select>
            <Select value={filterRisk} onValueChange={setFilterRisk}>
              <SelectTrigger className="h-8 w-32 text-xs" data-testid="sw-filter-risk"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Any risk</SelectItem>
                <SelectItem value="low">Low</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="high">High</SelectItem>
              </SelectContent>
            </Select>
            <div className="flex-1" />
            <Button size="sm" onClick={() => setShowNewCase(true)} data-testid="sw-new-case-btn"><Plus size={13} className="mr-1" />New Case</Button>
          </div>
          {cases.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-12">No cases match these filters.</p>
          ) : (
            <div className="space-y-2">
              {cases.map(c => (
                <Card key={c.id} className="rounded-xl cursor-pointer hover:border-primary/40" onClick={() => setOpenCase(c)} data-testid={`sw-case-${c.id}`}>
                  <CardContent className="p-3 flex items-center gap-3">
                    <div className="relative">
                      {c.subject_photo_url
                        ? <img src={c.subject_photo_url} alt="" className="h-10 w-10 rounded-full object-cover" />
                        : <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center text-sm">{(c.subject_name || '?').slice(0, 1)}</div>}
                      {c.protection?.has_active_concern && (
                        // Red dot — child has an active protection concern flagged by a recent welfare review.
                        // Tooltip surfaces the specific flag names. role+aria-label give screen-readers the
                        // same information.
                        <span
                          className="absolute -top-0.5 -right-0.5 h-3.5 w-3.5 rounded-full bg-rose-500 border-2 border-background ring-1 ring-rose-700"
                          title={`Active protection concern: ${Object.entries(c.protection.flags || {}).filter(([, v]) => v).map(([k]) => k.replace(/_/g, ' ')).join(', ') || 'unspecified'}`}
                          role="img"
                          aria-label={`Active protection concern: ${Object.entries(c.protection.flags || {}).filter(([, v]) => v).map(([k]) => k.replace(/_/g, ' ')).join(', ') || 'unspecified'}`}
                          data-testid={`sw-case-${c.id}-protection-flag`}
                        />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{c.subject_name}</p>
                      <p className="text-[11px] text-muted-foreground truncate">
                        {c.subject_kind} · {c.education?.school_name ? `${c.education.school_name} · ` : ''}{c.summary || 'No summary'}
                      </p>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Badge variant="outline" className={`text-[10px] ${CATEGORY_COLORS[c.category] || ''}`}>{CATEGORY_LABELS[c.category]}</Badge>
                      <Badge variant="outline" className={`text-[10px] ${RISK_COLORS[c.risk_level] || ''}`}>{c.risk_level}</Badge>
                      {c.status !== 'active' && <Badge variant="secondary" className="text-[10px]">{c.status}</Badge>}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* SCHOOLS */}
        <TabsContent value="schools" className="space-y-3">
          <div className="flex justify-end">
            <Button size="sm" onClick={() => setShowNewSchool(true)} data-testid="sw-new-school-btn"><Plus size={13} className="mr-1" />New School</Button>
          </div>
          {schools.length === 0 ? (
            <EmptyState
              icon={GraduationCap}
              title="No schools yet"
              description="Add the schools your sponsored / restricted-location children attend so you can track fees, performance, and assign portal access."
              action={{ label: 'New school', onClick: () => setShowNewSchool(true), testid: 'sw-empty-new-school-btn' }}
              testid="sw-schools-empty"
            />
          ) : (
            <div className="space-y-2">
              {schools.map(s => (
                <Card key={s.id} className="rounded-xl" data-testid={`sw-school-${s.id}`}>
                  <CardContent className="p-3">
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium">{s.name}</p>
                        <p className="text-[11px] text-muted-foreground">
                          {s.address || '—'}{s.head_teacher ? ` · ${s.head_teacher}` : ''}{s.phone ? ` · ${s.phone}` : ''}
                        </p>
                        <p className="text-[10px] text-muted-foreground mt-1">
                          Portal URL: <span className="font-mono">{window.location.origin}/school-portal/{s.portal_token}</span>
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-[10px]">{s.student_count} active student{s.student_count === 1 ? '' : 's'}</Badge>
                        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => issueSchoolPassword(s)} data-testid={`sw-issue-pw-${s.id}`}><KeyRound size={11} className="mr-1" />Issue password</Button>
                        <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setShowSchoolPasswords(s)} data-testid={`sw-list-pw-${s.id}`}><Eye size={11} className="mr-1" />Passwords</Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* PAYMENTS overview */}
        <TabsContent value="payments" className="space-y-3">
          {paymentsSummary ? (
            <Card className="rounded-xl">
              <CardHeader>
                <CardTitle className="text-base">Welfare payments — {paymentsSummary.period}</CardTitle>
                <CardDescription className="text-xs">All payments recorded against social work cases. Auto-posted to the financial + accounting ledgers.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                  {Object.entries(PAYMENT_KIND_LABELS).map(([k, lbl]) => (
                    <div key={k} className="p-3 rounded-lg border">
                      <p className="text-[10px] uppercase text-muted-foreground">{lbl}</p>
                      <p className="text-lg font-bold">{(paymentsSummary.by_kind?.[k] || 0).toLocaleString()}</p>
                    </div>
                  ))}
                </div>
                <h4 className="text-xs uppercase font-semibold text-muted-foreground mb-2">Top recipients</h4>
                {paymentsSummary.by_subject?.length === 0
                  ? <p className="text-xs text-muted-foreground">No payments this period.</p>
                  : (
                    <div className="space-y-1">
                      {paymentsSummary.by_subject.slice(0, 12).map((s, i) => (
                        <div key={i} className="flex justify-between text-xs p-1.5 rounded hover:bg-muted/50">
                          <span>{s.subject_name}</span>
                          <span className="font-medium">{s.total.toLocaleString()} <span className="text-muted-foreground">({s.count} payment{s.count === 1 ? '' : 's'})</span></span>
                        </div>
                      ))}
                    </div>
                  )}
              </CardContent>
            </Card>
          ) : <p className="text-sm text-muted-foreground text-center py-12">No payment data yet.</p>}
        </TabsContent>
      </Tabs>

      {/* NEW CASE DIALOG */}
      <Dialog open={showNewCase} onOpenChange={setShowNewCase}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Open a new case</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Subject kind *</Label>
              <Select value={caseForm.subject_kind} onValueChange={v => setCaseForm({ ...caseForm, subject_kind: v, subject_id: '' })}>
                <SelectTrigger data-testid="sw-form-subject-kind"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="child">Child</SelectItem>
                  <SelectItem value="member">Member / Adult</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{caseForm.subject_kind === 'child' ? 'Child' : 'Member'} *</Label>
              <Select value={caseForm.subject_id} onValueChange={v => setCaseForm({ ...caseForm, subject_id: v })}>
                <SelectTrigger data-testid="sw-form-subject-id"><SelectValue placeholder={`Pick ${caseForm.subject_kind}...`} /></SelectTrigger>
                <SelectContent>
                  {(caseForm.subject_kind === 'child' ? children : members).map(s => (
                    <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Category *</Label>
              <Select value={caseForm.category} onValueChange={v => setCaseForm({ ...caseForm, category: v })}>
                <SelectTrigger data-testid="sw-form-category"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(CATEGORY_LABELS).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Risk level</Label>
              <Select value={caseForm.risk_level} onValueChange={v => setCaseForm({ ...caseForm, risk_level: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">Low</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Summary</Label>
              <Textarea rows={3} value={caseForm.summary} onChange={e => setCaseForm({ ...caseForm, summary: e.target.value })} placeholder="One-line context that frames this case..." data-testid="sw-form-summary" />
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowNewCase(false)}>Cancel</Button>
              <Button className="flex-1" onClick={submitCase} disabled={!caseForm.subject_id} data-testid="sw-form-submit">Open Case</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* NEW SCHOOL DIALOG */}
      <Dialog open={showNewSchool} onOpenChange={setShowNewSchool}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Add a school</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label className="text-xs">Name *</Label><Input value={schoolForm.name} onChange={e => setSchoolForm({ ...schoolForm, name: e.target.value })} data-testid="school-form-name" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Country</Label><Input value={schoolForm.country} onChange={e => setSchoolForm({ ...schoolForm, country: e.target.value })} /></div>
              <div className="space-y-1.5"><Label className="text-xs">Phone</Label><Input value={schoolForm.phone} onChange={e => setSchoolForm({ ...schoolForm, phone: e.target.value })} /></div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Address</Label><Input value={schoolForm.address} onChange={e => setSchoolForm({ ...schoolForm, address: e.target.value })} /></div>
            <div className="space-y-1.5"><Label className="text-xs">Email</Label><Input type="email" value={schoolForm.email} onChange={e => setSchoolForm({ ...schoolForm, email: e.target.value })} /></div>
            <div className="space-y-1.5"><Label className="text-xs">Head teacher</Label><Input value={schoolForm.head_teacher} onChange={e => setSchoolForm({ ...schoolForm, head_teacher: e.target.value })} /></div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowNewSchool(false)}>Cancel</Button>
              <Button className="flex-1" onClick={submitSchool} disabled={!schoolForm.name} data-testid="school-form-submit">Add</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* PORTAL PASSWORD ISSUED — one-time-display modal */}
      <Dialog open={!!schoolPwModal} onOpenChange={(o) => { if (!o) setSchoolPwModal(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Password issued for {schoolPwModal?.school_name}</DialogTitle>
            <DialogDescription className="text-xs">Copy these credentials NOW — the password is not retrievable later. Send via your preferred secure channel.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/30 rounded p-3 text-xs">
              <p><strong>URL:</strong></p>
              <div className="font-mono break-all flex items-start gap-1 mt-1">
                <span className="flex-1">{window.location.origin}{schoolPwModal?.portal_url_path}</span>
                <button onClick={() => { navigator.clipboard.writeText(`${window.location.origin}${schoolPwModal.portal_url_path}`); toast.success('Copied'); }} className="text-primary"><Copy size={11} /></button>
              </div>
              <p className="mt-2"><strong>Password:</strong></p>
              <div className="font-mono break-all flex items-start gap-1 mt-1">
                <span className="flex-1" data-testid="issued-password">{schoolPwModal?.password_plaintext}</span>
                <button onClick={() => { navigator.clipboard.writeText(schoolPwModal.password_plaintext); toast.success('Copied'); }} className="text-primary"><Copy size={11} /></button>
              </div>
              <p className="mt-2 text-[10px]">Expires: {schoolPwModal?.expires_at?.slice(0, 16).replace('T', ' ')} UTC ({schoolPwModal?.ttl_days}-day TTL)</p>
            </div>
            <Button className="w-full" onClick={() => setSchoolPwModal(null)}>Done</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* PASSWORDS LIST DIALOG */}
      <SchoolPasswordsDialog school={showSchoolPasswords} onClose={() => setShowSchoolPasswords(null)} onReload={reload} />

      {/* CASE DETAIL DIALOG */}
      <CaseDetailDialog
        caseId={openCase?.id}
        schools={schools}
        members={members}
        onClose={() => { setOpenCase(null); reload(); }}
      />
    </div>
  );
}

// =================================================================
// SCHOOL PASSWORDS LIST DIALOG
// =================================================================
function SchoolPasswordsDialog({ school, onClose, onReload }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => {
    if (!school) return;
    setLoading(true);
    try {
      const r = await api.get(`/social-work/schools/${school.id}/portal-passwords`);
      setRows(r.data || []);
    } finally { setLoading(false); }
  }, [school]);
  useEffect(() => { load(); }, [load]);

  const revoke = async (id) => {
    if (!window.confirm('Revoke this password? Anyone using it will be logged out within minutes.')) return;
    try {
      await api.delete(`/social-work/schools/${school.id}/portal-passwords/${id}`);
      toast.success('Revoked');
      load();
      onReload?.();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  return (
    <Dialog open={!!school} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Portal passwords — {school?.name}</DialogTitle></DialogHeader>
        <div className="space-y-2 mt-2">
          {loading && [1, 2].map(i => <div key={i} className="h-14 bg-muted animate-pulse rounded" />)}
          {!loading && rows.length === 0 && <p className="text-sm text-muted-foreground text-center py-6">No passwords issued yet.</p>}
          {!loading && rows.map(r => (
            <div key={r.id} className="p-2 rounded border text-xs flex items-center justify-between gap-2 flex-wrap">
              <div className="flex-1">
                <p className="font-medium">Issued by {r.issued_by_name} <span className="text-muted-foreground">· {r.issued_at?.slice(0, 16).replace('T', ' ')}</span></p>
                <p className="text-muted-foreground text-[10px]">Expires {r.expires_at?.slice(0, 16).replace('T', ' ')} {r.last_used_at ? `· last used ${r.last_used_at.slice(0, 16).replace('T', ' ')}` : '· never used'}{r.note ? ` · "${r.note}"` : ''}</p>
              </div>
              {r.is_active
                ? <Badge className="bg-emerald-100 text-emerald-700 text-[10px]">Active</Badge>
                : <Badge variant="outline" className="text-[10px]">{r.revoked ? 'Revoked' : 'Expired'}</Badge>}
              {r.is_active && <Button size="sm" variant="ghost" className="h-7 text-destructive" onClick={() => revoke(r.id)}><Trash2 size={12} /></Button>}
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// =================================================================
// CASE DETAIL DIALOG — tabbed
// =================================================================
function CaseDetailDialog({ caseId, schools, members, onClose }) {
  const [caseDoc, setCaseDoc] = useState(null);
  const [notes, setNotes] = useState([]);
  const [payments, setPayments] = useState([]);
  const [complianceSchema, setComplianceSchema] = useState(null);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(null);  // local edits (education/medical/family/goals)
  const [complianceEdits, setComplianceEdits] = useState({});
  const [newNote, setNewNote] = useState({ kind: 'visit', body: '', is_confidential: false });
  const [newPayment, setNewPayment] = useState({ kind: 'tuition', amount: '', currency: 'UGX', date: new Date().toISOString().slice(0, 10), paid_to: '', source: 'org_fund', notes: '' });
  // When a manual sponsor's email matches an existing in-system user we surface a
  // "link this account instead?" banner so org-wide identity stays unified.
  const [sponsorUserMatch, setSponsorUserMatch] = useState(null);

  // Watch the manual-sponsor email and check the members directory for a match.
  // Debounced 400ms so we don't spam the API on every keystroke. Cleared when
  // the user dismisses, links, or switches sponsor modes.
  useEffect(() => {
    const email = (caseDoc?.sponsor_manual?.email || '').trim().toLowerCase();
    if (!email || email.length < 5 || !caseDoc?.sponsor_manual_mode) {
      setSponsorUserMatch(null);
      return;
    }
    const t = setTimeout(() => {
      const hit = (members || []).find(m => (m.email || '').toLowerCase() === email);
      setSponsorUserMatch(hit || null);
    }, 400);
    return () => clearTimeout(t);
  }, [caseDoc?.sponsor_manual?.email, caseDoc?.sponsor_manual_mode, members]);

  const reload = useCallback(async () => {
    if (!caseId) { setCaseDoc(null); setNotes([]); setPayments([]); setComplianceSchema(null); return; }
    setLoading(true);
    try {
      const [cR, nR, pR] = await Promise.all([
        api.get(`/social-work/cases/${caseId}`),
        api.get(`/social-work/cases/${caseId}/notes`),
        api.get(`/social-work/cases/${caseId}/payments`),
      ]);
      setCaseDoc(cR.data);
      setEditing({
        education: cR.data.education || {},
        medical: cR.data.medical || {},
        family: cR.data.family || {},
        goals: cR.data.goals || [],
      });
      setComplianceEdits(cR.data.compliance || {});
      setNotes(nR.data || []);
      setPayments(pR.data || []);
      // Pull the country-specific schema based on what the backend resolved
      const code = cR.data.compliance_country_code || 'GENERIC';
      try {
        const sR = await api.get(`/social-work/compliance/${code}`);
        setComplianceSchema(sR.data);
      } catch { setComplianceSchema(null); }
    } finally { setLoading(false); }
  }, [caseId]);
  useEffect(() => { reload(); }, [reload]);

  const saveSection = async (field) => {
    try {
      await api.put(`/social-work/cases/${caseId}`, { [field]: editing[field] });
      toast.success('Saved');
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const saveCompliance = async () => {
    try {
      await api.put(`/social-work/cases/${caseId}`, { compliance: complianceEdits });
      toast.success('Compliance fields saved');
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const downloadReport = async () => {
    try {
      const r = await api.get(`/social-work/cases/${caseId}/report`, { responseType: 'blob' });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `profile-${(caseDoc?.subject_name || 'beneficiary').replace(/\s+/g, '_')}-${caseId}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success('Profile report downloaded');
    } catch (e) { toast.error(e.response?.data?.detail || 'Download failed'); }
  };

  const updateStatus = async (status) => {
    try {
      await api.put(`/social-work/cases/${caseId}`, { status });
      toast.success(`Status: ${status}`);
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const addNote = async () => {
    if (!newNote.body.trim()) return;
    try {
      await api.post(`/social-work/cases/${caseId}/notes`, newNote);
      toast.success('Note added');
      setNewNote({ kind: 'visit', body: '', is_confidential: false });
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const addPayment = async () => {
    if (!newPayment.amount) return;
    try {
      await api.post(`/social-work/cases/${caseId}/payments`, { ...newPayment, amount: parseFloat(newPayment.amount) });
      toast.success('Payment recorded — wired to financials + accounting');
      setNewPayment({ kind: 'tuition', amount: '', currency: 'UGX', date: new Date().toISOString().slice(0, 10), paid_to: '', source: 'org_fund', notes: '' });
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const deletePayment = async (id) => {
    if (!window.confirm('Delete this payment? The corresponding finance entry will also be removed.')) return;
    try {
      await api.delete(`/social-work/cases/${caseId}/payments/${id}`);
      toast.success('Payment removed (ledger reversal required — handle on /accounting if needed)');
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  if (!caseId) return null;

  return (
    <Dialog open={!!caseId} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-5xl w-[96vw] max-h-[92vh] overflow-y-auto p-5 sm:p-6" data-testid="sw-case-detail-dialog" aria-describedby={undefined}>
        <DialogHeader className="space-y-1">
          <DialogTitle className="flex items-center gap-2 flex-wrap">
            {caseDoc?.subject_photo_url && <img src={caseDoc.subject_photo_url} alt="" className="h-8 w-8 rounded-full object-cover" />}
            <span>{caseDoc?.subject_name || 'Case'}</span>
            <Button size="sm" variant="outline" className="ml-auto h-7 text-xs" onClick={downloadReport} disabled={!caseDoc} data-testid="cd-download-report-btn">
              <FileDown size={11} className="mr-1" />Download Profile Report
            </Button>
          </DialogTitle>
          {caseDoc && (
            <div className="text-xs flex flex-wrap items-center gap-2 mt-1" data-testid="cd-case-meta">
              <Badge variant="outline" className={`text-[10px] ${CATEGORY_COLORS[caseDoc.category]}`}>{CATEGORY_LABELS[caseDoc.category]}</Badge>
              <Badge variant="outline" className={`text-[10px] ${RISK_COLORS[caseDoc.risk_level]}`}>{caseDoc.risk_level} risk</Badge>
              <Badge variant="secondary" className="text-[10px]">{caseDoc.status}</Badge>
              <span className="text-muted-foreground">opened {caseDoc.opened_at?.slice(0, 10)} by {caseDoc.opened_by_name}</span>
            </div>
          )}
        </DialogHeader>

        {loading || !caseDoc ? (
          <div className="space-y-2 mt-3">{[1, 2, 3].map(i => <div key={i} className="h-16 bg-muted animate-pulse rounded" />)}</div>
        ) : (
          <Tabs defaultValue="overview" className="mt-3">
            {/* Tab strip: scrolls horizontally on narrow screens so tabs never wrap onto two rows.
                Abbreviated labels keep each trigger compact while testids remain stable. */}
            <TabsList className="w-full flex flex-nowrap overflow-x-auto justify-start gap-0.5 h-auto p-1">
              <TabsTrigger value="overview" data-testid="cd-tab-overview" className="text-xs px-2.5 py-1.5 shrink-0">Overview</TabsTrigger>
              <TabsTrigger value="education" data-testid="cd-tab-education" className="text-xs px-2.5 py-1.5 shrink-0"><BookOpen size={11} className="mr-1" />Education</TabsTrigger>
              <TabsTrigger value="medical" data-testid="cd-tab-medical" className="text-xs px-2.5 py-1.5 shrink-0"><Heart size={11} className="mr-1" />Medical</TabsTrigger>
              <TabsTrigger value="family" data-testid="cd-tab-family" className="text-xs px-2.5 py-1.5 shrink-0"><Home size={11} className="mr-1" />Family</TabsTrigger>
              <TabsTrigger value="compliance" data-testid="cd-tab-compliance" className="text-xs px-2.5 py-1.5 shrink-0"><Globe size={11} className="mr-1" />Compliance</TabsTrigger>
              <TabsTrigger value="goals" data-testid="cd-tab-goals" className="text-xs px-2.5 py-1.5 shrink-0"><Target size={11} className="mr-1" />Goals</TabsTrigger>
              <TabsTrigger value="payments" data-testid="cd-tab-payments" className="text-xs px-2.5 py-1.5 shrink-0"><DollarSign size={11} className="mr-1" />Payments ({payments.length})</TabsTrigger>
              <TabsTrigger value="notes" data-testid="cd-tab-notes" className="text-xs px-2.5 py-1.5 shrink-0"><ClipboardList size={11} className="mr-1" />Notes ({notes.length})</TabsTrigger>
              <TabsTrigger value="school_reviews" data-testid="cd-tab-school-reviews" className="text-xs px-2.5 py-1.5 shrink-0"><GraduationCap size={11} className="mr-1" />School</TabsTrigger>
              <TabsTrigger value="welfare_visits" data-testid="cd-tab-welfare-visits" className="text-xs px-2.5 py-1.5 shrink-0"><ClipboardCheck size={11} className="mr-1" />Welfare</TabsTrigger>
              <TabsTrigger value="documents" data-testid="cd-tab-documents" className="text-xs px-2.5 py-1.5 shrink-0"><FileText size={11} className="mr-1" />Documents</TabsTrigger>
            </TabsList>

            {/* OVERVIEW */}
            <TabsContent value="overview" className="space-y-4 mt-4">
              <div className="space-y-1.5">
                <Label className="text-xs">Summary</Label>
                <Textarea rows={3} value={caseDoc.summary || ''}
                  onChange={e => setCaseDoc({ ...caseDoc, summary: e.target.value })}
                  onBlur={() => api.put(`/social-work/cases/${caseId}`, { summary: caseDoc.summary }).catch(() => {})}
                  data-testid="cd-summary"
                />
              </div>

              {/* Support type + Risk + Status — all three now editable inline. Was display-only before. */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                <div className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground uppercase tracking-wide">Support type</Label>
                  <Select value={caseDoc.category} onValueChange={async v => {
                    const prev = caseDoc.category;
                    setCaseDoc({ ...caseDoc, category: v });
                    try {
                      await api.put(`/social-work/cases/${caseId}`, { category: v });
                      toast.success('Support type updated');
                    } catch (e) {
                      setCaseDoc({ ...caseDoc, category: prev });
                      toast.error(e.response?.data?.detail || 'Update failed');
                    }
                  }}>
                    <SelectTrigger className="h-8 text-xs" data-testid="cd-category"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {Object.entries(CATEGORY_LABELS).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground uppercase tracking-wide">Risk level</Label>
                  <Select value={caseDoc.risk_level} onValueChange={async v => {
                    const prev = caseDoc.risk_level;
                    setCaseDoc({ ...caseDoc, risk_level: v });
                    try {
                      await api.put(`/social-work/cases/${caseId}`, { risk_level: v });
                      toast.success('Risk level updated');
                    } catch (e) {
                      setCaseDoc({ ...caseDoc, risk_level: prev });
                      toast.error(e.response?.data?.detail || 'Update failed');
                    }
                  }}>
                    <SelectTrigger className="h-8 text-xs" data-testid="cd-risk-level"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">Low</SelectItem>
                      <SelectItem value="medium">Medium</SelectItem>
                      <SelectItem value="high">High</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground uppercase tracking-wide">Case status</Label>
                  <Select value={caseDoc.status} onValueChange={updateStatus}>
                    <SelectTrigger className="h-8 text-xs" data-testid="cd-status"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="active">Active</SelectItem>
                      <SelectItem value="on_hold">On hold</SelectItem>
                      <SelectItem value="discharged">Discharged</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* SPONSOR — supports two modes: link an existing user, OR enter a manual sponsor
                  (external donor not in the system). Toggle controls which mode is active.
                  Stored as case.sponsor_member_id (existing) or case.sponsor_manual {name,email,phone,notes}. */}
              <div className="border-t pt-3 space-y-2">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <Label className="text-xs font-semibold">Sponsor</Label>
                  <div className="flex rounded border overflow-hidden text-[11px]">
                    <button
                      type="button"
                      className={`px-2.5 py-1 ${!caseDoc.sponsor_manual_mode ? 'bg-primary text-primary-foreground' : 'bg-background hover:bg-muted'}`}
                      onClick={() => setCaseDoc({ ...caseDoc, sponsor_manual_mode: false })}
                      data-testid="cd-sponsor-mode-existing"
                    >Existing user</button>
                    <button
                      type="button"
                      className={`px-2.5 py-1 border-l ${caseDoc.sponsor_manual_mode || caseDoc.sponsor_manual ? 'bg-primary text-primary-foreground' : 'bg-background hover:bg-muted'}`}
                      onClick={() => setCaseDoc({ ...caseDoc, sponsor_manual_mode: true })}
                      data-testid="cd-sponsor-mode-manual"
                    >Manual entry</button>
                  </div>
                </div>

                {(caseDoc.sponsor_manual_mode || caseDoc.sponsor_manual) ? (
                  <>
                    {/* In-system user match prompt — if the manual email matches an
                        existing app user, suggest linking that account instead so
                        org-wide identity stays unified. */}
                    {sponsorUserMatch && (
                      <div className="p-2 rounded border border-amber-300 bg-amber-50 text-xs flex items-center justify-between gap-2 flex-wrap" data-testid="cd-sponsor-user-match-banner">
                        <p className="text-amber-900 flex-1 min-w-0">
                          <strong>{sponsorUserMatch.name}</strong> is already a user in your team ({sponsorUserMatch.email}).
                          Link their account instead?
                        </p>
                        <button
                          type="button"
                          className="px-2.5 py-1 rounded bg-amber-600 text-white text-[11px] shrink-0"
                          onClick={async () => {
                            await api.put(`/social-work/cases/${caseId}`, { sponsor_member_id: sponsorUserMatch.id, sponsor_manual: null });
                            setCaseDoc({ ...caseDoc, sponsor_member_id: sponsorUserMatch.id, sponsor_manual: null, sponsor_manual_mode: false });
                            toast.success(`Linked ${sponsorUserMatch.name}`);
                          }}
                          data-testid="cd-sponsor-link-user-btn"
                        >Link account</button>
                      </div>
                    )}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                    <div className="space-y-1">
                      <Label className="text-[10px] text-muted-foreground">Sponsor name * <span className="opacity-60">(type to find existing donors)</span></Label>
                      <ExternalSponsorAutocomplete
                        value={caseDoc.sponsor_manual?.name || ''}
                        onChange={v => setCaseDoc({ ...caseDoc, sponsor_manual: { ...(caseDoc.sponsor_manual || {}), name: v } })}
                        onPick={(g) => {
                          const next = { name: g.name, email: g.email || '', phone: g.phone || '', notes: g.notes || '' };
                          setCaseDoc({ ...caseDoc, sponsor_manual: next });
                          api.put(`/social-work/cases/${caseId}`, { sponsor_manual: next, sponsor_member_id: null }).catch(() => {});
                          toast.success(`Picked existing sponsor: ${g.name}${g.active_cases > 0 ? ` (already on ${g.active_cases} case${g.active_cases === 1 ? '' : 's'})` : ''}`);
                        }}
                        placeholder="e.g. Sarah Johnson"
                        testid="cd-sponsor-manual-name"
                      />
                      {caseDoc.sponsor_manual?.name && (
                        <Button
                          size="sm" variant="ghost" className="h-6 text-[10px] -mt-0.5 px-1"
                          onClick={() => api.put(`/social-work/cases/${caseId}`, { sponsor_manual: caseDoc.sponsor_manual, sponsor_member_id: null }).then(() => toast.success('Sponsor saved')).catch(() => toast.error('Save failed'))}
                          data-testid="cd-sponsor-manual-save-name"
                          title="Save the current name + email + phone + notes to this case"
                        >Save sponsor</Button>
                      )}
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[10px] text-muted-foreground">Email</Label>
                      <Input
                        className="h-8 text-xs"
                        type="email"
                        value={caseDoc.sponsor_manual?.email || ''}
                        onChange={e => setCaseDoc({ ...caseDoc, sponsor_manual: { ...(caseDoc.sponsor_manual || {}), email: e.target.value } })}
                        onBlur={() => api.put(`/social-work/cases/${caseId}`, { sponsor_manual: caseDoc.sponsor_manual }).catch(() => {})}
                        placeholder="sponsor@example.org"
                        data-testid="cd-sponsor-manual-email"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[10px] text-muted-foreground">Phone</Label>
                      <Input
                        className="h-8 text-xs"
                        value={caseDoc.sponsor_manual?.phone || ''}
                        onChange={e => setCaseDoc({ ...caseDoc, sponsor_manual: { ...(caseDoc.sponsor_manual || {}), phone: e.target.value } })}
                        onBlur={() => api.put(`/social-work/cases/${caseId}`, { sponsor_manual: caseDoc.sponsor_manual }).catch(() => {})}
                        placeholder="+256 700 123 456"
                        data-testid="cd-sponsor-manual-phone"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[10px] text-muted-foreground">Organisation / notes</Label>
                      <Input
                        className="h-8 text-xs"
                        value={caseDoc.sponsor_manual?.notes || ''}
                        onChange={e => setCaseDoc({ ...caseDoc, sponsor_manual: { ...(caseDoc.sponsor_manual || {}), notes: e.target.value } })}
                        onBlur={() => api.put(`/social-work/cases/${caseId}`, { sponsor_manual: caseDoc.sponsor_manual }).catch(() => {})}
                        placeholder="Hope Foundation · monthly $50"
                        data-testid="cd-sponsor-manual-notes"
                      />
                    </div>
                    {caseDoc.sponsor_manual && (
                      <div className="col-span-full">
                        <Button
                          size="sm" variant="ghost" className="h-7 text-[11px] text-destructive"
                          onClick={async () => {
                            if (!window.confirm('Clear the manual sponsor info?')) return;
                            await api.put(`/social-work/cases/${caseId}`, { sponsor_manual: null });
                            setCaseDoc({ ...caseDoc, sponsor_manual: null, sponsor_manual_mode: false });
                            toast.success('Cleared');
                          }}
                          data-testid="cd-sponsor-manual-clear"
                        >Clear manual sponsor</Button>
                      </div>
                    )}
                  </div>
                  </>
                ) : (
                  <div className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground">Link an existing user account</Label>
                    <Select value={caseDoc.sponsor_member_id || 'none'} onValueChange={async v => {
                      const val = v === 'none' ? null : v;
                      await api.put(`/social-work/cases/${caseId}`, { sponsor_member_id: val, sponsor_manual: null });
                      setCaseDoc({ ...caseDoc, sponsor_member_id: val, sponsor_manual: null });
                      reload();
                    }}>
                      <SelectTrigger className="h-8 text-xs" data-testid="cd-sponsor-existing"><SelectValue placeholder="None" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">None</SelectItem>
                        {members.slice(0, 100).map(m => <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>)}
                      </SelectContent>
                    </Select>
                    <p className="text-[10px] text-muted-foreground">Switch to &ldquo;Manual entry&rdquo; if the sponsor isn&apos;t an in-system user.</p>
                  </div>
                )}
              </div>
              {caseDoc.payments_total && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-2">
                  {Object.entries(caseDoc.payments_total).map(([k, v]) => (
                    <div key={k} className="p-2 rounded border text-xs">
                      <p className="text-[10px] uppercase text-muted-foreground">{k.replace(/_/g, ' ')}</p>
                      <p className="text-base font-semibold">{(v || 0).toLocaleString()}</p>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* EDUCATION */}
            <TabsContent value="education" className="space-y-4 mt-4">
              <p className="text-[11px] text-muted-foreground -mb-2">Click any field to edit. Save with the button at the bottom of the section.</p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label className="text-xs">Grade / Level</Label>
                  <Input value={editing.education?.grade || ''} onChange={e => setEditing({ ...editing, education: { ...editing.education, grade: e.target.value } })} data-testid="cd-grade" />
                </div>
                <div className="space-y-1.5"><Label className="text-xs">Enrollment date</Label>
                  <Input type="date" value={editing.education?.enrollment_date || ''} onChange={e => setEditing({ ...editing, education: { ...editing.education, enrollment_date: e.target.value } })} />
                </div>
              </div>
              <div className="space-y-1.5"><Label className="text-xs">School</Label>
                <Select value={editing.education?.school_id || 'none'} onValueChange={v => {
                  const s = schools.find(x => x.id === v);
                  setEditing({ ...editing, education: { ...editing.education, school_id: v === 'none' ? null : v, school_name: s?.name || '' } });
                }}>
                  <SelectTrigger data-testid="cd-school"><SelectValue placeholder="No school" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No school</SelectItem>
                    {schools.map(s => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label className="text-xs">Extracurricular activities (comma-separated)</Label>
                <Input value={(editing.education?.extracurricular || []).join(', ')} onChange={e => setEditing({ ...editing, education: { ...editing.education, extracurricular: e.target.value.split(',').map(x => x.trim()).filter(Boolean) } })} placeholder="football, choir, debate" />
              </div>
              <Button size="sm" onClick={() => saveSection('education')} data-testid="cd-education-save">Save education</Button>
            </TabsContent>

            {/* MEDICAL */}
            <TabsContent value="medical" className="space-y-4 mt-4">
              {/* Combined Medical view — quick-edit summary + full Medical Examinations history
                  (was two separate tabs in iter-172; user asked us to merge). Summary fields auto-sync
                  from the form below when a new medical_exam is saved, so editing here directly is
                  for one-off corrections between exams. */}
              <div className="space-y-3 p-3 rounded-lg border" data-testid="cd-medical-summary">
                <p className="text-[11px] text-muted-foreground -mb-1">Quick summary — full exam history + forms below.</p>
                <div className="space-y-1.5"><Label className="text-xs">Conditions (comma-separated)</Label>
                  <Input value={(editing.medical?.conditions || []).join(', ')} onChange={e => setEditing({ ...editing, medical: { ...editing.medical, conditions: e.target.value.split(',').map(x => x.trim()).filter(Boolean) } })} data-testid="cd-conditions" />
                </div>
                <div className="space-y-1.5"><Label className="text-xs">Allergies (comma-separated)</Label>
                  <Input value={(editing.medical?.allergies || []).join(', ')} onChange={e => setEditing({ ...editing, medical: { ...editing.medical, allergies: e.target.value.split(',').map(x => x.trim()).filter(Boolean) } })} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5"><Label className="text-xs">Receives medical support?</Label>
                    <Select value={editing.medical?.receives_medical_support ? 'yes' : 'no'} onValueChange={v => setEditing({ ...editing, medical: { ...editing.medical, receives_medical_support: v === 'yes' } })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem value="no">No</SelectItem><SelectItem value="yes">Yes</SelectItem></SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5"><Label className="text-xs">Primary doctor / clinic</Label>
                    <Input value={editing.medical?.primary_doctor || ''} onChange={e => setEditing({ ...editing, medical: { ...editing.medical, primary_doctor: e.target.value } })} />
                  </div>
                </div>
                <div className="space-y-1.5"><Label className="text-xs">Medical notes</Label>
                  <Textarea rows={2} value={editing.medical?.notes || ''} onChange={e => setEditing({ ...editing, medical: { ...editing.medical, notes: e.target.value } })} />
                </div>
                <Button size="sm" onClick={() => saveSection('medical')} data-testid="cd-medical-save">Save medical summary</Button>
              </div>

              {/* Full medical-examination history (form + scan upload + OCR). Auto-syncs to
                  child.medical.* — the summary above reads from the same fields. */}
              <div className="pt-2 border-t" data-testid="cd-medical-exams-section">
                <p className="text-xs font-semibold mb-2">Medical Examinations</p>
                <SocialReviewsPanel child={editing} kind="medical_exam" />
              </div>
            </TabsContent>

            {/* FAMILY */}
            <TabsContent value="family" className="space-y-4 mt-4">
              <div className="space-y-1.5"><Label className="text-xs">Guardians (comma-separated)</Label>
                <Input value={(editing.family?.guardians || []).join(', ')} onChange={e => setEditing({ ...editing, family: { ...editing.family, guardians: e.target.value.split(',').map(x => x.trim()).filter(Boolean) } })} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label className="text-xs">Number of siblings</Label>
                  <Input type="number" value={editing.family?.siblings ?? ''} onChange={e => setEditing({ ...editing, family: { ...editing.family, siblings: parseInt(e.target.value) || 0 } })} />
                </div>
                <div className="space-y-1.5"><Label className="text-xs">Household income notes</Label>
                  <Input value={editing.family?.household_income || ''} onChange={e => setEditing({ ...editing, family: { ...editing.family, household_income: e.target.value } })} placeholder="e.g. mother is single, casual labour" />
                </div>
              </div>
              <div className="space-y-1.5"><Label className="text-xs">Family situation</Label>
                <Textarea rows={3} value={editing.family?.notes || ''} onChange={e => setEditing({ ...editing, family: { ...editing.family, notes: e.target.value } })} />
              </div>
              <Button size="sm" onClick={() => saveSection('family')} data-testid="cd-family-save">Save family</Button>
            </TabsContent>

            {/* COMPLIANCE — country-specific fields */}
            <TabsContent value="compliance" className="space-y-4 mt-4">
              {!complianceSchema ? (
                <p className="text-sm text-muted-foreground text-center py-6">No compliance template for this country.</p>
              ) : (
                <>
                  <div className="bg-primary/5 border border-primary/20 rounded p-2.5 text-xs flex items-center gap-2" data-testid="cd-compliance-header">
                    <Globe size={13} className="text-primary" />
                    <div>
                      <p className="font-medium">{complianceSchema.name}</p>
                      <p className="text-muted-foreground text-[10px]">{complianceSchema.fields.length} fields recommended for this country.</p>
                    </div>
                  </div>
                  {(() => {
                    const groupLabels = {
                      identity: 'Identity & Registration',
                      official: 'Administrative & Official',
                      family: 'Family & Vulnerability',
                      school: 'School',
                      health: 'Health',
                    };
                    const groups = {};
                    complianceSchema.fields.forEach(f => {
                      const g = f.group || 'family';
                      if (!groups[g]) groups[g] = [];
                      groups[g].push(f);
                    });
                    return Object.keys(groupLabels).filter(g => groups[g]?.length).map(g => (
                      <div key={g} className="space-y-2">
                        <h4 className="text-xs uppercase text-muted-foreground font-semibold pt-2 border-t">{groupLabels[g]}</h4>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          {groups[g].map(f => {
                            const v = complianceEdits[f.id];
                            const setV = (val) => setComplianceEdits({ ...complianceEdits, [f.id]: val });
                            const baseLabel = <Label className="text-xs">{f.label}</Label>;
                            const tid = `cd-compliance-${f.id}`;
                            if (f.type === 'yesno') return (
                              <div key={f.id} className={`space-y-1 ${f.type === 'textarea' ? 'sm:col-span-2' : ''}`}>
                                {baseLabel}
                                <Select value={v === true ? 'yes' : v === false ? 'no' : ''} onValueChange={val => setV(val === 'yes')}>
                                  <SelectTrigger className="h-8 text-xs" data-testid={tid}><SelectValue placeholder="—" /></SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="yes">Yes</SelectItem>
                                    <SelectItem value="no">No</SelectItem>
                                  </SelectContent>
                                </Select>
                              </div>
                            );
                            if (f.type === 'select') return (
                              <div key={f.id} className="space-y-1">
                                {baseLabel}
                                <Select value={v || ''} onValueChange={setV}>
                                  <SelectTrigger className="h-8 text-xs" data-testid={tid}><SelectValue placeholder="Choose..." /></SelectTrigger>
                                  <SelectContent>
                                    {(f.options || []).map(o => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                                  </SelectContent>
                                </Select>
                              </div>
                            );
                            if (f.type === 'textarea') return (
                              <div key={f.id} className="space-y-1 sm:col-span-2">
                                {baseLabel}
                                <Textarea rows={2} value={v || ''} onChange={e => setV(e.target.value)} data-testid={tid} />
                              </div>
                            );
                            if (f.type === 'date') return (
                              <div key={f.id} className="space-y-1">
                                {baseLabel}
                                <Input type="date" value={v || ''} onChange={e => setV(e.target.value)} className="h-8 text-xs" data-testid={tid} />
                              </div>
                            );
                            if (f.type === 'number') return (
                              <div key={f.id} className="space-y-1">
                                {baseLabel}
                                <Input type="number" step="0.1" value={v ?? ''} onChange={e => setV(e.target.value === '' ? null : parseFloat(e.target.value))} className="h-8 text-xs" data-testid={tid} />
                              </div>
                            );
                            return (
                              <div key={f.id} className="space-y-1">
                                {baseLabel}
                                <Input value={v || ''} onChange={e => setV(e.target.value)} className="h-8 text-xs" data-testid={tid} />
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ));
                  })()}
                  <Button size="sm" onClick={saveCompliance} data-testid="cd-compliance-save">Save compliance fields</Button>
                </>
              )}
            </TabsContent>

            {/* GOALS */}
            <TabsContent value="goals" className="space-y-4 mt-4">
              {(editing.goals || []).map((g, i) => (
                <div key={i} className="p-2 rounded border space-y-1.5">
                  <Input value={g.goal || ''} onChange={e => { const goals = [...editing.goals]; goals[i] = { ...g, goal: e.target.value }; setEditing({ ...editing, goals }); }} placeholder="Goal" />
                  <div className="grid grid-cols-3 gap-2">
                    <Input type="date" value={g.target_date || ''} onChange={e => { const goals = [...editing.goals]; goals[i] = { ...g, target_date: e.target.value }; setEditing({ ...editing, goals }); }} className="text-xs h-8" />
                    <Input type="number" min={0} max={100} value={g.progress_pct ?? ''} onChange={e => { const goals = [...editing.goals]; goals[i] = { ...g, progress_pct: parseInt(e.target.value) || 0 }; setEditing({ ...editing, goals }); }} placeholder="Progress %" className="text-xs h-8" />
                    <Button size="sm" variant="ghost" className="h-8 text-destructive text-xs" onClick={() => setEditing({ ...editing, goals: editing.goals.filter((_, j) => j !== i) })}>Remove</Button>
                  </div>
                </div>
              ))}
              <Button size="sm" variant="outline" className="w-full" onClick={() => setEditing({ ...editing, goals: [...(editing.goals || []), { goal: '', progress_pct: 0 }] })}>+ Add goal</Button>
              <Button size="sm" onClick={() => saveSection('goals')} data-testid="cd-goals-save">Save goals</Button>
            </TabsContent>

            {/* PAYMENTS */}
            <TabsContent value="payments" className="space-y-4 mt-4">
              <Card className="rounded-lg border-dashed">
                <CardContent className="p-3 space-y-2">
                  <p className="text-xs font-semibold uppercase text-muted-foreground">Record a payment</p>
                  <div className="grid grid-cols-2 gap-2">
                    <Select value={newPayment.kind} onValueChange={v => setNewPayment({ ...newPayment, kind: v })}>
                      <SelectTrigger className="h-8 text-xs" data-testid="cd-pay-kind"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {Object.entries(PAYMENT_KIND_LABELS).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
                      </SelectContent>
                    </Select>
                    <Input className="h-8 text-xs" type="number" step="0.01" value={newPayment.amount} onChange={e => setNewPayment({ ...newPayment, amount: e.target.value })} placeholder="Amount" data-testid="cd-pay-amount" />
                    <Input className="h-8 text-xs" value={newPayment.currency} onChange={e => setNewPayment({ ...newPayment, currency: e.target.value.toUpperCase().slice(0, 5) })} placeholder="UGX" />
                    <Input className="h-8 text-xs" type="date" value={newPayment.date} onChange={e => setNewPayment({ ...newPayment, date: e.target.value })} />
                    <Input className="h-8 text-xs col-span-2" value={newPayment.paid_to} onChange={e => setNewPayment({ ...newPayment, paid_to: e.target.value })} placeholder={newPayment.kind === 'child_support' ? 'Sponsor name (received from)' : 'Paid to (school, clinic, vendor)'} />
                    <Input className="h-8 text-xs col-span-2" value={newPayment.notes} onChange={e => setNewPayment({ ...newPayment, notes: e.target.value })} placeholder="Notes" />
                  </div>
                  <Button size="sm" className="w-full" onClick={addPayment} disabled={!newPayment.amount} data-testid="cd-pay-submit">Record &amp; auto-post to finance + accounting</Button>
                  <p className="text-[10px] text-muted-foreground">This creates a finance entry (donation for inbound sponsor payments; expense for outflows) and a balanced journal entry in the accounting ledger.</p>
                </CardContent>
              </Card>
              {payments.length === 0 ? <p className="text-xs text-muted-foreground text-center py-4">No payments recorded yet.</p> : (
                <div className="space-y-1.5">
                  {payments.map(p => (
                    <div key={p.id} className="p-2 rounded border text-xs flex items-center justify-between" data-testid={`cd-pay-${p.id}`}>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium">{PAYMENT_KIND_LABELS[p.kind]} <span className={`text-[10px] ml-1 ${p.direction === 'in' ? 'text-emerald-600' : 'text-red-600'}`}>{p.direction === 'in' ? '+ inflow' : '- outflow'}</span></p>
                        <p className="text-muted-foreground text-[10px]">{p.date} · {p.paid_to || '—'} · {p.notes || ''} <span className="italic">{p.mirror_collection ? `[mirror: ${p.mirror_collection}]` : ''}</span></p>
                      </div>
                      <span className="font-semibold mr-2">{p.currency} {(p.amount || 0).toLocaleString()}</span>
                      <Button size="sm" variant="ghost" className="h-7 text-destructive" onClick={() => deletePayment(p.id)}><Trash2 size={12} /></Button>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* NOTES */}
            <TabsContent value="notes" className="space-y-4 mt-4">
              <Card className="rounded-lg border-dashed">
                <CardContent className="p-3 space-y-2">
                  <p className="text-xs font-semibold uppercase text-muted-foreground">Add a note</p>
                  <div className="grid grid-cols-3 gap-2">
                    <Select value={newNote.kind} onValueChange={v => setNewNote({ ...newNote, kind: v })}>
                      <SelectTrigger className="h-8 text-xs" data-testid="cd-note-kind"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {['visit', 'counseling', 'safeguarding', 'milestone', 'school', 'medical', 'other'].map(k => <SelectItem key={k} value={k} className="capitalize">{k}</SelectItem>)}
                      </SelectContent>
                    </Select>
                    <Select value={newNote.is_confidential ? 'yes' : 'no'} onValueChange={v => setNewNote({ ...newNote, is_confidential: v === 'yes' })}>
                      <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem value="no">Standard</SelectItem><SelectItem value="yes">Confidential</SelectItem></SelectContent>
                    </Select>
                    <Button size="sm" onClick={addNote} disabled={!newNote.body.trim()} data-testid="cd-note-submit">Add</Button>
                  </div>
                  <Textarea rows={3} value={newNote.body} onChange={e => setNewNote({ ...newNote, body: e.target.value })} placeholder="What happened? Visit observations, counseling notes, safeguarding flags, milestones..." data-testid="cd-note-body" />
                </CardContent>
              </Card>
              {notes.length === 0 ? <EmptyState compact icon={ClipboardList} title="No notes yet" description="Use this space for visit observations, counseling notes, and safeguarding flags." testid="cd-notes-empty" /> : (
                <div className="space-y-2">
                  {notes.map(n => (
                    <div key={n.id} className="p-2 rounded border text-xs" data-testid={`cd-note-${n.id}`}>
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <div className="flex items-center gap-1.5">
                          <Badge variant="outline" className="text-[10px] capitalize">{n.kind}</Badge>
                          {n.is_confidential && <Badge className="bg-red-100 text-red-700 text-[10px]"><AlertTriangle size={9} className="mr-0.5" />Confidential</Badge>}
                          {n.source === 'school_portal' && <Badge className="bg-blue-100 text-blue-700 text-[10px]"><GraduationCap size={9} className="mr-0.5" />from {n.school_name}</Badge>}
                        </div>
                        <span className="text-[10px] text-muted-foreground">{n.created_at?.slice(0, 16).replace('T', ' ')} · {n.created_by_name}</span>
                      </div>
                      <p className="whitespace-pre-wrap">{n.body}</p>
                      {(n.attachments || []).length > 0 && (
                        <div className="mt-1 text-[10px]">
                          {n.attachments.map((a, i) => <a key={i} href={a.url} target="_blank" rel="noopener noreferrer" className="text-primary underline mr-2">📎 {a.name || 'Attachment'}</a>)}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* SCHOOL PROGRESS REVIEWS — termly review forms filled at school visits */}
            <TabsContent value="school_reviews" className="space-y-4 mt-4">
              <SocialReviewsPanel child={editing} kind="school_progress" />
            </TabsContent>

            {/* WELFARE VISITS — home visits, protection assessment, household checks */}
            <TabsContent value="welfare_visits" className="space-y-4 mt-4">
              <SocialReviewsPanel child={editing} kind="welfare_visit" />
            </TabsContent>

            {/* DOCUMENTS — typed file-checklist (LC1, guardian ID, school reports, etc.) + bundle download */}
            <TabsContent value="documents" className="space-y-4 mt-4">
              <ChildDocumentsPanel child={editing} />
            </TabsContent>
          </Tabs>
        )}
      </DialogContent>
    </Dialog>
  );
}
