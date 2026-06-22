/**
 * FundRequestsPanel — staff-facing fund request workflow.
 *
 * Embedded as a tab on FinancialPage so it lives alongside donations/expenses
 * but is reachable by EVERY staff member regardless of finance access. Staff
 * sees "My Requests" + can submit a new one; finance staff see "All requests"
 * + can mark them paid (which auto-creates the matching expense entry).
 */
import React, { useEffect, useState, useCallback } from 'react';
import { CardContent, Card, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { Textarea } from './ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { Plus, Receipt, Upload, RefreshCw, CheckCircle2, X, Banknote } from 'lucide-react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import EmptyState from './EmptyState';

const STATUS_BADGE = {
  in_progress: { cls: 'bg-amber-100 text-amber-700', label: 'Pending' },
  approved: { cls: 'bg-emerald-100 text-emerald-700', label: 'Approved' },
  rejected: { cls: 'bg-rose-100 text-rose-700', label: 'Rejected' },
  cancelled: { cls: 'bg-slate-100 text-slate-600', label: 'Cancelled' },
};

const PRIVILEGED = new Set(['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director', 'Manager']);

export default function FundRequestsPanel() {
  const { user } = useAuth();
  const hasFinance = PRIVILEGED.has(user?.role) || !!user?.finance_access;
  const [mine, setMine] = useState([]);
  const [all, setAll] = useState([]);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState('mine'); // 'mine' | 'all' (finance only)
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ kind: 'reimbursement', amount: '', currency: 'UGX', purpose: '', category: '' });
  const [submitting, setSubmitting] = useState(false);
  const [receiptUploadFor, setReceiptUploadFor] = useState(null);
  // Mark-paid dialog state (replaces window.prompt)
  const [markPaidFor, setMarkPaidFor] = useState(null); // holds the request
  const [markPaidNotes, setMarkPaidNotes] = useState('');
  const [markPaidBusy, setMarkPaidBusy] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [m, a] = await Promise.all([
        api.get('/funds/requests/mine'),
        hasFinance ? api.get('/funds/requests') : Promise.resolve({ data: [] }),
      ]);
      setMine(m.data || []);
      setAll(a.data || []);
    } catch (e) { console.warn(e?.message || e); }
    finally { setLoading(false); }
  }, [hasFinance]);

  useEffect(() => { refresh(); }, [refresh]);

  const submit = async () => {
    if (!form.amount || Number(form.amount) <= 0) { toast.error('Enter an amount'); return; }
    if (!form.purpose.trim()) { toast.error('Describe the purpose'); return; }
    setSubmitting(true);
    try {
      await api.post('/funds/requests', {
        kind: form.kind,
        amount: Number(form.amount),
        currency: form.currency,
        purpose: form.purpose.trim(),
        category: form.category.trim() || undefined,
      });
      toast.success('Fund request submitted — finance will be notified');
      setShowCreate(false);
      setForm({ kind: 'reimbursement', amount: '', currency: 'UGX', purpose: '', category: '' });
      await refresh();
    } catch (e) { toast.error(e.response?.data?.detail || 'Submit failed'); }
    finally { setSubmitting(false); }
  };

  const uploadReceipt = async (requestId, file) => {
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    try {
      const r = await api.post(`/funds/requests/${requestId}/receipt`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success('Receipt uploaded');
      setReceiptUploadFor(null);
      await refresh();
      return r.data?.receipt_url;
    } catch (e) { toast.error(e.response?.data?.detail || 'Upload failed'); }
  };

  const markPaid = (req) => {
    setMarkPaidFor(req);
    setMarkPaidNotes('');
  };

  const confirmMarkPaid = async () => {
    if (!markPaidFor) return;
    setMarkPaidBusy(true);
    try {
      await api.post(`/funds/requests/${markPaidFor.id}/mark-paid`, { notes: markPaidNotes });
      toast.success(`Paid → expense created (${markPaidFor.currency} ${markPaidFor.amount.toLocaleString()})`);
      setMarkPaidFor(null);
      setMarkPaidNotes('');
      await refresh();
    } catch (e) { toast.error(e.response?.data?.detail || 'Mark-paid failed'); }
    finally { setMarkPaidBusy(false); }
  };

  const cancel = async (req) => {
    if (!window.confirm(`Cancel this ${req.metadata?.kind} request?`)) return;
    try {
      await api.delete(`/funds/requests/${req.id}`);
      toast.success('Cancelled');
      await refresh();
    } catch (e) { toast.error(e.response?.data?.detail || 'Cancel failed'); }
  };

  const renderRow = (req, { withActions = false } = {}) => {
    const sb = STATUS_BADGE[req.status] || { cls: 'bg-slate-100', label: req.status };
    const md = req.metadata || {};
    return (
      <div key={req.id} className="p-3 rounded-lg border" data-testid={`fund-row-${req.id}`}>
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <p className="font-medium text-sm">{req.title}</p>
              <Badge className={`${sb.cls} text-[10px]`}>{sb.label}</Badge>
              <Badge variant="outline" className="text-[10px] capitalize">{md.kind || 'request'}</Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              <span className="font-semibold text-foreground">{req.currency} {Number(req.amount || 0).toLocaleString()}</span>
              {' · '}{req.summary}
            </p>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              {req.submitted_by_name || req.submitted_by_email || 'Anonymous'}
              {' · '}{(req.created_at || '').slice(0, 10)}
              {md.expense_id && <span className="ml-1 text-emerald-700">· paid (exp {md.expense_id.slice(0, 12)}…)</span>}
            </p>
            {md.receipt_url && (
              <a href={md.receipt_url} target="_blank" rel="noreferrer" className="text-[11px] text-primary inline-flex items-center gap-1 mt-1 hover:underline">
                <Receipt size={10} /> View receipt
              </a>
            )}
          </div>
          <div className="flex flex-col gap-1.5 items-end">
            {req.status === 'in_progress' && req.submitted_by === user?.id && (
              <Button size="sm" variant="ghost" className="h-7 text-[11px] text-destructive" onClick={() => cancel(req)} data-testid={`fund-cancel-${req.id}`}>
                <X size={11} className="mr-1" /> Cancel
              </Button>
            )}
            {!md.receipt_url && (req.submitted_by === user?.id || hasFinance) && (
              <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={() => setReceiptUploadFor(req.id)} data-testid={`fund-receipt-btn-${req.id}`}>
                <Upload size={11} className="mr-1" /> Upload receipt
              </Button>
            )}
            {withActions && req.status === 'approved' && !md.expense_id && hasFinance && (
              <Button size="sm" className="h-7 text-[11px]" onClick={() => markPaid(req)} data-testid={`fund-mark-paid-${req.id}`}>
                <CheckCircle2 size={11} className="mr-1" /> Mark paid
              </Button>
            )}
          </div>
        </div>
        {receiptUploadFor === req.id && (
          <div className="mt-2 p-2 rounded border bg-muted/30 flex items-center gap-2 flex-wrap">
            <Input
              type="file"
              accept="image/*,application/pdf"
              onChange={e => uploadReceipt(req.id, e.target.files?.[0])}
              className="h-8 text-xs flex-1 min-w-0"
              data-testid={`fund-receipt-input-${req.id}`}
            />
            <Button size="sm" variant="ghost" className="h-7" onClick={() => setReceiptUploadFor(null)}>Cancel</Button>
          </div>
        )}
      </div>
    );
  };

  const visibleList = tab === 'all' ? all : mine;

  return (
    <div className="space-y-3" data-testid="fund-requests-panel">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          {hasFinance && (
            <div className="flex rounded border overflow-hidden">
              <button
                className={`px-3 py-1.5 text-xs ${tab === 'mine' ? 'bg-primary text-primary-foreground' : 'bg-background hover:bg-muted'}`}
                onClick={() => setTab('mine')}
                data-testid="fund-tab-mine"
              >My requests ({mine.length})</button>
              <button
                className={`px-3 py-1.5 text-xs border-l ${tab === 'all' ? 'bg-primary text-primary-foreground' : 'bg-background hover:bg-muted'}`}
                onClick={() => setTab('all')}
                data-testid="fund-tab-all"
              >All requests ({all.length})</button>
            </div>
          )}
          <Button size="sm" variant="ghost" onClick={refresh} disabled={loading} data-testid="fund-refresh-btn">
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          </Button>
        </div>
        <Button size="sm" onClick={() => setShowCreate(true)} data-testid="fund-new-btn">
          <Plus size={13} className="mr-1" /> New request
        </Button>
      </div>

      <Card className="rounded-xl shadow-soft">
        <CardContent className="p-3 space-y-2">
          {visibleList.length === 0 ? (
            <EmptyState
              icon={Banknote}
              title={tab === 'mine' ? 'No fund requests yet' : 'No requests submitted yet'}
              description={tab === 'mine'
                ? 'Use this to request an advance for a purchase, or to claim back money you\'ve already spent on the org\'s behalf.'
                : 'Staff requests will appear here for finance to review and approve.'}
              action={tab === 'mine' ? { label: 'New request', onClick: () => setShowCreate(true), testid: 'fund-empty-new-btn' } : null}
              testid={`fund-${tab}-empty`}
            />
          ) : visibleList.map(req => renderRow(req, { withActions: tab === 'all' }))}
        </CardContent>
      </Card>

      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-md" data-testid="fund-create-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Banknote size={16} /> New fund request</DialogTitle>
            <DialogDescription className="text-xs">
              Advance = funds up-front before you spend. Reimbursement = you already spent, claim it back.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1">
              <Label className="text-xs">Kind</Label>
              <Select value={form.kind} onValueChange={v => setForm({ ...form, kind: v })}>
                <SelectTrigger data-testid="fund-form-kind"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="reimbursement">Reimbursement (I already paid)</SelectItem>
                  <SelectItem value="advance">Advance (Pay me first)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="space-y-1 col-span-2">
                <Label className="text-xs">Amount</Label>
                <Input type="number" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} placeholder="50000" data-testid="fund-form-amount" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Currency</Label>
                <Input value={form.currency} onChange={e => setForm({ ...form, currency: e.target.value })} className="font-mono uppercase" maxLength={4} data-testid="fund-form-currency" />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Purpose</Label>
              <Textarea
                rows={3}
                value={form.purpose}
                onChange={e => setForm({ ...form, purpose: e.target.value })}
                placeholder="Bought stationery for the literacy programme — invoice attached"
                data-testid="fund-form-purpose"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Expense category (optional)</Label>
              <Input value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} placeholder="Office Supplies / Travel / Programme" data-testid="fund-form-category" />
              <p className="text-[10px] text-muted-foreground">If blank, finance assigns it when approving.</p>
            </div>
          </div>
          <div className="flex gap-2 pt-3">
            <Button variant="ghost" onClick={() => setShowCreate(false)} className="flex-1">Cancel</Button>
            <Button onClick={submit} disabled={submitting} className="flex-1" data-testid="fund-form-submit">
              {submitting ? 'Submitting…' : 'Submit request'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Mark-paid confirmation dialog (replaces window.prompt) */}
      <Dialog open={!!markPaidFor} onOpenChange={(o) => { if (!o) { setMarkPaidFor(null); setMarkPaidNotes(''); } }}>
        <DialogContent className="max-w-md" data-testid="fund-mark-paid-dialog">
          <DialogHeader>
            <DialogTitle>Mark as paid</DialogTitle>
            <DialogDescription className="text-xs">
              This creates a matching <strong>expense entry</strong> in the books. The submitter will be notified.
            </DialogDescription>
          </DialogHeader>
          {markPaidFor && (
            <div className="space-y-3 mt-2">
              <div className="rounded-lg bg-muted/40 p-3 text-xs space-y-1">
                <p className="font-semibold text-sm">{markPaidFor.title}</p>
                <p className="text-muted-foreground">
                  <Banknote size={10} className="inline mr-1 mb-0.5" />
                  {markPaidFor.currency} {Number(markPaidFor.amount || 0).toLocaleString()} · {markPaidFor.metadata?.kind || 'reimbursement'}
                </p>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Payment notes <span className="text-muted-foreground font-normal">(optional — e.g. transaction ID, payment method)</span></Label>
                <Textarea
                  rows={3}
                  value={markPaidNotes}
                  onChange={e => setMarkPaidNotes(e.target.value)}
                  placeholder="e.g. Sent via mobile money — txn ABC123"
                  data-testid="fund-mark-paid-notes"
                />
              </div>
              <div className="flex gap-2 pt-1">
                <Button variant="ghost" className="flex-1" onClick={() => { setMarkPaidFor(null); setMarkPaidNotes(''); }}>Cancel</Button>
                <Button className="flex-1" onClick={confirmMarkPaid} disabled={markPaidBusy} data-testid="fund-mark-paid-confirm">
                  {markPaidBusy ? 'Recording…' : 'Confirm & create expense'}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
