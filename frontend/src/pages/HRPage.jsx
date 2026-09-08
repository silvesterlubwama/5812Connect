import React, { useState, useEffect, useCallback } from 'react';
import AdminPage from './AdminPage';
import { Users, DollarSign, FileText, Clock, Plus, Trash2, Send, CheckCircle, CheckCircle2, XCircle, Download, RefreshCw, Settings, Pencil, History, Wrench } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { Switch } from '../components/ui/switch';
import api from '../services/api';
import { adminApi, locationsApi, departmentsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

export default function HRPage() {
  const { user } = useAuth();
  const activeCampus = localStorage.getItem('5812_active_campus') || user?.location_id || '';
  const [salaries, setSalaries] = useState([]);
  const [activeTab, setActiveTab] = useState('salaries');
  const [payslips, setPayslips] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [contracts, setContracts] = useState([]);
  const [docRequests, setDocRequests] = useState([]);
  const [staff, setStaff] = useState([]);
  const [locations, setLocations] = useState([]);
  const [hrSettings, setHrSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showSalary, setShowSalary] = useState(false);
  const [showTemplate, setShowTemplate] = useState(false);
  const [repairModal, setRepairModal] = useState(null);   // { data, busy, phase }
  const [showPayslipGen, setShowPayslipGen] = useState(false);
  const [showManualPayslip, setShowManualPayslip] = useState(false);
  const [manualPayslip, setManualPayslip] = useState({
    staff_id: '',
    period: new Date().toISOString().slice(0, 7),
    gross_salary: '',
    currency: 'UGX',
    allowances: [],
    deductions: [],
    notes: '',
  });
  const [savingManual, setSavingManual] = useState(false);
  const [showDocReq, setShowDocReq] = useState(false);
  const [showIssueContract, setShowIssueContract] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [salaryForm, setSalaryForm] = useState({ staff_id: '', base_salary: '', currency: 'UGX', pay_frequency: 'monthly', wage_type: 'salary', line_items: [], department_ids: [], department_splits: [] });
  // iter-departments: list of departments visible in the current campus, used
  // by the salary form's multi-department picker + funding-splits editor.
  const [availableDepartments, setAvailableDepartments] = useState([]);
  const [editingSalaryId, setEditingSalaryId] = useState(null);
  const [editReason, setEditReason] = useState('');
  const [historySalary, setHistorySalary] = useState(null);
  const [historyEntries, setHistoryEntries] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [templateForm, setTemplateForm] = useState({ name: '', content: '' });
  // Payslip generation is now payday-driven (fetched from hr_settings). The
  // period we submit to /payslips/generate is the canonical period label the
  // backend returns (monthly=YYYY-MM, weekly/biweekly=window string).
  const [upcomingPaydays, setUpcomingPaydays] = useState([]);   // [{ date, period }]
  const [selectedPayday, setSelectedPayday] = useState('');     // canonical period label
  const [paydayFrequency, setPaydayFrequency] = useState('monthly');
  const [paydaysLoading, setPaydaysLoading] = useState(false);
  // Payslip edit + history dialogs (iter209b)
  const [editingPayslip, setEditingPayslip] = useState(null);
  const [editPayslipForm, setEditPayslipForm] = useState({});
  const [editPayslipReason, setEditPayslipReason] = useState('');
  const [payslipHistory, setPayslipHistory] = useState(null);
  const [bulkExportPeriod, setBulkExportPeriod] = useState(new Date().toISOString().slice(0, 7));
  // iter 335 — dry-run preview before writing draft payslips
  const [previewRows, setPreviewRows] = useState(null); // null = not previewed yet
  const [previewLoading, setPreviewLoading] = useState(false);
  // Cash accounts + locations for the payslip edit dialog (iter210b)
  const [cashAccountOptions, setCashAccountOptions] = useState([]);
  const [locationOptions, setLocationOptions] = useState([]);
  useEffect(() => {
    api.get('/financial/chart-accounts', { params: { active_only: false, limit: 200 } })
      .then(r => setCashAccountOptions(r.data || [])).catch(() => {});
    api.get('/locations').then(r => setLocationOptions(r.data || [])).catch(() => {});
    // iter-departments: load cost-centre list so the salary form's picker
    // and splits editor always reflect the current department catalogue.
    departmentsApi.list({ include_inactive: false })
      .then(r => setAvailableDepartments(r.data || []))
      .catch(() => setAvailableDepartments([]));
  }, []);
  // Auto-select the staff member on the contract dialog when the user hit "Fix"
  // from the onboarding checklist (iter215). Cleared after read so the next
  // free-form "Issue Contract" click starts empty.
  useEffect(() => {
    if (!showIssueContract) return;
    try {
      const preselect = localStorage.getItem('5812_onboarding_preselect_staff');
      if (preselect) {
        setIssueForm(f => ({ ...f, staff_id: preselect }));
        localStorage.removeItem('5812_onboarding_preselect_staff');
      }
    } catch { /* localStorage unavailable */ }
  }, [showIssueContract]);
  const [docReqForm, setDocReqForm] = useState({ staff_id: '', doc_types: ['resume', 'id_document'], message: '' });
  const [issueForm, setIssueForm] = useState({ template_id: '', staff_id: '', start_date: '', salary: '' });
  const [settingsForm, setSettingsForm] = useState({ hr_enabled: false, pay_frequency: 'monthly', currency: 'UGX', pay_day: 28 });
  const [lineItem, setLineItem] = useState({ name: '', type: 'allowance', amount: '', is_percentage: false });
  const [saving, setSaving] = useState(false);
  const isAdmin = ['admin', 'system_admin'].includes(user?.role);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [salRes, psRes, tplRes, conRes, drRes, staffRes, locRes] = await Promise.all([
        api.get('/hr/salaries').catch(() => ({ data: [] })),
        api.get('/hr/payslips').catch(() => ({ data: [] })),
        api.get('/hr/contracts/templates').catch(() => ({ data: [] })),
        api.get('/hr/contracts').catch(() => ({ data: [] })),
        api.get('/hr/document-requests').catch(() => ({ data: [] })),
        adminApi.userDirectory().catch(() => ({ data: [] })),
        locationsApi.list().catch(() => ({ data: [] })),
      ]);
      setSalaries(salRes.data || []);
      setPayslips(psRes.data || []);
      setTemplates(tplRes.data || []);
      setContracts(conRes.data || []);
      setDocRequests(drRes.data || []);
      setStaff(staffRes.data || []);
      setLocations(locRes.data || []);
      if (activeCampus) {
        const sRes = await api.get(`/hr/settings/${activeCampus}`).catch(() => ({ data: null }));
        setHrSettings(sRes.data);
        setSettingsForm(sRes.data || { hr_enabled: false, pay_frequency: 'monthly', currency: 'UGX', pay_day: 28 });
      }
    } catch { toast.error('Failed to load HR data'); }
    finally { setLoading(false); }
  }, [activeCampus]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const addLineItem = () => {
    if (!lineItem.name || !lineItem.amount) return;
    setSalaryForm(prev => ({ ...prev, line_items: [...prev.line_items, { ...lineItem, amount: parseFloat(lineItem.amount) }] }));
    setLineItem({ name: '', type: 'allowance', amount: '', is_percentage: false });
  };

  const handleCreateSalary = async () => {
    setSaving(true);
    try {
      // iter-departments: validate splits (if any) sum to 100 before hitting
      // the API so the user sees a clear inline error instead of a 400.
      const splits = salaryForm.department_splits || [];
      if (splits.length && Math.abs(splits.reduce((s, x) => s + (parseFloat(x.pct) || 0), 0) - 100) > 0.01) {
        toast.error('Department splits must total 100%.');
        setSaving(false);
        return;
      }
      if (editingSalaryId) {
        const res = await api.put(`/hr/salaries/${editingSalaryId}`, {
          base_salary: parseFloat(salaryForm.base_salary),
          currency: salaryForm.currency,
          pay_frequency: salaryForm.pay_frequency,
          wage_type: salaryForm.wage_type || 'salary',
          hourly_rate: salaryForm.wage_type === 'hourly' ? parseFloat(salaryForm.base_salary) : 0,
          daily_rate: salaryForm.wage_type === 'daily' ? parseFloat(salaryForm.base_salary) : 0,
          weekly_rate: salaryForm.wage_type === 'weekly' ? parseFloat(salaryForm.base_salary) : 0,
          biweekly_rate: salaryForm.wage_type === 'biweekly' ? parseFloat(salaryForm.base_salary) : 0,
          line_items: salaryForm.line_items,
          department_ids: salaryForm.department_ids || [],
          department_splits: (salaryForm.department_splits || []).map(s => ({ department_id: s.department_id, pct: parseFloat(s.pct) })),
          reason: editReason,
        });
        setSalaries(prev => prev.map(x => x.id === editingSalaryId ? res.data : x));
        toast.success('Salary updated');
      } else {
        const res = await api.post('/hr/salaries', {
          ...salaryForm,
          base_salary: parseFloat(salaryForm.base_salary),
          wage_type: salaryForm.wage_type || 'salary',
          hourly_rate: salaryForm.wage_type === 'hourly' ? parseFloat(salaryForm.base_salary) : 0,
          daily_rate: salaryForm.wage_type === 'daily' ? parseFloat(salaryForm.base_salary) : 0,
          weekly_rate: salaryForm.wage_type === 'weekly' ? parseFloat(salaryForm.base_salary) : 0,
          biweekly_rate: salaryForm.wage_type === 'biweekly' ? parseFloat(salaryForm.base_salary) : 0,
          location_id: activeCampus,
          department_splits: (salaryForm.department_splits || []).map(s => ({ department_id: s.department_id, pct: parseFloat(s.pct) })),
        });
        setSalaries(prev => [res.data, ...prev]);
        toast.success('Salary record created');
      }
      setShowSalary(false);
      setEditingSalaryId(null);
      setEditReason('');
      setSalaryForm({ staff_id: '', base_salary: '', currency: 'UGX', pay_frequency: 'monthly', line_items: [], department_ids: [], department_splits: [] });
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
  };

  const openEditSalary = (s) => {
    setEditingSalaryId(s.id);
    setEditReason('');
    setSalaryForm({
      staff_id: s.staff_id || '',
      base_salary: String(s.base_salary || s.hourly_rate || s.daily_rate || s.weekly_rate || s.biweekly_rate || ''),
      wage_type: s.wage_type || 'salary',
      currency: s.currency || 'UGX',
      pay_frequency: s.pay_frequency || 'monthly',
      line_items: s.line_items || [],
      // iter-departments: hydrate multi-dept tag + funding splits so an
      // Edit → Save round-trip doesn't silently wipe them (same class of
      // hydration bug we fixed on UserEditDialog).
      department_ids: s.department_ids || [],
      department_splits: s.department_splits || [],
    });
    setShowSalary(true);
  };

  const openSalaryHistory = async (s) => {
    setHistorySalary(s);
    setHistoryEntries([]);
    setHistoryLoading(true);
    try {
      const res = await api.get('/hr/salaries/history', { params: { staff_id: s.staff_id } });
      setHistoryEntries(res.data || []);
    } catch (e) { toast.error('Failed to load history'); }
    finally { setHistoryLoading(false); }
  };

  const handleCreateTemplate = async () => {
    setSaving(true);
    try {
      const res = await api.post('/hr/contracts/templates', { ...templateForm, location_id: activeCampus });
      setTemplates(prev => [res.data, ...prev]);
      setShowTemplate(false);
      setTemplateForm({ name: '', content: '' });
      toast.success('Template created');
    } catch { toast.error('Failed'); }
    finally { setSaving(false); }
  };

  const handleGeneratePayslips = async () => {
    if (!selectedPayday) { toast.error('Choose a payday first'); return; }
    setSaving(true);
    try {
      const res = await api.post('/hr/payslips/generate', { period: selectedPayday, location_id: activeCampus });
      setPayslips(prev => [...res.data.payslips, ...prev]);
      setShowPayslipGen(false);
      setPreviewRows(null);
      toast.success(`Generated ${res.data.generated} payslips`);
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
  };

  // iter 335: dry-run every staffer's calculated gross/net so directors
  // catch surprises BEFORE draft payslips are written. Reuses the exact
  // same math as /payslips/generate.
  const handlePreviewPayslips = async () => {
    if (!selectedPayday) { toast.error('Choose a payday first'); return; }
    setPreviewLoading(true);
    try {
      const res = await api.post('/hr/payslips/preview', { period: selectedPayday, location_id: activeCampus });
      setPreviewRows(res.data.rows || []);
    } catch (err) { toast.error(err.response?.data?.detail || 'Preview failed'); }
    finally { setPreviewLoading(false); }
  };

  // Fetch upcoming paydays whenever the Generate dialog opens so the picker
  // always reflects the campus's current HR settings (frequency + weekday snap).
  useEffect(() => {
    if (!showPayslipGen || !activeCampus) return;
    setPaydaysLoading(true);
    api.get('/hr/payslips/upcoming-paydays', { params: { count: 6, location_id: activeCampus } })
      .then(r => {
        const list = r.data?.paydays || [];
        setUpcomingPaydays(list);
        setPaydayFrequency(r.data?.frequency || 'monthly');
        setSelectedPayday(prev => (list.find(p => p.period === prev) ? prev : (list[0]?.period || '')));
      })
      .catch(() => {
        setUpcomingPaydays([]);
        toast.error('Could not load paydays — check HR settings for this campus');
      })
      .finally(() => setPaydaysLoading(false));
  }, [showPayslipGen, activeCampus]);

  const handleIssueContract = async () => {
    setSaving(true);
    try {
      const res = await api.post('/hr/contracts/issue', issueForm);
      setContracts(prev => [res.data, ...prev]);
      setShowIssueContract(false);
      toast.success('Contract issued');
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
  };

  const handleDocRequest = async () => {
    setSaving(true);
    try {
      const res = await api.post('/hr/document-requests', docReqForm);
      setDocRequests(prev => [res.data, ...prev]);
      setShowDocReq(false);
      toast.success('Document request sent');
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
  };

  const handleSaveSettings = async () => {
    try {
      await api.put(`/hr/settings/${activeCampus}`, settingsForm);
      toast.success('HR settings saved');
      setShowSettings(false);
    } catch { toast.error('Failed'); }
  };

  const fmt = (v) => `${salaryForm.currency || 'UGX'} ${(v || 0).toLocaleString()}`;
  const staffName = (id) => staff.find(s => s.id === id)?.name || id;

  if (loading) return <div className="p-6"><div className="space-y-4">{[1,2,3].map(i => <div key={i} className="h-24 bg-muted animate-pulse rounded-xl" />)}</div></div>;

  return (
    <div className="p-6 space-y-5" data-testid="hr-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Human Resources</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{salaries.length} staff salaries · {payslips.length} payslips · {contracts.length} contracts</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setShowSettings(true)} data-testid="hr-settings-btn"><Settings size={14} /></Button>
          <Button variant="outline" size="sm" onClick={fetchAll}><RefreshCw size={14} /></Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Card className="rounded-xl"><CardContent className="p-4 text-center"><p className="text-2xl font-bold">{salaries.length}</p><p className="text-xs text-muted-foreground">Staff on Payroll</p></CardContent></Card>
        <Card className="rounded-xl"><CardContent className="p-4 text-center"><p className="text-2xl font-bold">{payslips.filter(p => p.status === 'draft').length}</p><p className="text-xs text-muted-foreground">Draft Payslips</p></CardContent></Card>
        <Card className="rounded-xl"><CardContent className="p-4 text-center"><p className="text-2xl font-bold">{contracts.filter(c => c.status === 'pending_signature').length}</p><p className="text-xs text-muted-foreground">Pending Contracts</p></CardContent></Card>
        <Card className="rounded-xl"><CardContent className="p-4 text-center"><p className="text-2xl font-bold">{docRequests.filter(d => d.status === 'pending').length}</p><p className="text-xs text-muted-foreground">Pending Doc Requests</p></CardContent></Card>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="w-full flex overflow-x-auto no-scrollbar md:inline-flex md:w-auto md:flex-wrap">
          <TabsTrigger value="salaries" data-testid="hr-tab-salaries"><DollarSign size={13} className="mr-1" /> Salaries</TabsTrigger>
          <TabsTrigger value="payslips" data-testid="hr-tab-payslips"><FileText size={13} className="mr-1" /> Payslips</TabsTrigger>
          <TabsTrigger value="contracts" data-testid="hr-tab-contracts"><FileText size={13} className="mr-1" /> Contracts</TabsTrigger>
          <TabsTrigger value="documents" data-testid="hr-tab-documents"><Users size={13} className="mr-1" /> Documents</TabsTrigger>
          <TabsTrigger value="leave" data-testid="hr-tab-leave"><Clock size={13} className="mr-1" /> Leave</TabsTrigger>
          <TabsTrigger value="reimbursements" data-testid="hr-tab-reimbursements"><DollarSign size={13} className="mr-1" /> Reimbursements</TabsTrigger>
          <TabsTrigger value="attendance" data-testid="hr-tab-attendance"><Clock size={13} className="mr-1" /> Attendance</TabsTrigger>
          <TabsTrigger value="timesheets" data-testid="hr-tab-timesheets"><Clock size={13} className="mr-1" /> Timesheets</TabsTrigger>
          <TabsTrigger value="time-off" data-testid="hr-tab-time-off"><Clock size={13} className="mr-1" /> Time Off</TabsTrigger>
          <TabsTrigger value="onboarding" data-testid="hr-tab-onboarding"><CheckCircle2 size={13} className="mr-1" /> Onboarding</TabsTrigger>
          {isAdmin && <TabsTrigger value="staff" data-testid="hr-tab-staff"><Users size={13} className="mr-1" /> Staff & Users</TabsTrigger>}
        </TabsList>

        {/* SALARIES TAB */}
        <TabsContent value="salaries" className="mt-4">
          <div className="flex justify-end mb-3">
            <Button size="sm" className="gap-1.5" onClick={() => setShowSalary(true)} data-testid="add-salary-btn"><Plus size={14} /> Add Salary</Button>
          </div>
          {salaries.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">No salary records yet.</p> : (
            <div className="space-y-2">
              {salaries.map(s => (
                <Card key={s.id} className="rounded-xl" data-testid={`salary-${s.id}`}>
                  <CardContent className="p-4 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">{s.staff_name}</p>
                      <p className="text-xs text-muted-foreground">{s.staff_role} · {s.department} · {s.pay_frequency}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-bold">{s.currency} {(s.base_salary || 0).toLocaleString()}</p>
                      <p className="text-[10px] text-muted-foreground">{(s.line_items || []).length} line items</p>
                    </div>
                    <div className="flex items-center gap-1">
                      <Button size="sm" variant="ghost" className="h-7" onClick={async () => {
                        try {
                          const yr = new Date().getFullYear();
                          const res = await api.get(`/hr/staff/${s.staff_id}/compensation-summary`, { params: { year: yr }, responseType: 'blob' });
                          const url = URL.createObjectURL(res.data);
                          const a = document.createElement('a');
                          a.href = url; a.download = `compensation-${(s.staff_name||'staff').replace(/\s+/g,'_')}-${yr}.pdf`;
                          document.body.appendChild(a); a.click(); a.remove();
                          URL.revokeObjectURL(url);
                          toast.success('Compensation PDF downloaded');
                        } catch { toast.error('Download failed'); }
                      }} data-testid={`salary-comp-pdf-${s.id}`} title="Download yearly compensation summary"><FileText size={13} /></Button>
                      <Button size="sm" variant="ghost" className="h-7" onClick={() => openSalaryHistory(s)} data-testid={`salary-history-${s.id}`} title="View change history"><History size={13} /></Button>
                      <Button size="sm" variant="ghost" className="h-7" onClick={() => openEditSalary(s)} data-testid={`salary-edit-${s.id}`} title="Edit salary"><Pencil size={13} /></Button>
                      <Button size="sm" variant="ghost" className="text-destructive h-7" data-testid={`salary-delete-${s.id}`} onClick={async () => { if (!window.confirm('Delete salary record?')) return; await api.delete(`/hr/salaries/${s.id}`); setSalaries(prev => prev.filter(x => x.id !== s.id)); toast.success('Deleted'); }}><Trash2 size={13} /></Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* PAYSLIPS TAB */}
        <TabsContent value="payslips" className="mt-4">
          <div className="flex justify-between items-center gap-2 mb-3 flex-wrap">
            <div className="flex items-center gap-2 flex-wrap">
              <Label className="text-xs text-muted-foreground">Export period:</Label>
              <Input type="month" value={bulkExportPeriod} onChange={e => setBulkExportPeriod(e.target.value)} className="h-8 text-xs w-36" data-testid="bulk-export-period-input" />
              <Button size="sm" variant="outline" className="gap-1.5 h-8" data-testid="export-payslips-csv-btn" onClick={async () => {
                try {
                  const url = `${process.env.REACT_APP_BACKEND_URL}/api/hr/payslips/export.csv?period=${encodeURIComponent(bulkExportPeriod)}`;
                  const r = await fetch(url, { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } });
                  if (!r.ok) { toast.error('Export failed'); return; }
                  const blob = await r.blob();
                  const link = document.createElement('a');
                  link.href = URL.createObjectURL(blob);
                  link.download = `payslips_${bulkExportPeriod}.csv`;
                  link.click();
                  toast.success('CSV downloaded');
                } catch (e) { toast.error('Export failed'); }
              }}><Download size={14} /> CSV</Button>
              <Button size="sm" variant="outline" className="gap-1.5 h-8" data-testid="export-payslips-zip-btn" onClick={async () => {
                try {
                  const url = `${process.env.REACT_APP_BACKEND_URL}/api/hr/payslips/export.zip?period=${encodeURIComponent(bulkExportPeriod)}`;
                  const r = await fetch(url, { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } });
                  if (!r.ok) { toast.error(r.status === 404 ? 'No payslips for that period' : 'Export failed'); return; }
                  const blob = await r.blob();
                  const link = document.createElement('a');
                  link.href = URL.createObjectURL(blob);
                  link.download = `payslips_${bulkExportPeriod}.zip`;
                  link.click();
                  toast.success('ZIP downloaded');
                } catch (e) { toast.error('Export failed'); }
              }}><Download size={14} /> ZIP</Button>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {['admin', 'system_admin', 'Executive Director'].includes(user?.role) && (
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1.5 h-8 text-amber-700 border-amber-300 hover:bg-amber-50"
                  data-testid="repair-payslip-je-btn"
                  onClick={async () => {
                    setRepairModal({ busy: true, data: null, phase: 'preview' });
                    try {
                      const res = await api.post('/hr/repair-payslip-journals', {});
                      setRepairModal({ busy: false, data: res.data, phase: 'preview' });
                    } catch (e) {
                      setRepairModal(null);
                      toast.error(e.response?.data?.detail || 'Diagnostic failed');
                    }
                  }}
                  title="Backfill accounting entries for paid payslips that never made it to the ledger — safe to re-run"
                >
                  <Wrench size={14} /> Fix Ledger Postings
                </Button>
              )}
              <Button size="sm" variant="outline" className="gap-1.5" data-testid="generate-payday-btn" onClick={async () => {
                try {
                  const res = await api.post('/hr/payslips/generate-payday');
                  if (res.data.generated > 0) {
                    toast.success(`Generated ${res.data.generated} payslips for ${res.data.period} (payday today!)`);
                    setPayslips(prev => [...(res.data.payslips || []), ...prev]);
                  } else {
                    toast.info(res.data.message || `No campuses have payday today (${res.data.day_of_month})`);
                  }
                } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
              }}><CheckCircle size={14} /> Run Payday Now</Button>
              <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setShowManualPayslip(true)} data-testid="manual-payslip-btn"><FileText size={14} /> Manual Payslip</Button>
              <Button size="sm" className="gap-1.5" onClick={() => setShowPayslipGen(true)} data-testid="generate-payslips-btn"><Plus size={14} /> Generate Payslips</Button>
            </div>
          </div>
          {payslips.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">No payslips generated yet.</p> : (
            <div className="space-y-2">
              {payslips.map(p => (
                <Card key={p.id} className="rounded-xl">
                  <CardContent className="p-4 flex items-center justify-between flex-wrap gap-3">
                    <div>
                      <p className="text-sm font-medium">{p.staff_name}</p>
                      <p className="text-xs text-muted-foreground">Period: {p.period} · {p.department}</p>
                      {(p.edit_history?.length || 0) > 0 && <p className="text-[10px] text-amber-600">✎ Edited {p.edit_history.length}x</p>}
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <div className="text-right">
                        <p className="text-sm font-bold text-green-600">{p.currency} {(p.net_salary || 0).toLocaleString()}</p>
                        <p className="text-[10px] text-muted-foreground">Gross: {(p.gross_salary || 0).toLocaleString()}</p>
                      </div>
                      <Badge variant={p.status === 'approved' ? 'outline' : (p.status === 'paid' ? 'default' : 'secondary')} className={`text-xs ${p.status === 'approved' ? 'border-green-400 text-green-600' : ''}`}>{p.status}</Badge>
                      <Button size="sm" variant="ghost" className="h-7 text-xs gap-1" data-testid={`payslip-pdf-${p.id}`} title="Download PDF" onClick={async () => {
                        try {
                          const url = `${process.env.REACT_APP_BACKEND_URL}/api/hr/payslips/${p.id}/pdf`;
                          const r = await fetch(url, { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } });
                          if (!r.ok) { toast.error('PDF failed'); return; }
                          const blob = await r.blob();
                          const link = document.createElement('a');
                          link.href = URL.createObjectURL(blob);
                          link.download = `payslip_${p.staff_name?.replace(/\s+/g,'_')}_${p.period}.pdf`;
                          link.click();
                        } catch { toast.error('PDF failed'); }
                      }}><Download size={12} /></Button>
                      <Button size="sm" variant="outline" className="h-7 text-xs gap-1" data-testid={`payslip-edit-${p.id}`} onClick={() => {
                        setEditingPayslip(p);
                        setEditPayslipForm({
                          gross_salary: p.gross_salary || 0,
                          allowances: p.allowances || 0,
                          deductions: p.deductions || 0,
                          net_salary: p.net_salary || 0,
                          notes: p.notes || '',
                          status: p.status,
                          paid_from_account_id: p.paid_from_account_id || '',
                          payroll_location_id: p.payroll_location_id || '',
                        });
                        setEditPayslipReason('');
                      }}><Pencil size={12} /> Edit</Button>
                      <Button size="sm" variant="ghost" className="h-7 text-xs gap-1" data-testid={`payslip-history-${p.id}`} title="View edit history" onClick={async () => {
                        try {
                          // iter-payroll-alloc: also fetch the department
                          // allocations produced when this payslip was paid,
                          // so the info-strip in the history dialog shows
                          // the cost-centre split without an extra click.
                          const [hr, ar] = await Promise.all([
                            api.get(`/hr/payslips/${p.id}/history`),
                            p.status === 'paid'
                              ? api.get(`/hr/payslips/${p.id}/allocations`).catch(() => ({ data: { allocations: [] } }))
                              : Promise.resolve({ data: { allocations: [] } }),
                          ]);
                          setPayslipHistory({ payslip: p, ...hr.data, allocations: ar.data?.allocations || [] });
                        } catch { toast.error('Failed to load history'); }
                      }}><History size={12} /></Button>
                      {p.status === 'draft' && <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={async () => { await api.put(`/hr/payslips/${p.id}`, { status: 'approved' }); setPayslips(prev => prev.map(x => x.id === p.id ? { ...x, status: 'approved' } : x)); toast.success('Approved'); }}><CheckCircle size={12} /> Approve</Button>}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* CONTRACTS TAB */}
        <TabsContent value="contracts" className="mt-4">
          <div className="flex justify-between mb-3">
            <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setShowTemplate(true)}><Plus size={14} /> New Template</Button>
            <Button size="sm" className="gap-1.5" onClick={() => setShowIssueContract(true)} data-testid="issue-contract-btn"><Send size={14} /> Issue Contract</Button>
          </div>
          {templates.length > 0 && (
            <div className="mb-4">
              <p className="text-xs font-semibold text-muted-foreground uppercase mb-2">Templates</p>
              <div className="flex flex-wrap gap-2">
                {templates.map(t => (
                  <Badge key={t.id} variant="outline" className="gap-1.5 text-xs cursor-pointer hover:bg-destructive/10" onClick={async () => { if (!window.confirm(`Delete template "${t.name}"?`)) return; await api.delete(`/hr/contracts/templates/${t.id}`); setTemplates(prev => prev.filter(x => x.id !== t.id)); }}>
                    <FileText size={10} /> {t.name}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {contracts.length === 0 ? <p className="text-sm text-muted-foreground text-center py-8">No contracts issued yet.</p> : (
            <div className="space-y-2">
              {contracts.map(c => (
                <Card key={c.id} className="rounded-xl">
                  <CardContent className="p-4 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">{c.staff_name}</p>
                      <p className="text-xs text-muted-foreground">{c.template_name} · {c.issued_at?.slice(0, 10)}</p>
                    </div>
                    <Badge variant={c.status === 'signed' ? 'outline' : 'secondary'} className={`text-xs ${c.status === 'signed' ? 'border-green-400 text-green-600' : c.status === 'pending_signature' ? 'border-amber-400 text-amber-600' : ''}`}>{c.status?.replace('_', ' ')}</Badge>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* DOCUMENTS TAB */}
        <TabsContent value="documents" className="mt-4">
          <div className="flex justify-end mb-3">
            <Button size="sm" className="gap-1.5" onClick={() => setShowDocReq(true)} data-testid="request-docs-btn"><Send size={14} /> Request Documents</Button>
          </div>
          {docRequests.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">No document requests.</p> : (
            <div className="space-y-2">
              {docRequests.map(d => (
                <Card key={d.id} className="rounded-xl">
                  <CardContent className="p-4 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">{d.staff_name}</p>
                      <p className="text-xs text-muted-foreground">{(d.doc_types || []).join(', ')} · {d.created_at?.slice(0, 10)}</p>
                    </div>
                    <Badge variant={d.status === 'completed' ? 'outline' : 'secondary'} className={`text-xs ${d.status === 'completed' ? 'border-green-400 text-green-600' : ''}`}>{d.status}</Badge>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* LEAVE TAB */}
        <TabsContent value="leave" className="mt-4">
          <LeavePanel currentUser={user} staff={staff} isHr={salaries.length >= 0 /* user has hr page access */} />
        </TabsContent>

        {/* REIMBURSEMENTS TAB */}
        <TabsContent value="reimbursements" className="mt-4">
          <ReimbursementsPanel currentUser={user} />
        </TabsContent>

        {/* ATTENDANCE TAB */}
        <TabsContent value="attendance" className="mt-4">
          <AttendancePanel currentUser={user} staff={staff} />
        </TabsContent>
        <TabsContent value="timesheets" className="mt-4">
          <TimesheetsPanel />
        </TabsContent>
        <TabsContent value="time-off" className="mt-4">
          <TimeOffPanel />
        </TabsContent>
        <TabsContent value="onboarding" className="mt-4">
          <OnboardingPanel onFix={(check, row) => {
            if (check === 'has_salary') {
              setSalaryForm({ staff_id: row.staff_id, base_salary: '', currency: 'UGX', pay_frequency: 'monthly', line_items: [] });
              setEditingSalaryId(null);
              setShowSalary(true);
              setActiveTab('salaries');
            } else if (check === 'has_contract') {
              setActiveTab('contracts');
              setShowIssueContract(true);
              // Contract form itself lets user pick staff; store hint via a shared "preselected" state
              try { localStorage.setItem('5812_onboarding_preselect_staff', row.staff_id); } catch { /* localStorage unavailable */ }
              toast(`Add contract for ${row.staff_name}`);
            } else if (check === 'has_chart_account') {
              toast('Go to Accounting → Cash Accounts → pick the location default and click "Assign Users"', { duration: 6000 });
            } else if (check === 'has_department' || check === 'has_location') {
              toast('Edit this user under People → Staff Directory to set their department/location.', { duration: 6000 });
            }
          }} />
        </TabsContent>
        {isAdmin && (
          <TabsContent value="staff" className="mt-4" data-testid="hr-tab-staff-content">
            {/* iter306 — staff/user admin lives inside HR now. AdminPage
                in mode="staff" renders just the directory + edit/reset/
                badge/bulk dialogs. The /admin route keeps the system-level
                cards (integrations, backup, branding, etc.). */}
            <AdminPage mode="staff" />
          </TabsContent>
        )}
      </Tabs>

      {/* Add/Edit Salary Dialog */}
      <Dialog open={showSalary} onOpenChange={(o) => { setShowSalary(o); if (!o) { setEditingSalaryId(null); setSalaryForm({ staff_id: '', base_salary: '', currency: 'UGX', pay_frequency: 'monthly', line_items: [] }); } }}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editingSalaryId ? 'Edit Salary Record' : 'Add Salary Record'}</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label>Staff Member *</Label>
              <Select value={salaryForm.staff_id} onValueChange={v => setSalaryForm({...salaryForm, staff_id: v})} disabled={!!editingSalaryId}>
                <SelectTrigger><SelectValue placeholder="Select staff" /></SelectTrigger>
                <SelectContent>{staff.map(s => <SelectItem key={s.id} value={s.id}>{s.name} ({s.role})</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>{(() => {
                  const wt = salaryForm.wage_type || 'salary';
                  if (wt === 'hourly') return 'Hourly Rate *';
                  if (wt === 'daily') return 'Daily Rate *';
                  if (wt === 'weekly') return 'Weekly Rate *';
                  if (wt === 'biweekly') return 'Biweekly Rate *';
                  return 'Monthly Salary *';
                })()}</Label>
                <Input type="number" value={salaryForm.base_salary} onChange={e => setSalaryForm({...salaryForm, base_salary: e.target.value})} data-testid="salary-base-input" />
                <p className="text-[10px] text-muted-foreground">
                  {(() => {
                    const wt = salaryForm.wage_type || 'salary';
                    if (wt === 'hourly') return 'Paid per hour worked. Payslip = rate × hours worked in the period.';
                    if (wt === 'daily') return 'Paid per day worked. E.g. 60,000/day × 10 working days = 600,000 per biweekly payslip.';
                    if (wt === 'weekly') return 'Fixed weekly rate. Biweekly period pays 2 weeks; monthly period pays ~4.33 weeks.';
                    if (wt === 'biweekly') return 'Fixed biweekly rate. Paid once per biweekly period; monthly pays ~2.17 biweekly cheques.';
                    return 'Fixed monthly salary. Biweekly period pays 12/26; weekly pays 12/52.';
                  })()}
                </p>
              </div>
              <div className="space-y-1.5"><Label>Currency</Label>
                <Select value={salaryForm.currency} onValueChange={v => setSalaryForm({...salaryForm, currency: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{['UGX','USD','KES','GBP','EUR','THB','HTG'].map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Rate Type</Label>
                <Select value={salaryForm.wage_type || 'salary'} onValueChange={v => setSalaryForm({...salaryForm, wage_type: v})}>
                  <SelectTrigger data-testid="salary-wage-type"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="salary">Monthly Salary</SelectItem>
                    <SelectItem value="hourly">Hourly</SelectItem>
                    <SelectItem value="daily">Daily</SelectItem>
                    <SelectItem value="weekly">Weekly</SelectItem>
                    <SelectItem value="biweekly">Biweekly</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label>Pay Frequency</Label>
                <Select value={salaryForm.pay_frequency} onValueChange={v => setSalaryForm({...salaryForm, pay_frequency: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="weekly">Weekly</SelectItem><SelectItem value="biweekly">Bi-weekly</SelectItem><SelectItem value="monthly">Monthly</SelectItem></SelectContent>
                </Select>
                <p className="text-[10px] text-muted-foreground">How often this staff member is actually paid — independent of Rate Type.</p>
              </div>
            </div>
            {/* Line Items */}
            <div className="space-y-2">
              <Label>Allowances & Deductions</Label>
              {salaryForm.line_items.map((li, i) => (
                <div key={i} className="flex items-center gap-2 text-xs p-2 rounded bg-muted/50">
                  <span className={li.type === 'deduction' ? 'text-red-600' : 'text-green-600'}>{li.type === 'deduction' ? '-' : '+'}</span>
                  <span className="flex-1">{li.name}</span>
                  <span>{li.is_percentage ? `${li.amount}%` : li.amount.toLocaleString()}</span>
                  <button onClick={() => setSalaryForm(prev => ({...prev, line_items: prev.line_items.filter((_, j) => j !== i)}))} className="text-destructive">x</button>
                </div>
              ))}
              <div className="flex gap-2">
                <Input className="flex-1 h-8 text-xs" placeholder="Name" value={lineItem.name} onChange={e => setLineItem({...lineItem, name: e.target.value})} />
                <Select value={lineItem.type} onValueChange={v => setLineItem({...lineItem, type: v})}>
                  <SelectTrigger className="w-28 h-8 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="allowance">Allowance</SelectItem><SelectItem value="deduction">Deduction</SelectItem></SelectContent>
                </Select>
                <Input className="w-20 h-8 text-xs" type="number" placeholder="Amount" value={lineItem.amount} onChange={e => setLineItem({...lineItem, amount: e.target.value})} />
                <Button size="sm" className="h-8" onClick={addLineItem}>+</Button>
              </div>
            </div>
            {/* iter-departments: multi-department tagging + funding splits.
                Departments are cost centres, not physical locations. Split
                percentages must sum to 100 (enforced client-side + server-side). */}
            <div className="space-y-2">
              <Label>Departments <span className="text-[10px] text-muted-foreground">(cost centres)</span></Label>
              <div className="flex flex-wrap gap-1.5 min-h-[24px]">
                {(salaryForm.department_ids || []).map(id => {
                  const d = availableDepartments.find(x => x.id === id);
                  if (!d) return null;
                  return (
                    <Badge key={id} variant="secondary" className="gap-1 text-xs cursor-pointer"
                      style={d.color ? { borderColor: d.color, color: d.color } : undefined}
                      onClick={() => setSalaryForm(prev => ({
                        ...prev,
                        department_ids: (prev.department_ids || []).filter(x => x !== id),
                        department_splits: (prev.department_splits || []).filter(s => s.department_id !== id),
                      }))}
                      data-testid={`salary-dept-chip-${id}`}
                    >
                      {d.color && <span className="w-2 h-2 rounded-full" style={{ background: d.color }} />}
                      {d.name} ×
                    </Badge>
                  );
                })}
                {(!salaryForm.department_ids || salaryForm.department_ids.length === 0) && (
                  <span className="text-[11px] text-muted-foreground italic pt-0.5">Untagged — funded from campus general fund</span>
                )}
              </div>
              <Select value="" onValueChange={id => {
                if (!id || (salaryForm.department_ids || []).includes(id)) return;
                setSalaryForm(prev => ({ ...prev, department_ids: [...(prev.department_ids || []), id] }));
              }}>
                <SelectTrigger data-testid="salary-dept-select" className="h-8 text-xs">
                  <SelectValue placeholder={availableDepartments.length ? 'Add department…' : 'No departments defined yet (Admin → Departments)'} />
                </SelectTrigger>
                <SelectContent>
                  {availableDepartments.filter(d => !(salaryForm.department_ids || []).includes(d.id)).map(d => (
                    <SelectItem key={d.id} value={d.id}>
                      <span className="inline-flex items-center gap-1.5">
                        {d.color && <span className="w-2 h-2 rounded-full" style={{ background: d.color }} />}
                        {d.name}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {salaryForm.department_ids && salaryForm.department_ids.length > 1 && (
              <div className="space-y-2 rounded-lg border border-primary/20 bg-primary/5 p-2">
                <div className="flex items-center justify-between">
                  <Label className="text-xs">Funding split</Label>
                  <button
                    type="button"
                    className="text-[11px] text-primary underline"
                    onClick={() => {
                      // Even split across all tagged departments
                      const n = salaryForm.department_ids.length;
                      const even = +(100 / n).toFixed(2);
                      const last = +(100 - even * (n - 1)).toFixed(2);
                      const splits = salaryForm.department_ids.map((id, i) => ({ department_id: id, pct: i === n - 1 ? last : even }));
                      setSalaryForm(prev => ({ ...prev, department_splits: splits }));
                    }}
                    data-testid="salary-split-even-btn"
                  >
                    Split evenly
                  </button>
                </div>
                {salaryForm.department_ids.map(id => {
                  const d = availableDepartments.find(x => x.id === id);
                  const split = (salaryForm.department_splits || []).find(s => s.department_id === id);
                  return (
                    <div key={id} className="flex items-center gap-2 text-xs">
                      {d?.color && <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: d.color }} />}
                      <span className="flex-1 truncate">{d?.name || id}</span>
                      <Input
                        type="number" min={0} max={100} step="0.01"
                        className="h-7 w-20 text-xs"
                        value={split ? String(split.pct) : ''}
                        onChange={e => {
                          const pct = e.target.value;
                          setSalaryForm(prev => {
                            const others = (prev.department_splits || []).filter(s => s.department_id !== id);
                            return { ...prev, department_splits: [...others, { department_id: id, pct: pct === '' ? 0 : parseFloat(pct) }] };
                          });
                        }}
                        data-testid={`salary-split-input-${id}`}
                      />
                      <span className="text-muted-foreground">%</span>
                    </div>
                  );
                })}
                {(() => {
                  const total = (salaryForm.department_splits || []).reduce((s, x) => s + (parseFloat(x.pct) || 0), 0);
                  const ok = Math.abs(total - 100) < 0.01;
                  return <p className={`text-[11px] ${ok ? 'text-emerald-600' : 'text-red-600'}`}>Total: {total.toFixed(2)}% {ok ? '✓' : '(must be 100)'}</p>;
                })()}
              </div>
            )}
            {editingSalaryId && (
              <div className="space-y-1.5">
                <Label className="text-xs">Reason for change (optional)</Label>
                <Input value={editReason} onChange={e => setEditReason(e.target.value)} placeholder="e.g. annual raise, promotion, role change" data-testid="salary-edit-reason" />
              </div>
            )}
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => { setShowSalary(false); setEditingSalaryId(null); setEditReason(''); }}>Cancel</Button>
              <Button className="flex-1" onClick={handleCreateSalary} disabled={saving || !salaryForm.staff_id || !salaryForm.base_salary} data-testid="salary-save-btn">{saving ? 'Saving...' : (editingSalaryId ? 'Save' : 'Create')}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Payslip Dialog (iter209b) */}
      <Dialog open={!!editingPayslip} onOpenChange={o => !o && setEditingPayslip(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Edit Payslip — {editingPayslip?.staff_name}</DialogTitle></DialogHeader>
          {editingPayslip && (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">Period {editingPayslip.period} · {editingPayslip.currency} · ID {editingPayslip.id}</p>
              <div className="grid grid-cols-2 gap-3">
                <div><Label>Gross Salary</Label><Input type="number" value={editPayslipForm.gross_salary} onChange={e => setEditPayslipForm({...editPayslipForm, gross_salary: e.target.value})} data-testid="edit-payslip-gross" /></div>
                <div><Label>Status</Label>
                  <Select value={editPayslipForm.status} onValueChange={v => setEditPayslipForm({...editPayslipForm, status: v})}>
                    <SelectTrigger data-testid="edit-payslip-status"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="draft">Draft</SelectItem>
                      <SelectItem value="approved">Approved</SelectItem>
                      <SelectItem value="paid">Paid</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div><Label>Allowances</Label><Input type="number" value={editPayslipForm.allowances} onChange={e => setEditPayslipForm({...editPayslipForm, allowances: e.target.value})} data-testid="edit-payslip-allowances" /></div>
                <div><Label>Deductions</Label><Input type="number" value={editPayslipForm.deductions} onChange={e => setEditPayslipForm({...editPayslipForm, deductions: e.target.value})} data-testid="edit-payslip-deductions" /></div>
                <div className="col-span-2">
                  <Label className="flex items-center gap-1">Cash account to pay from <span className="text-[10px] text-muted-foreground">(overrides location default)</span></Label>
                  <Select value={editPayslipForm.paid_from_account_id || 'default'} onValueChange={v => setEditPayslipForm({...editPayslipForm, paid_from_account_id: v === 'default' ? '' : v})}>
                    <SelectTrigger data-testid="edit-payslip-paid-from"><SelectValue placeholder="Location default" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="default">Location default</SelectItem>
                      {cashAccountOptions.map(a => <SelectItem key={a.id} value={a.id}>{a.name} · {a.currency} {(a.balance || 0).toLocaleString()}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="col-span-2">
                  <Label className="flex items-center gap-1">Location to charge <span className="text-[10px] text-muted-foreground">(overrides staff&apos;s location)</span></Label>
                  <Select value={editPayslipForm.payroll_location_id || 'default'} onValueChange={v => setEditPayslipForm({...editPayslipForm, payroll_location_id: v === 'default' ? '' : v})}>
                    <SelectTrigger data-testid="edit-payslip-location"><SelectValue placeholder="Staff&apos;s assigned location" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="default">Staff&apos;s assigned location</SelectItem>
                      {locationOptions.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="p-2 bg-muted rounded text-sm"><strong>Net (auto):</strong> {editingPayslip.currency} {(parseFloat(editPayslipForm.gross_salary || 0) + parseFloat(editPayslipForm.allowances || 0) - parseFloat(editPayslipForm.deductions || 0)).toLocaleString()}</div>
              <div><Label>Notes</Label><Textarea rows={2} value={editPayslipForm.notes} onChange={e => setEditPayslipForm({...editPayslipForm, notes: e.target.value})} data-testid="edit-payslip-notes" /></div>
              <div><Label>Reason for edit (audit) *</Label><Input placeholder="e.g. Corrected overtime calculation" value={editPayslipReason} onChange={e => setEditPayslipReason(e.target.value)} data-testid="edit-payslip-reason" /></div>
              <p className="text-[10px] text-muted-foreground">All changes are logged to the audit trail with your name + timestamp.</p>
            </div>
          )}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditingPayslip(null)}>Cancel</Button>
            <Button data-testid="save-payslip-edit-btn" onClick={async () => {
              if (!editPayslipReason.trim()) { toast.error('Please provide a reason for the edit'); return; }
              try {
                const payload = {
                  gross_salary: parseFloat(editPayslipForm.gross_salary) || 0,
                  allowances: parseFloat(editPayslipForm.allowances) || 0,
                  deductions: parseFloat(editPayslipForm.deductions) || 0,
                  notes: editPayslipForm.notes,
                  status: editPayslipForm.status,
                  paid_from_account_id: editPayslipForm.paid_from_account_id || '',
                  payroll_location_id: editPayslipForm.payroll_location_id || '',
                  reason: editPayslipReason,
                };
                const r = await api.put(`/hr/payslips/${editingPayslip.id}`, payload);
                setPayslips(prev => prev.map(x => x.id === editingPayslip.id ? r.data : x));
                setEditingPayslip(null);
                toast.success('Payslip updated');
              } catch (err) { toast.error(err.response?.data?.detail || 'Save failed'); }
            }}>Save changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Payslip History Dialog (audit trail + payroll split allocations) */}
      <Dialog open={!!payslipHistory} onOpenChange={o => !o && setPayslipHistory(null)}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Edit History — {payslipHistory?.payslip?.staff_name}</DialogTitle></DialogHeader>
          {payslipHistory && (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">Created {payslipHistory.created_at?.slice(0,10)} by {payslipHistory.created_by_name}</p>
              {payslipHistory.allocations && payslipHistory.allocations.length > 0 && (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 space-y-1" data-testid="payslip-allocation-strip">
                  <p className="text-[11px] uppercase tracking-wide font-medium text-emerald-800">Department funding split</p>
                  <div className="space-y-1">
                    {payslipHistory.allocations.map(a => (
                      <div key={a.id} className="flex items-center gap-2 text-xs">
                        {a.department_color && <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: a.department_color }} />}
                        <span className="flex-1">{a.department_name || a.department_id}</span>
                        <span className="font-mono">{Number(a.amount || 0).toLocaleString()} {a.currency}</span>
                        <span className="text-muted-foreground text-[10px]">({a.pct}%)</span>
                      </div>
                    ))}
                  </div>
                  <p className="text-[10px] text-emerald-700 italic">Aggregate expense JE unchanged — this is the cost-centre breakdown for department P&amp;L.</p>
                </div>
              )}
              {payslipHistory.history.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-8">No edits recorded yet.</p>
              ) : (
                <div className="space-y-3">
                  {payslipHistory.history.slice().reverse().map((h, i) => (
                    <Card key={i} className="border-l-4 border-l-amber-400">
                      <CardContent className="p-3 text-xs space-y-1">
                        <p className="font-medium">{h.by_name || 'Unknown'} · {h.at?.slice(0, 16).replace('T', ' ')}</p>
                        {h.reason && <p className="italic text-muted-foreground">&ldquo;{h.reason}&rdquo;</p>}
                        <div className="space-y-1 mt-2">
                          {Object.entries(h.changes || {}).map(([k, v]) => (
                            <div key={k} className="flex justify-between border-b py-1"><span className="capitalize font-medium">{k}:</span><span className="text-muted-foreground">{JSON.stringify(v.old)} → <span className="text-emerald-600 font-mono">{JSON.stringify(v.new)}</span></span></div>
                          ))}
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </div>
          )}
          <DialogFooter><Button variant="ghost" onClick={() => setPayslipHistory(null)}>Close</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Generate Payslips Dialog — payday-driven per campus HR settings */}
      <Dialog open={showPayslipGen} onOpenChange={(o) => { setShowPayslipGen(o); if (!o) setPreviewRows(null); }}>
        <DialogContent className={previewRows ? 'max-w-3xl max-h-[92vh] overflow-y-auto' : 'max-w-sm'}>
          <DialogHeader><DialogTitle>Generate Payslips</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5">
              <Label>Payday *</Label>
              {paydaysLoading ? (
                <div className="h-9 rounded-md border border-input bg-muted/40 animate-pulse" />
              ) : upcomingPaydays.length === 0 ? (
                <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-2">
                  No paydays available. Enable HR and set pay frequency + next pay date in <strong>HR Settings</strong>.
                </p>
              ) : (
                <Select value={selectedPayday} onValueChange={(v) => { setSelectedPayday(v); setPreviewRows(null); }}>
                  <SelectTrigger data-testid="pay-period-select"><SelectValue placeholder="Choose payday…" /></SelectTrigger>
                  <SelectContent>
                    {upcomingPaydays.map(p => {
                      const d = new Date(p.date + 'T00:00:00');
                      const label = d.toLocaleDateString(undefined, { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' });
                      return (
                        <SelectItem key={p.period} value={p.period} data-testid={`payday-opt-${p.date}`}>
                          {label}{paydayFrequency !== 'monthly' ? ` · ${p.period.split(' ')[1] || ''}` : ''}
                        </SelectItem>
                      );
                    })}
                  </SelectContent>
                </Select>
              )}
              <p className="text-[10px] text-muted-foreground">
                Paydays follow the campus <strong>{paydayFrequency}</strong> schedule. Adjust in HR Settings.
              </p>
              {paydayFrequency !== 'monthly' && selectedPayday && (() => {
                const match = String(selectedPayday).match(/^(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})/);
                if (!match) return null;
                const [, startIso, endIso] = match;
                const fmt = (iso) => new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
                return (
                  <div className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1.5 text-[11px] text-emerald-800" data-testid="pay-window-explainer">
                    Covers work performed from <strong>{fmt(startIso)}</strong> to <strong>{fmt(endIso)}</strong> ({paydayFrequency === 'weekly' ? '1 week' : '2 weeks'}). Amounts are pro-rated from each monthly base salary.
                  </div>
                );
              })()}
            </div>

            {previewRows === null ? (
              <>
                <p className="text-xs text-muted-foreground">{salaries.length} active salary records will be processed.</p>
                <div className="flex gap-3">
                  <Button variant="outline" className="flex-1" onClick={() => setShowPayslipGen(false)}>Cancel</Button>
                  <Button variant="secondary" className="flex-1" onClick={handlePreviewPayslips} disabled={previewLoading || !selectedPayday} data-testid="preview-payslips-btn">
                    {previewLoading ? 'Previewing…' : 'Preview'}
                  </Button>
                </div>
              </>
            ) : (
              <>
                <div className="rounded-md border" data-testid="payslip-preview-table">
                  <table className="w-full text-xs">
                    <thead className="bg-muted/50">
                      <tr>
                        <th className="text-left px-2 py-1.5">Staff</th>
                        <th className="text-left px-2 py-1.5 hidden sm:table-cell">Dept</th>
                        <th className="text-right px-2 py-1.5">Gross</th>
                        <th className="text-right px-2 py-1.5 hidden sm:table-cell">Allowances</th>
                        <th className="text-right px-2 py-1.5 hidden sm:table-cell">Deductions</th>
                        <th className="text-right px-2 py-1.5">Net</th>
                        <th className="text-center px-2 py-1.5">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {previewRows.length === 0 ? (
                        <tr><td colSpan={7} className="text-center text-muted-foreground py-4">No active salary records for this campus.</td></tr>
                      ) : previewRows.map(r => (
                        <tr key={r.staff_id} className={r.already_generated ? 'opacity-50' : ''} data-testid={`preview-row-${r.staff_id}`}>
                          <td className="px-2 py-1.5">{r.staff_name}</td>
                          <td className="px-2 py-1.5 hidden sm:table-cell text-muted-foreground">{r.department || '—'}</td>
                          <td className="px-2 py-1.5 text-right">
                            {r.currency} {r.gross.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                            {r.wage_details && (
                              <div className="text-[10px] text-muted-foreground font-normal">{r.wage_details}</div>
                            )}
                          </td>
                          <td className="px-2 py-1.5 text-right hidden sm:table-cell text-emerald-700">+{r.allowances.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                          <td className="px-2 py-1.5 text-right hidden sm:table-cell text-amber-700">-{r.deductions.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                          <td className="px-2 py-1.5 text-right font-semibold">{r.currency} {r.net.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                          <td className="px-2 py-1.5 text-center">
                            {r.already_generated ? (
                              <span className="text-[10px] rounded-full bg-slate-200 text-slate-700 px-2 py-0.5">Existing — skipped</span>
                            ) : (
                              <span className="text-[10px] rounded-full bg-emerald-100 text-emerald-700 px-2 py-0.5">Will draft</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    {previewRows.length > 0 && (
                      <tfoot className="bg-muted/30">
                        <tr>
                          <td colSpan={5} className="px-2 py-1.5 text-right font-medium text-muted-foreground">Total net pay ({previewRows.filter(r => !r.already_generated).length} new payslips)</td>
                          <td className="px-2 py-1.5 text-right font-bold" data-testid="preview-total-net">
                            {previewRows[0].currency} {previewRows.filter(r => !r.already_generated).reduce((s, r) => s + r.net, 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                          </td>
                          <td></td>
                        </tr>
                      </tfoot>
                    )}
                  </table>
                </div>
                <div className="flex gap-3">
                  <Button variant="outline" className="flex-1" onClick={() => setPreviewRows(null)}>Back</Button>
                  <Button className="flex-1" onClick={handleGeneratePayslips} disabled={saving || !selectedPayday || previewRows.every(r => r.already_generated)} data-testid="generate-payslips-submit">
                    {saving ? 'Generating…' : `Draft ${previewRows.filter(r => !r.already_generated).length} Payslip${previewRows.filter(r => !r.already_generated).length === 1 ? '' : 's'}`}
                  </Button>
                </div>
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Manual Payslip Dialog — HR types amount + deductions for an arbitrary staff member */}
      <Dialog open={showManualPayslip} onOpenChange={setShowManualPayslip}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto" data-testid="manual-payslip-dialog">
          <DialogHeader>
            <DialogTitle>Manual Payslip</DialogTitle>
            <p className="text-xs text-muted-foreground mt-1">
              Issue a one-off payslip without a recurring salary record — for casual workers, bonuses, severance, hardship payments, etc.
            </p>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Staff member *</Label>
              <Select value={manualPayslip.staff_id} onValueChange={v => setManualPayslip({ ...manualPayslip, staff_id: v })}>
                <SelectTrigger data-testid="manual-payslip-staff"><SelectValue placeholder="Select staff…" /></SelectTrigger>
                <SelectContent>
                  {staff.map(s => <SelectItem key={s.id} value={s.id}>{s.name} {s.department ? `· ${s.department}` : ''}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Pay period *</Label>
                <Input type="month" value={manualPayslip.period} onChange={e => setManualPayslip({ ...manualPayslip, period: e.target.value })} data-testid="manual-payslip-period" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Currency</Label>
                <Input value={manualPayslip.currency} onChange={e => setManualPayslip({ ...manualPayslip, currency: e.target.value.toUpperCase() })} maxLength={4} className="font-mono uppercase" data-testid="manual-payslip-currency" />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Gross amount *</Label>
              <Input type="number" value={manualPayslip.gross_salary} onChange={e => setManualPayslip({ ...manualPayslip, gross_salary: e.target.value })} placeholder="500000" data-testid="manual-payslip-gross" />
            </div>

            {/* Allowances */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label className="text-xs text-emerald-700">Allowances (+)</Label>
                <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={() => setManualPayslip({ ...manualPayslip, allowances: [...manualPayslip.allowances, { name: '', amount: '' }] })} data-testid="manual-payslip-add-allowance">
                  <Plus size={10} className="mr-1" /> Add
                </Button>
              </div>
              {manualPayslip.allowances.map((a, i) => (
                <div key={i} className="flex gap-1.5" data-testid={`manual-payslip-allowance-${i}`}>
                  <Input className="flex-1 h-8 text-xs" placeholder="Transport" value={a.name} onChange={e => { const next = [...manualPayslip.allowances]; next[i] = { ...next[i], name: e.target.value }; setManualPayslip({ ...manualPayslip, allowances: next }); }} />
                  <Input className="w-24 h-8 text-xs" type="number" placeholder="0" value={a.amount} onChange={e => { const next = [...manualPayslip.allowances]; next[i] = { ...next[i], amount: e.target.value }; setManualPayslip({ ...manualPayslip, allowances: next }); }} />
                  <Button size="sm" variant="ghost" className="h-8 px-2 text-destructive" onClick={() => setManualPayslip({ ...manualPayslip, allowances: manualPayslip.allowances.filter((_, j) => j !== i) })}>×</Button>
                </div>
              ))}
            </div>

            {/* Deductions */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label className="text-xs text-rose-700">Deductions (−)</Label>
                <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={() => setManualPayslip({ ...manualPayslip, deductions: [...manualPayslip.deductions, { name: '', amount: '' }] })} data-testid="manual-payslip-add-deduction">
                  <Plus size={10} className="mr-1" /> Add
                </Button>
              </div>
              {manualPayslip.deductions.map((d, i) => (
                <div key={i} className="flex gap-1.5" data-testid={`manual-payslip-deduction-${i}`}>
                  <Input className="flex-1 h-8 text-xs" placeholder="NSSF / PAYE / Loan" value={d.name} onChange={e => { const next = [...manualPayslip.deductions]; next[i] = { ...next[i], name: e.target.value }; setManualPayslip({ ...manualPayslip, deductions: next }); }} />
                  <Input className="w-24 h-8 text-xs" type="number" placeholder="0" value={d.amount} onChange={e => { const next = [...manualPayslip.deductions]; next[i] = { ...next[i], amount: e.target.value }; setManualPayslip({ ...manualPayslip, deductions: next }); }} />
                  <Button size="sm" variant="ghost" className="h-8 px-2 text-destructive" onClick={() => setManualPayslip({ ...manualPayslip, deductions: manualPayslip.deductions.filter((_, j) => j !== i) })}>×</Button>
                </div>
              ))}
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">Notes (optional)</Label>
              <Textarea rows={2} value={manualPayslip.notes} onChange={e => setManualPayslip({ ...manualPayslip, notes: e.target.value })} placeholder="End-of-year bonus, severance pay, etc." data-testid="manual-payslip-notes" />
            </div>

            {/* Live preview */}
            {(() => {
              const g = Number(manualPayslip.gross_salary || 0);
              const a = manualPayslip.allowances.reduce((sum, x) => sum + Number(x.amount || 0), 0);
              const d = manualPayslip.deductions.reduce((sum, x) => sum + Number(x.amount || 0), 0);
              const net = g + a - d;
              return (
                <div className="p-2 rounded bg-muted/40 text-xs space-y-0.5" data-testid="manual-payslip-preview">
                  <div className="flex justify-between"><span>Gross</span><span className="font-mono">{manualPayslip.currency} {g.toLocaleString()}</span></div>
                  <div className="flex justify-between text-emerald-700"><span>+ Allowances</span><span className="font-mono">{a.toLocaleString()}</span></div>
                  <div className="flex justify-between text-rose-700"><span>− Deductions</span><span className="font-mono">{d.toLocaleString()}</span></div>
                  <div className="flex justify-between font-semibold border-t pt-0.5"><span>Net</span><span className="font-mono">{net.toLocaleString()}</span></div>
                </div>
              );
            })()}

            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowManualPayslip(false)}>Cancel</Button>
              <Button
                className="flex-1"
                disabled={savingManual || !manualPayslip.staff_id || !manualPayslip.gross_salary}
                data-testid="manual-payslip-issue"
                onClick={async () => {
                  setSavingManual(true);
                  try {
                    const payload = {
                      staff_id: manualPayslip.staff_id,
                      period: manualPayslip.period,
                      gross_salary: Number(manualPayslip.gross_salary),
                      currency: manualPayslip.currency || 'UGX',
                      allowances: manualPayslip.allowances.filter(x => x.amount && Number(x.amount) > 0),
                      deductions: manualPayslip.deductions.filter(x => x.amount && Number(x.amount) > 0),
                      notes: manualPayslip.notes,
                    };
                    const res = await api.post('/hr/payslips/manual', payload);
                    toast.success(`Payslip issued — ${res.data.currency} ${res.data.net_salary.toLocaleString()} net`);
                    setPayslips(prev => [res.data, ...prev]);
                    setShowManualPayslip(false);
                    setManualPayslip({ staff_id: '', period: new Date().toISOString().slice(0, 7), gross_salary: '', currency: 'UGX', allowances: [], deductions: [], notes: '' });
                  } catch (e) {
                    toast.error(e.response?.data?.detail || 'Failed to issue payslip');
                  } finally {
                    setSavingManual(false);
                  }
                }}
              >
                {savingManual ? 'Issuing…' : 'Issue payslip'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Create Template Dialog */}
      <Dialog open={showTemplate} onOpenChange={setShowTemplate}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Create Contract Template</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label>Template Name *</Label><Input value={templateForm.name} onChange={e => setTemplateForm({...templateForm, name: e.target.value})} placeholder="e.g. Standard Employment Contract" /></div>
            <div className="space-y-1.5"><Label>Content</Label><p className="text-[10px] text-muted-foreground">Use {'{{staff_name}}'}, {'{{role}}'}, {'{{department}}'}, {'{{salary}}'}, {'{{start_date}}'} as variables</p>
              <Textarea rows={12} value={templateForm.content} onChange={e => setTemplateForm({...templateForm, content: e.target.value})} placeholder="This Employment Contract is entered into between 58:12 Global and {{staff_name}}..." />
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowTemplate(false)}>Cancel</Button>
              <Button className="flex-1" onClick={handleCreateTemplate} disabled={saving || !templateForm.name}>{saving ? 'Saving...' : 'Create'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Issue Contract Dialog */}
      <Dialog open={showIssueContract} onOpenChange={setShowIssueContract}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Issue Contract</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label>Template *</Label>
              <Select value={issueForm.template_id} onValueChange={v => setIssueForm({...issueForm, template_id: v})}>
                <SelectTrigger><SelectValue placeholder="Select template" /></SelectTrigger>
                <SelectContent>{templates.map(t => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label>Staff Member *</Label>
              <Select value={issueForm.staff_id} onValueChange={v => setIssueForm({...issueForm, staff_id: v})}>
                <SelectTrigger><SelectValue placeholder="Select staff" /></SelectTrigger>
                <SelectContent>{staff.map(s => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Start Date</Label><Input type="date" value={issueForm.start_date} onChange={e => setIssueForm({...issueForm, start_date: e.target.value})} /></div>
              <div className="space-y-1.5"><Label>Salary</Label><Input value={issueForm.salary} onChange={e => setIssueForm({...issueForm, salary: e.target.value})} /></div>
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowIssueContract(false)}>Cancel</Button>
              <Button className="flex-1" onClick={handleIssueContract} disabled={saving || !issueForm.template_id || !issueForm.staff_id}>{saving ? 'Issuing...' : 'Issue & Send'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Document Request Dialog */}
      <Dialog open={showDocReq} onOpenChange={setShowDocReq}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Request Documents</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label>Staff Member *</Label>
              <Select value={docReqForm.staff_id} onValueChange={v => setDocReqForm({...docReqForm, staff_id: v})}>
                <SelectTrigger><SelectValue placeholder="Select staff" /></SelectTrigger>
                <SelectContent>{staff.map(s => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label>Documents to Request</Label>
              <div className="flex flex-wrap gap-2">
                {['resume', 'id_document', 'passport', 'tax_id', 'bank_details', 'reference_letter', 'medical_certificate', 'police_clearance'].map(dt => (
                  <label key={dt} className="flex items-center gap-1.5 text-xs cursor-pointer">
                    <input type="checkbox" className="accent-primary" checked={(docReqForm.doc_types || []).includes(dt)} onChange={e => setDocReqForm(prev => ({ ...prev, doc_types: e.target.checked ? [...(prev.doc_types || []), dt] : (prev.doc_types || []).filter(d => d !== dt) }))} />
                    {dt.replace(/_/g, ' ')}
                  </label>
                ))}
              </div>
            </div>
            <div className="space-y-1.5"><Label>Message</Label><Textarea rows={2} value={docReqForm.message} onChange={e => setDocReqForm({...docReqForm, message: e.target.value})} placeholder="Please submit by..." /></div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowDocReq(false)}>Cancel</Button>
              <Button className="flex-1" onClick={handleDocRequest} disabled={saving || !docReqForm.staff_id}>{saving ? 'Sending...' : 'Send Request'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* HR Settings Dialog */}
      <Dialog open={showSettings} onOpenChange={setShowSettings}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>HR Settings</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="flex items-center justify-between">
              <div><p className="text-sm font-medium">HR Module Enabled</p><p className="text-xs text-muted-foreground">Enable HR features for this campus</p></div>
              <Switch checked={settingsForm.hr_enabled} onCheckedChange={v => setSettingsForm({...settingsForm, hr_enabled: v})} data-testid="hr-enabled-toggle" />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5"><Label>Pay Frequency</Label>
                <Select value={settingsForm.pay_frequency} onValueChange={v => {
                  // iter 335 anchor nudge: switching TO biweekly/weekly with no
                  // Next Pay Date pre-fills the coming Wednesday (or the
                  // configured pay_run_weekday) so the required field is never
                  // blank on save.
                  const next = { ...settingsForm, pay_frequency: v };
                  const needsAnchor = ['weekly', 'biweekly', 'bi-weekly', 'fortnightly'].includes(v.toLowerCase());
                  if (needsAnchor && !settingsForm.next_pay_date) {
                    const target = settingsForm.payday_weekday != null ? parseInt(settingsForm.payday_weekday) : 2; // 2 = Wed default
                    const today = new Date();
                    const delta = (target - today.getDay() + 7) % 7 || 7; // upcoming target weekday (never today)
                    const nextDate = new Date(today.getTime() + delta * 86400000);
                    next.next_pay_date = nextDate.toISOString().slice(0, 10);
                    toast.info(`Next Pay Date pre-filled to ${nextDate.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })} — tweak if needed.`);
                  }
                  setSettingsForm(next);
                }}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="weekly">Weekly</SelectItem><SelectItem value="biweekly">Bi-weekly</SelectItem><SelectItem value="monthly">Monthly</SelectItem></SelectContent>
                </Select>
              </div>
              {/* iter 334: day-of-month payday only makes sense for MONTHLY.
                  Biweekly / weekly cadences are anchor-driven — future
                  paydays are calculated from Next Pay Date every 14 or 7 days.
                  Showing the day-of-month picker for those frequencies caused
                  staff to misread payslip amounts. */}
              {(settingsForm.pay_frequency || 'monthly').toLowerCase() === 'monthly' ? (
                <div className="space-y-1.5">
                  <Label>Payday (day of month)</Label>
                  <Select value={String(settingsForm.pay_day || 28)} onValueChange={v => setSettingsForm({...settingsForm, pay_day: parseInt(v) || 28})}>
                    <SelectTrigger data-testid="pay-day-picker"><SelectValue /></SelectTrigger>
                    <SelectContent className="max-h-64">
                      {Array.from({length: 31}, (_, i) => i + 1).map(d => (
                        <SelectItem key={d} value={String(d)}>{d}{d === 1 ? 'st' : d === 2 ? 'nd' : d === 3 ? 'rd' : d === 21 ? 'st' : d === 22 ? 'nd' : d === 23 ? 'rd' : d === 31 ? 'st' : 'th'} of the month</SelectItem>
                      ))}
                      <SelectItem value="99">Last day of month</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-[10px] text-muted-foreground">Payslips are drafted automatically each month on this day. If it&apos;s a weekend or holiday, payslips still draft — payment can be issued on the next working day.</p>
                </div>
              ) : (
                <div className="space-y-1.5 col-span-1">
                  <Label className="text-muted-foreground">Payday</Label>
                  <div className="rounded-md border border-dashed border-muted-foreground/30 bg-muted/30 px-3 py-2">
                    <p className="text-[11px] text-muted-foreground">
                      Not needed for {settingsForm.pay_frequency}. Future paydays
                      are calculated from <strong>Next Pay Date</strong> every {(settingsForm.pay_frequency || '').toLowerCase() === 'weekly' ? '7' : '14'} days.
                    </p>
                  </div>
                </div>
              )}
              <div className="space-y-1.5"><Label>Next Pay Date <span className="text-[10px] text-red-500">*</span></Label><Input type="date" value={settingsForm.next_pay_date || ''} onChange={e => setSettingsForm({...settingsForm, next_pay_date: e.target.value})} data-testid="next-pay-date" />
                {(settingsForm.pay_frequency || 'monthly').toLowerCase() !== 'monthly' && !settingsForm.next_pay_date && (
                  <p className="text-[10px] text-red-600">Required for {settingsForm.pay_frequency} — every future payday and pay period is derived from this date.</p>
                )}
              </div>
            </div>
            {/* iter309 — weekly/bi-weekly payday-on-weekday.
                Hidden for monthly cadence because monthly still uses
                `pay_day` (day-of-month). For weekly/biweekly the admin
                picks the weekday the run should always land on, e.g.
                "the last two Mon-Sun weeks always pay on Wednesday". */}
            {['weekly', 'biweekly', 'bi-weekly', 'fortnightly'].includes((settingsForm.pay_frequency || '').toLowerCase()) && (
              <div className="grid grid-cols-2 gap-3 -mt-2">
                <div className="space-y-1.5">
                  <Label>Pay Run Weekday</Label>
                  <Select value={settingsForm.payday_weekday == null ? '__none__' : String(settingsForm.payday_weekday)} onValueChange={v => setSettingsForm({...settingsForm, payday_weekday: v === '__none__' ? null : parseInt(v)})}>
                    <SelectTrigger data-testid="payday-weekday-picker"><SelectValue placeholder="Not set — use anchor date" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">Not set — use anchor date</SelectItem>
                      <SelectItem value="0">Monday</SelectItem>
                      <SelectItem value="1">Tuesday</SelectItem>
                      <SelectItem value="2">Wednesday</SelectItem>
                      <SelectItem value="3">Thursday</SelectItem>
                      <SelectItem value="4">Friday</SelectItem>
                      <SelectItem value="5">Saturday</SelectItem>
                      <SelectItem value="6">Sunday</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-[10px] text-muted-foreground">
                    Snap every payday to this weekday. Example: bi-weekly + Wednesday means the last two Mon-Sun weeks pay on the following Wednesday.
                  </p>
                </div>
              </div>
            )}

            {/* Country compliance picker */}
            <div className="border-t pt-3 space-y-2">
              <div className="flex items-center justify-between">
                <Label className="text-sm font-semibold">Compliance (deductions/additions)</Label>
                <Select value={settingsForm.country || 'Uganda'} onValueChange={v => setSettingsForm({...settingsForm, country: v})}>
                  <SelectTrigger className="w-32 h-8 text-xs" data-testid="compliance-country"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {['Uganda','Kenya','USA','Haiti','Thailand'].map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              {/* Existing lines */}
              {(settingsForm.compliance_lines || []).map((cl, i) => (
                <div key={i} className="grid grid-cols-[1fr_90px_90px_90px_24px] gap-2 items-center text-xs">
                  <Input className="h-8 text-xs" value={cl.name} onChange={e => {
                    const next = [...settingsForm.compliance_lines]; next[i] = {...next[i], name: e.target.value}; setSettingsForm({...settingsForm, compliance_lines: next});
                  }} />
                  <Select value={cl.type} onValueChange={v => {
                    const next = [...settingsForm.compliance_lines]; next[i] = {...next[i], type: v}; setSettingsForm({...settingsForm, compliance_lines: next});
                  }}>
                    <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="deduction">Deduction</SelectItem><SelectItem value="addition">Addition</SelectItem></SelectContent>
                  </Select>
                  <Input className="h-8 text-xs" type="number" step="0.01" value={cl.amount || 0} onChange={e => {
                    const next = [...settingsForm.compliance_lines]; next[i] = {...next[i], amount: parseFloat(e.target.value) || 0}; setSettingsForm({...settingsForm, compliance_lines: next});
                  }} />
                  <label className="flex items-center gap-1 text-[10px] cursor-pointer">
                    <input type="checkbox" checked={!!cl.is_percentage} onChange={e => {
                      const next = [...settingsForm.compliance_lines]; next[i] = {...next[i], is_percentage: e.target.checked}; setSettingsForm({...settingsForm, compliance_lines: next});
                    }} /> %
                  </label>
                  <button type="button" className="text-destructive" onClick={() => {
                    setSettingsForm({...settingsForm, compliance_lines: settingsForm.compliance_lines.filter((_, j) => j !== i)});
                  }}>×</button>
                </div>
              ))}
              {(settingsForm.compliance_lines || []).length === 0 && <p className="text-[10px] text-muted-foreground">No compliance lines yet. Add common ones for your country below.</p>}

              {/* Compliance options dropdown */}
              <ComplianceOptionsPicker
                country={settingsForm.country || 'Uganda'}
                onPick={(opt) => setSettingsForm(prev => ({
                  ...prev,
                  compliance_lines: [...(prev.compliance_lines || []), opt]
                }))}
              />
            </div>

            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowSettings(false)}>Cancel</Button>
              <Button className="flex-1" onClick={handleSaveSettings} data-testid="hr-settings-save">Save Settings</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Salary Change History Dialog */}
      <Dialog open={!!historySalary} onOpenChange={(o) => { if (!o) { setHistorySalary(null); setHistoryEntries([]); } }}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Salary Change History — {historySalary?.staff_name}</DialogTitle>
          </DialogHeader>
          <div className="mt-2 space-y-2">
            {historyLoading ? (
              <div className="space-y-2">{[1,2,3].map(i => <div key={i} className="h-16 bg-muted animate-pulse rounded" />)}</div>
            ) : historyEntries.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">No changes recorded yet.</p>
            ) : historyEntries.map(h => (
              <div key={h.id} className="border rounded-lg p-3 text-xs space-y-1" data-testid={`history-${h.id}`}>
                <div className="flex justify-between text-[11px] text-muted-foreground">
                  <span>{h.changed_at?.slice(0, 16).replace('T', ' ')}</span>
                  <span><span className="font-medium text-foreground">{h.changed_by_name || 'Unknown'}</span> <span className="opacity-70">({h.changed_by_role})</span></span>
                </div>
                <div className="space-y-0.5">
                  {Object.entries(h.changes || {}).map(([field, v]) => {
                    const isMoney = field === 'base_salary';
                    const fmtV = (x) => {
                      if (x == null) return '—';
                      if (Array.isArray(x)) return `${x.length} item(s)`;
                      if (isMoney) return Number(x).toLocaleString();
                      return String(x);
                    };
                    return (
                      <div key={field} className="flex items-baseline gap-2">
                        <span className="capitalize text-muted-foreground min-w-[6.5rem]">{field.replace(/_/g, ' ')}:</span>
                        <span className="line-through opacity-60">{fmtV(v.from)}</span>
                        <span className="text-muted-foreground">→</span>
                        <span className="font-semibold">{fmtV(v.to)}</span>
                      </div>
                    );
                  })}
                </div>
                {h.reason && <p className="italic text-muted-foreground border-t pt-1 mt-1">“{h.reason}”</p>}
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      {/* ─── Fix Ledger Postings — diagnostic + apply modal (HRPage-level) ─── */}
      <Dialog open={!!repairModal} onOpenChange={o => { if (!o) setRepairModal(null); }}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" data-testid="repair-modal">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Wrench size={16} className="text-amber-600" /> Fix Ledger Postings
            </DialogTitle>
          </DialogHeader>
          {repairModal?.busy && !repairModal?.data && (
            <div className="py-10 text-center text-sm text-muted-foreground">
              Scanning payslips, expenses and journal entries…
            </div>
          )}
          {repairModal?.data && (() => {
            const d = repairModal.data;
            const a = d.pass_a_missing_je || {};
            const b = d.pass_b_reconstruct || {};
            const c = d.pass_c_wrong_journal || {};
            const diag = d.diagnostics || {};
            const totalFixes = (a.count || 0) + (b.count || 0) + (c.scanned || 0);
            return (
              <div className="space-y-4 text-sm">
                <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 space-y-1.5" data-testid="repair-diagnostics">
                  <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Current ledger state</p>
                  <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                    <span className="text-slate-500">Paid payslips</span>
                    <span className="font-mono text-right">{diag.paid_payslips || 0} · UGX {(diag.paid_payslips_total_ugx || 0).toLocaleString()}</span>
                    <span className="text-slate-500">Aggregate expenses</span>
                    <span className="font-mono text-right">{diag.aggregate_expenses || 0} · UGX {(diag.aggregate_expenses_total_ugx || 0).toLocaleString()}</span>
                    <span className="text-slate-500">Active payroll JEs</span>
                    <span className="font-mono text-right">{diag.active_payroll_jes || 0} · UGX {(diag.active_payroll_jes_total_ugx || 0).toLocaleString()}</span>
                  </div>
                  <div className={`text-xs font-semibold mt-2 ${diag.in_sync ? 'text-emerald-700' : 'text-amber-700'}`}>
                    {diag.in_sync
                      ? '✓ In sync — expenses total matches ledger total'
                      : '⚠ Out of sync — expenses total ≠ ledger total (repair needed)'}
                  </div>
                </div>

                {totalFixes === 0 ? (
                  <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-3 text-emerald-800 text-sm" data-testid="repair-nothing-to-fix">
                    <p className="font-semibold">No repair needed.</p>
                    <p className="text-xs mt-1">All existing payroll expenses have matching journal entries and no paid payslips are missing an aggregate. If new payslips still aren&apos;t hitting the ledger after marking them paid, the issue is likely that their location lacks a Chart of Accounts — see below.</p>
                  </div>
                ) : (
                  <>
                    <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 space-y-2" data-testid="repair-plan">
                      <p className="text-xs font-semibold text-amber-900 uppercase tracking-wide">Repair plan</p>
                      <div className="space-y-1 text-xs text-amber-900">
                        <p>• <strong>{a.count || 0}</strong> payroll expense(s) missing journal entries (UGX {(a.total_amount || 0).toLocaleString()})</p>
                        <p>• <strong>{b.count || 0}</strong> paid payslip group(s) never aggregated (UGX {(b.total_amount || 0).toLocaleString()})</p>
                        <p>• <strong>{c.scanned || 0}</strong> journal entry(ies) mis-routed to Sales journals</p>
                      </div>
                      <p className="text-[11px] text-amber-800 italic">Idempotent · safe to re-run · not reversible.</p>
                    </div>
                    {repairModal.phase === 'preview' && (
                      <Button
                        className="w-full bg-amber-600 hover:bg-amber-700 text-white"
                        data-testid="repair-apply-btn"
                        disabled={repairModal.busy}
                        onClick={async () => {
                          setRepairModal({ ...repairModal, busy: true });
                          try {
                            const res = await api.post('/hr/repair-payslip-journals', { apply: true });
                            const ra = res.data.pass_a_missing_je || {};
                            const rb = res.data.pass_b_reconstruct || {};
                            const skippedLocs = res.data.locations_missing_accounts || [];
                            const fixed = (ra.count - (ra.skipped_no_accounts || 0)) + (rb.count - (rb.skipped_no_accounts || 0));
                            toast.success(`Repaired ${fixed} journal entr${fixed === 1 ? 'y' : 'ies'}${skippedLocs.length ? ` · ${skippedLocs.length} location(s) blocked` : ''}`);
                            setRepairModal({ busy: false, data: res.data, phase: 'applied' });
                          } catch (e) {
                            toast.error(e.response?.data?.detail || 'Repair failed');
                            setRepairModal({ ...repairModal, busy: false });
                          }
                        }}
                      >
                        {repairModal.busy ? 'Applying…' : `Apply ${totalFixes} fix${totalFixes === 1 ? '' : 'es'}`}
                      </Button>
                    )}
                  </>
                )}

                {(d.locations_missing_accounts || []).length > 0 && (
                  <div className="rounded-lg bg-rose-50 border border-rose-200 p-3 space-y-2" data-testid="repair-blocked">
                    <p className="text-xs font-semibold text-rose-900 uppercase tracking-wide">Blocked — missing Chart of Accounts</p>
                    <p className="text-xs text-rose-800">
                      These {d.locations_missing_accounts.length} location(s) don&apos;t have a Wages/Salaries expense account and a Cash asset account, so their payroll can&apos;t post:
                    </p>
                    <ul className="text-xs font-mono text-rose-900 pl-3">
                      {d.locations_missing_accounts.map(lid => <li key={lid}>· {lid}</li>)}
                    </ul>
                    <Button
                      size="sm"
                      className="w-full bg-rose-600 hover:bg-rose-700 text-white"
                      data-testid="repair-auto-wire-btn"
                      disabled={repairModal.busy}
                      onClick={async () => {
                        setRepairModal({ ...repairModal, busy: true });
                        try {
                          const seedRes = await api.post('/accounting/seed-bulk', { location_ids: d.locations_missing_accounts });
                          const seeded = seedRes.data.total_accounts_seeded || 0;
                          toast.success(`Auto-wired ${seeded} accounts. Re-running fixer…`);
                          const rerun = await api.post('/hr/repair-payslip-journals', { apply: true });
                          const na = rerun.data.pass_a_missing_je || {};
                          const nb = rerun.data.pass_b_reconstruct || {};
                          const rerunFixed = (na.count - (na.skipped_no_accounts || 0)) + (nb.count - (nb.skipped_no_accounts || 0));
                          toast.success(`Round 2: repaired ${rerunFixed} more JE${rerunFixed === 1 ? '' : 's'}. Trial balance should now be in sync.`, { duration: 6000 });
                          setRepairModal({ busy: false, data: rerun.data, phase: 'applied' });
                        } catch (e) {
                          toast.error(e.response?.data?.detail || 'Auto-wire failed');
                          setRepairModal({ ...repairModal, busy: false });
                        }
                      }}
                    >
                      {repairModal.busy ? 'Wiring…' : `Auto-wire Chart of Accounts + re-run`}
                    </Button>
                  </div>
                )}
              </div>
            );
          })()}
          <DialogFooter>
            <Button variant="outline" onClick={() => setRepairModal(null)} data-testid="repair-close-btn">Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ─── HR RESET DIALOG moved to Admin → System Console → Data & Backup ─── */}
    </div>
  );
}

function ComplianceOptionsPicker({ country, onPick }) {
  const [options, setOptions] = React.useState([]);
  React.useEffect(() => {
    if (!country) return;
    api.get(`/hr/compliance-options/${encodeURIComponent(country)}`)
      .then(r => setOptions(r.data?.options || []))
      .catch(() => setOptions([]));
  }, [country]);
  if (options.length === 0) return null;
  return (
    <div className="border border-dashed border-border rounded-md p-2 space-y-1">
      <p className="text-[10px] text-muted-foreground">Common {country} compliance — click to add:</p>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o, i) => (
          <Button key={i} type="button" size="sm" variant="outline" className="h-6 text-[10px]" onClick={() => onPick(o)} data-testid={`compliance-opt-${i}`}>
            + {o.name} {o.amount}{o.is_percentage ? '%' : ''}
          </Button>
        ))}
      </div>
    </div>
  );
}


// ========= Leave / Time-off Panel =========
function LeavePanel({ currentUser, staff }) {
  const [types, setTypes] = useState([]);
  const [requests, setRequests] = useState([]);
  const [balance, setBalance] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showRequest, setShowRequest] = useState(false);
  const [requestForm, setRequestForm] = useState({ leave_type: 'annual', start_date: '', end_date: '', half_day: false, notes: '', staff_id: '' });
  const [decideOn, setDecideOn] = useState(null);
  const [decisionNote, setDecisionNote] = useState('');
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [tRes, rRes, bRes] = await Promise.all([
        api.get('/hr/leave/types').catch(() => ({ data: [] })),
        api.get('/hr/leave/requests').catch(() => ({ data: [] })),
        api.get('/hr/leave/balance').catch(() => ({ data: null })),
      ]);
      setTypes(tRes.data || []);
      setRequests(rRes.data || []);
      setBalance(bRes.data);
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { reload(); }, [reload]);
  const typeMeta = (id) => types.find(t => t.id === id) || { name: id, color: '#6b7280' };
  const submitRequest = async () => {
    try {
      const payload = { ...requestForm };
      if (!payload.staff_id) delete payload.staff_id;
      await api.post('/hr/leave/requests', payload);
      toast.success('Leave request submitted');
      setShowRequest(false);
      setRequestForm({ leave_type: 'annual', start_date: '', end_date: '', half_day: false, notes: '', staff_id: '' });
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };
  const decide = async (newStatus) => {
    try {
      await api.put(`/hr/leave/requests/${decideOn.id}`, { status: newStatus, decision_note: decisionNote });
      toast.success(newStatus === 'approved' ? 'Approved' : newStatus === 'declined' ? 'Declined' : 'Updated');
      setDecideOn(null); setDecisionNote('');
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };
  if (loading) return <div className="space-y-2">{[1,2,3].map(i => <div key={i} className="h-16 bg-muted animate-pulse rounded" />)}</div>;
  return (
    <div className="space-y-4" data-testid="leave-panel">
      {/* Personal balances row */}
      {balance && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          {balance.balances.map(b => (
            <div key={b.type} className="rounded-lg border p-2.5" style={{ borderLeftWidth: 3, borderLeftColor: b.color }} data-testid={`leave-balance-${b.type}`}>
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{b.name}</p>
              <p className="text-lg font-bold">{b.remaining}<span className="text-xs text-muted-foreground font-normal">/{b.allocated}d</span></p>
              <p className="text-[10px] text-muted-foreground">{b.used} used this year</p>
            </div>
          ))}
        </div>
      )}
      <div className="flex justify-between items-center">
        <h3 className="text-sm font-semibold">Leave Requests</h3>
        <Button size="sm" className="gap-1.5" onClick={() => setShowRequest(true)} data-testid="leave-new-btn"><Plus size={13} /> New Request</Button>
      </div>
      {requests.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">No leave requests.</p> : (
        <div className="space-y-2">
          {requests.map(r => {
            const meta = typeMeta(r.leave_type);
            const canDecide = r.status === 'pending' && r.staff_id !== currentUser.id;
            const canCancel = r.status === 'pending' && r.staff_id === currentUser.id;
            return (
              <Card key={r.id} className="rounded-xl" data-testid={`leave-${r.id}`}>
                <CardContent className="p-3 flex items-center justify-between gap-3 flex-wrap">
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    <span className="w-2 h-10 rounded-full" style={{ backgroundColor: meta.color }} />
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{r.staff_name} <span className="text-muted-foreground font-normal">· {meta.name}</span></p>
                      <p className="text-xs text-muted-foreground">{r.start_date} → {r.end_date} · {r.days}{r.half_day ? '' : 'd'} {r.half_day ? '(half day)' : ''} {r.notes ? `· ${r.notes}` : ''}</p>
                      {r.decision_by_name && r.status !== 'pending' && (
                        <p className="text-[10px] text-muted-foreground italic">{r.status} by {r.decision_by_name}{r.decision_note ? ` — “${r.decision_note}”` : ''}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Badge className={`text-[10px] capitalize ${r.status === 'approved' ? 'bg-green-100 text-green-700' : r.status === 'declined' ? 'bg-red-100 text-red-700' : r.status === 'cancelled' ? 'bg-gray-100 text-gray-700' : 'bg-amber-100 text-amber-700'}`}>{r.status}</Badge>
                    {canDecide && (
                      <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => { setDecideOn(r); setDecisionNote(''); }} data-testid={`leave-decide-${r.id}`}>Decide</Button>
                    )}
                    {canCancel && (
                      <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive" onClick={async () => { if (!window.confirm('Cancel this request?')) return; await api.put(`/hr/leave/requests/${r.id}`, { status: 'cancelled' }); reload(); }} data-testid={`leave-cancel-${r.id}`}>Cancel</Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* New Request Dialog */}
      <Dialog open={showRequest} onOpenChange={setShowRequest}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New Leave Request</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Leave Type *</Label>
              <Select value={requestForm.leave_type} onValueChange={v => setRequestForm({...requestForm, leave_type: v})}>
                <SelectTrigger data-testid="leave-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>{types.map(t => <SelectItem key={t.id} value={t.id}>{t.name}{!t.paid ? ' (unpaid)' : ''}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Start Date *</Label><Input type="date" value={requestForm.start_date} onChange={e => setRequestForm({...requestForm, start_date: e.target.value})} data-testid="leave-start-input" /></div>
              <div className="space-y-1.5"><Label className="text-xs">End Date *</Label><Input type="date" value={requestForm.end_date} min={requestForm.start_date} onChange={e => setRequestForm({...requestForm, end_date: e.target.value})} data-testid="leave-end-input" /></div>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded border">
              <div><p className="text-sm font-medium">Half-day</p><p className="text-[10px] text-muted-foreground">For single-day requests only</p></div>
              <Switch checked={requestForm.half_day} onCheckedChange={v => setRequestForm({...requestForm, half_day: v})} disabled={!requestForm.start_date || requestForm.start_date !== requestForm.end_date} />
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Notes</Label><Textarea rows={2} value={requestForm.notes} onChange={e => setRequestForm({...requestForm, notes: e.target.value})} placeholder="Reason (optional)" /></div>
            {staff.length > 0 && (
              <div className="space-y-1.5">
                <Label className="text-xs">File for (HR only — leave blank for yourself)</Label>
                <Select value={requestForm.staff_id || 'self'} onValueChange={v => setRequestForm({...requestForm, staff_id: v === 'self' ? '' : v})}>
                  <SelectTrigger><SelectValue placeholder="Yourself" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="self">Yourself</SelectItem>
                    {staff.map(s => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowRequest(false)}>Cancel</Button>
              <Button className="flex-1" data-testid="leave-submit-btn" disabled={!requestForm.start_date || !requestForm.end_date} onClick={submitRequest}>Submit</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Decision Dialog */}
      <Dialog open={!!decideOn} onOpenChange={(o) => { if (!o) setDecideOn(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Decide Leave Request</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <p className="text-xs text-muted-foreground"><strong>{decideOn?.staff_name}</strong> requests <strong>{typeMeta(decideOn?.leave_type).name}</strong> {decideOn?.start_date} → {decideOn?.end_date} ({decideOn?.days}d).</p>
            <div className="space-y-1">
              <Label className="text-xs">Decision Note (optional)</Label>
              <Textarea rows={2} value={decisionNote} onChange={e => setDecisionNote(e.target.value)} data-testid="leave-decision-note" />
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="destructive" className="flex-1" onClick={() => decide('declined')} data-testid="leave-decline-btn">Decline</Button>
              <Button className="flex-1" onClick={() => decide('approved')} data-testid="leave-approve-btn">Approve</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}



// ========= Employee Expense Reimbursements Panel =========
function ReimbursementsPanel({ currentUser }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({ title: '', amount: '', currency: 'UGX', category: 'travel', date: new Date().toISOString().slice(0, 10), receipt_url: '', notes: '' });
  const [decideOn, setDecideOn] = useState(null);
  const [decisionNote, setDecisionNote] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const params = filterStatus !== 'all' ? { status: filterStatus } : {};
      const res = await api.get('/hr/expenses', { params });
      setRows(res.data || []);
    } finally { setLoading(false); }
  }, [filterStatus]);
  useEffect(() => { reload(); }, [reload]);

  const openNew = () => {
    setEditingId(null);
    setForm({ title: '', amount: '', currency: 'UGX', category: 'travel', date: new Date().toISOString().slice(0, 10), receipt_url: '', notes: '' });
    setShowForm(true);
  };
  const openEdit = (e) => {
    setEditingId(e.id);
    setForm({ title: e.title || '', amount: String(e.amount || ''), currency: e.currency || 'UGX', category: e.category || 'other', date: (e.date || '').slice(0, 10), receipt_url: e.receipt_url || '', notes: e.notes || '' });
    setShowForm(true);
  };
  const submit = async () => {
    if (!form.title || !form.amount) { toast.error('Title and amount required'); return; }
    try {
      const payload = { ...form, amount: parseFloat(form.amount) };
      if (editingId) await api.put(`/hr/expenses/${editingId}`, payload);
      else await api.post('/hr/expenses', payload);
      toast.success(editingId ? 'Saved' : 'Submitted');
      setShowForm(false); setEditingId(null);
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };
  const decide = async (newStatus) => {
    try {
      await api.put(`/hr/expenses/${decideOn.id}`, { status: newStatus, decision_note: decisionNote });
      toast.success(newStatus === 'approved' ? 'Approved' : newStatus === 'rejected' ? 'Rejected' : 'Reimbursed');
      setDecideOn(null); setDecisionNote('');
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const STATUS_COLORS = {
    pending: 'bg-amber-100 text-amber-700',
    approved: 'bg-blue-100 text-blue-700',
    rejected: 'bg-red-100 text-red-700',
    reimbursed: 'bg-green-100 text-green-700',
  };

  if (loading) return <div className="space-y-2">{[1,2,3].map(i => <div key={i} className="h-16 bg-muted animate-pulse rounded" />)}</div>;

  return (
    <div className="space-y-3" data-testid="reimbursements-panel">
      <div className="flex justify-between items-center gap-2">
        <div className="flex gap-1.5">
          {['all', 'pending', 'approved', 'reimbursed', 'rejected'].map(s => (
            <Button key={s} size="sm" variant={filterStatus === s ? 'default' : 'outline'} className="h-7 text-xs capitalize" onClick={() => setFilterStatus(s)} data-testid={`reim-filter-${s}`}>{s}</Button>
          ))}
        </div>
        <Button size="sm" className="gap-1.5" onClick={openNew} data-testid="reim-new-btn"><Plus size={13} /> New Expense</Button>
      </div>

      {rows.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">No expenses {filterStatus !== 'all' ? `in "${filterStatus}"` : ''}.</p> : (
        <div className="space-y-2">
          {rows.map(e => {
            const isOwner = e.staff_id === currentUser.id;
            const canEdit = isOwner && e.status === 'pending';
            return (
              <Card key={e.id} className="rounded-xl" data-testid={`reim-${e.id}`}>
                <CardContent className="p-3 flex items-center justify-between gap-3 flex-wrap">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-medium">{e.title}</p>
                      <Badge variant="outline" className="text-[10px] capitalize">{e.category}</Badge>
                      {!isOwner && <Badge variant="secondary" className="text-[10px]">{e.staff_name}</Badge>}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">{e.date} · {e.notes || 'No notes'}</p>
                    {e.receipt_url && <a href={e.receipt_url} target="_blank" rel="noopener noreferrer" className="text-[10px] text-primary hover:underline">View receipt</a>}
                    {e.decision_by_name && (
                      <p className="text-[10px] text-muted-foreground italic mt-0.5">{e.status} by {e.decision_by_name}{e.decision_note ? ` — “${e.decision_note}”` : ''}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="text-right">
                      <p className="text-sm font-bold">{e.currency} {(e.amount || 0).toLocaleString()}</p>
                    </div>
                    <Badge className={`text-[10px] capitalize ${STATUS_COLORS[e.status] || ''}`}>{e.status}</Badge>
                    <div className="flex gap-0.5">
                      {!isOwner && e.status === 'pending' && (
                        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => { setDecideOn(e); setDecisionNote(''); }} data-testid={`reim-decide-${e.id}`}>Decide</Button>
                      )}
                      {!isOwner && e.status === 'approved' && (
                        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={async () => {
                          try { await api.put(`/hr/expenses/${e.id}`, { status: 'reimbursed' }); toast.success('Marked reimbursed'); reload(); }
                          catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
                        }} data-testid={`reim-pay-${e.id}`}>Mark Paid</Button>
                      )}
                      {canEdit && <Button size="sm" variant="ghost" className="h-7" onClick={() => openEdit(e)} data-testid={`reim-edit-${e.id}`}><Pencil size={12} /></Button>}
                      {(canEdit || !isOwner) && <Button size="sm" variant="ghost" className="h-7 text-destructive" data-testid={`reim-del-${e.id}`} onClick={async () => { if (!window.confirm('Delete this expense?')) return; await api.delete(`/hr/expenses/${e.id}`); reload(); }}><Trash2 size={12} /></Button>}
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* New/Edit Dialog */}
      <Dialog open={showForm} onOpenChange={(o) => { setShowForm(o); if (!o) setEditingId(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{editingId ? 'Edit Expense' : 'New Expense'}</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label className="text-xs">Title *</Label><Input value={form.title} onChange={e => setForm({...form, title: e.target.value})} placeholder="e.g. Uber to client meeting" data-testid="reim-title-input" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Amount *</Label><Input type="number" value={form.amount} onChange={e => setForm({...form, amount: e.target.value})} step="0.01" data-testid="reim-amount-input" /></div>
              <div className="space-y-1.5"><Label className="text-xs">Currency</Label>
                <Select value={form.currency} onValueChange={v => setForm({...form, currency: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{['UGX','USD','KES','EUR','GBP','THB','HTG'].map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Category</Label>
                <Select value={form.category} onValueChange={v => setForm({...form, category: v})}>
                  <SelectTrigger data-testid="reim-category-select"><SelectValue /></SelectTrigger>
                  <SelectContent>{['travel','meals','supplies','training','fuel','accommodation','other'].map(c => <SelectItem key={c} value={c} className="capitalize">{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label className="text-xs">Date</Label><Input type="date" value={form.date} onChange={e => setForm({...form, date: e.target.value})} /></div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Receipt URL</Label><Input type="url" value={form.receipt_url} onChange={e => setForm({...form, receipt_url: e.target.value})} placeholder="https://..." /></div>
            <div className="space-y-1.5"><Label className="text-xs">Notes</Label><Textarea rows={2} value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} /></div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => { setShowForm(false); setEditingId(null); }}>Cancel</Button>
              <Button className="flex-1" onClick={submit} data-testid="reim-submit-btn">{editingId ? 'Save' : 'Submit'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Decision Dialog */}
      <Dialog open={!!decideOn} onOpenChange={(o) => { if (!o) setDecideOn(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Decide Expense</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <p className="text-xs text-muted-foreground"><strong>{decideOn?.staff_name}</strong> submitted <strong>{decideOn?.title}</strong> — {decideOn?.currency} {(decideOn?.amount || 0).toLocaleString()}.</p>
            <div className="space-y-1"><Label className="text-xs">Decision Note (optional)</Label><Textarea rows={2} value={decisionNote} onChange={e => setDecisionNote(e.target.value)} data-testid="reim-decision-note" /></div>
            <div className="flex gap-2 pt-2">
              <Button variant="destructive" className="flex-1" onClick={() => decide('rejected')} data-testid="reim-reject-btn">Reject</Button>
              <Button className="flex-1" onClick={() => decide('approved')} data-testid="reim-approve-btn">Approve</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}



// ========= Attendance Panel =========
function AttendancePanel({ currentUser, staff }) {
  const [active, setActive] = useState(null);
  const [entries, setEntries] = useState([]);
  const [summary, setSummary] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);  // for live timer
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [aRes, eRes, sRes] = await Promise.all([
        api.get('/hr/attendance/me/active').catch(() => ({ data: null })),
        api.get('/hr/attendance').catch(() => ({ data: [] })),
        api.get('/hr/attendance/summary', { params: { period } }).catch(() => ({ data: [] })),
      ]);
      setActive(aRes.data);
      setEntries(eRes.data || []);
      setSummary(sRes.data || []);
    } finally { setLoading(false); }
  }, [period]);
  useEffect(() => { reload(); }, [reload]);
  // Live timer for active entry
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setTick(x => x + 1), 1000);
    return () => clearInterval(t);
  }, [active]);

  const elapsed = active ? (() => {
    const start = new Date(active.check_in_time);
    const diff = Math.max(0, Math.floor((Date.now() - start.getTime()) / 1000));
    const h = Math.floor(diff / 3600);
    const m = Math.floor((diff % 3600) / 60);
    const s = diff % 60;
    return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  })() : null;

  const clockIn = async () => {
    try { await api.post('/hr/attendance/clock-in'); toast.success('Clocked in'); reload(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };
  const clockOut = async () => {
    try { await api.post('/hr/attendance/clock-out'); toast.success('Clocked out'); reload(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const myEntries = entries.filter(e => e.staff_id === currentUser.id);
  const otherEntries = entries.filter(e => e.staff_id !== currentUser.id).slice(0, 30);

  if (loading) return <div className="space-y-2">{[1,2,3].map(i => <div key={i} className="h-16 bg-muted animate-pulse rounded" />)}</div>;

  return (
    <div className="space-y-4" data-testid="attendance-panel">
      {/* Clock card */}
      <Card className={`rounded-xl ${active ? 'border-emerald-300 bg-emerald-50/30 dark:bg-emerald-950/20' : ''}`}>
        <CardContent className="p-5 flex items-center justify-between flex-wrap gap-3">
          <div>
            <p className="text-xs text-muted-foreground">{active ? 'Currently clocked in' : 'Not clocked in'}</p>
            <p className="text-3xl font-bold font-mono mt-0.5" data-testid="att-timer">{elapsed || '00:00:00'}</p>
            {active && <p className="text-[10px] text-muted-foreground mt-1">Since {new Date(active.check_in_time).toLocaleString()}</p>}
          </div>
          {active ? (
            <Button size="lg" variant="destructive" onClick={clockOut} data-testid="att-clock-out-btn">Clock Out</Button>
          ) : (
            <Button size="lg" className="gap-2" onClick={clockIn} data-testid="att-clock-in-btn">Clock In</Button>
          )}
        </CardContent>
      </Card>

      {/* My recent entries */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold">My Recent Entries</h3>
        {myEntries.length === 0 ? <p className="text-sm text-muted-foreground text-center py-6" data-testid="hr-attendance-empty">No entries yet — punch in above to start tracking time.</p> : (
          <div className="space-y-1.5">
            {myEntries.slice(0, 12).map(e => (
              <div key={e.id} className="flex items-center justify-between p-2 rounded border border-border text-xs" data-testid={`att-${e.id}`}>
                <div>
                  <span className="font-medium">{e.date}</span>
                  <span className="text-muted-foreground ml-2">{new Date(e.check_in_time).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})} → {e.check_out_time ? new Date(e.check_out_time).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}) : '— (active)'}</span>
                </div>
                {e.duration_minutes != null ? (
                  <Badge variant="outline" className="text-[10px]">{Math.floor(e.duration_minutes/60)}h {e.duration_minutes%60}m</Badge>
                ) : (
                  <Badge className="bg-emerald-100 text-emerald-700 text-[10px]">active</Badge>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* HR-only: team summary */}
      {staff.length > 0 && summary.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold flex-1">Team Hours</h3>
            <Input type="month" value={period} onChange={e => setPeriod(e.target.value)} className="w-40 h-7 text-xs" data-testid="att-period-input" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {summary.map(s => (
              <Card key={s.staff_id} className="rounded-xl" data-testid={`att-summary-${s.staff_id}`}>
                <CardContent className="p-3">
                  <p className="text-sm font-medium truncate">{s.staff_name}</p>
                  <p className="text-2xl font-bold">{s.total_hours}<span className="text-xs text-muted-foreground font-normal">h</span></p>
                  <p className="text-[10px] text-muted-foreground">{s.days_present} day(s) · {s.entries_count} entr{s.entries_count === 1 ? 'y' : 'ies'}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* HR-only: other team's recent entries */}
      {otherEntries.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">Team Recent Activity</h3>
          <div className="space-y-1.5">
            {otherEntries.map(e => (
              <div key={e.id} className="flex items-center justify-between p-2 rounded border border-border text-xs">
                <div>
                  <span className="font-medium">{e.staff_name}</span>
                  <span className="text-muted-foreground ml-2">{e.date} · {new Date(e.check_in_time).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})} → {e.check_out_time ? new Date(e.check_out_time).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}) : 'active'}</span>
                </div>
                {e.duration_minutes != null && <Badge variant="outline" className="text-[10px]">{Math.floor(e.duration_minutes/60)}h {e.duration_minutes%60}m</Badge>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


// ========== TIMESHEETS PANEL (HR/manager view for approvals) ==========
function TimesheetsPanel() {
  const [timesheets, setTimesheets] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [statusFilter, setStatusFilter] = React.useState('submitted');
  const [periodFilter, setPeriodFilter] = React.useState('');
  const [rejecting, setRejecting] = React.useState(null);
  const [rejectReason, setRejectReason] = React.useState('');
  // On-behalf submission (iter214) — director+/admin can log a timesheet
  // for a staff member who doesn't use the app.
  const [showLogFor, setShowLogFor] = React.useState(false);
  const [staffOptions, setStaffOptions] = React.useState([]);
  const [logForm, setLogForm] = React.useState({
    staff_id: '',
    period: new Date().toISOString().slice(0, 7),
    days_worked: '',
    pto_days: '',
    notes: '',
  });

  React.useEffect(() => {
    api.get('/admin/users/directory', { params: { limit: 500 } })
      .then(r => setStaffOptions(r.data || []))
      .catch(() => setStaffOptions([]));
  }, []);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter && statusFilter !== 'all') params.status = statusFilter;
      if (periodFilter) params.period = periodFilter;
      const r = await api.get('/hr/timesheets', { params });
      setTimesheets(r.data || []);
    } catch { setTimesheets([]); }
    finally { setLoading(false); }
  }, [statusFilter, periodFilter]);

  React.useEffect(() => { load(); }, [load]);

  const approve = async (t) => {
    try {
      await api.put(`/hr/timesheets/${t.id}/approve`, { notes: '' });
      toast.success('Approved — will roll into next payslip run');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Approve failed'); }
  };
  const submitReject = async () => {
    if (!rejecting) return;
    try {
      await api.put(`/hr/timesheets/${rejecting.id}/reject`, { reason: rejectReason });
      toast.success('Rejected — staff can revise');
      setRejecting(null); setRejectReason('');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Reject failed'); }
  };
  const submitLogFor = async () => {
    if (!logForm.staff_id) return toast.error('Pick a staff member');
    if (!logForm.days_worked) return toast.error('Days worked required');
    try {
      await api.post('/hr/timesheets', {
        staff_id: logForm.staff_id,
        period: logForm.period,
        days_worked: parseFloat(logForm.days_worked) || 0,
        pto_days: parseFloat(logForm.pto_days) || 0,
        notes: logForm.notes,
      });
      toast.success('Timesheet logged on staff\u2019s behalf — status: submitted, awaits your approval');
      setShowLogFor(false);
      setLogForm({ staff_id: '', period: new Date().toISOString().slice(0, 7), days_worked: '', pto_days: '', notes: '' });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Log failed'); }
  };

  return (
    <Card className="rounded-xl">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-xs text-muted-foreground flex-1">Staff-submitted timesheets. Approved rows auto-feed the next payslip generation.</p>
          <Button size="sm" variant="outline" className="h-8 text-xs gap-1" onClick={() => setShowLogFor(true)} data-testid="log-for-staff-btn"><Plus size={12} /> Log for staff</Button>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="h-8 w-36 text-xs" data-testid="ts-status-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="submitted">Awaiting approval</SelectItem>
              <SelectItem value="approved">Approved</SelectItem>
              <SelectItem value="rejected">Rejected</SelectItem>
            </SelectContent>
          </Select>
          <Input type="month" value={periodFilter} onChange={e => setPeriodFilter(e.target.value)} className="h-8 w-36 text-xs" data-testid="ts-period-filter" />
        </div>
        {loading ? <p className="text-xs text-muted-foreground text-center py-6">Loading…</p> : timesheets.length === 0 ? (
          <p className="text-xs text-muted-foreground text-center py-6">No timesheets found.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left border-b text-xs text-muted-foreground"><th className="pb-2">Staff</th><th>Period</th><th>Days</th><th>PTO</th><th>Status</th><th>Notes</th><th>Actions</th></tr></thead>
              <tbody className="divide-y">
                {timesheets.map(t => (
                  <tr key={t.id} className="hover:bg-accent/30" data-testid={`ts-row-${t.id}`}>
                    <td className="py-2 font-medium">{t.staff_name || t.staff_id}</td>
                    <td>{t.period}</td>
                    <td>{t.days_worked}</td>
                    <td>{t.pto_days || 0}</td>
                    <td><Badge variant={t.status === 'approved' ? 'default' : t.status === 'rejected' ? 'destructive' : 'secondary'} className="text-[10px]">{t.status}</Badge></td>
                    <td className="max-w-[240px] truncate text-xs text-muted-foreground">{t.notes || t.review_notes || '—'}</td>
                    <td className="text-right">
                      {t.status === 'submitted' && <>
                        <Button size="sm" variant="ghost" className="h-7 text-xs text-green-700" onClick={() => approve(t)} data-testid={`ts-approve-${t.id}`}>Approve</Button>
                        <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive" onClick={() => setRejecting(t)} data-testid={`ts-reject-${t.id}`}>Reject</Button>
                      </>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>

      <Dialog open={!!rejecting} onOpenChange={(o) => { if (!o) { setRejecting(null); setRejectReason(''); } }}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Reject timesheet</DialogTitle></DialogHeader>
          <Textarea rows={3} placeholder="Reason (staff will see this)" value={rejectReason} onChange={e => setRejectReason(e.target.value)} data-testid="ts-reject-reason" />
          <div className="flex gap-2 pt-2">
            <Button variant="outline" className="flex-1" onClick={() => setRejecting(null)}>Cancel</Button>
            <Button variant="destructive" className="flex-1" onClick={submitReject} data-testid="ts-reject-confirm">Reject</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* LOG-FOR-STAFF DIALOG (iter214) */}
      <Dialog open={showLogFor} onOpenChange={setShowLogFor}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Log timesheet on staff&apos;s behalf</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">Use this for staff members who don&apos;t use the app. You can only log for users within your assigned locations.</p>
            <div className="space-y-1.5"><Label className="text-xs">Staff member</Label>
              <Select value={logForm.staff_id} onValueChange={v => setLogForm({...logForm, staff_id: v})}>
                <SelectTrigger data-testid="log-for-staff-select"><SelectValue placeholder="Pick a staff member" /></SelectTrigger>
                <SelectContent className="max-h-64">
                  {staffOptions.map(s => (<SelectItem key={s.id} value={s.id}>{s.name} — {s.role || 'staff'}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Pay Period</Label>
              <Input type="month" value={logForm.period} onChange={e => setLogForm({...logForm, period: e.target.value})} data-testid="log-for-period" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5"><Label className="text-xs">Days worked</Label>
                <Input type="number" value={logForm.days_worked} onChange={e => setLogForm({...logForm, days_worked: e.target.value})} data-testid="log-for-days" />
              </div>
              <div className="space-y-1.5"><Label className="text-xs">PTO days</Label>
                <Input type="number" value={logForm.pto_days} onChange={e => setLogForm({...logForm, pto_days: e.target.value})} data-testid="log-for-pto" />
              </div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Notes</Label>
              <Textarea rows={2} value={logForm.notes} onChange={e => setLogForm({...logForm, notes: e.target.value})} placeholder="e.g. Full month, worked from field" />
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowLogFor(false)}>Cancel</Button>
              <Button className="flex-1" onClick={submitLogFor} data-testid="log-for-submit-btn">Log &amp; submit</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}




// ========== TIME OFF (PTO) PANEL ==========
function TimeOffPanel() {
  const [requests, setRequests] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [statusFilter, setStatusFilter] = React.useState('pending');
  const [rejecting, setRejecting] = React.useState(null);
  const [rejectReason, setRejectReason] = React.useState('');

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter && statusFilter !== 'all') params.status = statusFilter;
      const r = await api.get('/hr/time-off', { params });
      setRequests(r.data || []);
    } catch { setRequests([]); }
    finally { setLoading(false); }
  }, [statusFilter]);

  React.useEffect(() => { load(); }, [load]);

  const approve = async (p) => {
    try {
      await api.put(`/hr/time-off/${p.id}/approve`, { notes: '' });
      toast.success('Approved');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Approve failed'); }
  };
  const submitReject = async () => {
    if (!rejecting) return;
    try {
      await api.put(`/hr/time-off/${rejecting.id}/reject`, { reason: rejectReason });
      toast.success('Rejected');
      setRejecting(null); setRejectReason('');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Reject failed'); }
  };

  return (
    <Card className="rounded-xl">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-xs text-muted-foreground flex-1">Staff time-off (PTO) requests. Requests must be within ±7 days of the requested date, except when marked as admin override.</p>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="h-8 w-36 text-xs" data-testid="pto-status-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="pending">Pending approval</SelectItem>
              <SelectItem value="approved">Approved</SelectItem>
              <SelectItem value="rejected">Rejected</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {loading ? <p className="text-xs text-muted-foreground text-center py-6">Loading…</p> : requests.length === 0 ? (
          <p className="text-xs text-muted-foreground text-center py-6">No time-off requests found.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left border-b text-xs text-muted-foreground"><th className="pb-2">Staff</th><th>Dates</th><th>Days</th><th>Reason</th><th>Status</th><th>Notes</th><th></th></tr></thead>
              <tbody className="divide-y">
                {requests.map(p => (
                  <tr key={p.id} className="hover:bg-accent/30" data-testid={`pto-row-${p.id}`}>
                    <td className="py-2 font-medium">{p.staff_name || p.staff_id}</td>
                    <td className="text-xs">{p.start_date}{p.end_date && p.end_date !== p.start_date ? ` → ${p.end_date}` : ''}{p.admin_override && <Badge variant="outline" className="ml-1 text-[9px] border-amber-400 text-amber-600">override</Badge>}</td>
                    <td>{p.days || 1}</td>
                    <td className="max-w-[240px] truncate text-xs text-muted-foreground">{p.reason || '—'}</td>
                    <td><Badge variant={p.status === 'approved' ? 'default' : p.status === 'rejected' ? 'destructive' : 'secondary'} className="text-[10px]">{p.status}</Badge></td>
                    <td className="max-w-[200px] truncate text-xs text-muted-foreground">{p.review_notes || '—'}</td>
                    <td className="text-right">
                      {p.status === 'pending' && <>
                        <Button size="sm" variant="ghost" className="h-7 text-xs text-green-700" onClick={() => approve(p)} data-testid={`pto-approve-${p.id}`}>Approve</Button>
                        <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive" onClick={() => setRejecting(p)} data-testid={`pto-reject-${p.id}`}>Reject</Button>
                      </>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
      <Dialog open={!!rejecting} onOpenChange={o => { if (!o) { setRejecting(null); setRejectReason(''); } }}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Reject time-off request</DialogTitle></DialogHeader>
          <Textarea rows={3} placeholder="Reason (staff will see this)" value={rejectReason} onChange={e => setRejectReason(e.target.value)} data-testid="pto-reject-reason" />
          <div className="flex gap-2 pt-2">
            <Button variant="outline" className="flex-1" onClick={() => setRejecting(null)}>Cancel</Button>
            <Button variant="destructive" className="flex-1" onClick={submitReject} data-testid="pto-reject-confirm">Reject</Button>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}


// ========== ONBOARDING CHECKLIST PANEL ==========
function OnboardingPanel({ onFix }) {
  const [data, setData] = React.useState({ total: 0, fully_onboarded: 0, needs_attention: 0, rows: [] });
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get('/hr/onboarding/checklist');
      setData(r.data || { rows: [] });
    } catch { setData({ rows: [] }); }
    finally { setLoading(false); }
  }, []);

  React.useEffect(() => { load(); }, [load]);

  const cell = (ok, staff, key, label) => {
    if (ok) return <td className="text-center"><CheckCircle2 size={14} className="inline text-green-600" /></td>;
    return (
      <td className="text-center">
        <button
          className="inline-flex items-center gap-1 text-red-500 hover:text-red-700 hover:underline cursor-pointer group"
          onClick={() => onFix && onFix(key, staff)}
          data-testid={`onb-fix-${staff.staff_id}-${key}`}
          title={`Fix: ${label}`}
        >
          <XCircle size={14} />
          <span className="text-[10px] opacity-0 group-hover:opacity-100 transition-opacity">Fix</span>
        </button>
      </td>
    );
  };

  return (
    <Card className="rounded-xl">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center gap-4 flex-wrap">
          <div>
            <p className="text-sm font-semibold">Staff onboarding status</p>
            <p className="text-xs text-muted-foreground">Every new hire needs contract → salary → cash account access before payslips can flow properly.</p>
          </div>
          <div className="flex items-center gap-4 ml-auto text-xs">
            <div><span className="text-muted-foreground">Fully onboarded:</span> <span className="font-semibold text-green-700" data-testid="onboarding-fully">{data.fully_onboarded}</span></div>
            <div><span className="text-muted-foreground">Needs attention:</span> <span className="font-semibold text-amber-700" data-testid="onboarding-needs">{data.needs_attention}</span></div>
            <div><span className="text-muted-foreground">Total:</span> <span className="font-semibold" data-testid="onboarding-total">{data.total}</span></div>
            <Button size="sm" variant="ghost" className="h-7" onClick={load}><RefreshCw size={12} /></Button>
          </div>
        </div>

        {loading ? <p className="text-xs text-muted-foreground text-center py-6">Loading…</p> : data.rows.length === 0 ? (
          <p className="text-xs text-muted-foreground text-center py-6">No staff found.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left border-b text-xs text-muted-foreground">
                <th className="pb-2">Staff</th>
                <th>Role · Dept</th>
                <th className="text-center">Dept</th>
                <th className="text-center">Location</th>
                <th className="text-center">Contract</th>
                <th className="text-center">Salary</th>
                <th className="text-center">Cash Acct</th>
                <th>Salary</th>
                <th className="text-right">%</th>
              </tr></thead>
              <tbody className="divide-y">
                {data.rows.map(r => (
                  <tr key={r.staff_id} className={`hover:bg-accent/30 ${r.completion_pct === 100 ? '' : 'bg-amber-50/40 dark:bg-amber-950/10'}`} data-testid={`onboarding-row-${r.staff_id}`}>
                    <td className="py-2 font-medium">{r.staff_name || '(unnamed)'}<div className="text-[10px] text-muted-foreground">{r.email}</div></td>
                    <td className="text-xs text-muted-foreground">{r.role || '—'}{r.department ? ` · ${r.department}` : ''}</td>
                    {cell(r.checks.has_department, r, 'has_department', 'Set department')}
                    {cell(r.checks.has_location, r, 'has_location', 'Set location')}
                    {cell(r.checks.has_contract, r, 'has_contract', 'Issue contract')}
                    {cell(r.checks.has_salary, r, 'has_salary', 'Add salary')}
                    {cell(r.checks.has_chart_account, r, 'has_chart_account', 'Assign cash account')}
                    <td className="text-[11px] text-muted-foreground">{r.salary_summary || '—'}</td>
                    <td className="text-right">
                      <Badge className={`text-[10px] ${r.completion_pct === 100 ? '' : 'bg-amber-100 text-amber-800 dark:bg-amber-900/40'}`} data-testid={`onb-pct-${r.staff_id}`}>{r.completion_pct}%</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

