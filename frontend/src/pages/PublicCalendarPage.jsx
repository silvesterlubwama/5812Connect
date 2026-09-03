// Public read-only calendar view — no auth. Fetches events by scope+token
// and renders a compact month grid. Tasks are never included on this feed.
import React, { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Calendar as CalIcon, MapPin, Clock, Download } from 'lucide-react';
import axios from 'axios';

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const TYPE_COLORS = {
  service: 'bg-purple-500', conference: 'bg-amber-500', meeting: 'bg-slate-500',
  community: 'bg-teal-500', outreach: 'bg-pink-500', workshop: 'bg-violet-500',
  training: 'bg-cyan-500', social: 'bg-orange-500', task: 'bg-blue-500',
};

export default function PublicCalendarPage() {
  const params = useParams();
  const path = window.location.pathname || '';
  // Detect scope from URL path (routes: /p/calendar/global/:token, /p/calendar/location/:locationId/:token, /p/calendar/user/:userToken)
  const scope = path.includes('/p/calendar/user/') ? 'user'
              : path.includes('/p/calendar/location/') ? 'location' : 'global';
  const token = params.userToken || params.token;
  const locationId = params.locationId;
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [cursor, setCursor] = useState(new Date());

  const backend = process.env.REACT_APP_BACKEND_URL || '';
  const jsonUrl = scope === 'global'
    ? `${backend}/api/public/calendar/global?token=${token}`
    : scope === 'user'
      ? `${backend}/api/public/calendar/user/${token}`
      : `${backend}/api/public/calendar/location/${locationId}?token=${token}`;
  const icalUrl = scope === 'global'
    ? `${backend}/api/public/calendar/global.ics?token=${token}`
    : scope === 'user'
      ? `${backend}/api/public/calendar/user/${token}.ics`
      : `${backend}/api/public/calendar/location/${locationId}.ics?token=${token}`;

  useEffect(() => {
    axios.get(jsonUrl)
      .then(r => setData(r.data))
      .catch(err => setError(err.response?.status === 404 ? 'Invalid or expired link' : 'Failed to load calendar'));
  }, [jsonUrl]);

  const byDate = useMemo(() => {
    const m = new Map();
    const push = (key, obj) => { if (!m.has(key)) m.set(key, []); m.get(key).push(obj); };
    for (const ev of (data?.events || [])) {
      const start = ev.date;
      const end = ev.end_date || ev.date;
      try {
        const s = new Date(start + 'T00:00:00');
        const e = new Date(end + 'T00:00:00');
        let c = new Date(s);
        while (c <= e) {
          const key = `${c.getFullYear()}-${String(c.getMonth() + 1).padStart(2, '0')}-${String(c.getDate()).padStart(2, '0')}`;
          push(key, { ...ev, _kind: 'event' });
          c = new Date(c.getTime() + 86400000);
        }
      } catch { /* skip */ }
    }
    for (const t of (data?.tasks || [])) {
      const due = (t.due_date || '').slice(0, 10);
      if (due) push(due, { id: t.id, title: `[Task] ${t.title || 'Task'}`, type: 'task', time: '', _kind: 'task', status: t.status });
    }
    for (const arr of m.values()) arr.sort((a, b) => (a.time || 'z').localeCompare(b.time || 'z'));
    return m;
  }, [data]);

  const y = cursor.getFullYear(), m = cursor.getMonth();
  const firstDay = new Date(y, m, 1).getDay();
  const daysInMonth = new Date(y, m + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  const today = new Date();

  if (error) return <div className="min-h-screen flex items-center justify-center bg-background p-6"><div className="max-w-md text-center space-y-2"><CalIcon size={40} className="mx-auto text-muted-foreground" /><h1 className="text-lg font-semibold">{error}</h1><p className="text-sm text-muted-foreground">Please check the link and try again.</p></div></div>;
  if (!data) return <div className="min-h-screen flex items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" /></div>;

  const title = data.scope === 'global' ? '58:12 Public Events'
               : data.scope === 'user' ? (data.name || 'My Calendar')
               : `58:12 · ${data.location?.name || 'Campus'}`;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="border-b border-border">
        <div className="max-w-5xl mx-auto px-6 py-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <CalIcon size={22} />
            <h1 className="text-xl font-semibold" data-testid="public-cal-title">{title}</h1>
          </div>
          <a href={icalUrl} className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline" data-testid="public-cal-subscribe">
            <Download size={14} /> Subscribe (.ics)
          </a>
        </div>
      </div>
      <div className="max-w-5xl mx-auto p-6 space-y-4">
        <div className="flex items-center justify-between">
          <button className="p-2 rounded hover:bg-accent" onClick={() => setCursor(c => { const n = new Date(c); n.setMonth(n.getMonth() - 1); return n; })} data-testid="public-cal-prev"><ChevronLeft size={16} /></button>
          <span className="text-lg font-semibold">{MONTHS[m]} {y}</span>
          <button className="p-2 rounded hover:bg-accent" onClick={() => setCursor(c => { const n = new Date(c); n.setMonth(n.getMonth() + 1); return n; })} data-testid="public-cal-next"><ChevronRight size={16} /></button>
        </div>
        <div className="bg-card rounded-xl border border-border overflow-hidden">
          <div className="grid grid-cols-7 border-b border-border">{DAYS.map(d => <div key={d} className="py-2 text-center text-xs font-semibold text-muted-foreground">{d}</div>)}</div>
          <div className="grid grid-cols-7">
            {cells.map((d, i) => {
              const dateStr = d ? `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}` : null;
              const dayItems = dateStr ? (byDate.get(dateStr) || []) : [];
              const isToday = d === today.getDate() && m === today.getMonth() && y === today.getFullYear();
              return (
                <div key={i} className={`min-h-[90px] p-1.5 border-b border-r border-border last:border-r-0 ${!d ? 'bg-muted/20' : ''}`}>
                  {d && (
                    <>
                      <span className={`text-sm font-medium inline-flex items-center justify-center w-7 h-7 rounded-full mb-1 ${isToday ? 'bg-primary text-primary-foreground' : ''}`}>{d}</span>
                      <div className="space-y-0.5">
                        {dayItems.slice(0, 3).map(ev => (
                          <div key={ev.id} className={`text-[10px] px-1 py-0.5 rounded truncate text-white ${TYPE_COLORS[ev.type] || 'bg-slate-500'}`} title={ev.title}>
                            {ev.time && <span className="opacity-80">{ev.time} </span>}{ev.title}
                          </div>
                        ))}
                        {dayItems.length > 3 && <p className="text-[10px] text-muted-foreground pl-1">+{dayItems.length - 3} more</p>}
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Upcoming list */}
        <div className="pt-2 space-y-2">
          <h2 className="text-sm font-semibold">Upcoming</h2>
          {(data.events || []).filter(ev => ev.date >= new Date().toISOString().slice(0, 10)).slice(0, 20).map(ev => (
            <div key={ev.id} className="rounded-lg border border-border bg-card px-3 py-2 flex items-center gap-3">
              <div className={`w-2 h-full rounded-full ${TYPE_COLORS[ev.type] || 'bg-slate-500'}`} style={{ minHeight: 32 }} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold truncate">{ev.title}</p>
                <p className="text-xs text-muted-foreground flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-1"><CalIcon size={11} />{new Date(ev.date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}</span>
                  {ev.time && <span className="inline-flex items-center gap-1"><Clock size={11} />{ev.time}{ev.end_time ? `–${ev.end_time}` : ''}</span>}
                  {ev.location && <span className="inline-flex items-center gap-1"><MapPin size={11} />{ev.location}</span>}
                </p>
              </div>
            </div>
          ))}
        </div>
        <p className="text-[10px] text-muted-foreground text-center pt-4">Public feed · Read-only · Powered by 58:12 Global</p>
      </div>
    </div>
  );
}
