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
import { formatDimCm, formatWeightKg, parseDimToCm, parseWeightToKg, dimPlaceholder, weightPlaceholder } from '../services/shipmentUnits';
import { Plus, Trash2, Copy, RefreshCw, Container, Sparkles, ExternalLink, ArrowLeft, Layers, Upload, Image as ImageIcon, Link2, FileSpreadsheet, Download, Pencil, Ruler, KeyRound, Boxes, Scissors, Loader2, ShieldAlert, Users, ChevronDown, FileText, MoreVertical, X } from 'lucide-react';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator, DropdownMenuLabel } from '../components/ui/dropdown-menu';
import { Checkbox } from '../components/ui/checkbox';
import api from '../services/api';
import { toast } from 'sonner';
import EmptyState from '../components/EmptyState';
import ContainerVisualizer from '../components/ContainerVisualizer';
import { ShipmentPackingPanel } from './shipping/ShipmentPackingPanel';
import { PackingDndProvider, useShipItemDrag } from './shipping/packingDnd';

// Small inline wrapper so we can use the react-dnd hook per-item without
// having to hoist the entire Card into a separate component. Renders a
// draggable Card via a `ref` from useDrag; children receive `isDragging`
// through a render-prop pattern for optional styling.
function DraggableItemCard({ itemId, className, testId, children, title }) {
  const { dragRef, isDragging } = useShipItemDrag(itemId);
  return (
    <div ref={dragRef} className={`cursor-move ${isDragging ? 'opacity-50' : ''} ${className || ''}`}
         data-testid={testId} title={title}>
      {typeof children === 'function' ? children({ isDragging }) : children}
    </div>
  );
}
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
  // iter228 — admin-side AI scan (mirrors public /scan-item without PIN gate)
  const [showAdminScan, setShowAdminScan] = useState(false);
  const [adminScanImages, setAdminScanImages] = useState([]);
  const [adminScanBusy, setAdminScanBusy] = useState(false);
  const [adminScanResult, setAdminScanResult] = useState(null);
  // iter 249 — batch box-photo scan. Uploads N photos of labeled cardboard
  // boxes; AI reads the box number + items and auto-populates the shipment.
  const [showBoxScan, setShowBoxScan] = useState(false);
  const [boxScanImages, setBoxScanImages] = useState([]);
  const [boxScanBusy, setBoxScanBusy] = useState(false);
  const [boxScanResult, setBoxScanResult] = useState(null);
  // iter229 — hide items that have been packed into a box/pallet/packing-unit/suitcase
  // (they still appear on the manifest & PDFs — just cleaner working view).
  const [hidePacked, setHidePacked] = useState(true);
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

  // ─── AI finds the best retailer search URL for a needed item ──
  const findLinkAi = async (itemId) => {
    setLinkBusyId(itemId);
    try {
      const r = await api.post(`/shipments/${selectedId}/items/${itemId}/find-link`);
      toast.success(`Linked to ${r.data.retailer} search · "${r.data.query}"`);
      setLinkUrlFor({ itemId, url: r.data.url });
      await refreshDetail();
    } catch (e) { toast.error(e.response?.data?.detail || 'AI find-link failed'); }
    finally { setLinkBusyId(null); }
  };

  // ─── Bulk find-links for every item still missing a source_url ─
  const [bulkFindBusy, setBulkFindBusy] = useState(false);
  const [packDialogFor, setPackDialogFor] = useState(null);  // {item: {...}}
  const bulkFindLinks = async () => {
    const missing = (selected?.items || []).filter(i => !i.source_url && (i.qty_acquired || 0) < (i.qty_needed || 0));
    if (missing.length === 0) { toast.info('All needed items already have a link'); return; }
    if (!window.confirm(`Ask AI to find buy-links for ${missing.length} un-linked item${missing.length === 1 ? '' : 's'}? Runs sequentially so you'll see progress.`)) return;
    setBulkFindBusy(true);
    let ok = 0, failed = 0;
    for (const it of missing) {
      try {
        await api.post(`/shipments/${selectedId}/items/${it.id}/find-link`);
        ok += 1;
      } catch { failed += 1; }
    }
    await refreshDetail();
    setBulkFindBusy(false);
    if (failed === 0) toast.success(`Linked ${ok} items`);
    else toast.warning(`Linked ${ok} · ${failed} failed`);
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
          condition: ((r.condition || 'used').toString().trim().toLowerCase()),
          hs_code: (r.hs_code || '').toString().trim(),
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
        packing_unit_id: editingItem.packing_unit_id || null,
        suitcase_id: editingItem.suitcase_id || null,
        x_cm: Number(editingItem.x_cm) || 0,
        y_cm: Number(editingItem.y_cm) || 0,
        z_cm: Number(editingItem.z_cm) || 0,
        notes: editingItem.notes || '',
        condition: editingItem.condition || 'used',
        hs_code: (editingItem.hs_code || '').trim(),
        requires_pvoc: !!editingItem.requires_pvoc,
        pvoc_reason: editingItem.pvoc_reason || '',
        manifest_group_id: editingItem.manifest_group_id || null,
      });
      toast.success('Item updated');
      setEditingItem(null);
      await refreshDetail();
    } catch (e) { toast.error(e.response?.data?.detail || 'Save failed'); }
  };

  // ─── AI bulk-classify HS codes + PVoC (customs manifest) ─────────
  const [hsBusy, setHsBusy] = useState(false);
  const bulkClassifyHs = async () => {
    const missing = (selected?.items || []).filter(i => !(i.hs_code || '').trim());
    if (missing.length === 0 && !window.confirm('All items already have HS codes. Re-classify everything anyway?')) return;
    const force = missing.length === 0;
    setHsBusy(true);
    try {
      const r = await api.post(`/shipments/${selectedId}/classify-hs-bulk`, { force });
      const { classified, failed, skipped_existing, pvoc_flagged } = r.data || {};
      toast.success(`AI classified ${classified} item${classified === 1 ? '' : 's'}${pvoc_flagged ? ` · ${pvoc_flagged} PVoC-flagged` : ''}${failed ? ` · ${failed} failed` : ''}${skipped_existing ? ` · ${skipped_existing} already had HS code` : ''}`);
      await refreshDetail();
    } catch (e) { toast.error(e.response?.data?.detail || 'HS classification failed'); }
    finally { setHsBusy(false); }
  };

  // ─── Toggle PVoC flag manually on a single item ────────────────
  const togglePvoc = async (item) => {
    try {
      await api.put(`/shipments/${selectedId}/items/${item.id}`, {
        requires_pvoc: !item.requires_pvoc,
        pvoc_reason: item.requires_pvoc ? '' : (item.pvoc_reason || 'Manually flagged'),
      });
      await refreshDetail();
    } catch (e) { toast.error(e.response?.data?.detail || 'PVoC toggle failed'); }
  };

  // ─── Assign an item to a manifest group ────────────────────────
  const setItemGroup = async (item, gid) => {
    try {
      await api.put(`/shipments/${selectedId}/items/${item.id}`, { manifest_group_id: gid || null });
      await refreshDetail();
    } catch (e) { toast.error(e.response?.data?.detail || 'Group assignment failed'); }
  };

  // ─── Manifest groups CRUD ──────────────────────────────────────
  const [newGroupName, setNewGroupName] = useState('');
  const [newGroupConsignee, setNewGroupConsignee] = useState('');
  const [showAddGroup, setShowAddGroup] = useState(false);
  const addManifestGroup = async () => {
    const name = newGroupName.trim();
    if (!name) return;
    try {
      await api.post(`/shipments/${selectedId}/manifest-groups`, { name, consignee_name: newGroupConsignee.trim() });
      toast.success(`Group "${name}" created`);
      setNewGroupName(''); setNewGroupConsignee(''); setShowAddGroup(false);
      await refreshDetail();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed to create group'); }
  };
  const deleteManifestGroup = async (g) => {
    if (!window.confirm(`Delete group "${g.name}"? Items in it will move back to Unassigned.`)) return;
    try {
      await api.delete(`/shipments/${selectedId}/manifest-groups/${g.id}`);
      toast.success('Group deleted');
      await refreshDetail();
    } catch (e) { toast.error(e.response?.data?.detail || 'Delete failed'); }
  };
  const renameManifestGroup = async (g) => {
    const name = window.prompt('New group name', g.name);
    if (!name || name.trim() === g.name) return;
    try {
      await api.put(`/shipments/${selectedId}/manifest-groups/${g.id}`, { name: name.trim() });
      await refreshDetail();
    } catch (e) { toast.error(e.response?.data?.detail || 'Rename failed'); }
  };

  // ─── Download printable customs manifest / invoice PDFs ─────────
  const downloadPdf = async (kind, gid) => {
    const path = kind === 'invoice' ? 'commercial-invoice.pdf' : 'manifest.pdf';
    const qs = gid ? `?group=${encodeURIComponent(gid)}` : '';
    try {
      const r = await api.get(`/shipments/${selectedId}/${path}${qs}`, { responseType: 'blob' });
      const blob = new Blob([r.data], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const groupSuffix = gid && gid !== 'unassigned' ? '_' + (selected?.manifest_groups || []).find(g => g.id === gid)?.name?.replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 40) : (gid === 'unassigned' ? '_unassigned' : '');
      a.download = `${kind === 'invoice' ? 'invoice' : 'manifest'}-${(selected?.name || 'shipment').replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 40)}${groupSuffix}.pdf`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success(`${kind === 'invoice' ? 'Invoice' : 'Manifest'} downloaded`);
    } catch (e) { toast.error(e.response?.data?.detail || 'PDF generation failed'); }
  };
  const downloadManifest = (gid) => downloadPdf('manifest', gid);
  const downloadInvoice = (gid) => downloadPdf('invoice', gid);

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
    <PackingDndProvider>
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
                <span>{formatWeightKg(Number(totals.weight) || 0, selected.units)} of {formatWeightKg(totals.cap, selected.units)} cap</span>
                <span className="text-muted-foreground">{totals.acquired} of {totals.acquired + totals.needed} items fully covered · est. value ${totals.value}</span>
              </div>
              <div className="h-2 rounded bg-muted overflow-hidden">
                <div className={`h-full ${totals.pct > 100 ? 'bg-rose-500' : totals.pct > 80 ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{ width: `${totals.pct}%` }} />
              </div>
              {totals.pct > 100 && <p className="text-[11px] text-rose-700">⚠ Over the 40&apos; container payload cap by {formatWeightKg((Number(totals.weight) || 0) - totals.cap, selected.units)}.</p>}
              <div className="flex items-center justify-end gap-1.5 pt-1">
                <span className="text-[10px] text-muted-foreground">Units:</span>
                <div className="inline-flex rounded border overflow-hidden text-[10px]">
                  <button
                    type="button"
                    className={`px-2 py-0.5 ${(selected.units || 'metric') === 'metric' ? 'bg-primary text-primary-foreground font-semibold' : 'bg-background hover:bg-muted'}`}
                    onClick={async () => {
                      if ((selected.units || 'metric') === 'metric') return;
                      try {
                        await api.put(`/shipments/${selected.id}`, { units: 'metric' });
                        await refreshDetail();
                        toast.success('Display switched to metric (cm/kg)');
                      } catch (e) { toast.error('Failed to switch units'); }
                    }}
                    data-testid="ship-units-metric"
                  >cm/kg</button>
                  <button
                    type="button"
                    className={`px-2 py-0.5 ${selected.units === 'imperial' ? 'bg-primary text-primary-foreground font-semibold' : 'bg-background hover:bg-muted'}`}
                    onClick={async () => {
                      if (selected.units === 'imperial') return;
                      try {
                        await api.put(`/shipments/${selected.id}`, { units: 'imperial' });
                        await refreshDetail();
                        toast.success('Display switched to imperial (ft·in / lb·oz)');
                      } catch (e) { toast.error('Failed to switch units'); }
                    }}
                    data-testid="ship-units-imperial"
                  >ft·in / lb·oz</button>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* iter223 — mode picker + waybill + AI tracking + packing units / passengers */}
      {/* iter228: The old dedicated "Pallets" row has been folded into the unified
          "Packing units" section below (which handles pallets/boxes/totes as one
          consistent surface). ContainerVisualizer now renders both legacy
          `pallets` AND `packing_units` in a single 2D+3D layout. */}
      <ShipmentPackingPanel
        shipment={selected}
        refresh={refreshDetail}
        onDropItem={(itemId, kind, containerId) => {
          // iter230 — drag-drop packing. kind is 'p' (legacy pallet) | 'u'
          // (packing unit) | 's' (suitcase); we normalise to the right field.
          const patch = { pallet_id: null, packing_unit_id: null, suitcase_id: null };
          if (kind === 'p') patch.pallet_id = containerId;
          else if (kind === 'u') patch.packing_unit_id = containerId;
          else if (kind === 's') patch.suitcase_id = containerId;
          return updateItem(itemId, patch);
        }}
      />

      <RecentScans shipmentId={selectedId} refreshDetail={refreshDetail} />

      {/* Manifest Groups (sub-consignments) */}
      <div className="mb-3" data-testid="ship-manifest-groups">
        <div className="flex items-center justify-between mb-1.5 gap-2 flex-wrap">
          <div className="flex items-center gap-1.5">
            <Users size={12} className="text-slate-500" />
            <p className="text-xs font-semibold">Manifest Groups ({(selected.manifest_groups || []).length})</p>
            <span className="text-[10px] text-muted-foreground">— split one container into multiple consignments</span>
          </div>
          <Button size="sm" variant="outline" onClick={() => setShowAddGroup(true)} data-testid="ship-add-manifest-group-btn">
            <Plus size={11} className="mr-1" /> New group
          </Button>
        </div>
        {(selected.manifest_groups || []).length === 0 ? (
          <p className="text-[10px] text-muted-foreground italic">No groups yet. Items ship on one combined manifest. Add a group (e.g. &ldquo;Lubwama Household Relocation&rdquo;) to split.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {(selected.manifest_groups || []).map(g => {
              const count = (selected.items || []).filter(i => i.manifest_group_id === g.id).length;
              return (
                <div key={g.id} className="flex items-center gap-1 bg-cyan-50 border border-cyan-200 rounded px-2 py-1 text-[11px]" data-testid={`ship-mg-${g.id}`}>
                  <span className="font-medium text-cyan-900">{g.name}</span>
                  <span className="text-cyan-600">· {count} item{count === 1 ? '' : 's'}</span>
                  {g.consignee_name && <span className="text-cyan-600 italic">· → {g.consignee_name}</span>}
                  <button onClick={() => renameManifestGroup(g)} className="ml-1 text-cyan-700 hover:text-cyan-900" title="Rename group"><Pencil size={10} /></button>
                  <button onClick={() => deleteManifestGroup(g)} className="text-rose-600 hover:text-rose-800" title="Delete group"><X size={11} /></button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Items list */}
      <div>
        <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
          {/* iter229 — item count now shows visible/total when hidePacked is on */}
          {(() => {
            const items = selected.items || [];
            const packed = items.filter(i => i.pallet_id || i.packing_unit_id || i.suitcase_id).length;
            const visible = hidePacked ? items.length - packed : items.length;
            return (
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-xs font-semibold">
                  Items ({visible}
                  {hidePacked && packed > 0 && <span className="text-slate-500 font-normal"> of {items.length}, {packed} packed hidden</span>})
                  <span className="text-[10px] font-normal text-muted-foreground ml-1">— sorted PVoC ▸ value ▸ weight</span>
                </p>
                {/* iter230 — drag-drop hint (auto-hides once any item is packed) */}
                {items.length > 0 && packed === 0 && (
                  <span className="text-[10px] italic text-indigo-600 bg-indigo-50 border border-indigo-200 rounded px-2 py-0.5">
                    💡 Tip: drag any item onto a pallet / box / suitcase below to pack it
                  </span>
                )}
                {packed > 0 && (
                  <label className="flex items-center gap-1 text-[10.5px] cursor-pointer select-none text-muted-foreground hover:text-foreground" data-testid="hide-packed-toggle">
                    <input type="checkbox" checked={hidePacked} onChange={e => setHidePacked(e.target.checked)} className="accent-emerald-600" />
                    Hide packed
                  </label>
                )}
              </div>
            );
          })()}
          <div className="flex gap-1.5 flex-wrap">
            {(() => {
              const missingHs = (selected.items || []).filter(i => !(i.hs_code || '').trim()).length;
              return (
                <Button size="sm" variant="outline" className="text-teal-700 border-teal-300 hover:bg-teal-50" onClick={bulkClassifyHs} disabled={hsBusy || (selected.items || []).length === 0} data-testid="ship-bulk-hs-btn" title="Ask AI to assign customs HS-6 codes + PVoC flags to every item without one">
                  {hsBusy ? <><Loader2 size={11} className="mr-1 animate-spin" /> Classifying…</> : <>🏷️ AI HS + PVoC{missingHs > 0 ? ` (${missingHs})` : ' · Re-classify'}</>}
                </Button>
              );
            })()}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" variant="outline" className="text-slate-700 border-slate-300 hover:bg-slate-50" disabled={(selected.items || []).length === 0} data-testid="ship-manifest-btn" title="Download printable customs manifest PDF — full container or per manifest group">
                  <Download size={11} className="mr-1" /> Print Manifest <ChevronDown size={10} className="ml-1" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-64">
                <DropdownMenuLabel>Customs Manifest</DropdownMenuLabel>
                <DropdownMenuItem onClick={() => downloadManifest(null)} data-testid="ship-manifest-all">
                  <Download size={12} className="mr-2" /> All items (whole container)
                </DropdownMenuItem>
                {(selected.manifest_groups || []).length > 0 && <DropdownMenuSeparator />}
                {(selected.manifest_groups || []).map(g => (
                  <DropdownMenuItem key={g.id} onClick={() => downloadManifest(g.id)} data-testid={`ship-manifest-grp-${g.id}`}>
                    <FileText size={12} className="mr-2" /> {g.name}
                  </DropdownMenuItem>
                ))}
                {(selected.items || []).some(i => !i.manifest_group_id) && (selected.manifest_groups || []).length > 0 && (
                  <DropdownMenuItem onClick={() => downloadManifest('unassigned')} data-testid="ship-manifest-unassigned">
                    <FileText size={12} className="mr-2" /> Unassigned items
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" variant="outline" className="text-emerald-700 border-emerald-300 hover:bg-emerald-50" disabled={(selected.items || []).length === 0} data-testid="ship-invoice-btn" title="Download commercial invoice PDF (declared values, HS codes, PVoC-first sort)">
                  <FileText size={11} className="mr-1" /> Invoice <ChevronDown size={10} className="ml-1" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-64">
                <DropdownMenuLabel>Commercial Invoice</DropdownMenuLabel>
                <DropdownMenuItem onClick={() => downloadInvoice(null)} data-testid="ship-invoice-all">
                  <FileText size={12} className="mr-2" /> All items (whole container)
                </DropdownMenuItem>
                {(selected.manifest_groups || []).length > 0 && <DropdownMenuSeparator />}
                {(selected.manifest_groups || []).map(g => (
                  <DropdownMenuItem key={g.id} onClick={() => downloadInvoice(g.id)} data-testid={`ship-invoice-grp-${g.id}`}>
                    <FileText size={12} className="mr-2" /> {g.name}
                  </DropdownMenuItem>
                ))}
                {(selected.items || []).some(i => !i.manifest_group_id) && (selected.manifest_groups || []).length > 0 && (
                  <DropdownMenuItem onClick={() => downloadInvoice('unassigned')} data-testid="ship-invoice-unassigned">
                    <FileText size={12} className="mr-2" /> Unassigned items
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
            {(() => {
              const unlinked = (selected.items || []).filter(i => !i.source_url && (i.qty_acquired || 0) < (i.qty_needed || 0)).length;
              if (unlinked === 0) return null;
              return (
                <Button size="sm" variant="outline" className="text-indigo-700 border-indigo-300 hover:bg-indigo-50" onClick={bulkFindLinks} disabled={bulkFindBusy} data-testid="ship-bulk-findlink-btn" title="Ask AI to pick a best-fit retailer search link for every needed item that isn't linked yet">
                  {bulkFindBusy ? <><Loader2 size={11} className="mr-1 animate-spin" /> Finding…</> : <>🤖 Find links ({unlinked})</>}
                </Button>
              );
            })()}
            {(totals?.overPledged || 0) > 0 && (
              <Button size="sm" variant="outline" className="text-amber-700 border-amber-300 hover:bg-amber-50" onClick={pruneOverPledged} data-testid="ship-prune-overpledged-btn" title="Trim over-pledged items back to their pledged quantity. Surplus is logged for redistribution.">
                <Scissors size={11} className="mr-1" /> Prune over-pledged ({totals.overPledged})
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => setShowCsvImport(true)} data-testid="ship-csv-import-btn">
              <FileSpreadsheet size={11} className="mr-1" /> Import CSV
            </Button>
            <Button size="sm" variant="outline" onClick={() => setShowAdminScan(true)} className="text-purple-700 border-purple-300 hover:bg-purple-50" data-testid="ship-ai-scan-btn">
              <Sparkles size={11} className="mr-1" /> AI Scan
            </Button>
            <Button size="sm" variant="outline" onClick={() => setShowBoxScan(true)} className="text-emerald-700 border-emerald-300 hover:bg-emerald-50" data-testid="ship-box-scan-btn">
              <Boxes size={11} className="mr-1" /> Scan Boxes
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
            {(() => {
              // Sort same as PDFs: PVoC-required first, then highest value, then heaviest.
              // iter229 — optionally hide items already assigned to a box/pallet/suitcase
              // (they're still on manifests & PDFs — cleaner working view).
              const source = hidePacked
                ? (selected.items || []).filter(i => !(i.pallet_id || i.packing_unit_id || i.suitcase_id))
                : (selected.items || []);
              const sorted = [...source].sort((a, b) => {
                const pvocA = a.requires_pvoc ? 0 : 1;
                const pvocB = b.requires_pvoc ? 0 : 1;
                if (pvocA !== pvocB) return pvocA - pvocB;
                const valA = (a.value_usd || 0) * (a.qty_acquired || 0);
                const valB = (b.value_usd || 0) * (b.qty_acquired || 0);
                if (valA !== valB) return valB - valA;
                const wtA = (a.weight_kg || 0) * (a.qty_acquired || 0);
                const wtB = (b.weight_kg || 0) * (b.qty_acquired || 0);
                return wtB - wtA;
              });
              return sorted;
            })().map(it => {
              const remaining = Math.max(0, (it.qty_needed || 0) - (it.qty_acquired || 0));
              const covered = remaining === 0;
              return (
                <DraggableItemCard
                  key={it.id}
                  itemId={it.id}
                  testId={`ship-item-${it.id}`}
                  title="Drag me onto a pallet, box or suitcase to pack this item"
                >
                <Card className={`rounded-lg ${covered ? 'bg-emerald-50/50' : ''} hover:shadow-md transition-shadow`}>
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
                        <button
                          onClick={() => togglePvoc(it)}
                          className={`inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded font-semibold transition-colors ${it.requires_pvoc ? 'bg-rose-100 text-rose-800 border border-rose-300 hover:bg-rose-200' : 'bg-slate-50 text-slate-400 border border-slate-200 hover:bg-slate-100 hover:text-slate-600'}`}
                          title={it.requires_pvoc ? `PVoC required: ${it.pvoc_reason || 'flagged manually'} — click to un-flag` : 'Click to flag as PVoC-required'}
                          data-testid={`ship-item-pvoc-${it.id}`}
                        >
                          <ShieldAlert size={10} /> PVoC{it.requires_pvoc ? '' : '?'}
                        </button>
                        {(selected.manifest_groups || []).length > 0 && (() => {
                          const g = (selected.manifest_groups || []).find(x => x.id === it.manifest_group_id);
                          return (
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <button
                                  className={`inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded border transition-colors ${g ? 'bg-cyan-50 text-cyan-800 border-cyan-300 hover:bg-cyan-100' : 'bg-slate-50 text-slate-500 border-slate-200 border-dashed hover:bg-slate-100'}`}
                                  title={g ? `In manifest group: ${g.name}` : 'Unassigned — click to add to a group'}
                                  data-testid={`ship-item-group-${it.id}`}
                                >
                                  <Users size={10} /> {g?.name?.slice(0, 20) || 'unassigned'}
                                  <ChevronDown size={9} />
                                </button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="start">
                                <DropdownMenuItem onClick={() => setItemGroup(it, null)}>
                                  <X size={11} className="mr-2" /> Unassigned
                                </DropdownMenuItem>
                                <DropdownMenuSeparator />
                                {(selected.manifest_groups || []).map(mg => (
                                  <DropdownMenuItem key={mg.id} onClick={() => setItemGroup(it, mg.id)}>
                                    <Users size={11} className="mr-2" /> {mg.name}
                                  </DropdownMenuItem>
                                ))}
                              </DropdownMenuContent>
                            </DropdownMenu>
                          );
                        })()}
                        {it.hs_code && (
                          <Badge variant="outline" className="text-[10px] font-mono bg-teal-50 text-teal-700 border-teal-200" title={it.hs_code_reason || 'AI-assigned HS-6 customs code'} data-testid={`ship-item-hs-${it.id}`}>
                            HS {it.hs_code}
                          </Badge>
                        )}
                        {it.condition && (
                          <Badge variant="outline" className={`text-[10px] ${it.condition === 'new' ? 'bg-green-50 text-green-700 border-green-200' : it.condition === 'refurbished' ? 'bg-blue-50 text-blue-700 border-blue-200' : 'bg-amber-50 text-amber-700 border-amber-200'}`} data-testid={`ship-item-cond-${it.id}`}>
                            {it.condition}
                          </Badge>
                        )}
                        {it.ai_estimate && <Badge variant="outline" className="text-[10px]" title={it.ai_estimate.reasoning}>AI · {it.ai_estimate.confidence}</Badge>}
                        {(it.auto_placed || it.auto_stacked) && (() => {
                          const palletLabel = palletsById[it.pallet_id]?.label || it.pallet_id || '—';
                          const parent = it.parent_id ? (selected.items || []).find(x => x.id === it.parent_id) : null;
                          const parts = [];
                          if (it.auto_placed) parts.push(`Auto-assigned to "${palletLabel}" (lightest pallet at the time)`);
                          if (it.auto_stacked && parent) parts.push(`Stacked on top of "${parent.name}" (heavier, sturdier base) at z=${it.z_cm}cm`);
                          const reason = parts.join('. ') || 'Auto-placed by scanner';
                          return (
                            <Badge variant="outline" className="text-[10px] bg-indigo-50 text-indigo-700 border-indigo-200 cursor-help" title={reason} data-testid={`ship-item-auto-${it.id}`}>
                              🤖 Auto-placed
                            </Badge>
                          );
                        })()}
                      </div>
                      <p className="text-[10px] text-muted-foreground">
                        {it.qty_acquired || 0} of {it.qty_needed || 0}
                        {it.weight_kg ? ` · ${formatWeightKg(it.weight_kg, selected.units)}/unit` : ''}
                        {(it.dims_cm?.length || it.dims_cm?.width || it.dims_cm?.height) ? ` · ${formatDimCm(it.dims_cm?.length || 0, selected.units)} × ${formatDimCm(it.dims_cm?.width || 0, selected.units)} × ${formatDimCm(it.dims_cm?.height || 0, selected.units)}` : ''}
                        {it.value_usd ? ` · $${it.value_usd}/unit` : ''}
                        {(() => {
                          // iter229 — show placement no matter which surface it came from
                          if (it.pallet_id) return ` · 🟫 ${palletsById[it.pallet_id]?.label || it.pallet_id}`;
                          if (it.packing_unit_id) {
                            const u = (selected.packing_units || []).find(x => x.id === it.packing_unit_id);
                            const icon = u?.type === 'box' ? '📦' : u?.type === 'tote' ? '🗑️' : u?.type === 'crate' ? '🪵' : '🟫';
                            return ` · ${icon} ${u?.name || u?.preset_key || it.packing_unit_id}`;
                          }
                          if (it.suitcase_id) {
                            const sc = (selected.suitcases || []).find(x => x.id === it.suitcase_id);
                            return ` · 🧳 ${sc?.name || it.suitcase_id}`;
                          }
                          return '';
                        })()}
                      </p>
                      {it.source_url && (
                        <a
                          href={it.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 mt-0.5 text-[10px] text-emerald-700 hover:text-emerald-900 hover:underline"
                          data-testid={`ship-item-buy-${it.id}`}
                          title={it.source_retailer ? `Open ${it.source_retailer} search` : 'Open product link'}
                        >
                          🛒 Buy {it.source_retailer ? `at ${it.source_retailer}` : 'link'} <ExternalLink size={9} />
                        </a>
                      )}
                    </div>
                    {/* iter229 — unified "Place in..." select combines legacy
                        pallets + new packing_units + suitcases so the user
                        always has a way to pack items regardless of which
                        surface they've been created in. Always shown so users
                        know packing is possible even before adding a container. */}
                    {(() => {
                      const legacyPallets = selected.pallets || [];
                      const packingUnits = selected.packing_units || [];
                      const suitcases = selected.suitcases || [];
                      const totalContainers = legacyPallets.length + packingUnits.length + suitcases.length;
                      // Current value key: id prefixed by kind so we can route on save
                      const currentKey = it.pallet_id ? `p:${it.pallet_id}`
                        : it.packing_unit_id ? `u:${it.packing_unit_id}`
                        : it.suitcase_id ? `s:${it.suitcase_id}`
                        : 'none';
                      if (totalContainers === 0) {
                        return (
                          <span
                            className="text-[10.5px] italic text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1 whitespace-nowrap"
                            title="Add a pallet / box / tote in the Packing units section above, then come back to assign this item."
                            data-testid={`ship-item-no-container-${it.id}`}
                          >
                            ↑ Add a box first
                          </span>
                        );
                      }
                      return (
                        <Select
                          value={currentKey}
                          onValueChange={v => {
                            const patch = { pallet_id: null, packing_unit_id: null, suitcase_id: null };
                            if (v.startsWith('p:')) patch.pallet_id = v.slice(2);
                            else if (v.startsWith('u:')) patch.packing_unit_id = v.slice(2);
                            else if (v.startsWith('s:')) patch.suitcase_id = v.slice(2);
                            updateItem(it.id, patch);
                          }}
                        >
                          <SelectTrigger className="h-7 w-40 text-[11px]" data-testid={`ship-item-place-${it.id}`}>
                            <SelectValue placeholder="Place in…" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="none">— Loose (no container) —</SelectItem>
                            {legacyPallets.length > 0 && (
                              <div className="px-2 py-1 text-[9px] uppercase tracking-wider text-muted-foreground">Pallets</div>
                            )}
                            {legacyPallets.map(p => (
                              <SelectItem key={p.id} value={`p:${p.id}`}>🟫 {p.label}</SelectItem>
                            ))}
                            {packingUnits.length > 0 && (
                              <div className="px-2 py-1 text-[9px] uppercase tracking-wider text-muted-foreground">Packing units</div>
                            )}
                            {packingUnits.map(u => {
                              const icon = u.type === 'box' ? '📦' : u.type === 'tote' ? '🗑️' : u.type === 'crate' ? '🪵' : u.type === 'bin' ? '🪣' : '🟫';
                              return (
                                <SelectItem key={u.id} value={`u:${u.id}`}>{icon} {u.name || u.preset_key || u.type}</SelectItem>
                              );
                            })}
                            {suitcases.length > 0 && (
                              <div className="px-2 py-1 text-[9px] uppercase tracking-wider text-muted-foreground">Suitcases</div>
                            )}
                            {suitcases.map(sc => (
                              <SelectItem key={sc.id} value={`s:${sc.id}`}>🧳 {sc.name || 'Suitcase'}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      );
                    })()}
                    <Input type="number" className="h-7 w-20 text-[11px]" value={it.qty_acquired || 0}
                      onChange={e => updateItem(it.id, { qty_acquired: parseInt(e.target.value) || 0 })} title="Manual adjustment of acquired qty" />
                    {(() => {
                      const packed = it.qty_packed || 0;
                      const acquired = it.qty_acquired || 0;
                      const mode = it.transport_mode || 'container';
                      const modeIcon = mode === 'suitcase' ? '🧳' : mode === 'holdback' ? '⏸' : '🚢';
                      return (
                        <div className="flex items-center gap-1" title={`${packed} of ${acquired} acquired have been packed for shipping (${mode})`}>
                          <Badge className={`text-[10px] ${packed > acquired ? 'bg-rose-100 text-rose-700 border-rose-300' : packed > 0 ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-600'}`}>
                            {modeIcon} Packed {packed}/{acquired}
                          </Badge>
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0"
                            title="Mark N units as packed for shipping"
                            onClick={() => setPackDialogFor({ item: it })}
                            data-testid={`ship-item-pack-${it.id}`}
                          >📦</Button>
                        </div>
                      );
                    })()}
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
                </DraggableItemCard>
              );
            })}
          </div>
        )}
      </div>

      {/* Container visualization — 2D / 3D (hidden in airport mode — iter226).
          iter228: now receives both legacy `pallets` AND new `packing_units` so
          the single visualizer shows the unified layout — no duplicate views. */}
      {(selected.mode || 'container') !== 'airport' && (
        <>
        <div className="flex justify-end gap-2 -mb-2">
          {/* iter 250 — one-tap map export. JSON for downstream tools (e.g.
              feeding a 3rd-party loader); PNG for sharing / whiteboards.
              PNG grabs the visualiser wrapper via html-to-image. */}
          <Button
            size="sm" variant="outline" data-testid="ship-export-map-json"
            onClick={() => {
              const map = {
                shipment_id: selectedId,
                shipment_name: selected.name,
                container: selected.container_dims_cm,
                packing_units: selected.packing_units || [],
                pallets: selected.pallets || [],
                items: (selected.items || []).map(i => ({
                  id: i.id, name: i.name, qty_acquired: i.qty_acquired,
                  weight_kg: i.weight_kg, dims_cm: i.dims_cm,
                  packing_unit_id: i.packing_unit_id, pallet_id: i.pallet_id,
                  suitcase_id: i.suitcase_id, x_cm: i.x_cm, y_cm: i.y_cm, z_cm: i.z_cm,
                })),
                exported_at: new Date().toISOString(),
              };
              const blob = new Blob([JSON.stringify(map, null, 2)], { type: 'application/json' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `container-map-${(selected.name || 'shipment').replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 40)}.json`;
              a.click();
              URL.revokeObjectURL(url);
              toast.success('Container map JSON downloaded');
            }}
          ><Download size={11} className="mr-1" />JSON</Button>
          <Button
            size="sm" variant="outline" data-testid="ship-export-map-png"
            onClick={async () => {
              try {
                const el = document.getElementById('ship-container-visualizer');
                if (!el) { toast.error('Visualiser not found'); return; }
                const { toPng } = await import('html-to-image');
                const dataUrl = await toPng(el, { cacheBust: true, pixelRatio: 2, backgroundColor: '#ffffff' });
                const a = document.createElement('a');
                a.href = dataUrl;
                a.download = `container-map-${(selected.name || 'shipment').replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 40)}.png`;
                a.click();
                toast.success('Container map PNG downloaded');
              } catch (e) { toast.error('PNG export failed'); }
            }}
          ><ImageIcon size={11} className="mr-1" />PNG</Button>
        </div>
        <div id="ship-container-visualizer">
        <ContainerVisualizer
          items={selected.items || []}
          pallets={selected.pallets || []}
          packing_units={selected.packing_units || []}
          container={selected.container_dims_cm}
          editable
          onPalletMove={async (pid, x, y) => {
            try {
              // iter228 — decide which collection this ID belongs to
              const isPackingUnit = (selected.packing_units || []).some(u => u.id === pid);
              // iter 252 — loose items are individually draggable now. Their
              // group id is prefixed with `_loose:<item_id>` so we route the
              // floor position to the item update endpoint.
              let url;
              let body;
              if (typeof pid === 'string' && pid.startsWith('_loose:')) {
                const itemId = pid.slice('_loose:'.length);
                url = `/shipments/${selectedId}/items/${itemId}`;
                body = { floor_x_cm: Math.round(x), floor_y_cm: Math.round(y) };
              } else if (isPackingUnit) {
                url = `/shipments/${selectedId}/packing-units/${pid}`;
                body = { x_cm: Math.round(x), y_cm: Math.round(y) };
              } else {
                url = `/shipments/${selectedId}/pallets/${pid}`;
                body = { x_cm: Math.round(x), y_cm: Math.round(y) };
              }
              await api.put(url, body);
              await refreshDetail();
            } catch (e) { toast.error(e.response?.data?.detail || 'Move failed'); }
          }}
        />
        </div>
        </>
      )}

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
                <div className="space-y-1"><Label className="text-xs">Weight per unit</Label>
                  <Input type="text" placeholder={weightPlaceholder(selected.units)} value={editingItem.weight_raw ?? (editingItem.weight_kg ? formatWeightKg(editingItem.weight_kg, selected.units) : '')}
                    onChange={e => setEditingItem({ ...editingItem, weight_raw: e.target.value, weight_kg: parseWeightToKg(e.target.value, selected.units) })} />
                </div>
                <div className="space-y-1"><Label className="text-xs">Value per unit (USD)</Label>
                  <Input type="number" step="0.01" value={editingItem.value_usd || 0} onChange={e => setEditingItem({ ...editingItem, value_usd: parseFloat(e.target.value) || 0 })} />
                </div>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Dimensions — L × W × H <span className="text-muted-foreground">({selected.units === 'imperial' ? `try 2'9"` : 'cm or m'})</span></Label>
                <div className="grid grid-cols-3 gap-2">
                  <Input type="text" placeholder={dimPlaceholder(selected.units)} value={editingItem.dim_length_raw ?? (editingItem.dims_cm?.length ? formatDimCm(editingItem.dims_cm.length, selected.units) : '')}
                    onChange={e => setEditingItem({ ...editingItem, dim_length_raw: e.target.value, dims_cm: { ...editingItem.dims_cm, length: parseDimToCm(e.target.value, selected.units) } })}
                    data-testid="ship-edit-item-length" />
                  <Input type="text" placeholder={dimPlaceholder(selected.units)} value={editingItem.dim_width_raw ?? (editingItem.dims_cm?.width ? formatDimCm(editingItem.dims_cm.width, selected.units) : '')}
                    onChange={e => setEditingItem({ ...editingItem, dim_width_raw: e.target.value, dims_cm: { ...editingItem.dims_cm, width: parseDimToCm(e.target.value, selected.units) } })}
                    data-testid="ship-edit-item-width" />
                  <Input type="text" placeholder={dimPlaceholder(selected.units)} value={editingItem.dim_height_raw ?? (editingItem.dims_cm?.height ? formatDimCm(editingItem.dims_cm.height, selected.units) : '')}
                    onChange={e => setEditingItem({ ...editingItem, dim_height_raw: e.target.value, dims_cm: { ...editingItem.dims_cm, height: parseDimToCm(e.target.value, selected.units) } })}
                    data-testid="ship-edit-item-height" />
                </div>
              </div>
              {/* iter229 — unified placement select in edit dialog too */}
              {(() => {
                const legacyPallets = selected.pallets || [];
                const packingUnits = selected.packing_units || [];
                const suitcases = selected.suitcases || [];
                if (legacyPallets.length + packingUnits.length + suitcases.length === 0) return null;
                const currentKey = editingItem.pallet_id ? `p:${editingItem.pallet_id}`
                  : editingItem.packing_unit_id ? `u:${editingItem.packing_unit_id}`
                  : editingItem.suitcase_id ? `s:${editingItem.suitcase_id}`
                  : 'none';
                return (
                  <div className="space-y-1">
                    <Label className="text-xs">Place in container</Label>
                    <Select
                      value={currentKey}
                      onValueChange={v => {
                        const patch = { pallet_id: null, packing_unit_id: null, suitcase_id: null };
                        if (v.startsWith('p:')) patch.pallet_id = v.slice(2);
                        else if (v.startsWith('u:')) patch.packing_unit_id = v.slice(2);
                        else if (v.startsWith('s:')) patch.suitcase_id = v.slice(2);
                        setEditingItem({ ...editingItem, ...patch });
                      }}
                    >
                      <SelectTrigger data-testid="ship-edit-item-place"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">— Loose (no container) —</SelectItem>
                        {legacyPallets.map(p => <SelectItem key={p.id} value={`p:${p.id}`}>🟫 {p.label}</SelectItem>)}
                        {packingUnits.map(u => {
                          const icon = u.type === 'box' ? '📦' : u.type === 'tote' ? '🗑️' : u.type === 'crate' ? '🪵' : u.type === 'bin' ? '🪣' : '🟫';
                          return <SelectItem key={u.id} value={`u:${u.id}`}>{icon} {u.name || u.preset_key || u.type}</SelectItem>;
                        })}
                        {suitcases.map(sc => <SelectItem key={sc.id} value={`s:${sc.id}`}>🧳 {sc.name || 'Suitcase'}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                );
              })()}
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
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">Condition</Label>
                  <Select value={editingItem.condition || 'used'} onValueChange={v => setEditingItem({ ...editingItem, condition: v })}>
                    <SelectTrigger data-testid="ship-edit-item-condition"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="new">New</SelectItem>
                      <SelectItem value="used">Used</SelectItem>
                      <SelectItem value="refurbished">Refurbished</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1"><Label className="text-xs">HS Code (customs, XXXX.XX)</Label>
                  <Input value={editingItem.hs_code || ''} onChange={e => setEditingItem({ ...editingItem, hs_code: e.target.value })} placeholder="e.g. 6309.00" className="font-mono" data-testid="ship-edit-item-hs" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label className="text-xs flex items-center gap-2">
                    <Checkbox
                      checked={!!editingItem.requires_pvoc}
                      onCheckedChange={v => setEditingItem({ ...editingItem, requires_pvoc: !!v })}
                      data-testid="ship-edit-item-pvoc"
                    />
                    <span>Requires PVoC (Pre-Export Verification)</span>
                  </Label>
                  <Input
                    value={editingItem.pvoc_reason || ''}
                    onChange={e => setEditingItem({ ...editingItem, pvoc_reason: e.target.value })}
                    placeholder="Reason (e.g. new electrical, cosmetic)"
                    disabled={!editingItem.requires_pvoc}
                    data-testid="ship-edit-item-pvoc-reason"
                  />
                </div>
                <div className="space-y-1"><Label className="text-xs">Manifest group</Label>
                  <Select
                    value={editingItem.manifest_group_id || '__none__'}
                    onValueChange={v => setEditingItem({ ...editingItem, manifest_group_id: v === '__none__' ? null : v })}
                  >
                    <SelectTrigger data-testid="ship-edit-item-group"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">Unassigned</SelectItem>
                      {(selected?.manifest_groups || []).map(g => (
                        <SelectItem key={g.id} value={g.id}>{g.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
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
      <Dialog open={showAddGroup} onOpenChange={setShowAddGroup}>
        <DialogContent className="max-w-md" data-testid="ship-add-group-dialog">
          <DialogHeader>
            <DialogTitle>New manifest group</DialogTitle>
            <DialogDescription>Split this container into sub-consignments — each group prints its own manifest + commercial invoice.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2 mt-2">
            <div className="space-y-1">
              <Label className="text-xs">Group name *</Label>
              <Input
                value={newGroupName}
                onChange={e => setNewGroupName(e.target.value)}
                placeholder="e.g. Lubwama Household Relocation"
                autoFocus
                data-testid="ship-add-group-name"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Consignee name (optional)</Label>
              <Input
                value={newGroupConsignee}
                onChange={e => setNewGroupConsignee(e.target.value)}
                placeholder="e.g. Lubwama Family"
                data-testid="ship-add-group-consignee"
              />
            </div>
            <p className="text-[10px] text-muted-foreground">
              After creating the group, use the badge on each item row to assign it.
              Items with no group print on the &ldquo;unassigned&rdquo; manifest.
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => { setShowAddGroup(false); setNewGroupName(''); setNewGroupConsignee(''); }}>Cancel</Button>
              <Button size="sm" onClick={addManifestGroup} disabled={!newGroupName.trim()} data-testid="ship-add-group-save">Create group</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

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
            <div className="space-y-1"><Label className="text-xs">Condition</Label>
              <Select value={itemForm.condition || 'used'} onValueChange={v => setItemForm({ ...itemForm, condition: v })}>
                <SelectTrigger data-testid="ship-item-condition"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="new">New</SelectItem>
                  <SelectItem value="used">Used (donated / gently worn)</SelectItem>
                  <SelectItem value="refurbished">Refurbished</SelectItem>
                </SelectContent>
              </Select>
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

      {/* iter228 — Admin AI Scan dialog (same UX as public donor page but no PIN gate) */}
      <Dialog open={showAdminScan} onOpenChange={(o) => { if (!o) { setShowAdminScan(false); setAdminScanImages([]); setAdminScanResult(null); } }}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto" data-testid="admin-scan-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Sparkles size={16} className="text-purple-600" /> AI Scan item</DialogTitle>
            <DialogDescription className="text-xs">Snap up to 3 photos of an item — Gemini identifies it and estimates weight, dimensions and retail value.</DialogDescription>
          </DialogHeader>
          {!adminScanResult ? (
            <div className="space-y-3">
              <div className="rounded-lg border-2 border-dashed border-border p-4 text-center">
                <input
                  id="admin-scan-file"
                  type="file"
                  accept="image/*"
                  multiple
                  capture="environment"
                  className="hidden"
                  data-testid="admin-scan-file"
                  onChange={e => {
                    const files = Array.from(e.target.files || []).slice(0, 3 - adminScanImages.length);
                    setAdminScanImages([...adminScanImages, ...files]);
                    e.target.value = '';
                  }}
                />
                <label htmlFor="admin-scan-file" className="cursor-pointer inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
                  <ImageIcon size={16} /> Tap to add photos ({adminScanImages.length}/3)
                </label>
              </div>
              {adminScanImages.length > 0 && (
                <div className="flex gap-2 flex-wrap">
                  {adminScanImages.map((f, i) => (
                    <div key={i} className="relative">
                      <img src={URL.createObjectURL(f)} alt="" className="w-20 h-20 object-cover rounded border" />
                      <button className="absolute -top-1.5 -right-1.5 rounded-full bg-rose-500 text-white p-0.5" onClick={() => setAdminScanImages(adminScanImages.filter((_, j) => j !== i))} data-testid={`admin-scan-remove-${i}`}>
                        <X size={12} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <p className="text-[10px] text-muted-foreground text-center">Cover, barcode, and clear-shot help AI accuracy.</p>
              <Button
                className="w-full bg-emerald-600 hover:bg-emerald-700"
                disabled={adminScanBusy || adminScanImages.length === 0}
                data-testid="admin-scan-submit"
                onClick={async () => {
                  setAdminScanBusy(true);
                  try {
                    const fd = new FormData();
                    adminScanImages.forEach(f => fd.append('images', f));
                    const r = await api.post(`/shipments/${selectedId}/scan-item`, fd, {
                      headers: { 'Content-Type': 'multipart/form-data' },
                    });
                    setAdminScanResult(r.data);
                  } catch (e) {
                    toast.error(e.response?.data?.detail || 'Scan failed');
                  } finally { setAdminScanBusy(false); }
                }}
              >
                {adminScanBusy ? <><Loader2 size={12} className="mr-1 animate-spin" /> Identifying…</> : <><Sparkles size={12} className="mr-1" /> Identify with AI</>}
              </Button>
            </div>
          ) : (
            <div className="space-y-2" data-testid="admin-scan-result">
              <div className="rounded-lg border p-3 space-y-1 bg-muted/30">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Identified</p>
                <p className="text-base font-semibold">{adminScanResult.name || 'Unknown'}</p>
                {adminScanResult.author && <p className="text-xs">by {adminScanResult.author}</p>}
                <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px] pt-1">
                  {adminScanResult.category && <span><b>Category:</b> {adminScanResult.category}</span>}
                  {adminScanResult.isbn && <span><b>ISBN:</b> {adminScanResult.isbn}</span>}
                  {adminScanResult.upc && <span><b>UPC:</b> {adminScanResult.upc}</span>}
                  <span><b>Weight:</b> {adminScanResult.weight_kg} kg</span>
                  <span><b>Value:</b> ~${adminScanResult.value_usd}</span>
                  {adminScanResult.source && <span><b>Source:</b> {adminScanResult.source}</span>}
                  {adminScanResult.ai_confidence && <span><b>Confidence:</b> <span className={`font-semibold ${adminScanResult.ai_confidence === 'high' ? 'text-emerald-700' : adminScanResult.ai_confidence === 'medium' ? 'text-amber-700' : 'text-rose-700'}`}>{adminScanResult.ai_confidence}</span></span>}
                </div>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" className="flex-1" onClick={() => { setAdminScanResult(null); setAdminScanImages([]); }} data-testid="admin-scan-again">Scan another</Button>
                <Button
                  className="flex-1 bg-emerald-600 hover:bg-emerald-700"
                  data-testid="admin-scan-add"
                  onClick={async () => {
                    try {
                      await api.post(`/shipments/${selectedId}/items`, {
                        name: adminScanResult.name || 'Unidentified',
                        category: adminScanResult.category || 'Other',
                        author: adminScanResult.author,
                        publisher: adminScanResult.publisher,
                        isbn: adminScanResult.isbn,
                        upc: adminScanResult.upc,
                        weight_kg: adminScanResult.weight_kg,
                        dims_cm: adminScanResult.dims_cm,
                        value_usd: adminScanResult.value_usd,
                        qty_needed: 1,
                        qty_acquired: 1,
                        photo_url: adminScanResult.photo_url,
                        image_urls: adminScanResult.image_urls || [],
                        priority: 'normal',
                        source: adminScanResult.source,
                        ai_confidence: adminScanResult.ai_confidence,
                      });
                      toast.success('Item added');
                      setShowAdminScan(false); setAdminScanImages([]); setAdminScanResult(null);
                      await refreshDetail();
                    } catch (e) { toast.error(e.response?.data?.detail || 'Add failed'); }
                  }}
                >
                  Add to shipment
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* iter 249 — BOX SCAN DIALOG: batch upload photos of labeled boxes.
          Different from AI Scan (single item) — this one reads the whole
          box: box number + item list, auto-creates boxes + items, and
          collapses "Personal Items" boxes into one Household Personal Item row. */}
      <Dialog open={showBoxScan} onOpenChange={(o) => { if (!o) { setShowBoxScan(false); setBoxScanImages([]); setBoxScanResult(null); } }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="box-scan-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Boxes size={18} className="text-emerald-600" /> Scan Boxes</DialogTitle>
            <DialogDescription>
              Upload photos of your labeled shipping boxes. AI reads the box number and item list written in marker,
              matches them to your shipment, and adds anything missing. Boxes marked &quot;Personal Items&quot; become a single
              &quot;Household Personal Item&quot; row. Values default to a conservative low-average estimate if none is on the box.
            </DialogDescription>
          </DialogHeader>

          {!boxScanResult ? (
            <div className="space-y-3">
              <div className="border-2 border-dashed rounded-lg p-4 text-center">
                <input
                  id="box-scan-file"
                  type="file"
                  accept="image/*"
                  multiple
                  className="hidden"
                  data-testid="box-scan-file"
                  onChange={(e) => {
                    const files = Array.from(e.target.files || []).slice(0, 20 - boxScanImages.length);
                    setBoxScanImages([...boxScanImages, ...files]);
                  }}
                />
                <label htmlFor="box-scan-file" className="cursor-pointer inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
                  <ImageIcon size={16} /> Tap to add photos ({boxScanImages.length}/20)
                </label>
              </div>
              {boxScanImages.length > 0 && (
                <div className="grid grid-cols-4 gap-2">
                  {boxScanImages.map((f, i) => (
                    <div key={i} className="relative">
                      <img src={URL.createObjectURL(f)} alt={`box ${i}`} className="rounded aspect-square object-cover w-full" />
                      <button className="absolute -top-1.5 -right-1.5 rounded-full bg-rose-500 text-white p-0.5" onClick={() => setBoxScanImages(boxScanImages.filter((_, j) => j !== i))} data-testid={`box-scan-remove-${i}`}>
                        <X size={11} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <Button
                className="w-full"
                disabled={boxScanBusy || boxScanImages.length === 0}
                data-testid="box-scan-submit"
                onClick={async () => {
                  setBoxScanBusy(true);
                  try {
                    const fd = new FormData();
                    boxScanImages.forEach(f => fd.append('images', f));
                    const res = await api.post(`/shipments/${selectedId}/scan-boxes`, fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 600000 });
                    setBoxScanResult(res.data);
                    await refreshDetail();
                  } catch (e) { toast.error(e.response?.data?.detail || 'Scan failed'); }
                  setBoxScanBusy(false);
                }}
              >
                {boxScanBusy ? <><Loader2 size={14} className="animate-spin mr-2" />Scanning… (10–40s per photo)</> : <><Sparkles size={14} className="mr-2" />Scan {boxScanImages.length} photo{boxScanImages.length !== 1 ? 's' : ''}</>}
              </Button>
            </div>
          ) : (
            <div className="space-y-3" data-testid="box-scan-result">
              <div className="grid grid-cols-4 gap-2 text-center text-sm">
                <div className="bg-emerald-50 rounded p-2"><div className="font-bold text-emerald-700">{boxScanResult.boxes_created}</div><div className="text-[10px] uppercase text-muted-foreground">New boxes</div></div>
                <div className="bg-blue-50 rounded p-2"><div className="font-bold text-blue-700">{boxScanResult.boxes_matched}</div><div className="text-[10px] uppercase text-muted-foreground">Matched boxes</div></div>
                <div className="bg-purple-50 rounded p-2"><div className="font-bold text-purple-700">{boxScanResult.items_added}</div><div className="text-[10px] uppercase text-muted-foreground">Items added</div></div>
                <div className="bg-amber-50 rounded p-2"><div className="font-bold text-amber-700">{boxScanResult.items_linked}</div><div className="text-[10px] uppercase text-muted-foreground">Items linked</div></div>
              </div>
              {(boxScanResult.errors || []).length > 0 && (
                <div className="bg-rose-50 border border-rose-200 rounded p-2 text-xs">
                  <div className="font-semibold text-rose-700 mb-1">{boxScanResult.errors.length} photo(s) failed:</div>
                  {boxScanResult.errors.map((e, i) => <div key={i} className="text-rose-600">Photo {e.photo_index + 1}: {e.error}</div>)}
                </div>
              )}
              <div className="max-h-64 overflow-y-auto border rounded divide-y">
                {(boxScanResult.results || []).map((r, i) => (
                  <div key={i} className="p-2 text-xs">
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <div className="font-semibold flex items-center gap-2">
                        Photo {r.photo_index + 1}
                        {r.box_number && <Badge variant="outline" className="text-[10px]">Box {r.box_number}</Badge>}
                        {r.is_personal && <Badge className="bg-purple-100 text-purple-700 text-[10px]">Personal</Badge>}
                        <Badge variant="outline" className={`text-[10px] ${r.confidence === 'high' ? 'text-emerald-700 border-emerald-300' : r.confidence === 'low' ? 'text-amber-700 border-amber-300' : ''}`}>{r.confidence}</Badge>
                      </div>
                      {r.matched_box_name && <span className="text-muted-foreground truncate">{r.matched_box_name}</span>}
                    </div>
                    {r.items.length > 0 && (
                      <ul className="mt-1 space-y-0.5">
                        {r.items.map((it, j) => (
                          <li key={j} className="flex items-center justify-between gap-2">
                            <span>{it.action === 'added' ? '➕' : '🔗'} {it.name} <span className="text-muted-foreground">× {it.qty}</span></span>
                            <span className="text-muted-foreground">${it.value_usd}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                    {r.notes && <div className="text-muted-foreground italic mt-1">{r.notes}</div>}
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                {boxScanResult.scan_run_id && (
                  // iter 250 — undo the entire run in one tap. Server rolls back
                  // added items + boxes and reverses qty bumps on linked items.
                  <Button
                    variant="outline"
                    className="text-rose-700 border-rose-300 hover:bg-rose-50"
                    onClick={async () => {
                      if (!window.confirm('Revert the whole scan? Every item and box created here will be removed and any qty bumps undone.')) return;
                      try {
                        const r = await api.post(`/shipments/${selectedId}/scan-runs/${boxScanResult.scan_run_id}/revert`);
                        toast.success(`Reverted: ${r.data.items_removed} items, ${r.data.boxes_removed} boxes, ${r.data.items_unlinked} unlinked`);
                        setShowBoxScan(false); setBoxScanImages([]); setBoxScanResult(null);
                        await refreshDetail();
                      } catch (e) { toast.error(e.response?.data?.detail || 'Revert failed'); }
                    }}
                    data-testid="box-scan-undo"
                  >
                    Undo this scan
                  </Button>
                )}
                <Button variant="outline" className="flex-1" onClick={() => { setBoxScanResult(null); setBoxScanImages([]); }} data-testid="box-scan-again">Scan more</Button>
                <Button className="flex-1" onClick={() => { setShowBoxScan(false); setBoxScanImages([]); setBoxScanResult(null); }} data-testid="box-scan-done">Done</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>


      {/* URL estimate dialog */}
      <Dialog open={!!linkUrlFor} onOpenChange={(o) => { if (!o) setLinkUrlFor(null); }}>
        <DialogContent className="max-w-md" data-testid="ship-link-dialog">
          <DialogHeader>
            <DialogTitle>Product link · AI estimate</DialogTitle>
            <DialogDescription className="text-xs">
              Paste an Amazon/Walmart/eBay/Home Depot URL and Gemini will estimate weight, dimensions, and value.
              Or tap <strong>Find link (AI)</strong> and Gemini will pick the best retailer + search query for you.
            </DialogDescription>
          </DialogHeader>
          {linkUrlFor && (
            <div className="space-y-2 mt-2">
              <Input value={linkUrlFor.url} onChange={e => setLinkUrlFor({ ...linkUrlFor, url: e.target.value })}
                placeholder="https://www.amazon.com/dp/B0..." data-testid="ship-link-url" />
              <p className="text-[10px] text-muted-foreground">Estimate takes ~10–15s · search URLs always resolve · ASIN/SKU deep-links may rot.</p>
              <div className="grid grid-cols-3 gap-2 pt-1">
                <Button variant="ghost" onClick={() => setLinkUrlFor(null)}>Cancel</Button>
                <Button variant="outline" disabled={linkBusyId === linkUrlFor.itemId} onClick={() => findLinkAi(linkUrlFor.itemId)} data-testid="ship-link-find-ai">
                  🤖 Find link
                </Button>
                <Button disabled={linkBusyId === linkUrlFor.itemId || !linkUrlFor.url} onClick={() => estimateFromLink(linkUrlFor.itemId, linkUrlFor.url)} data-testid="ship-link-submit">
                  {linkBusyId === linkUrlFor.itemId ? 'Working…' : 'Estimate'}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Pack dialog — mark N units as packed for shipping */}
      <Dialog open={!!packDialogFor} onOpenChange={(o) => { if (!o) setPackDialogFor(null); }}>
        <DialogContent className="max-w-sm" data-testid="ship-pack-dialog">
          <DialogHeader>
            <DialogTitle>Pack item</DialogTitle>
            <DialogDescription className="text-xs">
              {packDialogFor?.item?.name} — <strong>{packDialogFor?.item?.qty_acquired || 0} acquired</strong>, <strong>{packDialogFor?.item?.qty_packed || 0} already packed</strong>.
              Packing is INDEPENDENT of acquired count — the difference stays home or ships next trip.
            </DialogDescription>
          </DialogHeader>
          {packDialogFor && (
            <div className="space-y-3 mt-2">
              <div className="space-y-1">
                <Label className="text-xs">Quantity to pack</Label>
                <Input type="number" min="1" defaultValue={Math.max(1, (packDialogFor.item.qty_acquired || 0) - (packDialogFor.item.qty_packed || 0))}
                  onChange={e => setPackDialogFor({ ...packDialogFor, qty: parseInt(e.target.value) || 1 })}
                  data-testid="ship-pack-qty" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Transport mode</Label>
                <Select defaultValue={packDialogFor.item.transport_mode || 'container'}
                  onValueChange={v => setPackDialogFor({ ...packDialogFor, mode: v })}>
                  <SelectTrigger data-testid="ship-pack-mode"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="container">🚢 Container (sea)</SelectItem>
                    <SelectItem value="suitcase">🧳 Suitcase (air)</SelectItem>
                    <SelectItem value="holdback">⏸ Hold-back (stays home)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex gap-2 pt-1">
                <Button variant="ghost" className="flex-1" onClick={() => setPackDialogFor(null)}>Cancel</Button>
                <Button className="flex-1" data-testid="ship-pack-submit" onClick={async () => {
                  const qty = packDialogFor.qty || Math.max(1, (packDialogFor.item.qty_acquired || 0) - (packDialogFor.item.qty_packed || 0));
                  const mode = packDialogFor.mode || packDialogFor.item.transport_mode || 'container';
                  try {
                    const r = await api.post(`/shipments/${selectedId}/items/${packDialogFor.item.id}/pack`, { qty, mode });
                    if (r.data.over_packed) toast.warning(`Over-packed: ${r.data.qty_packed}/${r.data.qty_acquired} for "${packDialogFor.item.name}"`);
                    else toast.success(`Packed ${qty} → ${mode}`);
                    setPackDialogFor(null);
                    await refreshDetail();
                  } catch (e) { toast.error(e.response?.data?.detail || 'Pack failed'); }
                }}>Pack</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
    </PackingDndProvider>
  );
}

function emptyItem() {
  return {
    name: '', category: '', qty_needed: 1, qty_acquired: 0,
    weight_kg: 0, value_usd: 0, priority: 'normal',
    dims_cm: { length: 0, width: 0, height: 0 },
    notes: '', photo_url: '', condition: 'used',
  };
}


// iter 252 — Recent Scans sidebar. Lists the last N scan-runs on a shipment
// with a per-row Revert button so a mis-scan from 20 minutes ago is one tap
// to fix. Silent (returns null) when there's nothing to show, so the
// shipment detail stays clean on brand-new shipments.
function RecentScans({ shipmentId, refreshDetail }) {
  const [runs, setRuns] = React.useState([]);

  const reload = React.useCallback(async () => {
    if (!shipmentId) return;
    try {
      const r = await api.get(`/shipments/${shipmentId}/scan-runs`);
      setRuns(r.data || []);
    } catch {
      setRuns([]);
    }
  }, [shipmentId]);

  React.useEffect(() => { reload(); }, [reload]);

  const revert = async (runId) => {
    if (!window.confirm('Revert this scan? Items and boxes it created will be removed and any qty bumps undone.')) return;
    try {
      const r = await api.post(`/shipments/${shipmentId}/scan-runs/${runId}/revert`);
      toast.success(`Reverted: ${r.data.items_removed} items, ${r.data.boxes_removed} boxes`);
      await Promise.all([reload(), refreshDetail?.()]);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Revert failed');
    }
  };

  if (!runs.length) return null;

  return (
    <div className="mb-3" data-testid="ship-recent-scans">
      <div className="flex items-center gap-1.5 mb-1.5">
        <Sparkles size={12} className="text-emerald-600" />
        <p className="text-xs font-semibold">Recent Scans ({runs.length})</p>
        <span className="text-[10px] text-muted-foreground">— revert an entire batch in one click</span>
      </div>
      <div className="divide-y border rounded-md">
        {runs.slice(0, 6).map(r => {
          const when = r.created_at ? new Date(r.created_at).toLocaleString() : '—';
          const reverted = !!r.reverted;
          return (
            <div key={r.id} className={`px-3 py-2 flex items-center gap-2 text-xs flex-wrap ${reverted ? 'opacity-50 line-through' : ''}`} data-testid={`recent-scan-${r.id}`}>
              <span className="font-mono text-[10px] text-muted-foreground">{r.id.slice(-8)}</span>
              <span>{when}</span>
              <span className="text-muted-foreground">by {r.created_by_name || '—'}</span>
              <Badge variant="outline" className="text-[10px]">{r.photos_processed || 0} photo{r.photos_processed === 1 ? '' : 's'}</Badge>
              <Badge variant="outline" className="text-[10px] text-emerald-700 border-emerald-300">+{r.boxes_created || 0} box{r.boxes_created === 1 ? '' : 'es'}</Badge>
              <Badge variant="outline" className="text-[10px] text-purple-700 border-purple-300">+{r.items_added || 0} items</Badge>
              {r.items_linked > 0 && <Badge variant="outline" className="text-[10px] text-amber-700 border-amber-300">🔗 {r.items_linked} linked</Badge>}
              {reverted && <Badge variant="outline" className="text-[10px] text-rose-700 border-rose-300 no-underline">REVERTED</Badge>}
              {!reverted && (
                <Button
                  size="sm" variant="ghost"
                  className="ml-auto h-6 text-[10px] text-rose-700 hover:bg-rose-50 no-underline"
                  onClick={() => revert(r.id)}
                  data-testid={`recent-scan-revert-${r.id}`}
                >
                  Revert
                </Button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
