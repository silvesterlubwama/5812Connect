/**
 * BankPage — QuickBooks-style banking module.
 * Tabs: Accounts / Statements / Vendors / Bills / Recurring / Rules
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Textarea } from '../components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Landmark, Plus, RefreshCw, Upload, FileText, Users, Repeat, Filter, CheckCircle2, X, Trash2, Receipt } from 'lucide-react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

const STATUS_COLORS = {
  unreconciled: 'bg-amber-100 text-amber-700',
  matched: 'bg-green-100 text-green-700',
  ignored: 'bg-gray-100 text-gray-600',
  open: 'bg-amber-100 text-amber-700',
  paid: 'bg-green-100 text-green-700',
  partially_paid: 'bg-blue-100 text-blue-700',
  void: 'bg-gray-100 text-gray-600',
};

export default function BankPage() {
  const { user } = useAuth();
  const [accounts, setAccounts] = useState([]);
  const [coaAccounts, setCoaAccounts] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [bills, setBills] = useState([]);
  const [recurring, setRecurring] = useState([]);
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedBankId, setSelectedBankId] = useState('');
  const [transactions, setTransactions] = useState([]);
  const [txFilter, setTxFilter] = useState('unreconciled');

  // Dialog states
  const [showAcctForm, setShowAcctForm] = useState(false);
  const [acctForm, setAcctForm] = useState({ name: '', bank_name: '', account_number: '', account_type: 'checking', currency: 'UGX', country: 'UG', branch: '', opening_balance: '0', linked_account_id: '' });
  const [showVendorForm, setShowVendorForm] = useState(false);
  const [vendorForm, setVendorForm] = useState({ name: '', tin: '', vat_registered: false, email: '', phone: '', payment_terms_days: 30, currency: 'UGX', country: 'UG' });
  const [showRuleForm, setShowRuleForm] = useState(false);
  const [ruleForm, setRuleForm] = useState({ name: '', match_pattern: '', target_account_id: '', priority: 100 });
  const [reconcileTx, setReconcileTx] = useState(null);  // tx being reconciled
  const [reconcileAccount, setReconcileAccount] = useState('');
  const fileInputRef = useRef(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [aR, cR, vR, bR, rR, ruR] = await Promise.all([
        api.get('/bank/accounts').catch(() => ({ data: [] })),
        api.get('/accounting/accounts', { params: { location_id: user?.active_campus_id } }).catch(() => ({ data: [] })),
        api.get('/bank/vendors').catch(() => ({ data: [] })),
        api.get('/bank/bills').catch(() => ({ data: [] })),
        api.get('/bank/recurring').catch(() => ({ data: [] })),
        api.get('/bank/rules').catch(() => ({ data: [] })),
      ]);
      setAccounts(aR.data || []);
      setCoaAccounts(cR.data || []);
      setVendors(vR.data || []);
      setBills(bR.data || []);
      setRecurring(rR.data || []);
      setRules(ruR.data || []);
      if ((aR.data || []).length && !selectedBankId) setSelectedBankId(aR.data[0].id);
    } catch (e) {
      if (e.response?.status === 403) {
        toast.error('You don\'t have finance access. Ask an admin to grant it.');
      }
    } finally { setLoading(false); }
  }, [user?.active_campus_id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { reload(); }, [reload]);

  const reloadTransactions = useCallback(async () => {
    if (!selectedBankId) { setTransactions([]); return; }
    try {
      const params = { bank_account_id: selectedBankId };
      if (txFilter !== 'all') params.status = txFilter;
      const r = await api.get('/bank/transactions', { params });
      setTransactions(r.data || []);
    } catch { /* ignore */ }
  }, [selectedBankId, txFilter]);
  useEffect(() => { reloadTransactions(); }, [reloadTransactions]);

  const fmt = (n, c) => `${c || 'UGX'} ${(Number(n) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const createAccount = async () => {
    try {
      await api.post('/bank/accounts', { ...acctForm, opening_balance: parseFloat(acctForm.opening_balance) || 0, location_id: user?.active_campus_id });
      toast.success('Bank account created');
      setShowAcctForm(false);
      setAcctForm({ name: '', bank_name: '', account_number: '', account_type: 'checking', currency: 'UGX', country: 'UG', branch: '', opening_balance: '0', linked_account_id: '' });
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const createVendor = async () => {
    try {
      await api.post('/bank/vendors', { ...vendorForm });
      toast.success('Vendor created');
      setShowVendorForm(false);
      setVendorForm({ name: '', tin: '', vat_registered: false, email: '', phone: '', payment_terms_days: 30, currency: 'UGX', country: 'UG' });
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const createRule = async () => {
    try {
      await api.post('/bank/rules', { ...ruleForm });
      toast.success('Rule created');
      setShowRuleForm(false);
      setRuleForm({ name: '', match_pattern: '', target_account_id: '', priority: 100 });
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const importCsv = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !selectedBankId) return;
    const fd = new FormData();
    fd.append('file', file);
    try {
      const r = await api.post(`/bank/accounts/${selectedBankId}/import-csv`, fd);
      toast.success(`Imported ${r.data.transaction_count} txs · ${r.data.auto_suggested_count} auto-suggested`);
      reloadTransactions();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Import failed');
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const applySuggestions = async () => {
    if (!selectedBankId) return;
    try {
      const r = await api.post('/bank/transactions/bulk-apply-suggestions', { bank_account_id: selectedBankId });
      toast.success(`Reconciled ${r.data.posted} (skipped ${r.data.skipped})`);
      reloadTransactions();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const submitReconcile = async (mode) => {
    if (!reconcileTx) return;
    const body = mode === 'ignore' ? { action: 'ignore' } : { target_account_id: reconcileAccount };
    try {
      await api.post(`/bank/transactions/${reconcileTx.id}/reconcile`, body);
      toast.success('Reconciled');
      setReconcileTx(null); setReconcileAccount('');
      reloadTransactions();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  if (loading) {
    return <div className="p-6 space-y-2">{[1,2,3].map(i => <div key={i} className="h-20 bg-muted animate-pulse rounded-xl" />)}</div>;
  }

  const cashAccs = coaAccounts.filter(a => a.type?.startsWith('asset_'));
  const selectedAcct = accounts.find(a => a.id === selectedBankId);

  return (
    <div className="p-6 space-y-5" data-testid="bank-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold font-heading flex items-center gap-2">
            <Landmark size={22} className="text-primary" /> Banking
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">Bank accounts · Statement import & reconciliation · Vendors · Bills · Recurring</p>
        </div>
        <Button size="sm" variant="outline" onClick={reload} data-testid="bank-refresh-btn"><RefreshCw size={14} className="mr-1" />Refresh</Button>
      </div>

      <Tabs defaultValue="accounts" className="space-y-3">
        <TabsList>
          <TabsTrigger value="accounts" data-testid="bank-tab-accounts"><Landmark size={13} className="mr-1" />Accounts</TabsTrigger>
          <TabsTrigger value="transactions" data-testid="bank-tab-transactions"><FileText size={13} className="mr-1" />Statements & Reconcile</TabsTrigger>
          <TabsTrigger value="vendors" data-testid="bank-tab-vendors"><Users size={13} className="mr-1" />Vendors ({vendors.length})</TabsTrigger>
          <TabsTrigger value="bills" data-testid="bank-tab-bills"><Receipt size={13} className="mr-1" />Bills ({bills.length})</TabsTrigger>
          <TabsTrigger value="recurring" data-testid="bank-tab-recurring"><Repeat size={13} className="mr-1" />Recurring ({recurring.length})</TabsTrigger>
          <TabsTrigger value="rules" data-testid="bank-tab-rules"><Filter size={13} className="mr-1" />Rules ({rules.length})</TabsTrigger>
        </TabsList>

        {/* ACCOUNTS */}
        <TabsContent value="accounts" className="space-y-3">
          <div className="flex justify-end">
            <Button size="sm" onClick={() => setShowAcctForm(true)} data-testid="bank-new-account-btn"><Plus size={14} className="mr-1" />New Account</Button>
          </div>
          {accounts.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">No bank accounts yet.</p> : (
            <div className="space-y-2">
              {accounts.map(a => (
                <Card key={a.id} className="rounded-xl" data-testid={`bank-account-${a.id}`}>
                  <CardContent className="p-3 flex items-center justify-between flex-wrap gap-2">
                    <div>
                      <p className="font-medium">{a.name}</p>
                      <p className="text-xs text-muted-foreground">{a.bank_name} · {a.branch || '—'} · {a.account_number || '—'}</p>
                      <div className="flex items-center gap-1 mt-1">
                        <Badge variant="outline" className="text-[10px]">{a.account_type}</Badge>
                        <Badge variant="outline" className="text-[10px]">{a.country}</Badge>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-muted-foreground uppercase">Balance</p>
                      <p className="text-lg font-bold">{fmt(a.current_balance, a.currency)}</p>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* TRANSACTIONS / RECONCILIATION */}
        <TabsContent value="transactions" className="space-y-3">
          <Card className="rounded-xl">
            <CardContent className="p-3 space-y-2">
              <div className="flex flex-wrap items-end gap-2">
                <div className="flex-1 min-w-[200px]">
                  <Label className="text-xs">Bank account</Label>
                  <Select value={selectedBankId} onValueChange={setSelectedBankId}>
                    <SelectTrigger className="h-9" data-testid="bank-tx-acct-picker"><SelectValue placeholder="Pick..." /></SelectTrigger>
                    <SelectContent>{accounts.map(a => <SelectItem key={a.id} value={a.id}>{a.name} ({a.currency})</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="min-w-[120px]">
                  <Label className="text-xs">Status</Label>
                  <Select value={txFilter} onValueChange={setTxFilter}>
                    <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All</SelectItem>
                      <SelectItem value="unreconciled">Unreconciled</SelectItem>
                      <SelectItem value="matched">Matched</SelectItem>
                      <SelectItem value="ignored">Ignored</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <input ref={fileInputRef} type="file" accept=".csv,text/csv" onChange={importCsv} className="hidden" data-testid="bank-csv-input" />
                <Button size="sm" variant="outline" onClick={() => fileInputRef.current?.click()} disabled={!selectedBankId} data-testid="bank-import-csv-btn">
                  <Upload size={14} className="mr-1" />Import CSV
                </Button>
                <Button size="sm" onClick={applySuggestions} disabled={!selectedBankId} data-testid="bank-apply-suggestions-btn">
                  <CheckCircle2 size={14} className="mr-1" />Auto-apply suggestions
                </Button>
              </div>
              {selectedAcct && <p className="text-xs text-muted-foreground pt-1">Current balance: <strong>{fmt(selectedAcct.current_balance, selectedAcct.currency)}</strong></p>}
            </CardContent>
          </Card>

          {!selectedBankId ? <p className="text-sm text-muted-foreground text-center py-12">Pick a bank account to view transactions.</p> :
          transactions.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">No transactions to show.</p> :
          (
            <div className="space-y-1.5">
              {transactions.map(t => (
                <Card key={t.id} className="rounded-xl" data-testid={`bank-tx-${t.id}`}>
                  <CardContent className="p-2.5 flex items-center justify-between flex-wrap gap-2 text-sm">
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">{t.description}</p>
                      <p className="text-[11px] text-muted-foreground">{t.date} {t.reference ? `· ${t.reference}` : ''}</p>
                    </div>
                    <div className="text-right">
                      <p className={`text-sm font-bold ${t.amount > 0 ? 'text-green-700' : 'text-red-700'}`}>{t.amount > 0 ? '+' : ''}{t.amount.toFixed(2)}</p>
                      {t.balance != null && <p className="text-[10px] text-muted-foreground">bal {t.balance.toLocaleString()}</p>}
                    </div>
                    <Badge className={`text-[10px] ${STATUS_COLORS[t.status] || ''} capitalize`}>{t.status}</Badge>
                    {t.status === 'unreconciled' && (
                      <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => { setReconcileTx(t); setReconcileAccount(t.suggested_account_id || ''); }} data-testid={`bank-reconcile-btn-${t.id}`}>
                        Reconcile
                      </Button>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* VENDORS */}
        <TabsContent value="vendors" className="space-y-3">
          <div className="flex justify-end">
            <Button size="sm" onClick={() => setShowVendorForm(true)} data-testid="bank-new-vendor-btn"><Plus size={14} className="mr-1" />New Vendor</Button>
          </div>
          {vendors.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">No vendors yet.</p> : (
            <div className="space-y-2">
              {vendors.map(v => (
                <Card key={v.id} className="rounded-xl" data-testid={`bank-vendor-${v.id}`}>
                  <CardContent className="p-3 flex items-center justify-between">
                    <div>
                      <p className="font-medium">{v.name}</p>
                      <p className="text-xs text-muted-foreground">TIN: {v.tin || '—'} · {v.payment_terms_days}-day terms · {v.country}{v.vat_registered ? ' · VAT-reg' : ''}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-muted-foreground">Outstanding</p>
                      <p className="font-bold text-amber-700">{fmt(v.outstanding_balance, v.currency)}</p>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* BILLS */}
        <TabsContent value="bills" className="space-y-3">
          {bills.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">No bills yet. Bills can be created via API or the Vendors workflow.</p> : (
            <div className="space-y-2">
              {bills.map(b => (
                <Card key={b.id} className="rounded-xl" data-testid={`bank-bill-${b.id}`}>
                  <CardContent className="p-3 flex items-center justify-between flex-wrap gap-2">
                    <div>
                      <p className="font-medium font-mono">{b.bill_number}</p>
                      <p className="text-xs text-muted-foreground">{b.vendor_name} · {b.bill_date} · due {b.due_date}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <p className="font-bold">{fmt(b.balance, b.currency)} <span className="text-xs text-muted-foreground font-normal">of {fmt(b.total, b.currency)}</span></p>
                      <Badge className={`text-[10px] ${STATUS_COLORS[b.status] || ''} capitalize`}>{b.status?.replace('_', ' ')}</Badge>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* RECURRING */}
        <TabsContent value="recurring" className="space-y-3">
          {recurring.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">No recurring entries scheduled.</p> : (
            <div className="space-y-2">
              {recurring.map(r => (
                <Card key={r.id} className="rounded-xl" data-testid={`bank-recurring-${r.id}`}>
                  <CardContent className="p-3 flex items-center justify-between">
                    <div>
                      <p className="font-medium">{r.name}</p>
                      <p className="text-xs text-muted-foreground">{r.kind} · {r.schedule} · next: {r.next_run_date} · last: {r.last_run_date || 'never'} · {r.run_count || 0} runs</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant={r.is_active ? 'default' : 'secondary'} className="text-[10px]">{r.is_active ? 'active' : 'paused'}</Badge>
                      <Button size="sm" variant="outline" className="h-7 text-xs" onClick={async () => {
                        try { await api.post(`/bank/recurring/${r.id}/run-now`); toast.success('Ran successfully'); reload(); }
                        catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
                      }} data-testid={`bank-recurring-run-${r.id}`}>Run now</Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* RULES */}
        <TabsContent value="rules" className="space-y-3">
          <div className="flex justify-end">
            <Button size="sm" onClick={() => setShowRuleForm(true)} data-testid="bank-new-rule-btn"><Plus size={14} className="mr-1" />New Rule</Button>
          </div>
          {rules.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">No categorization rules yet. Add a rule like "AIRTIME.*MTN" → Communication expense to auto-categorise imports.</p> : (
            <div className="space-y-2">
              {rules.map(r => (
                <Card key={r.id} className="rounded-xl" data-testid={`bank-rule-${r.id}`}>
                  <CardContent className="p-3 flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <p className="font-medium">{r.name}</p>
                      <p className="text-xs text-muted-foreground"><code>{r.match_pattern}</code> → <strong>{(coaAccounts.find(a => a.id === r.target_account_id) || {}).name || r.target_account_id}</strong></p>
                    </div>
                    <Badge variant={r.is_active ? 'default' : 'secondary'} className="text-[10px]">priority {r.priority}</Badge>
                    <Button size="sm" variant="ghost" className="h-7 text-destructive" onClick={async () => {
                      if (!window.confirm('Delete this rule?')) return;
                      try { await api.delete(`/bank/rules/${r.id}`); reload(); }
                      catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
                    }} data-testid={`bank-rule-del-${r.id}`}><Trash2 size={12} /></Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* NEW ACCOUNT DIALOG */}
      <Dialog open={showAcctForm} onOpenChange={setShowAcctForm}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New Bank Account</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label className="text-xs">Display name *</Label><Input value={acctForm.name} onChange={e => setAcctForm({...acctForm, name: e.target.value})} placeholder="Stanbic Operations" data-testid="bank-form-name" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Bank</Label><Input value={acctForm.bank_name} onChange={e => setAcctForm({...acctForm, bank_name: e.target.value})} placeholder="Stanbic Bank Uganda" /></div>
              <div className="space-y-1.5"><Label className="text-xs">Account number</Label><Input value={acctForm.account_number} onChange={e => setAcctForm({...acctForm, account_number: e.target.value})} /></div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Type</Label>
                <Select value={acctForm.account_type} onValueChange={v => setAcctForm({...acctForm, account_type: v})}>
                  <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>{['checking','savings','mobile_money','fixed_deposit','credit_card'].map(t => <SelectItem key={t} value={t}>{t.replace('_', ' ')}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label className="text-xs">Currency</Label>
                <Select value={acctForm.currency} onValueChange={v => setAcctForm({...acctForm, currency: v})}>
                  <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>{['UGX','USD','KES','EUR','GBP','HTG','THB'].map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label className="text-xs">Country</Label>
                <Select value={acctForm.country} onValueChange={v => setAcctForm({...acctForm, country: v})}>
                  <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>{['UG','US','KE','HT','TH','GB','EU'].map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Branch</Label><Input value={acctForm.branch} onChange={e => setAcctForm({...acctForm, branch: e.target.value})} /></div>
              <div className="space-y-1.5"><Label className="text-xs">Opening balance</Label><Input type="number" step="0.01" value={acctForm.opening_balance} onChange={e => setAcctForm({...acctForm, opening_balance: e.target.value})} /></div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Link to CoA cash account *</Label>
              <Select value={acctForm.linked_account_id} onValueChange={v => setAcctForm({...acctForm, linked_account_id: v})}>
                <SelectTrigger className="h-9" data-testid="bank-form-coa-link"><SelectValue placeholder="Pick CoA account..." /></SelectTrigger>
                <SelectContent>{cashAccs.map(a => <SelectItem key={a.id} value={a.id}>{a.code} {a.name}</SelectItem>)}</SelectContent>
              </Select>
              <p className="text-[10px] text-muted-foreground">Every transaction posted will hit this account in the ledger.</p>
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowAcctForm(false)}>Cancel</Button>
              <Button className="flex-1" onClick={createAccount} disabled={!acctForm.name || !acctForm.linked_account_id} data-testid="bank-form-submit">Create</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* NEW VENDOR DIALOG */}
      <Dialog open={showVendorForm} onOpenChange={setShowVendorForm}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New Vendor</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label className="text-xs">Name *</Label><Input value={vendorForm.name} onChange={e => setVendorForm({...vendorForm, name: e.target.value})} placeholder="Bulunzi Bugagga Farm Supply" data-testid="vendor-form-name" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">TIN</Label><Input value={vendorForm.tin} onChange={e => setVendorForm({...vendorForm, tin: e.target.value})} placeholder="1234567890" /></div>
              <div className="space-y-1.5"><Label className="text-xs">VAT registered?</Label>
                <Select value={vendorForm.vat_registered ? 'yes' : 'no'} onValueChange={v => setVendorForm({...vendorForm, vat_registered: v === 'yes'})}>
                  <SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="no">No</SelectItem><SelectItem value="yes">Yes</SelectItem></SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Email</Label><Input type="email" value={vendorForm.email} onChange={e => setVendorForm({...vendorForm, email: e.target.value})} /></div>
              <div className="space-y-1.5"><Label className="text-xs">Phone</Label><Input value={vendorForm.phone} onChange={e => setVendorForm({...vendorForm, phone: e.target.value})} /></div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Currency</Label>
                <Select value={vendorForm.currency} onValueChange={v => setVendorForm({...vendorForm, currency: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{['UGX','USD','KES','EUR','GBP','HTG','THB'].map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label className="text-xs">Country</Label>
                <Select value={vendorForm.country} onValueChange={v => setVendorForm({...vendorForm, country: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{['UG','US','KE','HT','TH','GB','EU'].map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label className="text-xs">Terms (days)</Label><Input type="number" value={vendorForm.payment_terms_days} onChange={e => setVendorForm({...vendorForm, payment_terms_days: parseInt(e.target.value) || 30})} /></div>
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowVendorForm(false)}>Cancel</Button>
              <Button className="flex-1" onClick={createVendor} disabled={!vendorForm.name} data-testid="vendor-form-submit">Create</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* NEW RULE DIALOG */}
      <Dialog open={showRuleForm} onOpenChange={setShowRuleForm}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New Categorization Rule</DialogTitle><DialogDescription className="text-xs">When a bank transaction description matches the regex below, auto-suggest posting to the target account.</DialogDescription></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label className="text-xs">Rule name *</Label><Input value={ruleForm.name} onChange={e => setRuleForm({...ruleForm, name: e.target.value})} placeholder="MTN Airtime" data-testid="rule-form-name" /></div>
            <div className="space-y-1.5"><Label className="text-xs">Regex pattern *</Label><Input value={ruleForm.match_pattern} onChange={e => setRuleForm({...ruleForm, match_pattern: e.target.value})} placeholder="AIRTIME.*MTN" /></div>
            <div className="space-y-1.5"><Label className="text-xs">Target CoA account *</Label>
              <Select value={ruleForm.target_account_id} onValueChange={v => setRuleForm({...ruleForm, target_account_id: v})}>
                <SelectTrigger className="h-9"><SelectValue placeholder="Pick..." /></SelectTrigger>
                <SelectContent>{coaAccounts.map(a => <SelectItem key={a.id} value={a.id}>{a.code} {a.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Priority (lower = checked first)</Label><Input type="number" value={ruleForm.priority} onChange={e => setRuleForm({...ruleForm, priority: parseInt(e.target.value) || 100})} /></div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowRuleForm(false)}>Cancel</Button>
              <Button className="flex-1" onClick={createRule} disabled={!ruleForm.name || !ruleForm.match_pattern || !ruleForm.target_account_id} data-testid="rule-form-submit">Create</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* RECONCILE DIALOG */}
      <Dialog open={!!reconcileTx} onOpenChange={(o) => { if (!o) { setReconcileTx(null); setReconcileAccount(''); } }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Reconcile Transaction</DialogTitle></DialogHeader>
          {reconcileTx && (
            <div className="space-y-3 mt-2">
              <div className="text-xs p-2 rounded bg-muted">
                <p className="font-medium">{reconcileTx.description}</p>
                <p className="text-muted-foreground">{reconcileTx.date} · <strong className={reconcileTx.amount > 0 ? 'text-green-700' : 'text-red-700'}>{reconcileTx.amount > 0 ? '+' : ''}{reconcileTx.amount.toFixed(2)}</strong></p>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Post to CoA account</Label>
                <Select value={reconcileAccount} onValueChange={setReconcileAccount}>
                  <SelectTrigger data-testid="reconcile-acct-picker"><SelectValue placeholder="Pick..." /></SelectTrigger>
                  <SelectContent>{coaAccounts.map(a => <SelectItem key={a.id} value={a.id}>{a.code} {a.name}</SelectItem>)}</SelectContent>
                </Select>
                {reconcileTx.suggested_account_id && reconcileTx.suggested_account_id === reconcileAccount && (
                  <p className="text-[10px] text-green-700">✓ Auto-suggested by rule</p>
                )}
              </div>
              <div className="flex gap-2 pt-2">
                <Button variant="outline" className="flex-1" onClick={() => submitReconcile('ignore')} data-testid="reconcile-ignore-btn"><X size={13} className="mr-1" />Ignore</Button>
                <Button className="flex-1" onClick={() => submitReconcile('post')} disabled={!reconcileAccount} data-testid="reconcile-post-btn">Post JE</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
