/**
 * PaymentsInbox — every payment that arrived, and the ones nobody has claimed.
 *
 * Provider webhooks and hand-logged bank / mobile money receipts both land
 * here. Anything the system couldn't match to an order by reference sits in
 * "Needs matching" until finance attaches it, so money never quietly vanishes.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Inbox, Link2, EyeOff, Plus } from 'lucide-react';
import api from '../services/api';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { toast } from 'sonner';

export default function PaymentsInbox() {
  const [rows, setRows] = useState([]);
  const [unmatched, setUnmatched] = useState(0);
  const [filter, setFilter] = useState('');
  const [busy, setBusy] = useState(false);
  const [matchFor, setMatchFor] = useState(null);
  const [orderRef, setOrderRef] = useState('');
  const [showLog, setShowLog] = useState(false);
  const [logForm, setLogForm] = useState({ reference: '', amount: '', payer: '', method: 'bank_transfer', note: '' });

  const load = useCallback(async () => {
    try {
      const r = await api.get('/payments/inbox', { params: filter ? { status: filter } : {} });
      setRows(r.data?.payments || []);
      setUnmatched(r.data?.unmatched || 0);
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed to load payments'); }
  }, [filter]);
  useEffect(() => { load(); }, [load]);

  const match = async () => {
    setBusy(true);
    try {
      await api.post(`/payments/inbox/${matchFor.id}/match`, { sale_id: orderRef.trim() });
      toast.success('Payment matched to the order');
      setMatchFor(null); setOrderRef('');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Match failed'); }
    finally { setBusy(false); }
  };

  const ignore = async (row) => {
    if (!window.confirm(`Ignore the ${row.currency} ${row.amount} payment from ${row.payer || 'unknown'}?`)) return;
    try {
      await api.post(`/payments/inbox/${row.id}/match`, { ignore: true });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const logManual = async () => {
    setBusy(true);
    try {
      await api.post('/payments/inbox/manual', { ...logForm, amount: parseFloat(logForm.amount) || 0 });
      toast.success('Payment recorded');
      setShowLog(false);
      setLogForm({ reference: '', amount: '', payer: '', method: 'bank_transfer', note: '' });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed to record payment'); }
    finally { setBusy(false); }
  };

  return (
    <Card data-testid="payments-inbox">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="flex items-start gap-2">
            <Inbox size={16} className="text-blue-600 mt-0.5" />
            <div>
              <h3 className="text-sm font-semibold">Payments Inbox</h3>
              <p className="text-xs text-muted-foreground">
                Bank transfers, mobile money and gateway notifications. Match each one to its order.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {unmatched > 0 && <Badge className="bg-amber-100 text-amber-800" data-testid="payments-unmatched-badge">{unmatched} need matching</Badge>}
            <select className="h-8 rounded border bg-background px-2 text-xs" value={filter}
              onChange={e => setFilter(e.target.value)} data-testid="payments-inbox-filter">
              <option value="">All</option>
              <option value="unmatched">Needs matching</option>
              <option value="matched">Matched</option>
              <option value="ignored">Ignored</option>
            </select>
            <Button size="sm" className="h-8 text-[11px] gap-1" onClick={() => setShowLog(true)} data-testid="payments-log-btn">
              <Plus size={12} /> Log a payment
            </Button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead><tr className="text-left border-b text-muted-foreground">
              <th className="py-1.5">Received</th><th>Reference</th><th>From</th>
              <th className="text-right">Amount</th><th>Via</th><th>Order</th><th></th>
            </tr></thead>
            <tbody data-testid="payments-inbox-rows">
              {rows.length === 0 && (
                <tr><td colSpan={7} className="py-6 text-center text-muted-foreground">No payments recorded yet.</td></tr>
              )}
              {rows.map(r => (
                <tr key={r.id} className="border-b last:border-0" data-testid={`payment-row-${r.id}`}>
                  <td className="py-1.5 whitespace-nowrap">{(r.received_at || '').slice(0, 16).replace('T', ' ')}</td>
                  <td className="font-mono">{r.reference || '—'}</td>
                  <td>{r.payer || '—'}</td>
                  <td className="text-right font-semibold whitespace-nowrap">
                    {r.currency} {Number(r.amount || 0).toLocaleString()}
                    {r.status === 'matched' && r.amount_matches === false && (
                      <span className="ml-1 text-amber-600" title="Amount differs from the order total">≠</span>
                    )}
                  </td>
                  <td className="capitalize">{(r.provider || '').replace(/_/g, ' ')}</td>
                  <td>
                    {r.sale_id
                      ? <span className="font-mono">{r.sale_id}</span>
                      : <Badge variant="outline" className="text-[10px]">{r.status}</Badge>}
                  </td>
                  <td className="text-right whitespace-nowrap">
                    {r.status === 'unmatched' && (
                      <>
                        <Button size="sm" variant="outline" className="h-6 text-[10px] mr-1"
                          onClick={() => { setMatchFor(r); setOrderRef(r.reference || ''); }}
                          data-testid={`payment-match-${r.id}`}><Link2 size={10} className="mr-1" /> Match</Button>
                        <Button size="sm" variant="ghost" className="h-6 text-[10px]"
                          onClick={() => ignore(r)} data-testid={`payment-ignore-${r.id}`}><EyeOff size={10} /></Button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>

      <Dialog open={!!matchFor} onOpenChange={o => !o && setMatchFor(null)}>
        <DialogContent className="max-w-sm" data-testid="payment-match-dialog">
          <DialogHeader>
            <DialogTitle>Match this payment</DialogTitle>
            <DialogDescription>
              {matchFor && `${matchFor.currency} ${Number(matchFor.amount || 0).toLocaleString()} from ${matchFor.payer || 'unknown'}`}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Order / receipt number</Label>
              <Input value={orderRef} onChange={e => setOrderRef(e.target.value)}
                placeholder="INV-20260914-0001" className="font-mono" data-testid="payment-match-input" />
            </div>
            <Button className="w-full" disabled={busy || !orderRef.trim()} onClick={match} data-testid="payment-match-submit">
              {busy ? 'Matching…' : 'Match payment'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showLog} onOpenChange={setShowLog}>
        <DialogContent className="max-w-sm" data-testid="payment-log-dialog">
          <DialogHeader>
            <DialogTitle>Log a payment you received</DialogTitle>
            <DialogDescription>For money that arrived by bank transfer or mobile money.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2.5">
            <div className="space-y-1.5"><Label className="text-xs">Reference the payer used</Label>
              <Input value={logForm.reference} onChange={e => setLogForm({ ...logForm, reference: e.target.value })}
                placeholder="INV-20260914-0001" className="font-mono" data-testid="payment-log-reference" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5"><Label className="text-xs">Amount *</Label>
                <Input type="number" value={logForm.amount} onChange={e => setLogForm({ ...logForm, amount: e.target.value })} data-testid="payment-log-amount" />
              </div>
              <div className="space-y-1.5"><Label className="text-xs">Via</Label>
                <select className="h-9 w-full rounded border bg-background px-2 text-sm" value={logForm.method}
                  onChange={e => setLogForm({ ...logForm, method: e.target.value })} data-testid="payment-log-method">
                  <option value="bank_transfer">Bank transfer</option>
                  <option value="mtn_momo">MTN MoMo</option>
                  <option value="airtel_money">Airtel Money</option>
                  <option value="cash">Cash</option>
                </select>
              </div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">From (name / number)</Label>
              <Input value={logForm.payer} onChange={e => setLogForm({ ...logForm, payer: e.target.value })} data-testid="payment-log-payer" />
            </div>
            <Button className="w-full" disabled={busy || !logForm.amount} onClick={logManual} data-testid="payment-log-submit">
              {busy ? 'Saving…' : 'Record payment'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
