import React, { useState, useEffect, useCallback } from 'react';
import { Users, DollarSign, FileText, Clock, Plus, Trash2, Send, CheckCircle, Download, RefreshCw, Settings } from 'lucide-react';
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
      const res = await api.post('/hr/salaries', { ...salaryForm, base_salary: parseFloat(salaryForm.base_salary), location_id: activeCampus });
      setSalaries(prev => [res.data, ...prev]);
      setShowSalary(false);
      setSalaryForm({ staff_id: '', base_salary: '', currency: 'UGX', pay_frequency: 'monthly', line_items: [] });
      toast.success('Salary record created');
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
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
                    <Button size="sm" variant="ghost" className="text-destructive h-7" onClick={async () => { if (!window.confirm('Delete salary record?')) return; await api.delete(`/hr/salaries/${s.id}`); setSalaries(prev => prev.filter(x => x.id !== s.id)); toast.success('Deleted'); }}><Trash2 size={13} /></Button>
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
      </Tabs>

      {/* Add Salary Dialog */}
      <Dialog open={showSalary} onOpenChange={setShowSalary}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Add Salary Record</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label>Staff Member *</Label>
              <Select value={salaryForm.staff_id} onValueChange={v => setSalaryForm({...salaryForm, staff_id: v})}>
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
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowSalary(false)}>Cancel</Button>
              <Button className="flex-1" onClick={handleCreateSalary} disabled={saving || !salaryForm.staff_id || !salaryForm.base_salary}>{saving ? 'Saving...' : 'Create'}</Button>
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
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>HR Settings</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="flex items-center justify-between">
              <div><p className="text-sm font-medium">HR Module Enabled</p><p className="text-xs text-muted-foreground">Enable HR features for this campus</p></div>
              <Switch checked={settingsForm.hr_enabled} onCheckedChange={v => setSettingsForm({...settingsForm, hr_enabled: v})} data-testid="hr-enabled-toggle" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Pay Frequency</Label>
                <Select value={settingsForm.pay_frequency} onValueChange={v => setSettingsForm({...settingsForm, pay_frequency: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="weekly">Weekly</SelectItem><SelectItem value="biweekly">Bi-weekly</SelectItem><SelectItem value="monthly">Monthly</SelectItem></SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label>Pay Day</Label><Input type="number" min={1} max={31} value={settingsForm.pay_day} onChange={e => setSettingsForm({...settingsForm, pay_day: parseInt(e.target.value) || 28})} /></div>
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowSettings(false)}>Cancel</Button>
              <Button className="flex-1" onClick={handleSaveSettings}>Save Settings</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
