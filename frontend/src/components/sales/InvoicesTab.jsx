import React, { useState, useEffect, useCallback } from 'react';
import { invoicesApi } from '../../services/api';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Badge } from '../ui/badge';
import { Card, CardContent } from '../ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Plus, FileText, Edit2, Trash2, Printer, ShoppingCart, Search } from 'lucide-react';
import { toast } from 'sonner';
import InvoicePrintable from '../InvoicePrintable';

const fmt = (n, c = 'UGX') => `${c} ${(Number(n) || 0).toLocaleString()}`;

const STATUS_BADGE = {
  draft: 'bg-amber-100 text-amber-700 hover:bg-amber-200',
  sent: 'bg-blue-100 text-blue-700 hover:bg-blue-200',
  quote: 'bg-purple-100 text-purple-700 hover:bg-purple-200',
  converted: 'bg-green-100 text-green-700 hover:bg-green-200',
  cancelled: 'bg-slate-200 text-slate-700 hover:bg-slate-300',
};

const blankItem = () => ({ name: '', qty: 1, unit_price: 0, discount: 0 });
const blankForm = () => ({
  customer_name: 'Walk-in Customer', customer_phone: '', customer_email: '',
  items: [blankItem()], notes: '', due_date: '', payment_method: 'cash',
  discount: 0, tax_amount: 0,
});

