import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Ticket, Building, Search, Calendar, Clock, Users } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { MOCK_EVENTS, MOCK_VENUES } from '../mock';
import { toast } from 'sonner';

const publicEvents = MOCK_EVENTS.filter(e => e.isPublic && e.status !== 'completed');

const formatDate = (dateStr) => {
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
};

export default function PublicBookingsPage() {
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [regName, setRegName] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPhone, setRegPhone] = useState('');
  const [statusEmail, setStatusEmail] = useState('');
  const [statusResult, setStatusResult] = useState(null);

  const handleRegister = (e) => {
    e.preventDefault();
    toast.success(`Registered for "${selectedEvent.title}"! Confirmation sent to ${regEmail}`);
    setSelectedEvent(null);
    setRegName('');
    setRegEmail('');
    setRegPhone('');
  };

  const handleStatusLookup = (e) => {
    e.preventDefault();
    setStatusResult({
      found: true,
      bookings: [
        { event: 'Youth Leadership Summit', date: '2026-04-12', status: 'confirmed', ticketId: 'TKT-0042' },
        { event: 'Sunday Service', date: '2026-04-06', status: 'confirmed', ticketId: 'TKT-0039' },
      ]
    });
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="bg-card border-b border-border px-4 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <img
            src="https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1"
            alt="58:12 Global"
            className="h-8 w-auto object-contain"
          />
          <Link to="/login">
            <Button variant="outline" size="sm">Staff Login</Button>
          </Link>
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

          {/* Events tab */}
          <TabsContent value="events">
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
              {publicEvents.map(event => (
                <Card key={event.id} className="shadow-soft hover:shadow-soft-lg transition-shadow rounded-xl">
                  <CardContent className="p-6">
                    <div className="flex items-start justify-between mb-4">
                      <Badge variant="outline" className="capitalize">{event.type}</Badge>
                      {event.isFree
                        ? <Badge className="bg-green-600 text-white border-0">Free</Badge>
                        : <Badge className="bg-amber-600 text-white border-0">UGX {event.price?.toLocaleString()}</Badge>
                      }
                    </div>
                    <h3 className="font-semibold text-lg mb-3">{event.title}</h3>
                    <div className="space-y-2 text-sm text-muted-foreground mb-4">
                      <div className="flex items-center gap-2">
                        <Calendar size={14} />
                        <span>{formatDate(event.date)}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Clock size={14} />
                        <span>{event.time}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Users size={14} />
                        <span>{event.capacity - event.registered} spots left</span>
                      </div>
                    </div>
                    <Button className="w-full" onClick={() => setSelectedEvent(event)}>
                      {event.isFree ? 'Get Free Tickets' : 'Register Now'}
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          {/* Venues tab */}
          <TabsContent value="venues">
            <div className="grid md:grid-cols-2 gap-6">
              {MOCK_VENUES.map(venue => (
                <Card key={venue.id} className="shadow-soft rounded-xl">
                  <CardContent className="p-6">
                    <div className="flex items-start justify-between mb-3">
                      <h3 className="font-semibold text-lg">{venue.name}</h3>
                      <Badge variant={venue.available ? 'outline' : 'secondary'} className={venue.available ? 'border-green-500 text-green-600' : ''}>
                        {venue.available ? 'Available' : 'Booked'}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground mb-3">{venue.description}</p>
                    <div className="flex items-center gap-4 text-sm text-muted-foreground mb-4">
                      <span className="flex items-center gap-1"><Users size={13} /> {venue.capacity} capacity</span>
                      <span className="capitalize">{venue.type}</span>
                    </div>
                    {venue.hourlyRate && (
                      <p className="text-sm font-medium mb-3">UGX {venue.hourlyRate?.toLocaleString()} / hour</p>
                    )}
                    {!venue.hourlyRate && <p className="text-sm text-green-600 font-medium mb-3">Free use</p>}
                    <Button className="w-full" disabled={!venue.available} onClick={() => toast.success(`Booking request sent for ${venue.name}`)}>
                      {venue.available ? 'Request Booking' : 'Currently Unavailable'}
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          {/* Status tab */}
          <TabsContent value="status">
            <div className="max-w-lg mx-auto">
              <Card className="shadow-soft rounded-xl">
                <CardContent className="p-6 space-y-4">
                  <div>
                    <h3 className="font-semibold text-lg mb-1">Check Booking Status</h3>
                    <p className="text-sm text-muted-foreground">Enter your email to find your bookings</p>
                  </div>
                  <form onSubmit={handleStatusLookup} className="space-y-4">
                    <div className="space-y-2">
                      <Label>Email Address</Label>
                      <Input
                        type="email"
                        placeholder="your@email.com"
                        value={statusEmail}
                        onChange={e => setStatusEmail(e.target.value)}
                        required
                      />
                    </div>
                    <Button type="submit" className="w-full gap-2">
                      <Search size={15} /> Look Up Bookings
                    </Button>
                  </form>

                  {statusResult && (
                    <div className="mt-4 space-y-3">
                      <p className="text-sm font-medium">Found {statusResult.bookings.length} booking(s):</p>
                      {statusResult.bookings.map((b, i) => (
                        <div key={i} className="flex items-center justify-between p-3 rounded-lg border border-border bg-secondary/30">
                          <div>
                            <p className="text-sm font-medium">{b.event}</p>
                            <p className="text-xs text-muted-foreground">{b.date} • {b.ticketId}</p>
                          </div>
                          <Badge className="bg-green-600 text-white border-0">{b.status}</Badge>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>
      </main>

      {/* Registration dialog */}
      <Dialog open={!!selectedEvent} onOpenChange={() => setSelectedEvent(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Register for {selectedEvent?.title}</DialogTitle>
            <DialogDescription>
              {selectedEvent && formatDate(selectedEvent.date)} at {selectedEvent?.time}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleRegister} className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Full Name</Label>
              <Input placeholder="Your full name" value={regName} onChange={e => setRegName(e.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label>Email Address</Label>
              <Input type="email" placeholder="your@email.com" value={regEmail} onChange={e => setRegEmail(e.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label>Phone Number</Label>
              <Input placeholder="+256 700 000000" value={regPhone} onChange={e => setRegPhone(e.target.value)} />
            </div>
            <Button type="submit" className="w-full">
              {selectedEvent?.isFree ? 'Confirm Registration' : 'Proceed to Payment'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      <footer className="text-center py-6 text-sm text-muted-foreground border-t border-border mt-8">
        58:12 Global • Uganda CRM System
      </footer>
    </div>
  );
}
