// Unified Calendar page — replaces the legacy split of /events + /calendar.
// One canvas for events + tasks, three view modes (month/week/day), a
// visibility toggle for task scope, an event/task detail drawer, quick create,
// and shareable public feed URLs (JSON + iCal).
import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { ChevronLeft, ChevronRight, Plus, Download, Upload, Repeat, Share2, Copy, Check, Link as LinkIcon, X, Calendar as CalIcon, MapPin, Filter, Clock, Users as UsersIcon } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { eventsApi, exportApi, outreachApi, tasksApi, publicCalendarApi, boardsApi, locationsApi, holidaysApi } from '../services/api';
import { secureStorage } from '../services/secureStorage';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
// iter 281 — new palette per user request:
//   outreach = green, tasks = blue-light, US holidays = blue-deep, UG = red
// Every "user event" (i.e. an event YOU created) is coloured brown instead
// of using the type colour, so a leader can see their own contributions at
// a glance. The type map here still drives the default for events created
// by other people.
const TYPE_COLORS = {
  service:    'bg-purple-500',
  conference: 'bg-amber-500',
  meeting:    'bg-slate-500',
  community:  'bg-teal-500',
  outreach:   'bg-green-600',
  workshop:   'bg-violet-500',
  training:   'bg-cyan-500',
  social:     'bg-orange-500',
  task:       'bg-sky-400',
  imported:   'bg-gray-300',
  holiday_us: 'bg-blue-700',
  holiday_ug: 'bg-red-600',
  user_event: 'bg-amber-800',   // brown-ish, for events the current user authored
};
const VIEW_MODES = ['month', 'week', 'day'];
const TASK_SCOPES = [
  { value: 'mine', label: 'My tasks only' },
  { value: 'campus', label: 'All tasks in my campus' },
  { value: 'off', label: 'Hide tasks' },
];

const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const startOfWeek = (d) => { const x = new Date(d); x.setDate(x.getDate() - x.getDay()); x.setHours(0,0,0,0); return x; };
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };

