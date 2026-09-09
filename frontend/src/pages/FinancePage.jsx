import React, { useEffect, useMemo, useState, useRef } from 'react';
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
import { RefreshCw, Plus, TrendingUp, TrendingDown, DollarSign, Wallet, AlertTriangle, Download, Upload, Search, X, Pencil, Trash2, Camera } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import DepartmentPnlTab from '../components/DepartmentPnlTab';
import { sublocationsApi, departmentsApi, locationsApi } from '../services/api';
import { dataEvents } from '../services/dataEvents';
import Papa from 'papaparse';
import * as XLSX from 'xlsx';

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
        {/* Mobile-safe tab strip — on <md the tabs scroll horizontally instead
            of cramming into a 5-col grid (which caused label overlap at 390px). */}
        <TabsList className="w-full flex overflow-x-auto no-scrollbar md:grid md:grid-cols-7 md:max-w-4xl">
          <TabsTrigger value="overview" className="flex-shrink-0" data-testid="finance-tab-overview">Overview</TabsTrigger>
          <TabsTrigger value="journal" className="flex-shrink-0" data-testid="finance-tab-journal">Journal</TabsTrigger>
          <TabsTrigger value="review" className="flex-shrink-0" data-testid="finance-tab-review">Review Queue</TabsTrigger>
          <TabsTrigger value="coa" className="flex-shrink-0" data-testid="finance-tab-coa">Chart of Accounts</TabsTrigger>
          <TabsTrigger value="reports" className="flex-shrink-0" data-testid="finance-tab-reports">Reports</TabsTrigger>
          <TabsTrigger value="budgets" className="flex-shrink-0" data-testid="finance-tab-budgets">Budgets</TabsTrigger>
          <TabsTrigger value="dept-pnl" className="flex-shrink-0" data-testid="finance-tab-dept-pnl">Dept P&amp;L</TabsTrigger>
        </TabsList>
        <TabsContent value="overview"><OverviewPanel /></TabsContent>
        <TabsContent value="journal"><JournalPanel /></TabsContent>
        <TabsContent value="review"><ReviewQueuePanel /></TabsContent>
        <TabsContent value="coa"><CoaPanel /></TabsContent>
        <TabsContent value="reports"><ReportsPanel /></TabsContent>
        <TabsContent value="budgets"><BudgetsPanel /></TabsContent>
        <TabsContent value="dept-pnl"><DepartmentPnlTab /></TabsContent>
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
  const [transferOpen, setTransferOpen] = useState(false);
  const [receiptOpen, setReceiptOpen] = useState(false);

  const reload = async () => {
    const [p, b, r] = await Promise.all([
      api.get('/finance/reports/pnl'),
      api.get('/finance/reports/balance-sheet'),
      api.get('/finance/transactions/recent?limit=10'),
    ]);
    setPnl(p.data); setBs(b.data); setRecent(r.data);
  };
  useEffect(() => { reload().catch(() => {}); }, []);
  // iter-tx-refresh: any finance mutation from anywhere in the app pings
  // 'finance-changed' — refresh the recent-activity + stat cards so users
  // don't see stale totals after posting from the split dialog / transfer /
  // JE edit / receipt scan.
  useEffect(() => dataEvents.on('finance-changed', () => { reload().catch(() => {}); }), []);

  // iter 289 re-applied — sum EVERY active cash/bank/mobile-money account
  // (any asset flagged `is_cash: true`), not just accounts whose code starts
  // with "10". Bank accounts created via the Banking module get `is_cash` set
  // by their `bank_subtype`, and old-code aggregation missed Mobile Money +
  // savings accounts + any 5-digit chart pushed into the sub-1000 range.
  const cashOnHand = useMemo(
    () => (bs?.assets || []).filter(a => a.is_cash || (a.code || '').startsWith('10')).reduce((s, a) => s + Number(a.amount || 0), 0),
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
        <Button onClick={() => setTransferOpen(true)} data-testid="finance-add-transfer" size="sm" variant="outline"><RefreshCw size={14} className="mr-1" />Record transfer</Button>
        <Button onClick={() => setReceiptOpen(true)} data-testid="finance-scan-receipt" size="sm" variant="outline"><Camera size={14} className="mr-1" />Scan receipt</Button>
        <BackfillButtons onDone={reload} />
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Recent activity</CardTitle></CardHeader>
        <CardContent>
          {recent.length === 0 ? <p className="text-sm text-muted-foreground">No entries yet — post an income or expense to get going.</p> : (
            <div className="overflow-x-auto -mx-4 md:mx-0">
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
            </div>
          )}
        </CardContent>
      </Card>

      <QuickPostDialog mode={addOpen} onClose={() => setAddOpen(null)} onDone={() => { setAddOpen(null); reload(); }} />
      <TransferDialog open={transferOpen} onClose={() => setTransferOpen(false)} onDone={() => { setTransferOpen(false); reload(); }} />
      <ReceiptScanDialog open={receiptOpen} onClose={() => setReceiptOpen(false)} onDone={() => { setReceiptOpen(false); reload(); }} />
    </div>
  );
}

