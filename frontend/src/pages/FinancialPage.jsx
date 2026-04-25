import { secureStorage } from '../services/secureStorage';
import React, { useState, useEffect } from 'react';
import { DollarSign, TrendingUp, TrendingDown, Wallet, Plus, Download, Upload, RefreshCw } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { financialApi, financialExtrasApi, exportApi, locationsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import { BulkActionBar, exportToCSV, SelectCheckbox } from '../components/BulkActions';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

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
  const [selectedIds, setSelectedIds] = useState(new Set());
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
  const [showImportExport, setShowImportExport] = useState(false);
  const [importData, setImportData] = useState('');
  const [importingData, setImportingData] = useState(false);
  const today = new Date().toISOString().split('T')[0];

  const isFinanceAdmin = ['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director'].includes(user?.role);

  const currentCurrency = locationFilter ? (allLocations.find(l => l.id === locationFilter)?.currency || 'UGX') : 'USD';
  const fmt = (n) => `${currentCurrency} ${(n || 0).toLocaleString()}`;
  const [donationForm, setDonationForm] = useState(() => ({ donor_name: '', amount: '', currency: 'UGX', type: 'tithe', date: new Date().toISOString().split('T')[0], notes: '' }));
  const [expenseForm, setExpenseForm] = useState(() => ({ title: '', amount: '', currency: 'UGX', category: 'general', date: new Date().toISOString().split('T')[0], notes: '' }));

  // Default non-admin users to their campus
  useEffect(() => {
    if (!isFinanceAdmin && user?.location_id && !locationFilter) {
      setLocationFilter(user.location_id);
    }
  }, [user, isFinanceAdmin, locationFilter]);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [sumRes, donRes, expRes, cfRes] = await Promise.all([
        financialApi.summary(locationFilter || undefined),
        financialApi.donations({ limit: 50, date_from: dateFrom || undefined, date_to: dateTo || undefined, location_id: locationFilter || undefined }),
        financialApi.expenses({ limit: 50, date_from: dateFrom || undefined, date_to: dateTo || undefined, location_id: locationFilter || undefined }),
        financialExtrasApi.cashflow(cashflowMonths),
      ]);
      setSummary(sumRes.data);
      setDonations(donRes.data);
      setExpenses(expRes.data);
      setCashflowData(cfRes.data?.monthly || []);
    } catch { toast.error('Failed to load financial data'); }
    finally { setLoading(false); }
  };

  useEffect(() => { locationsApi.list().then(r => setAllLocations(r.data)).catch(() => {}); fetchPending(); }, []);
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
      setDonationForm({ donor_name: '', amount: '', currency: 'UGX', type: 'tithe', date: today, notes: '' });
      toast.success('Donation recorded!');
      fetchAll();
    } catch { toast.error('Failed to save donation'); }
    finally { setSaving(false); }
  };

  const handleAddExpense = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await financialApi.createExpense({ ...expenseForm, amount: parseFloat(expenseForm.amount) });
      setExpenses(prev => [res.data, ...prev]);
      setShowExpense(false);
      setExpenseForm({ title: '', amount: '', currency: 'UGX', category: 'general', date: today, notes: '' });
      toast.success('Expense recorded!');
      fetchAll();
    } catch { toast.error('Failed to save expense'); }
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

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Financial Management</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Track donations, expenses, and cashflow</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" size="sm" onClick={() => setShowDistribute(true)} className="gap-1.5" data-testid="distribute-funds-btn"><DollarSign size={14} /> Transfer</Button>
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
                    {selectedIds.size > 0 && <div className="mb-2"><BulkActionBar selectedIds={selectedIds} onClear={() => setSelectedIds(new Set())} onBulkExport={() => exportToCSV(donations.filter(d => selectedIds.has(d.id)), 'donations-export.csv')} /></div>}
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
                              {isFinanceAdmin && <Button size="sm" variant="ghost" className="h-6 text-xs text-destructive" onClick={async () => { if (!window.confirm('Delete this donation?')) return; try { await financialApi.deleteDonation(d.id); setDonations(prev => prev.filter(x => x.id !== d.id)); toast.success('Deleted'); } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); } }}>Del</Button>}
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
                  <table className="w-full text-sm">
                    <thead><tr className="text-left border-b border-border">
                      <th className="pb-2 font-medium text-muted-foreground">Title</th>
                      <th className="pb-2 font-medium text-muted-foreground">Amount</th>
                      <th className="pb-2 font-medium text-muted-foreground">Category</th>
                      <th className="pb-2 font-medium text-muted-foreground">Date</th>
                      <th className="pb-2 font-medium text-muted-foreground">Receipt</th>
                      <th className="pb-2 font-medium text-muted-foreground">Actions</th>
                    </tr></thead>
                    <tbody className="divide-y divide-border">
                      {expenses.map(e => (
                        <tr key={e.id} className="hover:bg-accent/30 transition-colors">
                          <td className="py-3 font-medium">{e.title}</td>
                          <td className="py-3 text-red-600 font-semibold">{e.currency} {(e.amount||0).toLocaleString()}</td>
                          <td className="py-3"><span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${expenseCategoryColors[e.category] || 'bg-slate-100 text-slate-700'}`}>{e.category}</span></td>
                          <td className="py-3 text-muted-foreground">{e.date}</td>
                          <td className="py-3">
                            {e.receipt_url ? (
                              <a href={e.receipt_url} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline">View</a>
                            ) : (
                              <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={() => {
                                const url = prompt('Paste receipt URL or image link:');
                                if (url) attachReceipt(e.id, url);
                              }}>Attach</Button>
                            )}
                          </td>
                          <td className="py-3">
                            <div className="flex gap-1">
                              <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={() => { setEditEntry({ ...e, type: 'expense' }); setEditForm({ title: e.title, amount: e.amount, currency: e.currency, category: e.category, date: e.date, notes: e.notes || '' }); }}>Edit</Button>
                              {isFinanceAdmin && <Button size="sm" variant="ghost" className="h-6 text-xs text-destructive" onClick={async () => { if (!window.confirm('Delete this expense?')) return; try { await financialApi.deleteExpense(e.id); setExpenses(prev => prev.filter(x => x.id !== e.id)); toast.success('Deleted'); } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); } }}>Del</Button>}
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
        <TabsContent value="balance" className="mt-4">
          {bsLoading ? (
            <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-20 bg-muted animate-pulse rounded-xl" />)}</div>
          ) : balanceSheet ? (
            <div className="space-y-4">
              <div className="grid sm:grid-cols-4 gap-4">
                <Card className="rounded-xl"><CardContent className="p-4 text-center"><p className="text-2xl font-bold text-green-600">{fmt(balanceSheet.total_income)}</p><p className="text-xs text-muted-foreground mt-1">Total Income ({balanceSheet.donation_count} donations)</p></CardContent></Card>
                <Card className="rounded-xl"><CardContent className="p-4 text-center"><p className="text-2xl font-bold text-blue-600">{fmt(balanceSheet.total_sales)}</p><p className="text-xs text-muted-foreground mt-1">Sales Revenue ({balanceSheet.sale_count} sales)</p></CardContent></Card>
                <Card className="rounded-xl"><CardContent className="p-4 text-center"><p className="text-2xl font-bold text-red-600">{fmt(balanceSheet.total_expenses)}</p><p className="text-xs text-muted-foreground mt-1">Total Expenses ({balanceSheet.expense_count})</p></CardContent></Card>
                <Card className="rounded-xl border-2 border-primary/20"><CardContent className="p-4 text-center"><p className={`text-2xl font-bold ${balanceSheet.net_balance >= 0 ? 'text-green-600' : 'text-red-600'}`}>{fmt(balanceSheet.net_balance)}</p><p className="text-xs text-muted-foreground mt-1">Net Balance</p></CardContent></Card>
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
                  {assets.length === 0 ? (
                    <p className="text-xs text-muted-foreground text-center py-4">No assets recorded. Track equipment, vehicles, property values here.</p>
                  ) : (
                    <table className="w-full text-sm">
                      <thead><tr className="text-left border-b"><th className="pb-2 text-xs text-muted-foreground">Asset</th><th className="pb-2 text-xs text-muted-foreground">Category</th><th className="pb-2 text-xs text-muted-foreground">Purchase Value</th><th className="pb-2 text-xs text-muted-foreground">Current Value</th><th className="pb-2 text-xs text-muted-foreground">Date</th>{isFinanceAdmin && <th className="pb-2 w-8"></th>}</tr></thead>
                      <tbody className="divide-y">
                        {assets.map(a => {
                          const age = a.purchase_date ? (new Date().getFullYear() - new Date(a.purchase_date).getFullYear()) : 0;
                          const depRate = a.depreciation_years > 0 ? 1 / a.depreciation_years : 0;
                          const currentVal = Math.max(0, (a.value || 0) * (1 - depRate * Math.min(age, a.depreciation_years || 5)));
                          return (
                            <tr key={a.id || a.name}>
                              <td className="py-2 font-medium">{a.name}</td>
                              <td className="py-2 text-muted-foreground capitalize">{a.category}</td>
                              <td className="py-2">{fmt(a.value)}</td>
                              <td className="py-2 text-blue-600">{fmt(currentVal)}</td>
                              <td className="py-2 text-muted-foreground">{a.purchase_date || '-'}</td>
                              {isFinanceAdmin && <td className="py-2"><Button size="sm" variant="ghost" className="h-6 text-xs text-destructive" onClick={async () => { if (!window.confirm(`Delete asset "${a.name}"?`)) return; try { await financialApi.deleteAsset(a.id); setAssets(prev => prev.filter(x => x.id !== a.id)); toast.success('Asset deleted'); } catch { toast.error('Failed'); } }} data-testid={`delete-asset-${a.id}`}>Del</Button></td>}
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
      </Tabs>

      {/* Rejection Comment Dialog */}
      <Dialog open={!!showApprovalComment} onOpenChange={() => setShowApprovalComment(null)}>
        <DialogContent className="max-w-sm">
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
        <DialogContent className="max-w-md">
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
              <Label>Notes</Label>
              <Input placeholder="Optional notes" value={donationForm.notes} onChange={e => setDonationForm({...donationForm, notes: e.target.value})} />
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowDonation(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving} data-testid="save-donation-btn">{saving ? 'Saving...' : 'Save Donation'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Add Expense Modal */}
      <Dialog open={showExpense} onOpenChange={setShowExpense}>
        <DialogContent className="max-w-md">
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
              <Label>Notes</Label>
              <Input placeholder="Optional notes" value={expenseForm.notes} onChange={e => setExpenseForm({...expenseForm, notes: e.target.value})} />
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowExpense(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving} data-testid="save-expense-btn">{saving ? 'Saving...' : 'Save Expense'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Fund Distribution Dialog */}
      <Dialog open={showDistribute} onOpenChange={setShowDistribute}>
        <DialogContent className="max-w-md">
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
        <DialogContent className="max-w-md">
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
              <Textarea rows={6} placeholder={'{\n  "donations": [{"donor_name": "John", "amount": 50000, "currency": "UGX", "date": "2026-01-15"}],\n  "expenses": [{"title": "Office Rent", "amount": 200000, "category": "rent", "date": "2026-01-15"}]\n}'}
                value={importData} onChange={e => setImportData(e.target.value)} data-testid="financial-import-input" />
              <Button className="w-full gap-2" onClick={handleFinancialImport} disabled={importingData || !importData.trim()} data-testid="financial-import-btn">
                <Upload size={14} /> {importingData ? 'Importing...' : 'Import Financial Data'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Add Asset Dialog */}
      <Dialog open={showAssetForm} onOpenChange={setShowAssetForm}>
        <DialogContent className="max-w-md">
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
        <DialogContent className="max-w-md">
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
    </div>
  );
}
