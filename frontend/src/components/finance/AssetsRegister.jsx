import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Building2, Plus, Wrench, TrendingUp, Trash2, ChevronDown, ChevronRight, Info, Pencil, GitMerge } from 'lucide-react';
import { Card, CardContent } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { Textarea } from '../ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { toast } from 'sonner';

const CATEGORIES = ['equipment', 'vehicle', 'building', 'land', 'furniture', 'livestock', 'IT', 'other'];
const CONDITIONS = ['good', 'fair', 'poor', 'written off'];
const CURRENCIES = ['UGX', 'USD', 'KES', 'EUR', 'GBP'];
const money = (n, cur) => new Intl.NumberFormat('en-US', {
  style: 'currency', currency: cur || 'UGX', maximumFractionDigits: 2,
}).format(Number(n || 0));
const BLANK_ASSET = {
  name: '', category: 'equipment', value: '', purchase_date: '', depreciation_years: 5,
  serial_number: '', condition: 'good', notes: '',
  post_expense: false, vendor: '', reference: '', paid_from_account_id: '',
};
const BLANK_SPEND = {
  kind: 'improvement', amount: '', date: '', description: '', vendor: '', reference: '',
  extends_life_years: '', post_expense: false, paid_from_account_id: '',
};

/** Money actually leaving a cash account — reuses the normal expense entry. */
const ExpenseOption = ({ form, setForm, accounts, expenseAccounts, hint }) => (
  <div className="rounded-lg border p-3 space-y-2" data-testid="asset-expense-option">
    <label className="flex items-start justify-between gap-3 cursor-pointer">
      <span className="text-xs">
        <span className="block font-medium text-sm">Also record this as an expense</span>
        <span className="text-muted-foreground">{hint}</span>
      </span>
      <Switch checked={!!form.post_expense} data-testid="asset-post-expense-toggle"
        onCheckedChange={v => setForm({ ...form, post_expense: v })} />
    </label>
    {form.post_expense && (
      <div className="space-y-1.5">
        <Label className="text-xs">Expense account</Label>
        <Select value={form.expense_account_id || '__default__'}
          onValueChange={v => setForm({ ...form, expense_account_id: v === '__default__' ? '' : v })}>
          <SelectTrigger className="h-8 text-xs" data-testid="asset-expense-account-select"><SelectValue placeholder="Expense account" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="__default__">Default expenses account</SelectItem>
            {expenseAccounts.map(a => <SelectItem key={a.id} value={a.id}>{a.code} — {a.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Label className="text-xs">Paid from</Label>
        <Select value={form.paid_from_account_id || '__none__'}
          onValueChange={v => setForm({ ...form, paid_from_account_id: v === '__none__' ? '' : v })}>
          <SelectTrigger className="h-8 text-xs" data-testid="asset-paid-from-select"><SelectValue placeholder="Cash / bank account" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">Use the campus default account</SelectItem>
            {accounts.map(a => <SelectItem key={a.id} value={a.id}>{a.code} — {a.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <p className="text-[11px] text-muted-foreground">
          Goes through the normal expense entry, so the account is drawn down and the vendor is recorded.
        </p>
      </div>
    )}
  </div>
);

// Fixed assets, and the one distinction auditors and customs care about:
// spending that extends an asset's life or capacity is capitalised onto its
// cost; spending that merely keeps it working is a repairs expense.
export const AssetsRegister = () => {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState({});
  const [showAsset, setShowAsset] = useState(false);
  const [assetForm, setAssetForm] = useState(BLANK_ASSET);
  const [editAsset, setEditAsset] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [spendFor, setSpendFor] = useState(null);
  const [spendForm, setSpendForm] = useState(BLANK_SPEND);
  const [saving, setSaving] = useState(false);
  const [accounts, setAccounts] = useState([]);
  const [expenseAccounts, setExpenseAccounts] = useState([]);
  const [locations, setLocations] = useState([]);
  const [selected, setSelected] = useState([]);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergeKeep, setMergeKeep] = useState('');
  const [combineValues, setCombineValues] = useState(true);
  const [confirmDelete, setConfirmDelete] = useState(null);

  const activeCampusId = user?.active_campus_id || user?.location_id || '';
  const activeCurrency = useMemo(() => {
    const id = user?.active_campus_id || user?.location_id;
    const loc = locations.find(l => l.id === id) || locations[0];
    return loc?.currency || 'UGX';
  }, [locations, user]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get('/finance/assets');
      setData(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not load the asset register'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    load();
    api.get('/finance/chart-of-accounts').then(r => {
      const rows = (r.data || []).filter(a => a.active !== false);
      setAccounts(rows.filter(a => a.is_cash));
      setExpenseAccounts(rows.filter(a => a.type === 'expense'));
    }).catch(() => {});
    api.get('/locations').then(r => setLocations(r.data || [])).catch(() => {});
  }, [load]);

  const createAsset = async () => {
    if (!assetForm.name.trim() || !assetForm.value) { toast.error('Name and purchase cost are needed'); return; }
    setSaving(true);
    try {
      const r = await api.post('/finance/assets', {
        ...assetForm, value: Number(assetForm.value), currency: assetForm.currency || activeCurrency,
        location_id: assetForm.location_id || activeCampusId,
      });
      toast.success(r.data?.purchase_expense_id ? 'Asset added and the expense recorded' : 'Asset added to the register');
      setShowAsset(false); setAssetForm(BLANK_ASSET); load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not save'); }
    finally { setSaving(false); }
  };

  const saveEdit = async () => {
    setSaving(true);
    try {
      await api.put(`/finance/assets/${editAsset.id}`, { ...editForm, value: Number(editForm.value || 0) });
      toast.success('Asset details updated');
      setEditAsset(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not save'); }
    finally { setSaving(false); }
  };

  const removeAsset = async () => {
    try {
      await api.delete(`/finance/assets/${confirmDelete.id}`);
      toast.success(`${confirmDelete.name} removed from the register`);
      setConfirmDelete(null); setSelected([]); load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not delete'); }
  };

  const logSpend = async () => {
    setSaving(true);
    try {
      const r = await api.post(`/finance/assets/${spendFor.id}/spend`, {
        ...spendForm,
        amount: Number(spendForm.amount),
        currency: spendFor.currency || activeCurrency,
        extends_life_years: spendForm.extends_life_years ? Number(spendForm.extends_life_years) : 0,
      });
      toast.success(spendForm.kind === 'improvement'
        ? `Capitalised — ${spendFor.name} now carries ${money(r.data.asset.total_cost, spendFor.currency || activeCurrency)}`
        : 'Logged as a repairs & maintenance expense — the asset value is unchanged');
      setSpendFor(null); setSpendForm(BLANK_SPEND); load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not log that'); }
    finally { setSaving(false); }
  };

  const removeSpend = async (assetId, entryId) => {
    try {
      await api.delete(`/finance/assets/${assetId}/spend/${entryId}`);
      toast.success('Entry removed'); load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not remove'); }
  };

  const doMerge = async () => {
    setSaving(true);
    try {
      const r = await api.post('/finance/assets/merge', {
        target_id: mergeKeep,
        source_ids: selected.filter(id => id !== mergeKeep),
        combine_values: combineValues,
      });
      toast.success(`Merged ${r.data.merged.length} record(s) — ${r.data.entries_moved} spend entries moved across`);
      setMergeOpen(false); setSelected([]); load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not merge'); }
    finally { setSaving(false); }
  };

  const assets = data?.assets || [];
  const toggleSel = (id) => setSelected(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);

  return (
    <div className="space-y-4" data-testid="assets-register">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Assets on register', value: data?.count ?? 0, testid: 'assets-count' },
          { label: 'Purchase cost', value: money(data?.purchase_total, activeCurrency), testid: 'assets-purchase-total' },
          { label: 'Capitalised improvements', value: money(data?.improvements_total, activeCurrency), testid: 'assets-improvements-total' },
          { label: 'Carried cost', value: money(data?.total_cost, activeCurrency), testid: 'assets-total-cost' },
        ].map(s => (
          <Card key={s.label} className="rounded-xl">
            <CardContent className="p-3">
              <p className="text-[11px] text-muted-foreground">{s.label}</p>
              <p className="text-lg font-semibold" data-testid={s.testid}>{s.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="rounded-xl border-blue-200 bg-blue-50/40 dark:bg-blue-950/20">
        <CardContent className="p-3 text-xs text-blue-900 dark:text-blue-100 flex gap-2">
          <Info size={14} className="mt-0.5 shrink-0" />
          <span>
            <strong>Improvement or repair?</strong> If the money made the asset last longer or do more
            (new roof, deeper borehole, replacement engine) it is an <strong>improvement</strong> — it is added
            to what the asset cost. If it just kept it working (servicing, paint, tyres) it is a{' '}
            <strong>repair</strong> — an expense that never changes the asset&apos;s value.
          </span>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="text-sm font-medium">Asset register</p>
        <div className="flex items-center gap-2">
          {selected.length > 1 && (
            <Button size="sm" variant="outline" className="gap-1.5" data-testid="merge-assets-btn"
              onClick={() => { setMergeKeep(selected[0]); setMergeOpen(true); }}>
              <GitMerge size={13} /> Merge {selected.length}
            </Button>
          )}
          <Button size="sm" className="gap-1.5" onClick={() => setShowAsset(true)} data-testid="add-asset-btn">
            <Plus size={13} /> Add asset
          </Button>
        </div>
      </div>

      {loading && <div className="h-24 bg-muted animate-pulse rounded-xl" />}
      {!loading && assets.length === 0 && (
        <Card className="rounded-xl" data-testid="assets-empty">
          <CardContent className="py-12 text-center">
            <Building2 size={36} className="mx-auto mb-3 opacity-20" />
            <p className="text-sm text-muted-foreground">No fixed assets recorded yet</p>
            <p className="text-xs text-muted-foreground mt-1">
              Add the vehicles, buildings, boreholes and equipment you own, then log every improvement or repair against them.
            </p>
          </CardContent>
        </Card>
      )}

      <div className="space-y-2">
        {assets.map(a => {
          const rows = a.spend || [];
          const isOpen = !!open[a.id];
          const cur = a.currency || activeCurrency;
          return (
            <Card key={a.id} className={`rounded-xl ${selected.includes(a.id) ? 'ring-2 ring-primary/40' : ''}`} data-testid={`asset-${a.id}`}>
              <CardContent className="p-3">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="flex items-start gap-2 min-w-0">
                    <input type="checkbox" className="accent-primary mt-1" checked={selected.includes(a.id)}
                      onChange={() => toggleSel(a.id)} data-testid={`asset-select-${a.id}`} />
                    <button className="flex items-start gap-2 text-left min-w-0" onClick={() => setOpen(o => ({ ...o, [a.id]: !isOpen }))}
                      data-testid={`asset-toggle-${a.id}`}>
                      {isOpen ? <ChevronDown size={15} className="mt-0.5" /> : <ChevronRight size={15} className="mt-0.5" />}
                      <span className="min-w-0">
                        <span className="text-sm font-medium block truncate">{a.name}</span>
                        <span className="text-[11px] text-muted-foreground">
                          {[a.category, a.purchase_date && `bought ${a.purchase_date}`, a.serial_number,
                            `${a.depreciation_years}yr life`, a.condition,
                            (a.merged_assets || []).length ? `${a.merged_assets.length} merged in` : '']
                            .filter(Boolean).join(' · ')}
                        </span>
                      </span>
                    </button>
                  </div>
                  <div className="flex items-center gap-4 text-xs shrink-0">
                    <span className="text-right">
                      <span className="block text-muted-foreground text-[10px]">Purchase</span>
                      {money(a.value, cur)}
                    </span>
                    <span className="text-right">
                      <span className="block text-muted-foreground text-[10px]">Improvements</span>
                      <span className={a.improvements_total ? 'text-emerald-700 font-medium' : ''}>{money(a.improvements_total, cur)}</span>
                    </span>
                    <span className="text-right">
                      <span className="block text-muted-foreground text-[10px]">Carried cost</span>
                      <span className="font-semibold" data-testid={`asset-total-${a.id}`}>{money(a.total_cost, cur)}</span>
                    </span>
                    <span className="text-right">
                      <span className="block text-muted-foreground text-[10px]">Repairs to date</span>
                      <span className="text-muted-foreground">{money(a.repairs_total, cur)}</span>
                    </span>
                    <Button size="sm" variant="outline" className="h-7 gap-1 text-[11px]"
                      onClick={() => { setSpendFor(a); setSpendForm({ ...BLANK_SPEND, date: new Date().toISOString().slice(0, 10) }); }}
                      data-testid={`asset-log-spend-${a.id}`}>
                      <Wrench size={12} /> Log spend
                    </Button>
                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0" data-testid={`asset-edit-${a.id}`}
                      onClick={() => {
                        setEditAsset(a);
                        setEditForm({
                          name: a.name || '', category: a.category || 'equipment', value: a.value ?? '',
                          currency: cur, purchase_date: a.purchase_date || '',
                          depreciation_years: a.depreciation_years ?? 5, serial_number: a.serial_number || '',
                          condition: a.condition || 'good', notes: a.notes || '',
                          location_id: a.location_id || '',
                        });
                      }}><Pencil size={12} /></Button>
                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" data-testid={`asset-delete-${a.id}`}
                      onClick={() => setConfirmDelete(a)}><Trash2 size={12} /></Button>
                  </div>
                </div>

                {isOpen && (
                  <div className="mt-3 rounded-lg border divide-y" data-testid={`asset-history-${a.id}`}>
                    {rows.length === 0 && (
                      <p className="p-2.5 text-[11px] text-muted-foreground">Nothing spent on this asset yet.</p>
                    )}
                    {rows.map(r => (
                      <div key={r.id} className="flex items-center gap-2 p-2.5 text-[11px]" data-testid={`asset-entry-${r.id}`}>
                        <Badge variant={r.kind === 'improvement' ? 'default' : 'outline'} className="text-[9px] gap-1 shrink-0">
                          {r.kind === 'improvement' ? <TrendingUp size={9} /> : <Wrench size={9} />}
                          {r.kind === 'improvement' ? 'Capitalised' : 'Repair'}
                        </Badge>
                        <span className="flex-1 min-w-0">
                          <span className="font-medium block truncate">{r.description}</span>
                          <span className="text-muted-foreground">
                            {[r.date, r.vendor, r.extends_life_years ? `+${r.extends_life_years}yr life` : '',
                              r.expense_id ? 'expensed' : '', r.merged_from_name ? `from ${r.merged_from_name}` : '']
                              .filter(Boolean).join(' · ')}
                          </span>
                        </span>
                        <span className="shrink-0 font-medium">{money(r.amount, r.currency || cur)}</span>
                        <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-destructive shrink-0"
                          onClick={() => removeSpend(a.id, r.id)} data-testid={`asset-entry-remove-${r.id}`}>
                          <Trash2 size={11} />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Add asset */}
      <Dialog open={showAsset} onOpenChange={setShowAsset}>
        <DialogContent className="max-w-md max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Add a fixed asset</DialogTitle>
            <DialogDescription>Something you own and will use for more than a year</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-1">
            <div className="space-y-1.5"><Label>What is it? *</Label>
              <Input value={assetForm.name} onChange={e => setAssetForm({ ...assetForm, name: e.target.value })}
                placeholder="e.g. Toyota Hiace UBH 123X" data-testid="asset-name-input" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Category</Label>
                <Select value={assetForm.category} onValueChange={v => setAssetForm({ ...assetForm, category: v })}>
                  <SelectTrigger data-testid="asset-category-select"><SelectValue /></SelectTrigger>
                  <SelectContent>{CATEGORIES.map(c => <SelectItem key={c} value={c} className="capitalize">{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label>Purchase cost ({assetForm.currency || activeCurrency}) *</Label>
                <Input type="number" min="0" step="0.01" value={assetForm.value}
                  onChange={e => setAssetForm({ ...assetForm, value: e.target.value })} data-testid="asset-value-input" />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5"><Label>Currency</Label>
                <Select value={assetForm.currency || activeCurrency} onValueChange={v => setAssetForm({ ...assetForm, currency: v })}>
                  <SelectTrigger data-testid="asset-currency-select"><SelectValue /></SelectTrigger>
                  <SelectContent>{CURRENCIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label>Purchase date</Label>
                <Input type="date" value={assetForm.purchase_date}
                  onChange={e => setAssetForm({ ...assetForm, purchase_date: e.target.value })} data-testid="asset-date-input" />
              </div>
              <div className="space-y-1.5"><Label>Life (years)</Label>
                <Input type="number" min="1" value={assetForm.depreciation_years}
                  onChange={e => setAssetForm({ ...assetForm, depreciation_years: Number(e.target.value) })} data-testid="asset-life-input" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Campus *</Label>
                <Select value={assetForm.location_id || activeCampusId} onValueChange={v => setAssetForm({ ...assetForm, location_id: v })}>
                  <SelectTrigger data-testid="asset-campus-select"><SelectValue placeholder="Campus" /></SelectTrigger>
                  <SelectContent>{locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label>Serial / plate number</Label>
                <Input value={assetForm.serial_number} onChange={e => setAssetForm({ ...assetForm, serial_number: e.target.value })} />
              </div>
            </div>
            <div className="space-y-1.5"><Label>Bought from</Label>
              <Input value={assetForm.vendor} onChange={e => setAssetForm({ ...assetForm, vendor: e.target.value })} data-testid="asset-vendor-input" />
            </div>
            <div className="space-y-1.5"><Label>Notes</Label>
              <Textarea rows={2} value={assetForm.notes} onChange={e => setAssetForm({ ...assetForm, notes: e.target.value })} />
            </div>
            <ExpenseOption form={assetForm} setForm={setAssetForm} accounts={accounts} expenseAccounts={expenseAccounts}
              hint="Books the purchase against a cash or bank account, exactly like a normal expense entry" />
            <div className="flex gap-3 pt-1">
              <Button variant="outline" className="flex-1" onClick={() => setShowAsset(false)}>Cancel</Button>
              <Button className="flex-1" onClick={createAsset} disabled={saving} data-testid="save-asset-btn">
                {saving ? 'Saving…' : 'Add asset'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit asset */}
      <Dialog open={!!editAsset} onOpenChange={o => { if (!o) setEditAsset(null); }}>
        <DialogContent className="max-w-md max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit {editAsset?.name}</DialogTitle>
            <DialogDescription>Details only — spend history and valuations are untouched</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-1">
            <div className="space-y-1.5"><Label>Name *</Label>
              <Input value={editForm.name || ''} onChange={e => setEditForm({ ...editForm, name: e.target.value })} data-testid="asset-edit-name" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Category</Label>
                <Select value={editForm.category || 'equipment'} onValueChange={v => setEditForm({ ...editForm, category: v })}>
                  <SelectTrigger data-testid="asset-edit-category"><SelectValue /></SelectTrigger>
                  <SelectContent>{CATEGORIES.map(c => <SelectItem key={c} value={c} className="capitalize">{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label>Purchase cost</Label>
                <Input type="number" min="0" step="0.01" value={editForm.value ?? ''}
                  onChange={e => setEditForm({ ...editForm, value: e.target.value })} data-testid="asset-edit-value" />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5"><Label>Currency</Label>
                <Select value={editForm.currency || activeCurrency} onValueChange={v => setEditForm({ ...editForm, currency: v })}>
                  <SelectTrigger data-testid="asset-edit-currency"><SelectValue /></SelectTrigger>
                  <SelectContent>{CURRENCIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label>Purchase date</Label>
                <Input type="date" value={editForm.purchase_date || ''} onChange={e => setEditForm({ ...editForm, purchase_date: e.target.value })} data-testid="asset-edit-date" />
              </div>
              <div className="space-y-1.5"><Label>Life (years)</Label>
                <Input type="number" min="1" value={editForm.depreciation_years ?? 5}
                  onChange={e => setEditForm({ ...editForm, depreciation_years: Number(e.target.value) })} data-testid="asset-edit-life" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Serial / plate number</Label>
                <Input value={editForm.serial_number || ''} onChange={e => setEditForm({ ...editForm, serial_number: e.target.value })} data-testid="asset-edit-serial" />
              </div>
              <div className="space-y-1.5"><Label>Condition</Label>
                <Select value={editForm.condition || 'good'} onValueChange={v => setEditForm({ ...editForm, condition: v })}>
                  <SelectTrigger data-testid="asset-edit-condition"><SelectValue /></SelectTrigger>
                  <SelectContent>{CONDITIONS.map(c => <SelectItem key={c} value={c} className="capitalize">{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5"><Label>Campus</Label>
              <Select value={editForm.location_id || activeCampusId} onValueChange={v => setEditForm({ ...editForm, location_id: v })}>
                <SelectTrigger data-testid="asset-edit-campus"><SelectValue placeholder="Campus" /></SelectTrigger>
                <SelectContent>{locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label>Notes</Label>
              <Textarea rows={2} value={editForm.notes || ''} onChange={e => setEditForm({ ...editForm, notes: e.target.value })} />
            </div>
            <div className="flex gap-3 pt-1">
              <Button variant="outline" className="flex-1" onClick={() => setEditAsset(null)}>Cancel</Button>
              <Button className="flex-1" onClick={saveEdit} disabled={saving || !editForm.name?.trim()} data-testid="asset-edit-save">
                {saving ? 'Saving…' : 'Save changes'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Log spend */}
      <Dialog open={!!spendFor} onOpenChange={o => { if (!o) setSpendFor(null); }}>
        <DialogContent className="max-w-md max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Money spent on {spendFor?.name}</DialogTitle>
            <DialogDescription>Improvements are added to the asset&apos;s cost; repairs are an expense</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-1">
            <div className="grid gap-2" data-testid="asset-spend-kind">
              {[
                { v: 'improvement', title: 'Improvement — capitalise it', hint: 'Made it last longer or do more: new roof, deeper borehole, replacement engine, extension' },
                { v: 'repair', title: 'Repair & maintenance — expense it', hint: 'Kept it working as it was: servicing, paint, tyres, spare parts' },
              ].map(opt => (
                <label key={opt.v}
                  className={`flex items-start gap-2 rounded-lg border p-2.5 text-xs cursor-pointer transition-colors ${spendForm.kind === opt.v ? 'border-primary bg-primary/5' : 'hover:bg-accent/40'}`}
                  data-testid={`asset-spend-${opt.v}`}>
                  <input type="radio" className="mt-0.5 accent-primary" checked={spendForm.kind === opt.v}
                    onChange={() => setSpendForm({ ...spendForm, kind: opt.v, post_expense: opt.v === 'repair' })} />
                  <span>
                    <span className="font-medium block">{opt.title}</span>
                    <span className="text-muted-foreground">{opt.hint}</span>
                  </span>
                </label>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Amount ({spendFor?.currency || activeCurrency}) *</Label>
                <Input type="number" min="0" step="0.01" value={spendForm.amount}
                  onChange={e => setSpendForm({ ...spendForm, amount: e.target.value })} data-testid="asset-spend-amount" />
              </div>
              <div className="space-y-1.5"><Label>Date</Label>
                <Input type="date" value={spendForm.date} onChange={e => setSpendForm({ ...spendForm, date: e.target.value })} data-testid="asset-spend-date" />
              </div>
            </div>
            <div className="space-y-1.5"><Label>What was done? *</Label>
              <Input value={spendForm.description} onChange={e => setSpendForm({ ...spendForm, description: e.target.value })}
                placeholder="e.g. Replaced engine" data-testid="asset-spend-description" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Paid to</Label>
                <Input value={spendForm.vendor} onChange={e => setSpendForm({ ...spendForm, vendor: e.target.value })} data-testid="asset-spend-vendor" />
              </div>
              {spendForm.kind === 'improvement' ? (
                <div className="space-y-1.5"><Label>Extra years of life</Label>
                  <Input type="number" min="0" step="0.5" value={spendForm.extends_life_years}
                    onChange={e => setSpendForm({ ...spendForm, extends_life_years: e.target.value })}
                    placeholder="optional" data-testid="asset-spend-extra-life" />
                </div>
              ) : (
                <div className="space-y-1.5"><Label>Receipt / reference</Label>
                  <Input value={spendForm.reference} onChange={e => setSpendForm({ ...spendForm, reference: e.target.value })} data-testid="asset-spend-reference" />
                </div>
              )}
            </div>
            <ExpenseOption form={spendForm} setForm={setSpendForm} accounts={accounts} expenseAccounts={expenseAccounts}
              hint="Draws the money out of a cash or bank account through the normal expense entry" />
            <div className="flex gap-3 pt-1">
              <Button variant="outline" className="flex-1" onClick={() => setSpendFor(null)}>Cancel</Button>
              <Button className="flex-1" onClick={logSpend}
                disabled={saving || !spendForm.amount || !spendForm.description.trim()} data-testid="save-asset-spend-btn">
                {saving ? 'Saving…' : spendForm.kind === 'improvement' ? 'Add to asset cost' : 'Log as expense'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Merge */}
      <Dialog open={mergeOpen} onOpenChange={setMergeOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Merge {selected.length} asset records</DialogTitle>
            <DialogDescription>Pick the record to keep — the others fold into it and disappear</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-1">
            <div className="space-y-1.5" data-testid="merge-keep-picker">
              <Label className="text-xs">Keep this one</Label>
              {selected.map(id => {
                const a = assets.find(x => x.id === id);
                if (!a) return null;
                return (
                  <label key={id} className={`flex items-start gap-2 rounded-lg border p-2.5 text-xs cursor-pointer ${mergeKeep === id ? 'border-primary bg-primary/5' : 'hover:bg-accent/40'}`}
                    data-testid={`merge-keep-${id}`}>
                    <input type="radio" className="mt-0.5 accent-primary" checked={mergeKeep === id} onChange={() => setMergeKeep(id)} />
                    <span>
                      <span className="font-medium block">{a.name}</span>
                      <span className="text-muted-foreground">
                        {money(a.value, a.currency || activeCurrency)} · {(a.spend || []).length} spend entries
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
            <label className="flex items-start justify-between gap-3 rounded-lg border p-3 cursor-pointer">
              <span className="text-xs">
                <span className="block font-medium text-sm">Add the purchase costs together</span>
                <span className="text-muted-foreground">Leave on if each record was a real separate purchase; turn off if they are duplicates of the same one</span>
              </span>
              <Switch checked={combineValues} onCheckedChange={setCombineValues} data-testid="merge-combine-values" />
            </label>
            <div className="flex gap-3 pt-1">
              <Button variant="outline" className="flex-1" onClick={() => setMergeOpen(false)}>Cancel</Button>
              <Button className="flex-1" onClick={doMerge} disabled={saving || !mergeKeep} data-testid="merge-confirm-btn">
                {saving ? 'Merging…' : 'Merge'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete */}
      <Dialog open={!!confirmDelete} onOpenChange={o => { if (!o) setConfirmDelete(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete {confirmDelete?.name}?</DialogTitle>
            <DialogDescription>
              Its spend history goes with it. Any expenses already recorded in Finance stay where they are.
            </DialogDescription>
          </DialogHeader>
          <div className="flex gap-3 pt-1">
            <Button variant="outline" className="flex-1" onClick={() => setConfirmDelete(null)}>Cancel</Button>
            <Button variant="destructive" className="flex-1" onClick={removeAsset} data-testid="asset-delete-confirm">Delete</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AssetsRegister;
