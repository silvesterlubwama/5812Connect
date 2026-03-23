import React, { useState } from 'react';
import { Plus, Calendar, Clock, MapPin, Users, Search } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Card, CardContent } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { MOCK_EVENTS } from '../mock';
import { toast } from 'sonner';

const statusColors = {
  upcoming: 'bg-blue-100 text-blue-700 border-blue-200',
  completed: 'bg-green-100 text-green-700 border-green-200',
  cancelled: 'bg-red-100 text-red-700 border-red-200',
};

const typeColors = {
  service: 'bg-purple-100 text-purple-700',
  conference: 'bg-amber-100 text-amber-700',
  meeting: 'bg-gray-100 text-gray-700',
  community: 'bg-teal-100 text-teal-700',
};

export default function EventsPage() {
  const [events, setEvents] = useState(MOCK_EVENTS);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [showAdd, setShowAdd] = useState(false);
  const [newEvent, setNewEvent] = useState({
    title: '', type: 'service', date: '', time: '', endTime: '', location: '',
    capacity: 100, description: '', isPublic: true, isFree: true,
  });

  const filtered = events.filter(e => {
    const matchSearch = !search || e.title.toLowerCase().includes(search.toLowerCase());
    const matchType = typeFilter === 'all' || e.type === typeFilter;
    return matchSearch && matchType;
  });

  const upcoming = filtered.filter(e => e.status === 'upcoming');
  const past = filtered.filter(e => e.status === 'completed');

  const handleAddEvent = (e) => {
    e.preventDefault();
    const event = {
      ...newEvent,
      id: `evt_${Date.now()}`,
      status: 'upcoming',
      registered: 0,
    };
    setEvents(prev => [event, ...prev]);
    setShowAdd(false);
    toast.success(`Event "${event.title}" created!`);
  };

  const formatDate = (dateStr) => new Date(dateStr).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });

  const EventCard = ({ event }) => (
    <Card className="shadow-soft rounded-xl hover:shadow-soft-lg transition-shadow">
      <CardContent className="p-5">
        <div className="flex items-start justify-between mb-3">
          <div className="flex flex-wrap gap-1.5">
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${typeColors[event.type] || typeColors.meeting}`}>
              {event.type}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium border capitalize ${statusColors[event.status] || ''}`}>
              {event.status}
            </span>
          </div>
          {event.isPublic
            ? <Badge variant="outline" className="text-xs border-green-500 text-green-600">Public</Badge>
            : <Badge variant="secondary" className="text-xs">Private</Badge>
          }
        </div>

        <h3 className="font-semibold text-base mb-3">{event.title}</h3>

        <div className="space-y-2 text-sm text-muted-foreground mb-4">
          <div className="flex items-center gap-2">
            <Calendar size={13} />
            <span>{formatDate(event.date)}</span>
          </div>
          <div className="flex items-center gap-2">
            <Clock size={13} />
            <span>{event.time}{event.endTime ? ` – ${event.endTime}` : ''}</span>
          </div>
          <div className="flex items-center gap-2">
            <MapPin size={13} />
            <span className="truncate">{event.location}</span>
          </div>
          <div className="flex items-center gap-2">
            <Users size={13} />
            <span>{event.registered}/{event.capacity} registered</span>
            <div className="flex-1 bg-muted rounded-full h-1.5 ml-1">
              <div
                className="bg-primary h-1.5 rounded-full transition-all"
                style={{ width: `${Math.min((event.registered / event.capacity) * 100, 100)}%` }}
              />
            </div>
          </div>
        </div>

        <div className="flex gap-2">
          <Button size="sm" variant="outline" className="flex-1" onClick={() => toast.info(`Viewing ${event.title}`)}>
            View Details
          </Button>
          <Button size="sm" className="flex-1" onClick={() => toast.success('Check-in opened')}>
            Check-In
          </Button>
        </div>
      </CardContent>
    </Card>
  );

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Events</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{events.length} total events</p>
        </div>
        <Button onClick={() => setShowAdd(true)} className="gap-2">
          <Plus size={16} /> Create Event
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input placeholder="Search events..." className="pl-9" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-full sm:w-40">
            <SelectValue placeholder="Type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            <SelectItem value="service">Service</SelectItem>
            <SelectItem value="conference">Conference</SelectItem>
            <SelectItem value="meeting">Meeting</SelectItem>
            <SelectItem value="community">Community</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Tabs defaultValue="upcoming">
        <TabsList>
          <TabsTrigger value="upcoming">Upcoming ({upcoming.length})</TabsTrigger>
          <TabsTrigger value="past">Past ({past.length})</TabsTrigger>
        </TabsList>
        <TabsContent value="upcoming" className="mt-4">
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {upcoming.map(event => <EventCard key={event.id} event={event} />)}
          </div>
          {upcoming.length === 0 && <p className="text-center py-10 text-muted-foreground">No upcoming events</p>}
        </TabsContent>
        <TabsContent value="past" className="mt-4">
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {past.map(event => <EventCard key={event.id} event={event} />)}
          </div>
          {past.length === 0 && <p className="text-center py-10 text-muted-foreground">No past events</p>}
        </TabsContent>
      </Tabs>

      {/* Add Event Dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Create New Event</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleAddEvent} className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Event Title</Label>
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
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Date</Label>
                <Input type="date" value={newEvent.date} onChange={e => setNewEvent({...newEvent, date: e.target.value})} required />
              </div>
              <div className="space-y-2">
                <Label>Start Time</Label>
                <Input type="time" value={newEvent.time} onChange={e => setNewEvent({...newEvent, time: e.target.value})} />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Location</Label>
              <Input placeholder="Event location" value={newEvent.location} onChange={e => setNewEvent({...newEvent, location: e.target.value})} />
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowAdd(false)}>Cancel</Button>
              <Button type="submit" className="flex-1">Create Event</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
