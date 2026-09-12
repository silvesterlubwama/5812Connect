import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Calendar, MapPin, Users, Check } from 'lucide-react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { portalApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

export default function PortalEvents() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    portalApi.events()
      .then(res => setEvents(res.data))
      .catch(() => toast.error('Failed to load events'))
      .finally(() => setLoading(false));
  }, []);

  const handleRsvp = async (eventId) => {
    try {
      const r = await portalApi.rsvpEvent(eventId);
      toast.success(r.data?.message || 'RSVP confirmed — your pass is in My Tickets');
      setEvents(prev => prev.map(e => e.id === eventId ? { ...e, attendees: [...(e.attendees || []), user.id] } : e));
    } catch (err) { toast.error(err.response?.data?.detail || 'RSVP failed'); }
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" /></div>;

  return (
    <div className="space-y-6 max-w-4xl" data-testid="portal-events">
      <div>
        <h1 className="text-2xl font-bold font-heading">Upcoming Events</h1>
        <p className="text-sm text-muted-foreground mt-1">{events.length} upcoming events</p>
      </div>

      {events.length === 0 ? (
        <Card className="shadow-soft rounded-xl">
          <CardContent className="py-12 text-center text-muted-foreground">No upcoming events</CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {events.map(event => {
            const isRegistered = (event.attendees || []).includes(user?.id);
            return (
              <Card key={event.id} className="shadow-soft rounded-xl" data-testid={`portal-event-${event.id}`}>
                <CardContent className="p-5">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-base font-semibold">{event.title}</h3>
                        <Badge variant="outline" className="text-xs">{event.type}</Badge>
                      </div>
                      <div className="flex flex-wrap gap-4 text-xs text-muted-foreground mt-2">
                        <span className="flex items-center gap-1"><Calendar size={12} />{event.date} {event.time && `at ${event.time}`}</span>
                        {event.location && <span className="flex items-center gap-1"><MapPin size={12} />{event.location}</span>}
                        <span className="flex items-center gap-1"><Users size={12} />{event.registered || 0}/{event.capacity || '∞'} registered</span>
                      </div>
                      {event.description && <p className="text-sm text-muted-foreground mt-2 line-clamp-2">{event.description}</p>}
                    </div>
                    <div className="ml-4">
                      {isRegistered ? (
                        <div className="flex flex-col items-end gap-1.5">
                          <Badge className="bg-green-100 text-green-700 gap-1"><Check size={12} /> Ticketed</Badge>
                          <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={() => navigate('/portal/tickets')} data-testid={`view-ticket-${event.id}`}>
                            View pass
                          </Button>
                        </div>
                      ) : (
                        <Button size="sm" onClick={() => handleRsvp(event.id)} data-testid={`rsvp-${event.id}`}>RSVP</Button>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
