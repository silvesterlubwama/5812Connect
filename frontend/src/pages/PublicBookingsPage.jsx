import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Ticket, Building, Search, Calendar, Clock, Users } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { publicApi } from '../services/api';
import { toast } from 'sonner';

const formatDate = (d) => new Date(d).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });

export default function PublicBookingsPage() {
  const [events, setEvents] = useState([]);
  const [venues, setVenues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [selectedVenue, setSelectedVenue] = useState(null);
  const [regData, setRegData] = useState({ name: '', email: '', phone: '', num_tickets: 1 });
  const [spaceData, setSpaceData] = useState({ name: '', email: '', phone: '', booking_date: '', start_time: '', end_time: '', purpose: '' });
  const [statusQuery, setStatusQuery] = useState({ booking_id: '', email: '', phone: '' });
  const [statusResults, setStatusResults] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [searchStatus, setSearchStatus] = useState(false);

  useEffect(() => {
    Promise.all([publicApi.events(), publicApi.venues()])
      .then(([evRes, venRes]) => { setEvents(evRes.data); setVenues(venRes.data); })
      .catch(() => toast.error('Failed to load data'))
      .finally(() => setLoading(false));
  }, []);

  const handleRegister = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await publicApi.bookEvent({ ...regData, event_id: selectedEvent.id });
      toast.success(`Registered! Ticket IDs: ${res.data.ticket_ids?.join(', ')}`);
      setSelectedEvent(null);
      setRegData({ name: '', email: '', phone: '', num_tickets: 1 });
      // Update local event count
      setEvents(prev => prev.map(ev => ev.id === selectedEvent.id ? { ...ev, registered: (ev.registered || 0) + regData.num_tickets } : ev));
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to register');
    } finally { setSubmitting(false); }
  };

  const handleSpaceBooking = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await publicApi.bookSpace({ ...spaceData, venue_id: selectedVenue.id });
      toast.success(`Space booking request submitted! ID: ${res.data.id}`);
      setSelectedVenue(null);
      setSpaceData({ name: '', email: '', phone: '', booking_date: '', start_time: '', end_time: '', purpose: '' });
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to submit booking');
    } finally { setSubmitting(false); }
  };

  const handleStatusLookup = async (e) => {
    e.preventDefault();
    setSearchStatus(true);
    try {
      const params = {};
      if (statusQuery.booking_id) params.booking_id = statusQuery.booking_id;
      else if (statusQuery.email) params.email = statusQuery.email;
      else if (statusQuery.phone) params.phone = statusQuery.phone;
      const res = await publicApi.checkStatus(params);
      setStatusResults(res.data);
      if (res.data.length === 0) toast.info('No bookings found');
    } catch { toast.error('Lookup failed'); }
    finally { setSearchStatus(false); }
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="bg-card border-b border-border px-4 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <img src="https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1" alt="58:12 Global" className="h-8 w-auto object-contain" />
          <Link to="/login"><Button variant="outline" size="sm">Staff Login</Button></Link>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8 space-y-6">
        <div className="text-center">
          <h2 className="text-3xl font-heading font-semibold mb-2">Book Events &amp; Spaces</h2>
          <p className="text-muted-foreground">Register for public events, reserve a venue, or check booking status.</p>
        </div>

        <Tabs defaultValue="events" className="space-y-6">
          <TabsList className="grid w-full max-w-lg mx-auto grid-cols-3">
            <TabsTrigger value="events" className="gap-2"><Ticket size={15} />Events</TabsTrigger>
            <TabsTrigger value="venues" className="gap-2"><Building size={15} />Book Space</TabsTrigger>
            <TabsTrigger value="status" className="gap-2"><Search size={15} />Status Lookup</TabsTrigger>
          </TabsList>

          <TabsContent value="events">
            {loading ? (
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
                {[1,2,3].map(i => <div key={i} className="h-64 bg-card border border-border rounded-xl animate-pulse" />)}
              </div>
            ) : events.length === 0 ? (
              <p className="text-center py-12 text-muted-foreground">No public events available</p>
            ) : (
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
                {events.map(event => (
                  <Card key={event.id} className="shadow-soft hover:shadow-soft-lg transition-shadow rounded-xl">
                    <CardContent className="p-6">
                      <div className="flex items-start justify-between mb-4">
                        <Badge variant="outline" className="capitalize">{event.type}</Badge>
                        {event.is_free
                          ? <Badge className="bg-green-600 text-white border-0">Free</Badge>
                          : <Badge className="bg-amber-600 text-white border-0">UGX {event.price?.toLocaleString()}</Badge>
                        }
                      </div>
                      <h3 className="font-semibold text-lg mb-3">{event.title}</h3>
                      <div className="space-y-2 text-sm text-muted-foreground mb-4">
                        <div className="flex items-center gap-2"><Calendar size={14} /><span>{formatDate(event.date)}</span></div>
                        <div className="flex items-center gap-2"><Clock size={14} /><span>{event.time}</span></div>
                        <div className="flex items-center gap-2"><Users size={14} /><span>{event.capacity - (event.registered || 0)} spots left</span></div>
                      </div>
                      <Button className="w-full" onClick={() => setSelectedEvent(event)} disabled={event.capacity - (event.registered || 0) <= 0}>
                        {event.capacity - (event.registered || 0) <= 0 ? 'Fully Booked' : event.is_free ? 'Get Free Tickets' : 'Register Now'}
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value="venues">
            {loading ? (
              <div className="grid md:grid-cols-2 gap-6">
                {[1,2].map(i => <div key={i} className="h-48 bg-card border border-border rounded-xl animate-pulse" />)}
              </div>
            ) : (
              <div className="grid md:grid-cols-2 gap-6">
                {venues.map(venue => (
                  <Card key={venue.id} className="shadow-soft rounded-xl">
                    <CardContent className="p-6">
                      <div className="flex items-start justify-between mb-3">
                        <h3 className="font-semibold text-lg">{venue.name}</h3>
                        <Badge variant={venue.available ? 'outline' : 'secondary'} className={venue.available ? 'border-green-500 text-green-600' : ''}>
                          {venue.available ? 'Available' : 'Unavailable'}
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground mb-3">{venue.description}</p>
                      <div className="flex items-center gap-4 text-sm text-muted-foreground mb-4">
                        <span className="flex items-center gap-1"><Users size={13} />{venue.capacity} capacity</span>
                        <span className="capitalize">{venue.type}</span>
                      </div>
                      <p className="text-sm font-medium mb-4">
                        {venue.hourly_rate ? `UGX ${venue.hourly_rate?.toLocaleString()} / hr` : 'Free use'}
                      </p>
                      <Button className="w-full" disabled={!venue.available} onClick={() => setSelectedVenue(venue)}>
                        {venue.available ? 'Request Booking' : 'Currently Unavailable'}
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value="status">
            <div className="max-w-lg mx-auto">
              <Card className="shadow-soft rounded-xl">
                <CardContent className="p-6 space-y-4">
                  <div>
                    <h3 className="font-semibold text-lg mb-1">Check Booking Status</h3>
                    <p className="text-sm text-muted-foreground">Enter your booking ID, email, or phone number</p>
                  </div>
                  <form onSubmit={handleStatusLookup} className="space-y-4">
                    <div className="space-y-2">
                      <Label>Booking ID</Label>
                      <Input placeholder="book_xxxxxxxxxxxx" value={statusQuery.booking_id} onChange={e => setStatusQuery({...statusQuery, booking_id: e.target.value})} />
                    </div>
                    <div className="text-center text-xs text-muted-foreground">— or —</div>
                    <div className="space-y-2">
                      <Label>Email (optional)</Label>
                      <Input type="email" placeholder="your@email.com" value={statusQuery.email} onChange={e => setStatusQuery({...statusQuery, email: e.target.value})} />
                    </div>
                    <div className="space-y-2">
                      <Label>Phone (optional)</Label>
                      <Input placeholder="+256 700 000000" value={statusQuery.phone} onChange={e => setStatusQuery({...statusQuery, phone: e.target.value})} />
                    </div>
                    <Button type="submit" className="w-full gap-2" disabled={searchStatus}>
                      <Search size={15} />{searchStatus ? 'Looking up...' : 'Check Booking Status'}
                    </Button>
                  </form>

                  {statusResults !== null && (
                    <div className="mt-4 space-y-3">
                      {statusResults.length === 0 ? (
                        <p className="text-sm text-muted-foreground text-center py-4">No bookings found</p>
                      ) : (
                        <>
                          <p className="text-sm font-medium">Found {statusResults.length} booking(s):</p>
                          {statusResults.map(b => (
                            <div key={b.id} className="flex items-center justify-between p-3 rounded-lg border border-border bg-secondary/30">
                              <div>
                                <p className="text-sm font-medium">{b.id}</p>
                                <p className="text-xs text-muted-foreground">{b.name} · {b.email}</p>
                              </div>
                              <Badge className={`border-0 text-white text-xs ${b.status === 'confirmed' ? 'bg-green-600' : 'bg-amber-600'}`}>
                                {b.status}
                              </Badge>
                            </div>
                          ))}
                        </>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>
      </main>

      {/* Event Registration Dialog */}
      <Dialog open={!!selectedEvent} onOpenChange={() => setSelectedEvent(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Register for {selectedEvent?.title}</DialogTitle>
            <DialogDescription>{selectedEvent && formatDate(selectedEvent.date)} at {selectedEvent?.time}</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleRegister} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Full Name *</Label><Input placeholder="Your full name" value={regData.name} onChange={e => setRegData({...regData, name: e.target.value})} required /></div>
            <div className="space-y-2"><Label>Email *</Label><Input type="email" placeholder="your@email.com" value={regData.email} onChange={e => setRegData({...regData, email: e.target.value})} required /></div>
            <div className="space-y-2"><Label>Phone</Label><Input placeholder="+256 700 000000" value={regData.phone} onChange={e => setRegData({...regData, phone: e.target.value})} /></div>
            <div className="space-y-2">
              <Label>Number of Tickets</Label>
              <Input type="number" min={1} max={10} value={regData.num_tickets} onChange={e => setRegData({...regData, num_tickets: parseInt(e.target.value)})} />
            </div>
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? 'Submitting...' : selectedEvent?.is_free ? 'Confirm Registration' : 'Register Now'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Space Booking Dialog */}
      <Dialog open={!!selectedVenue} onOpenChange={() => setSelectedVenue(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Book {selectedVenue?.name}</DialogTitle>
            <DialogDescription>Capacity: {selectedVenue?.capacity} · {selectedVenue?.hourly_rate ? `UGX ${selectedVenue?.hourly_rate?.toLocaleString()}/hr` : 'Free'}</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSpaceBooking} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Full Name *</Label><Input placeholder="Your full name" value={spaceData.name} onChange={e => setSpaceData({...spaceData, name: e.target.value})} required /></div>
            <div className="space-y-2"><Label>Email *</Label><Input type="email" value={spaceData.email} onChange={e => setSpaceData({...spaceData, email: e.target.value})} required /></div>
            <div className="space-y-2"><Label>Phone</Label><Input value={spaceData.phone} onChange={e => setSpaceData({...spaceData, phone: e.target.value})} /></div>
            <div className="space-y-2"><Label>Booking Date *</Label><Input type="date" value={spaceData.booking_date} onChange={e => setSpaceData({...spaceData, booking_date: e.target.value})} required /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Start Time</Label><Input type="time" value={spaceData.start_time} onChange={e => setSpaceData({...spaceData, start_time: e.target.value})} /></div>
              <div className="space-y-2"><Label>End Time</Label><Input type="time" value={spaceData.end_time} onChange={e => setSpaceData({...spaceData, end_time: e.target.value})} /></div>
            </div>
            <div className="space-y-2"><Label>Purpose</Label><Input placeholder="Event, meeting, class..." value={spaceData.purpose} onChange={e => setSpaceData({...spaceData, purpose: e.target.value})} /></div>
            <Button type="submit" className="w-full" disabled={submitting}>{submitting ? 'Submitting...' : 'Submit Booking Request'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      <footer className="text-center py-6 text-sm text-muted-foreground border-t border-border mt-8">
        58:12 Global • Uganda CRM System
      </footer>
    </div>
  );
}
