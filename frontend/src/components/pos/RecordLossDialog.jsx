import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { PackageX } from 'lucide-react';
import { toast } from 'sonner';
import { stockApi, chatApi } from '../../services/api';

export const LOSS_REASONS = [
  { value: 'spoiled', label: 'Spoiled or damaged' },
  { value: 'died', label: 'Died' },
  { value: 'stolen', label: 'Stolen or missing' },
  { value: 'used_by_farm', label: 'Eaten or used by the farm' },
  { value: 'negligence', label: 'Employee negligence' },
  { value: 'donated', label: 'Donated' },
  { value: 'other', label: 'Other' },
];

/** Write stock off — and print the slip that proves it. */
export const RecordLossDialog = ({ product, locationId, open, onOpenChange, currency = 'UGX', onDone }) => {
  const [qty, setQty] = useState('');
  const [reason, setReason] = useState('spoiled');
  const [note, setNote] = useState('');
  const [employeeId, setEmployeeId] = useState('');
  const [donatedTo, setDonatedTo] = useState('');
  const [staff, setStaff] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setQty(''); setReason('spoiled'); setNote(''); setEmployeeId(''); setDonatedTo('');
  }, [open]);

  useEffect(() => {
    if (reason !== 'negligence' || staff.length) return;
    chatApi.users().then(r => setStaff(r.data || [])).catch(() => setStaff([]));
  }, [reason, staff.length]);

  const onHand = Number(product?.stock ?? 0);
  const unit = Number(product?.price || 0);
  const value = (Number(qty) || 0) * unit;
  const money = (n) => `${currency} ${Number(n || 0).toLocaleString()}`;

  const submit = async () => {
    const n = Number(qty);
    if (!n || n <= 0) { toast.error('Say how many were lost'); return; }
    if (n > onHand) { toast.error(`Only ${onHand} on hand here`); return; }
    if (reason === 'negligence' && !employeeId) { toast.error('Say whose negligence it was'); return; }
    if (reason === 'donated' && !donatedTo.trim()) { toast.error('Say who it was donated to'); return; }
    setBusy(true);
    try {
      const res = await stockApi.recordLoss({
        product_id: product.id, qty: n, reason, location_id: locationId || undefined,
        note: note.trim(), employee_id: employeeId || undefined,
        donated_to: donatedTo.trim() || undefined,
      });
      toast.success(res.data?.message || 'Written off');
      onDone?.(res.data.loss);
      onOpenChange(false);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not record the loss');
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="record-loss-dialog">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2">
            <PackageX size={16} className="text-destructive" /> Write off — {product?.name}
          </DialogTitle>
        </DialogHeader>

        <p className="text-sm text-muted-foreground">
          <span className="font-semibold text-foreground" data-testid="loss-on-hand">{onHand}</span> on hand at this store.
          A slip prints for the file.
        </p>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="text-xs">How many</Label>
            <Input type="number" min="1" max={onHand || undefined} value={qty}
              onChange={(e) => setQty(e.target.value)} placeholder="0" data-testid="loss-qty-input" />
          </div>
          <div>
            <Label className="text-xs">What happened</Label>
            <Select value={reason} onValueChange={setReason}>
              <SelectTrigger data-testid="loss-reason-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                {LOSS_REASONS.map(r => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>

        {reason === 'negligence' && (
          <div>
            <Label className="text-xs">Whose negligence</Label>
            <Select value={employeeId} onValueChange={setEmployeeId}>
              <SelectTrigger data-testid="loss-employee-select"><SelectValue placeholder="Choose a staff member" /></SelectTrigger>
              <SelectContent>
                {staff.map(s => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <p className="text-xs text-amber-600 mt-1" data-testid="loss-deduction-note">
              {money(value)} will be queued to come off their pay.
            </p>
          </div>
        )}

        {reason === 'donated' && (
          <div>
            <Label className="text-xs">Donated to</Label>
            <Input value={donatedTo} onChange={(e) => setDonatedTo(e.target.value)}
              placeholder="Name of the person, church or school" data-testid="loss-donated-to-input" />
          </div>
        )}

        <div>
          <Label className="text-xs">Note (optional)</Label>
          <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)}
            placeholder="Found dead in the brooder overnight" data-testid="loss-note-input" />
        </div>

        <div className="flex justify-between items-center border-t border-border pt-3 text-sm">
          <span className="text-muted-foreground">{reason === 'donated' ? 'Value donated' : 'Value lost'}</span>
          <span className="text-lg font-bold text-destructive" data-testid="loss-value">{money(value)}</span>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="loss-cancel-btn">Cancel</Button>
          <Button onClick={submit} disabled={busy || !qty} variant="destructive" data-testid="loss-submit-btn">
            {busy ? 'Saving…' : 'Write off & print slip'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
