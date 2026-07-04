import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../components/ui/select';
import { Textarea } from '../components/ui/textarea';
import { toast } from 'sonner';
import api from '../services/api';
import { Users, Search, Mail, Phone, TrendingUp, ExternalLink, RefreshCw } from 'lucide-react';

/**
 * DonorsPage — auto-created donor profiles + drilldown of transactions.
 * Category, preferred contact and notes are editable inline on the drilldown.
 */
const DONOR_CATEGORIES = [
  { v: 'individual', label: 'Individual' },
  { v: 'corporation', label: 'Corporation' },
  { v: 'church', label: 'Church' },
  { v: 'government', label: 'Government' },
  { v: 'foundation', label: 'Foundation' },
  { v: 'anonymous', label: 'Anonymous' },
];
const CONTACT_METHODS = [
  { v: 'email', label: 'Email' },
  { v: 'phone', label: 'Phone' },
  { v: 'sms', label: 'SMS' },
  { v: 'whatsapp', label: 'WhatsApp' },
  { v: 'in_person', label: 'In person' },
  { v: 'postal', label: 'Postal' },
];

export default function DonorsPage() {
  const [donors, setDonors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState(null);
  const [txns, setTxns] = useState([]);
  const [editForm, setEditForm] = useState({});

  const fetchDonors = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get('/donors', { params: { search: search || undefined, limit: 200 } });
      setDonors(r.data || []);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to load donors');
    } finally { setLoading(false); }
  }, [search]);

  useEffect(() => { fetchDonors(); }, [fetchDonors]);

  const openDrilldown = async (d) => {
    setSelected(d);
    setEditForm({ ...d });
    try {
      const r = await api.get(`/donors/${d.id}/transactions`);
      setTxns(r.data || []);
    } catch { setTxns([]); }
  };

  const saveDonor = async () => {
    try {
      const payload = {
        name: editForm.name,
        category: editForm.category,
        email: editForm.email || '',
        phone: editForm.phone || '',
        preferred_contact: editForm.preferred_contact,
        notes: editForm.notes || '',
        address: editForm.address || '',
      };
      await api.put(`/donors/${selected.id}`, payload);
      toast.success('Donor updated');
      await fetchDonors();
      setSelected({ ...selected, ...payload });
    } catch (err) { toast.error(err.response?.data?.detail || 'Save failed'); }
  };

  const runBackfill = async () => {
    if (!window.confirm('Scan all historical donations and expenses; auto-create any missing donor/vendor profiles. Safe & idempotent. Continue?')) return;
    try {
      const r = await api.post('/donors-vendors/backfill');
      toast.success(r.data.message, { duration: 6000 });
      fetchDonors();
    } catch (err) { toast.error(err.response?.data?.detail || 'Backfill failed'); }
  };

  const fmt = (n) => (n || 0).toLocaleString();

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2"><Users size={22} /><h1 className="text-2xl font-bold">Donors</h1><Badge variant="secondary">{donors.length}</Badge></div>
        <div className="flex items-center gap-2">
          <div className="relative"><Search size={14} className="absolute left-2 top-2.5 text-muted-foreground" /><Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search by name..." className="pl-8 h-9 w-56" data-testid="donor-search-input" /></div>
          <Button variant="outline" size="sm" onClick={runBackfill} data-testid="donors-backfill-btn"><RefreshCw size={14} className="mr-1" /> Backfill</Button>
        </div>
      </div>

      <Card className="rounded-xl shadow-soft">
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead><tr className="border-b bg-muted/50"><th className="p-3 text-left text-xs">Name</th><th className="p-3 text-left text-xs">Category</th><th className="p-3 text-left text-xs">Contact</th><th className="p-3 text-right text-xs">Total Donated</th><th className="p-3 text-right text-xs"># Gifts</th><th className="p-3 text-right text-xs">Last Gift</th><th className="p-3 w-16"></th></tr></thead>
            <tbody>
              {loading && <tr><td colSpan={7} className="p-6 text-center text-muted-foreground">Loading...</td></tr>}
              {!loading && donors.length === 0 && <tr><td colSpan={7} className="p-6 text-center text-muted-foreground">No donors yet. Add a donation on Finance to auto-create one.</td></tr>}
              {donors.map(d => (
                <tr key={d.id} className="border-b last:border-0 hover:bg-accent/30 cursor-pointer" onClick={() => openDrilldown(d)} data-testid={`donor-row-${d.id}`}>
                  <td className="p-3 font-medium">{d.name}{d.auto_created && <Badge variant="secondary" className="ml-2 text-[9px]">auto</Badge>}</td>
                  <td className="p-3"><Badge variant="outline" className="text-[10px]">{d.category || 'individual'}</Badge></td>
                  <td className="p-3 text-xs text-muted-foreground">{d.email || d.phone || <span className="italic">—</span>}</td>
                  <td className="p-3 text-right font-mono text-green-600">{fmt(d.total_donated)}</td>
                  <td className="p-3 text-right">{d.donation_count || 0}</td>
                  <td className="p-3 text-right text-xs text-muted-foreground">{d.last_donation_date || '—'}</td>
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
                <Card><CardContent className="p-3"><p className="text-xs text-muted-foreground">Total Donated</p><p className="text-lg font-bold text-green-600">{fmt(selected.total_donated)}</p></CardContent></Card>
                <Card><CardContent className="p-3"><p className="text-xs text-muted-foreground"># Gifts</p><p className="text-lg font-bold">{selected.donation_count || 0}</p></CardContent></Card>
                <Card><CardContent className="p-3"><p className="text-xs text-muted-foreground">Last Gift</p><p className="text-sm font-medium">{selected.last_donation_date || '—'}</p></CardContent></Card>
                <Card><CardContent className="p-3"><p className="text-xs text-muted-foreground">Contact</p><p className="text-sm">{selected.preferred_contact || 'email'}</p></CardContent></Card>
              </div>

              <div className="space-y-3 border rounded-lg p-4">
                <p className="text-sm font-semibold flex items-center gap-2"><TrendingUp size={14} /> Profile</p>
                <div className="grid sm:grid-cols-2 gap-3">
                  <div><Label>Name</Label><Input value={editForm.name || ''} onChange={e => setEditForm({...editForm, name: e.target.value})} data-testid="donor-edit-name" /></div>
                  <div><Label>Category</Label>
                    <Select value={editForm.category || 'individual'} onValueChange={v => setEditForm({...editForm, category: v})}>
                      <SelectTrigger data-testid="donor-edit-category"><SelectValue /></SelectTrigger>
                      <SelectContent>{DONOR_CATEGORIES.map(c => <SelectItem key={c.v} value={c.v}>{c.label}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div><Label><Mail size={12} className="inline mr-1" />Email</Label><Input type="email" value={editForm.email || ''} onChange={e => setEditForm({...editForm, email: e.target.value})} data-testid="donor-edit-email" /></div>
                  <div><Label><Phone size={12} className="inline mr-1" />Phone</Label><Input value={editForm.phone || ''} onChange={e => setEditForm({...editForm, phone: e.target.value})} data-testid="donor-edit-phone" /></div>
                  <div><Label>Preferred contact</Label>
                    <Select value={editForm.preferred_contact || 'email'} onValueChange={v => setEditForm({...editForm, preferred_contact: v})}>
                      <SelectTrigger data-testid="donor-edit-contact"><SelectValue /></SelectTrigger>
                      <SelectContent>{CONTACT_METHODS.map(m => <SelectItem key={m.v} value={m.v}>{m.label}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div><Label>Address</Label><Input value={editForm.address || ''} onChange={e => setEditForm({...editForm, address: e.target.value})} /></div>
                </div>
                <div><Label>Notes</Label><Textarea rows={2} value={editForm.notes || ''} onChange={e => setEditForm({...editForm, notes: e.target.value})} /></div>
              </div>

              <div className="space-y-2">
                <p className="text-sm font-semibold">Donation history ({txns.length})</p>
                <div className="border rounded-lg divide-y max-h-64 overflow-y-auto">
                  {txns.length === 0 && <p className="p-4 text-xs text-muted-foreground text-center">No transactions yet</p>}
                  {txns.map(t => (
                    <div key={t.id} className="p-3 flex items-center justify-between text-sm">
                      <div><p className="font-medium">{t.date}</p><p className="text-xs text-muted-foreground">{t.type} · {t.notes || 'No notes'}</p></div>
                      <p className="font-mono text-green-600">+{fmt(t.amount)} {t.currency || 'UGX'}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setSelected(null)}>Close</Button>
            <Button onClick={saveDonor} data-testid="donor-save-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
