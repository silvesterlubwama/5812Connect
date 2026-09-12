import React, { useState, useEffect } from 'react';
import { Package, Plus, Trash2, Edit2, Search, Filter, BookOpen, CheckCircle, CalendarDays, Settings, Barcode, Printer } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Switch } from '../components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Textarea } from '../components/ui/textarea';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { locationsApi, bookingsApi, resourcesApi } from '../services/api';
import BarcodeLabelDialog from '../components/BarcodeLabelDialog';
import BulkBarcodeLabelDialog from '../components/BulkBarcodeLabelDialog';
import { toast } from 'sonner';
import { BulkActionBar, exportToCSV, SelectCheckbox } from '../components/BulkActions';

const RESOURCE_TYPES = [
  { value: 'venue', label: 'Venue' },
  { value: 'sports_equipment', label: 'Sports Equipment' },
  { value: 'media_equipment', label: 'Media Equipment' },
  { value: 'educational', label: 'Educational Material' },
  { value: 'consumable', label: 'Consumable Material' },
  { value: 'room', label: 'Room/Space' },
];

const emptyForm = {
  name: '', type: 'room', category: '', capacity: '', quantity: 1, description: '',
  location_id: '', hourly_rate: '', is_bookable: true, staff_only: false, is_consumable: false,
  unit: '', reorder_level: '',
};

