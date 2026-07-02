import { secureStorage } from '../services/secureStorage';
import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { DollarSign, TrendingUp, TrendingDown, Wallet, Plus, Download, Upload, RefreshCw, FileSpreadsheet } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { financialApi, financialExtrasApi, exportApi, locationsApi, chartAccountsApi } from '../services/api';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import { BulkActionBar, exportToCSV, SelectCheckbox } from '../components/BulkActions';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import EmptyState from '../components/EmptyState';

const SummaryCard = ({ title, value, sub, icon: Icon, color, loading }) => (
  <Card className="shadow-soft rounded-xl">
    <CardContent className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground mb-1">{title}</p>
          {loading ? <div className="h-7 w-28 bg-muted animate-pulse rounded mt-1" /> : (
            <p className="text-xl font-bold font-heading">{value}</p>
          )}
          {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
        </div>
        <div className={`p-2.5 rounded-lg ${color}`}>
          <Icon size={18} className="text-white" />
        </div>
      </div>
    </CardContent>
  </Card>
);

const typeColors = {
  tithe: 'bg-green-100 text-green-700',
  offering: 'bg-blue-100 text-blue-700',
  donation: 'bg-purple-100 text-purple-700',
  pledge: 'bg-amber-100 text-amber-700',
};
const expenseCategoryColors = {
  salaries: 'bg-red-100 text-red-700',
  utilities: 'bg-orange-100 text-orange-700',
  supplies: 'bg-yellow-100 text-yellow-700',
  maintenance: 'bg-blue-100 text-blue-700',
  programs: 'bg-purple-100 text-purple-700',
  general: 'bg-slate-100 text-slate-700',
};

export default function FinancialPage() {
  const { user } = useAuth();
  const [summary, setSummary] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());  // donations
  const [selectedExpenseIds, setSelectedExpenseIds] = useState(new Set());
  const [selectedBudgetIds, setSelectedBudgetIds] = useState(new Set());
  const [selectedAssetIds, setSelectedAssetIds] = useState(new Set());
  const [donations, setDonations] = useState([]);
  const [expenses, setExpenses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showDonation, setShowDonation] = useState(false);
  const [showExpense, setShowExpense] = useState(false);
  const [saving, setSaving] = useState(false);
  const [cashflowData, setCashflowData] = useState([]);
  const [cashflowMonths, setCashflowMonths] = useState(6);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [locationFilter, setLocationFilter] = useState('');
  const [allLocations, setAllLocations] = useState([]);
  const [showDistribute, setShowDistribute] = useState(false);
  const [distForm, setDistForm] = useState({ from_location_id: '', to_location_id: '', amount: '', currency: 'UGX', notes: '' });
  const [pendingExpenses, setPendingExpenses] = useState([]);
  const [balanceSheet, setBalanceSheet] = useState(null);
  const [bsLoading, setBsLoading] = useState(false);
  const [editEntry, setEditEntry] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [showAssetForm, setShowAssetForm] = useState(false);
  const [assets, setAssets] = useState([]);
  const [assetForm, setAssetForm] = useState({ name: '', value: 0, category: 'equipment', purchase_date: '', depreciation_years: 5 });
  const [showApprovalComment, setShowApprovalComment] = useState(null);
  const [approvalComment, setApprovalComment] = useState('');
  const [subAccounts, setSubAccounts] = useState(null);
  const [transfers, setTransfers] = useState([]);
  const [budgets, setBudgets] = useState([]);
  const [categories, setCategories] = useState([]);
  const [showCategories, setShowCategories] = useState(false);
  const [newCatName, setNewCatName] = useState('');
  const [newCatType, setNewCatType] = useState('both');
  const [subLocations, setSubLocations] = useState([]);
  // Chart accounts (cash/bank/mobile money) — my-scoped list with live balances
  const [myChartAccounts, setMyChartAccounts] = useState([]);
  const [showImportExport, setShowImportExport] = useState(false);
  const [importData, setImportData] = useState('');
  const [importingData, setImportingData] = useState(false);
  // Sheet import (Google Sheet CSV)
  const [sheetCsv, setSheetCsv] = useState('');
  const [sheetType, setSheetType] = useState('expense');
  const [sheetStatus, setSheetStatus] = useState('pending');
  const [sheetImporting, setSheetImporting] = useState(false);
  // Replace prompt() with dialogs
  const [showTransfer, setShowTransfer] = useState(false);
  const [transferForm, setTransferForm] = useState({ from_account_id: '', to_account_id: '', amount: '', currency: 'UGX', notes: '' });
  const [showBudget, setShowBudget] = useState(false);
  const [budgetForm, setBudgetForm] = useState({ department: '', period: new Date().toISOString().slice(0, 7), amount: '', category: 'general' });
  // Rejection dialog state (replaces window.prompt)
  const [rejectingExpense, setRejectingExpense] = useState(null); // holds the expense being rejected
  const [rejectReason, setRejectReason] = useState('');
  const [showRevalue, setShowRevalue] = useState(null); // holds the asset being revalued
  const [revalueForm, setRevalueForm] = useState({ current_value: 0, method: 'appreciation', notes: '' });
  const [showStartingBal, setShowStartingBal] = useState(null); // holds the account
  const [startingBalValue, setStartingBalValue] = useState('');
  const [showAttachReceipt, setShowAttachReceipt] = useState(null); // holds the expense being attached to
  const [attachReceiptUrl, setAttachReceiptUrl] = useState('');
  const today = new Date().toISOString().split('T')[0];

  const isFinanceAdmin = ['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director'].includes(user?.role);

  // Org-default currency: pulled from /api/admin/system-settings/public on mount,
  // falls back to UGX if the endpoint hasn't been configured yet. Lets the
  // financial UI reflect the org's actual home currency without code changes.
  const [orgDefaultCurrency, setOrgDefaultCurrency] = useState('UGX');
  useEffect(() => {
    let alive = true;
    api.get('/admin/system-settings/public')
      .then(r => { if (alive) setOrgDefaultCurrency(r.data?.org?.primary_currency || 'UGX'); })
      .catch(() => { /* keep UGX */ });
    return () => { alive = false; };
  }, []);

  // Currency: prefer the explicitly selected location. With no filter ("All Locations"),
  // default to the org's home currency (configurable from Admin → Integrations).
  const currentCurrency = (locationFilter
    ? allLocations.find(l => l.id === locationFilter)?.currency
    : null
  ) || orgDefaultCurrency;
  const fmt = (n) => `${currentCurrency} ${(n || 0).toLocaleString()}`;
  const [donationForm, setDonationForm] = useState(() => ({ donor_name: '', amount: '', currency: 'UGX', type: 'tithe', date: new Date().toISOString().split('T')[0], notes: '', sublocation_id: '', deposit_to_account_id: '' }));
  const [expenseForm, setExpenseForm] = useState(() => ({
    title: '', amount: '', currency: 'UGX', category: 'general', date: new Date().toISOString().split('T')[0], notes: '', sublocation_id: '',
    vendor: '', receipt_number: '', account: '', department: '', budget_category: '', usd_equivalent: '',
    paid_from_account_id: '',
  }));

  // Default non-admin users to their campus
  useEffect(() => {
    if (!isFinanceAdmin && user?.location_id && !locationFilter) {
      setLocationFilter(user.location_id);
    }
  }, [user, isFinanceAdmin, locationFilter]);

  const fetchAll = async () => {
    setLoading(true);
    try {
      // Promise.allSettled so one denied sub-fetch (e.g. cashflow needs director+
      // but summary only needs manager) doesn't blank the whole page.
      const results = await Promise.allSettled([
        financialApi.summary(locationFilter || undefined),
        financialApi.donations({ limit: 50, date_from: dateFrom || undefined, date_to: dateTo || undefined, location_id: locationFilter || undefined }),
        financialApi.expenses({ limit: 50, date_from: dateFrom || undefined, date_to: dateTo || undefined, location_id: locationFilter || undefined }),
        financialExtrasApi.cashflow(cashflowMonths),
      ]);
      const data = (i, fallback) => results[i].status === 'fulfilled' ? (results[i].value?.data ?? fallback) : fallback;
      setSummary(data(0, null));
      setDonations(data(1, []));
      setExpenses(data(2, []));
      setCashflowData(data(3, { monthly: [] })?.monthly || []);
    } catch { toast.error('Failed to load financial data'); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    locationsApi.list().then(r => {
      const allLocs = r.data || [];
      setAllLocations(allLocs);
      // Only show sub-locations under the user's active campus
      const activeCampus = localStorage.getItem('5812_active_campus') || '';
      if (activeCampus) {
        setSubLocations(allLocs.filter(l => l.parent_id === activeCampus));
      } else {
        setSubLocations([]);
      }
    }).catch(() => {});
    fetchPending();
    financialApi.accounts().then(r => setSubAccounts(r.data)).catch(() => {});
    financialApi.transfers().then(r => setTransfers(r.data || [])).catch(() => {});
    financialApi.budgets().then(r => setBudgets(r.data || [])).catch(() => {});
    financialApi.categories().then(r => setCategories(r.data || [])).catch(() => {});
    chartAccountsApi.mine().then(r => setMyChartAccounts(r.data || [])).catch(() => {});
  }, []);
  useEffect(() => { fetchAll(); }, [dateFrom, dateTo, cashflowMonths, locationFilter]);

  const fetchPending = async () => {
    try { const r = await financialApi.pendingExpenses(); setPendingExpenses(r.data); } catch (e) { console.warn(e.message || e); }
  };

  const fetchBalanceSheet = async () => {
    setBsLoading(true);
    try {
      const params = {};
      if (locationFilter) params.location_id = locationFilter;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const [r, aRes] = await Promise.all([
        financialApi.balanceSheet(params),
        financialApi.listAssets(params),
      ]);
      setBalanceSheet(r.data);
      setAssets(aRes.data || []);
    } catch (e) { console.warn(e.message || e); }
    finally { setBsLoading(false); }
  };

  const attachReceipt = async (expenseId, url) => {
    try {
      await financialApi.setReceiptUrl(expenseId, { receipt_url: url });
      setExpenses(prev => prev.map(e => e.id === expenseId ? { ...e, receipt_url: url } : e));
      toast.success('Receipt attached');
    } catch { toast.error('Failed'); }
  };

  const approveExpense = async (id) => {
    try { await financialApi.approveExpense(id, approvalComment); setPendingExpenses(prev => prev.filter(e => e.id !== id)); setShowApprovalComment(null); setApprovalComment(''); toast.success('Expense approved'); fetchAll(); } catch { toast.error('Failed'); }
  };

  const rejectExpense = async (id) => {
    try { await financialApi.rejectExpense(id, approvalComment); setPendingExpenses(prev => prev.filter(e => e.id !== id)); setShowApprovalComment(null); setApprovalComment(''); toast.success('Expense rejected'); } catch { toast.error('Failed'); }
  };

  const handleAddDonation = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await financialApi.createDonation({ ...donationForm, amount: parseFloat(donationForm.amount) });
      setDonations(prev => [res.data, ...prev]);
      setShowDonation(false);
      setDonationForm({ donor_name: '', amount: '', currency: 'UGX', type: 'tithe', date: today, notes: '', sublocation_id: '', deposit_to_account_id: '' });
      toast.success('Donation recorded!');
      fetchAll();
      chartAccountsApi.mine().then(r => setMyChartAccounts(r.data || [])).catch(() => {});
    } catch (err) {
      let msg = err.response?.data?.detail;
      if (Array.isArray(msg)) msg = msg.map(e => `${(e.loc || []).join('.')}: ${e.msg}`).join('; ');
      else if (typeof msg === 'object' && msg !== null) msg = JSON.stringify(msg);
      toast.error(`Failed: ${msg || err.message || 'unknown'}`);
      console.error('Donation save error:', err.response?.data || err);
    }
    finally { setSaving(false); }
  };

  const handleAddExpense = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await financialApi.createExpense({ ...expenseForm, amount: parseFloat(expenseForm.amount) });
      setExpenses(prev => [res.data, ...prev]);
      setShowExpense(false);
      setExpenseForm({ title: '', amount: '', currency: 'UGX', category: 'general', date: today, notes: '', sublocation_id: '', vendor: '', receipt_number: '', account: '', department: '', budget_category: '', usd_equivalent: '', paid_from_account_id: '' });
      toast.success('Expense recorded!');
      fetchAll();
      chartAccountsApi.mine().then(r => setMyChartAccounts(r.data || [])).catch(() => {});
    } catch (err) {
      let msg = err.response?.data?.detail;
      if (Array.isArray(msg)) msg = msg.map(e => `${(e.loc || []).join('.')}: ${e.msg}`).join('; ');
      else if (typeof msg === 'object' && msg !== null) msg = JSON.stringify(msg);
      toast.error(`Failed: ${msg || err.message || 'unknown'}`);
      console.error('Expense save error:', err.response?.data || err);
    }
    finally { setSaving(false); }
  };

  const downloadCSV = () => {
    const token = secureStorage.getToken();
    const url = exportApi.financial();
    const a = document.createElement('a');
    a.href = `${url}`;
    a.setAttribute('download', 'financial.csv');
    // Use fetch with auth header
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.blob())
      .then(blob => {
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = 'financial.csv';
        link.click();
      }).catch(() => toast.error('Export failed'));
  };

  const handleFinancialExport = async () => {
    try {
      const params = {};
      if (locationFilter) params.location_id = locationFilter;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const res = await financialExtrasApi.export(params);
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url;
      a.download = `financial_export_${new Date().toISOString().slice(0, 10)}.json`; a.click();
      toast.success(`Exported ${res.data.donations_count} donations & ${res.data.expenses_count} expenses`);
    } catch { toast.error('Export failed'); }
  };

  const handleFinancialImport = async () => {
    if (!importData.trim()) return;
    setImportingData(true);
    try {
      const parsed = JSON.parse(importData);
      const res = await financialExtrasApi.import(parsed);
      toast.success(`Imported ${res.data.donations_imported} donations & ${res.data.expenses_imported} expenses`);
      setShowImportExport(false); setImportData(''); fetchAll();
    } catch (err) { toast.error(err.message || 'Import failed - check JSON format'); }
    finally { setImportingData(false); }
  };

  const handleSheetImport = async () => {
    if (!sheetCsv.trim()) return;
    setSheetImporting(true);
    try {
      // Robust CSV parser — handles common Excel quirks the previous naive parser broke on:
      //   • UTF-8 BOM (\ufeff) prepended by Excel "Save As CSV"
      //   • CRLF / CR-only line endings (Windows / Mac Excel)
      //   • Quoted cells containing commas OR embedded newlines
      //   • Escaped double-quotes inside quoted cells ("" → ")
      let raw = sheetCsv;
      if (raw.charCodeAt(0) === 0xFEFF) raw = raw.slice(1); // strip BOM
      raw = raw.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

      // Auto-detect TAB-separated paste from Excel (copy-paste from a spreadsheet
      // sends tab-delimited text, not comma-delimited). Count delimiters on the
      // first non-empty line; if there are more tabs than commas, treat tabs as the
      // separator. Strings inside quotes are NOT yet protected, so this is best-effort
      // — quoted commas still work below regardless.
      const firstLine = raw.split('\n').find(l => l.trim()) || '';
      const sep = (firstLine.split('\t').length - 1) > (firstLine.split(',').length - 1) ? '\t' : ',';

      // Tokenise the entire blob — state machine so a quoted cell can contain \n.
      const rows = [];
      let row = []; let cur = ''; let inQ = false;
      for (let i = 0; i < raw.length; i++) {
        const ch = raw[i];
        if (inQ) {
          if (ch === '"') {
            if (raw[i + 1] === '"') { cur += '"'; i++; }   // escaped quote
            else inQ = false;
          } else {
            cur += ch;
          }
        } else {
          if (ch === '"') inQ = true;
          else if (ch === sep) { row.push(cur); cur = ''; }
          else if (ch === '\n') { row.push(cur); rows.push(row); row = []; cur = ''; }
          else cur += ch;
        }
      }
      // Flush trailing cell + row
      if (cur.length || row.length) { row.push(cur); rows.push(row); }
      // Drop fully-empty rows + trim every cell
      const cleaned = rows
        .map(r => r.map(c => (c || '').trim()))
        .filter(r => r.some(c => c.length > 0));

      if (cleaned.length < 2) {
        toast.error('Need at least a header + one data row');
        setSheetImporting(false);
        return;
      }
      const header = cleaned[0];
      const dataRows = cleaned.slice(1).map(cells => {
        const row = {};
        header.forEach((h, i) => { row[h] = cells[i] !== undefined ? cells[i] : ''; });
        return row;
      });
      const res = await api.post('/financial/import-sheet', {
        type: sheetType,
        rows: dataRows,
        default_status: sheetStatus,
        location_id: locationFilter || undefined,
      });
      const { created = 0, skipped = 0, errors = [] } = res.data || {};
      if (created === 0 && skipped > 0) {
        toast.error(
          `0 rows imported — ${skipped} skipped. ${errors.length ? `First error: ${errors[0]}` : 'Most common cause: missing or zero amount.'}`,
          { duration: 8000 },
        );
      } else if (errors.length) {
        toast.warning(`Imported ${created} ${sheetType}(s) · ${skipped} skipped · ${errors.length} row error(s) — see console`, { duration: 6000 });
      } else {
        toast.success(`Imported ${created} ${sheetType}(s) · ${skipped} skipped`);
      }
      if (errors.length) console.warn('Sheet import errors:', errors);
      setShowImportExport(false); setSheetCsv(''); fetchAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || 'Sheet import failed');
    } finally { setSheetImporting(false); }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Financial Management</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Track donations, expenses, and cashflow</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" size="sm" onClick={() => setShowDistribute(true)} className="gap-1.5" data-testid="distribute-funds-btn"><DollarSign size={14} /> Transfer</Button>
          <Button variant="outline" size="sm" onClick={() => setShowCategories(true)} data-testid="manage-categories-btn" className="gap-1.5 text-xs">Categories</Button>
          <Button variant="outline" size="sm" onClick={fetchAll} data-testid="financial-refresh"><RefreshCw size={14} /></Button>
          <Button variant="outline" size="sm" onClick={downloadCSV} className="gap-2" data-testid="financial-export">
            <Download size={14} /> Export CSV
          </Button>
          <Button variant="outline" size="sm" onClick={() => setShowImportExport(true)} className="gap-2" data-testid="financial-import-export-btn">
            <Upload size={14} /> Import/Export
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <SummaryCard title="Monthly Donations" value={fmt(summary?.monthly_donations)} sub="This month" icon={DollarSign} color="bg-green-500" loading={loading} />
        <SummaryCard title="Monthly Expenses" value={fmt(summary?.monthly_expenses)} sub="This month" icon={TrendingDown} color="bg-red-500" loading={loading} />
        <SummaryCard title="Monthly Sales" value={fmt(summary?.monthly_sales)} sub="Products sold" icon={Wallet} color="bg-blue-500" loading={loading} />
        <SummaryCard
          title="Net Balance"
          value={fmt(summary?.net_balance)}
          sub={`In: ${fmt(summary?.cashflow_in)} / Out: ${fmt(summary?.cashflow_out)}`}
          icon={TrendingUp}
          color={summary?.net_balance >= 0 ? 'bg-emerald-500' : 'bg-rose-500'}
          loading={loading}
        />
      </div>

      {/* Date Range Filter */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Label className="text-xs text-muted-foreground whitespace-nowrap">From</Label>
          <Input type="date" className="h-8 w-auto text-xs" value={dateFrom} onChange={e => setDateFrom(e.target.value)} data-testid="date-from" />
        </div>
        <div className="flex items-center gap-2">
          <Label className="text-xs text-muted-foreground whitespace-nowrap">To</Label>
          <Input type="date" className="h-8 w-auto text-xs" value={dateTo} onChange={e => setDateTo(e.target.value)} data-testid="date-to" />
        </div>
        {(dateFrom || dateTo) && (
          <Button variant="ghost" size="sm" className="text-xs h-8" onClick={() => { setDateFrom(''); setDateTo(''); }}>Clear</Button>
        )}
      </div>

      {/* Quick-link banner — clarifies the relationship between Financial / Accounting / Banking */}
      <div className="rounded-xl border border-primary/20 bg-primary/5 p-3 text-xs flex flex-wrap items-center gap-2" data-testid="financial-modules-banner">
        <span className="font-semibold">💡 Three connected views:</span>
        <span>This page = quick entry & cash chart.</span>
        <Link to="/accounting" className="text-primary hover:underline font-medium" data-testid="link-accounting">/accounting →</Link>
        <span>= double-entry ledger + statements.</span>
        <Link to="/banking" className="text-primary hover:underline font-medium" data-testid="link-banking">/banking →</Link>
        <span>= bank accounts, vendor bills (AP), recurring entries.</span>
        <span className="text-muted-foreground">Every entry here auto-posts to the ledger.</span>
      </div>

      {/* Cashflow Chart */}
      <Card className="shadow-soft rounded-xl">
        <CardHeader className="flex flex-row items-center justify-between pb-2 pt-4 px-5">
          <CardTitle className="text-base font-semibold">Cashflow Overview</CardTitle>
          <Select value={String(cashflowMonths)} onValueChange={v => setCashflowMonths(parseInt(v))}>
            <SelectTrigger className="w-28 h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="3">3 months</SelectItem>
              <SelectItem value="6">6 months</SelectItem>
              <SelectItem value="12">12 months</SelectItem>
            </SelectContent>
          </Select>
        </CardHeader>
        <CardContent className="px-5 pb-5">
          {loading ? <div className="h-52 bg-muted animate-pulse rounded" /> : (
            cashflowData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={cashflowData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `${(v/1000).toFixed(0)}K`} />
                  <Tooltip formatter={v => [fmt(v)]} contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 8 }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="inflow" name="Income" fill="#22c55e" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="outflow" name="Expenses" fill="#ef4444" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <p className="text-sm text-muted-foreground text-center py-12">No cashflow data yet. Add donations and expenses to see trends.</p>
          )}
        </CardContent>
      </Card>

      <Tabs defaultValue="donations">
        <TabsList>
          <TabsTrigger value="donations" data-testid="tab-donations">Donations</TabsTrigger>
          <TabsTrigger value="expenses" data-testid="tab-expenses">Expenses</TabsTrigger>
          <TabsTrigger value="accounts" data-testid="tab-accounts">Accounts</TabsTrigger>
          <TabsTrigger value="transfers" data-testid="tab-transfers">Transfers</TabsTrigger>
          <TabsTrigger value="budgets" data-testid="tab-budgets">Budgets</TabsTrigger>
          <TabsTrigger value="balance" data-testid="tab-balance" onClick={fetchBalanceSheet}>Balance Sheet</TabsTrigger>
          <TabsTrigger value="approvals" data-testid="tab-approvals">Approvals {pendingExpenses.length > 0 && <Badge className="ml-1 bg-amber-500 text-white text-xs px-1.5">{pendingExpenses.length}</Badge>}</TabsTrigger>
        </TabsList>

        <TabsContent value="donations" className="mt-4">
          <Card className="shadow-soft rounded-xl">
            <CardHeader className="flex flex-row items-center justify-between py-4 px-5">
              <CardTitle className="text-base font-semibold">Donation Records</CardTitle>
              <Button size="sm" className="gap-2" onClick={() => setShowDonation(true)} data-testid="add-donation-btn">
                <Plus size={14} /> Add Donation
              </Button>
            </CardHeader>
            <CardContent className="px-5 pb-5">
              {loading ? (
                <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-12 bg-muted animate-pulse rounded" />)}</div>
              ) : donations.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    {selectedIds.size > 0 && <div className="mb-2"><BulkActionBar
                      selectedIds={selectedIds}
                      onClear={() => setSelectedIds(new Set())}
                      onBulkExport={() => exportToCSV(donations.filter(d => selectedIds.has(d.id)), 'donations-export.csv')}
                      onBulkDelete={isFinanceAdmin ? async () => {
                        if (!window.confirm(`Delete ${selectedIds.size} donation(s)? This cannot be undone.`)) return;
                        try {
                          const ids = Array.from(selectedIds);
                          const r = await financialApi.bulkDeleteDonations(ids);
                          setDonations(prev => prev.filter(d => !selectedIds.has(d.id)));
                          setSelectedIds(new Set());
                          toast.success(`Deleted ${r.data.deleted}`);
                          fetchAll();
                        } catch (err) { toast.error(err.response?.data?.detail || 'Bulk delete failed'); }
                      } : undefined}
                    /></div>}
                    <thead><tr className="text-left border-b border-border">
                      <th className="pb-2 w-8"><input type="checkbox" className="accent-primary" checked={selectedIds.size > 0 && donations.every(d => selectedIds.has(d.id))} onChange={() => { if (selectedIds.size === donations.length) setSelectedIds(new Set()); else setSelectedIds(new Set(donations.map(d => d.id))); }} /></th>
                      <th className="pb-2 font-medium text-muted-foreground">Donor</th>
                      <th className="pb-2 font-medium text-muted-foreground">Amount</th>
                      <th className="pb-2 font-medium text-muted-foreground">Type</th>
                      <th className="pb-2 font-medium text-muted-foreground">Date</th>
                      <th className="pb-2 font-medium text-muted-foreground">Actions</th>
                    </tr></thead>
                    <tbody className="divide-y divide-border">
                      {donations.map(d => (
                        <tr key={d.id} className={`hover:bg-accent/30 transition-colors ${selectedIds.has(d.id) ? 'bg-primary/5' : ''}`}>
                          <td className="py-3 w-8"><input type="checkbox" className="accent-primary" checked={selectedIds.has(d.id)} onChange={() => setSelectedIds(prev => { const n = new Set(prev); n.has(d.id) ? n.delete(d.id) : n.add(d.id); return n; })} /></td>
                          <td className="py-3 font-medium">{d.donor_name}</td>
                          <td className="py-3 text-green-600 font-semibold">{d.currency} {(d.amount||0).toLocaleString()}</td>
                          <td className="py-3"><span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${typeColors[d.type] || 'bg-slate-100 text-slate-700'}`}>{d.type}</span></td>
                          <td className="py-3 text-muted-foreground">{d.date}</td>
                          <td className="py-3">
                            <div className="flex gap-1">
                              <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={() => { setEditEntry({ ...d, type: 'donation' }); setEditForm({ donor_name: d.donor_name, amount: d.amount, currency: d.currency, type: d.type, date: d.date, notes: d.notes || '' }); }}>Edit</Button>
                              {isFinanceAdmin && <Button size="sm" variant="ghost" className="h-6 text-xs text-destructive" onClick={async () => { if (!window.confirm('Delete this donation?')) return; try { await financialApi.deleteDonation(d.id); setDonations(prev => prev.filter(x => x.id !== d.id)); toast.success('Deleted'); fetchAll(); } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); } }}>Del</Button>}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-10">No donations recorded yet.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="expenses" className="mt-4">
          <Card className="shadow-soft rounded-xl">
            <CardHeader className="flex flex-row items-center justify-between py-4 px-5">
              <CardTitle className="text-base font-semibold">Expense Records</CardTitle>
              <Button size="sm" className="gap-2" onClick={() => setShowExpense(true)} data-testid="add-expense-btn">
                <Plus size={14} /> Add Expense
              </Button>
            </CardHeader>
            <CardContent className="px-5 pb-5">
              {loading ? (
                <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-12 bg-muted animate-pulse rounded" />)}</div>
              ) : expenses.length > 0 ? (
                <div className="overflow-x-auto">
                  {selectedExpenseIds.size > 0 && <div className="mb-2"><BulkActionBar
                    selectedIds={selectedExpenseIds}
                    onClear={() => setSelectedExpenseIds(new Set())}
                    onBulkExport={() => exportToCSV(expenses.filter(e => selectedExpenseIds.has(e.id)), 'expenses-export.csv')}
                    onBulkDelete={isFinanceAdmin ? async () => {
                      if (!window.confirm(`Delete ${selectedExpenseIds.size} expense(s)? This cannot be undone.`)) return;
                      try {
                        const ids = Array.from(selectedExpenseIds);
                        const r = await financialApi.bulkDeleteExpenses(ids);
                        setExpenses(prev => prev.filter(e => !selectedExpenseIds.has(e.id)));
                        setSelectedExpenseIds(new Set());
                        toast.success(`Deleted ${r.data.deleted}`);
                        fetchAll();
                      } catch (err) { toast.error(err.response?.data?.detail || 'Bulk delete failed'); }
                    } : undefined}
                  /></div>}
                  <table className="w-full text-sm">
                    <thead><tr className="text-left border-b border-border">
                      <th className="pb-2 w-8"><input type="checkbox" className="accent-primary" data-testid="expense-select-all" checked={selectedExpenseIds.size > 0 && expenses.every(e => selectedExpenseIds.has(e.id))} onChange={() => { if (selectedExpenseIds.size === expenses.length) setSelectedExpenseIds(new Set()); else setSelectedExpenseIds(new Set(expenses.map(e => e.id))); }} /></th>
                      <th className="pb-2 font-medium text-muted-foreground">Title</th>
                      <th className="pb-2 font-medium text-muted-foreground">Amount</th>
                      <th className="pb-2 font-medium text-muted-foreground">Category</th>
                      <th className="pb-2 font-medium text-muted-foreground">Date</th>
                      <th className="pb-2 font-medium text-muted-foreground">Receipt</th>
                      <th className="pb-2 font-medium text-muted-foreground">Actions</th>
                    </tr></thead>
                    <tbody className="divide-y divide-border">
                      {expenses.map(e => (
                        <tr key={e.id} className={`hover:bg-accent/30 transition-colors ${e.status === 'pending' ? 'bg-amber-50/50 dark:bg-amber-950/10' : e.status === 'rejected' ? 'opacity-50' : ''} ${selectedExpenseIds.has(e.id) ? 'bg-primary/5' : ''}`}>
                          <td className="py-3 w-8"><input type="checkbox" className="accent-primary" data-testid={`expense-select-${e.id}`} checked={selectedExpenseIds.has(e.id)} onChange={() => setSelectedExpenseIds(prev => { const n = new Set(prev); n.has(e.id) ? n.delete(e.id) : n.add(e.id); return n; })} /></td>
                          <td className="py-3 font-medium">
                            {e.title}
                            {e.status === 'pending' && <Badge variant="outline" className="ml-2 text-[10px] border-amber-300 text-amber-700">Pending approval</Badge>}
                            {e.status === 'rejected' && <Badge variant="outline" className="ml-2 text-[10px] border-red-300 text-red-700">Rejected</Badge>}
                          </td>
                          <td className="py-3 text-red-600 font-semibold">{e.currency} {(e.amount||0).toLocaleString()}</td>
                          <td className="py-3"><span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${expenseCategoryColors[e.category] || 'bg-slate-100 text-slate-700'}`}>{e.category}</span></td>
                          <td className="py-3 text-muted-foreground">{e.date}</td>
                          <td className="py-3">
                            {e.receipt_url ? (
                              <a href={e.receipt_url} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline">View</a>
                            ) : (
                              <Button size="sm" variant="ghost" className="h-6 text-xs" data-testid={`attach-receipt-${e.id}`} onClick={() => {
                                setShowAttachReceipt(e);
                                setAttachReceiptUrl('');
                              }}>Attach</Button>
                            )}
                          </td>
                          <td className="py-3">
                            <div className="flex gap-1 flex-wrap">
                              {e.status === 'pending' && isFinanceAdmin && (
                                <>
                                  <Button size="sm" variant="ghost" className="h-6 text-xs text-green-700 hover:bg-green-50" data-testid={`inline-approve-${e.id}`} onClick={async () => {
                                    try { await financialApi.approveExpense(e.id, ''); setExpenses(prev => prev.map(x => x.id === e.id ? { ...x, status: 'approved' } : x)); toast.success('Approved'); fetchAll(); } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
                                  }}>✓ Approve</Button>
                                  <Button size="sm" variant="ghost" className="h-6 text-xs text-red-700 hover:bg-red-50" data-testid={`inline-reject-${e.id}`} onClick={() => { setRejectingExpense(e); setRejectReason(''); }}>✕ Reject</Button>
                                </>
                              )}
                              <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={() => { setEditEntry({ ...e, type: 'expense' }); setEditForm({ title: e.title, amount: e.amount, currency: e.currency, category: e.category, date: e.date, notes: e.notes || '' }); }}>Edit</Button>
                              {isFinanceAdmin && <Button size="sm" variant="ghost" className="h-6 text-xs text-destructive" onClick={async () => { if (!window.confirm('Delete this expense?')) return; try { await financialApi.deleteExpense(e.id); setExpenses(prev => prev.filter(x => x.id !== e.id)); toast.success('Deleted'); fetchAll(); } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); } }}>Del</Button>}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-10">No expenses recorded yet.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* BALANCE SHEET TAB */}

        {/* Transfers Tab */}
        <TabsContent value="transfers" className="mt-4 space-y-3">
          <div className="flex justify-end">
            <Button size="sm" className="gap-1.5" onClick={() => { setTransferForm({ from_account_id: '', to_account_id: '', amount: '', currency: currentCurrency || 'UGX', notes: '' }); setShowTransfer(true); }} data-testid="create-transfer-btn">Create Transfer</Button>
          </div>
          <Card className="rounded-xl shadow-soft"><CardContent className="p-0">
            <table className="w-full text-sm"><thead><tr className="border-b"><th className="p-3 text-left text-xs text-muted-foreground">From</th><th className="p-3 text-left text-xs text-muted-foreground">To</th><th className="p-3 text-right text-xs text-muted-foreground">Amount</th><th className="p-3 text-left text-xs text-muted-foreground">Date</th></tr></thead>
            <tbody>{(transfers || []).map(t => <tr key={t.id} className="border-b last:border-0"><td className="p-3">{t.from_name}</td><td className="p-3">{t.to_name}</td><td className="p-3 text-right font-medium">{(t.amount || 0).toLocaleString()}</td><td className="p-3 text-muted-foreground text-xs">{t.created_at?.slice(0, 10)}</td></tr>)}
            {(!transfers || transfers.length === 0) && <tr><td colSpan={4} className="p-6 text-center text-muted-foreground text-xs" data-testid="fin-transfers-empty">No transfers yet — click "Create Transfer" above to move funds between accounts.</td></tr>}
            </tbody></table>
          </CardContent></Card>
        </TabsContent>

        {/* Budgets Tab */}
        <TabsContent value="budgets" className="mt-4 space-y-3">
          <div className="flex justify-end">
            <Button size="sm" className="gap-1.5" onClick={() => { setBudgetForm({ department: '', period: new Date().toISOString().slice(0, 7), amount: '', category: 'general' }); setShowBudget(true); }} data-testid="create-budget-btn">Add Budget</Button>
          </div>
          {selectedBudgetIds.size > 0 && <BulkActionBar
            selectedIds={selectedBudgetIds}
            onClear={() => setSelectedBudgetIds(new Set())}
            onBulkExport={() => exportToCSV((budgets || []).filter(b => selectedBudgetIds.has(b.id)), 'budgets-export.csv')}
            onBulkDelete={isFinanceAdmin ? async () => {
              if (!window.confirm(`Delete ${selectedBudgetIds.size} budget(s)? This cannot be undone.`)) return;
              try {
                const ids = Array.from(selectedBudgetIds);
                const r = await financialApi.bulkDeleteBudgets(ids);
                setBudgets(prev => (prev || []).filter(b => !selectedBudgetIds.has(b.id)));
                setSelectedBudgetIds(new Set());
                toast.success(`Deleted ${r.data.deleted}`);
              } catch (err) { toast.error(err.response?.data?.detail || 'Bulk delete failed'); }
            } : undefined}
          />}
          <Card className="rounded-xl shadow-soft"><CardContent className="p-0">
            <table className="w-full text-sm"><thead><tr className="border-b">
              <th className="p-3 w-8"><input type="checkbox" className="accent-primary" data-testid="budget-select-all" checked={(budgets || []).length > 0 && selectedBudgetIds.size > 0 && (budgets || []).every(b => selectedBudgetIds.has(b.id))} onChange={() => { if (selectedBudgetIds.size === (budgets || []).length) setSelectedBudgetIds(new Set()); else setSelectedBudgetIds(new Set((budgets || []).map(b => b.id))); }} /></th>
              <th className="p-3 text-left text-xs text-muted-foreground">Department</th><th className="p-3 text-left text-xs text-muted-foreground">Period</th><th className="p-3 text-right text-xs text-muted-foreground">Amount</th><th className="p-3 text-left text-xs text-muted-foreground">Category</th></tr></thead>
            <tbody>{(budgets || []).map(b => <tr key={b.id} className={`border-b last:border-0 ${selectedBudgetIds.has(b.id) ? 'bg-primary/5' : ''}`}>
              <td className="p-3 w-8"><input type="checkbox" className="accent-primary" data-testid={`budget-select-${b.id}`} checked={selectedBudgetIds.has(b.id)} onChange={() => setSelectedBudgetIds(prev => { const n = new Set(prev); n.has(b.id) ? n.delete(b.id) : n.add(b.id); return n; })} /></td>
              <td className="p-3">{b.department || b.location_id}</td><td className="p-3">{b.period}</td><td className="p-3 text-right font-medium">{(b.amount || 0).toLocaleString()}</td><td className="p-3 text-muted-foreground">{b.category}</td></tr>)}
            {(!budgets || budgets.length === 0) && <tr><td colSpan={5} className="p-6 text-center text-muted-foreground text-xs">No budgets set</td></tr>}
            </tbody></table>
          </CardContent></Card>
        </TabsContent>


        <TabsContent value="balance" className="mt-4">
          {bsLoading ? (
            <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-20 bg-muted animate-pulse rounded-xl" />)}</div>
          ) : balanceSheet ? (
            <div className="space-y-4">
              {/* Hero P&L Card — primary result of the balance sheet */}
              <Card className={`rounded-xl border-2 ${balanceSheet.is_profit ? 'border-green-300 bg-green-50/50 dark:bg-green-950/10' : 'border-red-300 bg-red-50/50 dark:bg-red-950/10'}`} data-testid="net-pnl-card">
                <CardContent className="p-5">
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div>
                      <p className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">{balanceSheet.is_profit ? 'Net Profit' : 'Net Loss'}</p>
                      <p className={`text-4xl font-bold mt-1 ${balanceSheet.is_profit ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}`} data-testid="net-pnl-amount">
                        {balanceSheet.is_profit ? '' : '-'}{fmt(Math.abs(balanceSheet.net_profit_loss ?? balanceSheet.net_balance))}
                      </p>
                      <p className="text-sm text-muted-foreground mt-2">
                        Revenue {fmt(balanceSheet.total_revenue ?? (balanceSheet.total_income + balanceSheet.total_sales))} − Expenses {fmt(balanceSheet.total_expenses)}
                        {balanceSheet.profit_margin_pct != null && <span className="ml-2 text-xs">· margin {balanceSheet.profit_margin_pct}%</span>}
                      </p>
                    </div>
                    <div className="text-right text-xs space-y-1 min-w-[180px]">
                      {balanceSheet.accounts_receivable > 0 && (
                        <div className="text-amber-700 dark:text-amber-400 bg-amber-100/50 dark:bg-amber-950/20 rounded px-2 py-1">
                          + {fmt(balanceSheet.accounts_receivable)} receivable
                          <span className="block text-[10px] opacity-75">{balanceSheet.pending_sales_count} pending sale{balanceSheet.pending_sales_count === 1 ? '' : 's'}</span>
                        </div>
                      )}
                      {balanceSheet.assets_total > 0 && (
                        <div className="text-blue-700 dark:text-blue-400">
                          Net Worth: <strong>{fmt(balanceSheet.net_worth)}</strong>
                          <span className="block text-[10px] opacity-75">incl. {fmt(balanceSheet.assets_total)} in assets</span>
                        </div>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>

              <div className="grid sm:grid-cols-3 gap-4">
                <Card className="rounded-xl"><CardContent className="p-4 text-center"><p className="text-2xl font-bold text-green-600">{fmt(balanceSheet.total_income)}</p><p className="text-xs text-muted-foreground mt-1">Donations Income ({balanceSheet.donation_count})</p></CardContent></Card>
                <Card className="rounded-xl"><CardContent className="p-4 text-center"><p className="text-2xl font-bold text-blue-600">{fmt(balanceSheet.total_sales)}</p><p className="text-xs text-muted-foreground mt-1">Sales Revenue ({balanceSheet.sale_count} paid)</p></CardContent></Card>
                <Card className="rounded-xl"><CardContent className="p-4 text-center"><p className="text-2xl font-bold text-red-600">{fmt(balanceSheet.total_expenses)}</p><p className="text-xs text-muted-foreground mt-1">Expenses ({balanceSheet.expense_count})</p></CardContent></Card>
              </div>
              <div className="grid sm:grid-cols-2 gap-4">
                <Card className="rounded-xl"><CardContent className="p-4"><h3 className="font-semibold text-sm mb-3">Income Breakdown</h3>
                  {Object.entries(balanceSheet.income_by_type || {}).map(([type, amount]) => (
                    <div key={type} className="flex justify-between py-1.5 text-sm border-b border-border last:border-0"><span className="capitalize text-muted-foreground">{type}</span><span className="font-medium text-green-600">{fmt(amount)}</span></div>
                  ))}
                  {Object.keys(balanceSheet.income_by_type || {}).length === 0 && <p className="text-xs text-muted-foreground text-center py-4">No income data</p>}
                </CardContent></Card>
                <Card className="rounded-xl"><CardContent className="p-4"><h3 className="font-semibold text-sm mb-3">Expense Breakdown</h3>
                  {Object.entries(balanceSheet.expense_by_category || {}).map(([cat, amount]) => (
                    <div key={cat} className="flex justify-between py-1.5 text-sm border-b border-border last:border-0"><span className="capitalize text-muted-foreground">{cat}</span><span className="font-medium text-red-600">{fmt(amount)}</span></div>
                  ))}
                  {Object.keys(balanceSheet.expense_by_category || {}).length === 0 && <p className="text-xs text-muted-foreground text-center py-4">No expense data</p>}
                </CardContent></Card>
              </div>
              {/* Assets Tracking */}
              <Card className="rounded-xl mt-4">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="font-semibold text-sm">Assets & Property</h3>
                    <Button size="sm" variant="outline" className="gap-1 text-xs h-7" onClick={() => setShowAssetForm(true)}>+ Add Asset</Button>
                  </div>
                  {selectedAssetIds.size > 0 && <div className="mb-3"><BulkActionBar
                    selectedIds={selectedAssetIds}
                    onClear={() => setSelectedAssetIds(new Set())}
                    onBulkExport={() => exportToCSV(assets.filter(a => selectedAssetIds.has(a.id)), 'assets-export.csv')}
                    onBulkDelete={isFinanceAdmin ? async () => {
                      if (!window.confirm(`Delete ${selectedAssetIds.size} asset(s)? This cannot be undone.`)) return;
                      try {
                        const ids = Array.from(selectedAssetIds);
                        const r = await financialApi.bulkDeleteAssets(ids);
                        setAssets(prev => prev.filter(a => !selectedAssetIds.has(a.id)));
                        setSelectedAssetIds(new Set());
                        toast.success(`Deleted ${r.data.deleted}`);
                      } catch (err) { toast.error(err.response?.data?.detail || 'Bulk delete failed'); }
                    } : undefined}
                  /></div>}
                  {assets.length === 0 ? (
                    <p className="text-xs text-muted-foreground text-center py-4">No assets recorded. Track equipment, vehicles, property values here.</p>
                  ) : (
                    <table className="w-full text-sm">
                      <thead><tr className="text-left border-b">
                        {isFinanceAdmin && <th className="pb-2 w-8"><input type="checkbox" className="accent-primary" data-testid="asset-select-all" checked={assets.length > 0 && selectedAssetIds.size > 0 && assets.every(a => selectedAssetIds.has(a.id))} onChange={() => { if (selectedAssetIds.size === assets.length) setSelectedAssetIds(new Set()); else setSelectedAssetIds(new Set(assets.map(a => a.id))); }} /></th>}
                        <th className="pb-2 text-xs text-muted-foreground">Asset</th><th className="pb-2 text-xs text-muted-foreground">Category</th><th className="pb-2 text-xs text-muted-foreground">Purchase Value</th><th className="pb-2 text-xs text-muted-foreground">Current Value</th><th className="pb-2 text-xs text-muted-foreground">Method</th>{isFinanceAdmin && <th className="pb-2 w-20"></th>}</tr></thead>
                      <tbody className="divide-y">
                        {assets.map(a => {
                          const age = a.purchase_date ? (new Date().getFullYear() - new Date(a.purchase_date).getFullYear()) : 0;
                          const method = a.valuation_method || 'appreciation';
                          const rate = a.depreciation_years > 0 ? 1 / a.depreciation_years : 0.03;
                          const currentVal = a.current_value != null ? a.current_value : (method === 'depreciation' ? Math.max(0, (a.value || 0) * (1 - rate * Math.min(age, a.depreciation_years || 10))) : (a.value || 0) * (1 + rate * age));
                          return (
                            <tr key={a.id || a.name} className={selectedAssetIds.has(a.id) ? 'bg-primary/5' : ''}>
                              {isFinanceAdmin && <td className="py-2 w-8"><input type="checkbox" className="accent-primary" data-testid={`asset-select-${a.id}`} checked={selectedAssetIds.has(a.id)} onChange={() => setSelectedAssetIds(prev => { const n = new Set(prev); n.has(a.id) ? n.delete(a.id) : n.add(a.id); return n; })} /></td>}
                              <td className="py-2 font-medium">{a.name}</td>
                              <td className="py-2 text-muted-foreground capitalize">{a.category}</td>
                              <td className="py-2">{fmt(a.value)}</td>
                              <td className={`py-2 font-medium ${method === 'depreciation' ? 'text-red-600' : 'text-green-600'}`}>{fmt(currentVal)}</td>
                              <td className="py-2"><Badge variant="outline" className={`text-[10px] ${method === 'depreciation' ? 'border-red-200 text-red-500' : 'border-green-200 text-green-600'}`}>{method}</Badge></td>
                              {isFinanceAdmin && <td className="py-2 flex gap-1">
                                <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={() => {
                                  setShowRevalue(a);
                                  setRevalueForm({ current_value: Number(currentVal) || 0, method: method || 'appreciation', notes: '' });
                                }} data-testid={`revalue-asset-${a.id}`}>Revalue</Button>
                                <Button size="sm" variant="ghost" className="h-6 text-xs text-destructive" onClick={async () => { if (!window.confirm(`Delete "${a.name}"?`)) return; try { await financialApi.deleteAsset(a.id); setAssets(prev => prev.filter(x => x.id !== a.id)); toast.success('Deleted'); } catch { toast.error('Failed'); } }}>Del</Button>
                              </td>}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </CardContent>
              </Card>
            </div>
          ) : (
            <Card className="rounded-xl"><CardContent className="py-12 text-center"><p className="text-muted-foreground">Click the Balance Sheet tab to generate the report for the selected campus and date range.</p></CardContent></Card>
          )}
        </TabsContent>

        <TabsContent value="approvals" className="mt-4">
          <Card className="shadow-soft rounded-xl">
            <CardHeader className="flex flex-row items-center justify-between py-4 px-5">
              <CardTitle className="text-base font-semibold">Pending Expense Approvals</CardTitle>
              <Button size="sm" variant="outline" onClick={fetchPending}><RefreshCw size={14} /></Button>
            </CardHeader>
            <CardContent className="px-5 pb-5">
              {pendingExpenses.length > 0 ? (
                <div className="space-y-3">
                  {pendingExpenses.map(e => (
                    <div key={e.id} className="flex items-center justify-between p-3 rounded-lg border border-border" data-testid={`pending-expense-${e.id}`}>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-sm">{e.title}</p>
                        <p className="text-xs text-muted-foreground">{e.category} · {e.date} · Submitted by: {e.submitted_by || e.created_by || 'Staff'}</p>
                      </div>
                      <p className="text-sm font-bold text-red-600 mx-4">{e.currency || 'UGX'} {(e.amount || 0).toLocaleString()}</p>
                      <div className="flex gap-1.5">
                        <Button data-testid={`approve-expense-${e.id}`} size="sm" className="bg-green-600 hover:bg-green-700 text-white h-8 text-xs" onClick={() => approveExpense(e.id)}>Approve</Button>
                        <Button data-testid={`reject-expense-${e.id}`} size="sm" variant="destructive" className="h-8 text-xs" onClick={() => { setShowApprovalComment(e); }}>Reject</Button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-10">No pending expenses to approve.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Sub-Location Accounts Tab */}
        <TabsContent value="accounts" className="mt-4 space-y-4">
          {subAccounts ? (
            <>
              <div className="grid grid-cols-4 gap-3">
                <Card className="rounded-xl bg-green-50 dark:bg-green-950/20 border-green-200"><CardContent className="p-4 text-center"><p className="text-xs text-green-600 font-medium">Campus Income</p><p className="text-lg font-bold text-green-700">{(subAccounts.campus_total_income || 0).toLocaleString()}</p></CardContent></Card>
                <Card className="rounded-xl bg-red-50 dark:bg-red-950/20 border-red-200"><CardContent className="p-4 text-center"><p className="text-xs text-red-600 font-medium">Campus Expenses</p><p className="text-lg font-bold text-red-700">{(subAccounts.campus_total_expenses || 0).toLocaleString()}</p></CardContent></Card>
                <Card className="rounded-xl bg-blue-50 dark:bg-blue-950/20 border-blue-200"><CardContent className="p-4 text-center"><p className="text-xs text-blue-600 font-medium">Net Balance</p><p className="text-lg font-bold text-blue-700">{(subAccounts.campus_balance || 0).toLocaleString()}</p></CardContent></Card>
                <Card className="rounded-xl bg-purple-50 dark:bg-purple-950/20 border-purple-200"><CardContent className="p-4 text-center"><p className="text-xs text-purple-600 font-medium">Starting Balance</p><p className="text-lg font-bold text-purple-700">{(subAccounts.accounts || []).reduce((s, a) => s + (a.starting_balance || 0), 0).toLocaleString()}</p></CardContent></Card>
              </div>
              <Card className="rounded-xl shadow-soft">
                <CardContent className="p-0">
                  <table className="w-full text-sm">
                    <thead><tr className="border-b"><th className="p-3 text-left text-xs text-muted-foreground">Location</th><th className="p-3 text-left text-xs text-muted-foreground">Type</th><th className="p-3 text-right text-xs text-muted-foreground">Starting Bal.</th><th className="p-3 text-right text-xs text-muted-foreground">Income</th><th className="p-3 text-right text-xs text-muted-foreground">Expenses</th><th className="p-3 text-right text-xs text-muted-foreground">Balance</th><th className="p-3 w-16"></th></tr></thead>
                    <tbody>
                      {(subAccounts.accounts || []).map(a => (
                        <tr key={a.location_id || a.id} className="border-b last:border-0 hover:bg-accent/30">
                          <td className="p-3 font-medium">{a.location_name}</td>
                          <td className="p-3"><Badge variant="secondary" className="text-[10px]">{a.location_type || a.type || ''}</Badge></td>
                          <td className="p-3 text-right text-purple-600">{(a.starting_balance || 0).toLocaleString()}</td>
                          <td className="p-3 text-right text-green-600">{(a.total_income || 0).toLocaleString()}</td>
                          <td className="p-3 text-right text-red-600">{(a.total_expenses || 0).toLocaleString()}</td>
                          <td className="p-3 text-right font-medium">{((a.starting_balance || 0) + (a.balance || 0)).toLocaleString()}</td>
                          <td className="p-3">{isFinanceAdmin && <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={() => {
                            setShowStartingBal(a);
                            setStartingBalValue(String(a.starting_balance || 0));
                          }} data-testid={`edit-account-${a.location_id}`}>Edit</Button>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            </>
          ) : <p className="text-sm text-muted-foreground text-center py-8">Select a campus to view sub-location accounts</p>}
        </TabsContent>

      </Tabs>

      {/* Rejection Comment Dialog */}
      <Dialog open={!!showApprovalComment} onOpenChange={() => setShowApprovalComment(null)}>
        <DialogContent className="max-w-sm max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Reject Expense</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <p className="text-sm">Rejecting: <strong>{showApprovalComment?.title}</strong></p>
            <div className="space-y-2"><Label>Reason (optional)</Label><Input placeholder="Reason for rejection" value={approvalComment} onChange={e => setApprovalComment(e.target.value)} /></div>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => { setShowApprovalComment(null); setApprovalComment(''); }}>Cancel</Button>
              <Button variant="destructive" className="flex-1" onClick={() => rejectExpense(showApprovalComment?.id)}>Reject</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Add Donation Modal */}
      <Dialog open={showDonation} onOpenChange={setShowDonation}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Record Donation</DialogTitle></DialogHeader>
          <form onSubmit={handleAddDonation} className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Donor Name *</Label>
              <Input placeholder="Donor name" value={donationForm.donor_name} onChange={e => setDonationForm({...donationForm, donor_name: e.target.value})} required data-testid="donor-name-input" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Amount (UGX) *</Label>
                <Input type="number" placeholder="0" value={donationForm.amount} onChange={e => setDonationForm({...donationForm, amount: e.target.value})} required data-testid="donation-amount-input" />
              </div>
              <div className="space-y-2">
                <Label>Type</Label>
                <Select value={donationForm.type} onValueChange={v => setDonationForm({...donationForm, type: v})}>
                  <SelectTrigger data-testid="donation-type-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="tithe">Tithe</SelectItem>
                    <SelectItem value="offering">Offering</SelectItem>
                    <SelectItem value="donation">Donation</SelectItem>
                    <SelectItem value="pledge">Pledge</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label>Date</Label>
              <Input type="date" value={donationForm.date} onChange={e => setDonationForm({...donationForm, date: e.target.value})} />
            </div>
            <div className="space-y-2">
              <Label>Sub-Location</Label>
              <Select value={donationForm.sublocation_id || '_none'} onValueChange={v => setDonationForm({...donationForm, sublocation_id: v === '_none' ? '' : v})}>
                <SelectTrigger className="h-9"><SelectValue placeholder="Campus default" /></SelectTrigger>
                <SelectContent><SelectItem value="_none">Campus default</SelectItem>{subLocations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Notes *</Label>
              <Input placeholder="Notes (required)" value={donationForm.notes} onChange={e => setDonationForm({...donationForm, notes: e.target.value})} required />
            </div>
            {myChartAccounts.length > 0 && (
              <div className="space-y-2">
                <Label>Deposit To (Cash / Bank / Momo Account)</Label>
                <Select value={donationForm.deposit_to_account_id || '_none'} onValueChange={v => setDonationForm({...donationForm, deposit_to_account_id: v === '_none' ? '' : v})}>
                  <SelectTrigger className="h-9" data-testid="donation-deposit-to-select"><SelectValue placeholder="Which account received this?" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_none">— None —</SelectItem>
                    {myChartAccounts.map(a => (
                      <SelectItem key={a.id} value={a.id} data-testid={`deposit-to-opt-${a.id}`}>
                        {a.name} · {a.kind} · {a.currency} {(a.balance || 0).toLocaleString()}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowDonation(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving} data-testid="save-donation-btn">{saving ? 'Saving...' : 'Save Donation'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Add Expense Modal */}
      <Dialog open={showExpense} onOpenChange={setShowExpense}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Record Expense</DialogTitle></DialogHeader>
          <form onSubmit={handleAddExpense} className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Title *</Label>
              <Input placeholder="Expense title" value={expenseForm.title} onChange={e => setExpenseForm({...expenseForm, title: e.target.value})} required data-testid="expense-title-input" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Amount (UGX) *</Label>
                <Input type="number" placeholder="0" value={expenseForm.amount} onChange={e => setExpenseForm({...expenseForm, amount: e.target.value})} required data-testid="expense-amount-input" />
              </div>
              <div className="space-y-2">
                <Label>Category</Label>
                <Select value={expenseForm.category} onValueChange={v => setExpenseForm({...expenseForm, category: v})}>
                  <SelectTrigger data-testid="expense-category-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="salaries">Salaries</SelectItem>
                    <SelectItem value="utilities">Utilities</SelectItem>
                    <SelectItem value="supplies">Supplies</SelectItem>
                    <SelectItem value="maintenance">Maintenance</SelectItem>
                    <SelectItem value="programs">Programs</SelectItem>
                    <SelectItem value="general">General</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label>Date</Label>
              <Input type="date" value={expenseForm.date} onChange={e => setExpenseForm({...expenseForm, date: e.target.value})} />
            </div>
            <div className="space-y-2">
              <Label>Sub-Location</Label>
              <Select value={expenseForm.sublocation_id || '_none'} onValueChange={v => setExpenseForm({...expenseForm, sublocation_id: v === '_none' ? '' : v})}>
                <SelectTrigger className="h-9"><SelectValue placeholder="Campus default" /></SelectTrigger>
                <SelectContent><SelectItem value="_none">Campus default</SelectItem>{subLocations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            {myChartAccounts.length > 0 && (
              <div className="space-y-2">
                <Label>Paid From (Cash / Bank / Momo Account) *</Label>
                <Select value={expenseForm.paid_from_account_id || '_none'} onValueChange={v => setExpenseForm({...expenseForm, paid_from_account_id: v === '_none' ? '' : v})}>
                  <SelectTrigger className="h-9" data-testid="expense-paid-from-select"><SelectValue placeholder="Which account funded this?" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_none">— None —</SelectItem>
                    {myChartAccounts.map(a => {
                      const insufficient = (a.balance || 0) < (parseFloat(expenseForm.amount) || 0);
                      return (
                        <SelectItem key={a.id} value={a.id} data-testid={`paid-from-opt-${a.id}`}>
                          <span className={insufficient && expenseForm.amount ? 'text-amber-700' : ''}>
                            {a.name} · {a.kind} · {a.currency} {(a.balance || 0).toLocaleString()}{insufficient && expenseForm.amount ? ' ⚠︎ low' : ''}
                          </span>
                        </SelectItem>
                      );
                    })}
                  </SelectContent>
                </Select>
                {expenseForm.paid_from_account_id && (() => {
                  const acct = myChartAccounts.find(a => a.id === expenseForm.paid_from_account_id);
                  const amt = parseFloat(expenseForm.amount) || 0;
                  if (!acct) return null;
                  const remaining = (acct.balance || 0) - amt;
                  return (
                    <p className={`text-xs ${remaining < 0 ? 'text-red-600' : 'text-muted-foreground'}`} data-testid="expense-paid-from-balance-hint">
                      Balance after this expense: {acct.currency} {remaining.toLocaleString()}
                    </p>
                  );
                })()}
              </div>
            )}
            {myChartAccounts.length === 0 && (
              <p className="text-xs text-muted-foreground italic" data-testid="no-chart-accounts-hint">No cash accounts assigned to you yet. Ask an admin to assign one under Accounting → Cash Accounts.</p>
            )}
            <div className="space-y-2">
              <Label>Notes *</Label>
              <Input placeholder="Notes (required)" value={expenseForm.notes} onChange={e => setExpenseForm({...expenseForm, notes: e.target.value})} required />
            </div>
            {/* Extended fields aligned with Google Sheet import schema */}
            <details className="border border-border rounded-lg p-3">
              <summary className="text-xs font-semibold cursor-pointer text-muted-foreground">Advanced (Vendor, Account, Department, Budget)</summary>
              <div className="space-y-3 mt-3">
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1"><Label className="text-xs">Vendor/Payee</Label>
                    <Input className="h-8 text-xs" placeholder="e.g. Bulunzi Farm Supply" value={expenseForm.vendor} onChange={e => setExpenseForm({...expenseForm, vendor: e.target.value})} data-testid="expense-vendor-input" />
                  </div>
                  <div className="space-y-1"><Label className="text-xs">Receipt #</Label>
                    <Input className="h-8 text-xs" placeholder="e.g. 1946" value={expenseForm.receipt_number} onChange={e => setExpenseForm({...expenseForm, receipt_number: e.target.value})} />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1"><Label className="text-xs">Account (Source)</Label>
                    <Select value={expenseForm.account || '_none'} onValueChange={v => setExpenseForm({...expenseForm, account: v === '_none' ? '' : v})}>
                      <SelectTrigger className="h-8 text-xs" data-testid="expense-account-select"><SelectValue placeholder="Select..." /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_none">—</SelectItem>
                        <SelectItem value="CASH DRAWER">Cash Drawer</SelectItem>
                        <SelectItem value="MTN MOMO">MTN Mobile Money</SelectItem>
                        <SelectItem value="AIRTEL MONEY">Airtel Money</SelectItem>
                        <SelectItem value="BANK">Bank</SelectItem>
                        <SelectItem value="OTHER">Other</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1"><Label className="text-xs">Department</Label>
                    <Select value={expenseForm.department || '_none'} onValueChange={v => setExpenseForm({...expenseForm, department: v === '_none' ? '' : v})}>
                      <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="Select..." /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_none">—</SelectItem>
                        {['FARM','SHELTER','OUTREACH','ADMIN/OPS','SECURITY','EDUCATION','MAINTENANCE','MEDIA','HR','FINANCE'].map(d => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1"><Label className="text-xs">Budget Line</Label>
                    <Input className="h-8 text-xs" placeholder="e.g. Uganda Farm" value={expenseForm.budget_category} onChange={e => setExpenseForm({...expenseForm, budget_category: e.target.value})} />
                  </div>
                  <div className="space-y-1"><Label className="text-xs">USD Equivalent</Label>
                    <Input className="h-8 text-xs" type="number" step="0.01" placeholder="e.g. 45.12" value={expenseForm.usd_equivalent} onChange={e => setExpenseForm({...expenseForm, usd_equivalent: e.target.value})} />
                  </div>
                </div>
              </div>
            </details>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowExpense(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving} data-testid="save-expense-btn">{saving ? 'Saving...' : 'Save Expense'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Fund Distribution Dialog */}
      <Dialog open={showDistribute} onOpenChange={setShowDistribute}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Distribute Funds</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2"><Label>From Location *</Label>
              <Select value={distForm.from_location_id || '_none'} onValueChange={v => setDistForm({...distForm, from_location_id: v === '_none' ? '' : v})}>
                <SelectTrigger data-testid="dist-from-select"><SelectValue placeholder="Select source" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">Select...</SelectItem>
                  {allLocations.map(l => <SelectItem key={l.id} value={l.id}>{l.name} ({l.currency})</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2"><Label>To Location *</Label>
              <Select value={distForm.to_location_id || '_none'} onValueChange={v => setDistForm({...distForm, to_location_id: v === '_none' ? '' : v})}>
                <SelectTrigger data-testid="dist-to-select"><SelectValue placeholder="Select destination" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">Select...</SelectItem>
                  {allLocations.filter(l => l.id !== distForm.from_location_id).map(l => <SelectItem key={l.id} value={l.id}>{l.name} ({l.currency})</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Amount *</Label>
                <Input type="number" min="0" step="0.01" placeholder="0.00" value={distForm.amount} onChange={e => setDistForm({...distForm, amount: e.target.value})} data-testid="dist-amount" />
              </div>
              <div className="space-y-2"><Label>Currency</Label>
                <Input value={distForm.currency} onChange={e => setDistForm({...distForm, currency: e.target.value})} />
              </div>
            </div>
            <div className="space-y-2"><Label>Notes</Label>
              <Input placeholder="Transfer reason" value={distForm.notes} onChange={e => setDistForm({...distForm, notes: e.target.value})} />
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowDistribute(false)}>Cancel</Button>
              <Button className="flex-1" disabled={!distForm.from_location_id || !distForm.to_location_id || !distForm.amount} data-testid="dist-submit-btn"
                onClick={async () => {
                  try {
                    await financialApi.distributeFunds({...distForm, amount: parseFloat(distForm.amount)});
                    toast.success('Funds distributed!');
                    setShowDistribute(false);
                    setDistForm({ from_location_id: '', to_location_id: '', amount: '', currency: 'UGX', notes: '' });
                    fetchAll();
                  } catch { toast.error('Transfer failed'); }
                }}>Transfer Funds</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Financial Import/Export Modal */}
      <Dialog open={showImportExport} onOpenChange={setShowImportExport}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Financial Data Import / Export</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2">
              <Button className="w-full gap-2" variant="outline" onClick={handleFinancialExport} data-testid="financial-json-export-btn">
                <Download size={14} /> Export Donations & Expenses (JSON)
              </Button>
              <p className="text-xs text-muted-foreground">Downloads all financial data{locationFilter ? ' for selected location' : ''} as JSON</p>
            </div>
            <div className="border-t border-border pt-4 space-y-2">
              <Label>Import Financial Data (JSON)</Label>
              <Textarea rows={5} placeholder={'{\n  "donations": [{"donor_name": "John", "amount": 50000, "currency": "UGX", "date": "2026-01-15"}],\n  "expenses": [{"title": "Office Rent", "amount": 200000, "category": "rent", "date": "2026-01-15"}]\n}'}
                value={importData} onChange={e => setImportData(e.target.value)} data-testid="financial-import-input" />
              <Button className="w-full gap-2" onClick={handleFinancialImport} disabled={importingData || !importData.trim()} data-testid="financial-import-btn">
                <Upload size={14} /> {importingData ? 'Importing...' : 'Import Financial Data'}
              </Button>
            </div>
            <div className="border-t border-border pt-4 space-y-2">
              <Label className="flex items-center gap-2"><FileSpreadsheet size={14} /> Import from Google Sheet (CSV)</Label>
              <p className="text-xs text-muted-foreground">
                Paste CSV rows from your Google Sheet. Expected columns:
                <code className="block mt-1 bg-muted p-1.5 rounded text-[10px]">Date, Vendor, Purpose/Beneficiary/Notes, Reff./Receipt#, ACCOUNT, Department, Budget, TOTAL UGX, USD</code>
              </p>
              <div className="flex items-center gap-2">
                <Label className="text-xs">Type:</Label>
                <Select value={sheetType} onValueChange={setSheetType}>
                  <SelectTrigger className="h-8 text-xs w-32"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="expense">Expenses</SelectItem>
                    <SelectItem value="donation">Income/Donations</SelectItem>
                  </SelectContent>
                </Select>
                <Label className="text-xs ml-3">Status:</Label>
                <Select value={sheetStatus} onValueChange={setSheetStatus}>
                  <SelectTrigger className="h-8 text-xs w-32"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pending">Pending</SelectItem>
                    <SelectItem value="approved">Approved (skip review)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Textarea rows={6} placeholder={'Date,Vendor,Purpose/Beneficiary/Notes,Reff./Receipt#,ACCOUNT,Department,Budget,TOTAL UGX,USD\n01/01,Sr chicken company,400 chicks,190,CASH DRAWER,FARM,Uganda Farm,480000,134.68'}
                value={sheetCsv} onChange={e => setSheetCsv(e.target.value)} className="text-xs font-mono" data-testid="sheet-import-input" />
              <Button className="w-full gap-2" onClick={handleSheetImport} disabled={sheetImporting || !sheetCsv.trim()} data-testid="sheet-import-btn">
                <FileSpreadsheet size={14} /> {sheetImporting ? 'Importing...' : 'Import from Sheet'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Add Asset Dialog */}
      <Dialog open={showAssetForm} onOpenChange={setShowAssetForm}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Add Asset</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Asset Name</Label><Input value={assetForm.name} onChange={e => setAssetForm({...assetForm, name: e.target.value})} placeholder="e.g. Toyota Land Cruiser" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Purchase Value</Label><Input type="number" value={assetForm.value} onChange={e => setAssetForm({...assetForm, value: parseFloat(e.target.value) || 0})} /></div>
              <div className="space-y-2"><Label>Purchase Date</Label><Input type="date" value={assetForm.purchase_date} onChange={e => setAssetForm({...assetForm, purchase_date: e.target.value})} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Category</Label>
                <Select value={assetForm.category} onValueChange={v => setAssetForm({...assetForm, category: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="equipment">Equipment</SelectItem>
                    <SelectItem value="vehicle">Vehicle</SelectItem>
                    <SelectItem value="property">Property/Building</SelectItem>
                    <SelectItem value="furniture">Furniture</SelectItem>
                    <SelectItem value="technology">Technology</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Depreciation (years)</Label><Input type="number" min={1} max={50} value={assetForm.depreciation_years} onChange={e => setAssetForm({...assetForm, depreciation_years: parseInt(e.target.value) || 5})} /></div>
            </div>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => setShowAssetForm(false)}>Cancel</Button>
              <Button className="flex-1" onClick={async () => {
                try { await financialApi.createAsset({ ...assetForm, location_id: locationFilter }); setShowAssetForm(false); setAssetForm({ name: '', value: 0, category: 'equipment', purchase_date: '', depreciation_years: 5 }); fetchBalanceSheet(); toast.success('Asset added'); }
                catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
              }}>Add Asset</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Entry Dialog */}
      <Dialog open={!!editEntry} onOpenChange={v => { if (!v) setEditEntry(null); }}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Edit {editEntry?.type === 'donation' ? 'Donation' : 'Expense'}</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            {editEntry?.type === 'donation' ? (
              <>
                <div className="space-y-2"><Label>Donor Name</Label><Input value={editForm.donor_name || ''} onChange={e => setEditForm({...editForm, donor_name: e.target.value})} /></div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2"><Label>Amount</Label><Input type="number" value={editForm.amount || ''} onChange={e => setEditForm({...editForm, amount: parseFloat(e.target.value) || 0})} /></div>
                  <div className="space-y-2"><Label>Date</Label><Input type="date" value={editForm.date || ''} onChange={e => setEditForm({...editForm, date: e.target.value})} /></div>
                </div>
              </>
            ) : (
              <>
                <div className="space-y-2"><Label>Title</Label><Input value={editForm.title || ''} onChange={e => setEditForm({...editForm, title: e.target.value})} /></div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2"><Label>Amount</Label><Input type="number" value={editForm.amount || ''} onChange={e => setEditForm({...editForm, amount: parseFloat(e.target.value) || 0})} /></div>
                  <div className="space-y-2"><Label>Date</Label><Input type="date" value={editForm.date || ''} onChange={e => setEditForm({...editForm, date: e.target.value})} /></div>
                </div>
                <div className="space-y-2"><Label>Category</Label><Input value={editForm.category || ''} onChange={e => setEditForm({...editForm, category: e.target.value})} /></div>
              </>
            )}
            <div className="space-y-2"><Label>Notes</Label><Input value={editForm.notes || ''} onChange={e => setEditForm({...editForm, notes: e.target.value})} /></div>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => setEditEntry(null)}>Cancel</Button>
              <Button className="flex-1" onClick={async () => {
                try {
                  if (editEntry.type === 'donation') {
                    await financialApi.updateDonation(editEntry.id, editForm);
                    setDonations(prev => prev.map(d => d.id === editEntry.id ? { ...d, ...editForm } : d));
                  } else {
                    await financialApi.approveExpense(editEntry.id, editForm);
                    setExpenses(prev => prev.map(e => e.id === editEntry.id ? { ...e, ...editForm } : e));
                  }
                  toast.success('Updated'); setEditEntry(null);
                } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
              }}>Save</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Expense Rejection Dialog (replaces window.prompt) */}
      <Dialog open={!!rejectingExpense} onOpenChange={(o) => { if (!o) { setRejectingExpense(null); setRejectReason(''); } }}>
        <DialogContent className="max-w-md" data-testid="reject-expense-dialog">
          <DialogHeader>
            <DialogTitle>Reject expense</DialogTitle>
          </DialogHeader>
          {rejectingExpense && (
            <div className="space-y-3 mt-2">
              <div className="rounded-lg bg-muted/40 p-3 text-xs space-y-1">
                <p className="font-semibold text-sm">{rejectingExpense.title}</p>
                <p className="text-muted-foreground">
                  {rejectingExpense.currency} {Number(rejectingExpense.amount || 0).toLocaleString()} · {rejectingExpense.category} · {rejectingExpense.date}
                </p>
                {rejectingExpense.submitted_by && (
                  <p className="text-muted-foreground">Submitted by: {rejectingExpense.submitted_by}</p>
                )}
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Rejection reason <span className="text-muted-foreground font-normal">(optional, shown to submitter)</span></Label>
                <Textarea
                  rows={3}
                  value={rejectReason}
                  onChange={ev => setRejectReason(ev.target.value)}
                  placeholder="e.g. Missing receipt — please attach and resubmit"
                  data-testid="reject-expense-reason"
                />
              </div>
              <div className="flex gap-2 pt-1">
                <Button variant="ghost" className="flex-1" onClick={() => { setRejectingExpense(null); setRejectReason(''); }}>Cancel</Button>
                <Button
                  variant="destructive"
                  className="flex-1"
                  onClick={async () => {
                    const id = rejectingExpense.id;
                    try {
                      await financialApi.rejectExpense(id, rejectReason);
                      setExpenses(prev => prev.map(x => x.id === id ? { ...x, status: 'rejected' } : x));
                      toast.success('Expense rejected');
                      setRejectingExpense(null);
                      setRejectReason('');
                      fetchAll();
                    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
                  }}
                  data-testid="reject-expense-confirm"
                >
                  Reject expense
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Categories Management Dialog */}
      <Dialog open={showCategories} onOpenChange={setShowCategories}>
        <DialogContent className="max-w-md max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Financial Categories</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-2 max-h-60 overflow-auto">
              {categories.map(c => (
                <div key={c.id} className="flex items-center justify-between p-2 rounded-lg border border-border">
                  <div><p className="text-sm font-medium">{c.name}</p><Badge variant="outline" className="text-[10px]">{c.type}</Badge></div>
                  {isFinanceAdmin && <Button size="sm" variant="ghost" className="h-6 text-xs text-destructive" onClick={async () => { await financialApi.deleteCategory(c.id); setCategories(prev => prev.filter(x => x.id !== c.id)); toast.success('Deleted'); }}>Del</Button>}
                </div>
              ))}
            </div>
            {isFinanceAdmin && (
              <div className="border-t pt-3 space-y-2">
                <p className="text-xs font-semibold text-muted-foreground">Add Category</p>
                <div className="flex gap-2">
                  <Input className="flex-1 h-8 text-xs" placeholder="Category name" value={newCatName} onChange={e => setNewCatName(e.target.value)} data-testid="new-category-name" />
                  <Select value={newCatType} onValueChange={setNewCatType}>
                    <SelectTrigger className="w-24 h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="income">Income</SelectItem><SelectItem value="expense">Expense</SelectItem><SelectItem value="both">Both</SelectItem></SelectContent>
                  </Select>
                  <Button size="sm" className="h-8" disabled={!newCatName.trim()} onClick={async () => {
                    try { const res = await financialApi.createCategory({ name: newCatName.trim(), type: newCatType }); setCategories(prev => [...prev, res.data]); setNewCatName(''); toast.success('Added'); }
                    catch { toast.error('Failed'); }
                  }} data-testid="add-category-btn">Add</Button>
                </div>
              </div>
            )}
            <Button variant="outline" className="w-full" onClick={() => setShowCategories(false)}>Close</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Create Transfer Dialog */}
      <Dialog open={showTransfer} onOpenChange={setShowTransfer}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Create Inter-Account Transfer</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1">
              <Label className="text-xs">From Account</Label>
              <Select value={transferForm.from_account_id} onValueChange={v => setTransferForm({ ...transferForm, from_account_id: v })}>
                <SelectTrigger data-testid="transfer-from-select"><SelectValue placeholder="Select source account" /></SelectTrigger>
                <SelectContent>
                  {(subAccounts?.accounts || []).filter(a => a.id).map(a => <SelectItem key={a.id} value={a.id}>{a.location_name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">To Account</Label>
              <Select value={transferForm.to_account_id} onValueChange={v => setTransferForm({ ...transferForm, to_account_id: v })}>
                <SelectTrigger data-testid="transfer-to-select"><SelectValue placeholder="Select destination account" /></SelectTrigger>
                <SelectContent>
                  {(subAccounts?.accounts || []).filter(a => a.id && a.id !== transferForm.from_account_id).map(a => <SelectItem key={a.id} value={a.id}>{a.location_name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-xs">Amount</Label>
                <Input type="number" min={0} value={transferForm.amount} onChange={e => setTransferForm({ ...transferForm, amount: e.target.value })} data-testid="transfer-amount-input" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Currency</Label>
                <Input value={transferForm.currency} onChange={e => setTransferForm({ ...transferForm, currency: e.target.value.toUpperCase() })} />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Notes (optional)</Label>
              <Input value={transferForm.notes} onChange={e => setTransferForm({ ...transferForm, notes: e.target.value })} />
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowTransfer(false)}>Cancel</Button>
              <Button className="flex-1" data-testid="confirm-transfer-btn" onClick={async () => {
                if (!transferForm.from_account_id || !transferForm.to_account_id || !transferForm.amount) { toast.error('All fields required'); return; }
                try {
                  await financialApi.createTransfer({
                    from_account_id: transferForm.from_account_id,
                    to_account_id: transferForm.to_account_id,
                    amount: parseFloat(transferForm.amount),
                    currency: transferForm.currency || 'UGX',
                    notes: transferForm.notes,
                  });
                  toast.success('Transfer created');
                  setShowTransfer(false);
                  fetchAll();
                } catch { toast.error('Failed to create transfer'); }
              }}>Create</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Add Budget Dialog */}
      <Dialog open={showBudget} onOpenChange={setShowBudget}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Add Budget</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1">
              <Label className="text-xs">Department</Label>
              <Input value={budgetForm.department} onChange={e => setBudgetForm({ ...budgetForm, department: e.target.value })} data-testid="budget-department-input" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-xs">Period (YYYY-MM)</Label>
                <Input value={budgetForm.period} onChange={e => setBudgetForm({ ...budgetForm, period: e.target.value })} placeholder="2026-05" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Category</Label>
                <Select value={budgetForm.category} onValueChange={v => setBudgetForm({ ...budgetForm, category: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="general">General</SelectItem>
                    {(categories || []).filter(c => c.name).map(c => <SelectItem key={c.id || c.name} value={c.name}>{c.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Amount</Label>
              <Input type="number" min={0} value={budgetForm.amount} onChange={e => setBudgetForm({ ...budgetForm, amount: e.target.value })} data-testid="budget-amount-input" />
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowBudget(false)}>Cancel</Button>
              <Button className="flex-1" data-testid="confirm-budget-btn" onClick={async () => {
                if (!budgetForm.department || !budgetForm.amount) { toast.error('Department and amount required'); return; }
                try {
                  await financialApi.createBudget({
                    department: budgetForm.department,
                    period: budgetForm.period,
                    amount: parseFloat(budgetForm.amount),
                    category: budgetForm.category,
                  });
                  toast.success('Budget created');
                  setShowBudget(false);
                  fetchAll();
                } catch { toast.error('Failed to create budget'); }
              }}>Save Budget</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Revalue Asset Dialog */}
      <Dialog open={!!showRevalue} onOpenChange={(o) => { if (!o) setShowRevalue(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Revalue: {showRevalue?.name}</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1">
              <Label className="text-xs">New current value</Label>
              <Input type="number" value={revalueForm.current_value} onChange={e => setRevalueForm({ ...revalueForm, current_value: e.target.value })} data-testid="revalue-value-input" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Valuation method</Label>
              <Select value={revalueForm.method} onValueChange={v => setRevalueForm({ ...revalueForm, method: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="appreciation">Appreciation</SelectItem>
                  <SelectItem value="depreciation">Depreciation</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Notes (optional)</Label>
              <Input value={revalueForm.notes} onChange={e => setRevalueForm({ ...revalueForm, notes: e.target.value })} />
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowRevalue(null)}>Cancel</Button>
              <Button className="flex-1" data-testid="confirm-revalue-btn" onClick={async () => {
                try {
                  await financialApi.updateAssetValuation(showRevalue.id, {
                    current_value: parseFloat(revalueForm.current_value) || 0,
                    method: revalueForm.method,
                    notes: revalueForm.notes,
                  });
                  toast.success('Revalued');
                  setShowRevalue(null);
                  fetchBalanceSheet();
                } catch { toast.error('Failed'); }
              }}>Save</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Set Starting Balance Dialog */}
      <Dialog open={!!showStartingBal} onOpenChange={(o) => { if (!o) setShowStartingBal(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Starting Balance — {showStartingBal?.location_name}</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1">
              <Label className="text-xs">Starting Balance ({showStartingBal?.currency || currentCurrency})</Label>
              <Input type="number" value={startingBalValue} onChange={e => setStartingBalValue(e.target.value)} data-testid="starting-balance-input" />
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowStartingBal(null)}>Cancel</Button>
              <Button className="flex-1" data-testid="confirm-starting-balance-btn" onClick={async () => {
                if (!showStartingBal?.id) { toast.error('No account id'); return; }
                try {
                  await financialApi.updateAccount(showStartingBal.id, { starting_balance: parseFloat(startingBalValue) || 0 });
                  toast.success('Updated');
                  setShowStartingBal(null);
                  financialApi.accounts().then(r => setSubAccounts(r.data)).catch(() => {});
                } catch { toast.error('Failed'); }
              }}>Save</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Attach Receipt Dialog (replaces prompt) */}
      <Dialog open={!!showAttachReceipt} onOpenChange={(o) => { if (!o) { setShowAttachReceipt(null); setAttachReceiptUrl(''); } }}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Attach Receipt</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <p className="text-xs text-muted-foreground">Paste a receipt URL or image link for <span className="font-semibold">{showAttachReceipt?.title}</span>.</p>
            <div className="space-y-1">
              <Label className="text-xs">Receipt URL</Label>
              <Input type="url" placeholder="https://..." value={attachReceiptUrl} onChange={e => setAttachReceiptUrl(e.target.value)} data-testid="attach-receipt-url-input" autoFocus />
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => { setShowAttachReceipt(null); setAttachReceiptUrl(''); }}>Cancel</Button>
              <Button className="flex-1" data-testid="confirm-attach-receipt-btn" disabled={!attachReceiptUrl.trim()} onClick={async () => {
                try {
                  await attachReceipt(showAttachReceipt.id, attachReceiptUrl.trim());
                  setShowAttachReceipt(null);
                  setAttachReceiptUrl('');
                } catch { /* attachReceipt handles its own toast */ }
              }}>Save</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
