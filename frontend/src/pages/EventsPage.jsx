import React, { useState, useEffect } from 'react';
import { Plus, Calendar, Clock, MapPin, Users, Search, Trash2, Eye, RefreshCw } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Card, CardContent } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Switch } from '../components/ui/switch';
import { eventsApi, checkinsApi } from '../services/api';
import { toast } from 'sonner';

const statusColors = {
  upcoming: 'bg-blue-100 text-blue-700 border-blue-200',
  completed: 'bg-green-100 text-green-700 border-green-200',
  cancelled: 'bg-red-100 text-red-700 border-red-200',
};
const typeColors = {
  service: 'bg-purple-100 text-purple-700',
  conference: 'bg-amber-100 text-amber-700',
  meeting: 'bg-slate-100 text-slate-700',
  community: 'bg-teal-100 text-teal-700',
};

export default function EventsPage() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [showAdd, setShowAdd] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [eventDetail, setEventDetail] = useState(null);
  const [saving, setSaving] = useState(false);
  const [newEvent, setNewEvent] = useState({
    title: '', type: 'service', date: '', time: '', end_time: '', location: '',
    capacity: 100, description: '', is_public: true, is_free: true, price: '',
  });

  const fetchEvents = async () => {
    setLoading(true);
    try {
      const res = await eventsApi.list({ search: search || undefined, type: typeFilter !== 'all' ? typeFilter : undefined });
      setEvents(res.data);
    } catch { toast.error('Failed to load events'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchEvents(); }, [search, typeFilter]);

  const upcoming = events.filter(e => e.status === 'upcoming');
  const past = events.filter(e => e.status !== 'upcoming');

  const handleAdd = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = { ...newEvent, price: newEvent.price ? parseFloat(newEvent.price) : undefined };
      if (!payload.price) delete payload.price;
      const res = await eventsApi.create(payload);
      setEvents(prev => [res.data, ...prev]);
      setShowAdd(false);
      setNewEvent({ title: '', type: 'service', date: '', time: '', end_time: '', location: '', capacity: 100, description: '', is_public: true, is_free: true, price: '' });
      toast.success(`Event "${res.data.title}" created!`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create event');
    } finally { setSaving(false); }
  };

  const viewEvent = async (event) => {
    setSelectedEvent(event);
    try {
      const res = await eventsApi.get(event.id);
      setEventDetail(res.data);
    } catch { setEventDetail(event); }
  };

  const deleteEvent = async (event) => {
    if (!window.confirm(`Delete "${event.title}"?`)) return;
    try {
      await eventsApi.delete(event.id);
      setEvents(prev => prev.filter(e => e.id !== event.id));
      toast.success('Event deleted');
    } catch { toast.error('Failed to delete'); }
  };

  const updateStatus = async (event, newStatus) => {
    try {
      await eventsApi.update(event.id, { status: newStatus });
      setEvents(prev => prev.map(e => e.id === event.id ? { ...e, status: newStatus } : e));
      toast.success('Event status updated');
    } catch { toast.error('Failed to update'); }
  };

  const formatDate = (d) => new Date(d).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });

  const EventCard = ({ event }) => (
    <Card className="shadow-soft rounded-xl hover:shadow-soft-lg transition-shadow">
      <CardContent className="p-5">
        <div className="flex items-start justify-between mb-3">
          <div className="flex flex-wrap gap-1.5">
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${typeColors[event.type] || typeColors.meeting}`}>{event.type}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium border capitalize ${statusColors[event.status] || ''}`}>{event.status}</span>
          </div>
          <Badge variant={event.is_public ? 'outline' : 'secondary'} className={`text-xs ${event.is_public ? 'border-green-500 text-green-600' : ''}`}>
            {event.is_public ? 'Public' : 'Private'}
          </Badge>
        </div>
        <h3 className="font-semibold text-base mb-3">{event.title}</h3>
        <div className="space-y-1.5 text-sm text-muted-foreground mb-4">
          <div className="flex items-center gap-2"><Calendar size={13} /><span>{formatDate(event.date)}</span></div>
          <div className="flex items-center gap-2"><Clock size={13} /><span>{event.time}{event.end_time ? ` – ${event.end_time}` : ''}</span></div>
          {event.location && <div className="flex items-center gap-2"><MapPin size={13} /><span className="truncate">{event.location}</span></div>}
          <div className="flex items-center gap-2">
            <Users size={13} />
            <span>{event.registered ?? 0}/{event.capacity} registered</span>
            <div className="flex-1 bg-muted rounded-full h-1.5 ml-1">
              <div className="bg-primary h-1.5 rounded-full" style={{ width: `${Math.min(((event.registered ?? 0) / event.capacity) * 100, 100)}%` }} />
            </div>
          </div>
        </div>
        {!event.is_free && event.price && (
          <p className="text-sm font-medium text-primary mb-3">UGX {event.price?.toLocaleString()}</p>
        )}
        <div className="flex gap-2">
          <Button size="sm" variant="outline" className="flex-1" onClick={() => viewEvent(event)}><Eye size={13} className="mr-1" />Details</Button>
          <Button size="sm" className="flex-1" onClick={() => toast.info('Check-in feature coming soon')}>Check-In</Button>
          <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive px-2" onClick={() => deleteEvent(event)}><Trash2 size={13} /></Button>
        </div>
      </CardContent>
    </Card>
  );

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Events</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{events.length} total · {upcoming.length} upcoming</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchEvents}><RefreshCw size={14} /></Button>
          <Button onClick={() => setShowAdd(true)} className="gap-2"><Plus size={16} /> Create Event</Button>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input placeholder="Search events..." className="pl-9" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-full sm:w-40"><SelectValue placeholder="Type" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            <SelectItem value="service">Service</SelectItem>
            <SelectItem value="conference">Conference</SelectItem>
            <SelectItem value="meeting">Meeting</SelectItem>
            <SelectItem value="community">Community</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {loading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => <div key={i} className="h-56 bg-card border border-border rounded-xl animate-pulse" />)}
        </div>
      ) : (
        <Tabs defaultValue="upcoming">
          <TabsList>
            <TabsTrigger value="upcoming">Upcoming ({upcoming.length})</TabsTrigger>
            <TabsTrigger value="past">Past ({past.length})</TabsTrigger>
          </TabsList>
          <TabsContent value="upcoming" className="mt-4">
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {upcoming.map(e => <EventCard key={e.id} event={e} />)}
            </div>
            {upcoming.length === 0 && (
              <div className="text-center py-12 text-muted-foreground">
                <Calendar size={40} className="mx-auto mb-3 opacity-30" />
                <p>No upcoming events</p>
                <Button variant="outline" className="mt-4" onClick={() => setShowAdd(true)}>Create an event</Button>
              </div>
            )}
          </TabsContent>
          <TabsContent value="past" className="mt-4">
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {past.map(e => <EventCard key={e.id} event={e} />)}
            </div>
            {past.length === 0 && <p className="text-center py-10 text-muted-foreground">No past events</p>}
          </TabsContent>
        </Tabs>
      )}

      {/* Add Event Dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Create New Event</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleAdd} className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Event Title *</Label>
              <Input placeholder="Event name" value={newEvent.title} onChange={e => setNewEvent({...newEvent, title: e.target.value})} required />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Type</Label>
                <Select value={newEvent.type} onValueChange={v => setNewEvent({...newEvent, type: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="service">Service</SelectItem>
                    <SelectItem value="conference">Conference</SelectItem>
                    <SelectItem value="meeting">Meeting</SelectItem>
                    <SelectItem value="community">Community</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Capacity</Label>
                <Input type="number" value={newEvent.capacity} onChange={e => setNewEvent({...newEvent, capacity: parseInt(e.target.value)})} />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-2">
                <Label>Date *</Label>
                <Input type="date" value={newEvent.date} onChange={e => setNewEvent({...newEvent, date: e.target.value})} required />
              </div>
              <div className="space-y-2">
                <Label>Start Time</Label>
                <Input type="time" value={newEvent.time} onChange={e => setNewEvent({...newEvent, time: e.target.value})} />
              </div>
              <div className="space-y-2">
                <Label>End Time</Label>
                <Input type="time" value={newEvent.end_time} onChange={e => setNewEvent({...newEvent, end_time: e.target.value})} />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Location</Label>
              <Input placeholder="Event location" value={newEvent.location} onChange={e => setNewEvent({...newEvent, location: e.target.value})} />
            </div>
            <div className="space-y-2">
              <Label>Description</Label>
              <Input placeholder="Brief description" value={newEvent.description} onChange={e => setNewEvent({...newEvent, description: e.target.value})} />
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg border border-border">
              <div><p className="text-sm font-medium">Public Event</p><p className="text-xs text-muted-foreground">Visible on public bookings page</p></div>
              <Switch checked={newEvent.is_public} onCheckedChange={v => setNewEvent({...newEvent, is_public: v})} />
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg border border-border">
              <div><p className="text-sm font-medium">Free Event</p><p className="text-xs text-muted-foreground">No payment required</p></div>
              <Switch checked={newEvent.is_free} onCheckedChange={v => setNewEvent({...newEvent, is_free: v})} />
            </div>
            {!newEvent.is_free && (
              <div className="space-y-2">
                <Label>Price (UGX)</Label>
                <Input type="number" placeholder="25000" value={newEvent.price} onChange={e => setNewEvent({...newEvent, price: e.target.value})} />
              </div>
            )}
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowAdd(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving}>{saving ? 'Creating...' : 'Create Event'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Event Detail Dialog */}
      <Dialog open={!!selectedEvent} onOpenChange={() => { setSelectedEvent(null); setEventDetail(null); }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{eventDetail?.title ?? selectedEvent?.title}</DialogTitle>
            <DialogDescription>{eventDetail?.location} · {eventDetail?.date}</DialogDescription>
          </DialogHeader>
          {eventDetail && (
            <div className="mt-2 space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div><p className="text-xs text-muted-foreground">Date & Time</p><p className="font-medium">{formatDate(eventDetail.date)} at {eventDetail.time}</p></div>
                <div><p className="text-xs text-muted-foreground">Location</p><p className="font-medium">{eventDetail.location || '—'}</p></div>
                <div><p className="text-xs text-muted-foreground">Capacity</p><p className="font-medium">{eventDetail.registered ?? 0} / {eventDetail.capacity}</p></div>
                <div><p className="text-xs text-muted-foreground">Status</p><p className="font-medium capitalize">{eventDetail.status}</p></div>
              </div>
              {eventDetail.description && (
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Description</p>
                  <p className="text-sm">{eventDetail.description}</p>
                </div>
              )}

              <Tabs defaultValue="attendees">
                <TabsList>
                  <TabsTrigger value="attendees">Registrations ({eventDetail.attendees?.length ?? 0})</TabsTrigger>
                  <TabsTrigger value="checkins">Check-Ins ({eventDetail.checkins?.length ?? 0})</TabsTrigger>
                </TabsList>
                <TabsContent value="attendees" className="mt-3">
                  {(eventDetail.attendees ?? []).length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-6">No registrations yet</p>
                  ) : (
                    <div className="space-y-2">
                      {eventDetail.attendees.map((a, i) => (
                        <div key={i} className="flex items-center justify-between p-2 rounded border border-border text-sm">
                          <div><p className="font-medium">{a.name}</p><p className="text-xs text-muted-foreground">{a.email}</p></div>
                          <Badge className="bg-green-600 text-white border-0 text-xs">{a.status}</Badge>
                        </div>
                      ))}
                    </div>
                  )}
                </TabsContent>
                <TabsContent value="checkins" className="mt-3">
                  {(eventDetail.checkins ?? []).length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-6">No check-ins for this event</p>
                  ) : (
                    <div className="space-y-2">
                      {eventDetail.checkins.map((ci, i) => (
                        <div key={i} className="flex items-center justify-between p-2 rounded border border-border text-sm">
                          <div><p className="font-medium">{ci.member_name}</p><p className="text-xs text-muted-foreground">{new Date(ci.check_in_time).toLocaleString()}</p></div>
                          <div className="flex gap-2">
                            <Badge variant="outline" className="text-xs capitalize">{ci.type}</Badge>
                            <Badge variant="secondary" className="text-xs capitalize">{ci.method}</Badge>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </TabsContent>
              </Tabs>

              <div className="flex gap-3 pt-2 border-t border-border">
                <Select value={eventDetail.status} onValueChange={v => { updateStatus(eventDetail, v); setEventDetail(prev => ({...prev, status: v})); }}>
                  <SelectTrigger className="flex-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="upcoming">Upcoming</SelectItem>
                    <SelectItem value="completed">Completed</SelectItem>
                    <SelectItem value="cancelled">Cancelled</SelectItem>
                  </SelectContent>
                </Select>
                <Button variant="destructive" onClick={() => { deleteEvent(eventDetail); setSelectedEvent(null); }}>Delete</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
