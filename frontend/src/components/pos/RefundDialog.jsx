import { useState, useMemo } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Minus, Plus, RotateCcw } from 'lucide-react';
import { toast } from 'sonner';
import { salesApi } from '../../services/api';

const unitPrice = (it) => {
  const sold = Number(it.qty ?? it.quantity ?? 1) || 1;
  if (it.line_total !== undefined && it.line_total !== null && it.line_total !== '') return Number(it.line_total) / sold;
  return Number(it.price || 0);
};

/** Return one line (or a few units of it) off a receipt — the rest stands.
 *  With items in the basket it can also swap: the customer pays the difference. */
export const RefundDialog = ({ sale, open, onOpenChange, currency = 'UGX', onDone, cart = [], cartTotal = 0, onExchanged }) => {
  const [qtys, setQtys] = useState({});
  const [reason, setReason] = useState('');
  const [method, setMethod] = useState('');
  const [busy, setBusy] = useState(false);
  const [exchange, setExchange] = useState(false);

  const lines = useMemo(() => (sale?.items || []).map((it, i) => ({
    ...it,
    _i: i,
    remaining: Number(it.qty ?? it.quantity ?? 0) - Number(it.refunded_qty || 0),
    unit: unitPrice(it),
  })), [sale]);

  const money = (n) => `${currency} ${Number(n || 0).toLocaleString()}`;
  const amount = lines.reduce((sum, l) => sum + (Number(qtys[l._i] || 0) * l.unit), 0);
  const picked = lines.filter(l => Number(qtys[l._i] || 0) > 0);
  const difference = Number(cartTotal || 0) - amount;

  const bump = (l, delta) => setQtys(q => {
    const next = Math.max(0, Math.min(l.remaining, Number(q[l._i] || 0) + delta));
    return { ...q, [l._i]: next };
  });

  const submit = async () => {
    if (!picked.length) { toast.error('Pick what is coming back'); return; }
    setBusy(true);
    try {
      const returnedLines = picked.map(l => ({
        name: l.name || l.product_name || 'Item',
        qty: Number(qtys[l._i]),
        price: l.unit,
        line_total: Number(qtys[l._i]) * l.unit,
      }));
      if (exchange) {
        const res = await salesApi.exchange(sale.id, {
          returns: picked.map(l => ({
            product_id: l.product_id, variant_id: l.variant_id || null,
            name: l.name, qty: Number(qtys[l._i]),
          })),
          items: cart,
          total: cartTotal,
          reason: reason.trim() || 'Exchange',
        });
        onExchanged?.(res.data, returnedLines, amount, reason.trim());
      } else {
        const res = await salesApi.refund(sale.id, {
          items: picked.map(l => ({
            product_id: l.product_id, variant_id: l.variant_id || null,
            name: l.name, qty: Number(qtys[l._i]),
          })),
          reason: reason.trim(),
          refund_method: method || undefined,
        });
        onDone?.(res.data, returnedLines, amount, reason.trim());
      }
      setQtys({}); setReason(''); setMethod(''); setExchange(false);
      onOpenChange(false);
    } catch (e) {
      toast.error(e.response?.data?.detail || (exchange ? 'Exchange failed' : 'Refund failed'));
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) { setQtys({}); setReason(''); } onOpenChange(v); }}>
      <DialogContent className="max-w-lg" data-testid="refund-dialog">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2">
            <RotateCcw size={16} className="text-amber-600" />
            Return items — {sale?.receipt_number || sale?.id}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
          {lines.map(l => (
            <div key={l._i} className="flex items-center gap-3 border border-border rounded-lg px-3 py-2"
                 data-testid={`refund-line-${l._i}`}>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{l.name || l.product_name || 'Item'}</p>
                <p className="text-xs text-muted-foreground">
                  {money(l.unit)} each · {l.remaining > 0 ? `${l.remaining} left to return` : 'already returned'}
                </p>
              </div>
              <div className="flex items-center gap-1">
                <Button size="icon" variant="outline" className="h-7 w-7" disabled={!qtys[l._i]}
                        data-testid={`refund-minus-${l._i}`} onClick={() => bump(l, -1)}><Minus size={12} /></Button>
                <span className="w-7 text-center text-sm font-semibold tabular-nums"
                      data-testid={`refund-qty-${l._i}`}>{qtys[l._i] || 0}</span>
                <Button size="icon" variant="outline" className="h-7 w-7" disabled={l.remaining <= (qtys[l._i] || 0)}
                        data-testid={`refund-plus-${l._i}`} onClick={() => bump(l, 1)}><Plus size={12} /></Button>
              </div>
            </div>
          ))}
          {!lines.length && <p className="text-sm text-muted-foreground">This receipt has no returnable lines.</p>}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="text-xs">Reason</Label>
            <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Damaged, wrong size…"
                   data-testid="refund-reason-input" />
          </div>
          <div>
            <Label className="text-xs">Money back as</Label>
            <Select value={method || (sale?.payment_method || 'cash')} onValueChange={setMethod} disabled={exchange}>
              <SelectTrigger data-testid="refund-method-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="cash">Cash</SelectItem>
                <SelectItem value="mobile_money">Mobile money</SelectItem>
                <SelectItem value="card">Card</SelectItem>
                <SelectItem value="store_credit">Store credit</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {cart.length > 0 && (
          <label className="flex items-start gap-2 text-sm border border-border rounded-lg px-3 py-2 cursor-pointer">
            <input type="checkbox" className="mt-1" checked={exchange} data-testid="refund-exchange-toggle"
                   onChange={(e) => setExchange(e.target.checked)} />
            <span>
              <span className="font-medium">Swap for what's in the basket</span>
              <span className="block text-xs text-muted-foreground">
                {cart.length} item(s) worth {money(cartTotal)} — the customer pays only the difference
              </span>
            </span>
          </label>
        )}

        <div className="flex justify-between items-center border-t border-border pt-3 text-sm">
          <span className="text-muted-foreground">{exchange ? 'Difference to pay' : 'Refund total'}</span>
          <span className={`text-lg font-bold ${exchange && difference < 0 ? 'text-emerald-600' : 'text-amber-600'}`}
                data-testid="refund-total">
            {exchange
              ? (difference >= 0 ? money(difference) : `${money(Math.abs(difference))} back`)
              : money(amount)}
          </span>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="refund-cancel-btn">Cancel</Button>
          <Button onClick={submit} disabled={busy || !picked.length} className="gap-2" data-testid="refund-submit-btn">
            {busy ? 'Working…' : (exchange ? 'Exchange & print' : 'Refund & print slip')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
