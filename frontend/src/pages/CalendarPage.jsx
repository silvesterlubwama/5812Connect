import { secureStorage } from '../services/secureStorage';
import React, { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight, Plus, Download, Upload, Repeat } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { eventsApi, exportApi, outreachApi, tasksApi } from '../services/api';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const typeColors = {
  service: 'bg-purple-500',
  conference: 'bg-amber-500',
  meeting: 'bg-slate-500',
  community: 'bg-teal-500',
  outreach: 'bg-pink-500',
  workshop: 'bg-violet-500',
  training: 'bg-cyan-500',
  social: 'bg-orange-500',
  task: 'bg-blue-500',
  imported: 'bg-gray-300',
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
    weeks: 12, interval: 1, nth_week: 1, nth_month_day: 'first',
  });
  const [creatingRecurring, setCreatingRecurring] = useState(false);
  const [showImportCal, setShowImportCal] = useState(false);
  const [icalContent, setIcalContent] = useState('');
  const [importingCal, setImportingCal] = useState(false);
  const [editEvent, setEditEvent] = useState(null);
  const [editForm, setEditForm] = useState({ title: '', date: '', time: '', end_time: '', location: '', description: '', type: 'service', capacity: 100, is_public: true });
  const [savingEdit, setSavingEdit] = useState(false);

  useEffect(() => {
    Promise.all([
      eventsApi.list(),
      outreachApi.sessions().catch(() => ({ data: [] })),
      outreachApi.programs().catch(() => ({ data: [] })),
      tasksApi.list().catch(() => ({ data: [] })),
    ]).then(([evtRes, sessRes, progRes, taskRes]) => {
      const allEvents = evtRes.data || [];
      // Convert outreach sessions to event-like objects for the calendar
      const programs = progRes.data || [];
      const progMap = Object.fromEntries(programs.map(p => [p.id, p]));
      const sessionEvents = (sessRes.data || []).filter(s => s.date).map(s => {
        const prog = progMap[s.program_id];
        return {
          id: s.id,
          title: prog ? `${prog.name} (Session)` : 'Outreach Session',
          type: 'outreach',
          date: s.date,
          time: s.time || '',
          location: s.location || prog?.location || '',
          status: 'completed',
          registered: s.attendees || 0,
          capacity: prog?.target || 100,
          _isSession: true,
        };
      });
      // iter 265 — Calendar shows tasks assigned to the current user OR
      // that they created. Previously it showed EVERY task with a due
      // date across the campus, which cluttered the view and buried the
      // things the viewer actually owns.
      const currentUser = secureStorage.get('user') || {};
      const myId = currentUser.id;
      const taskEvents = (taskRes.data || [])
        .filter(t => t.due_date && !t.is_archived)
        .filter(t => !myId
          || t.assignee_id === myId
          || (t.assignees || []).includes(myId)
          || t.created_by === myId
          || t.reporter_id === myId)
        .map(t => ({
          id: `task_${t.id}`,
          title: `${t.status === 'done' ? '✓ ' : ''}${t.title || 'Task'}`,
          type: 'task',
          date: (t.due_date || '').slice(0, 10),
          time: '',
          location: t.board_name || '',
          status: t.status,
          _isTask: true,
          _taskId: t.id,
          _boardId: t.board_id,
        }));
      // Merge: avoid duplicating sessions that already have a matching event
      const existingDates = new Set(allEvents.map(e => `${e.title}_${e.date}`));
      const newSessions = sessionEvents.filter(s => !existingDates.has(`${s.title}_${s.date}`));
      setEvents([...allEvents, ...newSessions, ...taskEvents]);
    }).catch(() => {})
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
    const token = secureStorage.getToken();
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

  const handleImportIcal = async () => {
    if (!icalContent.trim()) return;
    setImportingCal(true);
    try {
      const res = await exportApi.icalImport({ ical_content: icalContent });
      toast.success(res.data.message || `Imported ${res.data.imported} events`);
      setShowImportCal(false); setIcalContent('');
      // Refresh events
      const evRes = await eventsApi.list();
      setEvents(evRes.data);
    } catch (err) { toast.error('Import failed — check iCal format'); }
    finally { setImportingCal(false); }
  };

  const handleImportFile = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => setIcalContent(ev.target.result);
    reader.readAsText(file);
  };

  const openEditEvent = (ev) => {
    if (ev._isSession) return; // Don't edit outreach sessions from calendar
    if (ev._isTask) {
      // Navigate to the Boards page with the task's board; task card will open via board UI
      window.location.href = `/boards?board=${encodeURIComponent(ev._boardId || '')}&task=${encodeURIComponent(ev._taskId || '')}`;
      return;
    }
    setEditEvent(ev);
    setEditForm({
      title: ev.title || '', date: ev.date || '', time: ev.time || '', end_time: ev.end_time || '',
      location: ev.location || '', description: ev.description || '', type: ev.type || 'service',
      capacity: ev.capacity || 100, is_public: ev.is_public ?? true,
    });
  };

  const handleSaveEvent = async (e) => {
    e.preventDefault();
    setSavingEdit(true);
    try {
      const res = await eventsApi.update(editEvent.id, editForm);
      setEvents(prev => prev.map(ev => ev.id === editEvent.id ? { ...ev, ...res.data } : ev));
      setEditEvent(null);
      toast.success('Event updated!');
    } catch { toast.error('Failed to update event'); }
    finally { setSavingEdit(false); }
  };

  const handleDeleteEvent = async (eventId) => {
    if (!window.confirm('Delete this event?')) return;
    try {
      await eventsApi.delete(eventId);
      setEvents(prev => prev.filter(ev => ev.id !== eventId));
      setEditEvent(null);
      toast.success('Event deleted');
    } catch { toast.error('Failed to delete event'); }
  };

  const handleCreateRecurring = async (e) => {
    e.preventDefault();
    setCreatingRecurring(true);
    try {
      const payload = {
        title: recurForm.title,
        type: recurForm.type,
        location: recurForm.location,
        time: recurForm.time,
        pattern: recurForm.recurrence,
        start_date: recurForm.start_date,
        occurrences: parseInt(recurForm.weeks) || 12,
        interval: parseInt(recurForm.interval) || 1,
        day_of_week: parseInt(recurForm.day_of_week) || 0,
        nth_week: parseInt(recurForm.nth_week) || 1,
        day_of_month: parseInt(recurForm.nth_month_day) || 1,
        end_date: recurForm.end_date || undefined,
      };
      const res = await exportApi.generateRecurring(payload);
      setEvents(prev => [...prev, ...(res.data.events || [])]);
      setShowRecurring(false);
      toast.success(`Created ${res.data.created} recurring events!`);
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
          <Button variant="outline" size="sm" className="gap-2 hidden sm:flex" onClick={() => setShowImportCal(true)} data-testid="ical-import-btn">
            <Upload size={13} /> Import iCal
          </Button>
          <Button variant="outline" size="icon" onClick={prev}><ChevronLeft size={16} /></Button>
          <span className="text-sm font-semibold min-w-[150px] text-center cursor-pointer" onClick={() => setCurrent(c => ({ ...c, year: c.year - 1 }))} title="Click for previous year">{MONTHS[current.month]} {current.year}</span>
          <Button variant="outline" size="icon" onClick={next}><ChevronRight size={16} /></Button>
          <Button variant="outline" size="sm" onClick={() => setCurrent({ month: today.getMonth(), year: today.getFullYear() })}>Today</Button>
          <div className="hidden sm:flex items-center gap-1 border rounded-lg px-1">
            <Button variant="ghost" size="sm" className="h-7 text-xs px-1.5" onClick={() => setCurrent(c => ({ ...c, year: c.year - 1 }))} data-testid="prev-year-btn">{current.year - 1}</Button>
            <span className="text-xs font-bold text-primary">{current.year}</span>
            <Button variant="ghost" size="sm" className="h-7 text-xs px-1.5" onClick={() => setCurrent(c => ({ ...c, year: c.year + 1 }))} data-testid="next-year-btn">{current.year + 1}</Button>
          </div>
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
              <div key={day ? `day-${day}` : `empty-${i}`} className={`min-h-[90px] p-1.5 border-b border-r border-border last:border-r-0 ${!day ? 'bg-muted/20' : 'hover:bg-accent/30 transition-colors'}`}>
                {day && (
                  <>
                    <span className={`text-sm font-medium inline-flex items-center justify-center w-7 h-7 rounded-full mb-1 ${isToday(day) ? 'bg-primary text-primary-foreground' : ''}`}>
                      {day}
                    </span>
                    <div className="space-y-0.5">
                      {dayEvents.slice(0, 2).map(ev => (
                        <div key={ev.id} onClick={() => openEditEvent(ev)} className={`text-[10px] px-1 py-0.5 rounded truncate cursor-pointer hover:opacity-80 ${ev.type === 'imported' ? 'text-gray-400 bg-transparent border border-gray-200' : `text-white ${typeColors[ev.type] || 'bg-slate-500'}`}`} title={ev.title} data-testid={`cal-event-${ev.id}`}>
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
              <div key={event.id} onClick={() => openEditEvent(event)} className={`flex items-center gap-4 p-3 rounded-lg border transition-colors cursor-pointer ${event.type === 'imported' ? 'border-gray-200 bg-transparent hover:bg-gray-50' : 'border-border bg-card hover:bg-accent/30'}`} data-testid={`event-list-${event.id}`}>
                <div className={`w-3 h-3 rounded-full shrink-0 ${typeColors[event.type] || 'bg-slate-500'}`} />
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-medium ${event.type === 'imported' ? 'text-gray-400' : ''}`}>{event.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(event.date).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
                    {event.time ? ` · ${event.time}` : ''}
                    {event.location ? ` · ${event.location}` : ''}
                    {event.type === 'imported' && <span className="ml-1 text-gray-300">· Imported</span>}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {event.type !== 'imported' && <span className="text-xs text-muted-foreground">{event.registered ?? 0}/{event.capacity}</span>}
                  <Badge variant={event.status === 'upcoming' ? 'outline' : 'secondary'} className={`text-xs capitalize ${event.type === 'imported' ? 'border-gray-200 text-gray-400' : ''}`}>{event.type === 'imported' ? 'imported' : event.status}</Badge>
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
                    <SelectItem value="outreach">Outreach</SelectItem>
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
              <div className="space-y-2"><Label>Recurrence Pattern</Label>
                <Select value={recurForm.recurrence} onValueChange={v => setRecurForm({...recurForm, recurrence: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="daily">Daily</SelectItem>
                    <SelectItem value="weekly">Every N Weeks</SelectItem>
                    <SelectItem value="biweekly">Bi-weekly</SelectItem>
                    <SelectItem value="monthly">Every N Months</SelectItem>
                    <SelectItem value="yearly">Yearly</SelectItem>
                    <SelectItem value="nth_week">Nth Weekday of Month</SelectItem>
                    <SelectItem value="nth_month">Nth Day of Month</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Occurrences</Label>
                <Input type="number" min={1} max={52} value={recurForm.weeks} onChange={e => setRecurForm({...recurForm, weeks: parseInt(e.target.value) || 1})} />
              </div>
            </div>
            {['daily', 'weekly', 'monthly', 'yearly'].includes(recurForm.recurrence) && (
              <div className="space-y-2"><Label>Every N {{ weekly: 'weeks', daily: 'days', yearly: 'years', monthly: 'months' }[recurForm.recurrence] || 'units'}</Label>
                <Input type="number" min={1} max={recurForm.recurrence === 'yearly' ? 5 : 12} value={recurForm.interval} onChange={e => setRecurForm({...recurForm, interval: parseInt(e.target.value) || 1})} />
              </div>
            )}
            <div className="space-y-2"><Label>End Date (optional)</Label>
              <Input type="date" value={recurForm.end_date || ''} onChange={e => setRecurForm({...recurForm, end_date: e.target.value})} data-testid="recurrence-end-date" />
              <p className="text-xs text-muted-foreground">Events won't be created past this date</p>
            </div>
            {recurForm.recurrence === 'nth_week' && (
              <div className="grid grid-cols-2 gap-3 p-3 bg-muted/50 rounded-lg">
                <div className="space-y-2"><Label>Which Week</Label>
                  <Select value={String(recurForm.nth_week)} onValueChange={v => setRecurForm({...recurForm, nth_week: parseInt(v)})}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="1">1st</SelectItem>
                      <SelectItem value="2">2nd</SelectItem>
                      <SelectItem value="3">3rd</SelectItem>
                      <SelectItem value="4">4th</SelectItem>
                      <SelectItem value="-1">Last</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2"><Label>Day of Week</Label>
                  <Select value={recurForm.day_of_week} onValueChange={v => setRecurForm({...recurForm, day_of_week: v})}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="0">Sunday</SelectItem>
                      <SelectItem value="1">Monday</SelectItem>
                      <SelectItem value="2">Tuesday</SelectItem>
                      <SelectItem value="3">Wednesday</SelectItem>
                      <SelectItem value="4">Thursday</SelectItem>
                      <SelectItem value="5">Friday</SelectItem>
                      <SelectItem value="6">Saturday</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="col-span-2 space-y-2"><Label>Every N months</Label>
                  <Input type="number" min={1} max={12} value={recurForm.interval} onChange={e => setRecurForm({...recurForm, interval: parseInt(e.target.value) || 1})} />
                </div>
              </div>
            )}
            {recurForm.recurrence === 'nth_month' && (
              <div className="grid grid-cols-2 gap-3 p-3 bg-muted/50 rounded-lg">
                <div className="space-y-2"><Label>Day of Month</Label>
                  <Input type="number" min={1} max={31} value={recurForm.nth_month_day} onChange={e => setRecurForm({...recurForm, nth_month_day: e.target.value})} placeholder="e.g. 15" />
                </div>
                <div className="space-y-2"><Label>Every N months</Label>
                  <Input type="number" min={1} max={12} value={recurForm.interval} onChange={e => setRecurForm({...recurForm, interval: parseInt(e.target.value) || 1})} />
                </div>
              </div>
            )}
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

      {/* Import iCal Modal */}
      <Dialog open={showImportCal} onOpenChange={setShowImportCal}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Import Calendar (iCal)</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Upload .ics file</Label>
              <Input type="file" accept=".ics,.ical,.ifb,.icalendar" onChange={handleImportFile} data-testid="ical-file-input" />
            </div>
            <div className="space-y-2">
              <Label>Or paste iCal content</Label>
              <Textarea rows={8} placeholder="BEGIN:VCALENDAR&#10;VERSION:2.0&#10;..." value={icalContent} onChange={e => setIcalContent(e.target.value)} data-testid="ical-content-input" />
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowImportCal(false)}>Cancel</Button>
              <Button className="flex-1 gap-2" onClick={handleImportIcal} disabled={importingCal || !icalContent.trim()} data-testid="import-ical-btn">
                <Upload size={14} /> {importingCal ? 'Importing...' : 'Import Events'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Event Dialog */}
      <Dialog open={!!editEvent} onOpenChange={(open) => !open && setEditEvent(null)}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Edit Event</DialogTitle></DialogHeader>
          <form onSubmit={handleSaveEvent} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Title *</Label>
              <Input value={editForm.title} onChange={e => setEditForm({...editForm, title: e.target.value})} required data-testid="edit-event-title" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Date</Label>
                <Input type="date" value={editForm.date} onChange={e => setEditForm({...editForm, date: e.target.value})} data-testid="edit-event-date" />
              </div>
              <div className="space-y-2"><Label>Time</Label>
                <Input type="time" value={editForm.time} onChange={e => setEditForm({...editForm, time: e.target.value})} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>End Time</Label>
                <Input type="time" value={editForm.end_time} onChange={e => setEditForm({...editForm, end_time: e.target.value})} />
              </div>
              <div className="space-y-2"><Label>Type</Label>
                <Select value={editForm.type} onValueChange={v => setEditForm({...editForm, type: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.keys(typeColors).filter(t => t !== 'imported').map(t => (
                      <SelectItem key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2"><Label>Location</Label>
              <Input value={editForm.location} onChange={e => setEditForm({...editForm, location: e.target.value})} />
            </div>
            <div className="space-y-2"><Label>Description</Label>
              <Textarea rows={3} value={editForm.description} onChange={e => setEditForm({...editForm, description: e.target.value})} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Capacity</Label>
                <Input type="number" min={1} value={editForm.capacity} onChange={e => setEditForm({...editForm, capacity: parseInt(e.target.value) || 1})} />
              </div>
              <div className="flex items-center gap-2 pt-6">
                <input type="checkbox" id="edit-public" checked={editForm.is_public} onChange={e => setEditForm({...editForm, is_public: e.target.checked})} />
                <Label htmlFor="edit-public" className="cursor-pointer">Public Event</Label>
              </div>
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="destructive" size="sm" onClick={() => handleDeleteEvent(editEvent?.id)} data-testid="delete-event-btn">Delete</Button>
              <div className="flex-1" />
              <Button type="button" variant="outline" onClick={() => setEditEvent(null)}>Cancel</Button>
              <Button type="submit" disabled={savingEdit} data-testid="save-event-btn">{savingEdit ? 'Saving...' : 'Save'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
