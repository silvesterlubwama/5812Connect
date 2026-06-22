/**
 * ShipmentsAdminPage — admin-only management of container shipments.
 *
 * Lifecycle:
 *   1. Create a shipment (name, dest country, target date).
 *   2. Add items (per-unit weight + dimensions → drives AI packing scenarios).
 *   3. Add pallets, assign items to them.
 *   4. Click "Generate AI packing scenario" → Gemini-3-flash outputs a step
 *      plan + weight/volume summary.
 *   5. Share the public token URL with donors — they mark items as donated
 *      without needing an account.
 */
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Plus, Trash2, Copy, RefreshCw, Container, Sparkles, ExternalLink, ArrowLeft, Layers } from 'lucide-react';
import api from '../services/api';
import { toast } from 'sonner';
import EmptyState from '../components/EmptyState';

const PRIORITY_BADGE = {
  urgent: 'bg-rose-100 text-rose-700',
  high: 'bg-amber-100 text-amber-700',
  normal: 'bg-slate-100 text-slate-600',
  low: 'bg-slate-50 text-slate-500',
};

export default function ShipmentsAdminPage() {
  const [shipments, setShipments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [selected, setSelected] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showAddItem, setShowAddItem] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [createForm, setCreateForm] = useState({ name: '', dest_country: 'Uganda', target_ship_date: '', description: '' });
  const [itemForm, setItemForm] = useState(emptyItem());

  const refreshList = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get('/shipments');
      setShipments(r.data || []);
    } catch (e) { console.warn(e?.message || e); }
    finally { setLoading(false); }
  }, []);

  const refreshDetail = useCallback(async () => {
    if (!selectedId) { setSelected(null); return; }
    try {
      const r = await api.get(`/shipments/${selectedId}`);
      setSelected(r.data);
    } catch (e) { toast.error('Failed to load shipment'); }
  }, [selectedId]);

  useEffect(() => { refreshList(); }, [refreshList]);
  useEffect(() => { refreshDetail(); }, [refreshDetail]);

  const createShipment = async () => {
    if (!createForm.name.trim()) { toast.error('Name required'); return; }
    try {
      const r = await api.post('/shipments', createForm);
      toast.success('Shipment created');
      setShowCreate(false);
      setCreateForm({ name: '', dest_country: 'Uganda', target_ship_date: '', description: '' });
      await refreshList();
      setSelectedId(r.data.id);
    } catch (e) { toast.error(e.response?.data?.detail || 'Create failed'); }
  };

  const addItem = async () => {
    if (!itemForm.name.trim()) { toast.error('Item name required'); return; }
    try {
      await api.post(`/shipments/${selectedId}/items`, itemForm);
      setItemForm(emptyItem());
      setShowAddItem(false);
      await refreshDetail();
      toast.success('Item added');
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const deleteItem = async (itemId) => {
    if (!window.confirm('Remove this item?')) return;
    try {
      await api.delete(`/shipments/${selectedId}/items/${itemId}`);
      await refreshDetail();
    } catch (e) { toast.error('Failed to delete'); }
  };

  const updateItem = async (itemId, patch) => {
    try {
      await api.put(`/shipments/${selectedId}/items/${itemId}`, patch);
      await refreshDetail();
    } catch (e) { toast.error(e.response?.data?.detail || 'Update failed'); }
  };

  const addPallet = async () => {
    const label = window.prompt('Pallet label (e.g. "Pallet A — Kitchen")');
    if (!label) return;
    try {
      await api.post(`/shipments/${selectedId}/pallets`, { label });
      await refreshDetail();
    } catch { toast.error('Failed to add pallet'); }
  };

  const deletePallet = async (pid) => {
    if (!window.confirm('Delete this pallet? Items will be unassigned.')) return;
    try {
      await api.delete(`/shipments/${selectedId}/pallets/${pid}`);
      await refreshDetail();
    } catch { toast.error('Failed'); }
  };

  const runAiPacking = async () => {
    setAiBusy(true);
    try {
      const r = await api.post(`/shipments/${selectedId}/ai-packing`, {});
      toast.success(`AI scenario ready (${r.data.total_weight_kg} kg total)`);
      await refreshDetail();
    } catch (e) { toast.error(e.response?.data?.detail || 'AI packing failed'); }
    finally { setAiBusy(false); }
  };

  const copyShareLink = () => {
    if (!selected?.token) return;
    const url = `${window.location.origin}/donate/shipment/${selected.token}`;
    navigator.clipboard.writeText(url);
    toast.success('Public donor link copied to clipboard');
  };

  const rotateToken = async () => {
    if (!window.confirm('Invalidate the current public link and issue a new one? Anyone using the old link will get a 404.')) return;
    try {
      await api.post(`/shipments/${selectedId}/rotate-token`, {});
      toast.success('New token issued — old link is now invalid');
      await refreshDetail();
    } catch { toast.error('Failed to rotate token'); }
  };

  const totals = useMemo(() => {
    if (!selected) return null;
    const items = selected.items || [];
    const weight = items.reduce((s, i) => s + (Number(i.weight_kg) || 0) * (Number(i.qty_acquired) || 0), 0);
    const value = items.reduce((s, i) => s + (Number(i.value_usd) || 0) * (Number(i.qty_acquired) || 0), 0);
    return {
      weight: weight.toFixed(1),
      value: value.toFixed(2),
      cap: selected.max_payload_kg || 26000,
      pct: Math.min(100, (weight / (selected.max_payload_kg || 26000)) * 100),
      needed: items.filter(i => (i.qty_needed || 0) - (i.qty_acquired || 0) > 0).length,
      acquired: items.filter(i => (i.qty_needed || 0) - (i.qty_acquired || 0) <= 0).length,
    };
  }, [selected]);

  // ─── LIST view ────────────────────────────────────────────────
  if (!selectedId) {
    return (
      <div className="p-6 space-y-4 max-w-6xl">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
              <Container className="text-primary" size={20} />
            </div>
            <div>
              <h1 className="text-2xl font-semibold font-heading">Container Shipments</h1>
              <p className="text-sm text-muted-foreground mt-0.5">Manage 40' container collections + public donor links + AI packing scenarios.</p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" onClick={refreshList} disabled={loading}><RefreshCw size={12} className={loading ? 'animate-spin' : ''} /></Button>
            <Button size="sm" onClick={() => setShowCreate(true)} data-testid="ship-new-btn"><Plus size={13} className="mr-1" /> New shipment</Button>
          </div>
        </div>

        {shipments.length === 0 ? (
          <EmptyState
            icon={Container}
            title="No shipments yet"
            description="Create your first container shipment, then share the public donor link with supporters."
            action={{ label: 'New shipment', onClick: () => setShowCreate(true), testid: 'ship-empty-new' }}
            testid="ship-empty"
          />
        ) : (
          <div className="space-y-2">
            {shipments.map(s => {
              const pct = Math.min(100, ((s.total_weight_kg || 0) / (s.max_payload_kg || 26000)) * 100);
              return (
                <Card key={s.id} className="rounded-xl cursor-pointer hover:border-primary/40" onClick={() => setSelectedId(s.id)} data-testid={`ship-row-${s.id}`}>
                  <CardContent className="p-3">
                    <div className="flex items-start justify-between gap-3 flex-wrap">
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-sm">{s.name}</p>
                        <p className="text-[11px] text-muted-foreground">
                          → {s.dest_country}{s.target_ship_date ? ` · ship ${s.target_ship_date}` : ''} · {s.item_count} items · {s.total_acquired}/{s.total_needed} units acquired
                        </p>
                      </div>
                      <Badge variant="outline" className="text-[10px] capitalize">{s.status}</Badge>
                    </div>
                    <div className="h-1.5 rounded bg-muted mt-2 overflow-hidden">
                      <div className={`h-full ${pct > 100 ? 'bg-rose-500' : pct > 80 ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{ width: `${pct}%` }} />
                    </div>
                    <p className="text-[10px] text-muted-foreground mt-1">{(s.total_weight_kg || 0).toLocaleString()} kg of {(s.max_payload_kg || 26000).toLocaleString()} kg cap ({pct.toFixed(0)}%)</p>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}

        <Dialog open={showCreate} onOpenChange={setShowCreate}>
          <DialogContent className="max-w-md" data-testid="ship-create-dialog">
            <DialogHeader>
              <DialogTitle>New container shipment</DialogTitle>
              <DialogDescription className="text-xs">A long-running collection effort. You'll get a public donor link to share.</DialogDescription>
            </DialogHeader>
            <div className="space-y-3 mt-2">
              <div className="space-y-1"><Label className="text-xs">Name *</Label>
                <Input value={createForm.name} onChange={e => setCreateForm({ ...createForm, name: e.target.value })} placeholder="e.g. 58:12 Uganda Container — Spring 2027" data-testid="ship-create-name" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">Destination</Label>
                  <Input value={createForm.dest_country} onChange={e => setCreateForm({ ...createForm, dest_country: e.target.value })} />
                </div>
                <div className="space-y-1"><Label className="text-xs">Target ship date</Label>
                  <Input type="date" value={createForm.target_ship_date} onChange={e => setCreateForm({ ...createForm, target_ship_date: e.target.value })} />
                </div>
              </div>
              <div className="space-y-1"><Label className="text-xs">Description (optional)</Label>
                <Textarea rows={2} value={createForm.description} onChange={e => setCreateForm({ ...createForm, description: e.target.value })} placeholder="What's this shipment for? Who can sponsor?" />
              </div>
              <div className="flex gap-2 pt-2">
                <Button variant="ghost" className="flex-1" onClick={() => setShowCreate(false)}>Cancel</Button>
                <Button className="flex-1" onClick={createShipment} data-testid="ship-create-submit">Create</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  // ─── DETAIL view ──────────────────────────────────────────────
  if (!selected) {
    return <div className="p-6"><p className="text-sm text-muted-foreground">Loading…</p></div>;
  }
  const palletsById = Object.fromEntries((selected.pallets || []).map(p => [p.id, p]));

  return (
    <div className="p-6 space-y-4 max-w-6xl" data-testid="ship-detail-page">
      <Button size="sm" variant="ghost" onClick={() => setSelectedId(null)} data-testid="ship-back-btn">
        <ArrowLeft size={13} className="mr-1" /> All shipments
      </Button>

      {/* Header card with share link */}
      <Card className="rounded-xl">
        <CardContent className="p-4 space-y-3">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="flex-1 min-w-0">
              <Input value={selected.name} onChange={e => setSelected({ ...selected, name: e.target.value })}
                onBlur={() => api.put(`/shipments/${selectedId}`, { name: selected.name }).catch(() => {})}
                className="font-semibold text-lg border-0 px-0 -ml-0.5" data-testid="ship-name" />
              <p className="text-xs text-muted-foreground">→ {selected.dest_country}{selected.target_ship_date ? ` · ship ${selected.target_ship_date}` : ''}</p>
            </div>
            <div className="flex gap-1.5 flex-wrap">
              <Select value={selected.status} onValueChange={async v => {
                await api.put(`/shipments/${selectedId}`, { status: v });
                setSelected({ ...selected, status: v });
                toast.success('Status updated');
              }}>
                <SelectTrigger className="h-8 w-32 text-xs" data-testid="ship-status"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="planning">Planning</SelectItem>
                  <SelectItem value="collecting">Collecting</SelectItem>
                  <SelectItem value="packed">Packed</SelectItem>
                  <SelectItem value="shipped">Shipped</SelectItem>
                  <SelectItem value="delivered">Delivered</SelectItem>
                  <SelectItem value="cancelled">Cancelled</SelectItem>
                </SelectContent>
              </Select>
              <Button size="sm" variant="outline" onClick={copyShareLink} data-testid="ship-copy-link">
                <Copy size={11} className="mr-1" /> Copy donor link
              </Button>
              <Button size="sm" variant="ghost" onClick={rotateToken} title="Invalidate current link + issue a new one">
                <RefreshCw size={11} />
              </Button>
            </div>
          </div>

          {/* Totals + progress bar */}
          {totals && (
            <div className="space-y-1.5" data-testid="ship-totals">
              <div className="flex items-center justify-between text-xs">
                <span>{totals.weight} kg of {totals.cap.toLocaleString()} kg cap</span>
                <span className="text-muted-foreground">{totals.acquired} of {totals.acquired + totals.needed} items fully covered · est. value ${totals.value}</span>
              </div>
              <div className="h-2 rounded bg-muted overflow-hidden">
                <div className={`h-full ${totals.pct > 100 ? 'bg-rose-500' : totals.pct > 80 ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{ width: `${totals.pct}%` }} />
              </div>
              {totals.pct > 100 && <p className="text-[11px] text-rose-700">⚠ Over the 40' container payload cap by {(totals.weight - totals.cap).toFixed(0)} kg.</p>}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pallets row */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-semibold flex items-center gap-1"><Layers size={11} /> Pallets ({(selected.pallets || []).length})</p>
          <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={addPallet} data-testid="ship-add-pallet"><Plus size={10} className="mr-1" /> Pallet</Button>
        </div>
        <div className="flex gap-2 flex-wrap" data-testid="ship-pallets">
          {(selected.pallets || []).length === 0 ? (
            <p className="text-[11px] text-muted-foreground italic">No pallets yet — items will be loose until grouped.</p>
          ) : (selected.pallets || []).map(p => {
            const palletItems = (selected.items || []).filter(i => i.pallet_id === p.id);
            const w = palletItems.reduce((s, i) => s + (Number(i.weight_kg) || 0) * (Number(i.qty_acquired) || 0), 0);
            return (
              <div key={p.id} className="px-3 py-1.5 rounded border text-xs flex items-center gap-2" data-testid={`ship-pallet-${p.id}`}>
                <span className="font-medium">{p.label}</span>
                <span className="text-muted-foreground">· {palletItems.length} items · {w.toFixed(0)} kg</span>
                <button onClick={() => deletePallet(p.id)} className="text-rose-600 hover:text-rose-800" title="Delete"><Trash2 size={10} /></button>
              </div>
            );
          })}
        </div>
      </div>

      {/* Items list */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-semibold">Items ({(selected.items || []).length})</p>
          <Button size="sm" onClick={() => setShowAddItem(true)} data-testid="ship-add-item"><Plus size={11} className="mr-1" /> Item</Button>
        </div>
        {(selected.items || []).length === 0 ? (
          <EmptyState compact icon={Container} title="No items yet" description="Add items donors should look for. Each item's weight + dimensions feed the AI packing scenario."
            action={{ label: 'Add first item', onClick: () => setShowAddItem(true), testid: 'ship-empty-item' }}
            testid="ship-items-empty" />
        ) : (
          <div className="space-y-1.5" data-testid="ship-items">
            {(selected.items || []).map(it => {
              const remaining = Math.max(0, (it.qty_needed || 0) - (it.qty_acquired || 0));
              const covered = remaining === 0;
              return (
                <Card key={it.id} className={`rounded-lg ${covered ? 'bg-emerald-50/50' : ''}`} data-testid={`ship-item-${it.id}`}>
                  <CardContent className="p-2.5 flex items-center gap-3 flex-wrap">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-medium truncate">{it.name}</p>
                        {it.category && <Badge variant="outline" className="text-[10px]">{it.category}</Badge>}
                        <Badge className={`text-[10px] ${PRIORITY_BADGE[it.priority] || ''}`}>{it.priority}</Badge>
                        {covered && <Badge className="bg-emerald-100 text-emerald-700 text-[10px]">✓ covered</Badge>}
                      </div>
                      <p className="text-[10px] text-muted-foreground">
                        {it.qty_acquired || 0} of {it.qty_needed || 0}
                        {it.weight_kg ? ` · ${it.weight_kg} kg/unit` : ''}
                        {it.value_usd ? ` · $${it.value_usd}/unit` : ''}
                        {it.pallet_id ? ` · ${palletsById[it.pallet_id]?.label || it.pallet_id}` : ''}
                      </p>
                    </div>
                    {(selected.pallets || []).length > 0 && (
                      <Select value={it.pallet_id || 'none'} onValueChange={v => updateItem(it.id, { pallet_id: v === 'none' ? null : v })}>
                        <SelectTrigger className="h-7 w-32 text-[11px]" data-testid={`ship-item-pallet-${it.id}`}><SelectValue placeholder="Pallet" /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">— Unassigned —</SelectItem>
                          {(selected.pallets || []).map(p => <SelectItem key={p.id} value={p.id}>{p.label}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    )}
                    <Input type="number" className="h-7 w-20 text-[11px]" value={it.qty_acquired || 0}
                      onChange={e => updateItem(it.id, { qty_acquired: parseInt(e.target.value) || 0 })} title="Manual adjustment of acquired qty" />
                    <Button size="sm" variant="ghost" className="text-destructive h-7 w-7 p-0" onClick={() => deleteItem(it.id)} data-testid={`ship-item-delete-${it.id}`}>
                      <Trash2 size={11} />
                    </Button>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* AI Packing scenario */}
      <Card className="rounded-xl border-primary/20">
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold flex items-center gap-1.5"><Sparkles size={13} className="text-primary" /> AI Packing Scenario</p>
            <Button size="sm" onClick={runAiPacking} disabled={aiBusy || (selected.items || []).length === 0} data-testid="ship-ai-btn">
              {aiBusy ? 'Thinking…' : selected.ai_packing_text ? 'Regenerate' : 'Generate'}
            </Button>
          </div>
          {selected.ai_packing_text ? (
            <div className="prose prose-sm max-w-none text-xs whitespace-pre-wrap font-mono bg-muted/30 p-3 rounded">{selected.ai_packing_text}</div>
          ) : (
            <p className="text-xs text-muted-foreground italic">Add items + (optionally) pallets, then generate a step-by-step packing plan.</p>
          )}
          {selected.ai_packing_generated_at && <p className="text-[10px] text-muted-foreground">Last generated {new Date(selected.ai_packing_generated_at).toLocaleString()}</p>}
        </CardContent>
      </Card>

      {/* Public link preview */}
      {selected.token && (
        <Card className="rounded-xl bg-muted/30">
          <CardContent className="p-3 flex items-center gap-2 flex-wrap text-xs">
            <ExternalLink size={12} className="text-muted-foreground shrink-0" />
            <span className="text-muted-foreground">Public donor link:</span>
            <code className="font-mono text-[11px] truncate flex-1 min-w-0">{window.location.origin}/donate/shipment/{selected.token}</code>
            <Button size="sm" variant="ghost" className="h-6 text-[11px]" onClick={copyShareLink}>Copy</Button>
            <a href={`/donate/shipment/${selected.token}`} target="_blank" rel="noreferrer">
              <Button size="sm" variant="outline" className="h-6 text-[11px]">Preview</Button>
            </a>
          </CardContent>
        </Card>
      )}

      {/* Danger zone */}
      <Card className="rounded-xl border-rose-200">
        <CardContent className="p-3 flex items-center justify-between">
          <p className="text-xs text-muted-foreground">Permanently delete this shipment + all items + donor records.</p>
          <Button size="sm" variant="destructive" onClick={async () => {
            if (!window.confirm(`Delete "${selected.name}" permanently? This cannot be undone.`)) return;
            try {
              await api.delete(`/shipments/${selectedId}`);
              toast.success('Shipment deleted');
              setSelectedId(null);
              await refreshList();
            } catch { toast.error('Delete failed'); }
          }} data-testid="ship-delete-btn">Delete shipment</Button>
        </CardContent>
      </Card>

      {/* Add item dialog */}
      <Dialog open={showAddItem} onOpenChange={setShowAddItem}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto" data-testid="ship-add-item-dialog">
          <DialogHeader><DialogTitle>Add item to shipment</DialogTitle></DialogHeader>
          <div className="space-y-2 mt-2">
            <div className="space-y-1"><Label className="text-xs">Name *</Label>
              <Input value={itemForm.name} onChange={e => setItemForm({ ...itemForm, name: e.target.value })} placeholder="School backpacks" data-testid="ship-item-name" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1"><Label className="text-xs">Category</Label>
                <Input value={itemForm.category} onChange={e => setItemForm({ ...itemForm, category: e.target.value })} placeholder="School / Kitchen / Medical" />
              </div>
              <div className="space-y-1"><Label className="text-xs">Priority</Label>
                <Select value={itemForm.priority} onValueChange={v => setItemForm({ ...itemForm, priority: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {['urgent', 'high', 'normal', 'low'].map(p => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1"><Label className="text-xs">Quantity needed *</Label>
                <Input type="number" value={itemForm.qty_needed} onChange={e => setItemForm({ ...itemForm, qty_needed: parseInt(e.target.value) || 1 })} />
              </div>
              <div className="space-y-1"><Label className="text-xs">Already acquired</Label>
                <Input type="number" value={itemForm.qty_acquired} onChange={e => setItemForm({ ...itemForm, qty_acquired: parseInt(e.target.value) || 0 })} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1"><Label className="text-xs">Weight per unit (kg)</Label>
                <Input type="number" step="0.1" value={itemForm.weight_kg} onChange={e => setItemForm({ ...itemForm, weight_kg: parseFloat(e.target.value) || 0 })} placeholder="1.5" />
              </div>
              <div className="space-y-1"><Label className="text-xs">Value per unit (USD)</Label>
                <Input type="number" step="0.01" value={itemForm.value_usd} onChange={e => setItemForm({ ...itemForm, value_usd: parseFloat(e.target.value) || 0 })} placeholder="25" />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Dimensions per unit — L × W × H (cm)</Label>
              <div className="grid grid-cols-3 gap-2">
                <Input type="number" step="1" placeholder="L" value={itemForm.dims_cm.length} onChange={e => setItemForm({ ...itemForm, dims_cm: { ...itemForm.dims_cm, length: parseFloat(e.target.value) || 0 } })} />
                <Input type="number" step="1" placeholder="W" value={itemForm.dims_cm.width} onChange={e => setItemForm({ ...itemForm, dims_cm: { ...itemForm.dims_cm, width: parseFloat(e.target.value) || 0 } })} />
                <Input type="number" step="1" placeholder="H" value={itemForm.dims_cm.height} onChange={e => setItemForm({ ...itemForm, dims_cm: { ...itemForm.dims_cm, height: parseFloat(e.target.value) || 0 } })} />
              </div>
            </div>
            <div className="space-y-1"><Label className="text-xs">Notes</Label>
              <Textarea rows={2} value={itemForm.notes} onChange={e => setItemForm({ ...itemForm, notes: e.target.value })} placeholder="Brand, model, condition…" />
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="ghost" className="flex-1" onClick={() => setShowAddItem(false)}>Cancel</Button>
              <Button className="flex-1" onClick={addItem} data-testid="ship-item-submit">Add item</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function emptyItem() {
  return {
    name: '', category: '', qty_needed: 1, qty_acquired: 0,
    weight_kg: 0, value_usd: 0, priority: 'normal',
    dims_cm: { length: 0, width: 0, height: 0 },
    notes: '', photo_url: '',
  };
}