export default function ResourcesPage() {
  const { user } = useAuth();
  const canIssueBarcodes = (() => {
    const r = (user?.role || '').toLowerCase();
    return ['admin', 'system_admin', 'executive director', 'director', 'adviser'].includes(r);
  })();
  const activeCampus = localStorage.getItem('5812_active_campus') || user?.location_id || '';
  const [resources, setResources] = useState([]);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [search, setSearch] = useState('');
  const [showStock, setShowStock] = useState(false);
  const [stockResource, setStockResource] = useState(null);
  const [stockMap, setStockMap] = useState({});
  const [typeFilter, setTypeFilter] = useState('all');
  // iter-resource-kind-tabs: separate the "kind" (bookable vs consumable
  // vs static asset) from the type dropdown (room/laptop/car/…). Users
  // now filter by kind with a tab strip, and by type via the stat-card grid.
  const [kindFilter, setKindFilter] = useState('all'); // all | bookable | consumable | unbookable
  const [showBooking, setShowBooking] = useState(false);
  const [bookingResource, setBookingResource] = useState(null);
  const [barcodeResource, setBarcodeResource] = useState(null);
  const [bulkBarcodeOpen, setBulkBarcodeOpen] = useState(false);
  const [bookingForm, setBookingForm] = useState({ title: '', date: '', start_time: '09:00', end_time: '10:00', notes: '' });
  const [bookings, setBookings] = useState([]);
  const [mainTab, setMainTab] = useState('resources');
  const [resourceTypes, setResourceTypes] = useState(RESOURCE_TYPES);
  const [showTypeManager, setShowTypeManager] = useState(false);
  const [newTypeName, setNewTypeName] = useState('');
  const [showSheetUpload, setShowSheetUpload] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [resRes, locRes, typRes] = await Promise.all([
        api.get('/resources'),
        locationsApi.list(),
        resourcesApi.types(),
      ]);
      setResources(resRes.data);
      setLocations(locRes.data);
      // Merge fetched types on top of built-in defaults so custom types added
      // via the Type Manager become selectable immediately (dedupe by `value`).
      const fetched = (typRes.data || []).map(t => ({ value: t.name, label: t.label, id: t.id }));
      const byVal = new Map();
      [...RESOURCE_TYPES, ...fetched].forEach(t => { byVal.set(t.value, { ...(byVal.get(t.value) || {}), ...t }); });
      setResourceTypes(Array.from(byVal.values()));
      // Load stock for all consumables in parallel
      const consumables = (resRes.data || []).filter(r => r.is_consumable);
      const stockResults = await Promise.all(consumables.map(r => resourcesApi.stock(r.id).catch(() => null)));
      const smap = {};
      consumables.forEach((r, i) => { if (stockResults[i]?.data) smap[r.id] = stockResults[i].data; });
      setStockMap(smap);
    } catch { toast.error('Failed to load resources'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchData(); }, []);

  const fetchBookings = async () => {
    try {
      const res = await bookingsApi.list({});
      setBookings(res.data || []);
    } catch (e) { console.warn(e.message || e); }
  };

  useEffect(() => { fetchBookings(); }, []);

  const openAdd = () => { setEditing(null); setForm(emptyForm); setShowModal(true); };
  const openEdit = (r) => {
    setEditing(r);
    setForm({
      name: r.name || '', type: r.type || 'room', category: r.category || '',
      capacity: r.capacity || '', quantity: r.quantity || 1, description: r.description || '',
      location_id: r.location_id || '', hourly_rate: r.hourly_rate || '',
      is_bookable: r.is_bookable !== false, staff_only: r.staff_only || false,
      is_consumable: r.is_consumable || false,
      unit: r.unit || '', reorder_level: r.reorder_level || '',
      serving_conversions: r.serving_conversions || [],
    });
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.location_id) { toast.error('Pick a campus / location'); return; }
    setSaving(true);
    try {
      // iter 285 — only send fields that apply to the resource kind. Consumables
      // don't carry hourly_rate/mac/manufacturer/model/is_bookable; bookable
      // gear doesn't carry unit/reorder_level/serving_conversions. Empty ""
      // strings are collapsed to null so Pydantic doesn't reject int fields.
      const isCons = !!form.is_consumable;
      const clean = {
        name: form.name.trim(),
        type: form.type,
        category: form.category || null,
        quantity: parseInt(form.quantity) || 1,
        description: form.description || null,
        location_id: form.location_id || null,
        serial_number: form.serial_number || null,
      };
      if (isCons) {
        Object.assign(clean, {
          is_consumable: true,
          is_bookable: false,
          staff_only: false,
          unit: form.unit || null,
          reorder_level: form.reorder_level ? parseFloat(form.reorder_level) : null,
          serving_conversions: form.serving_conversions || [],
        });
      } else {
        Object.assign(clean, {
          is_consumable: false,
          is_bookable: !!form.is_bookable,
          staff_only: !!form.staff_only,
          capacity: form.capacity ? parseInt(form.capacity) : null,
          hourly_rate: form.hourly_rate ? parseFloat(form.hourly_rate) : null,
          mac_address: form.mac_address || null,
          manufacturer: form.manufacturer || null,
          model: form.model || null,
        });
      }
      if (editing) {
        await api.put(`/resources/${editing.id}`, clean);
        setResources(prev => prev.map(r => r.id === editing.id ? { ...r, ...clean } : r));
        toast.success('Resource updated!');
      } else {
        const res = await api.post('/resources', clean);
        setResources(prev => [...prev, res.data]);
        toast.success('Resource added!');
      }
      setShowModal(false);
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail[0]?.msg || 'Validation failed' : 'Failed to save');
    }
    finally { setSaving(false); }
  };

  const deleteResource = async (id) => {
    if (!window.confirm('Delete this resource?')) return;
    await api.delete(`/resources/${id}`);
    setResources(prev => prev.filter(r => r.id !== id));
    toast.success('Deleted');
  };

  const getLocationName = (lid) => locations.find(l => l.id === lid)?.name || 'Unassigned';

  const filtered = resources.filter(r => {
    if (search && !r.name.toLowerCase().includes(search.toLowerCase())) return false;
    if (typeFilter !== 'all' && r.type !== typeFilter) return false;
    if (kindFilter === 'bookable' && !(r.is_bookable && !r.is_consumable)) return false;
    if (kindFilter === 'consumable' && !r.is_consumable) return false;
    if (kindFilter === 'unbookable' && (r.is_bookable || r.is_consumable)) return false;
    return true;
  });

  const kindCounts = {
    all: resources.length,
    bookable: resources.filter(r => r.is_bookable && !r.is_consumable).length,
    consumable: resources.filter(r => r.is_consumable).length,
    unbookable: resources.filter(r => !r.is_bookable && !r.is_consumable).length,
  };

  const allFilteredSelected = filtered.length > 0 && filtered.every(r => selectedIds.has(r.id));
  const someFilteredSelected = filtered.some(r => selectedIds.has(r.id));
  const toggleSelectAll = () => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (allFilteredSelected) filtered.forEach(r => next.delete(r.id));
      else filtered.forEach(r => next.add(r.id));
      return next;
    });
  };

  const byType = resourceTypes.map(t => ({ ...t, count: resources.filter(r => r.type === t.value).length }));

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading" data-testid="resources-title">Resources</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{resources.length} total resources across {locations.length} locations</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setShowTypeManager(true)}>Resource Types</Button>
          <Button className="gap-2" onClick={openAdd} data-testid="add-resource-btn"><Plus size={16} /> Add Resource</Button>
        </div>
      </div>

      {/* Type Stats */}
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
        {byType.map(t => (
          <Card key={t.value} className={`shadow-soft rounded-xl cursor-pointer transition-all ${typeFilter === t.value ? 'ring-2 ring-primary' : ''}`} onClick={() => setTypeFilter(typeFilter === t.value ? 'all' : t.value)}>
            <CardContent className="p-3 text-center">
              <p className="text-lg font-bold">{t.count}</p>
              <p className="text-xs text-muted-foreground">{t.label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input className="pl-9 h-8 text-xs" placeholder="Search resources..." value={search} onChange={e => setSearch(e.target.value)} data-testid="resource-search" />
        </div>
        {/* Kind tabs: All / Bookable / Consumable / Unbookable */}
        <div className="inline-flex rounded-lg border bg-muted/40 p-0.5 text-xs" data-testid="resource-kind-tabs">
          {[
            { v: 'all', label: 'All' },
            { v: 'bookable', label: 'Bookable' },
            { v: 'consumable', label: 'Consumable' },
            { v: 'unbookable', label: 'Unbookable' },
          ].map(t => (
            <button
              key={t.v}
              onClick={() => setKindFilter(t.v)}
              className={`px-3 py-1 rounded-md font-medium transition-colors ${kindFilter === t.v ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
              data-testid={`resource-kind-tab-${t.v}`}
            >
              {t.label} <span className="ml-1 text-[10px] opacity-60">({kindCounts[t.v]})</span>
            </button>
          ))}
        </div>
        {/* Select-all — visible only when there are rows to select */}
        {filtered.length > 0 && (
          <label className="inline-flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer" data-testid="resource-select-all">
            <input
              type="checkbox"
              className="accent-primary"
              checked={allFilteredSelected}
              ref={el => { if (el) el.indeterminate = !allFilteredSelected && someFilteredSelected; }}
              onChange={toggleSelectAll}
            />
            Select all ({filtered.length})
          </label>
        )}
      </div>

      {/* Resources Grid */}
      {loading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1,2,3,4,5,6].map(i => <div key={i} className="h-36 bg-muted animate-pulse rounded-xl" />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-sm text-muted-foreground">
          <Package size={40} className="mx-auto mb-3 opacity-30" />
          {search || typeFilter !== 'all' || kindFilter !== 'all' ? 'No matching resources.' : 'No resources added yet.'}
        </div>
      ) : (
        <div>
          {selectedIds.size > 0 && <div className="mb-3 flex items-center gap-2 flex-wrap">
            <BulkActionBar selectedIds={selectedIds} onClear={() => setSelectedIds(new Set())} onBulkExport={() => exportToCSV(filtered.filter(r => selectedIds.has(r.id)), 'resources-export.csv')} onBulkDelete={async () => { if (!window.confirm(`Delete ${selectedIds.size} resources?`)) return; for (const id of selectedIds) { try { await resourcesApi.delete(id); } catch (e) { console.warn(e.message || e); } } setSelectedIds(new Set()); fetchData(); toast.success('Deleted'); }} />
            <Button size="sm" variant="outline" className="gap-1.5 h-8 text-xs" onClick={() => setBulkBarcodeOpen(true)} data-testid="bulk-barcode-print-btn">
              <Barcode size={13} /> Print Barcodes ({Array.from(selectedIds).filter(id => filtered.find(r => r.id === id)?.serial_number).length})
            </Button>
          </div>}
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map(r => (
            <Card key={r.id} className={`shadow-soft rounded-xl hover:shadow-md transition-shadow ${selectedIds.has(r.id) ? 'ring-2 ring-primary/40' : ''}`} data-testid="resource-card">
              <CardContent className="p-4">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-start gap-2">
                    <input type="checkbox" className="accent-primary mt-1" checked={selectedIds.has(r.id)} onChange={() => setSelectedIds(prev => { const n = new Set(prev); n.has(r.id) ? n.delete(r.id) : n.add(r.id); return n; })} />
                    <div>
                      <p className="font-semibold text-sm">{r.name}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">{getLocationName(r.location_id)}</p>
                    </div>
                  </div>
                  <div className="flex gap-1">
                    {r.is_consumable && (
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-blue-600" title="Log usage / restock" onClick={() => { setStockResource(r); setShowStock(true); }} data-testid={`log-usage-${r.id}`}><Package size={12} /></Button>
                    )}
                    {r.is_bookable && (
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-primary" title="Book" onClick={() => { setBookingResource(r); setShowBooking(true); }} data-testid="book-resource-btn"><CalendarDays size={12} /></Button>
                    )}
                    <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground" onClick={() => openEdit(r)}><Edit2 size={12} /></Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={() => deleteResource(r.id)}><Trash2 size={12} /></Button>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1 mb-2">
                  <Badge variant="outline" className="text-xs capitalize">{resourceTypes.find(t => t.value === r.type)?.label || r.type}</Badge>
                  {r.is_bookable && <Badge variant="outline" className="text-xs bg-green-50 text-green-700 border-green-200 dark:bg-green-950 dark:text-green-300">Bookable</Badge>}
                  {r.staff_only && <Badge variant="outline" className="text-xs bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300">Staff Only</Badge>}
                  {!r.is_bookable && <Badge variant="outline" className="text-xs bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-900 dark:text-slate-300">Not Bookable</Badge>}
                  {r.is_consumable && <Badge variant="outline" className="text-xs">Consumable</Badge>}
                  {r.is_consumable && stockMap[r.id] != null && (
                    <Badge variant="outline" className={`text-xs ${stockMap[r.id].low_stock ? 'bg-red-50 text-red-700 border-red-200' : 'bg-blue-50 text-blue-700 border-blue-200'}`} data-testid={`stock-badge-${r.id}`}>
                      {stockMap[r.id].on_hand} {stockMap[r.id].unit || ''}{stockMap[r.id].low_stock ? ' · LOW' : ''}
                    </Badge>
                  )}
                </div>
                {r.serial_number && (
                  <div className="flex items-center justify-between gap-2 mb-2 p-1.5 rounded bg-muted/50">
                    <code className="font-mono text-[10px] truncate flex-1" title={r.serial_number}>{r.serial_number}</code>
                    <Button size="sm" variant="ghost" className="h-6 px-2 text-[10px] gap-1" title="Print barcode label" onClick={() => setBarcodeResource(r)} data-testid={`print-resource-barcode-${r.id}`}>
                      <Barcode size={10} /> Label
                    </Button>
                  </div>
                )}
                {!r.serial_number && canIssueBarcodes && (
                  <Button size="sm" variant="outline" className="h-6 text-[10px] w-full mb-2 gap-1" onClick={async () => {
                    if (!r.location_id) {
                      toast.error('Set a location on this resource first — the barcode prefix derives from its campus, not yours.');
                      return;
                    }
                    try {
                      const res = await resourcesApi.generateSerial(r.id);
                      toast.success(`Serial issued: ${res.data.serial_number}`);
                      fetchData();
                    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
                  }} data-testid={`generate-serial-${r.id}`}>
                    <Barcode size={10} /> Issue 58:12 Serial Number
                  </Button>
                )}
                {!r.serial_number && !canIssueBarcodes && (
                  <p className="text-[10px] text-muted-foreground italic mb-2">No barcode — admin/director can issue one</p>
                )}
                {r.is_consumable && (
                  <div className="flex items-center gap-1 mb-2">
                    <Button size="sm" variant="outline" className="h-7 text-[10px] flex-1 gap-1" onClick={async () => {
                      const month = window.prompt('Month for tracking sheet (YYYY-MM):', new Date().toISOString().slice(0,7));
                      if (!month) return;
                      const url = resourcesApi.trackingSheetUrl(r.id, month);
                      // Auth is via bearer token — fetch the HTML then render it
                      // into a hidden iframe and print. A post-fetch
                      // window.open() is outside the click gesture and gets
                      // silently blocked, which is why printing never happened.
                      try {
                        const { secureStorage } = await import('../services/secureStorage');
                        const { fetchAndPrint } = await import('../utils/printHtml');
                        toast.info('Preparing sheet…');
                        await fetchAndPrint(url, secureStorage.getToken());
                      } catch (err) {
                        toast.error('Failed: ' + (err?.message || err));
                      }
                    }} data-testid={`tracking-sheet-btn-${r.id}`}>
                      <Printer size={10} /> Print Sheet
                    </Button>
                    <Button size="sm" variant="outline" className="h-7 text-[10px] flex-1 gap-1" onClick={() => { setStockResource(r); setShowSheetUpload(true); }} data-testid={`upload-sheet-btn-${r.id}`}>
                      <Package size={10} /> Upload Sheet
                    </Button>
                  </div>
                )}
                {r.is_consumable && (
                  <SheetHistory resourceId={r.id} />
                )}
                {r.description && <p className="text-xs text-muted-foreground line-clamp-2">{r.description}</p>}
                <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                  {r.quantity > 1 && <span>Qty: {r.quantity}</span>}
                  {r.capacity && <span>Cap: {r.capacity}</span>}
                  {r.hourly_rate && <span>Rate: {r.hourly_rate}/hr</span>}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
        </div>
      )}

      {/* Add/Edit Dialog */}
      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit Resource' : 'Add Resource'}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Name *</Label>
              <Input placeholder="Resource name" value={form.name} onChange={e => setForm({...form, name: e.target.value})} required data-testid="resource-name-input" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Type</Label>
                <Select value={form.type} onValueChange={v => setForm({...form, type: v, is_consumable: v === 'consumable'})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {resourceTypes.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Location <span className="text-destructive">*</span></Label>
                <Select value={form.location_id || ''} onValueChange={v => setForm({...form, location_id: v})}>
                  <SelectTrigger data-testid="resource-location-select"><SelectValue placeholder="Required — picks barcode prefix" /></SelectTrigger>
                  <SelectContent>
                    {locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}{l.country ? ` (${l.country})` : ''}</SelectItem>)}
                  </SelectContent>
                </Select>
                {form.location_id && (() => {
                  const loc = locations.find(l => l.id === form.location_id);
                  if (!loc) return null;
                  return <p className="text-[10px] text-muted-foreground">Barcode prefix will derive from <span className="font-mono">{loc.name} ({loc.country || '—'})</span></p>;
                })()}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-2"><Label>Quantity</Label>
                <Input type="number" min="1" value={form.quantity} onChange={e => setForm({...form, quantity: e.target.value})} />
              </div>
              {!form.is_consumable && (
                <>
                  <div className="space-y-2"><Label>Capacity</Label>
                    <Input type="number" min="0" placeholder="Optional" value={form.capacity} onChange={e => setForm({...form, capacity: e.target.value})} />
                  </div>
                  <div className="space-y-2"><Label>Hourly Rate</Label>
                    <Input type="number" min="0" step="0.01" placeholder="0.00" value={form.hourly_rate} onChange={e => setForm({...form, hourly_rate: e.target.value})} />
                  </div>
                </>
              )}
              {form.is_consumable && (
                <>
                  <div className="space-y-2"><Label>Base unit *</Label>
                    <Input placeholder="kg, liter, bar" value={form.unit} onChange={e => setForm({...form, unit: e.target.value})} data-testid="resource-unit-input" />
                  </div>
                  <div className="space-y-2"><Label>Reorder level</Label>
                    <Input type="number" min="0" step="any" placeholder="Alert threshold" value={form.reorder_level} onChange={e => setForm({...form, reorder_level: e.target.value})} />
                  </div>
                </>
              )}
            </div>
            <div className="space-y-2"><Label>Description</Label>
              <Textarea rows={2} placeholder="Describe this resource" value={form.description} onChange={e => setForm({...form, description: e.target.value})} />
            </div>
            {!form.is_consumable && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Label>Serial Number / Barcode</Label>
                    <div className="flex gap-1">
                      <Input className="font-mono text-xs" placeholder="Auto-issued if empty" value={form.serial_number || ''} onChange={e => setForm({...form, serial_number: e.target.value})} data-testid="resource-serial-input" />
                      {!form.serial_number && (
                        <span className="text-[10px] text-muted-foreground self-center px-1" title="Will auto-generate 5812-XXX serial">auto</span>
                      )}
                    </div>
                    <p className="text-[10px] text-muted-foreground">Format: <span className="font-mono">5812-{`<COUNTRY><LOC>-<DDMMYY>-<NNNN>`}</span></p>
                  </div>
                  <div className="space-y-2"><Label>MAC Address</Label><Input placeholder="AA:BB:CC:DD:EE:FF" value={form.mac_address || ''} onChange={e => setForm({...form, mac_address: e.target.value})} /></div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2"><Label>Manufacturer</Label><Input placeholder="e.g. Dell, Apple" value={form.manufacturer || ''} onChange={e => setForm({...form, manufacturer: e.target.value})} /></div>
                  <div className="space-y-2"><Label>Model</Label><Input placeholder="e.g. XPS 15" value={form.model || ''} onChange={e => setForm({...form, model: e.target.value})} /></div>
                </div>
                <div className="space-y-3 p-3 border border-border rounded-lg">
                  <div className="flex items-center justify-between">
                    <div><p className="text-sm font-medium">Bookable</p>
                      <p className="text-xs text-muted-foreground">Can this resource be booked?</p></div>
                    <Switch checked={form.is_bookable} onCheckedChange={v => setForm({...form, is_bookable: v})} data-testid="resource-bookable-toggle" />
                  </div>
                  {form.is_bookable && (
                    <div className="flex items-center justify-between">
                      <div><p className="text-sm font-medium">Staff Only</p>
                        <p className="text-xs text-muted-foreground">Only staff can book (not public)</p></div>
                      <Switch checked={form.staff_only} onCheckedChange={v => setForm({...form, staff_only: v})} data-testid="resource-staffonly-toggle" />
                    </div>
                  )}
                </div>
              </>
            )}
            {form.is_consumable && (
              <div className="space-y-2 p-3 border border-border rounded-lg">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium">Serving Conversions</p>
                  <Button type="button" size="sm" variant="ghost" onClick={() => setForm({ ...form, serving_conversions: [...(form.serving_conversions || []), { unit: '', per_base: 0.5, base: form.unit || 'kg' }] })} data-testid="add-conversion-btn"><Plus size={12} /></Button>
                </div>
                <p className="text-[10px] text-muted-foreground">1 serving unit ≈ X base units — used for sheet uploads. Empty falls back to defaults (rice 2 UG cups/kg, posho 3, soap 4 quarters/bar).</p>
                {(form.serving_conversions || []).map((c, i) => (
                  <div key={i} className="grid grid-cols-12 gap-1 items-center">
                    <Input className="col-span-4 h-7 text-xs" placeholder="Unit (e.g. Ugandan cup)" value={c.unit} onChange={e => setForm({ ...form, serving_conversions: form.serving_conversions.map((x, j) => j === i ? { ...x, unit: e.target.value } : x) })} data-testid={`conv-unit-${i}`} />
                    <span className="col-span-1 text-[10px] text-center">= 1</span>
                    <Input className="col-span-3 h-7 text-xs" type="number" min="0" step="any" placeholder="Per base" value={c.per_base} onChange={e => setForm({ ...form, serving_conversions: form.serving_conversions.map((x, j) => j === i ? { ...x, per_base: parseFloat(e.target.value) || 0 } : x) })} />
                    <Input className="col-span-3 h-7 text-xs" placeholder="Base (kg/liter/bar)" value={c.base} onChange={e => setForm({ ...form, serving_conversions: form.serving_conversions.map((x, j) => j === i ? { ...x, base: e.target.value } : x) })} />
                    <Button type="button" size="sm" variant="ghost" className="col-span-1 h-7 w-7 p-0 text-destructive" onClick={() => setForm({ ...form, serving_conversions: form.serving_conversions.filter((_, j) => j !== i) })}><Trash2 size={12} /></Button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowModal(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving} data-testid="save-resource-btn">
                {saving ? 'Saving...' : editing ? 'Update' : 'Add Resource'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Booking Dialog */}
      <Dialog open={showBooking} onOpenChange={setShowBooking}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Book: {bookingResource?.name}</DialogTitle>
            <DialogDescription>1-hour buffer is enforced between bookings</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Booking Title *</Label>
              <Input placeholder="e.g. Team meeting" value={bookingForm.title} onChange={e => setBookingForm({...bookingForm, title: e.target.value})} data-testid="booking-title-input" />
            </div>
            <div className="space-y-2"><Label>Date *</Label>
              <Input type="date" value={bookingForm.date} onChange={e => setBookingForm({...bookingForm, date: e.target.value})} data-testid="booking-date-input" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Start Time</Label>
                <Input type="time" value={bookingForm.start_time} onChange={e => setBookingForm({...bookingForm, start_time: e.target.value})} />
              </div>
              <div className="space-y-2"><Label>End Time</Label>
                <Input type="time" value={bookingForm.end_time} onChange={e => setBookingForm({...bookingForm, end_time: e.target.value})} />
              </div>
            </div>
            <div className="space-y-2"><Label>Notes</Label>
              <Input placeholder="Additional details" value={bookingForm.notes} onChange={e => setBookingForm({...bookingForm, notes: e.target.value})} />
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowBooking(false)}>Cancel</Button>
              <Button className="flex-1" disabled={!bookingForm.title || !bookingForm.date} data-testid="confirm-booking-btn" onClick={async () => {
                try {
                  await bookingsApi.create({
                    resource_id: bookingResource?.id,
                    location_id: bookingResource?.location_id,
                    ...bookingForm,
                  });
                  toast.success('Booked!');
                  setShowBooking(false);
                  setBookingForm({ title: '', date: '', start_time: '09:00', end_time: '10:00', notes: '' });
                  fetchBookings();
                } catch (err) {
                  toast.error(err.response?.data?.detail || 'Booking failed');
                }
              }}>Confirm Booking</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Resource Type Manager */}
      <Dialog open={showTypeManager} onOpenChange={setShowTypeManager}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Manage Resource Types</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            {resourceTypes.map(t => (
              <div key={t.value || t.id} className="flex items-center justify-between p-2 rounded border border-border">
                <span className="text-sm font-medium">{t.label}</span>
                {t.id && <Button size="sm" variant="ghost" className="text-destructive h-7" onClick={async () => { try { await resourcesApi.deleteType(t.id); setResourceTypes(prev => prev.filter(rt => rt.id !== t.id)); toast.success('Deleted'); } catch { toast.error('Failed'); } }}><Trash2 size={13} /></Button>}
              </div>
            ))}
            <div className="flex gap-2 pt-2 border-t border-border">
              <Input placeholder="New resource type" value={newTypeName} onChange={e => setNewTypeName(e.target.value)} className="flex-1" />
              <Button size="sm" onClick={async () => { if (!newTypeName.trim()) return; try { const r = await resourcesApi.createType({ name: newTypeName, label: newTypeName }); setResourceTypes(prev => [...prev, { value: r.data.name, label: r.data.label, id: r.data.id }]); setNewTypeName(''); toast.success('Added'); } catch { toast.error('Failed'); } }} disabled={!newTypeName.trim()}>Add</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Barcode label dialog */}
      <BarcodeLabelDialog
        resource={barcodeResource ? { ...barcodeResource, location_name: getLocationName(barcodeResource.location_id) } : null}
        open={!!barcodeResource}
        onOpenChange={(o) => { if (!o) setBarcodeResource(null); }}
      />

      {/* Bulk barcode print dialog */}
      <BulkBarcodeLabelDialog
        open={bulkBarcodeOpen}
        onOpenChange={setBulkBarcodeOpen}
        title="Print Resource Barcodes"
        items={Array.from(selectedIds)
          .map(id => filtered.find(r => r.id === id))
          .filter(r => r && r.serial_number)
          .map(r => ({ name: r.name, code: r.serial_number, location_name: getLocationName(r.location_id) }))}
      />

      <StockDialog
        open={showStock} onOpenChange={setShowStock}
        resource={stockResource}
        onDone={() => { setShowStock(false); fetchData(); }}
      />

      <SheetUploadDialog
        open={showSheetUpload} onOpenChange={setShowSheetUpload}
        resource={stockResource}
        onDone={() => { setShowSheetUpload(false); fetchData(); }}
      />
    </div>
  );
}

// Consumable stock adjustment dialog — in/out with reason picker (event/child/department)
function SheetHistory({ resourceId }) {
  const [sheets, setSheets] = useState([]);
  React.useEffect(() => {
    let cancelled = false;
    resourcesApi.listTrackingSheets(resourceId)
      .then(r => { if (!cancelled) setSheets((r.data || []).slice(0, 2)); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [resourceId]);
  if (sheets.length === 0) return null;
  return (
    <div className="mb-2 border-l-2 border-emerald-200 pl-2 py-1 space-y-0.5" data-testid={`sheet-history-${resourceId}`}>
      <p className="text-[9px] font-semibold text-emerald-700 uppercase tracking-wide">Recent Sheets</p>
      {sheets.map(s => (
        <p key={s.id} className="text-[10px] text-muted-foreground truncate" title={`${s.total_servings} ${s.serving_unit} = ${s.base_qty} ${s.base_unit} · ${s.filled_by || '—'}`}>
          <span className="font-mono">{s.month || s.uploaded_at?.slice(0, 7)}</span> · {s.total_servings} {s.serving_unit} → {s.base_qty} {s.base_unit}
        </p>
      ))}
    </div>
  );
}

function StockDialog({ open, onOpenChange, resource, onDone }) {
  const [tab, setTab] = useState('out');
  const [qty, setQty] = useState('');
  const [note, setNote] = useState('');
  const [q, setQ] = useState('');
  const [picker, setPicker] = useState({ events: [], children: [], departments: [] });
  const [ref, setRef] = useState(null);
  const [movements, setMovements] = useState([]);
  const [stock, setStock] = useState(null);
  const [busy, setBusy] = useState(false);

  React.useEffect(() => {
    if (!open || !resource) return;
    setTab('out'); setQty(''); setNote(''); setRef(null); setQ('');
    resourcesApi.stock(resource.id).then(r => setStock(r.data)).catch(() => setStock(null));
    resourcesApi.movements(resource.id, { limit: 20 }).then(r => setMovements(r.data || []));
    resourcesApi.consumablesLookup('').then(r => setPicker(r.data));
  }, [open, resource]);

  React.useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => resourcesApi.consumablesLookup(q).then(r => setPicker(r.data)).catch(() => {}), 250);
    return () => clearTimeout(t);
  }, [q, open]);

  const submit = async () => {
    if (!resource) return;
    const n = parseFloat(qty);
    if (!(n > 0)) { toast.error('Enter a quantity > 0'); return; }
    setBusy(true);
    try {
      await resourcesApi.adjust(resource.id, {
        type: tab, qty: n, location_id: resource.location_id,
        consumer_ref: ref || undefined, note: note || undefined,
      });
      toast.success(tab === 'out' ? `Logged ${n} used` : `Restocked ${n}`);
      onDone?.();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };

  const combined = [
    ...(picker.events || []).map(e => ({ ...e, group: 'Events' })),
    ...(picker.children || []).map(c => ({ ...c, group: 'Children' })),
    ...(picker.departments || []).map(d => ({ ...d, group: 'Departments' })),
  ];

  if (!resource) return null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto" data-testid="stock-dialog">
        <DialogHeader>
          <DialogTitle>{resource.name}</DialogTitle>
          <DialogDescription>
            On hand: <strong>{stock?.on_hand ?? '…'}</strong> {stock?.unit || 'unit'}
            {stock?.low_stock && <span className="ml-2 text-red-600 font-semibold">· LOW STOCK</span>}
          </DialogDescription>
        </DialogHeader>
        <div className="flex border rounded overflow-hidden text-sm">
          <button className={`flex-1 py-1.5 ${tab === 'out' ? 'bg-primary text-primary-foreground' : ''}`} onClick={() => setTab('out')} data-testid="stock-tab-out">Log usage</button>
          <button className={`flex-1 py-1.5 ${tab === 'in' ? 'bg-primary text-primary-foreground' : ''}`} onClick={() => setTab('in')} data-testid="stock-tab-in">Restock</button>
        </div>
        <div className="space-y-2">
          <div><Label>Quantity</Label><Input type="number" min="0" step="any" value={qty} onChange={e => setQty(e.target.value)} data-testid="stock-qty" /></div>
          {tab === 'out' && (
            <div>
              <Label>Given to / Used for</Label>
              <Input placeholder="Search events, children, departments…" value={q} onChange={e => setQ(e.target.value)} data-testid="stock-search" />
              <div className="max-h-40 overflow-y-auto border rounded mt-1 divide-y">
                {combined.map(item => (
                  <button key={`${item.kind}-${item.id}`} type="button" className={`w-full text-left px-2 py-1 text-xs hover:bg-accent ${ref?.id === item.id && ref?.kind === item.kind ? 'bg-accent' : ''}`}
                    onClick={() => setRef({ kind: item.kind, id: item.id, label: item.label })} data-testid={`stock-pick-${item.kind}-${item.id}`}>
                    <span className="text-[10px] uppercase text-muted-foreground mr-1">{item.kind}</span>{item.label}
                  </button>
                ))}
                {!combined.length && <p className="p-2 text-xs text-muted-foreground text-center">No matches</p>}
              </div>
              {ref && <p className="text-xs text-muted-foreground mt-1">Selected: <strong>{ref.label}</strong></p>}
            </div>
          )}
          <div><Label>Note (optional)</Label><Textarea rows={2} value={note} onChange={e => setNote(e.target.value)} /></div>
        </div>
        <div className="flex gap-2 pt-2"><Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button><div className="flex-1" /><Button onClick={submit} disabled={busy} data-testid="stock-submit">{busy ? 'Saving…' : (tab === 'out' ? 'Log usage' : 'Add stock')}</Button></div>
        <div className="pt-3 border-t border-border">
          <p className="text-xs font-semibold mb-1">Recent movements</p>
          <div className="max-h-32 overflow-y-auto space-y-1">
            {movements.map(m => (
              <div key={m.id} className="text-[11px] flex items-center gap-2">
                <span className={m.type === 'out' ? 'text-red-600' : 'text-green-600'}>{m.type === 'out' ? '−' : '+'}{m.qty}</span>
                <span className="text-muted-foreground">{m.at}</span>
                {m.consumer_ref?.label && <span className="truncate">→ {m.consumer_ref.label}</span>}
                {m.note && <span className="text-muted-foreground truncate">· {m.note}</span>}
              </div>
            ))}
            {!movements.length && <p className="text-xs text-muted-foreground">No history yet</p>}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}


// Upload a filled tracking sheet — total servings × conversion → auto-decrement stock
function SheetUploadDialog({ open, onOpenChange, resource, onDone }) {
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [total, setTotal] = useState('');
  const [servingUnit, setServingUnit] = useState('');
  const [filledBy, setFilledBy] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [convs, setConvs] = useState([]);

  React.useEffect(() => {
    if (!open || !resource) return;
    setMonth(new Date().toISOString().slice(0, 7));
    setTotal(''); setNote(''); setFilledBy('');
    // Pull the resource's serving_conversions (or fall back to defaults)
    api.get(`/resources/${resource.id}`).then(r => {
      const c = r.data?.serving_conversions || [];
      setConvs(c);
      setServingUnit(c[0]?.unit || '');
    }).catch(() => { setConvs([]); setServingUnit(''); });
  }, [open, resource]);

  const submit = async () => {
    const n = parseFloat(total);
    if (!(n > 0)) { toast.error('Enter total servings > 0'); return; }
    if (!servingUnit) { toast.error('Pick a serving unit'); return; }
    setBusy(true);
    try {
      const r = await resourcesApi.uploadTrackingSheet(resource.id, {
        month, total_servings: n, serving_unit: servingUnit,
        note, filled_by: filledBy,
      });
      toast.success(`Recorded ${r.data.movement.qty} ${r.data.movement.qty > 1 ? '' : ''}${resource.unit || 'unit'}(s) used · on hand: ${r.data.on_hand}`);
      onDone?.();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };

  if (!resource) return null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="sheet-upload-dialog">
        <DialogHeader>
          <DialogTitle>Upload Tracking Sheet — {resource.name}</DialogTitle>
          <DialogDescription>Enter the total from the printed sheet — we convert servings → {resource.unit || 'base unit'} and decrement stock.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <div><Label>Month</Label><Input type="month" value={month} onChange={e => setMonth(e.target.value)} data-testid="sheet-month" /></div>
          <div className="grid grid-cols-2 gap-2">
            <div><Label>Total servings</Label><Input type="number" min="0" step="any" value={total} onChange={e => setTotal(e.target.value)} data-testid="sheet-total" /></div>
            <div>
              <Label>Serving unit</Label>
              <Select value={servingUnit} onValueChange={setServingUnit}>
                <SelectTrigger data-testid="sheet-serving-unit"><SelectValue placeholder="Pick unit" /></SelectTrigger>
                <SelectContent>
                  {convs.length === 0 && <SelectItem value="Ugandan cup">Ugandan cup (default)</SelectItem>}
                  {convs.map((c, i) => <SelectItem key={i} value={c.unit}>{c.unit} — 1 {c.unit} ≈ {c.per_base} {c.base}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div><Label>Filled by (caregiver initials)</Label><Input value={filledBy} onChange={e => setFilledBy(e.target.value)} data-testid="sheet-filled-by" /></div>
          <div><Label>Notes</Label><Textarea rows={2} value={note} onChange={e => setNote(e.target.value)} /></div>
          {convs.length === 0 && (
            <p className="text-[11px] text-amber-700">No custom conversions on this resource — we&apos;ll try the field defaults (rice 2 cups/kg, posho 3 cups/kg, soap 4 quarters/bar).  You can set exact conversions under Resources → Edit → Serving conversions.</p>
          )}
        </div>
        <div className="flex gap-2 pt-2"><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><div className="flex-1" /><Button onClick={submit} disabled={busy} data-testid="sheet-submit">{busy ? 'Uploading…' : 'Post & decrement stock'}</Button></div>
      </DialogContent>
    </Dialog>
  );
}

