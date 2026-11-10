import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { ArrowRightLeft } from 'lucide-react';
import { toast } from 'sonner';
import { salesApi } from '../../services/api';

/** Send stock from this shop to another — one count down, the other up. */
export const TransferStockDialog = ({ product, locations = [], fromLocationId, open, onOpenChange, onDone }) => {
  const [to, setTo] = useState('');
  const [qty, setQty] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState([]);

  useEffect(() => {
    if (!open || !product) return;
    setTo(''); setQty(''); setNote('');
    salesApi.stockTransfers({ location_id: fromLocationId || undefined, limit: 5 })
      .then(r => setHistory((r.data || []).filter(t => t.product_id === product.id)))
      .catch(() => setHistory([]));
  }, [open, product, fromLocationId]);

  const fromName = locations.find(l => l.id === fromLocationId)?.name || 'this store';
  const onHand = Number(product?.stock ?? 0);

  const submit = async () => {
    if (!to) { toast.error('Pick the store it is going to'); return; }
    const n = Number(qty);
    if (!n || n <= 0) { toast.error('Say how many are going across'); return; }
    setBusy(true);
    try {
      const res = await salesApi.transferStock({
        product_id: product.id, from_location_id: fromLocationId,
        to_location_id: to, qty: n, note: note.trim(),
      });
      toast.success(res.data?.message || 'Stock sent');
      onDone?.(res.data);
      onOpenChange(false);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Transfer failed');
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="transfer-stock-dialog">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2">
            <ArrowRightLeft size={16} className="text-primary" /> Send stock — {product?.name}
          </DialogTitle>
        </DialogHeader>

        <p className="text-sm text-muted-foreground">
          {fromName} holds <span className="font-semibold text-foreground" data-testid="transfer-on-hand">{onHand}</span>
          {product?.unit ? ` ${product.unit}` : ''}. What goes across leaves this count and lands on theirs.
        </p>

        <div className="space-y-3">
          <div>
            <Label className="text-xs">Send to</Label>
            <Select value={to} onValueChange={setTo}>
              <SelectTrigger data-testid="transfer-to-select"><SelectValue placeholder="Choose a store" /></SelectTrigger>
              <SelectContent>
                {locations.filter(l => l.id !== fromLocationId).map(l => (
                  <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">How many</Label>
            <Input type="number" min="1" max={onHand || undefined} value={qty}
              onChange={(e) => setQty(e.target.value)} placeholder="0" data-testid="transfer-qty-input" />
          </div>
          <div>
            <Label className="text-xs">Note (optional)</Label>
            <Input value={note} onChange={(e) => setNote(e.target.value)}
              placeholder="Sent with the Tuesday run" data-testid="transfer-note-input" />
          </div>
        </div>

        {!!history.length && (
          <div className="border-t border-border pt-2">
            <p className="text-xs text-muted-foreground mb-1">Recent moves of this item</p>
            {history.slice(0, 4).map(t => (
              <p key={t.id} className="text-xs text-muted-foreground" data-testid={`transfer-history-${t.id}`}>
                {t.qty} · {t.from_location_name} → {t.to_location_name} · {String(t.created_at).slice(0, 10)}
              </p>
            ))}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="transfer-cancel-btn">Cancel</Button>
          <Button onClick={submit} disabled={busy || !to || !qty} data-testid="transfer-submit-btn">
            {busy ? 'Sending…' : 'Send stock'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};
