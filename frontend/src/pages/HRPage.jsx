import React, { useState, useEffect, useCallback } from 'react';
import { Users, DollarSign, FileText, Clock, Plus, Trash2, Send, CheckCircle, Download, RefreshCw, Settings, Pencil, History } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Switch } from '../components/ui/switch';
import api from '../services/api';
import { adminApi, locationsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

export default function HRPage() {
  const { user } = useAuth();
  const activeCampus = localStorage.getItem('5812_active_campus') || user?.location_id || '';
  const [salaries, setSalaries] = useState([]);
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
  const [showPayslipGen, setShowPayslipGen] = useState(false);
  const [showDocReq, setShowDocReq] = useState(false);
  const [showIssueContract, setShowIssueContract] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [salaryForm, setSalaryForm] = useState({ staff_id: '', base_salary: '', currency: 'UGX', pay_frequency: 'monthly', line_items: [] });
  const [editingSalaryId, setEditingSalaryId] = useState(null);
  const [editReason, setEditReason] = useState('');
  const [historySalary, setHistorySalary] = useState(null);
  const [historyEntries, setHistoryEntries] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [templateForm, setTemplateForm] = useState({ name: '', content: '' });
  const [payPeriod, setPayPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [docReqForm, setDocReqForm] = useState({ staff_id: '', doc_types: ['resume', 'id_document'], message: '' });
  const [issueForm, setIssueForm] = useState({ template_id: '', staff_id: '', start_date: '', salary: '' });
  const [settingsForm, setSettingsForm] = useState({ hr_enabled: false, pay_frequency: 'monthly', currency: 'UGX', pay_day: 28 });
  const [lineItem, setLineItem] = useState({ name: '', type: 'allowance', amount: '', is_percentage: false });
  const [saving, setSaving] = useState(false);

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
      if (editingSalaryId) {
        const res = await api.put(`/hr/salaries/${editingSalaryId}`, {
          base_salary: parseFloat(salaryForm.base_salary),
          currency: salaryForm.currency,
          pay_frequency: salaryForm.pay_frequency,
          line_items: salaryForm.line_items,
          reason: editReason,
        });
        setSalaries(prev => prev.map(x => x.id === editingSalaryId ? res.data : x));
        toast.success('Salary updated');
      } else {
        const res = await api.post('/hr/salaries', { ...salaryForm, base_salary: parseFloat(salaryForm.base_salary), location_id: activeCampus });
        setSalaries(prev => [res.data, ...prev]);
        toast.success('Salary record created');
      }
      setShowSalary(false);
      setEditingSalaryId(null);
      setEditReason('');
      setSalaryForm({ staff_id: '', base_salary: '', currency: 'UGX', pay_frequency: 'monthly', line_items: [] });
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
  };

  const openEditSalary = (s) => {
    setEditingSalaryId(s.id);
    setEditReason('');
    setSalaryForm({
      staff_id: s.staff_id || '',
      base_salary: String(s.base_salary || ''),
      currency: s.currency || 'UGX',
      pay_frequency: s.pay_frequency || 'monthly',
      line_items: s.line_items || [],
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
    setSaving(true);
    try {
      const res = await api.post('/hr/payslips/generate', { period: payPeriod, location_id: activeCampus });
      setPayslips(prev => [...res.data.payslips, ...prev]);
      setShowPayslipGen(false);
      toast.success(`Generated ${res.data.generated} payslips`);
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
  };

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

      <Tabs defaultValue="salaries">
        <TabsList className="flex-wrap">
          <TabsTrigger value="salaries"><DollarSign size={13} className="mr-1" /> Salaries</TabsTrigger>
          <TabsTrigger value="payslips"><FileText size={13} className="mr-1" /> Payslips</TabsTrigger>
          <TabsTrigger value="contracts"><FileText size={13} className="mr-1" /> Contracts</TabsTrigger>
          <TabsTrigger value="documents"><Users size={13} className="mr-1" /> Documents</TabsTrigger>
          <TabsTrigger value="leave"><Clock size={13} className="mr-1" /> Leave</TabsTrigger>
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
          <div className="flex justify-end gap-2 mb-3">
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
            <Button size="sm" className="gap-1.5" onClick={() => setShowPayslipGen(true)} data-testid="generate-payslips-btn"><Plus size={14} /> Generate Payslips</Button>
          </div>
          {payslips.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">No payslips generated yet.</p> : (
            <div className="space-y-2">
              {payslips.map(p => (
                <Card key={p.id} className="rounded-xl">
                  <CardContent className="p-4 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">{p.staff_name}</p>
                      <p className="text-xs text-muted-foreground">Period: {p.period} · {p.department}</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="text-right">
                        <p className="text-sm font-bold text-green-600">{p.currency} {(p.net_salary || 0).toLocaleString()}</p>
                        <p className="text-[10px] text-muted-foreground">Gross: {(p.gross_salary || 0).toLocaleString()}</p>
                      </div>
                      <Badge variant={p.status === 'approved' ? 'outline' : 'secondary'} className={`text-xs ${p.status === 'approved' ? 'border-green-400 text-green-600' : ''}`}>{p.status}</Badge>
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
              <div className="space-y-1.5"><Label>Base Salary *</Label><Input type="number" value={salaryForm.base_salary} onChange={e => setSalaryForm({...salaryForm, base_salary: e.target.value})} /></div>
              <div className="space-y-1.5"><Label>Currency</Label>
                <Select value={salaryForm.currency} onValueChange={v => setSalaryForm({...salaryForm, currency: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{['UGX','USD','KES','GBP','EUR','THB','HTG'].map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5"><Label>Pay Frequency</Label>
              <Select value={salaryForm.pay_frequency} onValueChange={v => setSalaryForm({...salaryForm, pay_frequency: v})}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="weekly">Weekly</SelectItem><SelectItem value="biweekly">Bi-weekly</SelectItem><SelectItem value="monthly">Monthly</SelectItem></SelectContent>
              </Select>
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

      {/* Generate Payslips Dialog */}
      <Dialog open={showPayslipGen} onOpenChange={setShowPayslipGen}>
        <DialogContent className="max-w-xs">
          <DialogHeader><DialogTitle>Generate Payslips</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label>Pay Period *</Label><Input type="month" value={payPeriod} onChange={e => setPayPeriod(e.target.value)} data-testid="pay-period-input" /></div>
            <p className="text-xs text-muted-foreground">{salaries.length} active salary records will be processed.</p>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => setShowPayslipGen(false)}>Cancel</Button>
              <Button className="flex-1" onClick={handleGeneratePayslips} disabled={saving}>{saving ? 'Generating...' : 'Generate'}</Button>
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
                <Select value={settingsForm.pay_frequency} onValueChange={v => setSettingsForm({...settingsForm, pay_frequency: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="weekly">Weekly</SelectItem><SelectItem value="biweekly">Bi-weekly</SelectItem><SelectItem value="monthly">Monthly</SelectItem></SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label>Pay Day (1-31)</Label><Input type="number" min={1} max={31} value={settingsForm.pay_day} onChange={e => setSettingsForm({...settingsForm, pay_day: parseInt(e.target.value) || 28})} /></div>
              <div className="space-y-1.5"><Label>Next Pay Date</Label><Input type="date" value={settingsForm.next_pay_date || ''} onChange={e => setSettingsForm({...settingsForm, next_pay_date: e.target.value})} data-testid="next-pay-date" /></div>
            </div>

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

