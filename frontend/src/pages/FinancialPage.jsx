import React, { useState, useEffect } from 'react';
import { DollarSign, TrendingUp, TrendingDown, Wallet, Plus, Download, RefreshCw } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { financialApi, financialExtrasApi, exportApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const fmt = (n) => `UGX ${(n || 0).toLocaleString()}`;

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
  const today = new Date().toISOString().split('T')[0];
  const [donationForm, setDonationForm] = useState(() => ({ donor_name: '', amount: '', currency: 'UGX', type: 'tithe', date: new Date().toISOString().split('T')[0], notes: '' }));
  const [expenseForm, setExpenseForm] = useState(() => ({ title: '', amount: '', currency: 'UGX', category: 'general', date: new Date().toISOString().split('T')[0], notes: '' }));

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [sumRes, donRes, expRes, cfRes] = await Promise.all([
        financialApi.summary(),
        financialApi.donations({ limit: 50, date_from: dateFrom || undefined, date_to: dateTo || undefined }),
        financialApi.expenses({ limit: 50, date_from: dateFrom || undefined, date_to: dateTo || undefined }),
        financialExtrasApi.cashflow(cashflowMonths),
      ]);
      setSummary(sumRes.data);
      setDonations(donRes.data);
      setExpenses(expRes.data);
      setCashflowData(cfRes.data?.monthly || []);
    } catch { toast.error('Failed to load financial data'); }
    finally { setLoading(false); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchAll(); }, [dateFrom, dateTo, cashflowMonths]);

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
    const token = localStorage.getItem('5812_token');
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

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Financial Management</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Track donations, expenses, and cashflow</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchAll} data-testid="financial-refresh"><RefreshCw size={14} /></Button>
          <Button variant="outline" size="sm" onClick={downloadCSV} className="gap-2" data-testid="financial-export">
            <Download size={14} /> Export CSV
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
                    <thead><tr className="text-left border-b border-border">
                      <th className="pb-2 font-medium text-muted-foreground">Donor</th>
                      <th className="pb-2 font-medium text-muted-foreground">Amount</th>
                      <th className="pb-2 font-medium text-muted-foreground">Type</th>
                      <th className="pb-2 font-medium text-muted-foreground">Date</th>
                    </tr></thead>
                    <tbody className="divide-y divide-border">
                      {donations.map(d => (
                        <tr key={d.id} className="hover:bg-accent/30 transition-colors">
                          <td className="py-3 font-medium">{d.donor_name}</td>
                          <td className="py-3 text-green-600 font-semibold">{d.currency} {(d.amount||0).toLocaleString()}</td>
                          <td className="py-3"><span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${typeColors[d.type] || 'bg-slate-100 text-slate-700'}`}>{d.type}</span></td>
                          <td className="py-3 text-muted-foreground">{d.date}</td>
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
                    </tr></thead>
                    <tbody className="divide-y divide-border">
                      {expenses.map(e => (
                        <tr key={e.id} className="hover:bg-accent/30 transition-colors">
                          <td className="py-3 font-medium">{e.title}</td>
                          <td className="py-3 text-red-600 font-semibold">{e.currency} {(e.amount||0).toLocaleString()}</td>
                          <td className="py-3"><span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${expenseCategoryColors[e.category] || 'bg-slate-100 text-slate-700'}`}>{e.category}</span></td>
                          <td className="py-3 text-muted-foreground">{e.date}</td>
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
      </Tabs>

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
    </div>
  );
}
