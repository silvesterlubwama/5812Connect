import React, { useState, useEffect } from 'react';
import { Plus, Trash2, FileText, Check, X, Send, Package, DollarSign } from 'lucide-react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Textarea } from '../components/ui/textarea';
import { purchaseOrdersApi, locationsApi } from '../services/api';
import api from '../services/api';
import { toast } from 'sonner';

const STATUS_COLORS = {
  draft: 'bg-slate-200 text-slate-700',
  submitted: 'bg-blue-100 text-blue-700',
  approved: 'bg-emerald-100 text-emerald-700',
  received: 'bg-amber-100 text-amber-700',
  billed: 'bg-purple-100 text-purple-700',
  closed: 'bg-green-100 text-green-800',
  cancelled: 'bg-red-100 text-red-700',
};

const emptyLine = () => ({ description: '', qty: 1, unit: 'ea', unit_price: 0, account_id: '' });

export default function PurchaseOrdersPage() {
  const [pos, setPos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [showCreate, setShowCreate] = useState(false);
  const [openPo, setOpenPo] = useState(null);
  const [vendors, setVendors] = useState([]);
  const [locations, setLocations] = useState([]);
  const [form, setForm] = useState({
    vendor_id: '', vendor_name: '', location_id: '', currency: 'UGX',
    requested_date: new Date().toISOString().slice(0, 10),
    delivery_date: '', notes: '', tax: 0,
    lines: [emptyLine()],
  });

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [pR, vR, lR] = await Promise.all([
        purchaseOrdersApi.list({ status: statusFilter }),
        api.get('/vendors').catch(() => ({ data: [] })),
        locationsApi.list().catch(() => ({ data: [] })),
      ]);
      setPos(pR.data || []);
      setVendors(vR.data || []);
      setLocations(lR.data || []);
    } catch { toast.error('Failed to load POs'); }
    finally { setLoading(false); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchAll(); }, [statusFilter]);

  const totals = () => {
    const subtotal = form.lines.reduce((s, l) => s + (parseFloat(l.qty) || 0) * (parseFloat(l.unit_price) || 0), 0);
    return { subtotal: subtotal.toFixed(2), total: (subtotal + (parseFloat(form.tax) || 0)).toFixed(2) };
  };

  const saveNew = async () => {
    if (!form.vendor_name.trim()) return toast.error('Vendor required');
    if (!form.lines.some(l => l.description.trim())) return toast.error('At least one line item');
    try {
      await purchaseOrdersApi.create({
        ...form,
        lines: form.lines.filter(l => l.description.trim()).map(l => ({
          ...l, qty: parseFloat(l.qty) || 0, unit_price: parseFloat(l.unit_price) || 0,
        })),
        tax: parseFloat(form.tax) || 0,
      });
      toast.success('Purchase order created');
      setShowCreate(false);
      setForm({ vendor_id: '', vendor_name: '', location_id: '', currency: 'UGX',
        requested_date: new Date().toISOString().slice(0, 10), delivery_date: '',
        notes: '', tax: 0, lines: [emptyLine()] });
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const transition = async (poId, to) => {
    try {
      await purchaseOrdersApi.transition(poId, { to });
      toast.success(`Moved to ${to}`);
      fetchAll();
      if (openPo?.id === poId) {
        const fresh = await purchaseOrdersApi.get(poId);
        setOpenPo(fresh.data);
      }
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const deletePo = async (poId) => {
    if (!window.confirm('Delete this draft/cancelled PO?')) return;
    try {
      await purchaseOrdersApi.delete(poId);
      toast.success('Deleted');
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const nextActions = (status) => {
    if (status === 'draft') return [{ to: 'submitted', label: 'Submit', icon: Send }, { to: 'cancelled', label: 'Cancel', icon: X, variant: 'ghost' }];
    if (status === 'submitted') return [{ to: 'approved', label: 'Approve', icon: Check }, { to: 'draft', label: 'Return to draft', icon: FileText, variant: 'ghost' }];
    if (status === 'approved') return [{ to: 'received', label: 'Mark received', icon: Package }];
    if (status === 'received') return [{ to: 'billed', label: 'Mark billed', icon: DollarSign }, { to: 'closed', label: 'Close', icon: Check, variant: 'outline' }];
    if (status === 'billed') return [{ to: 'closed', label: 'Close', icon: Check }];
    return [];
  };

  return (
    <div className="p-6 space-y-6" data-testid="purchase-orders-page">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Purchase Orders</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Draft → Submit → Approve → Receive → Bill → Close</p>
        </div>
        <div className="flex gap-2 items-center">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="h-9 w-40" data-testid="po-status-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              {Object.keys(STATUS_COLORS).map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button onClick={() => setShowCreate(true)} className="gap-2" data-testid="po-new-btn"><Plus size={14} /> New PO</Button>
        </div>
      </div>

      {loading ? (
        <div className="grid gap-3">{[1, 2, 3].map(i => <div key={i} className="h-20 bg-muted animate-pulse rounded-xl" />)}</div>
      ) : pos.length === 0 ? (
        <Card className="rounded-xl"><CardContent className="py-16 text-center text-muted-foreground">
          <FileText size={40} className="mx-auto mb-3 opacity-30" />
          No purchase orders yet.
        </CardContent></Card>
      ) : (
        <div className="space-y-2">
          {pos.map(po => (
            <Card key={po.id} className="rounded-xl hover:border-primary/40 cursor-pointer" onClick={() => setOpenPo(po)} data-testid={`po-row-${po.id}`}>
              <CardContent className="p-3 flex items-center gap-3 flex-wrap">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold font-mono">{po.po_number}</p>
                  <p className="text-xs text-muted-foreground">{po.vendor_name || 'No vendor'} · {po.requested_date}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-semibold">{po.currency} {(po.total || 0).toLocaleString()}</p>
                  <p className="text-[10px] text-muted-foreground">{po.lines?.length || 0} line(s)</p>
                </div>
                <Badge className={`${STATUS_COLORS[po.status]} text-[10px]`} data-testid={`po-status-${po.id}`}>{po.status}</Badge>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New Purchase Order</DialogTitle><DialogDescription>Line items are required. Number auto-generated on save.</DialogDescription></DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Vendor name *</Label><Input value={form.vendor_name} onChange={e => setForm({ ...form, vendor_name: e.target.value })} placeholder="Vendor / supplier" data-testid="po-vendor-name" list="po-vendor-list" />
                <datalist id="po-vendor-list">{vendors.map(v => <option key={v.id} value={v.name} />)}</datalist>
              </div>
              <div><Label>Campus</Label>
                <Select value={form.location_id || '_none'} onValueChange={v => setForm({ ...form, location_id: v === '_none' ? '' : v })}>
                  <SelectTrigger data-testid="po-location"><SelectValue placeholder="Pick campus" /></SelectTrigger>
                  <SelectContent><SelectItem value="_none">— My campus —</SelectItem>{locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div><Label>Currency</Label><Input value={form.currency} onChange={e => setForm({ ...form, currency: e.target.value.toUpperCase() })} maxLength={5} /></div>
              <div><Label>Requested</Label><Input type="date" value={form.requested_date} onChange={e => setForm({ ...form, requested_date: e.target.value })} /></div>
              <div><Label>Delivery by</Label><Input type="date" value={form.delivery_date} onChange={e => setForm({ ...form, delivery_date: e.target.value })} /></div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-1"><Label>Line items *</Label><Button type="button" size="sm" variant="ghost" onClick={() => setForm({ ...form, lines: [...form.lines, emptyLine()] })} data-testid="po-add-line"><Plus size={12} className="mr-1" />Add line</Button></div>
              <div className="space-y-1">
                {form.lines.map((ln, i) => (
                  <div key={i} className="grid grid-cols-12 gap-1 items-center">
                    <Input className="col-span-6 h-8 text-xs" placeholder="Description" value={ln.description} onChange={e => setForm({ ...form, lines: form.lines.map((l, j) => j === i ? { ...l, description: e.target.value } : l) })} data-testid={`po-line-desc-${i}`} />
                    <Input className="col-span-2 h-8 text-xs" type="number" min="0" step="any" placeholder="Qty" value={ln.qty} onChange={e => setForm({ ...form, lines: form.lines.map((l, j) => j === i ? { ...l, qty: e.target.value } : l) })} data-testid={`po-line-qty-${i}`} />
                    <Input className="col-span-3 h-8 text-xs" type="number" min="0" step="any" placeholder="Unit price" value={ln.unit_price} onChange={e => setForm({ ...form, lines: form.lines.map((l, j) => j === i ? { ...l, unit_price: e.target.value } : l) })} data-testid={`po-line-price-${i}`} />
                    <Button type="button" size="sm" variant="ghost" className="col-span-1 h-8 w-8 p-0 text-destructive" onClick={() => setForm({ ...form, lines: form.lines.filter((_, j) => j !== i) })} disabled={form.lines.length === 1}><Trash2 size={12} /></Button>
                  </div>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 items-center">
              <div><Label>Tax</Label><Input type="number" min="0" step="any" value={form.tax} onChange={e => setForm({ ...form, tax: e.target.value })} /></div>
              <div className="text-right text-sm"><p className="text-muted-foreground">Subtotal: <strong>{form.currency} {totals().subtotal}</strong></p><p className="text-lg font-bold">Total: {form.currency} {totals().total}</p></div>
            </div>
            <div><Label>Notes</Label><Textarea rows={2} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} /></div>
          </div>
          <div className="flex gap-2 pt-3"><Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button><div className="flex-1" /><Button onClick={saveNew} data-testid="po-save">Create draft</Button></div>
        </DialogContent>
      </Dialog>

      {/* Detail dialog */}
      <Dialog open={!!openPo} onOpenChange={o => { if (!o) setOpenPo(null); }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          {openPo && <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-3">{openPo.po_number} <Badge className={STATUS_COLORS[openPo.status]}>{openPo.status}</Badge></DialogTitle>
              <DialogDescription>{openPo.vendor_name} · {openPo.requested_date} · {openPo.currency} {(openPo.total || 0).toLocaleString()}</DialogDescription>
            </DialogHeader>
            <div className="space-y-2">
              <div className="text-xs text-muted-foreground">Requested by <strong>{openPo.requested_by_name || openPo.requested_by}</strong>{openPo.delivery_date ? ` · Delivery by ${openPo.delivery_date}` : ''}</div>
              <table className="w-full text-sm">
                <thead><tr className="border-b text-xs text-muted-foreground text-left"><th>Description</th><th className="text-right">Qty</th><th className="text-right">Unit price</th><th className="text-right">Line total</th><th className="text-right">Received</th></tr></thead>
                <tbody>
                  {(openPo.lines || []).map((l, i) => (
                    <tr key={i} className="border-b"><td className="py-1">{l.description}</td><td className="text-right">{l.qty} {l.unit || ''}</td><td className="text-right">{l.unit_price?.toLocaleString?.() || l.unit_price}</td><td className="text-right">{(l.line_total || 0).toLocaleString()}</td><td className="text-right">{l.received_qty || 0}</td></tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr><td colSpan={3} className="text-right pt-2">Subtotal:</td><td className="text-right pt-2">{(openPo.subtotal || 0).toLocaleString()}</td><td /></tr>
                  <tr><td colSpan={3} className="text-right">Tax:</td><td className="text-right">{(openPo.tax || 0).toLocaleString()}</td><td /></tr>
                  <tr className="font-bold"><td colSpan={3} className="text-right">Total:</td><td className="text-right">{(openPo.total || 0).toLocaleString()}</td><td /></tr>
                </tfoot>
              </table>
              {openPo.notes && <p className="text-xs text-muted-foreground italic border-t pt-2">{openPo.notes}</p>}
            </div>
            <div className="flex gap-2 pt-3 flex-wrap border-t">
              {nextActions(openPo.status).map(a => {
                const Icon = a.icon;
                return <Button key={a.to} variant={a.variant || 'default'} size="sm" onClick={() => transition(openPo.id, a.to)} className="gap-1" data-testid={`po-${a.to}-btn`}><Icon size={13} />{a.label}</Button>;
              })}
              {(openPo.status === 'draft' || openPo.status === 'cancelled') && <Button variant="ghost" size="sm" className="text-destructive gap-1" onClick={() => { deletePo(openPo.id); setOpenPo(null); }}><Trash2 size={13} />Delete</Button>}
              <div className="flex-1" />
              <Button variant="outline" size="sm" onClick={() => setOpenPo(null)}>Close</Button>
            </div>
          </>}
        </DialogContent>
      </Dialog>
    </div>
  );
}
