import React, { useState, useEffect } from 'react';
import { Package, Plus, Trash2, Edit2, Search, Filter, BookOpen, CheckCircle, CalendarDays, Settings } from 'lucide-react';
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
import { locationsApi, bookingsApi, resourcesApi } from '../services/api';
import { toast } from 'sonner';

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
};

export default function ResourcesPage() {
  const [resources, setResources] = useState([]);
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [locationFilter, setLocationFilter] = useState('all');
  const [showBooking, setShowBooking] = useState(false);
  const [bookingResource, setBookingResource] = useState(null);
  const [bookingForm, setBookingForm] = useState({ title: '', date: '', start_time: '09:00', end_time: '10:00', notes: '' });
  const [bookings, setBookings] = useState([]);
  const [mainTab, setMainTab] = useState('resources');
  const [resourceTypes, setResourceTypes] = useState(RESOURCE_TYPES);
  const [showTypeManager, setShowTypeManager] = useState(false);
  const [newTypeName, setNewTypeName] = useState('');

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
      if (typRes.data?.length > 0) setResourceTypes(typRes.data.map(t => ({ value: t.name, label: t.label, id: t.id })));
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
    });
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        ...form,
        capacity: form.capacity ? parseInt(form.capacity) : null,
        quantity: parseInt(form.quantity) || 1,
        hourly_rate: form.hourly_rate ? parseFloat(form.hourly_rate) : null,
        location_id: form.location_id || null,
      };
      if (editing) {
        await api.put(`/resources/${editing.id}`, payload);
        setResources(prev => prev.map(r => r.id === editing.id ? { ...r, ...payload } : r));
        toast.success('Resource updated!');
      } else {
        const res = await api.post('/resources', payload);
        setResources(prev => [...prev, res.data]);
        toast.success('Resource added!');
      }
      setShowModal(false);
    } catch { toast.error('Failed to save'); }
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
    if (locationFilter !== 'all' && r.location_id !== locationFilter) return false;
    return true;
  });

  const byType = RESOURCE_TYPES.map(t => ({ ...t, count: resources.filter(r => r.type === t.value).length }));

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
        <Select value={locationFilter} onValueChange={setLocationFilter}>
          <SelectTrigger className="w-40 h-8 text-xs"><SelectValue placeholder="All Locations" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Locations</SelectItem>
            {locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {/* Resources Grid */}
      {loading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1,2,3,4,5,6].map(i => <div key={i} className="h-36 bg-muted animate-pulse rounded-xl" />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-sm text-muted-foreground">
          <Package size={40} className="mx-auto mb-3 opacity-30" />
          {search || typeFilter !== 'all' || locationFilter !== 'all' ? 'No matching resources.' : 'No resources added yet.'}
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map(r => (
            <Card key={r.id} className="shadow-soft rounded-xl hover:shadow-md transition-shadow" data-testid="resource-card">
              <CardContent className="p-4">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <p className="font-semibold text-sm">{r.name}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{getLocationName(r.location_id)}</p>
                  </div>
                  <div className="flex gap-1">
                    {r.is_bookable && (
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-primary" title="Book" onClick={() => { setBookingResource(r); setShowBooking(true); }} data-testid="book-resource-btn"><CalendarDays size={12} /></Button>
                    )}
                    <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground" onClick={() => openEdit(r)}><Edit2 size={12} /></Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={() => deleteResource(r.id)}><Trash2 size={12} /></Button>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1 mb-2">
                  <Badge variant="outline" className="text-xs capitalize">{RESOURCE_TYPES.find(t => t.value === r.type)?.label || r.type}</Badge>
                  {r.is_bookable && <Badge variant="outline" className="text-xs bg-green-50 text-green-700 border-green-200 dark:bg-green-950 dark:text-green-300">Bookable</Badge>}
                  {r.staff_only && <Badge variant="outline" className="text-xs bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300">Staff Only</Badge>}
                  {!r.is_bookable && <Badge variant="outline" className="text-xs bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-900 dark:text-slate-300">Not Bookable</Badge>}
                  {r.is_consumable && <Badge variant="outline" className="text-xs">Consumable</Badge>}
                </div>
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
                    {RESOURCE_TYPES.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Location</Label>
                <Select value={form.location_id || '_none'} onValueChange={v => setForm({...form, location_id: v === '_none' ? '' : v})}>
                  <SelectTrigger><SelectValue placeholder="Select location" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_none">Unassigned</SelectItem>
                    {locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-2"><Label>Quantity</Label>
                <Input type="number" min="1" value={form.quantity} onChange={e => setForm({...form, quantity: e.target.value})} />
              </div>
              <div className="space-y-2"><Label>Capacity</Label>
                <Input type="number" min="0" placeholder="Optional" value={form.capacity} onChange={e => setForm({...form, capacity: e.target.value})} />
              </div>
              <div className="space-y-2"><Label>Hourly Rate</Label>
                <Input type="number" min="0" step="0.01" placeholder="0.00" value={form.hourly_rate} onChange={e => setForm({...form, hourly_rate: e.target.value})} />
              </div>
            </div>
            <div className="space-y-2"><Label>Description</Label>
              <Textarea rows={2} placeholder="Describe this resource" value={form.description} onChange={e => setForm({...form, description: e.target.value})} />
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
    </div>
  );
}
