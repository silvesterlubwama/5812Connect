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
import EmptyState from '../components/EmptyState';

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
  const [editingAcctId, setEditingAcctId] = useState(null);
  const [acctForm, setAcctForm] = useState({ name: '', bank_name: '', account_number: '', account_type: 'checking', currency: 'UGX', country: 'UG', branch: '', opening_balance: '0', linked_account_id: '' });
  const [showVendorForm, setShowVendorForm] = useState(false);
  const [vendorForm, setVendorForm] = useState({ name: '', tin: '', vat_registered: false, email: '', phone: '', payment_terms_days: 30, currency: 'UGX', country: 'UG' });
  const [showRuleForm, setShowRuleForm] = useState(false);
  const [ruleForm, setRuleForm] = useState({ name: '', match_pattern: '', target_account_id: '', priority: 100 });
  const [showBillForm, setShowBillForm] = useState(false);
  const [billForm, setBillForm] = useState({ vendor_id: '', bill_date: new Date().toISOString().slice(0, 10), due_date: '', currency: 'UGX', notes: '', items: [{ description: '', qty: 1, unit_price: 0, account_id: '', tax_rate: 0 }] });
  const [payBill, setPayBill] = useState(null);
  const [payForm, setPayForm] = useState({ amount: '', bank_account_id: '', method: 'bank_transfer', reference: '', notes: '' });
  const [showRecForm, setShowRecForm] = useState(false);
  const [recForm, setRecForm] = useState({ name: '', kind: 'bill', schedule: 'monthly', day_of_month: 1, next_run_date: '', template_vendor_id: '', template_items: [{ description: '', qty: 1, unit_price: 0, account_id: '' }], template_currency: 'UGX' });
  const [reconcileTx, setReconcileTx] = useState(null);  // tx being reconciled
  const [reconcileAccount, setReconcileAccount] = useState('');
  const fileInputRef = useRef(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [aR, cR, vR, bR, rR, ruR] = await Promise.all([
        api.get('/bank/accounts').catch(() => ({ data: [] })),
        // iter 246+: use the new single-ledger Chart of Accounts. The old
        // `/api/accounting/accounts` endpoint was retired in the finance reset.
        api.get('/finance/chart-of-accounts').catch(() => ({ data: [] })),
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
      if (editingAcctId) {
        await api.put(`/bank/accounts/${editingAcctId}`, {
          name: acctForm.name, bank_name: acctForm.bank_name, account_number: acctForm.account_number,
          account_type: acctForm.account_type, branch: acctForm.branch, linked_account_id: acctForm.linked_account_id,
        });
        toast.success('Bank account updated');
      } else {
        await api.post('/bank/accounts', { ...acctForm, opening_balance: parseFloat(acctForm.opening_balance) || 0, location_id: user?.active_campus_id });
        toast.success('Bank account created');
      }
      setShowAcctForm(false);
      setEditingAcctId(null);
      setAcctForm({ name: '', bank_name: '', account_number: '', account_type: 'checking', currency: 'UGX', country: 'UG', branch: '', opening_balance: '0', linked_account_id: '' });
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const openEditAccount = (a) => {
    setEditingAcctId(a.id);
    setAcctForm({
      name: a.name || '', bank_name: a.bank_name || '', account_number: a.account_number || '',
      account_type: a.account_type || 'checking', currency: a.currency || 'UGX', country: a.country || 'UG',
      branch: a.branch || '', opening_balance: String(a.opening_balance ?? 0),
      linked_account_id: a.linked_account_id || '',
    });
    setShowAcctForm(true);
  };

  const toggleAccountActive = async (a) => {
    try {
      await api.put(`/bank/accounts/${a.id}`, { active: !a.active });
      toast.success(a.active ? 'Account closed' : 'Account reopened');
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const deleteAccount = async (a) => {
    if (!window.confirm(`Delete "${a.name}"? If any transactions exist it will be closed instead.`)) return;
    try {
      const r = await api.delete(`/bank/accounts/${a.id}`);
      toast.success(r.data?.deactivated ? 'Account had transactions — closed (deactivated)' : 'Account deleted');
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

  // Bill form helpers
  const billItems = billForm.items;
  const updateBillItem = (i, k, v) => setBillForm(p => { const it = [...p.items]; it[i] = { ...it[i], [k]: v }; return { ...p, items: it }; });
  const addBillItem = () => setBillForm(p => ({ ...p, items: [...p.items, { description: '', qty: 1, unit_price: 0, account_id: '', tax_rate: 0 }] }));
  const removeBillItem = (i) => setBillForm(p => ({ ...p, items: p.items.filter((_, j) => j !== i) }));
  const billSubtotal = billItems.reduce((s, i) => s + (parseFloat(i.qty) || 0) * (parseFloat(i.unit_price) || 0), 0);
  const billTax = billItems.reduce((s, i) => s + (parseFloat(i.qty) || 0) * (parseFloat(i.unit_price) || 0) * (parseFloat(i.tax_rate) || 0) / 100, 0);
  const billTotal = billSubtotal + billTax;

  const createBill = async () => {
    if (!billForm.vendor_id) { toast.error('Pick a vendor'); return; }
    const cleanedItems = billForm.items
      .filter(i => i.description && parseFloat(i.unit_price) > 0 && i.account_id)
      .map(i => ({
        description: i.description, qty: parseFloat(i.qty) || 1,
        unit_price: parseFloat(i.unit_price) || 0, account_id: i.account_id,
        tax_rate: parseFloat(i.tax_rate) || 0,
      }));
    if (!cleanedItems.length) { toast.error('At least one valid line item with description, price, and expense account'); return; }
    try {
      await api.post('/bank/bills', {
        vendor_id: billForm.vendor_id, bill_date: billForm.bill_date,
        due_date: billForm.due_date || undefined, currency: billForm.currency,
        notes: billForm.notes, items: cleanedItems,
      });
      toast.success('Bill created — auto-posted to ledger');
      setShowBillForm(false);
      setBillForm({ vendor_id: '', bill_date: new Date().toISOString().slice(0, 10), due_date: '', currency: 'UGX', notes: '', items: [{ description: '', qty: 1, unit_price: 0, account_id: '', tax_rate: 0 }] });
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const submitBillPayment = async () => {
    if (!payBill) return;
    try {
      await api.post(`/bank/bills/${payBill.id}/payments`, {
        amount: parseFloat(payForm.amount), bank_account_id: payForm.bank_account_id,
        method: payForm.method, reference: payForm.reference, notes: payForm.notes,
      });
      toast.success('Payment recorded — JE auto-posted');
      setPayBill(null);
      setPayForm({ amount: '', bank_account_id: '', method: 'bank_transfer', reference: '', notes: '' });
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  // Recurring form helpers
  const updateRecItem = (i, k, v) => setRecForm(p => { const it = [...p.template_items]; it[i] = { ...it[i], [k]: v }; return { ...p, template_items: it }; });
  const addRecItem = () => setRecForm(p => ({ ...p, template_items: [...p.template_items, { description: '', qty: 1, unit_price: 0, account_id: '' }] }));
  const removeRecItem = (i) => setRecForm(p => ({ ...p, template_items: p.template_items.filter((_, j) => j !== i) }));

  const createRecurring = async () => {
    if (!recForm.name || !recForm.next_run_date) { toast.error('Name and next run date required'); return; }
    if (recForm.kind === 'bill' && !recForm.template_vendor_id) { toast.error('Pick a vendor for recurring bill'); return; }
    const cleanedItems = recForm.template_items
      .filter(i => i.description && parseFloat(i.unit_price) > 0 && i.account_id)
      .map(i => ({ description: i.description, qty: parseFloat(i.qty) || 1, unit_price: parseFloat(i.unit_price) || 0, account_id: i.account_id }));
    if (!cleanedItems.length) { toast.error('At least one valid line item'); return; }
    try {
      const template = recForm.kind === 'bill'
        ? { vendor_id: recForm.template_vendor_id, items: cleanedItems, currency: recForm.template_currency }
        : { journal_id: null, items: cleanedItems };  // For JE — needs further fields; placeholder
      await api.post('/bank/recurring', {
        name: recForm.name, kind: recForm.kind, schedule: recForm.schedule,
        day_of_month: recForm.day_of_month, next_run_date: recForm.next_run_date,
        template,
      });
      toast.success('Recurring template created');
      setShowRecForm(false);
      setRecForm({ name: '', kind: 'bill', schedule: 'monthly', day_of_month: 1, next_run_date: '', template_vendor_id: '', template_items: [{ description: '', qty: 1, unit_price: 0, account_id: '' }], template_currency: 'UGX' });
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const importStatement = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !selectedBankId) return;
    const isPdf = file.name.toLowerCase().endsWith('.pdf') || file.type === 'application/pdf';
    const endpoint = isPdf
      ? `/bank/accounts/${selectedBankId}/import-pdf`
      : `/bank/accounts/${selectedBankId}/import-csv`;
    const fd = new FormData();
    fd.append('file', file);
    try {
      const r = await api.post(endpoint, fd);
      toast.success(`Imported ${r.data.transaction_count} ${isPdf ? 'PDF rows' : 'txs'} · ${r.data.auto_suggested_count} auto-suggested${isPdf ? ' (review for false positives)' : ''}`);
      reloadTransactions();
    } catch (err) {
      toast.error(err.response?.data?.detail || `${isPdf ? 'PDF' : 'CSV'} import failed`);
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

  // iter 246+: new COA uses type='asset' + is_cash=true (not the old `asset_cash`).
  const cashAccs = coaAccounts.filter(a => a.type === 'asset' && a.is_cash);
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
                <Card key={a.id} className={`rounded-xl ${a.active === false ? 'opacity-60' : ''}`} data-testid={`bank-account-${a.id}`}>
                  <CardContent className="p-3 flex items-center justify-between flex-wrap gap-2">
                    <div>
                      <div className="font-medium">{a.name}{a.active === false && <Badge variant="outline" className="ml-2 text-[10px] bg-gray-100">CLOSED</Badge>}</div>
                      <p className="text-xs text-muted-foreground">{a.bank_name} · {a.branch || '—'} · {a.account_number || '—'}</p>
                      <div className="flex items-center gap-1 mt-1">
                        <Badge variant="outline" className="text-[10px]">{a.account_type}</Badge>
                        <Badge variant="outline" className="text-[10px]">{a.country}</Badge>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="text-right">
                        <p className="text-xs text-muted-foreground uppercase">Balance</p>
                        <p className="text-lg font-bold">{fmt(a.current_balance, a.currency)}</p>
                      </div>
                      <div className="flex flex-col gap-1">
                        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => openEditAccount(a)} data-testid={`bank-account-edit-${a.id}`}>Edit</Button>
                        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => toggleAccountActive(a)} data-testid={`bank-account-close-${a.id}`}>{a.active === false ? 'Reopen' : 'Close'}</Button>
                        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-destructive hover:text-destructive" onClick={() => deleteAccount(a)} data-testid={`bank-account-del-${a.id}`}><Trash2 size={12} /></Button>
                      </div>
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
                <input ref={fileInputRef} type="file" accept=".csv,.pdf,text/csv,application/pdf" onChange={importStatement} className="hidden" data-testid="bank-statement-input" />
                <Button size="sm" variant="outline" onClick={() => fileInputRef.current?.click()} disabled={!selectedBankId} data-testid="bank-import-stmt-btn">
                  <Upload size={14} className="mr-1" />Import CSV / PDF
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
          {vendors.length === 0 ? (
            <EmptyState
              icon={Users}
              title="No vendors yet"
              description="Add suppliers and contractors here to track bills, payment terms, and outstanding balances."
              action={{ label: 'New vendor', onClick: () => setShowVendorForm(true), testid: 'bank-empty-new-vendor-btn' }}
              testid="bank-vendors-empty"
            />
          ) : (
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
          <div className="flex justify-end">
            <Button size="sm" onClick={() => setShowBillForm(true)} disabled={vendors.length === 0} data-testid="bank-new-bill-btn"><Plus size={14} className="mr-1" />New Bill</Button>
          </div>
          {bills.length === 0 ? (
            <EmptyState
              icon={Receipt}
              title="No bills yet"
              description={vendors.length === 0 ? 'Create a vendor first, then enter bills against them.' : 'Track payables — when they\'re due, what\'s outstanding, and what\'s been paid.'}
              action={vendors.length > 0 ? { label: 'New bill', onClick: () => setShowBillForm(true), testid: 'bank-empty-new-bill-btn' } : null}
              testid="bank-bills-empty"
            />
          ) : (
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
                      {(b.status === 'open' || b.status === 'partially_paid') && (
                        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => { setPayBill(b); setPayForm({ amount: String(b.balance || ''), bank_account_id: accounts[0]?.id || '', method: 'bank_transfer', reference: '', notes: '' }); }} data-testid={`bank-bill-pay-${b.id}`}>Record payment</Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* RECURRING */}
        <TabsContent value="recurring" className="space-y-3">
          <div className="flex justify-end">
            <Button size="sm" onClick={() => setShowRecForm(true)} disabled={vendors.length === 0} data-testid="bank-new-recurring-btn"><Plus size={14} className="mr-1" />New Recurring</Button>
          </div>
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
      <Dialog open={showAcctForm} onOpenChange={(o) => { setShowAcctForm(o); if (!o) setEditingAcctId(null); }}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editingAcctId ? 'Edit Bank Account' : 'New Bank Account'}</DialogTitle></DialogHeader>
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
              <Button className="flex-1" onClick={createAccount} disabled={!acctForm.name || !acctForm.linked_account_id} data-testid="bank-form-submit">{editingAcctId ? 'Save' : 'Create'}</Button>
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

      {/* NEW BILL DIALOG */}
      <Dialog open={showBillForm} onOpenChange={setShowBillForm}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New Bill</DialogTitle><DialogDescription className="text-xs">Vendor bills auto-post to the accounting ledger (Dr Expense / Cr AP).</DialogDescription></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Vendor *</Label>
                <Select value={billForm.vendor_id} onValueChange={v => setBillForm({ ...billForm, vendor_id: v })}>
                  <SelectTrigger className="h-9" data-testid="bill-form-vendor"><SelectValue placeholder="Pick..." /></SelectTrigger>
                  <SelectContent>{vendors.map(v => <SelectItem key={v.id} value={v.id}>{v.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label className="text-xs">Bill date *</Label><Input type="date" value={billForm.bill_date} onChange={e => setBillForm({ ...billForm, bill_date: e.target.value })} /></div>
              <div className="space-y-1.5"><Label className="text-xs">Due date</Label><Input type="date" value={billForm.due_date} onChange={e => setBillForm({ ...billForm, due_date: e.target.value })} placeholder="Auto from terms" /></div>
            </div>
            <div className="border rounded-lg p-2 space-y-2">
              <div className="grid grid-cols-12 gap-1.5 text-[10px] uppercase text-muted-foreground font-semibold px-1">
                <div className="col-span-4">Description</div>
                <div className="col-span-1 text-right">Qty</div>
                <div className="col-span-2 text-right">Unit Price</div>
                <div className="col-span-3">Expense Account</div>
                <div className="col-span-1 text-right">VAT %</div>
                <div className="col-span-1"></div>
              </div>
              {billItems.map((it, i) => (
                <div key={i} className="grid grid-cols-12 gap-1.5 items-center" data-testid={`bill-item-${i}`}>
                  <Input className="col-span-4 h-8 text-xs" value={it.description} onChange={e => updateBillItem(i, 'description', e.target.value)} placeholder="Maize seeds" />
                  <Input className="col-span-1 h-8 text-xs text-right" type="number" step="1" value={it.qty} onChange={e => updateBillItem(i, 'qty', e.target.value)} />
                  <Input className="col-span-2 h-8 text-xs text-right" type="number" step="0.01" value={it.unit_price} onChange={e => updateBillItem(i, 'unit_price', e.target.value)} />
                  <Select value={it.account_id} onValueChange={v => updateBillItem(i, 'account_id', v)}>
                    <SelectTrigger className="col-span-3 h-8 text-xs"><SelectValue placeholder="Account" /></SelectTrigger>
                    <SelectContent>{coaAccounts.filter(a => a.type === 'expense' || (a.type === 'asset' && !a.is_cash)).map(a => <SelectItem key={a.id} value={a.id}>{a.code} {a.name}</SelectItem>)}</SelectContent>
                  </Select>
                  <Input className="col-span-1 h-8 text-xs text-right" type="number" step="0.1" value={it.tax_rate} onChange={e => updateBillItem(i, 'tax_rate', e.target.value)} />
                  <Button size="sm" variant="ghost" className="col-span-1 h-8 text-destructive" disabled={billItems.length <= 1} onClick={() => removeBillItem(i)}>×</Button>
                </div>
              ))}
              <Button size="sm" variant="outline" className="w-full h-8 text-xs" onClick={addBillItem}><Plus size={12} className="mr-1" />Add line</Button>
              <div className="grid grid-cols-12 gap-1.5 text-xs font-semibold pt-2 border-t">
                <div className="col-span-7 text-right">Subtotal / VAT / Total</div>
                <div className="col-span-2 text-right">{billSubtotal.toLocaleString()}</div>
                <div className="col-span-1 text-right">{billTax.toLocaleString()}</div>
                <div className="col-span-2 text-right text-base">{billTotal.toLocaleString()}</div>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Currency</Label>
                <Select value={billForm.currency} onValueChange={v => setBillForm({ ...billForm, currency: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{['UGX','USD','KES','EUR','GBP','HTG','THB'].map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5 col-span-2"><Label className="text-xs">Notes</Label><Input value={billForm.notes} onChange={e => setBillForm({ ...billForm, notes: e.target.value })} /></div>
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowBillForm(false)}>Cancel</Button>
              <Button className="flex-1" onClick={createBill} disabled={!billForm.vendor_id || billTotal === 0} data-testid="bill-form-submit">Create Bill</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* RECORD PAYMENT DIALOG */}
      <Dialog open={!!payBill} onOpenChange={(o) => { if (!o) setPayBill(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Record payment — {payBill?.bill_number}</DialogTitle><DialogDescription className="text-xs">Vendor: <strong>{payBill?.vendor_name}</strong> · Balance: <strong>{payBill ? fmt(payBill.balance, payBill.currency) : ''}</strong></DialogDescription></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Amount *</Label><Input type="number" step="0.01" value={payForm.amount} onChange={e => setPayForm({ ...payForm, amount: e.target.value })} data-testid="pay-amount" /></div>
              <div className="space-y-1.5"><Label className="text-xs">Method</Label>
                <Select value={payForm.method} onValueChange={v => setPayForm({ ...payForm, method: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{['bank_transfer','cheque','cash','mobile_money','card'].map(m => <SelectItem key={m} value={m} className="capitalize">{m.replace('_', ' ')}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">From bank account *</Label>
              <Select value={payForm.bank_account_id} onValueChange={v => setPayForm({ ...payForm, bank_account_id: v })}>
                <SelectTrigger data-testid="pay-bank"><SelectValue placeholder="Pick..." /></SelectTrigger>
                <SelectContent>{accounts.map(a => <SelectItem key={a.id} value={a.id}>{a.name} ({a.currency})</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Reference</Label><Input value={payForm.reference} onChange={e => setPayForm({ ...payForm, reference: e.target.value })} placeholder="TXN ref / cheque #" /></div>
            <div className="space-y-1.5"><Label className="text-xs">Notes</Label><Input value={payForm.notes} onChange={e => setPayForm({ ...payForm, notes: e.target.value })} /></div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setPayBill(null)}>Cancel</Button>
              <Button className="flex-1" onClick={submitBillPayment} disabled={!payForm.amount || !payForm.bank_account_id} data-testid="pay-submit">Record Payment</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* NEW RECURRING DIALOG */}
      <Dialog open={showRecForm} onOpenChange={setShowRecForm}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New Recurring Bill</DialogTitle><DialogDescription className="text-xs">A new bill will be auto-created on the schedule below.</DialogDescription></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Name *</Label><Input value={recForm.name} onChange={e => setRecForm({ ...recForm, name: e.target.value })} placeholder="Monthly Office Rent" data-testid="rec-form-name" /></div>
              <div className="space-y-1.5"><Label className="text-xs">Next run date *</Label><Input type="date" value={recForm.next_run_date} onChange={e => setRecForm({ ...recForm, next_run_date: e.target.value })} /></div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Schedule</Label>
                <Select value={recForm.schedule} onValueChange={v => setRecForm({ ...recForm, schedule: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{['daily','weekly','biweekly','monthly','quarterly','yearly'].map(s => <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label className="text-xs">Day of month</Label><Input type="number" min={1} max={31} value={recForm.day_of_month} onChange={e => setRecForm({ ...recForm, day_of_month: parseInt(e.target.value) || 1 })} /></div>
              <div className="space-y-1.5"><Label className="text-xs">Currency</Label>
                <Select value={recForm.template_currency} onValueChange={v => setRecForm({ ...recForm, template_currency: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{['UGX','USD','KES','EUR','GBP'].map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Vendor *</Label>
              <Select value={recForm.template_vendor_id} onValueChange={v => setRecForm({ ...recForm, template_vendor_id: v })}>
                <SelectTrigger data-testid="rec-form-vendor"><SelectValue placeholder="Pick..." /></SelectTrigger>
                <SelectContent>{vendors.map(v => <SelectItem key={v.id} value={v.id}>{v.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="border rounded-lg p-2 space-y-2">
              <p className="text-[10px] uppercase text-muted-foreground font-semibold">Line items (template)</p>
              {recForm.template_items.map((it, i) => (
                <div key={i} className="grid grid-cols-12 gap-1.5 items-center">
                  <Input className="col-span-5 h-8 text-xs" value={it.description} onChange={e => updateRecItem(i, 'description', e.target.value)} placeholder="Office rent" />
                  <Input className="col-span-2 h-8 text-xs text-right" type="number" step="1" value={it.qty} onChange={e => updateRecItem(i, 'qty', e.target.value)} />
                  <Input className="col-span-2 h-8 text-xs text-right" type="number" step="0.01" value={it.unit_price} onChange={e => updateRecItem(i, 'unit_price', e.target.value)} placeholder="Price" />
                  <Select value={it.account_id} onValueChange={v => updateRecItem(i, 'account_id', v)}>
                    <SelectTrigger className="col-span-2 h-8 text-xs"><SelectValue placeholder="Acct" /></SelectTrigger>
                    <SelectContent>{coaAccounts.filter(a => a.type === 'expense').map(a => <SelectItem key={a.id} value={a.id}>{a.code} {a.name}</SelectItem>)}</SelectContent>
                  </Select>
                  <Button size="sm" variant="ghost" className="col-span-1 h-8 text-destructive" disabled={recForm.template_items.length <= 1} onClick={() => removeRecItem(i)}>×</Button>
                </div>
              ))}
              <Button size="sm" variant="outline" className="w-full h-8 text-xs" onClick={addRecItem}><Plus size={12} className="mr-1" />Add line</Button>
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowRecForm(false)}>Cancel</Button>
              <Button className="flex-1" onClick={createRecurring} disabled={!recForm.name || !recForm.next_run_date || !recForm.template_vendor_id} data-testid="rec-form-submit">Create Schedule</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
