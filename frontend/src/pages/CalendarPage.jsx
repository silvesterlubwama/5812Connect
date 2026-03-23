import React, { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight, Plus, Download, Repeat } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { eventsApi, exportApi } from '../services/api';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const typeColors = {
  service: 'bg-purple-500',
  conference: 'bg-amber-500',
  meeting: 'bg-slate-500',
  community: 'bg-teal-500',
};

export default function CalendarPage() {
  const today = new Date();
  const [current, setCurrent] = useState({ month: today.getMonth(), year: today.getFullYear() });
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showRecurring, setShowRecurring] = useState(false);
  const [recurForm, setRecurForm] = useState({
    title: '', type: 'service', location: '', time: '09:00',
    recurrence: 'weekly', day_of_week: '0', start_date: today.toISOString().split('T')[0],
    weeks: 12,
  });
  const [creatingRecurring, setCreatingRecurring] = useState(false);

  useEffect(() => {
    eventsApi.list()
      .then(res => setEvents(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const firstDay = new Date(current.year, current.month, 1).getDay();
  const daysInMonth = new Date(current.year, current.month + 1, 0).getDate();

  const prev = () => setCurrent(c => c.month === 0 ? { month: 11, year: c.year - 1 } : { ...c, month: c.month - 1 });
  const next = () => setCurrent(c => c.month === 11 ? { month: 0, year: c.year + 1 } : { ...c, month: c.month + 1 });

  const getEventsForDay = (day) => {
    const dateStr = `${current.year}-${String(current.month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    return events.filter(e => e.date === dateStr);
  };

  const isToday = (day) => day === today.getDate() && current.month === today.getMonth() && current.year === today.getFullYear();

  const monthEvents = events.filter(e => {
    const d = new Date(e.date);
    return d.getMonth() === current.month && d.getFullYear() === current.year;
  }).sort((a, b) => a.date.localeCompare(b.date));

  const cells = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  const downloadIcal = () => {
    const token = localStorage.getItem('5812_token');
    const url = exportApi.ical();
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.blob())
      .then(blob => {
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = '5812global-events.ics';
        link.click();
        toast.success('Calendar exported!');
      }).catch(() => toast.error('Export failed'));
  };

  const handleCreateRecurring = async (e) => {
    e.preventDefault();
    setCreatingRecurring(true);
    try {
      const startDate = new Date(recurForm.start_date);
      const created = [];
      for (let i = 0; i < recurForm.weeks; i++) {
        const eventDate = new Date(startDate);
        if (recurForm.recurrence === 'weekly') {
          eventDate.setDate(startDate.getDate() + i * 7);
        } else if (recurForm.recurrence === 'biweekly') {
          eventDate.setDate(startDate.getDate() + i * 14);
        } else {
          eventDate.setMonth(startDate.getMonth() + i);
        }
        const dateStr = eventDate.toISOString().split('T')[0];
        const res = await eventsApi.create({
          title: recurForm.title,
          type: recurForm.type,
          location: recurForm.location,
          time: recurForm.time,
          date: dateStr,
          status: 'upcoming',
          capacity: 100,
          is_recurring: true,
          recurrence_pattern: recurForm.recurrence,
        });
        created.push(res.data);
      }
      setEvents(prev => [...prev, ...created]);
      setShowRecurring(false);
      toast.success(`Created ${created.length} recurring events!`);
    } catch { toast.error('Failed to create recurring events'); }
    finally { setCreatingRecurring(false); }
  };

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold font-heading">Calendar</h1>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="gap-2 hidden sm:flex" onClick={downloadIcal} data-testid="ical-export-btn">
            <Download size={13} /> Export iCal
          </Button>
          <Button variant="outline" size="icon" onClick={prev}><ChevronLeft size={16} /></Button>
          <span className="text-sm font-semibold min-w-[150px] text-center">{MONTHS[current.month]} {current.year}</span>
          <Button variant="outline" size="icon" onClick={next}><ChevronRight size={16} /></Button>
          <Button variant="outline" size="sm" onClick={() => setCurrent({ month: today.getMonth(), year: today.getFullYear() })}>Today</Button>
          <Button size="sm" className="gap-1.5" asChild><Link to="/events"><Plus size={14} />New Event</Link></Button>
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setShowRecurring(true)} data-testid="recurring-events-btn"><Repeat size={14} />Recurring</Button>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3">
        {Object.entries(typeColors).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1.5">
            <div className={`w-2.5 h-2.5 rounded-full ${color}`} />
            <span className="text-xs text-muted-foreground capitalize">{type}</span>
          </div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="bg-card rounded-xl border border-border shadow-soft overflow-hidden">
        <div className="grid grid-cols-7 border-b border-border">
          {DAYS.map(d => (
            <div key={d} className="py-2 text-center text-xs font-semibold text-muted-foreground">{d}</div>
          ))}
        </div>
        <div className="grid grid-cols-7">
          {cells.map((day, i) => {
            const dayEvents = day ? getEventsForDay(day) : [];
            return (
              <div key={i} className={`min-h-[90px] p-1.5 border-b border-r border-border last:border-r-0 ${!day ? 'bg-muted/20' : 'hover:bg-accent/30 transition-colors'}`}>
                {day && (
                  <>
                    <span className={`text-sm font-medium inline-flex items-center justify-center w-7 h-7 rounded-full mb-1 ${isToday(day) ? 'bg-primary text-primary-foreground' : ''}`}>
                      {day}
                    </span>
                    <div className="space-y-0.5">
                      {dayEvents.slice(0, 2).map(ev => (
                        <div key={ev.id} className={`text-[10px] text-white px-1 py-0.5 rounded truncate ${typeColors[ev.type] || 'bg-slate-500'}`} title={ev.title}>
                          {ev.time && <span className="opacity-80">{ev.time} </span>}{ev.title}
                        </div>
                      ))}
                      {dayEvents.length > 2 && <p className="text-[10px] text-muted-foreground pl-1">+{dayEvents.length - 2} more</p>}
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* This month's events list */}
      <div>
        <h2 className="text-base font-semibold mb-3">Events in {MONTHS[current.month]}</h2>
        {loading ? (
          <div className="space-y-2">{[1,2,3].map(i => <div key={i} className="h-14 bg-muted animate-pulse rounded-lg" />)}</div>
        ) : monthEvents.length === 0 ? (
          <p className="text-sm text-muted-foreground">No events this month</p>
        ) : (
          <div className="space-y-2">
            {monthEvents.map(event => (
              <div key={event.id} className="flex items-center gap-4 p-3 rounded-lg border border-border bg-card hover:bg-accent/30 transition-colors">
                <div className={`w-3 h-3 rounded-full shrink-0 ${typeColors[event.type] || 'bg-slate-500'}`} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">{event.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(event.date).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
                    {event.time ? ` · ${event.time}` : ''}
                    {event.location ? ` · ${event.location}` : ''}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs text-muted-foreground">{event.registered ?? 0}/{event.capacity}</span>
                  <Badge variant={event.status === 'upcoming' ? 'outline' : 'secondary'} className="text-xs capitalize">{event.status}</Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recurring Events Dialog */}
      <Dialog open={showRecurring} onOpenChange={setShowRecurring}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Create Recurring Events</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateRecurring} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Event Title *</Label>
              <Input placeholder="e.g. Sunday Service" value={recurForm.title} onChange={e => setRecurForm({...recurForm, title: e.target.value})} required data-testid="recurring-title-input" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Type</Label>
                <Select value={recurForm.type} onValueChange={v => setRecurForm({...recurForm, type: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="service">Service</SelectItem>
                    <SelectItem value="meeting">Meeting</SelectItem>
                    <SelectItem value="conference">Conference</SelectItem>
                    <SelectItem value="community">Community</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Time</Label>
                <Input type="time" value={recurForm.time} onChange={e => setRecurForm({...recurForm, time: e.target.value})} />
              </div>
            </div>
            <div className="space-y-2"><Label>Location</Label>
              <Input placeholder="Where will it be?" value={recurForm.location} onChange={e => setRecurForm({...recurForm, location: e.target.value})} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Recurrence</Label>
                <Select value={recurForm.recurrence} onValueChange={v => setRecurForm({...recurForm, recurrence: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="weekly">Weekly</SelectItem>
                    <SelectItem value="biweekly">Bi-weekly</SelectItem>
                    <SelectItem value="monthly">Monthly</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Occurrences</Label>
                <Input type="number" min={1} max={52} value={recurForm.weeks} onChange={e => setRecurForm({...recurForm, weeks: parseInt(e.target.value) || 1})} />
              </div>
            </div>
            <div className="space-y-2"><Label>Start Date</Label>
              <Input type="date" value={recurForm.start_date} onChange={e => setRecurForm({...recurForm, start_date: e.target.value})} />
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowRecurring(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={creatingRecurring} data-testid="create-recurring-btn">{creatingRecurring ? 'Creating...' : 'Create Events'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
