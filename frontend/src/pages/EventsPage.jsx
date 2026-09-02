import React, { useState, useEffect, useCallback } from 'react';
import { Plus, Calendar, Clock, MapPin, Users, Search, Trash2, Eye, RefreshCw, Copy, Lock, Globe, Tag, DollarSign, Download } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Card, CardContent } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Switch } from '../components/ui/switch';
import { eventsApi, checkinsApi, locationsApi, venuesApi, locationVenuesApi } from '../services/api';
import api from '../services/api';
import { BulkActionBar, exportToCSV, SelectCheckbox } from '../components/BulkActions';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

const statusColors = { upcoming: 'bg-blue-100 text-blue-700 border-blue-200', completed: 'bg-green-100 text-green-700 border-green-200', cancelled: 'bg-red-100 text-red-700 border-red-200' };

export default function EventsPage() {
  const { user } = useAuth();
  const activeCampus = localStorage.getItem('5812_active_campus') || user?.location_id || '';
  const isGlobalView = !activeCampus;
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [visFilter, setVisFilter] = useState('all');
  const [showAdd, setShowAdd] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [eventDetail, setEventDetail] = useState(null);
  const [saving, setSaving] = useState(false);
  const [eventTypes, setEventTypes] = useState([]);
  const [locations, setLocations] = useState([]);
  const [locationVenues, setLocationVenues] = useState([]);
  const [showTypeManager, setShowTypeManager] = useState(false);
  const [newTypeName, setNewTypeName] = useState('');
  const [newTypeColor, setNewTypeColor] = useState('#6366f1');
  const [editingEvent, setEditingEvent] = useState(null);
  const emptyEvent = { title: '', type: 'meeting', date: '', end_date: '', time: '', end_time: '', location: '', location_id: activeCampus, venue_id: '', capacity: 100, description: '', is_public: false, is_free: true, price: '', visibility: 'internal', is_recurring: false, recurrence_pattern: '', recurrence_type: 'weekly', recurrence_interval: 1, recurrence_end_date: '', recurrence_day: 1, recurrence_days_of_week: [], recurrence_week_of_month: null, occurrences: 12, country: '', ticket_tiers: [], waitlist_enabled: true };
  const [newEvent, setNewEvent] = useState({ ...emptyEvent });
  const [selectedIds, setSelectedIds] = useState(new Set());

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    try {
      const res = await eventsApi.list({ search: search || undefined, type: typeFilter !== 'all' ? typeFilter : undefined, visibility: visFilter !== 'all' ? visFilter : undefined });
      setEvents(res.data);
    } catch { toast.error('Failed to load events'); }
    finally { setLoading(false); }
  }, [search, typeFilter, visFilter]);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  useEffect(() => {
    eventsApi.types().then(r => setEventTypes(r.data)).catch(() => {});
    locationsApi.list().then(r => setLocations(r.data)).catch(() => {});
  }, []);

  const loadVenues = async (locId) => {
    if (!locId) { setLocationVenues([]); return []; }
    try {
      const r = await locationVenuesApi.get(locId);
      const combined = [...(r.data.venues || []), ...(r.data.sublocations || []).map(s => ({ id: s.id, name: s.name, type: 'sublocation' }))];
      setLocationVenues(combined);
      return combined;
    } catch (e) { console.warn(e.message || e); setLocationVenues([]); return []; }
  };

  // Get country from location
  const getLocationCountry = (locId) => {
    const loc = locations.find(l => l.id === locId);
    return loc?.country || '';
  };

  const upcoming = events.filter(e => e.status === 'upcoming');
  const past = events.filter(e => e.status !== 'upcoming');

  const handleAdd = async (e) => {
    e.preventDefault(); setSaving(true);
    try {
      // iter 265 — strip helper-only fields the backend doesn't accept before sending.
      const { recurrence_type, occurrences, end_date, ...eventFields } = newEvent;
      const payload = { ...eventFields, price: newEvent.price ? parseFloat(newEvent.price) : undefined, capacity: parseInt(newEvent.capacity) };
      if (!payload.price) delete payload.price;
      // iter 265 — multi-day span: attach end_date if the user picked one.
      if (end_date && end_date !== newEvent.date) payload.end_date = end_date;
      const res = editingEvent ? await eventsApi.update(editingEvent.id, payload) : await eventsApi.create(payload);
      // iter 265 — auto-fire generate-recurring when the event is created
      // WITH is_recurring=true. Previously the recurrence fields were
      // stored on the parent event but no follow-up dates were created,
      // so "recurring" events only ever showed up once.
      if (!editingEvent && newEvent.is_recurring) {
        try {
          const pattern = recurrence_type === 'nth_weekday' ? 'nth_week' : (recurrence_type || 'weekly');
          const dayMap = { sunday: 6, monday: 0, tuesday: 1, wednesday: 2, thursday: 3, friday: 4, saturday: 5 };
          const dow = typeof newEvent.recurrence_pattern === 'string' && dayMap[newEvent.recurrence_pattern.toLowerCase()] !== undefined
            ? dayMap[newEvent.recurrence_pattern.toLowerCase()] : 0;
          await eventsApi.generateRecurring({
            title: payload.title,
            type: payload.type,
            location: payload.location,
            location_id: payload.location_id,
            venue_id: payload.venue_id,
            time: payload.time,
            end_time: payload.end_time,
            start_date: payload.date,
            end_date: payload.end_date,
            pattern,
            interval: newEvent.recurrence_interval || 1,
            occurrences: Math.max(1, Math.min(52, newEvent.occurrences || 12)),
            day_of_week: dow,
            nth_week: newEvent.recurrence_day || 1,
            capacity: payload.capacity,
            is_public: payload.is_public,
            visibility: payload.visibility,
            description: payload.description,
          });
          toast.success(`Recurring series generated`);
        } catch (rerr) { toast.error(rerr.response?.data?.detail || 'Recurring series failed'); }
      }
      if (editingEvent) {
        setEvents(prev => prev.map(ev => ev.id === editingEvent.id ? res.data : ev));
        toast.success('Event updated');
      } else {
        // Refresh to include recurring children
        fetchEvents();
        toast.success(`Event "${res.data.title}" created!`);
      }
      setShowAdd(false); setEditingEvent(null); setNewEvent({ ...emptyEvent });
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to save event'); }
    finally { setSaving(false); }
  };

  const duplicateEvent = async (event) => {
    try {
      const res = await eventsApi.duplicate(event.id);
      setEvents(prev => [res.data, ...prev]);
      toast.success(`Duplicated as "${res.data.title}"`);
    } catch { toast.error('Failed to duplicate'); }
  };

  const editEvent = async (event) => {
    setEditingEvent(event);
    setNewEvent({ title: event.title, type: event.type || 'service', date: event.date || '', time: event.time || '', end_time: event.end_time || '', location: event.location || '', location_id: event.location_id || '', venue_id: event.venue_id || '', capacity: event.capacity || 100, description: event.description || '', is_public: event.is_public ?? true, is_free: event.is_free ?? true, price: event.price || '', visibility: event.visibility || 'external', is_recurring: event.is_recurring ?? false, recurrence_pattern: event.recurrence_pattern || '', recurrence_day: event.recurrence_day || 1, country: event.country || getLocationCountry(event.location_id), ticket_tiers: event.ticket_tiers || [], waitlist_enabled: event.waitlist_enabled ?? true });
    if (event.location_id) await loadVenues(event.location_id);
    setShowAdd(true);
  };

  const viewEvent = async (event) => {
    setSelectedEvent(event);
    try { const res = await eventsApi.get(event.id); setEventDetail(res.data); } catch { setEventDetail(event); }
  };

  const deleteEvent = async (event) => {
    if (!window.confirm(`Delete "${event.title}"?`)) return;
    try { await eventsApi.delete(event.id); setEvents(prev => prev.filter(e => e.id !== event.id)); toast.success('Event deleted'); } catch { toast.error('Failed to delete'); }
  };

  const updateStatus = async (event, newStatus) => {
    try { await eventsApi.update(event.id, { status: newStatus }); setEvents(prev => prev.map(e => e.id === event.id ? { ...e, status: newStatus } : e)); toast.success('Status updated'); } catch { toast.error('Failed to update'); }
  };

  const addEventType = async () => {
    if (!newTypeName.trim()) return;
    try { const r = await eventsApi.createType({ name: newTypeName, label: newTypeName, color: newTypeColor }); setEventTypes(prev => [...prev, r.data]); setNewTypeName(''); toast.success('Type added'); } catch { toast.error('Failed to add type'); }
  };

  const deleteEventType = async (id) => {
    try { await eventsApi.deleteType(id); setEventTypes(prev => prev.filter(t => t.id !== id)); toast.success('Type deleted'); } catch { toast.error('Failed to delete type'); }
  };

  const formatDate = (d) => new Date(d).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
  const typeColorMap = Object.fromEntries(eventTypes.map(t => [t.name, t.color]));

  const EventCard = ({ event }) => (
    <Card data-testid={`event-card-${event.id}`} className={`shadow-soft rounded-xl hover:shadow-soft-lg transition-shadow ${selectedIds.has(event.id) ? 'ring-2 ring-primary/40' : ''}`}>
      <CardContent className="p-5">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2">
            <SelectCheckbox id={event.id} checked={selectedIds.has(event.id)} onChange={() => setSelectedIds(prev => { const next = new Set(prev); next.has(event.id) ? next.delete(event.id) : next.add(event.id); return next; })} />
            <div className="flex flex-wrap gap-1.5">
            <span className="text-xs px-2 py-0.5 rounded-full font-medium capitalize" style={{ backgroundColor: (typeColorMap[event.type] || '#6366f1') + '22', color: typeColorMap[event.type] || '#6366f1' }}>{event.type}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium border capitalize ${statusColors[event.status] || ''}`}>{event.status}</span>
            </div>
          </div>
          <div className="flex gap-1">
            {event.visibility === 'internal' ? <Lock size={13} className="text-amber-500" /> : <Globe size={13} className="text-green-500" />}
            {!event.is_free && <DollarSign size={13} className="text-orange-500" />}
          </div>
        </div>
        <h3 className="font-semibold text-base mb-3">{event.title}</h3>
        <div className="space-y-1.5 text-sm text-muted-foreground mb-4">
          <div className="flex items-center gap-2"><Calendar size={13} /><span>{formatDate(event.date)}</span></div>
          <div className="flex items-center gap-2"><Clock size={13} /><span>{event.time}{event.end_time ? ` – ${event.end_time}` : ''}</span></div>
          {event.venue_name && <div className="flex items-center gap-2"><MapPin size={13} className="text-primary/70" /><span className="truncate font-medium">{event.venue_name}</span></div>}
          {event.location && !event.venue_name && <div className="flex items-center gap-2"><MapPin size={13} /><span className="truncate">{event.location}</span></div>}
          {event.end_date && event.end_date !== event.date && <div className="flex items-center gap-2 text-xs"><Calendar size={11} /><span className="text-primary">Ends {formatDate(event.end_date)}</span></div>}
          <div className="flex items-center gap-2">
            <Users size={13} />
            <span>{event.registered ?? 0}/{event.capacity}</span>
            <div className="flex-1 bg-muted rounded-full h-1.5 ml-1"><div className="bg-primary h-1.5 rounded-full" style={{ width: `${Math.min(((event.registered ?? 0) / event.capacity) * 100, 100)}%` }} /></div>
          </div>
        </div>
        {!event.is_free && event.price && <p className="text-sm font-medium text-primary mb-3">UGX {event.price?.toLocaleString()}</p>}
        <div className="flex gap-1.5">
          <Button data-testid={`event-view-${event.id}`} size="sm" variant="outline" className="flex-1" onClick={() => viewEvent(event)}><Eye size={13} className="mr-1" />View</Button>
          <Button size="sm" variant="ghost" onClick={() => editEvent(event)} title="Edit"><Tag size={13} /></Button>
          <Button data-testid={`event-duplicate-${event.id}`} size="sm" variant="ghost" onClick={() => duplicateEvent(event)} title="Duplicate"><Copy size={13} /></Button>
          <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => deleteEvent(event)}><Trash2 size={13} /></Button>
        </div>
      </CardContent>
    </Card>
  );

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Events</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{events.length} total · {upcoming.length} upcoming</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setShowTypeManager(true)}>Event Types</Button>
          <Button variant="outline" size="sm" onClick={fetchEvents}><RefreshCw size={14} /></Button>
          <Button data-testid="create-event-btn" onClick={() => { setEditingEvent(null); setNewEvent({ ...emptyEvent }); setShowAdd(true); }} className="gap-2"><Plus size={16} /> Create Event</Button>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input data-testid="event-search" placeholder="Search events..." className="pl-9" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-full sm:w-40"><SelectValue placeholder="Type" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            {eventTypes.map(t => <SelectItem key={t.id} value={t.name}>{t.label}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={visFilter} onValueChange={setVisFilter}>
          <SelectTrigger className="w-full sm:w-40"><SelectValue placeholder="Visibility" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="internal">Internal</SelectItem>
            <SelectItem value="external">External</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Select All + Bulk Action Bar */}
      <div className="flex items-center gap-3">
        <label className="flex items-center gap-2 text-xs cursor-pointer">
          <input type="checkbox" className="accent-primary" checked={selectedIds.size > 0 && selectedIds.size === events.length} onChange={() => selectedIds.size === events.length ? setSelectedIds(new Set()) : setSelectedIds(new Set(events.map(e => e.id)))} data-testid="select-all-events" />
          Select All ({events.length})
        </label>
      </div>
      <BulkActionBar selectedIds={selectedIds} onClear={() => setSelectedIds(new Set())}
        onBulkDelete={async () => {
          if (!window.confirm(`Delete ${selectedIds.size} events?`)) return;
          try { await eventsApi.bulkDelete([...selectedIds]); toast.success('Deleted'); setSelectedIds(new Set()); fetchEvents(); }
          catch (e) { toast.error(e.message || 'Failed'); }
        }}
        onBulkExport={async () => {
          try { const res = await eventsApi.bulkExport([...selectedIds]); exportToCSV(res.data, 'events-export.csv'); toast.success('Exported!'); }
          catch (e) { toast.error(e.message || 'Failed'); }
        }}
      />

      {loading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">{[...Array(6)].map((_, i) => <div key={i} className="h-56 bg-card border border-border rounded-xl animate-pulse" />)}</div>
      ) : (
        <Tabs defaultValue="upcoming">
          <TabsList><TabsTrigger value="upcoming">Upcoming ({upcoming.length})</TabsTrigger><TabsTrigger value="past">Past ({past.length})</TabsTrigger></TabsList>
          <TabsContent value="upcoming" className="mt-4">
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">{upcoming.map(e => <EventCard key={e.id} event={e} />)}</div>
            {upcoming.length === 0 && <div className="text-center py-12 text-muted-foreground"><Calendar size={40} className="mx-auto mb-3 opacity-30" /><p>No upcoming events</p><Button variant="outline" className="mt-4" onClick={() => setShowAdd(true)}>Create an event</Button></div>}
          </TabsContent>
          <TabsContent value="past" className="mt-4">
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">{past.map(e => <EventCard key={e.id} event={e} />)}</div>
            {past.length === 0 && <p className="text-center py-10 text-muted-foreground">No past events</p>}
          </TabsContent>
        </Tabs>
      )}

      {/* Add/Edit Event Dialog */}
      <Dialog open={showAdd} onOpenChange={v => { if (!v) { setShowAdd(false); setEditingEvent(null); } }}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editingEvent ? 'Edit Event' : 'Create New Event'}</DialogTitle></DialogHeader>
          <form onSubmit={handleAdd} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Event Title *</Label><Input data-testid="event-title-input" placeholder="Event name" value={newEvent.title} onChange={e => setNewEvent({...newEvent, title: e.target.value})} required /></div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2"><Label>Type</Label>
                <Select value={newEvent.type} onValueChange={v => setNewEvent({...newEvent, type: v})}><SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{eventTypes.map(t => <SelectItem key={t.id} value={t.name}>{t.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Visibility</Label>
                <Select value={newEvent.visibility} onValueChange={v => setNewEvent({...newEvent, visibility: v})}><SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="external">External (Public)</SelectItem><SelectItem value="internal">Internal Only</SelectItem></SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-2"><Label>Date *</Label><Input type="date" value={newEvent.date} onChange={e => setNewEvent({...newEvent, date: e.target.value, end_date: newEvent.end_date && newEvent.end_date < e.target.value ? e.target.value : newEvent.end_date})} required /></div>
              <div className="space-y-2"><Label>End Date (multi-day, optional)</Label><Input type="date" min={newEvent.date} value={newEvent.end_date || ''} onChange={e => setNewEvent({...newEvent, end_date: e.target.value})} data-testid="event-end-date" /></div>
              <div className="space-y-2"><Label>Start</Label><Input type="time" value={newEvent.time} onChange={e => setNewEvent({...newEvent, time: e.target.value})} /></div>
              <div className="space-y-2"><Label>End</Label><Input type="time" value={newEvent.end_time} onChange={e => setNewEvent({...newEvent, end_time: e.target.value})} /></div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2"><Label>Location</Label>
                <Select value={newEvent.location_id || '_none'} onValueChange={v => { const lid = v === '_none' ? '' : v; const country = getLocationCountry(lid); setNewEvent({...newEvent, location_id: lid, venue_id: '', country}); loadVenues(lid); }}>
                  <SelectTrigger><SelectValue placeholder="Select location" /></SelectTrigger>
                  <SelectContent><SelectItem value="_none">-- Select --</SelectItem>{locations.filter(l => !activeCampus || l.id === activeCampus || l.parent_id === activeCampus).map(l => <SelectItem key={l.id} value={l.id}>{l.name} {l.country ? `(${l.country})` : ''}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Venue / Sub-location</Label>
                <Select value={newEvent.venue_id || '_none'} onValueChange={v => { const vid = v === '_none' ? '' : v; const vn = locationVenues.find(lv => lv.id === vid); setNewEvent({...newEvent, venue_id: vid, location: vn ? vn.name : newEvent.location}); }}>
                  <SelectTrigger><SelectValue placeholder="Select venue" /></SelectTrigger>
                  <SelectContent><SelectItem value="_none">-- Select --</SelectItem>{locationVenues.map(v => <SelectItem key={v.id} value={v.id}>{v.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            {!newEvent.location_id && <div className="space-y-2"><Label>Or type location</Label><Input placeholder="Custom location" value={newEvent.location} onChange={e => setNewEvent({...newEvent, location: e.target.value})} /></div>}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2"><Label>Capacity</Label><Input type="number" value={newEvent.capacity} onChange={e => setNewEvent({...newEvent, capacity: e.target.value})} /></div>
            </div>
            <div className="space-y-2"><Label>Description</Label><Input placeholder="Brief description" value={newEvent.description} onChange={e => setNewEvent({...newEvent, description: e.target.value})} /></div>
            <div className="flex items-center justify-between p-3 rounded-lg border border-border">
              <div><p className="text-sm font-medium">Public Event</p><p className="text-xs text-muted-foreground">Visible on public bookings page</p></div>
              <Switch checked={newEvent.is_public} onCheckedChange={v => setNewEvent({...newEvent, is_public: v})} />
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg border border-border">
              <div><p className="text-sm font-medium">Free Event</p><p className="text-xs text-muted-foreground">No payment required</p></div>
              <Switch checked={newEvent.is_free} onCheckedChange={v => setNewEvent({...newEvent, is_free: v})} />
            </div>
            {!newEvent.is_free && <div className="space-y-2"><Label>Price (UGX)</Label><Input type="number" placeholder="25000" value={newEvent.price} onChange={e => setNewEvent({...newEvent, price: e.target.value})} /></div>}

            {/* Ticket Tiers (Odoo-style multi-tier pricing) */}
            <div className="space-y-2 p-3 rounded-lg border border-border">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">Ticket Tiers <span className="text-xs text-muted-foreground font-normal">(optional — overrides base price)</span></p>
                  <p className="text-xs text-muted-foreground">e.g. Early Bird, Regular, VIP — each with its own price &amp; capacity</p>
                </div>
                <Button type="button" size="sm" variant="outline" onClick={() => setNewEvent({...newEvent, ticket_tiers: [...(newEvent.ticket_tiers || []), { id: `tier_${Date.now().toString(36)}`, name: '', price: 0, capacity: 0, sold: 0, description: '' }]})} data-testid="add-tier-btn">+ Add Tier</Button>
              </div>
              {(newEvent.ticket_tiers || []).map((t, idx) => (
                <div key={t.id || idx} className="grid grid-cols-12 gap-2 items-end pt-2 border-t" data-testid={`tier-row-${idx}`}>
                  <div className="col-span-4 space-y-1">
                    <Label className="text-[10px]">Name</Label>
                    <Input className="h-8 text-xs" placeholder="Early Bird" value={t.name || ''} onChange={e => { const tiers = [...newEvent.ticket_tiers]; tiers[idx] = {...t, name: e.target.value}; setNewEvent({...newEvent, ticket_tiers: tiers}); }} />
                  </div>
                  <div className="col-span-3 space-y-1">
                    <Label className="text-[10px]">Price</Label>
                    <Input className="h-8 text-xs" type="number" value={t.price ?? 0} onChange={e => { const tiers = [...newEvent.ticket_tiers]; tiers[idx] = {...t, price: parseFloat(e.target.value) || 0}; setNewEvent({...newEvent, ticket_tiers: tiers}); }} />
                  </div>
                  <div className="col-span-3 space-y-1">
                    <Label className="text-[10px]">Capacity</Label>
                    <Input className="h-8 text-xs" type="number" value={t.capacity ?? 0} onChange={e => { const tiers = [...newEvent.ticket_tiers]; tiers[idx] = {...t, capacity: parseInt(e.target.value) || 0}; setNewEvent({...newEvent, ticket_tiers: tiers}); }} />
                  </div>
                  <div className="col-span-1 space-y-1 text-center">
                    <Label className="text-[10px] block">Sold</Label>
                    <span className="text-xs font-medium block py-1.5">{t.sold || 0}</span>
                  </div>
                  <Button type="button" size="sm" variant="ghost" className="col-span-1 h-8 text-destructive" onClick={() => setNewEvent({...newEvent, ticket_tiers: newEvent.ticket_tiers.filter((_, j) => j !== idx)})} data-testid={`tier-delete-${idx}`}>×</Button>
                </div>
              ))}
            </div>

            <div className="flex items-center justify-between p-3 rounded-lg border border-border">
              <div><p className="text-sm font-medium">Enable Waitlist</p><p className="text-xs text-muted-foreground">Allow signups when sold out (auto-promote when seats open)</p></div>
              <Switch checked={newEvent.waitlist_enabled ?? true} onCheckedChange={v => setNewEvent({...newEvent, waitlist_enabled: v})} data-testid="waitlist-switch" />
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg border border-border">
              <div><p className="text-sm font-medium">Recurring Event</p><p className="text-xs text-muted-foreground">Repeats on a schedule</p></div>
              <Switch checked={newEvent.is_recurring} onCheckedChange={v => setNewEvent({...newEvent, is_recurring: v})} />
            </div>
            {newEvent.is_recurring && (
              <div className="space-y-3 p-3 rounded-lg bg-muted/50">
                <div className="space-y-2"><Label>Recurrence Type</Label>
                  <Select value={newEvent.recurrence_type || 'weekly'} onValueChange={v => setNewEvent({...newEvent, recurrence_type: v})}>
                    <SelectTrigger data-testid="recurrence-type-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="daily">Daily</SelectItem>
                      <SelectItem value="weekly">Weekly (specific day)</SelectItem>
                      <SelectItem value="biweekly">Bi-weekly</SelectItem>
                      <SelectItem value="monthly">Monthly (same date)</SelectItem>
                      <SelectItem value="bimonthly">Bi-monthly (every 2 months)</SelectItem>
                      <SelectItem value="quarterly">Quarterly (every 3 months)</SelectItem>
                      <SelectItem value="nth_weekday">Monthly (nth weekday)</SelectItem>
                      <SelectItem value="yearly">Yearly (same date)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {(newEvent.recurrence_type === 'weekly' || newEvent.recurrence_type === 'nth_weekday' || !newEvent.recurrence_type) && (
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-2"><Label>Day of Week</Label>
                      <Select value={newEvent.recurrence_pattern || 'sunday'} onValueChange={v => setNewEvent({...newEvent, recurrence_pattern: v})}><SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>{['sunday','monday','tuesday','wednesday','thursday','friday','saturday'].map(d => <SelectItem key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                    {newEvent.recurrence_type === 'nth_weekday' && (
                      <div className="space-y-2"><Label>Which Occurrence</Label>
                        <Select value={String(newEvent.recurrence_day || 1)} onValueChange={v => setNewEvent({...newEvent, recurrence_day: parseInt(v)})}><SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent><SelectItem value="1">1st</SelectItem><SelectItem value="2">2nd</SelectItem><SelectItem value="3">3rd</SelectItem><SelectItem value="4">4th</SelectItem><SelectItem value="-1">Last</SelectItem></SelectContent>
                        </Select>
                      </div>
                    )}
                  </div>
                )}
                {['daily', 'weekly', 'monthly', 'bimonthly', 'quarterly', 'yearly'].includes(newEvent.recurrence_type) && (
                  <div className="space-y-2"><Label>Repeat every N {{ daily: 'days', weekly: 'weeks', yearly: 'years', monthly: 'months', bimonthly: 'intervals (2 months each)', quarterly: 'intervals (3 months each)' }[newEvent.recurrence_type] || 'units'}</Label>
                    <Input type="number" min={1} max={12} value={newEvent.recurrence_interval || 1} onChange={e => setNewEvent({...newEvent, recurrence_interval: parseInt(e.target.value) || 1})} />
                  </div>
                )}
                <div className="space-y-2"><Label>End Date (optional)</Label>
                  <Input type="date" value={newEvent.recurrence_end_date || ''} onChange={e => setNewEvent({...newEvent, recurrence_end_date: e.target.value})} data-testid="event-recurrence-end" />
                </div>
              </div>
            )}
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => { setShowAdd(false); setEditingEvent(null); }}>Cancel</Button>
              <Button data-testid="save-event-btn" type="submit" className="flex-1" disabled={saving}>{saving ? 'Saving...' : editingEvent ? 'Update Event' : 'Create Event'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Event Detail Dialog */}
      <Dialog open={!!selectedEvent} onOpenChange={() => { setSelectedEvent(null); setEventDetail(null); }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{eventDetail?.title ?? selectedEvent?.title}</DialogTitle><DialogDescription>{eventDetail?.location} · {eventDetail?.date}</DialogDescription></DialogHeader>
          {eventDetail && (
            <div className="mt-2 space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
                <div><p className="text-xs text-muted-foreground">Date & Time</p><p className="font-medium">{formatDate(eventDetail.date)} at {eventDetail.time}</p></div>
                <div><p className="text-xs text-muted-foreground">Location</p><p className="font-medium">{eventDetail.location || '—'}</p></div>
                <div><p className="text-xs text-muted-foreground">Capacity</p><p className="font-medium">{eventDetail.registered ?? 0} / {eventDetail.capacity}</p></div>
                <div><p className="text-xs text-muted-foreground">Status</p><p className="font-medium capitalize">{eventDetail.status}</p></div>
                <div><p className="text-xs text-muted-foreground">Visibility</p><p className="font-medium capitalize">{eventDetail.visibility || 'external'}</p></div>
                <div><p className="text-xs text-muted-foreground">Pricing</p><p className="font-medium">{eventDetail.is_free ? 'Free' : `UGX ${eventDetail.price?.toLocaleString() || '—'}`}</p></div>
              </div>
              {eventDetail.description && <div><p className="text-xs text-muted-foreground mb-1">Description</p><p className="text-sm">{eventDetail.description}</p></div>}
              <Tabs defaultValue="checkins">
                <TabsList>
                  <TabsTrigger value="checkins">Check-Ins ({eventDetail.checkins?.length ?? 0})</TabsTrigger>
                  <TabsTrigger value="attendees">Registrations ({eventDetail.attendees?.length ?? 0})</TabsTrigger>
                  <TabsTrigger value="tiers">Ticket Tiers ({(eventDetail.ticket_tiers || []).length})</TabsTrigger>
                  <TabsTrigger value="waitlist">Waitlist</TabsTrigger>
                </TabsList>
                <TabsContent value="checkins" className="mt-3">
                  {(eventDetail.checkins ?? []).length === 0 ? <p className="text-sm text-muted-foreground text-center py-6">No check-ins</p> : (
                    <div className="space-y-2">{eventDetail.checkins.map((ci, i) => (
                      <div key={ci.id || `ci-${i}`} className="flex items-center justify-between p-2 rounded border border-border text-sm">
                        <div><p className="font-medium">{ci.member_name}</p><p className="text-xs text-muted-foreground">{new Date(ci.check_in_time).toLocaleString()}</p></div>
                        <div className="flex gap-2">
                          <Badge variant="outline" className="text-xs capitalize">{ci.type}</Badge>
                          <Badge variant="secondary" className="text-xs capitalize">{ci.method}</Badge>
                          {!ci.check_out_time && <Button size="sm" variant="outline" className="h-6 text-xs" onClick={async () => { try { await checkinsApi.checkout(ci.id); toast.success('Checked out'); viewEvent(eventDetail); } catch { toast.error('Checkout failed'); } }}>Check Out</Button>}
                          {ci.check_out_time && <Badge className="bg-green-100 text-green-700 text-xs">Out</Badge>}
                        </div>
                      </div>
                    ))}</div>
                  )}
                </TabsContent>
                <TabsContent value="attendees" className="mt-3">
                  {(eventDetail.attendees ?? []).length === 0 ? <p className="text-sm text-muted-foreground text-center py-6" data-testid="event-attendees-empty">No registrations yet — when people sign up via the public event page or staff register them internally, they'll appear here.</p> : (
                    <div className="space-y-2" data-testid="event-attendees-list">{eventDetail.attendees.map((a, i) => (
                      <div key={a.id || a.email || `att-${i}`} className="flex items-center justify-between gap-2 p-2 rounded border border-border text-sm flex-wrap" data-testid={`attendee-row-${a.id || i}`}>
                        <div className="flex-1 min-w-0">
                          <p className="font-medium truncate">{a.name}</p>
                          <p className="text-xs text-muted-foreground truncate">
                            {a.email || '—'}{a.phone ? ` · ${a.phone}` : ''}
                          </p>
                          {(a.num_tickets > 1 || a.tier_name) && (
                            <p className="text-[10px] text-muted-foreground mt-0.5">
                              {a.num_tickets || 1} ticket{(a.num_tickets || 1) === 1 ? '' : 's'}
                              {a.tier_name ? ` · ${a.tier_name}` : ''}
                              {a.total ? ` · ${eventDetail.currency || 'UGX'} ${Number(a.total).toLocaleString()}` : ''}
                            </p>
                          )}
                          {a.created_at && (
                            <p className="text-[10px] text-muted-foreground">Registered {new Date(a.created_at).toLocaleString()}</p>
                          )}
                        </div>
                        <div className="flex items-center gap-1.5">
                          {a.payment_status && a.payment_status !== 'paid' && a.payment_status !== 'free' && (
                            <Badge variant="outline" className="text-[10px] capitalize">{a.payment_status}</Badge>
                          )}
                          <Badge className="bg-green-600 text-white border-0 text-xs capitalize">{a.status}</Badge>
                        </div>
                      </div>
                    ))}</div>
                  )}
                </TabsContent>
                <TabsContent value="tiers" className="mt-3">
                  {(eventDetail.ticket_tiers || []).length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-6">No ticket tiers — edit the event to add them.</p>
                  ) : (
                    <div className="space-y-2" data-testid="tiers-summary">
                      {eventDetail.ticket_tiers.map((t, i) => {
                        const pct = t.capacity ? Math.min(100, ((t.sold || 0) / t.capacity) * 100) : 0;
                        return (
                          <div key={t.id || i} className="p-3 rounded-lg border border-border">
                            <div className="flex items-center justify-between">
                              <div>
                                <p className="font-medium text-sm">{t.name}</p>
                                {t.description && <p className="text-xs text-muted-foreground">{t.description}</p>}
                              </div>
                              <div className="text-right">
                                <p className="font-bold text-sm">{(t.price || 0).toLocaleString()}</p>
                                <p className="text-xs text-muted-foreground">{t.sold || 0} / {t.capacity} sold</p>
                              </div>
                            </div>
                            <div className="mt-2 bg-muted rounded-full h-1.5"><div className="bg-primary h-1.5 rounded-full" style={{ width: `${pct}%` }} /></div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </TabsContent>
                <TabsContent value="waitlist" className="mt-3">
                  <EventWaitlistPanel eventId={eventDetail.id} ticketTiers={eventDetail.ticket_tiers} onPromoted={() => viewEvent(eventDetail)} />
                </TabsContent>
              </Tabs>
              <div className="flex gap-3 pt-2 border-t border-border flex-wrap">
                <Select value={eventDetail.status} onValueChange={v => { updateStatus(eventDetail, v); setEventDetail(prev => ({...prev, status: v})); }}>
                  <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="upcoming">Upcoming</SelectItem><SelectItem value="completed">Completed</SelectItem><SelectItem value="cancelled">Cancelled</SelectItem></SelectContent>
                </Select>
                <Button variant="outline" onClick={() => { editEvent(eventDetail); setSelectedEvent(null); }}>Edit</Button>
                <Button variant="outline" onClick={() => { duplicateEvent(eventDetail); setSelectedEvent(null); }}><Copy size={14} className="mr-1" />Duplicate</Button>
                <Button variant="outline" data-testid="export-attendees-csv" onClick={async () => {
                  try {
                    const res = await api.get(`/events/${eventDetail.id}/attendees/export`, { responseType: 'blob' });
                    const url = URL.createObjectURL(res.data);
                    const a = document.createElement('a');
                    a.href = url; a.download = `attendees-${eventDetail.id}.csv`;
                    document.body.appendChild(a); a.click(); a.remove();
                    URL.revokeObjectURL(url);
                    toast.success('Attendees exported');
                  } catch (e) { toast.error('Export failed'); }
                }}><Download size={14} className="mr-1" />Export CSV</Button>
                <Button variant="destructive" onClick={() => { deleteEvent(eventDetail); setSelectedEvent(null); }}>Delete</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Event Type Manager Dialog */}
      <Dialog open={showTypeManager} onOpenChange={setShowTypeManager}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Manage Event Types</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            {eventTypes.map(t => (
              <div key={t.id} className="flex items-center justify-between p-2 rounded border border-border">
                <div className="flex items-center gap-2"><div className="w-4 h-4 rounded-full" style={{ backgroundColor: t.color }} /><span className="text-sm font-medium">{t.label}</span></div>
                <Button size="sm" variant="ghost" className="text-destructive h-7" onClick={() => deleteEventType(t.id)}><Trash2 size={13} /></Button>
              </div>
            ))}
            <div className="flex gap-2 pt-2 border-t border-border">
              <Input placeholder="New type name" value={newTypeName} onChange={e => setNewTypeName(e.target.value)} className="flex-1" />
              <input type="color" value={newTypeColor} onChange={e => setNewTypeColor(e.target.value)} className="w-10 h-9 rounded border cursor-pointer" />
              <Button size="sm" onClick={addEventType} disabled={!newTypeName.trim()}>Add</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ========= Event Waitlist Panel =========
function EventWaitlistPanel({ eventId, ticketTiers, onPromoted }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`/events/${eventId}/waitlist`);
      setEntries(res.data || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [eventId]);
  useEffect(() => { reload(); }, [reload]);
  const tierName = (id) => (ticketTiers || []).find(t => t.id === id)?.name || '—';
  if (loading) return <div className="space-y-2">{[1,2].map(i => <div key={i} className="h-12 bg-muted animate-pulse rounded" />)}</div>;
  if (entries.length === 0) return <p className="text-sm text-muted-foreground text-center py-6">No one on the waitlist.</p>;
  return (
    <div className="space-y-2" data-testid="waitlist-panel">
      {entries.map(e => (
        <div key={e.id} className="flex items-center justify-between p-2 rounded border border-border text-sm" data-testid={`waitlist-${e.id}`}>
          <div>
            <p className="font-medium">{e.name} <span className="text-xs text-muted-foreground font-normal">· {e.num_tickets} ticket(s) · {tierName(e.tier_id)}</span></p>
            <p className="text-xs text-muted-foreground">{e.email} {e.phone ? `· ${e.phone}` : ''} · joined {e.created_at?.slice(0, 10)}</p>
          </div>
          <div className="flex gap-1">
            {e.status === 'waiting' && (
              <>
                <Button size="sm" variant="outline" className="h-7 text-xs" data-testid={`waitlist-promote-${e.id}`} onClick={async () => {
                  try { await api.post(`/events/${eventId}/waitlist/${e.id}/promote`); toast.success('Promoted to booking'); reload(); onPromoted?.(); }
                  catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
                }}>Promote</Button>
                <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive" data-testid={`waitlist-cancel-${e.id}`} onClick={async () => {
                  if (!window.confirm('Cancel this waitlist entry?')) return;
                  try { await api.delete(`/events/${eventId}/waitlist/${e.id}`); toast.success('Cancelled'); reload(); }
                  catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
                }}>Cancel</Button>
              </>
            )}
            {e.status !== 'waiting' && <Badge variant="outline" className="text-[10px] capitalize">{e.status}</Badge>}
          </div>
        </div>
      ))}
    </div>
  );
}

