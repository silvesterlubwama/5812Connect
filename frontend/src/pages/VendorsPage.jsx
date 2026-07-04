import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../components/ui/select';
import { Textarea } from '../components/ui/textarea';
import { toast } from 'sonner';
import api from '../services/api';
import { Truck, Search, Mail, Phone, ExternalLink, RefreshCw, FileText } from 'lucide-react';

const VENDOR_CATEGORIES = [
  { v: 'individual', label: 'Individual' },
  { v: 'corporation', label: 'Corporation' },
  { v: 'government', label: 'Government' },
  { v: 'utility', label: 'Utility' },
  { v: 'supplier', label: 'Supplier' },
  { v: 'contractor', label: 'Contractor' },
];
const CONTACT_METHODS = [
  { v: 'email', label: 'Email' }, { v: 'phone', label: 'Phone' }, { v: 'sms', label: 'SMS' },
  { v: 'whatsapp', label: 'WhatsApp' }, { v: 'in_person', label: 'In person' }, { v: 'postal', label: 'Postal' },
];

export default function VendorsPage() {
  const [vendors, setVendors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState(null);
  const [txns, setTxns] = useState({ expenses: [], bills: [] });
  const [editForm, setEditForm] = useState({});

  const fetchVendors = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get('/vendors', { params: { search: search || undefined, limit: 200 } });
      setVendors(r.data || []);
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to load vendors'); }
    finally { setLoading(false); }
  }, [search]);

  useEffect(() => { fetchVendors(); }, [fetchVendors]);

  const openDrilldown = async (v) => {
    setSelected(v);
    setEditForm({ ...v });
    try {
      const r = await api.get(`/vendors/${v.id}/transactions`);
      setTxns(r.data || { expenses: [], bills: [] });
    } catch { setTxns({ expenses: [], bills: [] }); }
  };

  const saveVendor = async () => {
    try {
      const payload = {
        name: editForm.name, category: editForm.category,
        email: editForm.email || '', phone: editForm.phone || '',
        preferred_contact: editForm.preferred_contact,
        notes: editForm.notes || '', address: editForm.address || '',
        contact_name: editForm.contact_name || '',
        payment_terms_days: parseInt(editForm.payment_terms_days) || 30,
        vat_registered: !!editForm.vat_registered, tin: editForm.tin || '',
      };
      await api.put(`/vendors/${selected.id}`, payload);
      toast.success('Vendor updated');
      await fetchVendors();
      setSelected({ ...selected, ...payload });
    } catch (err) { toast.error(err.response?.data?.detail || 'Save failed'); }
  };

  const fmt = (n) => (n || 0).toLocaleString();

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2"><Truck size={22} /><h1 className="text-2xl font-bold">Vendors</h1><Badge variant="secondary">{vendors.length}</Badge></div>
        <div className="relative"><Search size={14} className="absolute left-2 top-2.5 text-muted-foreground" /><Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search by name..." className="pl-8 h-9 w-56" data-testid="vendor-search-input" /></div>
      </div>

      <Card className="rounded-xl shadow-soft">
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead><tr className="border-b bg-muted/50"><th className="p-3 text-left text-xs">Name</th><th className="p-3 text-left text-xs">Category</th><th className="p-3 text-left text-xs">Contact</th><th className="p-3 text-right text-xs">Expense Total</th><th className="p-3 text-right text-xs"># Exp</th><th className="p-3 text-right text-xs">Bills</th><th className="p-3 w-16"></th></tr></thead>
            <tbody>
              {loading && <tr><td colSpan={7} className="p-6 text-center text-muted-foreground">Loading...</td></tr>}
              {!loading && vendors.length === 0 && <tr><td colSpan={7} className="p-6 text-center text-muted-foreground">No vendors yet. Add an expense on Finance to auto-create one.</td></tr>}
              {vendors.map(v => (
                <tr key={v.id} className="border-b last:border-0 hover:bg-accent/30 cursor-pointer" onClick={() => openDrilldown(v)} data-testid={`vendor-row-${v.id}`}>
                  <td className="p-3 font-medium">{v.name}{v.auto_created && <Badge variant="secondary" className="ml-2 text-[9px]">auto</Badge>}</td>
                  <td className="p-3"><Badge variant="outline" className="text-[10px]">{v.category || 'supplier'}</Badge></td>
                  <td className="p-3 text-xs text-muted-foreground">{v.email || v.phone || <span className="italic">—</span>}</td>
                  <td className="p-3 text-right font-mono text-rose-600">{fmt(v.total_expenses)}</td>
                  <td className="p-3 text-right">{v.expense_count || 0}</td>
                  <td className="p-3 text-right">{v.bill_count || 0}</td>
                  <td className="p-3 text-right"><ExternalLink size={14} className="text-muted-foreground" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Dialog open={!!selected} onOpenChange={o => !o && setSelected(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{selected?.name}</DialogTitle></DialogHeader>
          {selected && (
            <div className="space-y-6">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <Card><CardContent className="p-3"><p className="text-xs text-muted-foreground">Expense Total</p><p className="text-lg font-bold text-rose-600">{fmt(selected.total_expenses)}</p></CardContent></Card>
                <Card><CardContent className="p-3"><p className="text-xs text-muted-foreground"># Expenses</p><p className="text-lg font-bold">{selected.expense_count || 0}</p></CardContent></Card>
                <Card><CardContent className="p-3"><p className="text-xs text-muted-foreground">Bills</p><p className="text-lg font-bold">{selected.bill_count || 0}</p></CardContent></Card>
                <Card><CardContent className="p-3"><p className="text-xs text-muted-foreground">Contact</p><p className="text-sm">{selected.preferred_contact || 'email'}</p></CardContent></Card>
              </div>

              <div className="space-y-3 border rounded-lg p-4">
                <p className="text-sm font-semibold">Profile</p>
                <div className="grid sm:grid-cols-2 gap-3">
                  <div><Label>Name</Label><Input value={editForm.name || ''} onChange={e => setEditForm({...editForm, name: e.target.value})} data-testid="vendor-edit-name" /></div>
                  <div><Label>Category</Label>
                    <Select value={editForm.category || 'supplier'} onValueChange={v => setEditForm({...editForm, category: v})}>
                      <SelectTrigger data-testid="vendor-edit-category"><SelectValue /></SelectTrigger>
                      <SelectContent>{VENDOR_CATEGORIES.map(c => <SelectItem key={c.v} value={c.v}>{c.label}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div><Label><Mail size={12} className="inline mr-1" />Email</Label><Input type="email" value={editForm.email || ''} onChange={e => setEditForm({...editForm, email: e.target.value})} data-testid="vendor-edit-email" /></div>
                  <div><Label><Phone size={12} className="inline mr-1" />Phone</Label><Input value={editForm.phone || ''} onChange={e => setEditForm({...editForm, phone: e.target.value})} data-testid="vendor-edit-phone" /></div>
                  <div><Label>Contact person</Label><Input value={editForm.contact_name || ''} onChange={e => setEditForm({...editForm, contact_name: e.target.value})} /></div>
                  <div><Label>Preferred contact</Label>
                    <Select value={editForm.preferred_contact || 'email'} onValueChange={v => setEditForm({...editForm, preferred_contact: v})}>
                      <SelectTrigger data-testid="vendor-edit-contact"><SelectValue /></SelectTrigger>
                      <SelectContent>{CONTACT_METHODS.map(m => <SelectItem key={m.v} value={m.v}>{m.label}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div><Label>Payment terms (days)</Label><Input type="number" value={editForm.payment_terms_days || 30} onChange={e => setEditForm({...editForm, payment_terms_days: e.target.value})} /></div>
                  <div><Label>TIN</Label><Input value={editForm.tin || ''} onChange={e => setEditForm({...editForm, tin: e.target.value})} /></div>
                  <div><Label>Address</Label><Input value={editForm.address || ''} onChange={e => setEditForm({...editForm, address: e.target.value})} /></div>
                </div>
                <div><Label>Notes</Label><Textarea rows={2} value={editForm.notes || ''} onChange={e => setEditForm({...editForm, notes: e.target.value})} /></div>
              </div>

              <div className="space-y-2">
                <p className="text-sm font-semibold flex items-center gap-2"><FileText size={14} /> Expense history ({txns.expenses?.length || 0})</p>
                <div className="border rounded-lg divide-y max-h-48 overflow-y-auto">
                  {(txns.expenses || []).length === 0 && <p className="p-4 text-xs text-muted-foreground text-center">No expenses</p>}
                  {(txns.expenses || []).map(t => (
                    <div key={t.id} className="p-3 flex items-center justify-between text-sm">
                      <div><p className="font-medium">{t.date} · {t.title || t.category}</p><p className="text-xs text-muted-foreground">{t.status} · {t.notes || ''}</p></div>
                      <p className="font-mono text-rose-600">-{fmt(t.amount)} {t.currency || 'UGX'}</p>
                    </div>
                  ))}
                </div>
                {(txns.bills || []).length > 0 && <>
                  <p className="text-sm font-semibold">Bills ({txns.bills.length})</p>
                  <div className="border rounded-lg divide-y max-h-32 overflow-y-auto">
                    {txns.bills.map(b => (
                      <div key={b.id} className="p-3 flex items-center justify-between text-sm">
                        <div><p className="font-medium">{b.bill_date || b.date} · {b.bill_number || b.id}</p><p className="text-xs text-muted-foreground">Due {b.due_date || '—'}</p></div>
                        <p className="font-mono">{fmt(b.amount_due)} {b.currency || 'UGX'}</p>
                      </div>
                    ))}
                  </div>
                </>}
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setSelected(null)}>Close</Button>
            <Button onClick={saveVendor} data-testid="vendor-save-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
