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
import { Plus, Trash2, Copy, RefreshCw, Container, Sparkles, ExternalLink, ArrowLeft, Layers, Upload, Image as ImageIcon, Link2, FileSpreadsheet, Download, Pencil, Ruler, KeyRound, Boxes, Scissors } from 'lucide-react';
import api from '../services/api';
import { toast } from 'sonner';
import EmptyState from '../components/EmptyState';
import ContainerVisualizer from '../components/ContainerVisualizer';
import Papa from 'papaparse';

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
  const [showCsvImport, setShowCsvImport] = useState(false);
  const [csvRows, setCsvRows] = useState([]);
  const [csvBusy, setCsvBusy] = useState(false);
  const [linkBusyId, setLinkBusyId] = useState(null);
  const [linkUrlFor, setLinkUrlFor] = useState(null);   // {itemId, url}
  const [aiBusy, setAiBusy] = useState(false);
  const [createForm, setCreateForm] = useState({ name: '', dest_country: 'Uganda', target_ship_date: '', description: '' });
  const [itemForm, setItemForm] = useState(emptyItem());
  // Full-edit dialog for an existing item (dimensions, pallet, position, etc.)
  const [editingItem, setEditingItem] = useState(null);   // the item object being edited
  // Pallet manager dialog (size, label, position)
  const [editingPallet, setEditingPallet] = useState(null); // null|{} (new)| existing pallet
  // Container-dims editor
  const [showContainerEdit, setShowContainerEdit] = useState(false);
  const [containerForm, setContainerForm] = useState({ length_cm: 1203, width_cm: 235, height_cm: 269, max_payload_kg: 26000 });
  // PIN management
  const [showPinDialog, setShowPinDialog] = useState(false);
  const [pinForm, setPinForm] = useState('');

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

  // ─── Per-item photo upload ────────────────────────────────────
  const uploadItemPhoto = async (itemId, file) => {
    if (!file) return;
    if (!file.type?.startsWith('image/')) { toast.error('Photo must be an image'); return; }
    if (file.size > 5 * 1024 * 1024) { toast.error('Photo must be under 5 MB'); return; }
    const fd = new FormData();
    fd.append('file', file);
    try {
      await api.post(`/shipments/${selectedId}/items/${itemId}/photo`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success('Photo uploaded');
      await refreshDetail();
    } catch (e) { toast.error(e.response?.data?.detail || 'Upload failed'); }
  };

  // ─── AI estimate weight/dims from product URL ─────────────────
  const estimateFromLink = async (itemId, url) => {
    if (!url || !url.startsWith('http')) { toast.error('Paste a product URL starting with http(s)'); return; }
    setLinkBusyId(itemId);
    try {
      const r = await api.post(`/shipments/${selectedId}/items/${itemId}/estimate-from-link`, { url });
      toast.success(`Estimated: ${r.data.weight_kg} kg, ${r.data.dims_cm.length}×${r.data.dims_cm.width}×${r.data.dims_cm.height} cm (${r.data.confidence})`);
      setLinkUrlFor(null);
      await refreshDetail();
    } catch (e) { toast.error(e.response?.data?.detail || 'AI estimate failed'); }
    finally { setLinkBusyId(null); }
  };

  // ─── CSV import (Papaparse client-side → bulk-import endpoint) ─
  const parseCsvFile = (file) => {
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      transformHeader: h => (h || '').trim().toLowerCase().replace(/\s+/g, '_'),
      complete: (res) => {
        const rows = (res.data || []).map(r => ({
          name: (r.name || r.item || '').toString().trim(),
          category: (r.category || '').toString().trim(),
          qty_needed: parseInt(r.qty_needed || r.quantity || r.qty || 1) || 1,
          qty_acquired: parseInt(r.qty_acquired || r.acquired || 0) || 0,
          weight_kg: parseFloat(r.weight_kg || r.weight || 0) || 0,
          value_usd: parseFloat(r.value_usd || r.value || r.price || 0) || 0,
          priority: ((r.priority || 'normal').toString().trim().toLowerCase()),
          dims_cm: {
            length: parseFloat(r.length_cm || r.length || 0) || 0,
            width: parseFloat(r.width_cm || r.width || 0) || 0,
            height: parseFloat(r.height_cm || r.height || 0) || 0,
          },
          notes: (r.notes || '').toString().trim(),
        })).filter(r => r.name);
        setCsvRows(rows);
        if (rows.length === 0) toast.error('No valid rows found — make sure your CSV has a "name" column');
      },
      error: (err) => toast.error(`CSV parse error: ${err.message}`),
    });
  };

  const submitCsvImport = async () => {
    if (csvRows.length === 0) return;
    setCsvBusy(true);
    try {
      const r = await api.post(`/shipments/${selectedId}/items/bulk-import`, { items: csvRows });
      toast.success(`Imported ${r.data.imported} item${r.data.imported === 1 ? '' : 's'}`);
      setCsvRows([]);
      setShowCsvImport(false);
      await refreshDetail();
    } catch (e) { toast.error(e.response?.data?.detail || 'Import failed'); }
    finally { setCsvBusy(false); }
  };

  const downloadCsvTemplate = () => {
    const csv = 'name,category,qty_needed,qty_acquired,weight_kg,length_cm,width_cm,height_cm,value_usd,priority,notes\nSchool backpack,School,50,0,1.2,45,30,15,25,high,"Sturdy material please"\nMosquito net,Medical,100,0,0.3,30,20,5,8,urgent,Family-size only\n';
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'shipment-items-template.csv';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const openNewPallet = () => setEditingPallet({
    label: '', notes: '', length_cm: 120, width_cm: 80, height_cm: 150, x_cm: 0, y_cm: 0, color: '',
  });

  const savePallet = async () => {
    if (!editingPallet) return;
    const payload = {
      label: editingPallet.label,
      notes: editingPallet.notes,
      length_cm: Number(editingPallet.length_cm) || 120,
      width_cm: Number(editingPallet.width_cm) || 80,
      height_cm: Number(editingPallet.height_cm) || 150,
      x_cm: Number(editingPallet.x_cm) || 0,
      y_cm: Number(editingPallet.y_cm) || 0,
      color: editingPallet.color || '',
    };
    try {
      if (editingPallet.id) {
        await api.put(`/shipments/${selectedId}/pallets/${editingPallet.id}`, payload);
        toast.success('Pallet updated');
      } else {
        await api.post(`/shipments/${selectedId}/pallets`, payload);
        toast.success('Pallet added');
      }
      setEditingPallet(null);
      await refreshDetail();
    } catch (e) { toast.error(e.response?.data?.detail || 'Save failed'); }
  };

  const deletePallet = async (pid) => {
    if (!window.confirm('Delete this pallet? Items will be unassigned.')) return;
    try {
      await api.delete(`/shipments/${selectedId}/pallets/${pid}`);
      await refreshDetail();
    } catch { toast.error('Failed'); }
  };

  // Container dims editor
  const openContainerEdit = () => {
    const c = selected?.container_dims_cm || {};
    setContainerForm({
      length_cm: c.length_cm || 1203,
      width_cm: c.width_cm || 235,
      height_cm: c.height_cm || 269,
      max_payload_kg: c.max_payload_kg || selected?.max_payload_kg || 26000,
    });
    setShowContainerEdit(true);
  };
  const saveContainer = async () => {
    try {
      await api.put(`/shipments/${selectedId}`, {
        container_dims_cm: {
          length_cm: Number(containerForm.length_cm),
          width_cm: Number(containerForm.width_cm),
          height_cm: Number(containerForm.height_cm),
          max_payload_kg: Number(containerForm.max_payload_kg),
        },
        max_payload_kg: Number(containerForm.max_payload_kg),
      });
      toast.success('Container dimensions saved');
      setShowContainerEdit(false);
      await refreshDetail();
    } catch (e) { toast.error(e.response?.data?.detail || 'Save failed'); }
  };

  // Edit-PIN management
  const savePin = async () => {
    try {
      const r = await api.post(`/shipments/${selectedId}/set-pin`, { pin: pinForm.trim() });
      toast.success(r.data.set ? 'PIN set — share it with trusted editors' : 'PIN cleared');
      setShowPinDialog(false);
      setPinForm('');
      await refreshDetail();
    } catch (e) { toast.error(e.response?.data?.detail || 'PIN update failed'); }
  };

  // Open full-edit dialog for an item
  const openItemEdit = (item) => setEditingItem({
    ...item,
    dims_cm: item.dims_cm || { length: 0, width: 0, height: 0 },
    x_cm: item.x_cm || 0, y_cm: item.y_cm || 0, z_cm: item.z_cm || 0,
  });
  const saveItemEdit = async () => {
    if (!editingItem) return;
    try {
      await api.put(`/shipments/${selectedId}/items/${editingItem.id}`, {
        name: editingItem.name,
        category: editingItem.category,
        priority: editingItem.priority,
        qty_needed: Number(editingItem.qty_needed) || 1,
        qty_acquired: Number(editingItem.qty_acquired) || 0,
        weight_kg: Number(editingItem.weight_kg) || 0,
        value_usd: Number(editingItem.value_usd) || 0,
        dims_cm: {
          length: Number(editingItem.dims_cm?.length) || 0,
          width: Number(editingItem.dims_cm?.width) || 0,
          height: Number(editingItem.dims_cm?.height) || 0,
        },
        pallet_id: editingItem.pallet_id || null,
        x_cm: Number(editingItem.x_cm) || 0,
        y_cm: Number(editingItem.y_cm) || 0,
        z_cm: Number(editingItem.z_cm) || 0,
        notes: editingItem.notes || '',
      });
      toast.success('Item updated');
      setEditingItem(null);
      await refreshDetail();
    } catch (e) { toast.error(e.response?.data?.detail || 'Save failed'); }
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
      overPledged: items.filter(i => (Number(i.qty_acquired) || 0) > (Number(i.qty_needed) || 0)).length,
    };
  }, [selected]);

  const pruneOverPledged = async () => {
    if (!selected) return;
    if (!window.confirm(`Trim ${totals?.overPledged || 0} over-pledged item(s) back to pledged qty? Surplus is logged for audit but qty_acquired will drop.`)) return;
    try {
      const r = await api.post(`/shipments/${selected.id}/prune-over-pledged`);
      const { trimmed, total_surplus } = r.data || {};
      toast.success(`Trimmed ${trimmed?.length || 0} item(s) — ${total_surplus || 0} surplus units logged`);
      await refreshDetail();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Prune failed');
    }
  };

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
              <p className="text-sm text-muted-foreground mt-0.5">Manage 40&apos; container collections + public donor links + AI packing scenarios.</p>
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
              <DialogDescription className="text-xs">A long-running collection effort. You&apos;ll get a public donor link to share.</DialogDescription>
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
              <Button size="sm" variant="outline" onClick={openContainerEdit} title="Edit container dimensions" data-testid="ship-edit-container">
                <Ruler size={11} className="mr-1" /> Container
              </Button>
              <Button size="sm" variant="outline" onClick={() => { setPinForm(''); setShowPinDialog(true); }} title="Set / change shipment edit PIN" data-testid="ship-edit-pin">
                <KeyRound size={11} className="mr-1" /> {selected?.access_pin_hash ? 'PIN set' : 'Set PIN'}
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
              {totals.pct > 100 && <p className="text-[11px] text-rose-700">⚠ Over the 40&apos; container payload cap by {(totals.weight - totals.cap).toFixed(0)} kg.</p>}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pallets row */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-semibold flex items-center gap-1"><Layers size={11} /> Pallets ({(selected.pallets || []).length})</p>
          <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={openNewPallet} data-testid="ship-add-pallet"><Plus size={10} className="mr-1" /> Pallet</Button>
        </div>
        <div className="flex gap-2 flex-wrap" data-testid="ship-pallets">
          {(selected.pallets || []).length === 0 ? (
            <p className="text-[11px] text-muted-foreground italic">No pallets yet — items will be loose until grouped.</p>
          ) : (selected.pallets || []).map(p => {
            const palletItems = (selected.items || []).filter(i => i.pallet_id === p.id);
            const w = palletItems.reduce((s, i) => s + (Number(i.weight_kg) || 0) * (Number(i.qty_acquired) || 0), 0);
            return (
              <div key={p.id} className="px-3 py-1.5 rounded border text-xs flex items-center gap-2" data-testid={`ship-pallet-${p.id}`} style={p.color ? { borderLeft: `4px solid ${p.color}` } : {}}>
                <span className="font-medium">{p.label}</span>
                <span className="text-muted-foreground">
                  · {palletItems.length} items · {w.toFixed(0)} kg
                  {(p.length_cm && p.width_cm) ? ` · ${p.length_cm}×${p.width_cm}×${p.height_cm || 0} cm` : ''}
                </span>
                <button onClick={() => setEditingPallet({ ...p })} className="text-primary hover:text-primary/80" title="Edit pallet" data-testid={`ship-pallet-edit-${p.id}`}><Pencil size={10} /></button>
                <button onClick={() => deletePallet(p.id)} className="text-rose-600 hover:text-rose-800" title="Delete" data-testid={`ship-pallet-del-${p.id}`}><Trash2 size={10} /></button>
              </div>
            );
          })}
        </div>
      </div>

      {/* Items list */}
      <div>
        <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
          <p className="text-xs font-semibold">Items ({(selected.items || []).length})</p>
          <div className="flex gap-1.5">
            {(totals?.overPledged || 0) > 0 && (
              <Button size="sm" variant="outline" className="text-amber-700 border-amber-300 hover:bg-amber-50" onClick={pruneOverPledged} data-testid="ship-prune-overpledged-btn" title="Trim over-pledged items back to their pledged quantity. Surplus is logged for redistribution.">
                <Scissors size={11} className="mr-1" /> Prune over-pledged ({totals.overPledged})
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => setShowCsvImport(true)} data-testid="ship-csv-import-btn">
              <FileSpreadsheet size={11} className="mr-1" /> Import CSV
            </Button>
            <Button size="sm" onClick={() => setShowAddItem(true)} data-testid="ship-add-item"><Plus size={11} className="mr-1" /> Item</Button>
          </div>
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
                    {/* Photo thumbnail + upload */}
                    <label className="relative w-12 h-12 rounded border bg-muted/40 flex items-center justify-center overflow-hidden cursor-pointer hover:border-primary shrink-0" title="Click to upload photo">
                      {it.photo_url ? (
                        <img src={it.photo_url} alt={it.name} className="w-full h-full object-cover" />
                      ) : (
                        <ImageIcon size={14} className="text-muted-foreground/60" />
                      )}
                      <input type="file" accept="image/*" className="hidden" onChange={e => uploadItemPhoto(it.id, e.target.files?.[0])} data-testid={`ship-item-photo-${it.id}`} />
                    </label>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-medium truncate">{it.name}</p>
                        {it.category && <Badge variant="outline" className="text-[10px]">{it.category}</Badge>}
                        <Badge className={`text-[10px] ${PRIORITY_BADGE[it.priority] || ''}`}>{it.priority}</Badge>
                        {covered && <Badge className="bg-emerald-100 text-emerald-700 text-[10px]">✓ covered</Badge>}
                        {it.ai_estimate && <Badge variant="outline" className="text-[10px]" title={it.ai_estimate.reasoning}>AI · {it.ai_estimate.confidence}</Badge>}
                      </div>
                      <p className="text-[10px] text-muted-foreground">
                        {it.qty_acquired || 0} of {it.qty_needed || 0}
                        {it.weight_kg ? ` · ${it.weight_kg} kg/unit` : ''}
                        {(it.dims_cm?.length || it.dims_cm?.width || it.dims_cm?.height) ? ` · ${it.dims_cm?.length || 0}×${it.dims_cm?.width || 0}×${it.dims_cm?.height || 0} cm` : ''}
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
                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0" title="Edit details (dimensions, pallet, position…)"
                      onClick={() => openItemEdit(it)} data-testid={`ship-item-edit-${it.id}`}>
                      <Pencil size={11} />
                    </Button>
                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0" title="AI estimate weight + size from product URL"
                      onClick={() => setLinkUrlFor({ itemId: it.id, url: it.source_url || '' })}
                      data-testid={`ship-item-link-${it.id}`}>
                      <Link2 size={11} />
                    </Button>
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

      {/* Container visualization — 2D / 3D */}
      <ContainerVisualizer items={selected.items || []} pallets={selected.pallets || []} container={selected.container_dims_cm} editable onPalletMove={async (pid, x, y) => {
        try {
          await api.put(`/shipments/${selectedId}/pallets/${pid}`, { x_cm: Math.round(x), y_cm: Math.round(y) });
          await refreshDetail();
        } catch (e) { toast.error(e.response?.data?.detail || 'Move failed'); }
      }} />

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

      {/* Edit item dialog (full form: dimensions, pallet, position, notes) */}
      <Dialog open={!!editingItem} onOpenChange={(o) => { if (!o) setEditingItem(null); }}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="ship-edit-item-dialog">
          <DialogHeader><DialogTitle>Edit item — {editingItem?.name}</DialogTitle></DialogHeader>
          {editingItem && (
            <div className="space-y-2 mt-2">
              <div className="space-y-1"><Label className="text-xs">Name</Label>
                <Input value={editingItem.name} onChange={e => setEditingItem({ ...editingItem, name: e.target.value })} data-testid="ship-edit-item-name" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">Category</Label>
                  <Input value={editingItem.category || ''} onChange={e => setEditingItem({ ...editingItem, category: e.target.value })} />
                </div>
                <div className="space-y-1"><Label className="text-xs">Priority</Label>
                  <Select value={editingItem.priority || 'normal'} onValueChange={v => setEditingItem({ ...editingItem, priority: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {['urgent', 'high', 'normal', 'low'].map(p => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">Qty needed</Label>
                  <Input type="number" value={editingItem.qty_needed || 1} onChange={e => setEditingItem({ ...editingItem, qty_needed: parseInt(e.target.value) || 1 })} />
                </div>
                <div className="space-y-1"><Label className="text-xs">Qty acquired</Label>
                  <Input type="number" value={editingItem.qty_acquired || 0} onChange={e => setEditingItem({ ...editingItem, qty_acquired: parseInt(e.target.value) || 0 })} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">Weight per unit (kg)</Label>
                  <Input type="number" step="0.01" value={editingItem.weight_kg || 0} onChange={e => setEditingItem({ ...editingItem, weight_kg: parseFloat(e.target.value) || 0 })} />
                </div>
                <div className="space-y-1"><Label className="text-xs">Value per unit (USD)</Label>
                  <Input type="number" step="0.01" value={editingItem.value_usd || 0} onChange={e => setEditingItem({ ...editingItem, value_usd: parseFloat(e.target.value) || 0 })} />
                </div>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Dimensions (cm) — L × W × H</Label>
                <div className="grid grid-cols-3 gap-2">
                  <Input type="number" placeholder="length" value={editingItem.dims_cm?.length || 0} onChange={e => setEditingItem({ ...editingItem, dims_cm: { ...editingItem.dims_cm, length: parseFloat(e.target.value) || 0 } })} data-testid="ship-edit-item-length" />
                  <Input type="number" placeholder="width" value={editingItem.dims_cm?.width || 0} onChange={e => setEditingItem({ ...editingItem, dims_cm: { ...editingItem.dims_cm, width: parseFloat(e.target.value) || 0 } })} data-testid="ship-edit-item-width" />
                  <Input type="number" placeholder="height" value={editingItem.dims_cm?.height || 0} onChange={e => setEditingItem({ ...editingItem, dims_cm: { ...editingItem.dims_cm, height: parseFloat(e.target.value) || 0 } })} data-testid="ship-edit-item-height" />
                </div>
              </div>
              {(selected.pallets || []).length > 0 && (
                <div className="space-y-1"><Label className="text-xs">Pallet placement</Label>
                  <Select value={editingItem.pallet_id || 'none'} onValueChange={v => setEditingItem({ ...editingItem, pallet_id: v === 'none' ? null : v })}>
                    <SelectTrigger data-testid="ship-edit-item-pallet"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">— Unassigned (loose) —</SelectItem>
                      {(selected.pallets || []).map(p => <SelectItem key={p.id} value={p.id}>{p.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              )}
              {editingItem.pallet_id && (
                <div className="space-y-1">
                  <Label className="text-xs">Position within pallet (cm) — X · Y · Z</Label>
                  <div className="grid grid-cols-3 gap-2">
                    <Input type="number" value={editingItem.x_cm || 0} onChange={e => setEditingItem({ ...editingItem, x_cm: parseFloat(e.target.value) || 0 })} />
                    <Input type="number" value={editingItem.y_cm || 0} onChange={e => setEditingItem({ ...editingItem, y_cm: parseFloat(e.target.value) || 0 })} />
                    <Input type="number" value={editingItem.z_cm || 0} onChange={e => setEditingItem({ ...editingItem, z_cm: parseFloat(e.target.value) || 0 })} />
                  </div>
                </div>
              )}
              <div className="space-y-1"><Label className="text-xs">Notes</Label>
                <Textarea rows={2} value={editingItem.notes || ''} onChange={e => setEditingItem({ ...editingItem, notes: e.target.value })} />
              </div>
              <div className="flex gap-2 pt-2">
                <Button variant="ghost" className="flex-1" onClick={() => setEditingItem(null)}>Cancel</Button>
                <Button className="flex-1" onClick={saveItemEdit} data-testid="ship-edit-item-save">Save changes</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Pallet manager dialog (add / edit with size + position) */}
      <Dialog open={!!editingPallet} onOpenChange={(o) => { if (!o) setEditingPallet(null); }}>
        <DialogContent className="max-w-md" data-testid="ship-pallet-dialog">
          <DialogHeader>
            <DialogTitle>{editingPallet?.id ? 'Edit pallet' : 'New pallet'}</DialogTitle>
            <DialogDescription className="text-xs">
              Set pallet footprint + position inside the container so the visualizer can lay it out to scale.
              <br />Standard EUR pallet: 120 × 80 cm.
            </DialogDescription>
          </DialogHeader>
          {editingPallet && (
            <div className="space-y-2 mt-2">
              <div className="space-y-1"><Label className="text-xs">Label *</Label>
                <Input value={editingPallet.label || ''} onChange={e => setEditingPallet({ ...editingPallet, label: e.target.value })} placeholder="Pallet A — Kitchen" data-testid="ship-pallet-label" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Footprint (cm) — L × W × stack height</Label>
                <div className="grid grid-cols-3 gap-2">
                  <Input type="number" value={editingPallet.length_cm} onChange={e => setEditingPallet({ ...editingPallet, length_cm: parseFloat(e.target.value) || 0 })} data-testid="ship-pallet-length" />
                  <Input type="number" value={editingPallet.width_cm} onChange={e => setEditingPallet({ ...editingPallet, width_cm: parseFloat(e.target.value) || 0 })} data-testid="ship-pallet-width" />
                  <Input type="number" value={editingPallet.height_cm} onChange={e => setEditingPallet({ ...editingPallet, height_cm: parseFloat(e.target.value) || 0 })} data-testid="ship-pallet-height" />
                </div>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Position in container (cm from back-left)</Label>
                <div className="grid grid-cols-2 gap-2">
                  <Input type="number" value={editingPallet.x_cm} onChange={e => setEditingPallet({ ...editingPallet, x_cm: parseFloat(e.target.value) || 0 })} placeholder="X (along length)" />
                  <Input type="number" value={editingPallet.y_cm} onChange={e => setEditingPallet({ ...editingPallet, y_cm: parseFloat(e.target.value) || 0 })} placeholder="Y (across width)" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">Color tag</Label>
                  <Input type="color" value={editingPallet.color || '#10b981'} onChange={e => setEditingPallet({ ...editingPallet, color: e.target.value })} className="h-9" />
                </div>
                <div className="space-y-1"><Label className="text-xs">Notes</Label>
                  <Input value={editingPallet.notes || ''} onChange={e => setEditingPallet({ ...editingPallet, notes: e.target.value })} placeholder="Kitchen supplies" />
                </div>
              </div>
              <div className="flex gap-2 pt-2">
                <Button variant="ghost" className="flex-1" onClick={() => setEditingPallet(null)}>Cancel</Button>
                <Button className="flex-1" onClick={savePallet} data-testid="ship-pallet-save">Save pallet</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Container dimensions editor */}
      <Dialog open={showContainerEdit} onOpenChange={setShowContainerEdit}>
        <DialogContent className="max-w-md" data-testid="ship-container-dialog">
          <DialogHeader>
            <DialogTitle>Container dimensions</DialogTitle>
            <DialogDescription className="text-xs">
              Defaults match a 40&apos; high-cube (1203 × 235 × 269 cm interior, 26,000 kg payload). Override for 20&apos;, refrigerated, or partial-load shipments.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 mt-2">
            <div className="grid grid-cols-3 gap-2">
              <div className="space-y-1"><Label className="text-xs">Length (cm)</Label>
                <Input type="number" value={containerForm.length_cm} onChange={e => setContainerForm({ ...containerForm, length_cm: parseFloat(e.target.value) || 0 })} data-testid="ship-container-length" />
              </div>
              <div className="space-y-1"><Label className="text-xs">Width (cm)</Label>
                <Input type="number" value={containerForm.width_cm} onChange={e => setContainerForm({ ...containerForm, width_cm: parseFloat(e.target.value) || 0 })} data-testid="ship-container-width" />
              </div>
              <div className="space-y-1"><Label className="text-xs">Height (cm)</Label>
                <Input type="number" value={containerForm.height_cm} onChange={e => setContainerForm({ ...containerForm, height_cm: parseFloat(e.target.value) || 0 })} data-testid="ship-container-height" />
              </div>
            </div>
            <div className="space-y-1"><Label className="text-xs">Max payload (kg)</Label>
              <Input type="number" value={containerForm.max_payload_kg} onChange={e => setContainerForm({ ...containerForm, max_payload_kg: parseFloat(e.target.value) || 0 })} data-testid="ship-container-payload" />
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="ghost" className="flex-1" onClick={() => setShowContainerEdit(false)}>Cancel</Button>
              <Button className="flex-1" onClick={saveContainer} data-testid="ship-container-save">Save dimensions</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit-PIN dialog */}
      <Dialog open={showPinDialog} onOpenChange={(o) => { if (!o) { setShowPinDialog(false); setPinForm(''); } }}>
        <DialogContent className="max-w-md" data-testid="ship-pin-dialog">
          <DialogHeader>
            <DialogTitle>Shipment edit PIN</DialogTitle>
            <DialogDescription className="text-xs">
              Share this PIN with trusted volunteers (warehouse leads, partner orgs). They&apos;ll log in via the donor page and gain <strong>edit access to this shipment only</strong>. Session lasts 12h. Leave blank to clear.
              {selected?.access_pin_hash && <span className="block mt-1 text-emerald-700">A PIN is currently active.</span>}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 mt-2">
            <div className="space-y-1"><Label className="text-xs">New PIN (4-32 chars, leave blank to clear)</Label>
              <Input type="text" value={pinForm} onChange={e => setPinForm(e.target.value)} placeholder="e.g. warehouse-2026" data-testid="ship-pin-input" />
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="ghost" className="flex-1" onClick={() => { setShowPinDialog(false); setPinForm(''); }}>Cancel</Button>
              <Button className="flex-1" onClick={savePin} data-testid="ship-pin-save">{pinForm.trim() ? 'Set / update PIN' : 'Clear PIN'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

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

      {/* CSV import dialog */}
      <Dialog open={showCsvImport} onOpenChange={(o) => { if (!o) { setShowCsvImport(false); setCsvRows([]); } }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="ship-csv-dialog">
          <DialogHeader>
            <DialogTitle>Bulk import items from CSV</DialogTitle>
            <DialogDescription className="text-xs">
              Paste-friendly format. Required column: <code className="bg-muted px-1 rounded">name</code>.
              Optional: <code className="bg-muted px-1 rounded">category, qty_needed, qty_acquired, weight_kg, length_cm, width_cm, height_cm, value_usd, priority, notes</code>.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="flex gap-2 flex-wrap">
              <Button size="sm" variant="outline" onClick={downloadCsvTemplate} data-testid="ship-csv-template">
                <Download size={11} className="mr-1" /> Download template
              </Button>
              <label className="cursor-pointer">
                <input type="file" accept=".csv,text/csv" className="hidden" onChange={e => e.target.files?.[0] && parseCsvFile(e.target.files[0])} data-testid="ship-csv-file" />
                <span className="inline-flex items-center px-3 py-1.5 rounded text-xs bg-primary text-primary-foreground hover:bg-primary/90">
                  <Upload size={11} className="mr-1" /> Choose CSV file
                </span>
              </label>
              {csvRows.length > 0 && (
                <Badge variant="outline" className="text-[10px]">{csvRows.length} row{csvRows.length === 1 ? '' : 's'} ready</Badge>
              )}
            </div>

            {csvRows.length > 0 && (
              <div className="border rounded overflow-auto max-h-[40vh]">
                <table className="w-full text-[11px]">
                  <thead className="bg-muted/40 sticky top-0">
                    <tr>
                      <th className="text-left p-2">Name</th>
                      <th className="text-left p-2">Category</th>
                      <th className="text-left p-2">Qty</th>
                      <th className="text-left p-2">Weight</th>
                      <th className="text-left p-2">L×W×H</th>
                      <th className="text-left p-2">Value</th>
                      <th className="text-left p-2">Priority</th>
                    </tr>
                  </thead>
                  <tbody>
                    {csvRows.slice(0, 100).map((r, idx) => (
                      <tr key={idx} className="border-t" data-testid={`ship-csv-row-${idx}`}>
                        <td className="p-2 font-medium">{r.name}</td>
                        <td className="p-2 text-muted-foreground">{r.category || '—'}</td>
                        <td className="p-2">{r.qty_needed}</td>
                        <td className="p-2">{r.weight_kg || '—'}</td>
                        <td className="p-2">{(r.dims_cm.length || r.dims_cm.width || r.dims_cm.height) ? `${r.dims_cm.length}×${r.dims_cm.width}×${r.dims_cm.height}` : '—'}</td>
                        <td className="p-2">{r.value_usd ? `$${r.value_usd}` : '—'}</td>
                        <td className="p-2">{r.priority}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {csvRows.length > 100 && <p className="text-[10px] text-muted-foreground p-2">Showing first 100 of {csvRows.length} — all will be imported.</p>}
              </div>
            )}

            <div className="flex gap-2 pt-1">
              <Button variant="ghost" className="flex-1" onClick={() => { setShowCsvImport(false); setCsvRows([]); }}>Cancel</Button>
              <Button className="flex-1" disabled={csvRows.length === 0 || csvBusy} onClick={submitCsvImport} data-testid="ship-csv-submit">
                {csvBusy ? 'Importing…' : `Import ${csvRows.length} item${csvRows.length === 1 ? '' : 's'}`}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* URL estimate dialog */}
      <Dialog open={!!linkUrlFor} onOpenChange={(o) => { if (!o) setLinkUrlFor(null); }}>
        <DialogContent className="max-w-md" data-testid="ship-link-dialog">
          <DialogHeader>
            <DialogTitle>Estimate size & weight from product URL</DialogTitle>
            <DialogDescription className="text-xs">
              Paste an Amazon, Walmart, or any retailer&apos;s product link. Gemini will guess weight, dimensions, and approximate value — you can edit afterward.
            </DialogDescription>
          </DialogHeader>
          {linkUrlFor && (
            <div className="space-y-2 mt-2">
              <Input value={linkUrlFor.url} onChange={e => setLinkUrlFor({ ...linkUrlFor, url: e.target.value })}
                placeholder="https://www.amazon.com/dp/B0..." data-testid="ship-link-url" />
              <p className="text-[10px] text-muted-foreground">Takes ~10–15 seconds. Confidence (high/medium/low) is shown on the item badge after.</p>
              <div className="flex gap-2 pt-1">
                <Button variant="ghost" className="flex-1" onClick={() => setLinkUrlFor(null)}>Cancel</Button>
                <Button className="flex-1" disabled={linkBusyId === linkUrlFor.itemId} onClick={() => estimateFromLink(linkUrlFor.itemId, linkUrlFor.url)} data-testid="ship-link-submit">
                  {linkBusyId === linkUrlFor.itemId ? 'Estimating…' : 'Estimate'}
                </Button>
              </div>
            </div>
          )}
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