export default function CalendarPage() {
  const { user } = useAuth();
  const isAdminOrManager = ['admin', 'system_admin', 'manager', 'director', 'executive director'].includes((user?.role || '').toLowerCase());
  const today = new Date();
  const [cursor, setCursor] = useState(new Date());
  const [view, setView] = useState(() => localStorage.getItem('5812_cal_view') || 'month');
  const [taskScope, setTaskScope] = useState(() => localStorage.getItem('5812_cal_task_scope') || 'mine');
  const [rawEvents, setRawEvents] = useState([]);
  const [rawTasks, setRawTasks] = useState([]);
  const [holidays, setHolidays] = useState([]);
  const [showHolidays, setShowHolidays] = useState(() => localStorage.getItem('5812_cal_holidays') !== 'off');
  const [loading, setLoading] = useState(true);

  // Selected item drawer & create dialog
  const [selected, setSelected] = useState(null);
  const [editMode, setEditMode] = useState(false);
  const [editForm, setEditForm] = useState({});
  const [savingEdit, setSavingEdit] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [createKind, setCreateKind] = useState('event');
  const [createForm, setCreateForm] = useState({ title: '', type: 'meeting', date: iso(today), time: '', end_time: '', location: '', description: '', is_public: false, capacity: 100, board_id: '', priority: 'medium' });
  const [saving, setSaving] = useState(false);
  const [boards, setBoards] = useState([]);
  const [locations, setLocations] = useState([]);
  const [showShare, setShowShare] = useState(false);
  const [showRecurring, setShowRecurring] = useState(false);
  const [showImportCal, setShowImportCal] = useState(false);

  useEffect(() => localStorage.setItem('5812_cal_view', view), [view]);
  useEffect(() => localStorage.setItem('5812_cal_task_scope', taskScope), [taskScope]);
  useEffect(() => localStorage.setItem('5812_cal_holidays', showHolidays ? 'on' : 'off'), [showHolidays]);

  // Pull public holidays for the current + next year so month/week/day views
  // are always populated regardless of which month the user paged to. This
  // is a public endpoint, cached in state so no repeated fetches during nav.
  const yearKey = cursor.getFullYear();
  useEffect(() => {
    holidaysApi.list({ year: yearKey, year_to: yearKey + 1, country: 'all' })
      .then(r => setHolidays(r.data || []))
      .catch(() => setHolidays([]));
  }, [yearKey]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [evtRes, sessRes, progRes, taskRes, boardsRes, locsRes] = await Promise.all([
        eventsApi.list().catch(() => ({ data: [] })),
        outreachApi.sessions().catch(() => ({ data: [] })),
        outreachApi.programs().catch(() => ({ data: [] })),
        tasksApi.list().catch(() => ({ data: [] })),
        boardsApi.list().catch(() => ({ data: [] })),
        locationsApi.list().catch(() => ({ data: [] })),
      ]);
      // Convert outreach sessions to event-like objects
      const progMap = Object.fromEntries((progRes.data || []).map(p => [p.id, p]));
      const sessionEvents = (sessRes.data || []).filter(s => s.date).map(s => {
        const prog = progMap[s.program_id];
        return {
          id: s.id, title: prog ? `${prog.name} (Session)` : 'Outreach Session',
          type: 'outreach', date: s.date, time: s.time || '',
          location: s.location || prog?.location || '',
          status: 'completed', _isSession: true,
        };
      });
      const existingKey = new Set((evtRes.data || []).map(e => `${e.title}_${e.date}`));
      const newSessions = sessionEvents.filter(s => !existingKey.has(`${s.title}_${s.date}`));
      setRawEvents([...(evtRes.data || []), ...newSessions]);
      setRawTasks((taskRes.data || []).filter(t => t.due_date && !t.is_archived));
      setBoards(boardsRes.data || []);
      setLocations(locsRes.data || []);
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { loadAll(); }, [loadAll]);

  // Expand multi-day events into every day and merge tasks (scoped by taskScope).
  const items = useMemo(() => {
    const out = [];
    for (const ev of rawEvents) {
      if (!ev.end_date || ev.end_date === ev.date) { out.push({ ...ev, _kind: 'event' }); continue; }
      try {
        const s = new Date(ev.date + 'T00:00:00');
        const e = new Date(ev.end_date + 'T00:00:00');
        if (isNaN(s) || isNaN(e) || e < s) { out.push({ ...ev, _kind: 'event' }); continue; }
        let c = new Date(s); let idx = 1;
        while (c <= e) {
          out.push({ ...ev, _kind: 'event', date: iso(c), id: iso(c) === ev.date ? ev.id : `${ev.id}_d${idx}`, _multiDay: true });
          c = addDays(c, 1); idx += 1;
        }
      } catch { out.push({ ...ev, _kind: 'event' }); }
    }
    if (taskScope !== 'off') {
      const myId = user?.id;
      const filtered = rawTasks.filter(t => {
        if (taskScope === 'campus') return true; // backend already scopes to campus
        return t.assignee_id === myId || (t.assignees || []).includes(myId) || t.created_by === myId || t.reporter_id === myId;
      });
      for (const t of filtered) {
        out.push({
          _kind: 'task', id: `task_${t.id}`, _taskId: t.id, _boardId: t.board_id,
          title: `${t.status === 'done' ? '✓ ' : ''}${t.title || 'Task'}`,
          type: 'task', date: (t.due_date || '').slice(0, 10), time: '',
          location: t.board_name || '', status: t.status, priority: t.priority,
          description: t.description || '',
        });
      }
    }
    // Merge holidays as read-only calendar items with country-specific type
    if (showHolidays) {
      for (const h of holidays) {
        out.push({
          _kind: 'holiday', _readOnly: true, id: `hol_${h.country}_${h.date}`,
          title: h.name, type: h.country === 'US' ? 'holiday_us' : 'holiday_ug',
          date: h.date, time: '', location: h.country === 'US' ? '🇺🇸 United States' : '🇺🇬 Uganda',
          description: `${h.country === 'US' ? 'US Federal' : 'Uganda Public'} Holiday`,
        });
      }
    }
    // Flag any event authored by the current user so it renders in "user" brown
    if (user?.id) {
      for (const it of out) {
        if (it._kind === 'event' && (it.created_by === user.id || it.reporter_id === user.id)) {
          it._authoredByMe = true;
        }
      }
    }
    return out;
  }, [rawEvents, rawTasks, taskScope, user?.id, holidays, showHolidays]);

  // Item bucketing by ISO date for fast rendering
  const byDate = useMemo(() => {
    const m = new Map();
    for (const it of items) {
      if (!it.date) continue;
      if (!m.has(it.date)) m.set(it.date, []);
      m.get(it.date).push(it);
    }
    for (const arr of m.values()) arr.sort((a, b) => (a.time || 'z').localeCompare(b.time || 'z'));
    return m;
  }, [items]);

  const goPrev = () => {
    const c = new Date(cursor);
    if (view === 'month') c.setMonth(c.getMonth() - 1);
    else if (view === 'week') c.setDate(c.getDate() - 7);
    else c.setDate(c.getDate() - 1);
    setCursor(c);
  };
  const goNext = () => {
    const c = new Date(cursor);
    if (view === 'month') c.setMonth(c.getMonth() + 1);
    else if (view === 'week') c.setDate(c.getDate() + 7);
    else c.setDate(c.getDate() + 1);
    setCursor(c);
  };
  const goToday = () => setCursor(new Date());

  const headerLabel = useMemo(() => {
    if (view === 'month') return `${MONTHS[cursor.getMonth()]} ${cursor.getFullYear()}`;
    if (view === 'week') {
      const s = startOfWeek(cursor); const e = addDays(s, 6);
      return `${s.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} – ${e.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`;
    }
    return cursor.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
  }, [cursor, view]);

  // ── Actions ──────────────────────────────────────────────────────────
  const openItem = (it) => {
    if (it._kind === 'task') {
      // Route to Boards page for full task edit
      window.location.href = `/boards?board=${encodeURIComponent(it._boardId || '')}&task=${encodeURIComponent(it._taskId || '')}`;
      return;
    }
    if (it._isSession) return;
    setSelected(it);
    setEditMode(false);
    setEditForm({
      title: it.title || '', date: it.date || '', end_date: it.end_date || '',
      time: it.time || '', end_time: it.end_time || '', location: it.location || '',
      description: it.description || '', type: it.type || 'meeting',
      capacity: it.capacity || 100, is_public: it.is_public ?? false,
    });
  };
  const saveEdit = async (e) => {
    e.preventDefault(); setSavingEdit(true);
    try {
      const payload = { ...editForm };
      if (!payload.end_date || payload.end_date === payload.date) delete payload.end_date;
      const res = await eventsApi.update(selected.id, payload);
      toast.success('Event updated');
      setSelected({ ...selected, ...res.data });
      setEditMode(false);
      loadAll();
    } catch (err) {
      if (err.response?.status === 409) toast.error('Venue already booked for that time');
      else toast.error('Failed to update event');
    }
    finally { setSavingEdit(false); }
  };
  const deleteEvent = async () => {
    if (!selected || !window.confirm('Delete this event?')) return;
    try { await eventsApi.delete(selected.id); toast.success('Event deleted'); setSelected(null); loadAll(); }
    catch { toast.error('Failed to delete'); }
  };
  const submitCreate = async (e) => {
    e.preventDefault(); setSaving(true);
    try {
      if (createKind === 'event') {
        const payload = { title: createForm.title, type: createForm.type, date: createForm.date, time: createForm.time || undefined, end_time: createForm.end_time || undefined, location: createForm.location, description: createForm.description, is_public: createForm.is_public, capacity: parseInt(createForm.capacity) || 100 };
        await eventsApi.create(payload);
        toast.success('Event created');
      } else {
        if (!createForm.board_id) { toast.error('Please pick a board for the task'); setSaving(false); return; }
        // Board tasks require a list; grab first list of the chosen board
        const boardRes = await boardsApi.get(createForm.board_id);
        const lists = boardRes.data?.lists || [];
        if (!lists.length) { toast.error('Board has no lists — open Boards to add one'); setSaving(false); return; }
        await tasksApi.create({
          title: createForm.title, description: createForm.description,
          board_id: createForm.board_id, list_id: lists[0].id,
          due_date: createForm.date, priority: createForm.priority,
          assignees: [user?.id], status: 'todo',
        });
        toast.success('Task created');
      }
      setShowCreate(false);
      setCreateForm({ title: '', type: 'meeting', date: iso(cursor), time: '', end_time: '', location: '', description: '', is_public: false, capacity: 100, board_id: '', priority: 'medium' });
      loadAll();
    } catch (err) {
      if (err.response?.status === 409) toast.error('Venue already booked for that time');
      else toast.error(err.response?.data?.detail || 'Failed to create');
    }
    finally { setSaving(false); }
  };

  const [shareLinks, setShareLinks] = useState(null);
  const [shareConfigs, setShareConfigs] = useState([]);
  const [shareConfigsLoading, setShareConfigsLoading] = useState(false);
  const openShare = async () => {
    setShowShare(true);
    if (!shareLinks) {
      try { const r = await publicCalendarApi.shareLinks(); setShareLinks(r.data); }
      catch { toast.error('Could not load share links'); }
    }
    setShareConfigsLoading(true);
    try { const r = await publicCalendarApi.listConfigs(); setShareConfigs(r.data || []); }
    catch { /* silent */ }
    setShareConfigsLoading(false);
  };
  const backend = process.env.REACT_APP_BACKEND_URL || '';
  const buildIcalUrl = (scope, id, token) => {
    if (scope === 'global') return `${backend}/api/public/calendar/global.ics?token=${token}`;
    if (scope === 'user') return `${backend}/api/public/calendar/user/${token}.ics`;
    return `${backend}/api/public/calendar/location/${id}.ics?token=${token}`;
  };
  const buildViewUrl = (scope, id, token) => {
    if (scope === 'global') return `${window.location.origin}/p/calendar/global/${token}`;
    if (scope === 'user') return `${window.location.origin}/p/calendar/user/${token}`;
    return `${window.location.origin}/p/calendar/location/${id}/${token}`;
  };
  const createShareConfig = async (payload) => {
    try {
      const r = await publicCalendarApi.createConfig(payload);
      setShareConfigs(list => [r.data, ...list]);
      toast.success('Share link created');
    } catch { toast.error('Could not create share link'); }
  };
  const revokeShareConfig = async (id) => {
    if (!window.confirm('Revoke this share link? Anyone using it will lose access.')) return;
    try { await publicCalendarApi.deleteConfig(id); setShareConfigs(list => list.filter(c => c.id !== id)); toast.success('Link revoked'); }
    catch { toast.error('Could not revoke link'); }
  };

  // ── Rendering ────────────────────────────────────────────────────────
  const CellItem = ({ it }) => (
    <div onClick={(e) => { e.stopPropagation(); openItem(it); }}
         className={`text-[10px] px-1 py-0.5 rounded truncate cursor-pointer hover:opacity-80 ${it._kind === 'task' ? `${TYPE_COLORS.task} text-white` : it._kind === 'holiday' ? `text-white ${TYPE_COLORS[it.type] || 'bg-slate-500'}` : `text-white ${it._authoredByMe ? TYPE_COLORS.user_event : (TYPE_COLORS[it.type] || 'bg-slate-500')}`}`}
         title={it.title} data-testid={`cal-item-${it.id}`}>
      {it.time && <span className="opacity-80">{it.time} </span>}{it.title}
    </div>
  );

  const MonthGrid = () => {
    const y = cursor.getFullYear(), m = cursor.getMonth();
    const firstDay = new Date(y, m, 1).getDay();
    const daysInMonth = new Date(y, m + 1, 0).getDate();
    const cells = [];
    for (let i = 0; i < firstDay; i++) cells.push(null);
    for (let d = 1; d <= daysInMonth; d++) cells.push(d);
    return (
      <div className="bg-card rounded-xl border border-border shadow-soft overflow-hidden">
        <div className="grid grid-cols-7 border-b border-border">{DAYS.map(d => <div key={d} className="py-2 text-center text-xs font-semibold text-muted-foreground">{d}</div>)}</div>
        <div className="grid grid-cols-7">
          {cells.map((d, i) => {
            const dateStr = d ? `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}` : null;
            const dayItems = dateStr ? (byDate.get(dateStr) || []) : [];
            const isToday = d === today.getDate() && m === today.getMonth() && y === today.getFullYear();
            return (
              <div key={i} onClick={() => d && (setCreateForm(f => ({ ...f, date: dateStr })), setShowCreate(true))}
                   className={`min-h-[100px] p-1.5 border-b border-r border-border last:border-r-0 ${!d ? 'bg-muted/20' : 'hover:bg-accent/20 transition-colors cursor-pointer'}`}>
                {d && (
                  <>
                    <span className={`text-sm font-medium inline-flex items-center justify-center w-7 h-7 rounded-full mb-1 ${isToday ? 'bg-primary text-primary-foreground' : ''}`}>{d}</span>
                    <div className="space-y-0.5">
                      {dayItems.slice(0, 3).map(it => <CellItem key={it.id} it={it} />)}
                      {dayItems.length > 3 && <p className="text-[10px] text-muted-foreground pl-1">+{dayItems.length - 3} more</p>}
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const WeekOrDayGrid = ({ days }) => {
    // Time-based grid: 6am → 10pm rows. Left column = time labels; each column = one day.
    const hours = Array.from({ length: 17 }, (_, i) => 6 + i); // 6..22
    const cols = days.length;
    const laneFor = (it) => {
      const t = (it.time || '00:00');
      const [hh, mm] = t.split(':').map(Number);
      const top = (Math.max(0, (hh || 0) - 6) + (mm || 0) / 60) * 40; // 40px per hour
      const endT = it.end_time || t;
      const [eh, em] = (endT || '').split(':').map(Number);
      const durH = Math.max(0.5, ((eh || hh) - hh) + ((em || mm) - mm) / 60);
      return { top, height: Math.max(24, durH * 40) };
    };
    return (
      <div className="bg-card rounded-xl border border-border shadow-soft overflow-hidden">
        <div className="grid" style={{ gridTemplateColumns: `56px repeat(${cols}, minmax(0, 1fr))` }}>
          <div className="border-b border-r border-border bg-muted/30" />
          {days.map(d => {
            const isToday = iso(d) === iso(today);
            return (
              <div key={iso(d)} className={`text-center py-2 border-b border-r border-border last:border-r-0 text-xs ${isToday ? 'bg-primary/10 font-bold text-primary' : ''}`}>
                <div>{d.toLocaleDateString('en-US', { weekday: 'short' })}</div>
                <div className={`text-lg ${isToday ? '' : 'font-semibold'}`}>{d.getDate()}</div>
              </div>
            );
          })}
        </div>
        <div className="grid relative" style={{ gridTemplateColumns: `56px repeat(${cols}, minmax(0, 1fr))` }}>
          <div>
            {hours.map(h => <div key={h} className="h-10 pr-1 text-right text-[10px] text-muted-foreground border-b border-border">{h}:00</div>)}
          </div>
          {days.map(d => {
            const dayItems = byDate.get(iso(d)) || [];
            return (
              <div key={iso(d)} className="relative border-r border-border last:border-r-0" onClick={() => (setCreateForm(f => ({ ...f, date: iso(d) })), setShowCreate(true))}>
                {hours.map(h => <div key={h} className="h-10 border-b border-border hover:bg-accent/10 cursor-pointer" />)}
                {dayItems.map(it => {
                  const { top, height } = laneFor(it);
                  const color = it._kind === 'task'
                    ? TYPE_COLORS.task
                    : it._kind === 'holiday'
                      ? (TYPE_COLORS[it.type] || 'bg-slate-500')
                      : (it._authoredByMe ? TYPE_COLORS.user_event : (TYPE_COLORS[it.type] || 'bg-slate-500'));
                  return (
                    <div key={it.id} onClick={(e) => { e.stopPropagation(); openItem(it); }}
                         className={`absolute left-1 right-1 rounded px-1.5 py-0.5 text-[10px] text-white cursor-pointer hover:opacity-90 ${color} overflow-hidden`}
                         style={{ top, height }} data-testid={`cal-item-${it.id}`}>
                      <div className="font-semibold truncate">{it.title}</div>
                      {it.time && <div className="opacity-80">{it.time}{it.end_time ? `–${it.end_time}` : ''}</div>}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const weekDays = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(startOfWeek(cursor), i)), [cursor]);
  const dayDays = useMemo(() => [new Date(cursor)], [cursor]);

  return (
    <div className="p-6 space-y-4" data-testid="calendar-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold font-heading flex items-center gap-2"><CalIcon size={22} /> Calendar</h1>
          <p className="text-xs text-muted-foreground">{headerLabel}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* View toggle */}
          <div className="flex items-center border rounded-lg overflow-hidden" data-testid="view-toggle">
            {VIEW_MODES.map(v => (
              <Button key={v} size="sm" variant={view === v ? 'default' : 'ghost'} className="h-8 rounded-none text-xs capitalize" onClick={() => setView(v)} data-testid={`view-${v}`}>{v}</Button>
            ))}
          </div>
          {/* Task scope */}
          <Select value={taskScope} onValueChange={setTaskScope}>
            <SelectTrigger className="h-8 text-xs w-[170px]" data-testid="task-scope-toggle"><Filter size={13} className="mr-1" /><SelectValue /></SelectTrigger>
            <SelectContent>{TASK_SCOPES.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
          </Select>
          <Button variant="outline" size="icon" onClick={goPrev} data-testid="cal-prev"><ChevronLeft size={16} /></Button>
          <Button variant="outline" size="sm" onClick={goToday} data-testid="cal-today">Today</Button>
          <Button variant="outline" size="icon" onClick={goNext} data-testid="cal-next"><ChevronRight size={16} /></Button>
          <Button size="sm" variant="outline" className="gap-1.5" onClick={openShare} data-testid="cal-share-btn"><Share2 size={14} />Share</Button>
          <Popover>
            <PopoverTrigger asChild><Button size="sm" variant="outline" className="gap-1.5" data-testid="cal-more-btn">More</Button></PopoverTrigger>
            <PopoverContent className="w-52 p-1" align="end">
              <Button variant="ghost" size="sm" className="w-full justify-start gap-2 h-8" onClick={() => setShowRecurring(true)}><Repeat size={14} /> Recurring events</Button>
              <Button variant="ghost" size="sm" className="w-full justify-start gap-2 h-8" onClick={() => setShowImportCal(true)}><Upload size={14} /> Import .ics</Button>
              <Button variant="ghost" size="sm" className="w-full justify-start gap-2 h-8" onClick={() => {
                const token = secureStorage.getToken();
                fetch(exportApi.ical(), { headers: { Authorization: `Bearer ${token}` } }).then(r => r.blob()).then(b => {
                  const link = document.createElement('a'); link.href = URL.createObjectURL(b); link.download = '5812-calendar.ics'; link.click();
                }).catch(() => toast.error('Export failed'));
              }}><Download size={14} /> Export .ics</Button>
            </PopoverContent>
          </Popover>
          <Button size="sm" variant={showHolidays ? 'default' : 'outline'} className="h-8 text-xs gap-1" onClick={() => setShowHolidays(v => !v)} data-testid="cal-holidays-toggle" title="Toggle US federal + Ugandan public holidays">
            {showHolidays ? '🎉 Holidays on' : 'Holidays off'}
          </Button>
          <Button size="sm" className="gap-1.5" onClick={() => { setCreateKind('event'); setCreateForm(f => ({ ...f, date: iso(cursor) })); setShowCreate(true); }} data-testid="cal-new-btn"><Plus size={14} />New</Button>
        </div>
      </div>

      {/* Legend — new palette (iter 281): outreach=green, US holidays=blue,
          UG holidays=red, your own events=brown, other events keep type colour */}
      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
        {[
          ['user_event', 'Your events'],
          ['task', 'Tasks'],
          ['holiday_us', 'US Holiday'],
          ['holiday_ug', 'UG Holiday'],
          ['outreach', 'Outreach'],
          ['service', 'Service'],
          ['conference', 'Conference'],
          ['meeting', 'Meeting'],
          ['community', 'Community'],
          ['workshop', 'Workshop'],
          ['training', 'Training'],
          ['social', 'Social'],
        ].map(([k, label]) => (
          <div key={k} className="flex items-center gap-1.5"><div className={`w-2.5 h-2.5 rounded-full ${TYPE_COLORS[k] || 'bg-slate-500'}`} /><span>{label}</span></div>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2">{[1,2,3].map(i => <div key={i} className="h-14 bg-muted animate-pulse rounded-lg" />)}</div>
      ) : view === 'month' ? <MonthGrid /> : view === 'week' ? <WeekOrDayGrid days={weekDays} /> : <WeekOrDayGrid days={dayDays} />}

      {/* Selected event detail dialog */}
      <Dialog open={!!selected} onOpenChange={o => { if (!o) { setSelected(null); setEditMode(false); } }}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editMode ? 'Edit Event' : selected?.title}</DialogTitle></DialogHeader>
          {selected && !editMode && (
            <div className="space-y-3 text-sm">
              <div className="flex items-center gap-2 text-muted-foreground"><CalIcon size={14} />
                {new Date(selected.date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
                {selected.end_date && selected.end_date !== selected.date && <> → {new Date(selected.end_date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</>}
              </div>
              {selected.time && <div className="flex items-center gap-2 text-muted-foreground"><Clock size={14} />{selected.time}{selected.end_time && ` – ${selected.end_time}`}</div>}
              {selected.location && <div className="flex items-center gap-2 text-muted-foreground"><MapPin size={14} />{selected.location}</div>}
              {selected.description && <p className="text-sm whitespace-pre-line pt-2 border-t border-border">{selected.description}</p>}
              <div className="flex items-center gap-2 pt-2 border-t border-border">
                <Badge variant="outline" className="capitalize">{selected.type}</Badge>
                {selected.is_public && <Badge variant="secondary">Public</Badge>}
                <Badge variant="outline">{selected.registered ?? 0}/{selected.capacity ?? '∞'}</Badge>
              </div>
              <div className="flex gap-2 pt-3">
                <Button variant="destructive" size="sm" onClick={deleteEvent} data-testid="delete-event-btn">Delete</Button>
                <div className="flex-1" />
                <Button variant="outline" size="sm" onClick={() => { navigator.clipboard.writeText(buildViewUrl('global', '', shareLinks?.global?.token || '')); toast.success('Link copied'); }} disabled={!shareLinks}><LinkIcon size={14} className="mr-1" />Copy</Button>
                <Button size="sm" onClick={() => setEditMode(true)} data-testid="edit-event-btn">Edit</Button>
              </div>
            </div>
          )}
          {selected && editMode && (
            <form onSubmit={saveEdit} className="space-y-3 mt-2" data-testid="edit-event-form">
              <div className="space-y-1"><Label>Title</Label><Input value={editForm.title} onChange={e => setEditForm({ ...editForm, title: e.target.value })} required /></div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>Date</Label><Input type="date" value={editForm.date} onChange={e => setEditForm({ ...editForm, date: e.target.value })} /></div>
                <div><Label>End Date</Label><Input type="date" value={editForm.end_date} onChange={e => setEditForm({ ...editForm, end_date: e.target.value })} /></div>
                <div><Label>Time</Label><Input type="time" value={editForm.time} onChange={e => setEditForm({ ...editForm, time: e.target.value })} /></div>
                <div><Label>End Time</Label><Input type="time" value={editForm.end_time} onChange={e => setEditForm({ ...editForm, end_time: e.target.value })} /></div>
              </div>
              <div><Label>Location</Label><Input value={editForm.location} onChange={e => setEditForm({ ...editForm, location: e.target.value })} /></div>
              <div><Label>Description</Label><Textarea rows={2} value={editForm.description} onChange={e => setEditForm({ ...editForm, description: e.target.value })} /></div>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={editForm.is_public} onChange={e => setEditForm({ ...editForm, is_public: e.target.checked })} /> Public event (appears on shared calendar)</label>
              <div className="flex gap-2 pt-2"><Button type="button" variant="outline" onClick={() => setEditMode(false)}>Cancel</Button><div className="flex-1" /><Button type="submit" disabled={savingEdit} data-testid="save-event-btn">{savingEdit ? 'Saving…' : 'Save'}</Button></div>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* Create dialog — Event or Task */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New {createKind === 'event' ? 'Event' : 'Task'}</DialogTitle></DialogHeader>
          <div className="flex items-center border rounded-lg overflow-hidden text-xs mt-1" data-testid="create-kind-toggle">
            <Button size="sm" variant={createKind === 'event' ? 'default' : 'ghost'} className="rounded-none flex-1" onClick={() => setCreateKind('event')}>Event</Button>
            <Button size="sm" variant={createKind === 'task' ? 'default' : 'ghost'} className="rounded-none flex-1" onClick={() => setCreateKind('task')}>Task</Button>
          </div>
          <form onSubmit={submitCreate} className="space-y-3 mt-3">
            <div><Label>Title</Label><Input value={createForm.title} onChange={e => setCreateForm({ ...createForm, title: e.target.value })} required data-testid="create-title" /></div>
            <div className="grid grid-cols-2 gap-2">
              <div><Label>{createKind === 'event' ? 'Date' : 'Due date'}</Label><Input type="date" value={createForm.date} onChange={e => setCreateForm({ ...createForm, date: e.target.value })} required data-testid="create-date" /></div>
              {createKind === 'event' ? (
                <div><Label>Time</Label><Input type="time" value={createForm.time} onChange={e => setCreateForm({ ...createForm, time: e.target.value })} /></div>
              ) : (
                <div><Label>Priority</Label>
                  <Select value={createForm.priority} onValueChange={v => setCreateForm({ ...createForm, priority: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="low">Low</SelectItem><SelectItem value="medium">Medium</SelectItem><SelectItem value="high">High</SelectItem><SelectItem value="urgent">Urgent</SelectItem></SelectContent>
                  </Select>
                </div>
              )}
            </div>
            {createKind === 'event' && (
              <>
                <div className="grid grid-cols-2 gap-2">
                  <div><Label>End time</Label><Input type="time" value={createForm.end_time} onChange={e => setCreateForm({ ...createForm, end_time: e.target.value })} /></div>
                  <div><Label>Type</Label>
                    <Select value={createForm.type} onValueChange={v => setCreateForm({ ...createForm, type: v })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>{Object.keys(TYPE_COLORS).filter(t => t !== 'imported' && t !== 'task').map(t => <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                </div>
                <div><Label>Location</Label><Input value={createForm.location} onChange={e => setCreateForm({ ...createForm, location: e.target.value })} /></div>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={createForm.is_public} onChange={e => setCreateForm({ ...createForm, is_public: e.target.checked })} data-testid="create-is-public" /> Public event (appears on shared calendar)</label>
              </>
            )}
            {createKind === 'task' && (
              <div><Label>Board</Label>
                <Select value={createForm.board_id} onValueChange={v => setCreateForm({ ...createForm, board_id: v })}>
                  <SelectTrigger data-testid="create-board"><SelectValue placeholder="Pick a board" /></SelectTrigger>
                  <SelectContent>{boards.map(b => <SelectItem key={b.id} value={b.id}>{b.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            )}
            <div><Label>Description</Label><Textarea rows={2} value={createForm.description} onChange={e => setCreateForm({ ...createForm, description: e.target.value })} /></div>
            <div className="flex gap-2 pt-2"><Button type="button" variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button><div className="flex-1" /><Button type="submit" disabled={saving} data-testid="create-submit">{saving ? 'Creating…' : 'Create'}</Button></div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Share dialog */}
      <Dialog open={showShare} onOpenChange={setShowShare}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Share Calendar</DialogTitle></DialogHeader>

          {/* Custom (personalised) link creator */}
          <div className="rounded-lg border border-primary/30 bg-primary/5 p-4 space-y-3">
            <div>
              <p className="text-sm font-semibold">Create a custom share link</p>
              <p className="text-xs text-muted-foreground">Pick exactly what to include — public events, your private events, your tasks, and which campuses. Each link has its own unique code so you can revoke it later.</p>
            </div>
            <CustomShareForm locations={locations} onCreate={createShareConfig} />
          </div>

          {/* My saved custom links */}
          {(shareConfigs.length > 0 || shareConfigsLoading) && (
            <div className="space-y-3">
              <p className="text-sm font-semibold">My saved links</p>
              {shareConfigsLoading && shareConfigs.length === 0 && <div className="animate-pulse h-16 bg-muted rounded" />}
              {shareConfigs.map(cfg => (
                <div key={cfg.id} className="rounded-lg border border-border p-3 space-y-2" data-testid={`saved-share-${cfg.id}`}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold truncate">{cfg.name}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {cfg.include_public_events && '· Public events '}
                        {cfg.include_private_events && '· Private events '}
                        {cfg.include_tasks && `· Tasks (${cfg.task_scope}) `}
                        {(cfg.location_ids || []).length ? `· ${cfg.location_ids.length} campus${cfg.location_ids.length > 1 ? 'es' : ''}` : '· All my campuses'}
                      </p>
                    </div>
                    <Button size="sm" variant="ghost" className="text-destructive h-8" onClick={() => revokeShareConfig(cfg.id)} data-testid={`revoke-share-${cfg.id}`}><X size={14} /></Button>
                  </div>
                  <div className="flex items-center gap-2">
                    <Input readOnly value={buildViewUrl('user', '', cfg.token)} className="text-xs font-mono h-8" />
                    <Button size="sm" variant="outline" className="h-8" onClick={() => { navigator.clipboard.writeText(buildViewUrl('user', '', cfg.token)); toast.success('Link copied'); }}><Copy size={14} /></Button>
                  </div>
                  <div className="flex items-center gap-2">
                    <Input readOnly value={buildIcalUrl('user', '', cfg.token)} className="text-xs font-mono h-8" />
                    <Button size="sm" variant="outline" className="h-8" onClick={() => { navigator.clipboard.writeText(buildIcalUrl('user', '', cfg.token)); toast.success('Subscribe URL copied'); }}><Copy size={14} /></Button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Static global / per-location links (public events only, no revoke) */}
          <div className="space-y-3 pt-2 border-t border-border">
            <p className="text-sm font-semibold">Quick share (public events only)</p>
            <p className="text-xs text-muted-foreground">Fixed links — always work, always public-only. Rotate the server SECRET_KEY to invalidate.</p>
            {shareLinks ? (
              <div className="space-y-3">
                <ShareBlock title="Global — all campuses" viewUrl={buildViewUrl('global', '', shareLinks.global.token)} icalUrl={buildIcalUrl('global', '', shareLinks.global.token)} />
                {shareLinks.locations?.map(loc => (
                  <ShareBlock key={loc.location_id} title={loc.location_name} viewUrl={buildViewUrl('location', loc.location_id, loc.token)} icalUrl={buildIcalUrl('location', loc.location_id, loc.token)} />
                ))}
              </div>
            ) : <div className="animate-pulse h-24 bg-muted rounded" />}
          </div>
        </DialogContent>
      </Dialog>

      {/* Recurring events (kept from previous) */}
      <RecurringEventsDialog open={showRecurring} onOpenChange={setShowRecurring} onCreated={loadAll} />
      {/* Import iCal */}
      <ImportIcalDialog open={showImportCal} onOpenChange={setShowImportCal} onImported={loadAll} />
    </div>
  );
}

function ShareBlock({ title, viewUrl, icalUrl }) {
  const [copied, setCopied] = useState('');
  const copy = (which, url) => { navigator.clipboard.writeText(url); setCopied(which); setTimeout(() => setCopied(''), 1500); };
  return (
    <div className="rounded-lg border border-border p-3 space-y-2" data-testid="share-block">
      <p className="text-sm font-semibold">{title}</p>
      <div className="flex items-center gap-2">
        <Input readOnly value={viewUrl} className="text-xs font-mono" />
        <Button size="sm" variant="outline" onClick={() => copy('view', viewUrl)}>{copied === 'view' ? <Check size={14} /> : <Copy size={14} />}</Button>
      </div>
      <div className="flex items-center gap-2">
        <Input readOnly value={icalUrl} className="text-xs font-mono" />
        <Button size="sm" variant="outline" onClick={() => copy('ics', icalUrl)}>{copied === 'ics' ? <Check size={14} /> : <Copy size={14} />}</Button>
      </div>
      <p className="text-[10px] text-muted-foreground">Top row = read-only page. Bottom = subscribe URL for Google/Apple Calendar.</p>
    </div>
  );
}

// Selection wizard for personalised share links.
function CustomShareForm({ locations, onCreate }) {
  const [name, setName] = useState('My calendar');
  const [inclPublic, setInclPublic] = useState(true);
  const [inclPrivate, setInclPrivate] = useState(false);
  const [inclTasks, setInclTasks] = useState(false);
  const [taskScope, setTaskScope] = useState('mine');
  const [selectedLocs, setSelectedLocs] = useState([]);   // empty = all
  const [busy, setBusy] = useState(false);
  const toggleLoc = (id) => setSelectedLocs(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);
  const submit = async (e) => {
    e.preventDefault();
    if (!inclPublic && !inclPrivate && !inclTasks) { toast.error('Include at least one thing'); return; }
    setBusy(true);
    await onCreate({
      name: name.trim() || 'My calendar',
      include_public_events: inclPublic,
      include_private_events: inclPrivate,
      include_tasks: inclTasks,
      task_scope: taskScope,
      location_ids: selectedLocs,
    });
    setBusy(false);
    setName('My calendar');
  };
  return (
    <form onSubmit={submit} className="space-y-3" data-testid="custom-share-form">
      <div>
        <Label className="text-xs">Link name</Label>
        <Input value={name} onChange={e => setName(e.target.value)} placeholder="My weekly plan" data-testid="share-name-input" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-sm">
        <label className="flex items-center gap-2"><input type="checkbox" checked={inclPublic} onChange={e => setInclPublic(e.target.checked)} data-testid="share-incl-public" /> Public events</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={inclPrivate} onChange={e => setInclPrivate(e.target.checked)} data-testid="share-incl-private" /> My private events</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={inclTasks} onChange={e => setInclTasks(e.target.checked)} data-testid="share-incl-tasks" /> Tasks (with due dates)</label>
        {inclTasks && (
          <Select value={taskScope} onValueChange={setTaskScope}>
            <SelectTrigger className="h-8" data-testid="share-task-scope"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="mine">Only my tasks</SelectItem><SelectItem value="campus">All in my campus</SelectItem></SelectContent>
          </Select>
        )}
      </div>
      <div>
        <Label className="text-xs">Campuses (leave empty = all my campuses)</Label>
        <div className="max-h-28 overflow-y-auto rounded border border-border p-2 space-y-1 mt-1">
          {(locations || []).slice(0, 30).map(l => (
            <label key={l.id} className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={selectedLocs.includes(l.id)} onChange={() => toggleLoc(l.id)} data-testid={`share-loc-${l.id}`} />
              <span className="truncate">{l.name}</span>
            </label>
          ))}
        </div>
      </div>
      <Button type="submit" size="sm" disabled={busy} data-testid="share-create-btn">{busy ? 'Creating…' : 'Generate link'}</Button>
    </form>
  );
}

function RecurringEventsDialog({ open, onOpenChange, onCreated }) {
  const [form, setForm] = useState({ title: '', type: 'service', location: '', time: '09:00', recurrence: 'weekly', day_of_week: '0', start_date: iso(new Date()), weeks: 12, interval: 1, nth_week: 1, nth_month_day: 1, end_date: '' });
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try {
      const payload = { title: form.title, type: form.type, location: form.location, time: form.time, pattern: form.recurrence, start_date: form.start_date, occurrences: parseInt(form.weeks) || 12, interval: parseInt(form.interval) || 1, day_of_week: parseInt(form.day_of_week) || 0, nth_week: parseInt(form.nth_week) || 1, day_of_month: parseInt(form.nth_month_day) || 1, end_date: form.end_date || undefined };
      const res = await exportApi.generateRecurring(payload);
      toast.success(`Created ${res.data.created || res.data.events?.length || 0} events`);
      onOpenChange(false); onCreated?.();
    } catch { toast.error('Failed to create recurring events'); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Create Recurring Events</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-3 mt-2">
          <div><Label>Title</Label><Input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} required /></div>
          <div className="grid grid-cols-2 gap-2">
            <div><Label>Pattern</Label>
              <Select value={form.recurrence} onValueChange={v => setForm({ ...form, recurrence: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="daily">Daily</SelectItem><SelectItem value="weekly">Weekly</SelectItem><SelectItem value="biweekly">Bi-weekly</SelectItem><SelectItem value="monthly">Monthly</SelectItem><SelectItem value="yearly">Yearly</SelectItem></SelectContent>
              </Select>
            </div>
            <div><Label>Occurrences</Label><Input type="number" min={1} max={104} value={form.weeks} onChange={e => setForm({ ...form, weeks: parseInt(e.target.value) || 1 })} /></div>
            <div><Label>Start</Label><Input type="date" value={form.start_date} onChange={e => setForm({ ...form, start_date: e.target.value })} /></div>
            <div><Label>End (optional)</Label><Input type="date" value={form.end_date} onChange={e => setForm({ ...form, end_date: e.target.value })} /></div>
            <div><Label>Time</Label><Input type="time" value={form.time} onChange={e => setForm({ ...form, time: e.target.value })} /></div>
            <div><Label>Location</Label><Input value={form.location} onChange={e => setForm({ ...form, location: e.target.value })} /></div>
          </div>
          <div className="flex gap-2 pt-2"><Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><div className="flex-1" /><Button type="submit" disabled={busy}>{busy ? 'Creating…' : 'Create'}</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ImportIcalDialog({ open, onOpenChange, onImported }) {
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);
  const onFile = (e) => {
    const f = e.target.files[0]; if (!f) return;
    const r = new FileReader(); r.onload = (ev) => setContent(ev.target.result); r.readAsText(f);
  };
  const submit = async () => {
    if (!content.trim()) return;
    setBusy(true);
    try { const res = await exportApi.icalImport({ ical_content: content }); toast.success(res.data.message || `Imported ${res.data.imported} events`); onOpenChange(false); setContent(''); onImported?.(); }
    catch { toast.error('Import failed'); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Import Calendar (.ics)</DialogTitle></DialogHeader>
        <div className="space-y-3 mt-2">
          <div><Label>Upload file</Label><Input type="file" accept=".ics,.ical" onChange={onFile} /></div>
          <div><Label>Or paste content</Label><Textarea rows={8} value={content} onChange={e => setContent(e.target.value)} placeholder="BEGIN:VCALENDAR..." /></div>
          <div className="flex gap-2 pt-2"><Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><div className="flex-1" /><Button onClick={submit} disabled={busy || !content.trim()}>{busy ? 'Importing…' : 'Import'}</Button></div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
