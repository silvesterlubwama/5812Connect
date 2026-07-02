import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Textarea } from '../components/ui/textarea';
import { BookOpen, Plus, RefreshCw, Trash2, Check, X, RotateCcw, FileText, TrendingUp, TrendingDown, Scale, Wallet, Users } from 'lucide-react';
import api, { chartAccountsApi, adminApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import EmptyState from '../components/EmptyState';

const CATEGORY_COLORS = {
  asset: 'bg-blue-100 text-blue-700 border-blue-200',
  liability: 'bg-amber-100 text-amber-700 border-amber-200',
  equity: 'bg-purple-100 text-purple-700 border-purple-200',
  income: 'bg-green-100 text-green-700 border-green-200',
  expense: 'bg-red-100 text-red-700 border-red-200',
};
const STATUS_COLORS = {
  draft: 'bg-amber-100 text-amber-700',
  posted: 'bg-green-100 text-green-700',
  cancelled: 'bg-gray-100 text-gray-700',
};

export default function AccountingPage() {
  const { user } = useAuth();
  // Campus switcher — mirrors Financial page pattern. Defaults to active campus / user's primary.
  const [locationFilter, setLocationFilter] = useState(localStorage.getItem('5812_active_campus') || user?.location_id || 'loc_001');
  const [allLocations, setAllLocations] = useState([]);
  // Currency derived from the chosen location (falls back to UGX)
  const currentLocation = allLocations.find(l => l.id === locationFilter);
  const currentCurrency = currentLocation?.currency || 'UGX';
  const isFinanceAdmin = ['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director'].includes(user?.role);
  const [accounts, setAccounts] = useState([]);
  const [journals, setJournals] = useState([]);
  const [accountTypes, setAccountTypes] = useState([]);
  const [entries, setEntries] = useState([]);
  const [taxes, setTaxes] = useState([]);
  const [fiscalPeriods, setFiscalPeriods] = useState([]);
  const [tb, setTb] = useState(null);
  const [pl, setPl] = useState(null);
  const [bs, setBs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showAccountForm, setShowAccountForm] = useState(false);
  const [accountForm, setAccountForm] = useState({ id: '', code: '', name: '', type: 'asset_current', currency: 'UGX' });
  const [showJournalForm, setShowJournalForm] = useState(false);
  const [journalForm, setJournalForm] = useState({ id: '', code: '', name: '', kind: 'miscellaneous', default_debit_account_id: '', default_credit_account_id: '' });
  const [showEntryForm, setShowEntryForm] = useState(false);
  const [entryForm, setEntryForm] = useState({ journal_id: '', date: new Date().toISOString().slice(0, 10), ref: '', narration: '', lines: [{ account_id: '', debit: '', credit: '', description: '' }, { account_id: '', debit: '', credit: '', description: '' }] });
  const [viewEntry, setViewEntry] = useState(null);
  const [showTaxForm, setShowTaxForm] = useState(false);
  const [taxForm, setTaxForm] = useState({ id: '', name: '', rate: '', kind: 'sales', inclusive: false, account_id: '' });
  const [showFiscalForm, setShowFiscalForm] = useState(false);
  const [fiscalForm, setFiscalForm] = useState({ name: '', start_date: '', end_date: '' });
  const [viewLedger, setViewLedger] = useState(null);

  // ===== CHART CASH ACCOUNTS (cash/bank/momo — user-assignable) =====
  const [chartAccounts, setChartAccounts] = useState([]);
  const [chartAccountsLoading, setChartAccountsLoading] = useState(false);
  const [showChartAccountForm, setShowChartAccountForm] = useState(false);
  const [chartAccountForm, setChartAccountForm] = useState({ id: '', name: '', kind: 'cash', currency: 'UGX', starting_balance: '', location_id: '', assigned_user_ids: [], notes: '' });
  const [showAssignees, setShowAssignees] = useState(null); // account being edited
  const [assigneePicks, setAssigneePicks] = useState([]);
  const [allUsers, setAllUsers] = useState([]);
  const [viewAccountTxns, setViewAccountTxns] = useState(null); // { account, transactions }
  const [showTransferForm, setShowTransferForm] = useState(false);
  const [transferForm, setTransferForm] = useState({ from_account_id: '', to_account_id: '', amount: '', notes: '' });

  const loadChartAccounts = useCallback(async () => {
    setChartAccountsLoading(true);
    try {
      const r = await chartAccountsApi.list();
      setChartAccounts(r.data || []);
    } catch { setChartAccounts([]); }
    finally { setChartAccountsLoading(false); }
  }, []);

  useEffect(() => { loadChartAccounts(); }, [loadChartAccounts]);

  useEffect(() => {
    if (isFinanceAdmin) {
      adminApi.userDirectory().then(r => setAllUsers(r.data || [])).catch(() => {});
    }
  }, [isFinanceAdmin]);

  const openNewChartAccount = () => {
    setChartAccountForm({ id: '', name: '', kind: 'cash', currency: currentCurrency || 'UGX', starting_balance: '', location_id: locationFilter, assigned_user_ids: [], notes: '' });
    setShowChartAccountForm(true);
  };

  const saveChartAccount = async () => {
    if (!chartAccountForm.name.trim()) return toast.error('Name required');
    try {
      const payload = {
        name: chartAccountForm.name.trim(),
        kind: chartAccountForm.kind,
        currency: chartAccountForm.currency,
        starting_balance: parseFloat(chartAccountForm.starting_balance) || 0,
        location_id: chartAccountForm.location_id || '',
        assigned_user_ids: chartAccountForm.assigned_user_ids || [],
        notes: chartAccountForm.notes || '',
      };
      if (chartAccountForm.id) {
        await chartAccountsApi.update(chartAccountForm.id, payload);
        toast.success('Account updated');
      } else {
        await chartAccountsApi.create(payload);
        toast.success('Account created');
      }
      setShowChartAccountForm(false);
      loadChartAccounts();
    } catch (err) { toast.error(err.response?.data?.detail || 'Save failed'); }
  };

  const openAssignees = (acct) => {
    setShowAssignees(acct);
    setAssigneePicks(acct.assigned_user_ids || []);
  };
  const saveAssignees = async () => {
    try {
      await chartAccountsApi.setAssignees(showAssignees.id, assigneePicks);
      toast.success('Assignees updated');
      setShowAssignees(null);
      loadChartAccounts();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
  };

  const openTxns = async (acct) => {
    try {
      const r = await chartAccountsApi.transactions(acct.id, 200);
      setViewAccountTxns({ account: acct, ...r.data });
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to load'); }
  };

  const removeChartAccount = async (acct) => {
    if (!window.confirm(`Delete "${acct.name}"? If transactions exist, it will be archived instead.`)) return;
    try {
      const r = await chartAccountsApi.remove(acct.id);
      toast.success(r.data.archived ? `Archived (${r.data.referenced_txns} txns keep history)` : 'Deleted');
      loadChartAccounts();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
  };

  const submitTransfer = async () => {
    try {
      await chartAccountsApi.transfer({
        from_account_id: transferForm.from_account_id,
        to_account_id: transferForm.to_account_id,
        amount: parseFloat(transferForm.amount),
        notes: transferForm.notes,
      });
      toast.success('Transfer recorded');
      setShowTransferForm(false);
      setTransferForm({ from_account_id: '', to_account_id: '', amount: '', notes: '' });
      loadChartAccounts();
    } catch (err) { toast.error(err.response?.data?.detail || 'Transfer failed'); }
  };

  // Load all locations once (for the switcher) — admins see all; non-admins are
  // restricted by the backend to their own campuses anyway.
  useEffect(() => {
    api.get('/locations').then(r => setAllLocations(r.data || [])).catch(() => setAllLocations([]));
  }, []);

  // Force non-admins to their primary campus (mirrors Financial restriction).
  useEffect(() => {
    if (!isFinanceAdmin && user?.location_id && locationFilter !== user.location_id) {
      setLocationFilter(user.location_id);
    }
  }, [user, isFinanceAdmin]); // eslint-disable-line react-hooks/exhaustive-deps

  const [showReversed, setShowReversed] = useState(false);
  const [selectedEntryIds, setSelectedEntryIds] = useState(new Set());
  const bulkDeleteEntries = async () => {
    if (selectedEntryIds.size === 0) return;
    if (!window.confirm(`Delete ${selectedEntryIds.size} entr(ies)? Posted entries will be skipped — use Bulk Reverse for those.`)) return;
    try {
      const ids = Array.from(selectedEntryIds);
      const r = await api.post('/accounting/entries/bulk-delete', { ids });
      if (r.data.skipped_posted) {
        toast.success(`Deleted ${r.data.deleted} draft entries. ${r.data.skipped_posted} posted entries were skipped — click Bulk Reverse to reverse them instead.`, { duration: 6000 });
      } else {
        toast.success(`Deleted ${r.data.deleted} entr(ies)`);
      }
      setSelectedEntryIds(new Set());
      fetchAll();
    } catch (err) { toast.error(err.response?.data?.detail || 'Bulk delete failed'); }
  };
  const bulkReverseEntries = async () => {
    if (selectedEntryIds.size === 0) return;
    if (!window.confirm(`Reverse ${selectedEntryIds.size} posted entr(ies)? Each will create a mirror entry that cancels the original.`)) return;
    try {
      const ids = Array.from(selectedEntryIds);
      const r = await api.post('/accounting/entries/bulk-reverse', { ids });
      const parts = [];
      if (r.data.reversed) parts.push(`Reversed ${r.data.reversed}`);
      if (r.data.skipped_already_reversed) parts.push(`${r.data.skipped_already_reversed} already reversed`);
      if (r.data.skipped_not_posted) parts.push(`${r.data.skipped_not_posted} not posted`);
      toast.success(parts.join(' · ') || 'Nothing to reverse', { duration: 5000 });
      setSelectedEntryIds(new Set());
      fetchAll();
    } catch (err) { toast.error(err.response?.data?.detail || 'Bulk reverse failed'); }
  };
  const repairReversalLines = async () => {
    if (!window.confirm('This scans all posted entries and fixes reversal lines that were left as draft. Safe to run — only flips line-status to posted. Continue?')) return;
    try {
      const r = await api.post('/accounting/entries/repair-reversal-lines');
      toast.success(`Repaired ${r.data.fixed_entries} entr(ies). Refresh the reports to see corrected totals.`, { duration: 6000 });
      fetchAll();
    } catch (err) { toast.error(err.response?.data?.detail || 'Repair failed'); }
  };
  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [accRes, jrnRes, typesRes, entRes, taxRes, fpRes, tbRes, plRes, bsRes] = await Promise.all([
        api.get('/accounting/accounts', { params: { location_id: locationFilter } }).catch(() => ({ data: [] })),
        api.get('/accounting/journals').catch(() => ({ data: [] })),
        api.get('/accounting/account-types').catch(() => ({ data: [] })),
        api.get('/accounting/entries', { params: { limit: 100, include_reversed: showReversed } }).catch(() => ({ data: [] })),
        api.get('/accounting/taxes').catch(() => ({ data: [] })),
        api.get('/accounting/fiscal-periods').catch(() => ({ data: [] })),
        api.get('/accounting/reports/trial-balance', { params: { location_id: locationFilter } }).catch(() => ({ data: null })),
        api.get('/accounting/reports/profit-loss', { params: { location_id: locationFilter } }).catch(() => ({ data: null })),
        api.get('/accounting/reports/balance-sheet', { params: { location_id: locationFilter } }).catch(() => ({ data: null })),
      ]);
      setAccounts(accRes.data || []);
      // Filter journals + entries to the picked campus (so Director of one campus
      // doesn't see another's journals if get_campus_filter happens to be permissive).
      setJournals((jrnRes.data || []).filter(j => !j.location_id || j.location_id === locationFilter));
      setAccountTypes(typesRes.data || []);
      setEntries((entRes.data || []).filter(e => !e.location_id || e.location_id === locationFilter));
      setTaxes((taxRes.data || []).filter(t => !t.location_id || t.location_id === locationFilter));
      setFiscalPeriods((fpRes.data || []).filter(f => !f.location_id || f.location_id === locationFilter));
      setTb(tbRes.data); setPl(plRes.data); setBs(bsRes.data);
    } finally { setLoading(false); }
  }, [locationFilter, showReversed]);
  useEffect(() => { fetchAll(); }, [fetchAll]);

  const seedDefault = async () => {
    try {
      const res = await api.post('/accounting/seed', { location_id: locationFilter, currency: currentCurrency });
      toast.success(`Seeded ${res.data.seeded} accounts (${res.data.skipped} already existed)`);
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const openNewAccountForm = () => {
    setAccountForm({ id: '', code: '', name: '', type: 'asset_current', currency: currentCurrency });
    setShowAccountForm(true);
  };

  const openEditAccount = (a) => {
    setAccountForm({ id: a.id, code: a.code, name: a.name, type: a.type, currency: a.currency || currentCurrency });
    setShowAccountForm(true);
  };

  const saveAccount = async () => {
    try {
      if (accountForm.id) {
        await api.put(`/accounting/accounts/${accountForm.id}`, { code: accountForm.code, name: accountForm.name, type: accountForm.type, currency: accountForm.currency });
        toast.success('Account updated');
      } else {
        await api.post('/accounting/accounts', { ...accountForm, location_id: locationFilter });
        toast.success('Account created');
      }
      setShowAccountForm(false);
      setAccountForm({ id: '', code: '', name: '', type: 'asset_current', currency: 'UGX' });
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const deleteAccount = async (a) => {
    if (!window.confirm(`Delete account "${a.code} ${a.name}"? Accounts with journal lines will be deactivated instead.`)) return;
    try {
      const r = await api.delete(`/accounting/accounts/${a.id}`);
      toast.success(r.data.deactivated ? 'Deactivated (had journal lines)' : 'Deleted');
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const openEditJournal = (j) => {
    setJournalForm({ id: j.id, code: j.code, name: j.name, kind: j.kind, default_debit_account_id: j.default_debit_account_id || '', default_credit_account_id: j.default_credit_account_id || '' });
    setShowJournalForm(true);
  };

  const saveJournal = async () => {
    try {
      if (journalForm.id) {
        await api.put(`/accounting/journals/${journalForm.id}`, { code: journalForm.code, name: journalForm.name, kind: journalForm.kind, default_debit_account_id: journalForm.default_debit_account_id, default_credit_account_id: journalForm.default_credit_account_id });
        toast.success('Journal updated');
      } else {
        await api.post('/accounting/journals', { ...journalForm, location_id: locationFilter });
        toast.success('Journal created');
      }
      setShowJournalForm(false);
      setJournalForm({ id: '', code: '', name: '', kind: 'miscellaneous', default_debit_account_id: '', default_credit_account_id: '' });
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const deleteJournal = async (j) => {
    if (!window.confirm(`Delete journal "${j.code} ${j.name}"?`)) return;
    try {
      await api.delete(`/accounting/journals/${j.id}`);
      toast.success('Deleted');
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const openEditTax = (t) => {
    setTaxForm({ id: t.id, name: t.name, rate: t.rate, kind: t.kind, inclusive: !!t.inclusive, account_id: t.account_id || '' });
    setShowTaxForm(true);
  };

  const saveTax = async () => {
    try {
      const payload = { ...taxForm, rate: parseFloat(taxForm.rate) };
      if (taxForm.id) {
        await api.put(`/accounting/taxes/${taxForm.id}`, payload);
        toast.success('Tax updated');
      } else {
        await api.post('/accounting/taxes', { ...payload, location_id: locationFilter });
        toast.success('Tax created');
      }
      setShowTaxForm(false);
      setTaxForm({ id: '', name: '', rate: '', kind: 'sales', inclusive: false, account_id: '' });
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const deleteTax = async (t) => {
    if (!window.confirm(`Delete tax "${t.name}"?`)) return;
    try {
      await api.delete(`/accounting/taxes/${t.id}`);
      toast.success('Deleted');
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const createAccount = saveAccount; // legacy alias
  const createJournal = saveJournal; // legacy alias
  const createTax = saveTax; // legacy alias

  const createFiscal = async () => {
    try {
      await api.post('/accounting/fiscal-periods', { ...fiscalForm, location_id: locationFilter });
      toast.success('Fiscal period created');
      setShowFiscalForm(false);
      setFiscalForm({ name: '', start_date: '', end_date: '' });
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const cycleFiscalStatus = async (fp) => {
    const next = fp.status === 'open' ? 'closed' : fp.status === 'closed' ? 'locked' : 'open';
    try {
      await api.put(`/accounting/fiscal-periods/${fp.id}`, { status: next });
      toast.success(`Period set to ${next}`);
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const updateLine = (idx, key, value) => {
    setEntryForm(prev => {
      const lines = [...prev.lines];
      lines[idx] = { ...lines[idx], [key]: value };
      return { ...prev, lines };
    });
  };
  const addLine = () => setEntryForm(prev => ({ ...prev, lines: [...prev.lines, { account_id: '', debit: '', credit: '', description: '' }] }));
  const removeLine = (idx) => setEntryForm(prev => ({ ...prev, lines: prev.lines.filter((_, i) => i !== idx) }));
  const lineTotals = () => {
    const d = entryForm.lines.reduce((s, l) => s + (parseFloat(l.debit) || 0), 0);
    const c = entryForm.lines.reduce((s, l) => s + (parseFloat(l.credit) || 0), 0);
    return { debit: d, credit: c, balanced: Math.abs(d - c) < 0.01 && d > 0 };
  };

  const submitEntry = async () => {
    const totals = lineTotals();
    if (!totals.balanced) { toast.error(`Unbalanced: D ${totals.debit} ≠ C ${totals.credit}`); return; }
    try {
      const lines = entryForm.lines.map(l => ({
        account_id: l.account_id,
        debit: parseFloat(l.debit) || 0,
        credit: parseFloat(l.credit) || 0,
        description: l.description,
      })).filter(l => l.account_id && (l.debit > 0 || l.credit > 0));
      await api.post('/accounting/entries', { ...entryForm, lines, location_id: locationFilter });
      toast.success('Entry created (draft)');
      setShowEntryForm(false);
      setEntryForm({ journal_id: '', date: new Date().toISOString().slice(0, 10), ref: '', narration: '', lines: [{ account_id: '', debit: '', credit: '', description: '' }, { account_id: '', debit: '', credit: '', description: '' }] });
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const postEntry = async (id) => {
    try { await api.post(`/accounting/entries/${id}/post`); toast.success('Posted'); fetchAll(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };
  const cancelEntry = async (id) => {
    if (!window.confirm('Cancel this draft entry?')) return;
    try { await api.post(`/accounting/entries/${id}/cancel`); toast.success('Cancelled'); fetchAll(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };
  const reverseEntry = async (id) => {
    if (!window.confirm('Create a reverse entry today?')) return;
    try { await api.post(`/accounting/entries/${id}/reverse`); toast.success('Reverse draft created'); fetchAll(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const openLedger = async (acc) => {
    try {
      const res = await api.get(`/accounting/accounts/${acc.id}/ledger`);
      setViewLedger(res.data);
    } catch { toast.error('Failed to load ledger'); }
  };

  const openEntry = async (entry) => {
    try {
      const res = await api.get(`/accounting/entries/${entry.id}`);
      setViewEntry(res.data);
    } catch { toast.error('Failed to load entry'); }
  };

  if (loading) return <div className="p-6"><div className="space-y-4">{[1,2,3].map(i => <div key={i} className="h-24 bg-muted animate-pulse rounded-xl" />)}</div></div>;

  const fmt = (n) => (Number(n) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const accountName = (id) => accounts.find(a => a.id === id) || {};

  return (
    <div className="p-6 space-y-5" data-testid="accounting-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold font-heading flex items-center gap-2">
            <BookOpen size={22} className="text-primary" /> Accounting
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">Double-entry ledger · Chart of Accounts · Journals · Reports{currentLocation ? <> · <span className="font-medium">{currentLocation.name}</span> ({currentCurrency})</> : null}</p>
        </div>
        <div className="flex gap-2 items-center flex-wrap">
          {/* Campus switcher — same pattern as Financial page */}
          <Select value={locationFilter} onValueChange={setLocationFilter} disabled={!isFinanceAdmin && allLocations.length === 1}>
            <SelectTrigger className="h-9 w-56 text-xs" data-testid="acc-campus-switcher"><SelectValue placeholder="Pick campus" /></SelectTrigger>
            <SelectContent>
              {allLocations.map(l => (
                <SelectItem key={l.id} value={l.id}>{l.name} <span className="text-muted-foreground">({l.currency || 'UGX'})</span></SelectItem>
              ))}
            </SelectContent>
          </Select>
          {accounts.length === 0 && (
            <Button size="sm" onClick={seedDefault} data-testid="acc-seed-btn"><Plus size={14} className="mr-1" /> Seed Default CoA</Button>
          )}
          <Button size="sm" variant="outline" onClick={fetchAll} data-testid="acc-refresh-btn"><RefreshCw size={14} className="mr-1" /> Refresh</Button>
        </div>
      </div>

      {/* Reports summary */}
      {tb && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3" data-testid="acc-reports-summary">
          <Card className="rounded-xl"><CardContent className="p-4">
            <div className="flex items-center gap-2 mb-1"><Scale size={14} className="text-muted-foreground" /><p className="text-xs text-muted-foreground uppercase">Trial Balance</p></div>
            <p className="text-2xl font-bold">{tb.totals.balanced ? '✓ Balanced' : '⚠ Off'}</p>
            <p className="text-xs text-muted-foreground">D {fmt(tb.totals.debit)} = C {fmt(tb.totals.credit)} {currentCurrency}</p>
          </CardContent></Card>
          {pl && (
            <Card className="rounded-xl"><CardContent className="p-4">
              <div className="flex items-center gap-2 mb-1"><TrendingUp size={14} className="text-green-600" /><p className="text-xs text-muted-foreground uppercase">Income</p></div>
              <p className="text-2xl font-bold text-green-700">{currentCurrency} {fmt(pl.totals.income)}</p>
            </CardContent></Card>
          )}
          {pl && (
            <Card className="rounded-xl"><CardContent className="p-4">
              <div className="flex items-center gap-2 mb-1"><TrendingDown size={14} className="text-red-600" /><p className="text-xs text-muted-foreground uppercase">Expense</p></div>
              <p className="text-2xl font-bold text-red-700">{currentCurrency} {fmt(pl.totals.expense)}</p>
            </CardContent></Card>
          )}
          {pl && (
            <Card className="rounded-xl"><CardContent className="p-4">
              <p className="text-xs text-muted-foreground uppercase mb-1">Net Profit</p>
              <p className={`text-2xl font-bold ${pl.totals.net_profit >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>{currentCurrency} {fmt(pl.totals.net_profit)}</p>
            </CardContent></Card>
          )}
        </div>
      )}

      <Tabs defaultValue="entries" className="space-y-3">
        <TabsList className="flex-wrap">
          <TabsTrigger value="entries" data-testid="acc-tab-entries"><FileText size={13} className="mr-1" /> Journal Entries</TabsTrigger>
          <TabsTrigger value="cash-accounts" data-testid="acc-tab-cash-accounts"><Wallet size={13} className="mr-1" /> Cash Accounts</TabsTrigger>
          <TabsTrigger value="accounts" data-testid="acc-tab-accounts">Chart of Accounts</TabsTrigger>
          <TabsTrigger value="journals" data-testid="acc-tab-journals">Journals</TabsTrigger>
          <TabsTrigger value="taxes" data-testid="acc-tab-taxes">Taxes</TabsTrigger>
          <TabsTrigger value="fiscal" data-testid="acc-tab-fiscal">Fiscal Periods</TabsTrigger>
          <TabsTrigger value="reports" data-testid="acc-tab-reports">Reports</TabsTrigger>
        </TabsList>

        {/* ENTRIES */}
        <TabsContent value="entries" className="space-y-3">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer select-none">
              <input
                type="checkbox"
                checked={showReversed}
                onChange={e => setShowReversed(e.target.checked)}
                data-testid="acc-show-reversed"
              />
              Show reversed entries (originals + their reversals)
            </label>
            <div className="flex items-center gap-2">
              {selectedEntryIds.size > 0 && (
                <>
                  <Badge className="text-xs" data-testid="acc-bulk-count">{selectedEntryIds.size} selected</Badge>
                  <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={bulkReverseEntries} data-testid="acc-bulk-reverse-btn"><RotateCcw size={12} /> Reverse</Button>
                  <Button size="sm" variant="destructive" className="h-7 text-xs gap-1" onClick={bulkDeleteEntries} data-testid="acc-bulk-delete-btn"><Trash2 size={12} /> Delete</Button>
                  <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setSelectedEntryIds(new Set())}><X size={12} /></Button>
                </>
              )}
              {isFinanceAdmin && selectedEntryIds.size === 0 && (
                <Button size="sm" variant="ghost" className="h-7 text-xs text-muted-foreground" onClick={repairReversalLines} data-testid="acc-repair-reversals-btn" title="One-time fix for legacy reversals whose lines were left as draft"><RefreshCw size={12} className="mr-1" /> Repair Reversals</Button>
              )}
              <Button size="sm" disabled={journals.length === 0} onClick={() => setShowEntryForm(true)} data-testid="acc-new-entry-btn"><Plus size={14} className="mr-1" /> New Entry</Button>
            </div>
          </div>
          {entries.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">No entries yet.</p> : (
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-[11px] text-muted-foreground pl-3 cursor-pointer select-none">
                <input
                  type="checkbox"
                  data-testid="acc-select-all"
                  checked={entries.length > 0 && entries.every(e => selectedEntryIds.has(e.id))}
                  onChange={() => { if (selectedEntryIds.size === entries.length) setSelectedEntryIds(new Set()); else setSelectedEntryIds(new Set(entries.map(e => e.id))); }}
                />
                Select all visible
              </label>
              {entries.map(e => (
                <Card key={e.id} className={`rounded-xl ${(e.is_reversed || e.reverses) ? 'opacity-60' : ''} ${selectedEntryIds.has(e.id) ? 'ring-2 ring-primary/40' : ''}`} data-testid={`acc-entry-${e.id}`}>
                  <CardContent className="p-3 flex items-center justify-between gap-3 flex-wrap">
                    <input
                      type="checkbox"
                      className="accent-primary"
                      data-testid={`acc-select-${e.id}`}
                      checked={selectedEntryIds.has(e.id)}
                      onChange={() => setSelectedEntryIds(prev => { const n = new Set(prev); n.has(e.id) ? n.delete(e.id) : n.add(e.id); return n; })}
                      onClick={ev => ev.stopPropagation()}
                    />
                    <div className="flex-1 min-w-0 cursor-pointer" onClick={() => openEntry(e)}>
                      <p className={`text-sm font-medium font-mono ${(e.is_reversed || e.reverses) ? 'line-through' : ''}`}>{e.number}</p>
                      <p className="text-xs text-muted-foreground">{e.date} · {e.journal_code} · {e.narration || e.ref || '—'}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold">{fmt(e.total_debit)}</p>
                      {e.is_reversed && <Badge className="text-[10px] bg-slate-200 text-slate-700" title={`Reversed by ${e.reversed_by || ''} on ${e.reversed_at || ''}`}>reversed</Badge>}
                      {e.reverses && <Badge className="text-[10px] bg-slate-200 text-slate-700" title={`Reverses ${e.reverses}`}>reversal</Badge>}
                      <Badge className={`text-[10px] ${STATUS_COLORS[e.status] || ''}`}>{e.status}</Badge>
                      {e.status === 'draft' && <>
                        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => postEntry(e.id)} data-testid={`acc-post-${e.id}`}><Check size={12} className="mr-1" />Post</Button>
                        <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive" onClick={() => cancelEntry(e.id)} data-testid={`acc-cancel-${e.id}`}><X size={12} /></Button>
                      </>}
                      {e.status === 'posted' && !e.is_reversed && !e.reverses && (
                        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => reverseEntry(e.id)} data-testid={`acc-reverse-${e.id}`}><RotateCcw size={12} className="mr-1" />Reverse</Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* CASH ACCOUNTS — real-world wallets/tills, assignable to users */}
        <TabsContent value="cash-accounts" className="space-y-3">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div>
              <p className="text-xs text-muted-foreground">Actual cash / bank / mobile-money balances. Admin assigns users so they can only spend from accounts they&apos;re accountable for.</p>
            </div>
            {isFinanceAdmin && (
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => setShowTransferForm(true)} data-testid="cha-new-transfer-btn"><RotateCcw size={12} className="mr-1" /> Transfer</Button>
                <Button size="sm" onClick={openNewChartAccount} data-testid="cha-new-account-btn"><Plus size={14} className="mr-1" /> New Cash Account</Button>
              </div>
            )}
          </div>
          {chartAccountsLoading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">{[1,2,3].map(i => <div key={i} className="h-32 bg-muted animate-pulse rounded-xl" />)}</div>
          ) : chartAccounts.length === 0 ? (
            <EmptyState icon={Wallet} title="No cash accounts yet" description={isFinanceAdmin ? "Create your first cash / bank / mobile-money account. Then assign it to the users who should spend from it." : "You haven't been assigned to any cash accounts yet. Ask an admin to assign one."} />
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {chartAccounts.map(a => (
                <Card key={a.id} className={`rounded-xl ${a.active === false ? 'opacity-50' : ''}`} data-testid={`cha-card-${a.id}`}>
                  <CardContent className="p-4 space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-sm truncate" data-testid={`cha-name-${a.id}`}>{a.name}</p>
                        <p className="text-[11px] text-muted-foreground uppercase">{a.kind} {a.active === false && '· archived'}</p>
                      </div>
                      <Wallet size={16} className="text-muted-foreground" />
                    </div>
                    <p className="text-2xl font-bold" data-testid={`cha-balance-${a.id}`}>{a.currency} {(a.balance ?? a.starting_balance ?? 0).toLocaleString()}</p>
                    <p className="text-[11px] text-muted-foreground">Starting: {a.currency} {(a.starting_balance || 0).toLocaleString()}</p>
                    <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                      <Users size={11} /> {(a.assigned_user_ids || []).length} assigned
                    </div>
                    <div className="flex gap-1 flex-wrap pt-1">
                      <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => openTxns(a)} data-testid={`cha-txns-${a.id}`}>Ledger</Button>
                      {isFinanceAdmin && <>
                        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => { setChartAccountForm({ id: a.id, name: a.name, kind: a.kind, currency: a.currency, starting_balance: a.starting_balance, location_id: a.location_id || '', assigned_user_ids: a.assigned_user_ids || [], notes: a.notes || '' }); setShowChartAccountForm(true); }} data-testid={`cha-edit-${a.id}`}>Edit</Button>
                        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => openAssignees(a)} data-testid={`cha-assign-${a.id}`}>Assign Users</Button>
                        <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive" onClick={() => removeChartAccount(a)} data-testid={`cha-delete-${a.id}`}><Trash2 size={12} /></Button>
                      </>}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* ACCOUNTS */}
        <TabsContent value="accounts" className="space-y-3">
          <div className="flex justify-end">
            <Button size="sm" onClick={openNewAccountForm} data-testid="acc-new-account-btn"><Plus size={14} className="mr-1" /> New Account</Button>
          </div>
          {accounts.length === 0 ? (
            <EmptyState
              icon={BookOpen}
              title="No accounts yet"
              description='Click "Seed Default CoA" to bootstrap a standard chart of accounts, or create one manually.'
              action={{ label: 'New account', onClick: openNewAccountForm, testid: 'acc-empty-new-account-btn' }}
              testid="acc-accounts-empty"
            />
          ) : (
            <div className="space-y-1.5">
              {accounts.map(a => (
                <Card key={a.id} className={`rounded-xl hover:border-primary/40 ${a.active === false ? 'opacity-50' : ''}`} data-testid={`acc-account-${a.id}`}>
                  <CardContent className="p-3 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 flex-1 min-w-0 cursor-pointer" onClick={() => openLedger(a)}>
                      <span className="font-mono text-sm font-semibold text-muted-foreground w-12">{a.code}</span>
                      <span className="text-sm font-medium truncate">{a.name}{a.active === false && ' (inactive)'}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className={`text-[10px] ${CATEGORY_COLORS[a.category] || ''} capitalize`}>{a.category}</Badge>
                      <Badge variant="secondary" className="text-[10px]">{a.type_label}</Badge>
                      {isFinanceAdmin && (
                        <>
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={(e) => { e.stopPropagation(); openEditAccount(a); }} data-testid={`acc-edit-account-${a.id}`} title="Edit"><FileText size={12} /></Button>
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" onClick={(e) => { e.stopPropagation(); deleteAccount(a); }} data-testid={`acc-delete-account-${a.id}`} title="Delete"><Trash2 size={12} /></Button>
                        </>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* JOURNALS */}
        <TabsContent value="journals" className="space-y-3">
          <div className="flex justify-end">
            <Button size="sm" disabled={accounts.length === 0} onClick={() => { setJournalForm({ id: '', code: '', name: '', kind: 'miscellaneous', default_debit_account_id: '', default_credit_account_id: '' }); setShowJournalForm(true); }} data-testid="acc-new-journal-btn"><Plus size={14} className="mr-1" /> New Journal</Button>
          </div>
          {journals.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">No journals. Create one to start posting entries.</p> : (
            <div className="space-y-1.5">
              {journals.map(j => (
                <Card key={j.id} className="rounded-xl" data-testid={`acc-journal-${j.id}`}>
                  <CardContent className="p-3 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium"><span className="font-mono text-muted-foreground mr-2">{j.code}</span>{j.name}</p>
                      <p className="text-xs text-muted-foreground">{j.kind}</p>
                    </div>
                    {isFinanceAdmin && (
                      <div className="flex items-center gap-1">
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => openEditJournal(j)} data-testid={`acc-edit-journal-${j.id}`} title="Edit"><FileText size={12} /></Button>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" onClick={() => deleteJournal(j)} data-testid={`acc-delete-journal-${j.id}`} title="Delete"><Trash2 size={12} /></Button>
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* TAXES */}
        <TabsContent value="taxes" className="space-y-3">
          <div className="flex justify-end">
            <Button size="sm" onClick={() => { setTaxForm({ id: '', name: '', rate: '', kind: 'sales', inclusive: false, account_id: '' }); setShowTaxForm(true); }} data-testid="acc-new-tax-btn"><Plus size={14} className="mr-1" /> New Tax</Button>
          </div>
          {taxes.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">No tax codes defined.</p> : (
            <div className="space-y-1.5">
              {taxes.map(t => (
                <Card key={t.id} className="rounded-xl" data-testid={`acc-tax-${t.id}`}>
                  <CardContent className="p-3 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">{t.name}</p>
                      <p className="text-xs text-muted-foreground">{t.kind} · {t.inclusive ? 'inclusive' : 'exclusive'}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <p className="text-lg font-bold">{t.rate}%</p>
                      {isFinanceAdmin && (
                        <>
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => openEditTax(t)} data-testid={`acc-edit-tax-${t.id}`} title="Edit"><FileText size={12} /></Button>
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" onClick={() => deleteTax(t)} data-testid={`acc-delete-tax-${t.id}`} title="Delete"><Trash2 size={12} /></Button>
                        </>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* FISCAL PERIODS */}
        <TabsContent value="fiscal" className="space-y-3">
          <div className="flex justify-end">
            <Button size="sm" onClick={() => setShowFiscalForm(true)} data-testid="acc-new-fiscal-btn"><Plus size={14} className="mr-1" /> New Period</Button>
          </div>
          {fiscalPeriods.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">No fiscal periods defined.</p> : (
            <div className="space-y-1.5">
              {fiscalPeriods.map(fp => (
                <Card key={fp.id} className="rounded-xl" data-testid={`acc-fiscal-${fp.id}`}>
                  <CardContent className="p-3 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">{fp.name}</p>
                      <p className="text-xs text-muted-foreground">{fp.start_date} → {fp.end_date}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge className={`capitalize text-[10px] ${fp.status === 'open' ? 'bg-green-100 text-green-700' : fp.status === 'closed' ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'}`}>{fp.status}</Badge>
                      <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => cycleFiscalStatus(fp)} data-testid={`acc-fp-cycle-${fp.id}`}>→ {fp.status === 'open' ? 'closed' : fp.status === 'closed' ? 'locked' : 'open'}</Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* REPORTS */}
        <TabsContent value="reports" className="space-y-4" data-testid="acc-reports-tab">
          {tb && (
            <Card className="rounded-xl">
              <CardHeader><CardTitle className="text-base">Trial Balance <span className="text-xs text-muted-foreground font-normal">({currentCurrency})</span></CardTitle></CardHeader>
              <CardContent className="text-xs space-y-1">
                <table className="w-full">
                  <thead><tr className="border-b text-muted-foreground"><th className="text-left py-1">Code</th><th className="text-left">Account</th><th className="text-right">Debit</th><th className="text-right">Credit</th><th className="text-right">Balance</th></tr></thead>
                  <tbody>{tb.rows.map(r => (
                    <tr key={r.account_id} className="border-b">
                      <td className="py-1 font-mono">{r.code}</td>
                      <td>{r.name}</td>
                      <td className="text-right">{fmt(r.debit)}</td>
                      <td className="text-right">{fmt(r.credit)}</td>
                      <td className="text-right font-semibold">{fmt(r.balance)}</td>
                    </tr>
                  ))}</tbody>
                  <tfoot><tr className="font-bold border-t-2"><td colSpan={2} className="py-2">TOTALS</td><td className="text-right">{fmt(tb.totals.debit)}</td><td className="text-right">{fmt(tb.totals.credit)}</td><td></td></tr></tfoot>
                </table>
              </CardContent>
            </Card>
          )}
          {bs && (
            <Card className="rounded-xl">
              <CardHeader><CardTitle className="text-base">Balance Sheet <span className="text-xs text-muted-foreground font-normal">({currentCurrency})</span> {bs.totals.balanced ? '✓' : '⚠'}</CardTitle></CardHeader>
              <CardContent className="text-xs grid grid-cols-1 md:grid-cols-3 gap-3">
                <div><h4 className="font-semibold mb-1 text-blue-700">Assets · {fmt(bs.totals.assets)}</h4>{bs.assets.map(a => <p key={a.account_id} className="text-[11px]">{a.code} {a.name}: {fmt(a.balance)}</p>)}</div>
                <div><h4 className="font-semibold mb-1 text-amber-700">Liabilities · {fmt(bs.totals.liabilities)}</h4>{bs.liabilities.map(a => <p key={a.account_id} className="text-[11px]">{a.code} {a.name}: {fmt(-a.balance)}</p>)}</div>
                <div><h4 className="font-semibold mb-1 text-purple-700">Equity · {fmt(bs.totals.equity)}</h4>{bs.equity.map(a => <p key={a.account_id} className="text-[11px]">{a.code} {a.name}: {fmt(-a.balance)}</p>)}<p className="text-[11px] mt-1 italic">+ Retained net profit: {fmt(bs.totals.retained_net_profit)}</p></div>
              </CardContent>
            </Card>
          )}
          <AdvancedReports locationId={locationFilter} currency={currentCurrency} />
        </TabsContent>
      </Tabs>

      {/* New Account Dialog */}
      <Dialog open={showAccountForm} onOpenChange={setShowAccountForm}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{accountForm.id ? 'Edit' : 'New'} Account</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Code *</Label><Input value={accountForm.code} onChange={e => setAccountForm({...accountForm, code: e.target.value})} placeholder="e.g. 1200" data-testid="acc-form-code" /></div>
              <div className="space-y-1.5"><Label className="text-xs">Currency</Label>
                <Select value={accountForm.currency} onValueChange={v => setAccountForm({...accountForm, currency: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{['UGX','USD','KES','EUR','GBP','THB','HTG'].map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Name *</Label><Input value={accountForm.name} onChange={e => setAccountForm({...accountForm, name: e.target.value})} data-testid="acc-form-name" /></div>
            <div className="space-y-1.5"><Label className="text-xs">Type *</Label>
              <Select value={accountForm.type} onValueChange={v => setAccountForm({...accountForm, type: v})}>
                <SelectTrigger data-testid="acc-form-type"><SelectValue /></SelectTrigger>
                <SelectContent>{accountTypes.map(t => <SelectItem key={t.id} value={t.id}>{t.label} ({t.category})</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowAccountForm(false)}>Cancel</Button>
              <Button className="flex-1" data-testid="acc-form-submit" disabled={!accountForm.code || !accountForm.name} onClick={createAccount}>{accountForm.id ? 'Save' : 'Create'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* New Journal Dialog */}
      <Dialog open={showJournalForm} onOpenChange={setShowJournalForm}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{journalForm.id ? 'Edit' : 'New'} Journal</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Code *</Label><Input value={journalForm.code} onChange={e => setJournalForm({...journalForm, code: e.target.value.toUpperCase()})} placeholder="SAL" data-testid="jrn-form-code" /></div>
              <div className="space-y-1.5"><Label className="text-xs">Kind</Label>
                <Select value={journalForm.kind} onValueChange={v => setJournalForm({...journalForm, kind: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{['sales','purchases','bank','cash','miscellaneous'].map(k => <SelectItem key={k} value={k} className="capitalize">{k}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Name *</Label><Input value={journalForm.name} onChange={e => setJournalForm({...journalForm, name: e.target.value})} placeholder="Sales Journal" data-testid="jrn-form-name" /></div>
            <div className="space-y-1.5"><Label className="text-xs">Default Debit Account (optional)</Label>
              <Select value={journalForm.default_debit_account_id || 'none'} onValueChange={v => setJournalForm({...journalForm, default_debit_account_id: v === 'none' ? '' : v})}>
                <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                <SelectContent><SelectItem value="none">None</SelectItem>{accounts.map(a => <SelectItem key={a.id} value={a.id}>{a.code} {a.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Default Credit Account (optional)</Label>
              <Select value={journalForm.default_credit_account_id || 'none'} onValueChange={v => setJournalForm({...journalForm, default_credit_account_id: v === 'none' ? '' : v})}>
                <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                <SelectContent><SelectItem value="none">None</SelectItem>{accounts.map(a => <SelectItem key={a.id} value={a.id}>{a.code} {a.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowJournalForm(false)}>Cancel</Button>
              <Button className="flex-1" disabled={!journalForm.code || !journalForm.name} onClick={createJournal} data-testid="jrn-form-submit">{journalForm.id ? 'Save' : 'Create'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* New Entry Dialog */}
      <Dialog open={showEntryForm} onOpenChange={setShowEntryForm}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New Journal Entry</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Journal *</Label>
                <Select value={entryForm.journal_id} onValueChange={v => {
                  const j = journals.find(x => x.id === v);
                  const lines = entryForm.lines.length === 2 && !entryForm.lines.some(l => l.account_id) ? [
                    { account_id: j?.default_debit_account_id || '', debit: '', credit: '', description: '' },
                    { account_id: j?.default_credit_account_id || '', debit: '', credit: '', description: '' },
                  ] : entryForm.lines;
                  setEntryForm({...entryForm, journal_id: v, lines});
                }}>
                  <SelectTrigger data-testid="entry-form-journal"><SelectValue placeholder="Pick journal" /></SelectTrigger>
                  <SelectContent>{journals.map(j => <SelectItem key={j.id} value={j.id}>{j.code} {j.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label className="text-xs">Date *</Label><Input type="date" value={entryForm.date} onChange={e => setEntryForm({...entryForm, date: e.target.value})} data-testid="entry-form-date" /></div>
              <div className="space-y-1.5"><Label className="text-xs">Reference</Label><Input value={entryForm.ref} onChange={e => setEntryForm({...entryForm, ref: e.target.value})} placeholder="INV-001" /></div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Narration</Label><Textarea rows={2} value={entryForm.narration} onChange={e => setEntryForm({...entryForm, narration: e.target.value})} /></div>
            <div className="border rounded-lg p-2 space-y-1.5">
              <div className="grid grid-cols-12 gap-1.5 text-[10px] uppercase text-muted-foreground font-semibold px-1">
                <div className="col-span-5">Account</div>
                <div className="col-span-2 text-right">Debit</div>
                <div className="col-span-2 text-right">Credit</div>
                <div className="col-span-2">Description</div>
                <div className="col-span-1"></div>
              </div>
              {entryForm.lines.map((ln, idx) => (
                <div key={idx} className="grid grid-cols-12 gap-1.5 items-center" data-testid={`entry-line-${idx}`}>
                  <div className="col-span-5">
                    <Select value={ln.account_id} onValueChange={v => updateLine(idx, 'account_id', v)}>
                      <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="Pick account" /></SelectTrigger>
                      <SelectContent>{accounts.map(a => <SelectItem key={a.id} value={a.id}>{a.code} {a.name}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <Input className="col-span-2 h-8 text-xs text-right" type="number" step="0.01" value={ln.debit} onChange={e => updateLine(idx, 'debit', e.target.value)} placeholder="0.00" />
                  <Input className="col-span-2 h-8 text-xs text-right" type="number" step="0.01" value={ln.credit} onChange={e => updateLine(idx, 'credit', e.target.value)} placeholder="0.00" />
                  <Input className="col-span-2 h-8 text-xs" value={ln.description} onChange={e => updateLine(idx, 'description', e.target.value)} placeholder="Detail" />
                  <Button size="sm" variant="ghost" className="col-span-1 h-8 text-destructive" disabled={entryForm.lines.length <= 2} onClick={() => removeLine(idx)}>×</Button>
                </div>
              ))}
              <Button size="sm" variant="outline" className="w-full h-8 text-xs" onClick={addLine}><Plus size={12} className="mr-1" />Add Line</Button>
              <div className="grid grid-cols-12 gap-1.5 text-xs font-semibold pt-2 border-t">
                <div className="col-span-5 text-right">Totals</div>
                <div className="col-span-2 text-right">{fmt(lineTotals().debit)}</div>
                <div className="col-span-2 text-right">{fmt(lineTotals().credit)}</div>
                <div className="col-span-3">{lineTotals().balanced ? <span className="text-green-600">✓ Balanced</span> : <span className="text-red-600">⚠ Unbalanced</span>}</div>
              </div>
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowEntryForm(false)}>Cancel</Button>
              <Button className="flex-1" disabled={!entryForm.journal_id || !lineTotals().balanced} onClick={submitEntry} data-testid="entry-form-submit">Save as Draft</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* New Tax Dialog */}
      <Dialog open={showTaxForm} onOpenChange={setShowTaxForm}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New Tax Code</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Name *</Label><Input value={taxForm.name} onChange={e => setTaxForm({...taxForm, name: e.target.value})} placeholder="VAT 18%" /></div>
              <div className="space-y-1.5"><Label className="text-xs">Rate (%) *</Label><Input type="number" step="0.01" value={taxForm.rate} onChange={e => setTaxForm({...taxForm, rate: e.target.value})} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Kind</Label>
                <Select value={taxForm.kind} onValueChange={v => setTaxForm({...taxForm, kind: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="sales">Sales (output)</SelectItem><SelectItem value="purchase">Purchase (input)</SelectItem></SelectContent></Select>
              </div>
              <div className="space-y-1.5"><Label className="text-xs">Inclusive?</Label>
                <Select value={taxForm.inclusive ? 'yes' : 'no'} onValueChange={v => setTaxForm({...taxForm, inclusive: v === 'yes'})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="no">Exclusive</SelectItem><SelectItem value="yes">Inclusive</SelectItem></SelectContent></Select>
              </div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Tax Account</Label>
              <Select value={taxForm.account_id || 'none'} onValueChange={v => setTaxForm({...taxForm, account_id: v === 'none' ? '' : v})}><SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                <SelectContent><SelectItem value="none">None</SelectItem>{accounts.filter(a => a.type === 'liability_tax').map(a => <SelectItem key={a.id} value={a.id}>{a.code} {a.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowTaxForm(false)}>Cancel</Button>
              <Button className="flex-1" disabled={!taxForm.name || !taxForm.rate} onClick={createTax}>{taxForm.id ? 'Save' : 'Create'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* New Fiscal Period Dialog */}
      <Dialog open={showFiscalForm} onOpenChange={setShowFiscalForm}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New Fiscal Period</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label className="text-xs">Name *</Label><Input value={fiscalForm.name} onChange={e => setFiscalForm({...fiscalForm, name: e.target.value})} placeholder="FY 2026" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Start *</Label><Input type="date" value={fiscalForm.start_date} onChange={e => setFiscalForm({...fiscalForm, start_date: e.target.value})} /></div>
              <div className="space-y-1.5"><Label className="text-xs">End *</Label><Input type="date" value={fiscalForm.end_date} onChange={e => setFiscalForm({...fiscalForm, end_date: e.target.value})} /></div>
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowFiscalForm(false)}>Cancel</Button>
              <Button className="flex-1" disabled={!fiscalForm.name || !fiscalForm.start_date || !fiscalForm.end_date} onClick={createFiscal}>Create</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Entry Detail Dialog */}
      <Dialog open={!!viewEntry} onOpenChange={(o) => { if (!o) setViewEntry(null); }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>{viewEntry?.number}</DialogTitle></DialogHeader>
          {viewEntry && (
            <div className="space-y-2 text-sm mt-2">
              <p className="text-xs text-muted-foreground">{viewEntry.date} · {viewEntry.journal_code} · <Badge className={`ml-1 text-[10px] ${STATUS_COLORS[viewEntry.status] || ''}`}>{viewEntry.status}</Badge></p>
              {viewEntry.narration && <p className="text-xs italic">{viewEntry.narration}</p>}
              <table className="w-full text-xs mt-3">
                <thead><tr className="border-b text-muted-foreground"><th className="text-left">Account</th><th className="text-right">Debit</th><th className="text-right">Credit</th><th className="text-left">Desc</th></tr></thead>
                <tbody>{viewEntry.lines.map(ln => (
                  <tr key={ln.id} className="border-b">
                    <td className="py-1"><span className="font-mono">{ln.account_code}</span> {ln.account_name}</td>
                    <td className="text-right">{fmt(ln.debit)}</td>
                    <td className="text-right">{fmt(ln.credit)}</td>
                    <td>{ln.description}</td>
                  </tr>
                ))}</tbody>
                <tfoot><tr className="font-bold border-t-2"><td className="py-2">Totals</td><td className="text-right">{fmt(viewEntry.total_debit)}</td><td className="text-right">{fmt(viewEntry.total_credit)}</td><td></td></tr></tfoot>
              </table>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Ledger Dialog */}
      <Dialog open={!!viewLedger} onOpenChange={(o) => { if (!o) setViewLedger(null); }}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{viewLedger?.account?.code} — {viewLedger?.account?.name}</DialogTitle></DialogHeader>
          {viewLedger && (
            <div className="space-y-2 text-xs mt-2">
              <p className="text-sm">Ending balance: <span className="font-bold">{fmt(viewLedger.ending_balance)}</span></p>
              {viewLedger.lines.length === 0 ? (
                <EmptyState compact icon={Scale} title="No postings yet" description="Once journal entries reference this account, postings will appear here." testid="acc-ledger-empty" />
              ) : (
                <table className="w-full">
                  <thead><tr className="border-b text-muted-foreground"><th className="text-left">Date</th><th className="text-left">Entry</th><th className="text-left">Narration</th><th className="text-right">Debit</th><th className="text-right">Credit</th><th className="text-right">Running</th></tr></thead>
                  <tbody>{viewLedger.lines.map(ln => (
                    <tr key={ln.id} className="border-b">
                      <td className="py-1">{ln.date}</td>
                      <td className="font-mono">{ln.entry_number}</td>
                      <td>{ln.narration || ln.ref || '—'}</td>
                      <td className="text-right">{fmt(ln.debit)}</td>
                      <td className="text-right">{fmt(ln.credit)}</td>
                      <td className="text-right font-semibold">{fmt(ln.running_balance)}</td>
                    </tr>
                  ))}</tbody>
                </table>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* CHART ACCOUNT CREATE/EDIT DIALOG */}
      <Dialog open={showChartAccountForm} onOpenChange={setShowChartAccountForm}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{chartAccountForm.id ? 'Edit' : 'New'} Cash Account</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5"><Label className="text-xs">Name *</Label>
              <Input value={chartAccountForm.name} onChange={e => setChartAccountForm({...chartAccountForm, name: e.target.value})} placeholder="e.g. Uganda Cash Drawer" data-testid="cha-form-name" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5"><Label className="text-xs">Kind</Label>
                <Select value={chartAccountForm.kind} onValueChange={v => setChartAccountForm({...chartAccountForm, kind: v})}>
                  <SelectTrigger data-testid="cha-form-kind"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Cash</SelectItem>
                    <SelectItem value="petty_cash">Petty Cash</SelectItem>
                    <SelectItem value="bank">Bank</SelectItem>
                    <SelectItem value="mobile_money">Mobile Money</SelectItem>
                    <SelectItem value="credit">Credit</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label className="text-xs">Currency</Label>
                <Input value={chartAccountForm.currency} onChange={e => setChartAccountForm({...chartAccountForm, currency: e.target.value.toUpperCase()})} placeholder="UGX" />
              </div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Starting Balance</Label>
              <Input type="number" step="0.01" value={chartAccountForm.starting_balance} onChange={e => setChartAccountForm({...chartAccountForm, starting_balance: e.target.value})} placeholder="0" data-testid="cha-form-starting" />
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Location</Label>
              <Select value={chartAccountForm.location_id || '_none'} onValueChange={v => setChartAccountForm({...chartAccountForm, location_id: v === '_none' ? '' : v})}>
                <SelectTrigger className="h-9"><SelectValue placeholder="Org-wide" /></SelectTrigger>
                <SelectContent><SelectItem value="_none">Org-wide</SelectItem>{allLocations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Notes</Label>
              <Textarea rows={2} value={chartAccountForm.notes} onChange={e => setChartAccountForm({...chartAccountForm, notes: e.target.value})} />
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowChartAccountForm(false)}>Cancel</Button>
              <Button className="flex-1" onClick={saveChartAccount} data-testid="cha-form-save">Save</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* ASSIGNEES DIALOG */}
      <Dialog open={!!showAssignees} onOpenChange={(o) => { if (!o) setShowAssignees(null); }}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Assign users · {showAssignees?.name}</DialogTitle></DialogHeader>
          <p className="text-xs text-muted-foreground">Only assigned users (plus admins) can spend from this account when entering expenses or donations.</p>
          <div className="space-y-1 max-h-96 overflow-y-auto">
            {allUsers.length === 0 && <p className="text-xs text-muted-foreground py-4">Loading users…</p>}
            {allUsers.map(u => {
              const on = assigneePicks.includes(u.id);
              return (
                <label key={u.id} className={`flex items-center gap-2 p-2 rounded cursor-pointer border ${on ? 'border-primary bg-primary/5' : 'border-transparent hover:bg-accent/40'}`} data-testid={`cha-assign-row-${u.id}`}>
                  <input type="checkbox" className="accent-primary" checked={on} onChange={() => setAssigneePicks(prev => on ? prev.filter(x => x !== u.id) : [...prev, u.id])} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{u.name || u.email}</p>
                    <p className="text-[11px] text-muted-foreground truncate">{u.role} · {u.email}</p>
                  </div>
                </label>
              );
            })}
          </div>
          <div className="flex gap-2 pt-2">
            <Button variant="outline" className="flex-1" onClick={() => setShowAssignees(null)}>Cancel</Button>
            <Button className="flex-1" onClick={saveAssignees} data-testid="cha-assign-save">Save ({assigneePicks.length})</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* ACCOUNT TRANSACTIONS / LEDGER */}
      <Dialog open={!!viewAccountTxns} onOpenChange={(o) => { if (!o) setViewAccountTxns(null); }}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Ledger · {viewAccountTxns?.account?.name}</DialogTitle></DialogHeader>
          {viewAccountTxns && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
                <div className="p-2 border rounded"><p className="text-muted-foreground">Balance</p><p className="text-xl font-bold" data-testid="cha-ledger-balance">{viewAccountTxns.account.currency} {(viewAccountTxns.balance || 0).toLocaleString()}</p></div>
                <div className="p-2 border rounded"><p className="text-muted-foreground">Starting</p><p className="text-lg">{viewAccountTxns.account.currency} {(viewAccountTxns.starting_balance || 0).toLocaleString()}</p></div>
                <div className="p-2 border rounded"><p className="text-muted-foreground">Txns</p><p className="text-lg">{viewAccountTxns.transactions?.length || 0}</p></div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead><tr className="border-b text-left text-muted-foreground"><th className="py-2">Date</th><th>Type</th><th>Party</th><th className="text-right">Amount</th><th>Notes</th></tr></thead>
                  <tbody className="divide-y">
                    {(viewAccountTxns.transactions || []).map(t => (
                      <tr key={t.id} className="hover:bg-accent/20">
                        <td className="py-1.5">{t.date}</td>
                        <td><Badge className="text-[10px] capitalize">{t.type}</Badge></td>
                        <td className="max-w-[140px] truncate">{t.party}</td>
                        <td className={`text-right font-mono ${t.direction === 'in' ? 'text-green-700' : 'text-red-700'}`}>{t.direction === 'in' ? '+' : '-'}{t.currency} {(t.amount || 0).toLocaleString()}</td>
                        <td className="max-w-[160px] truncate text-muted-foreground">{t.notes || t.ref}</td>
                      </tr>
                    ))}
                    {(viewAccountTxns.transactions || []).length === 0 && <tr><td colSpan={5} className="py-6 text-center text-muted-foreground">No transactions yet.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* CHART TRANSFER DIALOG */}
      <Dialog open={showTransferForm} onOpenChange={setShowTransferForm}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Transfer between Cash Accounts</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5"><Label className="text-xs">From *</Label>
              <Select value={transferForm.from_account_id || '_none'} onValueChange={v => setTransferForm({...transferForm, from_account_id: v === '_none' ? '' : v})}>
                <SelectTrigger data-testid="cha-transfer-from"><SelectValue placeholder="Source account" /></SelectTrigger>
                <SelectContent><SelectItem value="_none">—</SelectItem>{chartAccounts.map(a => <SelectItem key={a.id} value={a.id}>{a.name} · {a.currency} {(a.balance || 0).toLocaleString()}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">To *</Label>
              <Select value={transferForm.to_account_id || '_none'} onValueChange={v => setTransferForm({...transferForm, to_account_id: v === '_none' ? '' : v})}>
                <SelectTrigger data-testid="cha-transfer-to"><SelectValue placeholder="Destination account" /></SelectTrigger>
                <SelectContent><SelectItem value="_none">—</SelectItem>{chartAccounts.filter(a => a.id !== transferForm.from_account_id).map(a => <SelectItem key={a.id} value={a.id}>{a.name} · {a.currency} {(a.balance || 0).toLocaleString()}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Amount *</Label>
              <Input type="number" step="0.01" value={transferForm.amount} onChange={e => setTransferForm({...transferForm, amount: e.target.value})} placeholder="0" data-testid="cha-transfer-amount" />
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Notes</Label>
              <Textarea rows={2} value={transferForm.notes} onChange={e => setTransferForm({...transferForm, notes: e.target.value})} />
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowTransferForm(false)}>Cancel</Button>
              <Button className="flex-1" onClick={submitTransfer} disabled={!transferForm.from_account_id || !transferForm.to_account_id || !transferForm.amount} data-testid="cha-transfer-save">Transfer</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}


// ============== ADVANCED REPORTS (Phase D) ==============
function AdvancedReports({ locationId, currency }) {
  const [activeReport, setActiveReport] = useState(null);  // 'cash_flow' | 'ar' | 'ap'
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [vatRange, setVatRange] = useState({ from: '', to: '' });

  const fmt = (n) => (Number(n) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const loadReport = async (which) => {
    setLoading(true); setActiveReport(which); setData(null);
    try {
      let path;
      if (which === 'cash_flow') path = '/accounting/reports/cash-flow';
      else if (which === 'ar') path = '/accounting/reports/ar-aging';
      else if (which === 'ap') path = '/accounting/reports/ap-aging';
      const r = await api.get(path, { params: { location_id: locationId } });
      setData(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed to load report'); }
    finally { setLoading(false); }
  };

  const downloadVatExport = async () => {
    if (!vatRange.from || !vatRange.to) { toast.error('Pick a date range'); return; }
    try {
      const r = await api.get('/accounting/reports/uganda-vat-export', {
        params: { date_from: vatRange.from, date_to: vatRange.to, location_id: locationId },
        responseType: 'blob',
      });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url; a.download = `uganda-vat-${vatRange.from}-to-${vatRange.to}.csv`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success('Uganda VAT CSV downloaded');
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  return (
    <div className="space-y-4" data-testid="acc-advanced-reports">
      <h3 className="text-sm font-semibold uppercase text-muted-foreground border-t pt-4">Phase D — Advanced Reports</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <Card className="rounded-xl cursor-pointer hover:border-primary/40" onClick={() => loadReport('cash_flow')} data-testid="acc-rep-cf-btn">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-1"><TrendingUp size={14} className="text-blue-600" /><p className="text-xs uppercase text-muted-foreground">Cash Flow Statement</p></div>
            <p className="text-xs text-muted-foreground">Operating / Investing / Financing classification</p>
          </CardContent>
        </Card>
        <Card className="rounded-xl cursor-pointer hover:border-primary/40" onClick={() => loadReport('ar')} data-testid="acc-rep-ar-btn">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-1"><Scale size={14} className="text-amber-600" /><p className="text-xs uppercase text-muted-foreground">AR Aging</p></div>
            <p className="text-xs text-muted-foreground">Customer outstanding by bucket (0-30 / 31-60 / 61-90 / 90+)</p>
          </CardContent>
        </Card>
        <Card className="rounded-xl cursor-pointer hover:border-primary/40" onClick={() => loadReport('ap')} data-testid="acc-rep-ap-btn">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-1"><Scale size={14} className="text-red-600" /><p className="text-xs uppercase text-muted-foreground">AP Aging</p></div>
            <p className="text-xs text-muted-foreground">Vendor bills outstanding by bucket</p>
          </CardContent>
        </Card>
        <Card className="rounded-xl" data-testid="acc-rep-vat-card">
          <CardContent className="p-4 space-y-2">
            <div className="flex items-center gap-2"><FileText size={14} className="text-emerald-600" /><p className="text-xs uppercase text-muted-foreground">Uganda VAT / EFRIS</p></div>
            <div className="grid grid-cols-2 gap-1.5">
              <Input type="date" className="h-8 text-xs" value={vatRange.from} onChange={e => setVatRange({ ...vatRange, from: e.target.value })} placeholder="From" />
              <Input type="date" className="h-8 text-xs" value={vatRange.to} onChange={e => setVatRange({ ...vatRange, to: e.target.value })} placeholder="To" />
            </div>
            <Button size="sm" className="w-full h-8 text-xs" onClick={downloadVatExport} disabled={!vatRange.from || !vatRange.to} data-testid="acc-rep-vat-download"><FileText size={11} className="mr-1" />Download CSV</Button>
          </CardContent>
        </Card>
      </div>

      {loading && <div className="space-y-2">{[1, 2].map(i => <div key={i} className="h-16 bg-muted animate-pulse rounded" />)}</div>}

      {!loading && activeReport === 'cash_flow' && data && (
        <Card className="rounded-xl">
          <CardHeader><CardTitle className="text-base">Cash Flow Statement <span className="text-xs text-muted-foreground font-normal">({currency})</span></CardTitle></CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            <div>
              <h4 className="font-semibold mb-1 text-blue-700">Operating · {fmt(data.totals.operating)}</h4>
              {data.operating.map((r, i) => <p key={i} className="text-[11px] flex justify-between"><span>{r.account}</span><span className={r.amount < 0 ? 'text-red-600' : ''}>{fmt(r.amount)}</span></p>)}
            </div>
            <div>
              <h4 className="font-semibold mb-1 text-purple-700">Investing · {fmt(data.totals.investing)}</h4>
              {data.investing.length === 0 && <p className="text-[11px] text-muted-foreground">—</p>}
              {data.investing.map((r, i) => <p key={i} className="text-[11px] flex justify-between"><span>{r.account}</span><span className={r.amount < 0 ? 'text-red-600' : ''}>{fmt(r.amount)}</span></p>)}
            </div>
            <div>
              <h4 className="font-semibold mb-1 text-emerald-700">Financing · {fmt(data.totals.financing)}</h4>
              {data.financing.length === 0 && <p className="text-[11px] text-muted-foreground">—</p>}
              {data.financing.map((r, i) => <p key={i} className="text-[11px] flex justify-between"><span>{r.account}</span><span className={r.amount < 0 ? 'text-red-600' : ''}>{fmt(r.amount)}</span></p>)}
            </div>
            <div className="md:col-span-3 border-t pt-2 text-right text-base font-bold">
              Net change in cash: <span className={data.totals.net_change < 0 ? 'text-red-700' : 'text-emerald-700'}>{fmt(data.totals.net_change)}</span>
            </div>
          </CardContent>
        </Card>
      )}

      {!loading && (activeReport === 'ar' || activeReport === 'ap') && data && (
        <Card className="rounded-xl">
          <CardHeader><CardTitle className="text-base">{activeReport === 'ar' ? 'Accounts Receivable Aging' : 'Accounts Payable Aging'} <span className="text-xs text-muted-foreground font-normal">({currency})</span></CardTitle></CardHeader>
          <CardContent className="text-xs">
            {data.rows.length === 0 ? <p className="text-muted-foreground text-center py-4">No outstanding {activeReport === 'ar' ? 'receivables' : 'payables'}.</p> : (
              <table className="w-full">
                <thead><tr className="border-b text-muted-foreground"><th className="text-left">{activeReport === 'ar' ? 'Customer' : 'Vendor'}</th><th className="text-right">0-30</th><th className="text-right">31-60</th><th className="text-right">61-90</th><th className="text-right">90+</th><th className="text-right">Total</th></tr></thead>
                <tbody>{data.rows.map((r, i) => (
                  <tr key={i} className="border-b">
                    <td className="py-1">{r.customer_name || r.vendor_name}</td>
                    <td className="text-right">{fmt(r['0-30'])}</td>
                    <td className="text-right">{fmt(r['31-60'])}</td>
                    <td className="text-right">{fmt(r['61-90'])}</td>
                    <td className={`text-right ${r['90+'] > 0 ? 'text-red-700 font-semibold' : ''}`}>{fmt(r['90+'])}</td>
                    <td className="text-right font-semibold">{fmt(r.total)}</td>
                  </tr>
                ))}</tbody>
                <tfoot><tr className="font-bold border-t-2"><td className="py-2">TOTAL</td><td className="text-right">{fmt(data.totals['0-30'])}</td><td className="text-right">{fmt(data.totals['31-60'])}</td><td className="text-right">{fmt(data.totals['61-90'])}</td><td className="text-right text-red-700">{fmt(data.totals['90+'])}</td><td className="text-right">{fmt(data.totals.total)}</td></tr></tfoot>
              </table>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

