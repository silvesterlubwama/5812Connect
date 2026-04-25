import React, { useState, useEffect, useCallback } from 'react';
import { Plus, Calendar, Clock, MapPin, Users, Search, Trash2, Eye, RefreshCw, Copy, Lock, Globe, Tag, DollarSign } from 'lucide-react';
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
  const emptyEvent = { title: '', type: 'service', date: '', time: '', end_time: '', location: '', location_id: activeCampus, venue_id: '', capacity: 100, description: '', is_public: true, is_free: true, price: '', visibility: 'external', is_recurring: false, recurrence_pattern: '', recurrence_day: 1, country: '' };
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
      const payload = { ...newEvent, price: newEvent.price ? parseFloat(newEvent.price) : undefined, capacity: parseInt(newEvent.capacity) };
      if (!payload.price) delete payload.price;
      const res = editingEvent ? await eventsApi.update(editingEvent.id, payload) : await eventsApi.create(payload);
      if (editingEvent) {
        setEvents(prev => prev.map(ev => ev.id === editingEvent.id ? res.data : ev));
        toast.success('Event updated');
      } else {
        setEvents(prev => [res.data, ...prev]);
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
    setNewEvent({ title: event.title, type: event.type || 'service', date: event.date || '', time: event.time || '', end_time: event.end_time || '', location: event.location || '', location_id: event.location_id || '', venue_id: event.venue_id || '', capacity: event.capacity || 100, description: event.description || '', is_public: event.is_public ?? true, is_free: event.is_free ?? true, price: event.price || '', visibility: event.visibility || 'external', is_recurring: event.is_recurring ?? false, recurrence_pattern: event.recurrence_pattern || '', recurrence_day: event.recurrence_day || 1, country: event.country || getLocationCountry(event.location_id) });
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
          {event.location && <div className="flex items-center gap-2"><MapPin size={13} /><span className="truncate">{event.location}</span></div>}
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
              <div className="space-y-2"><Label>Date *</Label><Input type="date" value={newEvent.date} onChange={e => setNewEvent({...newEvent, date: e.target.value})} required /></div>
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
                <TabsList><TabsTrigger value="checkins">Check-Ins ({eventDetail.checkins?.length ?? 0})</TabsTrigger><TabsTrigger value="attendees">Registrations ({eventDetail.attendees?.length ?? 0})</TabsTrigger></TabsList>
                <TabsContent value="checkins" className="mt-3">
                  {(eventDetail.checkins ?? []).length === 0 ? <p className="text-sm text-muted-foreground text-center py-6">No check-ins</p> : (
                    <div className="space-y-2">{eventDetail.checkins.map((ci, i) => (
                      <div key={item?.id || item?.day || i} className="flex items-center justify-between p-2 rounded border border-border text-sm">
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
                  {(eventDetail.attendees ?? []).length === 0 ? <p className="text-sm text-muted-foreground text-center py-6">No registrations</p> : (
                    <div className="space-y-2">{eventDetail.attendees.map((a, i) => (
                      <div key={item?.id || item?.day || i} className="flex items-center justify-between p-2 rounded border border-border text-sm">
                        <div><p className="font-medium">{a.name}</p><p className="text-xs text-muted-foreground">{a.email}</p></div>
                        <Badge className="bg-green-600 text-white border-0 text-xs">{a.status}</Badge>
                      </div>
                    ))}</div>
                  )}
                </TabsContent>
              </Tabs>
              <div className="flex gap-3 pt-2 border-t border-border flex-wrap">
                <Select value={eventDetail.status} onValueChange={v => { updateStatus(eventDetail, v); setEventDetail(prev => ({...prev, status: v})); }}>
                  <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="upcoming">Upcoming</SelectItem><SelectItem value="completed">Completed</SelectItem><SelectItem value="cancelled">Cancelled</SelectItem></SelectContent>
                </Select>
                <Button variant="outline" onClick={() => { editEvent(eventDetail); setSelectedEvent(null); }}>Edit</Button>
                <Button variant="outline" onClick={() => { duplicateEvent(eventDetail); setSelectedEvent(null); }}><Copy size={14} className="mr-1" />Duplicate</Button>
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