export default function InvoicesTab({ products = [], onConverted }) {
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [showEditor, setShowEditor] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(blankForm());
  const [printInvoice, setPrintInvoice] = useState(null);
  const [printMode, setPrintMode] = useState('a4');
  const [showProductPicker, setShowProductPicker] = useState(false);
  const [pickerSearch, setPickerSearch] = useState('');

  const fetchInvoices = useCallback(async () => {
    setLoading(true);
    try {
      const res = await invoicesApi.list();
      setInvoices(res.data || []);
    } catch (e) { toast.error('Failed to load invoices'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchInvoices(); }, [fetchInvoices]);

  const total = (form.items || []).reduce((s, i) => s + ((i.qty || 0) * (i.unit_price || 0) - (i.discount || 0)), 0) - (form.discount || 0) + (form.tax_amount || 0);

  const openNew = () => {
    setEditingId(null);
    setForm(blankForm());
    setShowEditor(true);
  };

  const openEdit = (inv) => {
    setEditingId(inv.id);
    setForm({
      customer_name: inv.customer_name || '',
      customer_phone: inv.customer_phone || '',
      customer_email: inv.customer_email || '',
      items: (inv.items || []).map(i => ({ ...i })),
      notes: inv.notes || '',
      due_date: inv.due_date || '',
      payment_method: inv.payment_method || 'cash',
      discount: inv.discount || 0,
      tax_amount: inv.tax_amount || 0,
      status: inv.status,
    });
    setShowEditor(true);
  };

  const save = async (asQuote = false) => {
    if (!form.customer_name?.trim()) { toast.error('Customer name required'); return; }
    if (!(form.items || []).filter(i => i.name && i.qty > 0).length) { toast.error('At least one item required'); return; }
    const payload = {
      ...form,
      items: form.items.filter(i => i.name && i.qty > 0).map(i => ({
        ...i,
        qty: Number(i.qty) || 0,
        unit_price: Number(i.unit_price) || 0,
        discount: Number(i.discount) || 0,
      })),
      discount: Number(form.discount) || 0,
      tax_amount: Number(form.tax_amount) || 0,
    };
    try {
      if (editingId) {
        await invoicesApi.update(editingId, payload);
        toast.success('Invoice updated');
      } else {
        const res = await invoicesApi.create(payload, asQuote ? 'quote' : 'draft');
        toast.success(`${asQuote ? 'Quote' : 'Invoice'} ${res.data.invoice_number} created`);
      }
      setShowEditor(false);
      fetchInvoices();
    } catch (e) { toast.error(e.response?.data?.detail || 'Save failed'); }
  };

  const remove = async (inv) => {
    if (!window.confirm(`Delete invoice ${inv.invoice_number}?`)) return;
    try {
      await invoicesApi.delete(inv.id);
      setInvoices(prev => prev.filter(i => i.id !== inv.id));
      toast.success('Deleted');
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  // Add product (or variant) to invoice items from the inventory picker
  const addFromProduct = (product, variant = null) => {
    const item = {
      product_id: product.id,
      variant_id: variant?.id || null,
      name: product.name + (variant ? ` — ${variant.name}` : ''),
      qty: 1,
      unit_price: variant?.price ?? product.price ?? 0,
      discount: 0,
      units_per_pack: variant?.units_per_pack ?? 1,
      packaging_cost: variant?.packaging_cost ?? 0,
      packaging_label: variant?.packaging_label ?? '',
    };
    setForm(prev => ({ ...prev, items: [...(prev.items || []).filter(i => i.name), item] }));
    toast.success(`Added ${item.name}`);
  };

  const convert = async (inv) => {
    if (!window.confirm(`Convert ${inv.invoice_number} into a final sale? This decrements stock and creates a receipt.`)) return;
    try {
      const res = await invoicesApi.convert(inv.id, {});
      toast.success(`Sale recorded — receipt ${res.data.receipt_number}`);
      fetchInvoices();
      if (onConverted) onConverted(res.data);
    } catch (e) {
      let msg = e.response?.data?.detail;
      if (typeof msg === 'object' && msg !== null) {
        // Insufficient stock returns { error, items: [...] } — surface both
        if (msg.error && Array.isArray(msg.items)) {
          msg = `${msg.error}: ${msg.items.join('; ')}`;
        } else {
          msg = JSON.stringify(msg);
        }
      }
      toast.error(msg || 'Conversion failed');
      console.error('Invoice convert error:', e.response?.data || e);
    }
  };

  const filtered = invoices.filter(i => {
    if (filter !== 'all' && i.status !== filter) return false;
    if (search) {
      const s = search.toLowerCase();
      if (!(i.invoice_number || '').toLowerCase().includes(s) &&
          !(i.customer_name || '').toLowerCase().includes(s)) return false;
    }
    return true;
  });

  const counts = invoices.reduce((acc, i) => { acc[i.status] = (acc[i.status] || 0) + 1; return acc; }, {});

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input className="pl-9 h-9" placeholder="Search by invoice # or customer..." value={search} onChange={e => setSearch(e.target.value)} data-testid="invoice-search" />
        </div>
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger className="w-40 h-9" data-testid="invoice-filter"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All ({invoices.length})</SelectItem>
            <SelectItem value="draft">Draft ({counts.draft || 0})</SelectItem>
            <SelectItem value="quote">Quote ({counts.quote || 0})</SelectItem>
            <SelectItem value="sent">Sent ({counts.sent || 0})</SelectItem>
            <SelectItem value="converted">Converted ({counts.converted || 0})</SelectItem>
            <SelectItem value="cancelled">Cancelled ({counts.cancelled || 0})</SelectItem>
          </SelectContent>
        </Select>
        <Button onClick={openNew} className="gap-1.5" data-testid="new-invoice-btn"><Plus size={14} /> New Invoice</Button>
      </div>

      {loading ? (
        <div className="space-y-2">{[1,2,3].map(i => <div key={i} className="h-16 bg-muted animate-pulse rounded-lg" />)}</div>
      ) : filtered.length === 0 ? (
        <Card className="rounded-xl border-dashed"><CardContent className="p-8 text-center text-sm text-muted-foreground">
          <FileText size={28} className="mx-auto mb-2 opacity-40" />
          No invoices yet — click "New Invoice" to create one
        </CardContent></Card>
      ) : (
        <Card className="rounded-xl"><CardContent className="p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-border bg-muted/40">
              <th className="text-left p-3 font-medium text-muted-foreground">Invoice #</th>
              <th className="text-left p-3 font-medium text-muted-foreground">Customer</th>
              <th className="text-left p-3 font-medium text-muted-foreground">Items</th>
              <th className="text-right p-3 font-medium text-muted-foreground">Total</th>
              <th className="text-left p-3 font-medium text-muted-foreground">Status</th>
              <th className="text-left p-3 font-medium text-muted-foreground">Date</th>
              <th className="text-left p-3 font-medium text-muted-foreground"></th>
            </tr></thead>
            <tbody className="divide-y divide-border">
              {filtered.map(inv => (
                <tr key={inv.id} className="hover:bg-accent/30" data-testid={`invoice-row-${inv.invoice_number}`}>
                  <td className="p-3 font-mono text-xs text-primary font-semibold">{inv.invoice_number}</td>
                  <td className="p-3">{inv.customer_name}</td>
                  <td className="p-3 text-muted-foreground text-xs">{(inv.items || []).length} items</td>
                  <td className="p-3 font-bold text-primary text-right">{fmt(inv.total)}</td>
                  <td className="p-3"><Badge className={STATUS_BADGE[inv.status] || ''}>{inv.status}</Badge></td>
                  <td className="p-3 text-xs text-muted-foreground">{inv.created_at?.slice(0, 10)}</td>
                  <td className="p-3 flex gap-1 flex-wrap justify-end">
                    {inv.status !== 'converted' && inv.status !== 'cancelled' && (
                      <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => openEdit(inv)} data-testid={`edit-invoice-${inv.invoice_number}`}><Edit2 size={11} /></Button>
                    )}
                    <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => { setPrintInvoice(inv); setPrintMode('a4'); }} data-testid={`print-invoice-${inv.invoice_number}`}><Printer size={11} /></Button>
                    {inv.status !== 'converted' && inv.status !== 'cancelled' && (
                      <Button size="sm" className="h-7 text-xs gap-1 bg-green-600 hover:bg-green-700" onClick={() => convert(inv)} data-testid={`convert-invoice-${inv.invoice_number}`}>
                        <ShoppingCart size={11} /> Sale
                      </Button>
                    )}
                    {inv.status !== 'converted' && (
                      <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive" onClick={() => remove(inv)}><Trash2 size={11} /></Button>
                    )}
                    {inv.receipt_number && (
                      <span className="text-[10px] text-green-700 self-center">→ {inv.receipt_number}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent></Card>
      )}

      {/* Editor */}
      <Dialog open={showEditor} onOpenChange={setShowEditor}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editingId ? 'Edit Invoice' : 'New Invoice'}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-2">
              <div className="space-y-1"><Label className="text-xs">Customer Name *</Label>
                <Input value={form.customer_name} onChange={e => setForm({ ...form, customer_name: e.target.value })} data-testid="invoice-customer-name" />
              </div>
              <div className="space-y-1"><Label className="text-xs">Phone</Label>
                <Input value={form.customer_phone} onChange={e => setForm({ ...form, customer_phone: e.target.value })} />
              </div>
              <div className="space-y-1"><Label className="text-xs">Email</Label>
                <Input value={form.customer_email} onChange={e => setForm({ ...form, customer_email: e.target.value })} />
              </div>
            </div>

            <div className="space-y-2 border border-border rounded-lg p-3">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-semibold">Items</Label>
                <Button type="button" size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => setShowProductPicker(true)} data-testid="invoice-pick-product-btn">
                  <Plus size={11} /> Pick from inventory
                </Button>
              </div>
              {(form.items || []).map((item, i) => (
                <div key={i} className="grid grid-cols-[1fr_70px_90px_70px_28px] gap-2 items-center">
                  <Input className="h-8 text-xs" placeholder="Item name" value={item.name} onChange={e => {
                    const items = [...form.items]; items[i] = { ...items[i], name: e.target.value }; setForm({ ...form, items });
                  }} />
                  <Input className="h-8 text-xs" type="number" step="0.5" placeholder="Qty" value={item.qty} onChange={e => {
                    const items = [...form.items]; items[i] = { ...items[i], qty: Number(e.target.value) || 0 }; setForm({ ...form, items });
                  }} />
                  <Input className="h-8 text-xs" type="number" placeholder="Unit price" value={item.unit_price} onChange={e => {
                    const items = [...form.items]; items[i] = { ...items[i], unit_price: Number(e.target.value) || 0 }; setForm({ ...form, items });
                  }} />
                  <Input className="h-8 text-xs" type="number" placeholder="Disc" value={item.discount || 0} onChange={e => {
                    const items = [...form.items]; items[i] = { ...items[i], discount: Number(e.target.value) || 0 }; setForm({ ...form, items });
                  }} />
                  <button type="button" className="text-destructive text-sm" onClick={() => {
                    setForm({ ...form, items: form.items.filter((_, idx) => idx !== i) });
                  }}>×</button>
                </div>
              ))}
              <Button type="button" size="sm" variant="ghost" className="h-7 text-xs gap-1" onClick={() => setForm({ ...form, items: [...form.items, blankItem()] })} data-testid="invoice-add-item">
                <Plus size={11} /> Add custom item
              </Button>
            </div>

            <div className="grid grid-cols-4 gap-2">
              <div className="space-y-1"><Label className="text-xs">Discount</Label>
                <Input className="h-8 text-xs" type="number" value={form.discount} onChange={e => setForm({ ...form, discount: Number(e.target.value) || 0 })} />
              </div>
              <div className="space-y-1"><Label className="text-xs">Tax</Label>
                <Input className="h-8 text-xs" type="number" value={form.tax_amount} onChange={e => setForm({ ...form, tax_amount: Number(e.target.value) || 0 })} />
              </div>
              <div className="space-y-1"><Label className="text-xs">Due Date</Label>
                <Input className="h-8 text-xs" type="date" value={form.due_date} onChange={e => setForm({ ...form, due_date: e.target.value })} />
              </div>
              <div className="space-y-1"><Label className="text-xs">Payment</Label>
                <Select value={form.payment_method} onValueChange={v => setForm({ ...form, payment_method: v })}>
                  <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Cash</SelectItem>
                    <SelectItem value="mobile_money">Mobile Money</SelectItem>
                    <SelectItem value="bank_transfer">Bank Transfer</SelectItem>
                    <SelectItem value="card">Card</SelectItem>
                    <SelectItem value="cheque">Cheque</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1"><Label className="text-xs">Notes</Label>
              <Textarea rows={2} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
            </div>

            <div className="flex justify-between items-center bg-primary/10 rounded-lg p-3">
              <span className="text-sm font-semibold">Total</span>
              <span className="text-xl font-bold text-primary" data-testid="invoice-total">{fmt(total)}</span>
            </div>

            <div className="flex gap-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowEditor(false)}>Cancel</Button>
              {!editingId && (
                <Button variant="outline" className="flex-1 gap-1" onClick={() => save(true)} data-testid="invoice-save-quote-btn">
                  Save as Quote
                </Button>
              )}
              <Button className="flex-1" onClick={() => save(false)} data-testid="invoice-save-btn">{editingId ? 'Update' : 'Create Invoice'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Print Invoice */}
      <Dialog open={!!printInvoice} onOpenChange={(o) => { if (!o) setPrintInvoice(null); }}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="flex items-center justify-between gap-2">
            <span>Invoice {printInvoice?.invoice_number}</span>
            <Select value={printMode} onValueChange={setPrintMode}>
              <SelectTrigger className="w-32 h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="a4">A4 (full page)</SelectItem>
                <SelectItem value="thermal">80mm thermal</SelectItem>
              </SelectContent>
            </Select>
          </DialogTitle></DialogHeader>
          {printInvoice && <InvoicePrintable invoice={printInvoice} mode={printMode} />}
        </DialogContent>
      </Dialog>

      {/* Inventory picker — products + variants */}
      <Dialog open={showProductPicker} onOpenChange={setShowProductPicker}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Pick from inventory</DialogTitle></DialogHeader>
          <Input
            autoFocus
            placeholder="Search by name or barcode..."
            value={pickerSearch}
            onChange={(e) => setPickerSearch(e.target.value)}
            data-testid="invoice-picker-search"
          />
          <div className="space-y-1 max-h-[55vh] overflow-y-auto" data-testid="invoice-picker-list">
            {(products || []).filter(p => {
              if (!pickerSearch) return true;
              const s = pickerSearch.toLowerCase();
              if (p.name?.toLowerCase().includes(s)) return true;
              if ((p.variants || []).some(v => (v.name || '').toLowerCase().includes(s) || (v.barcode || '').toLowerCase().includes(s))) return true;
              return false;
            }).map(p => (
              <div key={p.id} className="border border-border rounded-md p-2">
                {!p.has_variants ? (
                  <button type="button" onClick={() => addFromProduct(p)}
                    className="w-full text-left p-2 rounded hover:bg-accent transition-colors flex items-center justify-between gap-3"
                    data-testid={`invoice-pick-product-${p.id}`}>
                    <div>
                      <p className="text-sm font-medium">{p.name}</p>
                      <p className="text-[10px] text-muted-foreground">{p.category} · stock {p.stock}</p>
                    </div>
                    <span className="text-sm font-bold text-primary">{p.currency || 'UGX'} {(p.price || 0).toLocaleString()}</span>
                  </button>
                ) : (
                  <div>
                    <p className="text-xs font-semibold px-2 mb-1">{p.name} <span className="text-[10px] font-normal text-muted-foreground">· {(p.variants || []).length} variants</span></p>
                    <div className="space-y-0.5">
                      {(p.variants || []).map(v => (
                        <button key={v.id} type="button" onClick={() => addFromProduct(p, v)}
                          className="w-full text-left p-1.5 rounded hover:bg-accent transition-colors flex items-center justify-between gap-3 text-xs"
                          data-testid={`invoice-pick-variant-${v.id}`}>
                          <div className="min-w-0 flex-1">
                            <p className="font-medium">{v.name}{v.units_per_pack > 1 ? ` (${v.units_per_pack} units)` : ''}</p>
                            <p className="text-[9px] text-muted-foreground font-mono truncate">{v.barcode || '—'}</p>
                          </div>
                          <span className="text-xs text-muted-foreground">stock {v.stock || 0}</span>
                          <span className="font-bold text-primary">{p.currency || 'UGX'} {(v.price || 0).toLocaleString()}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
            {(products || []).length === 0 && <p className="text-center text-sm text-muted-foreground py-6">No products in inventory.</p>}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