// ─── REVIEW QUEUE (draft / needs-review JEs from receipt scans) ────
// Reviewers see the OCR-drafted JEs, can reclassify a line's account (via a
// simple Select) and click Approve — which clears the `needs_review` flag.
// Reclassification hits PUT /finance/journal/{id} with the swapped lines,
// which the backend accepts as a full replace (reverse-and-repost path).
function ReviewQueuePanel() {
  const [rows, setRows] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [busyId, setBusyId] = useState(null);
  const [editing, setEditing] = useState(null); // { id, lines: [...] }

  const reload = async () => {
    const [q, coa] = await Promise.all([
      api.get('/finance/receipts/review-queue'),
      api.get('/finance/chart-of-accounts'),
    ]);
    setRows(q.data || []);
    setAccounts(coa.data || []);
  };
  useEffect(() => { reload().catch(() => {}); }, []);

  const approve = async (id) => {
    setBusyId(id);
    try {
      await api.put(`/finance/receipts/${id}/approve`);
      toast.success('Approved');
      await reload();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Approve failed'); }
    setBusyId(null);
  };

  const startEdit = (je) => setEditing({ id: je.id, lines: (je.lines || []).map(ln => ({ ...ln })) });
  const cancelEdit = () => setEditing(null);
  const swapAccount = (idx, acctId) => {
    const acct = accounts.find(a => a.id === acctId);
    if (!acct) return;
    setEditing(e => ({ ...e, lines: e.lines.map((ln, i) => i === idx ? { ...ln, account_id: acct.id, account_code: acct.code, account_name: acct.name } : ln) }));
  };
  const saveReclassify = async () => {
    if (!editing) return;
    setBusyId(editing.id);
    try {
      await api.put(`/finance/journal/${editing.id}`, { lines: editing.lines });
      toast.success('Reclassified — new JE posted');
      setEditing(null);
      await reload();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Reclassify failed'); }
    setBusyId(null);
  };

  return (
    <Card data-testid="review-queue-panel">
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="text-base">Receipt review queue</CardTitle>
          <p className="text-xs text-muted-foreground mt-1">
            Draft journal entries from receipt scans. Reclassify the account if the OCR guessed wrong, then approve.
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={() => reload().catch(() => {})} data-testid="review-queue-refresh"><RefreshCw size={14} className="mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground py-8 text-center" data-testid="review-queue-empty">
            No receipts waiting for review — the queue is clear.
          </p>
        ) : (
          <div className="overflow-x-auto -mx-4 md:mx-0">
          <Table>
            <TableHeader><TableRow>
              <TableHead>Date</TableHead>
              <TableHead>Description</TableHead>
              <TableHead>Lines</TableHead>
              <TableHead className="text-right">Total</TableHead>
              <TableHead className="w-56"></TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {rows.map(r => {
                const isEdit = editing?.id === r.id;
                const linesToShow = isEdit ? editing.lines : (r.lines || []);
                return (
                  <TableRow key={r.id} data-testid={`review-queue-row-${r.id}`}>
                    <TableCell className="font-mono text-xs">{r.date}</TableCell>
                    <TableCell className="max-w-xs">
                      <div className="font-medium text-sm">{r.description}</div>
                      {r.reference && <div className="text-[10px] text-muted-foreground font-mono">{r.reference}</div>}
                    </TableCell>
                    <TableCell>
                      <div className="space-y-1">
                        {linesToShow.map((ln, idx) => (
                          <div key={idx} className="flex items-center gap-2 text-xs">
                            <Badge variant={ln.debit > 0 ? 'default' : 'outline'} className="text-[9px] w-8 justify-center">
                              {ln.debit > 0 ? 'Dr' : 'Cr'}
                            </Badge>
                            {isEdit ? (
                              <Select value={ln.account_id} onValueChange={v => swapAccount(idx, v)}>
                                <SelectTrigger className="h-7 text-xs" data-testid={`review-queue-swap-${r.id}-${idx}`}>
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  {accounts.map(a => <SelectItem key={a.id} value={a.id}>{a.code} — {a.name}</SelectItem>)}
                                </SelectContent>
                              </Select>
                            ) : (
                              <span className="font-mono">{ln.account_code} — {ln.account_name}</span>
                            )}
                            <span className="font-mono ml-auto">{money(ln.debit || ln.credit)}</span>
                          </div>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell className="text-right font-mono">{money(r.total)}</TableCell>
                    <TableCell>
                      {isEdit ? (
                        <div className="flex gap-1 justify-end">
                          <Button size="sm" variant="ghost" onClick={cancelEdit} disabled={busyId === r.id} data-testid={`review-queue-cancel-${r.id}`}>Cancel</Button>
                          <Button size="sm" onClick={saveReclassify} disabled={busyId === r.id} data-testid={`review-queue-save-${r.id}`}>
                            {busyId === r.id ? 'Saving…' : 'Save & repost'}
                          </Button>
                        </div>
                      ) : (
                        <div className="flex gap-1 justify-end">
                          <Button size="sm" variant="outline" onClick={() => startEdit(r)} disabled={busyId === r.id} data-testid={`review-queue-reclass-${r.id}`}>
                            <Pencil size={12} className="mr-1" />Reclassify
                          </Button>
                          <Button size="sm" onClick={() => approve(r.id)} disabled={busyId === r.id} data-testid={`review-queue-approve-${r.id}`}>
                            {busyId === r.id ? 'Approving…' : 'Approve'}
                          </Button>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── RECEIPT SCAN DIALOG ─────────────────────────────────────
function ReceiptScanDialog({ open, onClose, onDone }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => { if (open) { setFile(null); setResult(null); } }, [open]);

  const submit = async () => {
    if (!file) { toast.error('Pick or snap a receipt first'); return; }
    setBusy(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await api.post('/finance/receipts/scan', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setResult(r.data);
      if (r.data?.journal_entry?.id) toast.success('Draft entry created — finance can now review');
      else if (r.data?.hint) toast.warning(r.data.hint);
    } catch (e) { toast.error(e?.response?.data?.detail || 'Scan failed'); }
    setBusy(false);
  };

  const closeAndReload = () => { setResult(null); setFile(null); onDone(); };

  return (
    <Dialog open={open} onOpenChange={o => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Scan receipt</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">Snap or upload a receipt — we OCR the image, pull out the vendor / date / amount, and drop a draft journal entry for finance to review. No AI, just Tesseract + regex.</p>
          <div>
            <Label className="text-xs">Receipt image or PDF</Label>
            <Input type="file" accept="image/*,application/pdf" capture="environment" onChange={e => setFile(e.target.files?.[0] || null)} data-testid="receipt-file-input" />
            {file && <p className="text-xs text-muted-foreground mt-1">{file.name} · {(file.size / 1024).toFixed(0)} KB</p>}
          </div>
          {result?.extracted && (
            <div className="rounded-md bg-muted/40 p-3 space-y-1 text-xs" data-testid="receipt-scan-result">
              <div><strong>Vendor:</strong> {result.extracted.vendor || '—'}</div>
              <div><strong>Date:</strong> {result.extracted.date || '—'}</div>
              <div><strong>Amount:</strong> {result.extracted.currency} {Number(result.extracted.amount || 0).toLocaleString()}</div>
              {result.journal_entry && (<div className="pt-1 border-t"><Badge variant="outline" className="text-[10px]">Draft posted · needs review</Badge> <span className="font-mono">{result.journal_entry.id}</span></div>)}
              {result.hint && <div className="text-amber-700 pt-1">{result.hint}</div>}
            </div>
          )}
        </div>
        <DialogFooter>
          {result ? (
            <Button onClick={closeAndReload} data-testid="receipt-done">Done</Button>
          ) : (
            <>
              <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
              <Button onClick={submit} disabled={busy || !file} data-testid="receipt-scan-submit">{busy ? 'Scanning…' : 'Scan & post draft'}</Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── TRANSFER DIALOG ─────────────────────────────────────────
// Optional txn-fee field lets users record a bank/wire fee inline. When a
// fee is present the JE has 3 lines: Dr destination `amount`, Dr fee-expense
// `fee`, Cr source (amount + fee) — source loses everything, destination
// receives net amount, fee flows to the chosen expense account.
function TransferDialog({ open, onClose, onDone }) {
  const { user } = useAuth();
  const defaultCampus = user?.active_campus_id || user?.location_id || '';
  const [accounts, setAccounts] = useState([]);
  const [locations, setLocations] = useState([]);
  const [subLocations, setSubLocations] = useState([]);
  const [form, setForm] = useState({ from_account_id: '', to_account_id: '', amount: '', date: todayIso(), description: '', reference: '', fee_amount: '', fee_account_id: '', location_id: defaultCampus });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    (async () => {
      const [r, lc] = await Promise.all([
        api.get('/finance/chart-of-accounts'),
        locationsApi.list().catch(() => ({ data: [] })),
      ]);
      setAccounts(r.data || []);
      setLocations((lc.data || []).filter(l => !l.parent_id));
    })().catch(() => {});
    setForm({ from_account_id: '', to_account_id: '', amount: '', date: todayIso(), description: '', reference: '', fee_amount: '', fee_account_id: '', location_id: defaultCampus });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Resolve sub-locations for the picked campus so users can tag transfers
  // down to a sub-campus (matches QuickPost). Same parent-vs-picked rule
  // that survives picking a sub-location without wiping the list.
  useEffect(() => {
    if (!form.location_id) { setSubLocations([]); return; }
    const picked = form.location_id;
    const parent = locations.find(l => l.id === picked)
      ? picked
      : (subLocations.find(s => s.id === picked)?.location_id || picked);
    sublocationsApi.list({ location_id: parent }).then(sl => {
      const list = sl.data || [];
      if (picked !== parent && !list.some(s => s.id === picked)) {
        list.push({ id: picked, name: '(picked sub-location)', location_id: parent });
      }
      setSubLocations(list);
    }).catch(() => setSubLocations([]));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.location_id]);

  const assetAccounts = accounts.filter(a => a.type === 'asset' && a.active !== false);
  const expenseAccounts = accounts.filter(a => a.type === 'expense' && a.active !== false);

  const submit = async () => {
    if (!form.from_account_id || !form.to_account_id || !form.amount) { toast.error('Source, destination and amount are required'); return; }
    if (form.from_account_id === form.to_account_id) { toast.error('Source and destination must be different'); return; }
    if (!form.location_id) { toast.error('Pick a campus / sub-location'); return; }
    const fee = Number(form.fee_amount || 0);
    if (fee > 0 && !form.fee_account_id) { toast.error('Pick a fee expense account when entering a fee'); return; }
    setBusy(true);
    try {
      await api.post('/finance/transfers', {
        from_account_id: form.from_account_id,
        to_account_id: form.to_account_id,
        amount: Number(form.amount),
        date: form.date,
        description: form.description,
        reference: form.reference,
        fee_amount: fee,
        fee_account_id: form.fee_account_id,
        location_id: form.location_id,
      });
      toast.success('Transfer recorded');
      dataEvents.emit('finance-changed', { source: 'transfer' });
      onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Failed to post'); }
    setBusy(false);
  };

  return (
    <Dialog open={open} onOpenChange={o => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Record transfer</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label>Amount</Label><Input data-testid="transfer-amount" type="number" step="0.01" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} /></div>
          <div><Label>Date</Label><Input type="date" value={form.date} onChange={e => setForm({ ...form, date: e.target.value })} /></div>

          {/* iter-transfer-loc: Campus / sub-location is REQUIRED on the
              backend — without this control the transfer POST always 400'd
              even though users had already picked the accounts, so nothing
              new appeared on the ledger but users saw a "posted" toast. */}
          <div>
            <Label>Campus / sub-location <span className="text-red-500">*</span></Label>
            <Select value={form.location_id} onValueChange={v => setForm({ ...form, location_id: v })}>
              <SelectTrigger data-testid="transfer-location"><SelectValue placeholder="Choose campus / sub-location" /></SelectTrigger>
              <SelectContent>
                {locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                {subLocations.map(s => <SelectItem key={s.id} value={s.id}>&nbsp;&nbsp;↳ {s.name}</SelectItem>)}
              </SelectContent>
            </Select>
            {defaultCampus === form.location_id && <p className="text-[10px] text-muted-foreground mt-1">Prefilled from your active campus</p>}
          </div>

          <div>
            <Label>From (source)</Label>
            <Select value={form.from_account_id} onValueChange={v => setForm({ ...form, from_account_id: v })}>
              <SelectTrigger data-testid="transfer-from"><SelectValue placeholder="Cash/bank source" /></SelectTrigger>
              <SelectContent>{assetAccounts.filter(a => a.id !== form.to_account_id).map(a => <SelectItem key={a.id} value={a.id}>{a.code} — {a.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label>To (destination)</Label>
            <Select value={form.to_account_id} onValueChange={v => setForm({ ...form, to_account_id: v })}>
              <SelectTrigger data-testid="transfer-to"><SelectValue placeholder="Cash/bank destination" /></SelectTrigger>
              <SelectContent>{assetAccounts.filter(a => a.id !== form.from_account_id).map(a => <SelectItem key={a.id} value={a.id}>{a.code} — {a.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div><Label>Fee (optional)</Label><Input data-testid="transfer-fee" type="number" step="0.01" value={form.fee_amount} onChange={e => setForm({ ...form, fee_amount: e.target.value })} placeholder="e.g. 500" /></div>
            <div>
              <Label>Fee expense account</Label>
              <Select value={form.fee_account_id} onValueChange={v => setForm({ ...form, fee_account_id: v })}>
                <SelectTrigger data-testid="transfer-fee-account"><SelectValue placeholder="—" /></SelectTrigger>
                <SelectContent>{expenseAccounts.map(a => <SelectItem key={a.id} value={a.id}>{a.code} — {a.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <div><Label>Reference / receipt #</Label><Input data-testid="transfer-ref" value={form.reference} onChange={e => setForm({ ...form, reference: e.target.value })} placeholder="Optional transaction / receipt id" /></div>
          <div><Label>Description</Label><Input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="Optional note (e.g. bank run, till top-up)" /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={submit} disabled={busy} data-testid="transfer-submit">{busy ? 'Posting…' : 'Post transfer'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
// iter-tx-scope: every JE must land on a campus (or sub-location) AND
// optionally a department so Dept P&L rollups stay accurate. Both fields
// are auto-prefilled from the current user (their active campus, then
// their primary department) so the common case is zero-click.
function QuickPostDialog({ mode, onClose, onDone }) {
  const { user } = useAuth();
  const isExpense = mode === 'expense';
  const isIncome = mode === 'income';
  const [accounts, setAccounts] = useState([]);
  const [locations, setLocations] = useState([]);
  const [subLocations, setSubLocations] = useState([]);
  const [departments, setDepartments] = useState([]);
  const defaultCampus = user?.active_campus_id || user?.location_id || '';
  const defaultDept = (user?.department_ids || [])[0] || '';
  const [form, setForm] = useState({
    amount: '', account_id: '', paid_from_id: '', date: todayIso(),
    description: '', reference: '', vendor: '',
    location_id: defaultCampus, department_id: defaultDept,
  });
  const [vendorMatches, setVendorMatches] = useState([]);
  const [busy, setBusy] = useState(false);
  // iter344j — Split mode. One transaction, N category rows + M cash rows.
  // Backend hit swaps from /transactions/expense to /finance/journal (custom JE).
  const [split, setSplit] = useState(false);
  const emptyLeg = () => ({ account_id: '', amount: '', memo: '' });
  const [primaryLegs, setPrimaryLegs] = useState([emptyLeg()]);   // expense/revenue side
  const [cashLegs, setCashLegs] = useState([emptyLeg()]);         // paid-from / deposited-to side
  const primarySum = primaryLegs.reduce((s, l) => s + (Number(l.amount) || 0), 0);
  const cashSum = cashLegs.reduce((s, l) => s + (Number(l.amount) || 0), 0);
  const balanced = split && primarySum > 0 && Math.abs(primarySum - cashSum) < 0.01;

  useEffect(() => {
    if (!mode) return;
    (async () => {
      const [ac, lc] = await Promise.all([
        api.get('/finance/chart-of-accounts'),
        locationsApi.list().catch(() => ({ data: [] })),
      ]);
      setAccounts(ac.data || []);
      setLocations((lc.data || []).filter(l => !l.parent_id));
    })().catch(() => {});
    // Reset form to prefilled defaults whenever the dialog opens.
    setForm({
      amount: '', account_id: '', paid_from_id: '', date: todayIso(),
      description: '', reference: '', vendor: '',
      location_id: defaultCampus, department_id: defaultDept,
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  // When campus changes, refetch its sub-locations + departments.
  // iter344g — resolve to top-level parent when the picked value is a
  // sub-location so we don't overwrite the list with an empty children
  // response for the just-picked row.
  useEffect(() => {
    if (!form.location_id) { setSubLocations([]); setDepartments([]); return; }
    const picked = form.location_id;
    const parent = locations.find(l => l.id === picked)
      ? picked
      : (subLocations.find(s => s.id === picked)?.location_id || picked);
    Promise.all([
      sublocationsApi.list({ location_id: parent }).catch(() => ({ data: [] })),
      departmentsApi.list({ location_id: parent }).catch(() => ({ data: [] })),
    ]).then(([sl, dp]) => {
      const list = sl.data || [];
      if (picked !== parent && !list.some(s => s.id === picked)) {
        list.push({ id: picked, name: '(picked sub-location)', location_id: parent });
      }
      setSubLocations(list);
      setDepartments(dp.data || []);
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.location_id]);

  const filterType = isExpense ? 'expense' : 'revenue';
  const primary = accounts.filter(a => a.type === filterType);
  const cashAccounts = accounts.filter(a => a.type === 'asset');

  const submit = async () => {
    // Split-mode branch — post directly to /finance/journal so the caller
    // can debit N expense accounts and credit M cash accounts (or the
    // inverse for income) in a single balanced JE.
    if (split) {
      if (!form.location_id) { toast.error('Pick a campus / sub-location'); return; }
      const validPrimary = primaryLegs.filter(l => l.account_id && Number(l.amount) > 0);
      const validCash = cashLegs.filter(l => l.account_id && Number(l.amount) > 0);
      if (!validPrimary.length || !validCash.length) { toast.error('Add at least one category row and one cash row'); return; }
      if (Math.abs(primarySum - cashSum) >= 0.01) { toast.error(`Debits/credits mismatch: ${primarySum.toFixed(2)} vs ${cashSum.toFixed(2)}`); return; }
      setBusy(true);
      try {
        const idx = (id) => accounts.find(a => a.id === id) || {};
        // Expense JE: debit expense accounts, credit cash accounts.
        // Income JE:  debit cash accounts,    credit revenue accounts.
        const lines = isExpense ? [
          ...validPrimary.map(l => { const a = idx(l.account_id); return { account_id: a.id, account_code: a.code, account_name: a.name, debit: Number(l.amount), credit: 0, memo: l.memo || '' }; }),
          ...validCash.map(l => { const a = idx(l.account_id); return { account_id: a.id, account_code: a.code, account_name: a.name, debit: 0, credit: Number(l.amount), memo: l.memo || '' }; }),
        ] : [
          ...validCash.map(l => { const a = idx(l.account_id); return { account_id: a.id, account_code: a.code, account_name: a.name, debit: Number(l.amount), credit: 0, memo: l.memo || '' }; }),
          ...validPrimary.map(l => { const a = idx(l.account_id); return { account_id: a.id, account_code: a.code, account_name: a.name, debit: 0, credit: Number(l.amount), memo: l.memo || '' }; }),
        ];
        await api.post('/finance/journal', {
          date: form.date,
          description: form.description || (isExpense ? 'Split expense' : 'Split income'),
          reference: form.reference,
          location_id: form.location_id,
          department_id: form.department_id || null,
          vendor: form.vendor || null,
          lines,
        });
        toast.success(`Split ${isExpense ? 'expense' : 'income'} recorded (${validPrimary.length}×${validCash.length} lines)`);
        // iter-tx-refresh: broadcast so JournalPanel / OverviewPanel refetch
        // when a split JE is posted from the QuickPost dialog — previously
        // only the caller's own `onDone` ran, so the Journal tab still
        // rendered stale data even though the account balances had moved.
        dataEvents.emit('finance-changed', { source: isExpense ? 'expense_split' : 'income_split' });
        onDone();
      } catch (e) { toast.error(e?.response?.data?.detail || 'Failed to post split entry'); }
      setBusy(false);
      return;
    }
    if (!form.amount || !form.account_id || !form.paid_from_id) { toast.error('Amount and both accounts are required'); return; }
    if (!form.location_id) { toast.error('Pick a campus / sub-location'); return; }
    setBusy(true);
    try {
      const url = isExpense ? '/finance/transactions/expense' : '/finance/transactions/income';
      const shared = {
        amount: Number(form.amount), date: form.date,
        description: form.description, reference: form.reference,
        location_id: form.location_id,
        department_id: form.department_id || undefined,
        // iter344h — pass vendor free-text so the backend auto-upserts
        // and returns a linked vendor_id on the resulting expense.
        vendor: form.vendor || undefined,
      };
      const payload = isExpense
        ? { ...shared, expense_account_id: form.account_id, paid_from_account_id: form.paid_from_id }
        : { ...shared, revenue_account_id: form.account_id, deposited_to_account_id: form.paid_from_id };
      await api.post(url, payload);
      toast.success(`${isExpense ? 'Expense' : 'Income'} recorded`);
      dataEvents.emit('finance-changed', { source: isExpense ? 'expense' : 'income' });
      onDone();
      setForm({
        amount: '', account_id: '', paid_from_id: '', date: todayIso(),
        description: '', reference: '', vendor: '',
        location_id: defaultCampus, department_id: defaultDept,
      });
    } catch (e) { toast.error(e?.response?.data?.detail || 'Failed to post'); }
    setBusy(false);
  };

  return (
    <Dialog open={!!mode} onOpenChange={o => !o && onClose()}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between">
            <span>{isExpense ? 'Record expense' : 'Record income'}</span>
            <label className="flex items-center gap-2 text-xs font-normal" data-testid="split-toggle-wrapper">
              <input type="checkbox" checked={split} onChange={e => setSplit(e.target.checked)} data-testid="quick-post-split-toggle" />
              Split across multiple accounts
            </label>
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          {!split && <div><Label>Amount</Label><Input data-testid="quick-post-amount" type="number" step="0.01" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} /></div>}
          <div><Label>Date</Label><Input type="date" value={form.date} onChange={e => setForm({ ...form, date: e.target.value })} /></div>

          {/* Campus / sub-location — required, defaults to user's active campus */}
          <div>
            <Label>Campus / sub-location <span className="text-red-500">*</span></Label>
            <Select value={form.location_id} onValueChange={v => setForm({ ...form, location_id: v, department_id: '' })}>
              <SelectTrigger data-testid="quick-post-location"><SelectValue placeholder="Choose campus / sub-location" /></SelectTrigger>
              <SelectContent>
                {locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                {subLocations.map(s => <SelectItem key={s.id} value={s.id}>&nbsp;&nbsp;↳ {s.name}</SelectItem>)}
              </SelectContent>
            </Select>
            {defaultCampus === form.location_id && <p className="text-[10px] text-muted-foreground mt-1">Prefilled from your active campus</p>}
          </div>

          {/* Department — optional cost-centre tag */}
          {departments.length > 0 && (
            <div>
              <Label>Department (optional)</Label>
              <Select value={form.department_id || '_none'} onValueChange={v => setForm({ ...form, department_id: v === '_none' ? '' : v })}>
                <SelectTrigger data-testid="quick-post-department"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">— No department —</SelectItem>
                  {departments.map(d => (
                    <SelectItem key={d.id} value={d.id}>
                      <span className="inline-flex items-center gap-1.5">
                        {d.color && <span className="w-2 h-2 rounded-full inline-block" style={{ background: d.color }} />}
                        {d.name}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {defaultDept && defaultDept === form.department_id && <p className="text-[10px] text-muted-foreground mt-1">Prefilled from your primary department</p>}
            </div>
          )}

          <div>
            <Label>{isExpense ? 'Expense account' : 'Revenue account'}</Label>
            {split ? (
              <div className="space-y-1.5" data-testid="split-primary-legs">
                {primaryLegs.map((leg, i) => (
                  <div key={i} className="grid grid-cols-[1fr_100px_28px] gap-1.5 items-center" data-testid={`split-primary-row-${i}`}>
                    <Select value={leg.account_id} onValueChange={v => setPrimaryLegs(rows => rows.map((r, j) => j === i ? { ...r, account_id: v } : r))}>
                      <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="Account" /></SelectTrigger>
                      <SelectContent>{primary.map(a => <SelectItem key={a.id} value={a.id}>{a.code} — {a.name}</SelectItem>)}</SelectContent>
                    </Select>
                    <Input type="number" step="0.01" placeholder="Amount" className="h-8 text-xs" value={leg.amount} onChange={e => setPrimaryLegs(rows => rows.map((r, j) => j === i ? { ...r, amount: e.target.value } : r))} data-testid={`split-primary-amount-${i}`} />
                    <Button variant="ghost" size="sm" className="h-8 w-8 p-0 text-destructive" disabled={primaryLegs.length === 1} onClick={() => setPrimaryLegs(rows => rows.filter((_, j) => j !== i))}>×</Button>
                  </div>
                ))}
                <Button variant="outline" size="sm" className="h-7 text-xs w-full" onClick={() => setPrimaryLegs(rows => [...rows, emptyLeg()])} data-testid="split-add-primary">+ Add {isExpense ? 'expense' : 'revenue'} line</Button>
              </div>
            ) : (
              <Select value={form.account_id} onValueChange={v => setForm({ ...form, account_id: v })}>
                <SelectTrigger data-testid="quick-post-account"><SelectValue placeholder="Choose account" /></SelectTrigger>
                <SelectContent>{primary.map(a => <SelectItem key={a.id} value={a.id}>{a.code} — {a.name}</SelectItem>)}</SelectContent>
              </Select>
            )}
          </div>
          <div>
            <Label>{isExpense ? 'Paid from (cash/bank)' : 'Deposited to (cash/bank)'}</Label>
            {split ? (
              <div className="space-y-1.5" data-testid="split-cash-legs">
                {cashLegs.map((leg, i) => (
                  <div key={i} className="grid grid-cols-[1fr_100px_28px] gap-1.5 items-center" data-testid={`split-cash-row-${i}`}>
                    <Select value={leg.account_id} onValueChange={v => setCashLegs(rows => rows.map((r, j) => j === i ? { ...r, account_id: v } : r))}>
                      <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="Cash / bank" /></SelectTrigger>
                      <SelectContent>{cashAccounts.map(a => <SelectItem key={a.id} value={a.id}>{a.code} — {a.name}</SelectItem>)}</SelectContent>
                    </Select>
                    <Input type="number" step="0.01" placeholder="Amount" className="h-8 text-xs" value={leg.amount} onChange={e => setCashLegs(rows => rows.map((r, j) => j === i ? { ...r, amount: e.target.value } : r))} data-testid={`split-cash-amount-${i}`} />
                    <Button variant="ghost" size="sm" className="h-8 w-8 p-0 text-destructive" disabled={cashLegs.length === 1} onClick={() => setCashLegs(rows => rows.filter((_, j) => j !== i))}>×</Button>
                  </div>
                ))}
                <Button variant="outline" size="sm" className="h-7 text-xs w-full" onClick={() => setCashLegs(rows => [...rows, emptyLeg()])} data-testid="split-add-cash">+ Add cash / bank line</Button>
                <div className={`text-[11px] mt-1 px-2 py-1 rounded ${balanced ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-700'}`} data-testid="split-balance-badge">
                  {isExpense ? 'Debits' : 'Credits'} {primarySum.toFixed(2)} · {isExpense ? 'Credits' : 'Debits'} {cashSum.toFixed(2)} {balanced ? '· balanced ✓' : `· off by ${(primarySum - cashSum).toFixed(2)}`}
                </div>
              </div>
            ) : (
              <Select value={form.paid_from_id} onValueChange={v => setForm({ ...form, paid_from_id: v })}>
                <SelectTrigger data-testid="quick-post-paid-from"><SelectValue placeholder="Choose account" /></SelectTrigger>
                <SelectContent>{cashAccounts.map(a => <SelectItem key={a.id} value={a.id}>{a.code} — {a.name}</SelectItem>)}</SelectContent>
              </Select>
            )}
          </div>
          <div><Label>Reference / receipt #</Label><Input data-testid="quick-post-ref" value={form.reference} onChange={e => setForm({ ...form, reference: e.target.value })} placeholder="Optional transaction / receipt id" /></div>
          {isExpense && (
            <div className="relative">
              <Label>Vendor</Label>
              <Input
                data-testid="quick-post-vendor"
                value={form.vendor || ''}
                placeholder="Start typing a vendor name…"
                onChange={async e => {
                  const v = e.target.value;
                  setForm({ ...form, vendor: v });
                  if (v && v.length >= 1) {
                    try {
                      const { vendorsApi } = await import('../services/api');
                      const r = await vendorsApi.suggest(v);
                      setVendorMatches(r.data || []);
                    } catch { setVendorMatches([]); }
                  } else setVendorMatches([]);
                }}
                onBlur={() => setTimeout(() => setVendorMatches([]), 200)}
              />
              {vendorMatches.length > 0 && (
                <div className="absolute z-50 left-0 right-0 top-full mt-1 border rounded-lg bg-popover shadow max-h-48 overflow-y-auto" data-testid="vendor-suggest-list">
                  {vendorMatches.map(v => (
                    <button key={v.id} type="button" className="w-full text-left px-3 py-1.5 text-xs hover:bg-accent" onClick={() => { setForm(f => ({ ...f, vendor: v.name })); setVendorMatches([]); }} data-testid={`vendor-suggest-${v.id}`}>
                      <div className="font-medium">{v.name}</div>
                      {(v.email || v.phone || v.category) && <div className="text-[10px] text-muted-foreground">{[v.category, v.phone, v.email].filter(Boolean).join(' · ')}</div>}
                    </button>
                  ))}
                </div>
              )}
              <p className="text-[10px] text-muted-foreground mt-1">Auto-links to an existing vendor profile, or creates one on the fly.</p>
            </div>
          )}
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
  const [editing, setEditing] = useState(null); // je object being edited (metadata only)
  const [editForm, setEditForm] = useState({ description: '', reference: '', date: '', location_id: '', department_id: '', vendor: '', lines: null });
  const [editAccounts, setEditAccounts] = useState([]); // CoA cache for the line-editor account swap
  const [editVendorMatches, setEditVendorMatches] = useState([]);
  // iter344e — retag a JE's campus/sub-location + department without a
  // full reverse+repost. Loaded lazily when the edit dialog opens.
  const [editLocations, setEditLocations] = useState([]);
  const [editSubLocations, setEditSubLocations] = useState([]);
  const [editDepartments, setEditDepartments] = useState([]);
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
  // iter-tx-refresh: when ANY finance mutation happens (split posts from
  // QuickPost, plain expenses, transfers, JE edits, reversals) rebroadcast
  // 'finance-changed' triggers a refetch here so users switching to the
  // Journal tab always see the latest ledger — even if their filters
  // haven't changed. Previously the Journal panel stayed on its stale
  // useEffect cache and users reported "amounts subtracted but no rows".
  useEffect(() => dataEvents.on('finance-changed', () => { reload().catch(() => {}); }), []);

  // When a JE is selected for editing, pre-fill the metadata form and pull
  // the current CoA once for the account-swap dropdown.
  useEffect(() => {
    if (!editing) return;
    setEditForm({
      description: editing.description || '',
      reference: editing.reference || '',
      date: editing.date || '',
      location_id: editing.location_id || '',
      department_id: editing.department_id || '',
      vendor: editing.vendor || '',
      lines: null,
    });
    if (editAccounts.length === 0) {
      api.get('/finance/chart-of-accounts').then(r => setEditAccounts(r.data || [])).catch(() => {});
    }
    // Load top-level campuses + child sublocations + this campus's departments
    if (editLocations.length === 0) {
      locationsApi.list().then(r => setEditLocations((r.data || []).filter(l => !l.parent_id))).catch(() => setEditLocations([]));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing]);

  // Chain department + sublocation fetch off the currently-picked location.
  // iter344g — resolve to the TOP-LEVEL campus (either the picked value or
  // its parent when the caller picked a sub-location). Without this, picking
  // a sub-location fired another lookup for its own children (zero rows),
  // wiped the dropdown, and the picker rendered blank because the just-
  // picked value no longer matched any option.
  useEffect(() => {
    if (!editing) return;
    const picked = editForm.location_id;
    if (!picked) { setEditSubLocations([]); setEditDepartments([]); return; }
    // Is `picked` a top-level campus? If yes, use it. Else look up its parent.
    const parent = editLocations.find(l => l.id === picked)
      ? picked
      : (editSubLocations.find(s => s.id === picked)?.location_id || picked);
    Promise.all([
      sublocationsApi.list({ location_id: parent }).catch(() => ({ data: [] })),
      departmentsApi.list({ location_id: parent }).catch(() => ({ data: [] })),
    ]).then(([sl, dp]) => {
      // Preserve the picked sub-location in the list even if the backend
      // response doesn't include it (defensive — should never happen once
      // parent resolution is right, but avoids Select rendering blank).
      const list = sl.data || [];
      if (picked !== parent && !list.some(s => s.id === picked)) {
        list.push({ id: picked, name: '(picked sub-location)', location_id: parent });
      }
      setEditSubLocations(list);
      // iter344i — preserve the currently-tagged department even when the
      // scope-filtered response doesn't include it (legacy JE points at a
      // deactivated / cross-campus dept). Without this the Select renders
      // blank instead of the retagable current value.
      const depts = dp.data || [];
      const currentDept = editForm.department_id;
      if (currentDept && !depts.some(d => d.id === currentDept)) {
        // Ask the backend for every department (no scope filter) so we can
        // resolve the legacy id → human name for the dropdown.
        api.get('/departments', { params: { include_inactive: true } })
          .then(r => {
            const match = (r.data || []).find(x => x.id === currentDept);
            setEditDepartments([...depts, match || { id: currentDept, name: '(current department)', location_id: parent }]);
          })
          .catch(() => setEditDepartments([...depts, { id: currentDept, name: '(current department)', location_id: parent }]));
      } else {
        setEditDepartments(depts);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editForm.location_id, editing?.id]);

  // Enter line-edit mode = clone the JE's lines into editForm.lines so
  // users can swap accounts / tweak memos without touching the amounts.
  const startLineEdit = () => {
    if (!editing) return;
    setEditForm(f => ({ ...f, lines: (editing.lines || []).map(ln => ({ ...ln })) }));
  };
  const cancelLineEdit = () => setEditForm(f => ({ ...f, lines: null }));
  const [linesDirty, setLinesDirty] = useState(false);
  const swapAccount = (idx, acctId) => {
    const acct = editAccounts.find(a => a.id === acctId);
    if (!acct) return;
    setLinesDirty(true);
    setEditForm(f => ({
      ...f,
      lines: f.lines.map((ln, i) => i === idx ? { ...ln, account_id: acct.id, account_code: acct.code, account_name: acct.name } : ln),
    }));
  };
  const setLineMemo = (idx, memo) => { setLinesDirty(true); setEditForm(f => ({ ...f, lines: f.lines.map((ln, i) => i === idx ? { ...ln, memo } : ln) })); };

  const saveEdit = async () => {
    if (!editing) return;
    setBusy(true);
    try {
      // iter344c — only pass `lines` when the caller actually retagged an
      // account or edited a memo. Without this the backend reverse-and-
      // repost path fires for every cosmetic edit (a description typo
      // would post two extra JEs). Frontend now tracks a `linesDirty`
      // flag that flips on any account swap / memo edit.
      const payload = {
        description: editForm.description,
        reference: editForm.reference,
        date: editForm.date,
      };
      // Retag campus / sub-location + department only when they actually
      // changed so we don't churn the JE's edit_history unnecessarily.
      if (editForm.location_id && editForm.location_id !== editing.location_id) {
        payload.location_id = editForm.location_id;
      }
      if ((editForm.department_id || '') !== (editing.department_id || '')) {
        payload.department_id = editForm.department_id || null;
      }
      if ((editForm.vendor || '') !== (editing.vendor || '')) {
        payload.vendor = editForm.vendor || null;
      }
      if (linesDirty && editForm.lines) {
        payload.lines = editForm.lines.map(ln => ({
          account_id: ln.account_id, account_code: ln.account_code, account_name: ln.account_name,
          debit: Number(ln.debit || 0), credit: Number(ln.credit || 0), memo: ln.memo || '',
        }));
      }
      await api.put(`/finance/journal/${editing.id}`, payload);
      toast.success(linesDirty ? 'Entry replaced (audit trail preserved)' : 'Entry updated in place');
      dataEvents.emit('finance-changed', { source: 'edit' });
      setEditing(null); setLinesDirty(false);
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Update failed'); }
    setBusy(false);
  };

  const deleteReversal = async (je) => {
    if (!window.confirm(`Delete this reversal (${je.description})? The original entry it reverses will be un-marked and post again. Only allowed while the fiscal period is open.`)) return;
    try {
      await api.delete(`/finance/journal/${je.id}`);
      toast.success('Reversal deleted, original restored');
      dataEvents.emit('finance-changed', { source: 'reversal_delete' });
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Delete failed'); }
  };

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
      dataEvents.emit('finance-changed', { source: 'reversal' });
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
          <div className="overflow-x-auto -mx-4 md:mx-0">
          <Table>
            <TableHeader><TableRow>
              <TableHead>Date</TableHead><TableHead>Description</TableHead><TableHead>Source</TableHead>
              <TableHead className="text-right">Total</TableHead>
              {canReverse && <TableHead className="w-36"></TableHead>}
            </TableRow></TableHeader>
            <TableBody>
              {filteredEntries.map(je => (
                <React.Fragment key={je.id}>
                  <TableRow className={`cursor-pointer hover:bg-muted/40 ${je.reversed ? 'opacity-50 line-through' : ''}`} onClick={() => setExpanded(e => ({ ...e, [je.id]: !e[je.id] }))} data-testid={`journal-row-${je.id}`}>
                    <TableCell className="font-mono text-xs">{je.date}</TableCell>
                    <TableCell>{je.description}{je.reversed && <Badge variant="outline" className="ml-2 text-[10px] text-red-700 border-red-300">REVERSED</Badge>}{je.edit_history?.length > 0 && <Badge variant="outline" className="ml-2 text-[10px]">EDITED</Badge>}</TableCell>
                    <TableCell><Badge variant="outline" className="text-[10px]">{je.source}</Badge></TableCell>
                    <TableCell className="text-right font-mono">{money(je.total)}</TableCell>
                    {canReverse && (
                      <TableCell className="text-right no-underline" onClick={(e) => e.stopPropagation()}>
                        {!je.reversed && je.source !== 'reversal' && (
                          <>
                            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setEditing(je)} data-testid={`journal-edit-${je.id}`}>Edit</Button>
                            <Button size="sm" variant="ghost" className="text-red-700 hover:bg-red-50 h-7 text-xs no-underline" onClick={() => { setReversing(je); setReason(''); }} data-testid={`journal-reverse-${je.id}`}>Reverse</Button>
                          </>
                        )}
                        {je.source === 'reversal' && (
                          <Button size="sm" variant="ghost" className="text-red-700 hover:bg-red-50 h-7 text-xs no-underline" title="Deletes this reversal and restores the original entry. Only allowed while the fiscal period is open." onClick={() => deleteReversal(je)} data-testid={`journal-delete-reversal-${je.id}`}>Delete reversal</Button>
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
          </div>
        )}
      </CardContent>
      <Dialog open={!!editing} onOpenChange={o => !o && setEditing(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="journal-edit-dialog">
          <DialogHeader><DialogTitle>Edit journal entry</DialogTitle></DialogHeader>
          <p className="text-xs text-muted-foreground">Metadata edits (description / reference / date) update in place with an audit trail. Reclassifying lines reverses this entry and posts a fresh one linked via <code>supersedes</code>. Both paths refuse when the fiscal period is locked.</p>
          <div className="space-y-3 pt-2">
            <div><Label className="text-xs">Description</Label><Input value={editForm.description} onChange={e => setEditForm({ ...editForm, description: e.target.value })} data-testid="journal-edit-description" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label className="text-xs">Reference / receipt #</Label><Input value={editForm.reference} onChange={e => setEditForm({ ...editForm, reference: e.target.value })} data-testid="journal-edit-reference" /></div>
              <div><Label className="text-xs">Date</Label><Input type="date" value={editForm.date} onChange={e => setEditForm({ ...editForm, date: e.target.value })} data-testid="journal-edit-date" /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Campus / sub-location</Label>
                <Select value={editForm.location_id} onValueChange={v => setEditForm({ ...editForm, location_id: v, department_id: '' })}>
                  <SelectTrigger data-testid="journal-edit-location"><SelectValue placeholder="Pick a campus" /></SelectTrigger>
                  <SelectContent>
                    {editLocations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                    {editSubLocations.map(s => <SelectItem key={s.id} value={s.id}>&nbsp;&nbsp;↳ {s.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Department</Label>
                <Select value={editForm.department_id || '__none__'} onValueChange={v => setEditForm({ ...editForm, department_id: v === '__none__' ? '' : v })}>
                  <SelectTrigger data-testid="journal-edit-department" disabled={!editForm.location_id}><SelectValue placeholder={editForm.location_id ? (editDepartments.length ? 'Untagged' : 'No departments for this campus') : 'Pick a campus first'} /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">Untagged</SelectItem>
                    {editDepartments.map(d => <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="relative">
              <Label className="text-xs">Vendor</Label>
              <Input
                data-testid="journal-edit-vendor"
                value={editForm.vendor || ''}
                placeholder="Vendor / payee (retag after the fact)"
                onChange={async e => {
                  const v = e.target.value;
                  setEditForm({ ...editForm, vendor: v });
                  if (v && v.length >= 1) {
                    try {
                      const { vendorsApi } = await import('../services/api');
                      const r = await vendorsApi.suggest(v);
                      setEditVendorMatches(r.data || []);
                    } catch { setEditVendorMatches([]); }
                  } else setEditVendorMatches([]);
                }}
                onBlur={() => setTimeout(() => setEditVendorMatches([]), 200)}
              />
              {editVendorMatches.length > 0 && (
                <div className="absolute z-50 left-0 right-0 top-full mt-1 border rounded-lg bg-popover shadow max-h-48 overflow-y-auto" data-testid="journal-edit-vendor-suggest">
                  {editVendorMatches.map(v => (
                    <button key={v.id} type="button" className="w-full text-left px-3 py-1.5 text-xs hover:bg-accent" onClick={() => { setEditForm(f => ({ ...f, vendor: v.name })); setEditVendorMatches([]); }} data-testid={`journal-edit-vendor-suggest-${v.id}`}>
                      <div className="font-medium">{v.name}</div>
                      {(v.email || v.phone || v.category) && <div className="text-[10px] text-muted-foreground">{[v.category, v.phone, v.email].filter(Boolean).join(' · ')}</div>}
                    </button>
                  ))}
                </div>
              )}
              <p className="text-[10px] text-muted-foreground mt-1">Typing a new name creates a vendor profile on save; picking a match links the existing one.</p>
            </div>

            <div className="pt-2 border-t">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-muted-foreground">Lines</span>
                {editForm.lines ? (
                  <Button size="sm" variant="ghost" onClick={cancelLineEdit} className="h-6 text-xs" data-testid="journal-edit-lines-cancel">Discard line changes</Button>
                ) : (
                  <Button size="sm" variant="outline" onClick={startLineEdit} className="h-6 text-xs" data-testid="journal-edit-lines-start">Reclassify lines</Button>
                )}
              </div>
              <div className="rounded-md border overflow-hidden">
                <table className="w-full text-xs">
                  <thead className="bg-muted/40 text-muted-foreground">
                    <tr><th className="text-left px-2 py-1.5">Account</th><th className="text-right px-2 py-1.5 w-20">Debit</th><th className="text-right px-2 py-1.5 w-20">Credit</th><th className="text-left px-2 py-1.5 w-40">Memo</th></tr>
                  </thead>
                  <tbody>
                    {(editForm.lines || editing?.lines || []).map((ln, i) => (
                      <tr key={i} className="border-t">
                        <td className="px-2 py-1.5">
                          {editForm.lines ? (
                            <Select value={ln.account_id} onValueChange={v => swapAccount(i, v)}>
                              <SelectTrigger className="h-7 text-xs" data-testid={`journal-edit-line-account-${i}`}><SelectValue /></SelectTrigger>
                              <SelectContent>{editAccounts.map(a => <SelectItem key={a.id} value={a.id}>{a.code} — {a.name} <span className="text-muted-foreground">({a.type})</span></SelectItem>)}</SelectContent>
                            </Select>
                          ) : (
                            <span className="font-mono">{ln.account_code} — {ln.account_name}</span>
                          )}
                        </td>
                        <td className="text-right font-mono px-2 py-1.5">{ln.debit ? money(ln.debit) : ''}</td>
                        <td className="text-right font-mono px-2 py-1.5">{ln.credit ? money(ln.credit) : ''}</td>
                        <td className="px-2 py-1.5">
                          {editForm.lines ? (
                            <Input value={ln.memo || ''} onChange={e => setLineMemo(i, e.target.value)} className="h-7 text-xs" data-testid={`journal-edit-line-memo-${i}`} />
                          ) : (ln.memo || '—')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {editForm.lines && <p className="text-[11px] text-amber-700 mt-2">Saving with line changes will REVERSE this entry and post a replacement. Debit and credit totals stay untouched — swap accounts / edit memos only.</p>}
            </div>

            {editing?.edit_history?.length > 0 && (
              <p className="text-[11px] text-muted-foreground">Previously edited {editing.edit_history.length}×</p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)} disabled={busy}>Cancel</Button>
            <Button onClick={saveEdit} disabled={busy} data-testid="journal-edit-save">{busy ? 'Saving…' : editForm.lines ? 'Reverse & repost' : 'Save'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
  const [importOpen, setImportOpen] = useState(false);
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
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setImportOpen(true)} data-testid="coa-import-btn"><Upload size={14} className="mr-1" />Import CSV/XLSX</Button>
          <Button size="sm" onClick={() => setAddOpen(true)} data-testid="coa-add"><Plus size={14} className="mr-1" />Add account</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto -mx-4 md:mx-0">
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
        </div>
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
      {/* Bulk import (CSV / XLSX) */}
      <CoaImportDialog open={importOpen} onClose={() => setImportOpen(false)} onDone={() => { setImportOpen(false); reload(); }} />
    </Card>
  );
}

// iter-coa-import: CSV/XLSX bulk import. Header row is inspected
// case-insensitively for `code`, `name`, `type`, `bank_subtype`. Rows are
// posted to /finance/chart-of-accounts/bulk-import which skips any code
// that already exists so re-uploading the same file is safe.
function CoaImportDialog({ open, onClose, onDone }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!open) { setFile(null); setPreview([]); setResult(null); }
  }, [open]);

  const normalize = (raw) => (raw || []).map(r => {
    const low = Object.fromEntries(Object.entries(r).map(([k, v]) => [String(k).trim().toLowerCase(), v]));
    return {
      code: String(low.code || '').trim(),
      name: String(low.name || '').trim(),
      type: String(low.type || '').trim().toLowerCase(),
      bank_subtype: String(low.bank_subtype || low['bank subtype'] || '').trim().toLowerCase(),
    };
  }).filter(r => r.code || r.name);

  const parseFile = (f) => {
    setFile(f); setPreview([]); setResult(null);
    if (!f) return;
    const ext = (f.name || '').toLowerCase().split('.').pop();
    if (ext === 'csv') {
      Papa.parse(f, {
        header: true, skipEmptyLines: true,
        complete: (res) => setPreview(normalize(res.data)),
        error: (e) => toast.error(`CSV parse failed: ${e.message}`),
      });
    } else if (ext === 'xlsx' || ext === 'xls') {
      const reader = new FileReader();
      reader.onload = (ev) => {
        try {
          const wb = XLSX.read(ev.target.result, { type: 'array' });
          const sheet = wb.Sheets[wb.SheetNames[0]];
          const json = XLSX.utils.sheet_to_json(sheet, { defval: '' });
          setPreview(normalize(json));
        } catch (e) { toast.error(`XLSX parse failed: ${e.message}`); }
      };
      reader.readAsArrayBuffer(f);
    } else {
      toast.error('Upload a .csv or .xlsx file');
    }
  };

  const submit = async () => {
    if (!preview.length) { toast.error('Nothing to import'); return; }
    setBusy(true);
    try {
      const r = await api.post('/finance/chart-of-accounts/bulk-import', { accounts: preview });
      setResult(r.data);
      const c = r.data.created_count, s = r.data.skipped_count, i = r.data.invalid_count;
      toast.success(`Imported ${c} · skipped ${s} · invalid ${i}`);
      if (c > 0) onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Import failed'); }
    setBusy(false);
  };

  const downloadTemplate = () => {
    const csv = 'code,name,type,bank_subtype\n5100,Rent Expense,expense,\n5200,Utilities,expense,\n1020,Stanbic Checking,asset,checking\n';
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'chart-of-accounts-template.csv'; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Dialog open={open} onOpenChange={o => !o && onClose()}>
      <DialogContent className="max-w-2xl" data-testid="coa-import-dialog">
        <DialogHeader><DialogTitle>Import Chart of Accounts</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            Upload a <strong>.csv</strong> or <strong>.xlsx</strong> file with columns
            <code className="mx-1">code</code>, <code>name</code>, <code>type</code>, and optional <code>bank_subtype</code>.
            Existing codes are skipped so re-uploading the same file is safe.
          </p>
          <div className="flex items-center gap-2 flex-wrap">
            <input ref={inputRef} type="file" accept=".csv,.xlsx,.xls" onChange={e => parseFile(e.target.files?.[0])} data-testid="coa-import-file" className="text-xs" />
            <Button variant="ghost" size="sm" onClick={downloadTemplate} data-testid="coa-import-template">
              <Download size={12} className="mr-1" />Template
            </Button>
          </div>
          {preview.length > 0 && !result && (
            <div className="border rounded max-h-64 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="bg-muted/50 sticky top-0"><tr>
                  <th className="p-2 text-left">Code</th><th className="p-2 text-left">Name</th>
                  <th className="p-2 text-left">Type</th><th className="p-2 text-left">Bank subtype</th>
                </tr></thead>
                <tbody>
                  {preview.slice(0, 200).map((r, i) => (
                    <tr key={i} className="border-t">
                      <td className="p-1.5 font-mono">{r.code}</td>
                      <td className="p-1.5">{r.name}</td>
                      <td className="p-1.5">{r.type}</td>
                      <td className="p-1.5 text-muted-foreground">{r.bank_subtype || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {preview.length > 200 && <p className="p-2 text-[10px] text-muted-foreground">Preview capped at 200 rows — {preview.length - 200} more will still be imported.</p>}
            </div>
          )}
          {result && (
            <div className="border rounded p-2 space-y-1.5 text-xs" data-testid="coa-import-result">
              <p className="font-semibold">Import complete</p>
              <p>✓ <strong>{result.created_count}</strong> created · ⏭ <strong>{result.skipped_count}</strong> skipped (code exists) · ✗ <strong>{result.invalid_count}</strong> invalid</p>
              {result.invalid?.length > 0 && (
                <details><summary className="cursor-pointer text-red-700">Invalid rows</summary>
                  <ul className="mt-1 space-y-0.5 text-[10px] text-muted-foreground">
                    {result.invalid.slice(0, 20).map((r, i) => <li key={i}>Row {r.row} ({r.code || '—'}): {r.reason}</li>)}
                  </ul>
                </details>
              )}
              {result.skipped?.length > 0 && (
                <details><summary className="cursor-pointer text-amber-700">Skipped rows</summary>
                  <ul className="mt-1 space-y-0.5 text-[10px] text-muted-foreground">
                    {result.skipped.slice(0, 20).map((r, i) => <li key={i}>Row {r.row} — code {r.code}: {r.reason}</li>)}
                  </ul>
                </details>
              )}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>{result ? 'Done' : 'Cancel'}</Button>
          {!result && <Button onClick={submit} disabled={busy || !preview.length} data-testid="coa-import-submit">{busy ? 'Importing…' : `Import ${preview.length || ''}`}</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
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


// ─── BUDGETS ────────────────────────────────────────────────
// iter-subloc-budget: inline editable hard cap for each sub-location.
// The auto-rolled department sum shows on the Dept P&L rollup strip by
// default; setting a value here becomes a hard cap that overrides the
// sum. Passing null (blank + save) clears the override.
function BudgetsPanel() {
  const [subs, setSubs] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [busy, setBusy] = useState(true);
  const [saving, setSaving] = useState(null);
  const load = async () => {
    setBusy(true);
    try {
      const r = await sublocationsApi.list();
      const rows = r.data || [];
      setSubs(rows);
      const initial = {};
      rows.forEach(s => { initial[s.id] = s.budget != null ? String(s.budget) : ''; });
      setDrafts(initial);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to load sub-locations');
    } finally { setBusy(false); }
  };
  useEffect(() => { load(); }, []);
  const save = async (s) => {
    const raw = drafts[s.id];
    const val = raw === '' || raw == null ? null : Number(raw);
    if (val != null && (Number.isNaN(val) || val < 0)) { toast.error('Enter a positive number or leave blank'); return; }
    setSaving(s.id);
    try {
      await sublocationsApi.setBudget(s.id, val);
      toast.success(val == null ? `Cleared cap for ${s.name}` : `Cap set for ${s.name}`);
      load();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to save'); }
    finally { setSaving(null); }
  };
  return (
    <Card data-testid="subloc-budget-panel">
      <CardHeader className="space-y-1">
        <CardTitle className="text-base">Sub-location budget caps</CardTitle>
        <p className="text-xs text-muted-foreground">
          Hard caps override the auto-rolled department sum on the Dept P&amp;L rollup strip.
          Leave blank to fall back to the rollup.
        </p>
      </CardHeader>
      <CardContent className="p-0">
        {busy ? (
          <p className="p-6 text-center text-sm text-muted-foreground">Loading…</p>
        ) : subs.length === 0 ? (
          <p className="p-6 text-center text-sm text-muted-foreground">
            No sub-locations in your scope yet. Add them from <strong>Admin → Locations</strong>.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead><tr className="border-t border-b bg-muted/30">
              <th className="p-3 text-left text-xs text-muted-foreground">Sub-location</th>
              <th className="p-3 text-right text-xs text-muted-foreground w-56">Hard-cap budget</th>
              <th className="p-3 w-28"></th>
            </tr></thead>
            <tbody>
              {subs.map(s => {
                const current = s.budget != null ? String(s.budget) : '';
                const dirty = (drafts[s.id] ?? '') !== current;
                return (
                  <tr key={s.id} className="border-b last:border-0" data-testid={`subloc-budget-row-${s.id}`}>
                    <td className="p-3 font-medium">{s.name}</td>
                    <td className="p-3">
                      <Input
                        type="number" min={0} className="h-8 text-xs text-right"
                        placeholder="Auto-rollup"
                        value={drafts[s.id] ?? ''}
                        onChange={e => setDrafts(prev => ({ ...prev, [s.id]: e.target.value }))}
                        data-testid={`subloc-budget-input-${s.id}`}
                      />
                    </td>
                    <td className="p-3 text-right">
                      <Button
                        size="sm" variant={dirty ? 'default' : 'ghost'}
                        disabled={!dirty || saving === s.id}
                        onClick={() => save(s)}
                        data-testid={`subloc-budget-save-${s.id}`}
                      >{saving === s.id ? 'Saving…' : dirty ? 'Save' : 'Saved'}</Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}

// ─── RESET (admin only) ──────────────────────────────────────
// Reset UI moved to Admin → Danger Zone (see AdminPage.jsx). Kept as a
// no-op placeholder to avoid churn if any test imports this file by path.
