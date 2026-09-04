import React, { useEffect, useMemo, useState } from 'react';
import api from '../services/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { toast } from 'sonner';
import { RefreshCw, Plus, TrendingUp, TrendingDown, DollarSign, Wallet, AlertTriangle, Download, Search, X, Pencil, Trash2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const money = (n, cur = 'UGX') => new Intl.NumberFormat('en-US', { style: 'currency', currency: cur, maximumFractionDigits: 0 }).format(Number(n || 0));
const todayIso = () => new Date().toISOString().slice(0, 10);
const monthAgoIso = () => { const d = new Date(); d.setDate(d.getDate() - 30); return d.toISOString().slice(0, 10); };

// CSV export helper — client-side so a director tapping "Export" gets a file
// instantly without waiting on the server to render a spreadsheet.
function downloadCsv(filename, rows) {
  if (!rows.length) { toast.error('Nothing to export'); return; }
  const escape = v => {
    if (v == null) return '';
    const s = String(v).replace(/"/g, '""');
    return /[",\n]/.test(s) ? `"${s}"` : s;
  };
  const headers = Object.keys(rows[0]);
  const csv = [headers.join(','), ...rows.map(r => headers.map(h => escape(r[h])).join(','))].join('\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

export default function FinancePage() {
  const { user } = useAuth();
  const [tab, setTab] = useState('overview');

  return (
    <div className="p-6 max-w-[1400px] mx-auto space-y-6" data-testid="finance-page">
      <header className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Finance</h1>
          <p className="text-sm text-muted-foreground">One ledger. Every posting balanced. Reports read straight from the journal.</p>
        </div>
      </header>

      <Tabs value={tab} onValueChange={setTab} className="space-y-4">
        <TabsList className="grid grid-cols-4 max-w-2xl">
          <TabsTrigger value="overview" data-testid="finance-tab-overview">Overview</TabsTrigger>
          <TabsTrigger value="journal" data-testid="finance-tab-journal">Journal</TabsTrigger>
          <TabsTrigger value="coa" data-testid="finance-tab-coa">Chart of Accounts</TabsTrigger>
          <TabsTrigger value="reports" data-testid="finance-tab-reports">Reports</TabsTrigger>
        </TabsList>
        <TabsContent value="overview"><OverviewPanel /></TabsContent>
        <TabsContent value="journal"><JournalPanel /></TabsContent>
        <TabsContent value="coa"><CoaPanel /></TabsContent>
        <TabsContent value="reports"><ReportsPanel /></TabsContent>
      </Tabs>
    </div>
  );
}

// ─── OVERVIEW ────────────────────────────────────────────────
function OverviewPanel() {
  const [pnl, setPnl] = useState(null);
  const [bs, setBs] = useState(null);
  const [recent, setRecent] = useState([]);
  const [addOpen, setAddOpen] = useState(null); // 'expense' | 'income'

  const reload = async () => {
    const [p, b, r] = await Promise.all([
      api.get('/finance/reports/pnl'),
      api.get('/finance/reports/balance-sheet'),
      api.get('/finance/transactions/recent?limit=10'),
    ]);
    setPnl(p.data); setBs(b.data); setRecent(r.data);
  };
  useEffect(() => { reload().catch(() => {}); }, []);

  const cashOnHand = useMemo(
    () => (bs?.assets || []).filter(a => (a.code || '').startsWith('10')).reduce((s, a) => s + Number(a.amount || 0), 0),
    [bs],
  );

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard icon={<Wallet size={18} className="text-emerald-600" />} label="Cash & bank" value={money(cashOnHand)} testid="finance-stat-cash" />
        <StatCard icon={<TrendingUp size={18} className="text-blue-600" />} label="Revenue (all-time)" value={money(pnl?.total_revenue)} testid="finance-stat-revenue" />
        <StatCard icon={<TrendingDown size={18} className="text-amber-600" />} label="Expenses (all-time)" value={money(pnl?.total_expenses)} testid="finance-stat-expenses" />
        <StatCard icon={<DollarSign size={18} className="text-indigo-600" />} label="Net income" value={money(pnl?.net_income)} testid="finance-stat-net" tone={Number(pnl?.net_income || 0) < 0 ? 'red' : 'green'} />
      </div>

      <div className="flex gap-2 flex-wrap">
        <Button onClick={() => setAddOpen('expense')} data-testid="finance-add-expense" size="sm" variant="outline"><Plus size={14} className="mr-1" />Record expense</Button>
        <Button onClick={() => setAddOpen('income')} data-testid="finance-add-income" size="sm" variant="outline"><Plus size={14} className="mr-1" />Record income</Button>
        <BackfillButtons onDone={reload} />
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Recent activity</CardTitle></CardHeader>
        <CardContent>
          {recent.length === 0 ? <p className="text-sm text-muted-foreground">No entries yet — post an income or expense to get going.</p> : (
            <Table>
              <TableHeader><TableRow>
                <TableHead>Date</TableHead><TableHead>Description</TableHead><TableHead>Account</TableHead>
                <TableHead>Source</TableHead><TableHead className="text-right">Amount</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {recent.map(r => (
                  <TableRow key={r.id} data-testid={`recent-tx-${r.id}`}>
                    <TableCell className="font-mono text-xs">{r.date}</TableCell>
                    <TableCell>{r.description}</TableCell>
                    <TableCell>{r.account}</TableCell>
                    <TableCell><Badge variant="outline" className="text-[10px]">{r.source}</Badge></TableCell>
                    <TableCell className="text-right font-mono">{money(r.total)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <QuickPostDialog mode={addOpen} onClose={() => setAddOpen(null)} onDone={() => { setAddOpen(null); reload(); }} />
    </div>
  );
}

// ─── BACKFILL BUTTONS (admin-only) ───────────────────────────
// Sweep any pre-reset payroll / social payments into the new ledger. Both
// endpoints are idempotent so hitting either twice is safe.
function BackfillButtons({ onDone }) {
  const { user } = useAuth();
  const isAdmin = ['admin', 'system_admin'].includes(user?.role || '');
  const [busy, setBusy] = useState('');
  if (!isAdmin) return null;
  const run = async (kind) => {
    setBusy(kind);
    try {
      const url = kind === 'payroll' ? '/finance/admin/backfill-payroll' : '/finance/admin/backfill-social-payments';
      const r = await api.post(url);
      const s = r.data || {};
      toast.success(`${kind === 'payroll' ? 'Payroll' : 'Social payments'}: posted ${s.posted_or_replayed}, skipped ${s.skipped_no_amount ?? s.skipped ?? 0}, failed ${s.failed}`);
      onDone?.();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Backfill failed'); }
    setBusy('');
  };
  return (
    <>
      <Button size="sm" variant="outline" className="text-indigo-700 border-indigo-300 hover:bg-indigo-50" onClick={() => run('payroll')} disabled={!!busy} data-testid="finance-backfill-payroll">
        {busy === 'payroll' ? 'Posting…' : 'Post all paid payslips'}
      </Button>
      <Button size="sm" variant="outline" className="text-indigo-700 border-indigo-300 hover:bg-indigo-50" onClick={() => run('social')} disabled={!!busy} data-testid="finance-backfill-social">
        {busy === 'social' ? 'Posting…' : 'Post all social payments'}
      </Button>
    </>
  );
}

function StatCard({ icon, label, value, testid, tone }) {
  const toneClass = tone === 'red' ? 'text-red-700' : tone === 'green' ? 'text-emerald-700' : '';
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-2 text-xs text-muted-foreground uppercase tracking-wide">{icon}{label}</div>
        <div className={`text-2xl font-bold mt-1 ${toneClass}`} data-testid={testid}>{value}</div>
      </CardContent>
    </Card>
  );
}

// ─── QUICK POST DIALOG (expense/income) ──────────────────────
function QuickPostDialog({ mode, onClose, onDone }) {
  const isExpense = mode === 'expense';
  const isIncome = mode === 'income';
  const [accounts, setAccounts] = useState([]);
  const [form, setForm] = useState({ amount: '', account_id: '', paid_from_id: '', date: todayIso(), description: '' });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!mode) return;
    (async () => {
      const r = await api.get('/finance/chart-of-accounts');
      setAccounts(r.data || []);
    })().catch(() => {});
  }, [mode]);

  const filterType = isExpense ? 'expense' : 'revenue';
  const primary = accounts.filter(a => a.type === filterType);
  const cashAccounts = accounts.filter(a => a.type === 'asset');

  const submit = async () => {
    if (!form.amount || !form.account_id || !form.paid_from_id) { toast.error('Amount and both accounts are required'); return; }
    setBusy(true);
    try {
      const url = isExpense ? '/finance/transactions/expense' : '/finance/transactions/income';
      const payload = isExpense
        ? { amount: Number(form.amount), expense_account_id: form.account_id, paid_from_account_id: form.paid_from_id, date: form.date, description: form.description }
        : { amount: Number(form.amount), revenue_account_id: form.account_id, deposited_to_account_id: form.paid_from_id, date: form.date, description: form.description };
      await api.post(url, payload);
      toast.success(`${isExpense ? 'Expense' : 'Income'} recorded`);
      onDone();
      setForm({ amount: '', account_id: '', paid_from_id: '', date: todayIso(), description: '' });
    } catch (e) { toast.error(e?.response?.data?.detail || 'Failed to post'); }
    setBusy(false);
  };

  return (
    <Dialog open={!!mode} onOpenChange={o => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>{isExpense ? 'Record expense' : 'Record income'}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label>Amount</Label><Input data-testid="quick-post-amount" type="number" step="0.01" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} /></div>
          <div><Label>Date</Label><Input type="date" value={form.date} onChange={e => setForm({ ...form, date: e.target.value })} /></div>
          <div>
            <Label>{isExpense ? 'Expense account' : 'Revenue account'}</Label>
            <Select value={form.account_id} onValueChange={v => setForm({ ...form, account_id: v })}>
              <SelectTrigger data-testid="quick-post-account"><SelectValue placeholder="Choose account" /></SelectTrigger>
              <SelectContent>{primary.map(a => <SelectItem key={a.id} value={a.id}>{a.code} — {a.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label>{isExpense ? 'Paid from (cash/bank)' : 'Deposited to (cash/bank)'}</Label>
            <Select value={form.paid_from_id} onValueChange={v => setForm({ ...form, paid_from_id: v })}>
              <SelectTrigger data-testid="quick-post-paid-from"><SelectValue placeholder="Choose account" /></SelectTrigger>
              <SelectContent>{cashAccounts.map(a => <SelectItem key={a.id} value={a.id}>{a.code} — {a.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><Label>Description</Label><Input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="What was this for?" /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={submit} disabled={busy} data-testid="quick-post-submit">{busy ? 'Posting…' : 'Post'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── JOURNAL ─────────────────────────────────────────────────
function JournalPanel() {
  const { user } = useAuth();
  const canReverse = ['admin', 'system_admin', 'director'].includes(user?.role || '');
  const [entries, setEntries] = useState([]);
  const [expanded, setExpanded] = useState({});
  const [reversing, setReversing] = useState(null); // je object being reversed
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  // Filters — kept in the URL query string on submit so the exact list can be shared
  const [filters, setFilters] = useState({
    date_from: '',
    date_to: '',
    source: 'all',
    search: '',
    include_reversed: true,
  });

  const reload = async () => {
    const params = new URLSearchParams();
    params.set('limit', '200');
    params.set('include_reversed', String(filters.include_reversed));
    if (filters.date_from) params.set('date_from', filters.date_from);
    if (filters.date_to) params.set('date_to', filters.date_to);
    if (filters.source && filters.source !== 'all') params.set('source', filters.source);
    const r = await api.get(`/finance/journal?${params}`);
    setEntries(r.data || []);
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { reload().catch(() => {}); }, [filters.date_from, filters.date_to, filters.source, filters.include_reversed]);

  // Text search is client-side across description + line account names/codes
  // — cheap on 200 rows and lets staff type freeform without waiting for the
  // API on every keystroke.
  const filteredEntries = useMemo(() => {
    const q = filters.search.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter(je => {
      if ((je.description || '').toLowerCase().includes(q)) return true;
      if ((je.reference || '').toLowerCase().includes(q)) return true;
      if ((je.source || '').toLowerCase().includes(q)) return true;
      return (je.lines || []).some(ln =>
        (ln.account_name || '').toLowerCase().includes(q) ||
        (ln.account_code || '').toLowerCase().includes(q) ||
        (ln.memo || '').toLowerCase().includes(q));
    });
  }, [entries, filters.search]);

  const clearFilters = () => setFilters({ date_from: '', date_to: '', source: 'all', search: '', include_reversed: true });
  const activeFilterCount = ['date_from', 'date_to'].filter(k => filters[k]).length + (filters.source !== 'all' ? 1 : 0) + (filters.search ? 1 : 0);

  const exportJournal = () => {
    const rows = filteredEntries.flatMap(je =>
      (je.lines || []).map(ln => ({
        date: je.date, description: je.description, source: je.source, reference: je.reference || '',
        account_code: ln.account_code, account_name: ln.account_name,
        debit: ln.debit || '', credit: ln.credit || '',
        reversed: je.reversed ? 'YES' : '',
      })),
    );
    downloadCsv(`journal-${todayIso()}.csv`, rows);
  };

  const submitReverse = async () => {
    if (!reason.trim()) { toast.error('Please give a reason for the reversal'); return; }
    setBusy(true);
    try {
      await api.post(`/finance/journal/${reversing.id}/reverse`, { reason });
      toast.success('Journal entry reversed');
      setReversing(null); setReason('');
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Reversal failed'); }
    setBusy(false);
  };

  return (
    <Card>
      <CardHeader className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">Journal — most recent 200 {activeFilterCount > 0 && <Badge variant="outline" className="ml-2 text-[10px]">{activeFilterCount} filter{activeFilterCount > 1 ? 's' : ''}</Badge>}</CardTitle>
          <Button size="sm" variant="outline" onClick={exportJournal} disabled={filteredEntries.length === 0} data-testid="journal-export"><Download size={13} className="mr-1" />Export CSV</Button>
        </div>
        <div className="flex flex-wrap gap-2 items-end">
          <div className="relative">
            <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input value={filters.search} onChange={e => setFilters({ ...filters, search: e.target.value })} placeholder="Search description or account…" className="pl-7 w-64" data-testid="journal-search" />
          </div>
          <div><Label className="text-xs">Source</Label>
            <Select value={filters.source} onValueChange={v => setFilters({ ...filters, source: v })}>
              <SelectTrigger className="w-40" data-testid="journal-filter-source"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All sources</SelectItem>
                <SelectItem value="expense">Expense</SelectItem>
                <SelectItem value="income">Income</SelectItem>
                <SelectItem value="payroll">Payroll</SelectItem>
                <SelectItem value="sale">Sale</SelectItem>
                <SelectItem value="bank_tx">Bank</SelectItem>
                <SelectItem value="social_donation">Sponsorship</SelectItem>
                <SelectItem value="social_expense">Social expense</SelectItem>
                <SelectItem value="reversal">Reversal</SelectItem>
                <SelectItem value="manual">Manual</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div><Label className="text-xs">From</Label><Input type="date" value={filters.date_from} onChange={e => setFilters({ ...filters, date_from: e.target.value })} className="w-36" data-testid="journal-filter-from" /></div>
          <div><Label className="text-xs">To</Label><Input type="date" value={filters.date_to} onChange={e => setFilters({ ...filters, date_to: e.target.value })} className="w-36" data-testid="journal-filter-to" /></div>
          <label className="flex items-center gap-1.5 text-xs pb-2"><input type="checkbox" checked={filters.include_reversed} onChange={e => setFilters({ ...filters, include_reversed: e.target.checked })} /> Include reversed</label>
          {activeFilterCount > 0 && <Button size="sm" variant="ghost" onClick={clearFilters} data-testid="journal-clear-filters"><X size={13} className="mr-1" />Clear</Button>}
        </div>
      </CardHeader>
      <CardContent>
        {filteredEntries.length === 0 ? <p className="text-sm text-muted-foreground">No journal entries match.</p> : (
          <Table>
            <TableHeader><TableRow>
              <TableHead>Date</TableHead><TableHead>Description</TableHead><TableHead>Source</TableHead>
              <TableHead className="text-right">Total</TableHead>
              {canReverse && <TableHead className="w-28"></TableHead>}
            </TableRow></TableHeader>
            <TableBody>
              {filteredEntries.map(je => (
                <React.Fragment key={je.id}>
                  <TableRow className={`cursor-pointer hover:bg-muted/40 ${je.reversed ? 'opacity-50 line-through' : ''}`} onClick={() => setExpanded(e => ({ ...e, [je.id]: !e[je.id] }))} data-testid={`journal-row-${je.id}`}>
                    <TableCell className="font-mono text-xs">{je.date}</TableCell>
                    <TableCell>{je.description}{je.reversed && <Badge variant="outline" className="ml-2 text-[10px] text-red-700 border-red-300">REVERSED</Badge>}</TableCell>
                    <TableCell><Badge variant="outline" className="text-[10px]">{je.source}</Badge></TableCell>
                    <TableCell className="text-right font-mono">{money(je.total)}</TableCell>
                    {canReverse && (
                      <TableCell className="text-right no-underline" onClick={(e) => e.stopPropagation()}>
                        {!je.reversed && je.source !== 'reversal' && (
                          <Button size="sm" variant="ghost" className="text-red-700 hover:bg-red-50 h-7 text-xs no-underline" onClick={() => { setReversing(je); setReason(''); }} data-testid={`journal-reverse-${je.id}`}>
                            Reverse
                          </Button>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                  {expanded[je.id] && (
                    <TableRow><TableCell colSpan={canReverse ? 5 : 4} className="bg-muted/20 p-3">
                      <table className="w-full text-xs">
                        <thead><tr className="text-muted-foreground"><th className="text-left">Account</th><th className="text-right">Debit</th><th className="text-right">Credit</th></tr></thead>
                        <tbody>
                          {je.lines.map((ln, i) => (
                            <tr key={i}><td className="font-mono">{ln.account_code} — {ln.account_name}</td><td className="text-right font-mono">{ln.debit ? money(ln.debit) : ''}</td><td className="text-right font-mono">{ln.credit ? money(ln.credit) : ''}</td></tr>
                          ))}
                        </tbody>
                      </table>
                      {je.reversed_by_je && <p className="mt-2 text-[11px] text-red-700">Reversed by {je.reversed_by_je} ({je.reversed_reason || 'no reason'})</p>}
                    </TableCell></TableRow>
                  )}
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
      <Dialog open={!!reversing} onOpenChange={o => !o && setReversing(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Reverse journal entry</DialogTitle></DialogHeader>
          <p className="text-sm">Posting a reversal doesn&apos;t delete the original — it adds a mirror JE with debits/credits swapped so the audit trail is intact.</p>
          <div className="mt-3 space-y-3">
            <div className="text-xs bg-muted/40 p-2 rounded font-mono">
              {reversing?.date} · {reversing?.description} · {money(reversing?.total)}
            </div>
            <div>
              <Label>Reason (required)</Label>
              <Input value={reason} onChange={e => setReason(e.target.value)} placeholder="e.g. Wrong account picked" data-testid="reverse-reason-input" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReversing(null)} disabled={busy}>Cancel</Button>
            <Button variant="destructive" onClick={submitReverse} disabled={busy || !reason.trim()} data-testid="reverse-submit">{busy ? 'Reversing…' : 'Post reversal'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ─── CHART OF ACCOUNTS ───────────────────────────────────────
const BANK_SUBTYPES = [
  { value: '', label: '— Not a bank account —' },
  { value: 'cash', label: 'Cash' },
  { value: 'checking', label: 'Checking' },
  { value: 'savings', label: 'Savings' },
  { value: 'momo', label: 'Mobile Money' },
  { value: 'credit_card', label: 'Credit Card' },
];

function CoaPanel() {
  const [rows, setRows] = useState([]);
  const [balances, setBalances] = useState({});   // { account_id: balance }
  const [addOpen, setAddOpen] = useState(false);
  const [editRow, setEditRow] = useState(null);
  const [obRow, setObRow] = useState(null);
  const [obForm, setObForm] = useState({ amount: '', date: todayIso(), memo: '' });
  const [form, setForm] = useState({ code: '', name: '', type: 'expense', bank_subtype: '' });
  const reload = async () => {
    const [coaR, tbR] = await Promise.all([
      api.get('/finance/chart-of-accounts?active_only=false'),
      api.get('/finance/reports/trial-balance').catch(() => ({ data: { rows: [] } })),
    ]);
    setRows(coaR.data || []);
    setBalances(Object.fromEntries((tbR.data?.rows || []).map(r => [r.account_id || r.id, r.balance || 0])));
  };
  useEffect(() => { reload().catch(() => {}); }, []);

  const submit = async () => {
    if (!form.code || !form.name) { toast.error('Code and name required'); return; }
    try {
      await api.post('/finance/chart-of-accounts', {
        code: form.code, name: form.name, type: form.type,
        bank_subtype: form.bank_subtype || null,
        is_cash: !!form.bank_subtype,
      });
      toast.success('Account created'); setAddOpen(false);
      setForm({ code: '', name: '', type: 'expense', bank_subtype: '' });
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Create failed'); }
  };

  // iter 282 — Chart of Accounts was previously read-only. Now supports
  // inline edit (name / type / bank subtype), delete (falls back to
  // deactivate when journal entries reference the account), and one-click
  // opening balance so admins can seed real balances against `3000 Opening
  // Balance Equity` without leaving the page.
  const saveEdit = async () => {
    if (!editRow?.code || !editRow?.name) { toast.error('Code and name required'); return; }
    try {
      await api.put(`/finance/chart-of-accounts/${editRow.id}`, {
        code: editRow.code, name: editRow.name, type: editRow.type,
        bank_subtype: editRow.bank_subtype || null,
        is_cash: !!editRow.bank_subtype,
      });
      toast.success('Account updated'); setEditRow(null); reload();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Update failed'); }
  };

  const removeAccount = async (a) => {
    if (a.is_system) { toast.error('System accounts cannot be deleted — deactivate instead'); return; }
    if (!window.confirm(`Delete account "${a.code} ${a.name}"? Accounts referenced by journal entries will be deactivated instead.`)) return;
    try { const r = await api.delete(`/finance/chart-of-accounts/${a.id}`); toast.success(r.data?.deactivated ? 'Deactivated (had journal entries)' : 'Deleted'); reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || 'Delete failed'); }
  };

  const toggleActive = async (a) => {
    try { await api.put(`/finance/chart-of-accounts/${a.id}`, { active: !a.active }); toast.success(a.active ? 'Deactivated' : 'Activated'); reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || 'Failed'); }
  };

  const submitOpeningBalance = async () => {
    const amt = parseFloat(obForm.amount);
    if (!obRow || !(amt !== 0)) { toast.error('Amount required (positive or negative)'); return; }
    try {
      await api.post(`/finance/chart-of-accounts/${obRow.id}/opening-balance`, {
        amount: amt, date: obForm.date, memo: obForm.memo,
      });
      toast.success('Opening balance posted');
      setObRow(null); setObForm({ amount: '', date: todayIso(), memo: '' });
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Failed'); }
  };

  const bankLabel = (a) => (BANK_SUBTYPES.find(s => s.value === (a.bank_subtype || '')) || { label: '' }).label;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Chart of Accounts</CardTitle>
        <Button size="sm" onClick={() => setAddOpen(true)} data-testid="coa-add"><Plus size={14} className="mr-1" />Add account</Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow><TableHead>Code</TableHead><TableHead>Name</TableHead><TableHead>Type</TableHead><TableHead>Bank subtype</TableHead><TableHead className="text-right">Balance</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
          <TableBody>
            {rows.map(a => {
              const bal = balances[a.id] ?? 0;
              return (
              <TableRow key={a.id} data-testid={`coa-row-${a.code}`} className={!a.active ? 'opacity-50' : ''}>
                <TableCell className="font-mono">{a.code}</TableCell>
                <TableCell>{a.name}{a.is_system && <span className="ml-1 text-[10px] text-muted-foreground">🔒 system</span>}</TableCell>
                <TableCell><Badge variant="outline" className="text-[10px]">{a.type}</Badge></TableCell>
                <TableCell>{a.bank_subtype ? <Badge className="text-[10px] bg-sky-100 text-sky-700">{bankLabel(a)}</Badge> : (a.is_cash ? <Badge className="text-[10px] bg-sky-100 text-sky-700">Cash</Badge> : <span className="text-[10px] text-muted-foreground">—</span>)}</TableCell>
                <TableCell className={`text-right font-mono text-xs ${bal < 0 ? 'text-rose-600' : bal > 0 ? 'text-emerald-700' : 'text-muted-foreground'}`} data-testid={`coa-balance-${a.code}`}>
                  {bal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </TableCell>
                <TableCell>
                  <button
                    className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${a.active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'}`}
                    onClick={() => toggleActive(a)}
                    data-testid={`coa-toggle-active-${a.code}`}
                    title={a.active ? 'Click to deactivate' : 'Click to activate'}
                  >
                    {a.active ? 'Active' : 'Inactive'}
                  </button>
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    <Button size="sm" variant="outline" className="h-7 text-[10px] gap-1" onClick={() => { setObRow(a); setObForm({ amount: '', date: todayIso(), memo: `Opening balance — ${a.name}` }); }} data-testid={`coa-opening-${a.code}`}>
                      Opening
                    </Button>
                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setEditRow({ ...a })} data-testid={`coa-edit-${a.code}`} title="Edit"><Pencil size={12} /></Button>
                    {!a.is_system && (
                      <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" onClick={() => removeAccount(a)} data-testid={`coa-delete-${a.code}`} title="Delete"><Trash2 size={12} /></Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>

      {/* Add */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Add account</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Code</Label><Input value={form.code} onChange={e => setForm({ ...form, code: e.target.value })} placeholder="e.g. 5500" /></div>
            <div><Label>Name</Label><Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></div>
            <div>
              <Label>Type</Label>
              <Select value={form.type} onValueChange={v => setForm({ ...form, type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{['asset', 'liability', 'equity', 'revenue', 'expense'].map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label>Bank subtype (optional)</Label>
              <Select value={form.bank_subtype || '_none'} onValueChange={v => setForm({ ...form, bank_subtype: v === '_none' ? '' : v })}>
                <SelectTrigger data-testid="coa-add-bank-subtype"><SelectValue /></SelectTrigger>
                <SelectContent>{BANK_SUBTYPES.map(s => <SelectItem key={s.value || '_none'} value={s.value || '_none'}>{s.label}</SelectItem>)}</SelectContent>
              </Select>
              <p className="text-[10px] text-muted-foreground mt-1">Cash/Checking/Savings/Momo accounts show up in the Banking module & Deposit-To pickers.</p>
            </div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setAddOpen(false)}>Cancel</Button><Button onClick={submit} data-testid="coa-add-submit">Create</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit */}
      <Dialog open={!!editRow} onOpenChange={o => { if (!o) setEditRow(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Edit account {editRow?.code}</DialogTitle></DialogHeader>
          {editRow && (
            <div className="space-y-3">
              <div><Label>Code</Label><Input value={editRow.code} onChange={e => setEditRow({ ...editRow, code: e.target.value })} disabled={editRow.is_system} /></div>
              <div><Label>Name</Label><Input value={editRow.name} onChange={e => setEditRow({ ...editRow, name: e.target.value })} data-testid="coa-edit-name" /></div>
              <div>
                <Label>Type</Label>
                <Select value={editRow.type} onValueChange={v => setEditRow({ ...editRow, type: v })} disabled={editRow.is_system}>
                  <SelectTrigger data-testid="coa-edit-type"><SelectValue /></SelectTrigger>
                  <SelectContent>{['asset', 'liability', 'equity', 'revenue', 'expense'].map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <Label>Bank subtype</Label>
                <Select value={editRow.bank_subtype || '_none'} onValueChange={v => setEditRow({ ...editRow, bank_subtype: v === '_none' ? '' : v })}>
                  <SelectTrigger data-testid="coa-edit-bank-subtype"><SelectValue /></SelectTrigger>
                  <SelectContent>{BANK_SUBTYPES.map(s => <SelectItem key={s.value || '_none'} value={s.value || '_none'}>{s.label}</SelectItem>)}</SelectContent>
                </Select>
                <p className="text-[10px] text-muted-foreground mt-1">Picking any subtype flags this as a bank/cash account so it appears in the Banking module.</p>
              </div>
              {editRow.is_system && <p className="text-[11px] text-amber-700">Seed account — only the name and bank subtype can be changed.</p>}
            </div>
          )}
          <DialogFooter><Button variant="outline" onClick={() => setEditRow(null)}>Cancel</Button><Button onClick={saveEdit} data-testid="coa-edit-submit">Save</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Opening Balance */}
      <Dialog open={!!obRow} onOpenChange={o => { if (!o) setObRow(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Opening balance — {obRow?.code} {obRow?.name}</DialogTitle></DialogHeader>
          {obRow && (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">
                Posts a balanced journal against <span className="font-mono">3000 Opening Balance Equity</span>. Positive amounts debit for assets/expenses, credit for liabilities/equity/revenue.
              </p>
              <div><Label>Amount</Label><Input type="number" step="any" value={obForm.amount} onChange={e => setObForm({ ...obForm, amount: e.target.value })} placeholder="e.g. 5000" data-testid="coa-ob-amount" /></div>
              <div><Label>Date</Label><Input type="date" value={obForm.date} onChange={e => setObForm({ ...obForm, date: e.target.value })} /></div>
              <div><Label>Memo</Label><Input value={obForm.memo} onChange={e => setObForm({ ...obForm, memo: e.target.value })} /></div>
            </div>
          )}
          <DialogFooter><Button variant="outline" onClick={() => setObRow(null)}>Cancel</Button><Button onClick={submitOpeningBalance} data-testid="coa-ob-submit">Post</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ─── REPORTS ─────────────────────────────────────────────────
function ReportsPanel() {
  const [kind, setKind] = useState('pnl');
  const [dateFrom, setDateFrom] = useState(monthAgoIso());
  const [dateTo, setDateTo] = useState(todayIso());
  const [locationId, setLocationId] = useState('all');
  const [locations, setLocations] = useState([]);
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.get('/locations').then(r => setLocations(r.data || [])).catch(() => {}); }, []);

  const run = async () => {
    setBusy(true);
    try {
      const path = { pnl: 'pnl', bs: 'balance-sheet', tb: 'trial-balance', cf: 'cashflow' }[kind];
      const params = new URLSearchParams();
      if (kind === 'bs') { params.set('as_of', dateTo); }
      else { params.set('date_from', dateFrom); params.set('date_to', dateTo); }
      if (locationId && locationId !== 'all') params.set('location_id', locationId);
      const r = await api.get(`/finance/reports/${path}?${params}`);
      setData(r.data);
    } catch (e) { toast.error(e?.response?.data?.detail || 'Report failed'); }
    setBusy(false);
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { run(); }, [kind, locationId]);

  // Flatten whichever report is on screen into CSV rows. Each report has its
  // own row shape so the export matches what the user sees.
  const exportReport = () => {
    if (!data) return;
    const stamp = `${todayIso()}`;
    if (kind === 'pnl') {
      const rows = [
        ...data.revenue.map(r => ({ section: 'Revenue', code: r.code, name: r.name, amount: r.amount })),
        { section: 'Revenue', code: '', name: 'Total Revenue', amount: data.total_revenue },
        ...data.expenses.map(r => ({ section: 'Expense', code: r.code, name: r.name, amount: r.amount })),
        { section: 'Expense', code: '', name: 'Total Expenses', amount: data.total_expenses },
        { section: 'Summary', code: '', name: 'Net Income', amount: data.net_income },
      ];
      downloadCsv(`pnl-${stamp}.csv`, rows);
    } else if (kind === 'bs') {
      const rows = [
        ...data.assets.map(r => ({ section: 'Asset', code: r.code, name: r.name, amount: r.amount })),
        { section: 'Asset', code: '', name: 'Total Assets', amount: data.total_assets },
        ...data.liabilities.map(r => ({ section: 'Liability', code: r.code, name: r.name, amount: r.amount })),
        { section: 'Liability', code: '', name: 'Total Liabilities', amount: data.total_liabilities },
        ...data.equity.map(r => ({ section: 'Equity', code: r.code, name: r.name, amount: r.amount })),
        { section: 'Equity', code: '', name: 'Total Equity', amount: data.total_equity },
      ];
      downloadCsv(`balance-sheet-${stamp}.csv`, rows);
    } else if (kind === 'tb') {
      downloadCsv(`trial-balance-${stamp}.csv`, (data.rows || []).map(r => ({
        code: r.code, name: r.name, type: r.type, debit: r.debit, credit: r.credit,
      })));
    } else if (kind === 'cf') {
      downloadCsv(`cashflow-${stamp}.csv`, (data.lines || []).map(r => ({
        code: r.code, name: r.name, source: r.source, inflow: r.inflow, outflow: r.outflow, net: r.net,
      })));
    }
  };

  return (
    <Card>
      <CardHeader className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">Reports</CardTitle>
          <Button size="sm" variant="outline" onClick={exportReport} disabled={!data} data-testid="reports-export"><Download size={13} className="mr-1" />Export CSV</Button>
        </div>
        <div className="flex flex-wrap gap-2 items-end">
          <div><Label className="text-xs">Report</Label>
            <Select value={kind} onValueChange={setKind}>
              <SelectTrigger className="w-52" data-testid="reports-kind"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="pnl">Profit &amp; Loss</SelectItem>
                <SelectItem value="bs">Balance Sheet</SelectItem>
                <SelectItem value="tb">Trial Balance</SelectItem>
                <SelectItem value="cf">Cashflow</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div><Label className="text-xs">Campus</Label>
            <Select value={locationId} onValueChange={setLocationId}>
              <SelectTrigger className="w-52" data-testid="reports-location"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All campuses</SelectItem>
                {locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          {kind !== 'bs' && <div><Label className="text-xs">From</Label><Input type="date" className="w-40" value={dateFrom} onChange={e => setDateFrom(e.target.value)} /></div>}
          <div><Label className="text-xs">{kind === 'bs' ? 'As of' : 'To'}</Label><Input type="date" className="w-40" value={dateTo} onChange={e => setDateTo(e.target.value)} /></div>
          <Button onClick={run} disabled={busy} data-testid="reports-run"><RefreshCw size={14} className="mr-1" />Run</Button>
        </div>
      </CardHeader>
      <CardContent>{data && <ReportView kind={kind} data={data} />}</CardContent>
    </Card>
  );
}

function ReportView({ kind, data }) {
  if (kind === 'pnl') return <PnlView d={data} />;
  if (kind === 'bs') return <BsView d={data} />;
  if (kind === 'tb') return <TbView d={data} />;
  if (kind === 'cf') return <CfView d={data} />;
  return null;
}

function Section({ title, rows, total }) {
  return (
    <div>
      <div className="font-semibold text-sm mt-3 mb-1">{title}</div>
      {rows.length === 0 && <p className="text-xs text-muted-foreground">None.</p>}
      {rows.map(r => (
        <div key={r.account_id || r.code} className="flex justify-between py-1 border-b border-muted/40 text-sm">
          <span className="font-mono text-xs text-muted-foreground w-14">{r.code}</span>
          <span className="flex-1">{r.name}</span>
          <span className="font-mono">{money(r.amount)}</span>
        </div>
      ))}
      <div className="flex justify-between py-1 font-bold mt-1 border-t-2 border-muted">
        <span>Total {title}</span><span className="font-mono">{money(total)}</span>
      </div>
    </div>
  );
}

function PnlView({ d }) {
  return (
    <div className="space-y-4" data-testid="report-pnl">
      <Section title="Revenue" rows={d.revenue} total={d.total_revenue} />
      <Section title="Expenses" rows={d.expenses} total={d.total_expenses} />
      <div className={`flex justify-between py-2 border-t-4 font-bold text-lg ${d.net_income < 0 ? 'text-red-700' : 'text-emerald-700'}`}>
        <span>Net income</span><span className="font-mono">{money(d.net_income)}</span>
      </div>
    </div>
  );
}
function BsView({ d }) {
  return (
    <div className="space-y-4" data-testid="report-bs">
      <Section title="Assets" rows={d.assets} total={d.total_assets} />
      <Section title="Liabilities" rows={d.liabilities} total={d.total_liabilities} />
      <Section title="Equity" rows={d.equity} total={d.total_equity} />
      <div className={`flex justify-between py-2 border-t-4 font-bold text-lg ${d.balanced ? 'text-emerald-700' : 'text-red-700'}`}>
        <span>{d.balanced ? '✓ Balanced' : '⚠ NOT BALANCED'}</span>
        <span className="font-mono">Assets {money(d.total_assets)} = L+E {money(d.total_liab_equity)}</span>
      </div>
    </div>
  );
}
function TbView({ d }) {
  return (
    <div data-testid="report-tb">
      <Table>
        <TableHeader><TableRow><TableHead>Code</TableHead><TableHead>Name</TableHead><TableHead>Type</TableHead><TableHead className="text-right">Debit</TableHead><TableHead className="text-right">Credit</TableHead></TableRow></TableHeader>
        <TableBody>
          {d.rows.map(r => (
            <TableRow key={r.account_id}>
              <TableCell className="font-mono text-xs">{r.code}</TableCell>
              <TableCell>{r.name}</TableCell>
              <TableCell><Badge variant="outline" className="text-[10px]">{r.type}</Badge></TableCell>
              <TableCell className="text-right font-mono">{r.debit ? money(r.debit) : ''}</TableCell>
              <TableCell className="text-right font-mono">{r.credit ? money(r.credit) : ''}</TableCell>
            </TableRow>
          ))}
          <TableRow className={`font-bold ${d.balanced ? '' : 'bg-red-50'}`}>
            <TableCell colSpan={3}>{d.balanced ? '✓ Balanced' : '⚠ NOT BALANCED'}</TableCell>
            <TableCell className="text-right font-mono">{money(d.total_debit)}</TableCell>
            <TableCell className="text-right font-mono">{money(d.total_credit)}</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  );
}
function CfView({ d }) {
  return (
    <div data-testid="report-cf">
      {(d.lines || []).length === 0 ? <p className="text-sm text-muted-foreground">{d.note || 'No cash movement in the window.'}</p> : (
        <Table>
          <TableHeader><TableRow><TableHead>Account</TableHead><TableHead>Source</TableHead><TableHead className="text-right">Inflow</TableHead><TableHead className="text-right">Outflow</TableHead><TableHead className="text-right">Net</TableHead></TableRow></TableHeader>
          <TableBody>
            {d.lines.map((r, i) => (
              <TableRow key={i}>
                <TableCell className="font-mono text-xs">{r.code} — {r.name}</TableCell>
                <TableCell><Badge variant="outline" className="text-[10px]">{r.source}</Badge></TableCell>
                <TableCell className="text-right font-mono">{r.inflow ? money(r.inflow) : ''}</TableCell>
                <TableCell className="text-right font-mono">{r.outflow ? money(r.outflow) : ''}</TableCell>
                <TableCell className={`text-right font-mono font-semibold ${r.net < 0 ? 'text-red-700' : 'text-emerald-700'}`}>{money(r.net)}</TableCell>
              </TableRow>
            ))}
            <TableRow className="font-bold border-t-2">
              <TableCell colSpan={4}>Net change in cash</TableCell>
              <TableCell className={`text-right font-mono ${d.net_change < 0 ? 'text-red-700' : 'text-emerald-700'}`}>{money(d.net_change)}</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      )}
    </div>
  );
}

// ─── RESET (admin only) ──────────────────────────────────────
// Reset UI moved to Admin → Danger Zone (see AdminPage.jsx). Kept as a
// no-op placeholder to avoid churn if any test imports this file by path.
