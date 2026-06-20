import React, { useState, useEffect } from 'react';
import { Globe, Plus, Trash2, Users, Calendar, MapPin, RefreshCw, Copy, Settings, Repeat } from 'lucide-react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Switch } from '../components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { outreachApi, locationsApi, locationVenuesApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import { BulkActionBar, exportToCSV, SelectCheckbox } from '../components/BulkActions';
import EmptyState from '../components/EmptyState';

const statusColors = { active: 'border-green-500 text-green-600', completed: 'border-slate-400 text-slate-500', paused: 'border-amber-500 text-amber-600' };

export default function OutreachPage() {
  const { user } = useAuth();
  const activeCampus = localStorage.getItem('5812_active_campus') || user?.location_id || '';
  const [programs, setPrograms] = useState([]);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [sessions, setSessions] = useState([]);
  const [categories, setCategories] = useState([]);
  const [locations, setLocations] = useState([]);
  const [locationVenues, setLocationVenues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showProgram, setShowProgram] = useState(false);
  const [showSession, setShowSession] = useState(false);
  const [showCatManager, setShowCatManager] = useState(false);
  const [showRecurring, setShowRecurring] = useState(null);
  const [editingProg, setEditingProg] = useState(null);
  const [saving, setSaving] = useState(false);
  const [newCatName, setNewCatName] = useState('');
  const [newCatColor, setNewCatColor] = useState('#10b981');
  const emptyProg = { name: '', description: '', category: 'community', status: 'active', location: '', location_id: activeCampus, venue_id: '', start_date: new Date().toISOString().split('T')[0], target: '', is_recurring: false, recurrence_pattern: 'saturday', recurrence_day: 1, recurrence_time: '09:00', recurrence_end_time: '12:00' };
  const [progForm, setProgForm] = useState({ ...emptyProg });
  const [sessionForm, setSessionForm] = useState({ program_id: '', date: new Date().toISOString().split('T')[0], time: '', location: '', attendees: '', notes: '', led_by: '' });
  const [recurForm, setRecurForm] = useState({ pattern: 'weekly', occurrences: 12, interval: 1, day_of_week: 5, nth_week: 2, day_of_month: 1, time: '09:00', end_time: '12:00', start_date: new Date().toISOString().split('T')[0], end_date: '' });

  const loadVenues = async (locId) => {
    if (!locId) { setLocationVenues([]); return; }
    try {
      const r = await locationVenuesApi.get(locId);
      setLocationVenues([...(r.data.venues || []), ...(r.data.sublocations || []).map(s => ({ id: s.id, name: s.name, type: 'sublocation' }))]);
    } catch { setLocationVenues([]); }
  };

  const fetchAll = async () => {
    setLoading(true);
    try {
      // Promise.allSettled — same resilience pattern as iter-172 Dashboard fix.
      // A 403 on any sub-fetch (e.g. sessions endpoint when permissions tighten)
      // shouldn't poison the whole page.
      const results = await Promise.allSettled([
        outreachApi.programs(), outreachApi.sessions(), outreachApi.categories(),
        locationsApi.list(),
      ]);
      const data = (i, fallback = []) => results[i].status === 'fulfilled' ? (results[i].value?.data ?? fallback) : fallback;
      setPrograms(data(0));
      setSessions(data(1));
      setCategories(data(2));
      setLocations(data(3));
    } catch { toast.error('Failed to load outreach data'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); }, []);

  const catColorMap = Object.fromEntries(categories.map(c => [c.name, c.color]));

  const handleAddProgram = async (e) => {
    e.preventDefault(); setSaving(true);
    try {
      const payload = { ...progForm, target: progForm.target ? parseInt(progForm.target) : null, location_id: progForm.location_id || activeCampus };
      const res = editingProg ? await outreachApi.updateProgram(editingProg.id, payload) : await outreachApi.createProgram(payload);
      if (editingProg) {
        setPrograms(prev => prev.map(p => p.id === editingProg.id ? res.data : p));
        toast.success('Programme updated');
      } else {
        setPrograms(prev => [res.data, ...prev]);
        toast.success('Programme created!');
      }
      setShowProgram(false); setEditingProg(null); setProgForm({ ...emptyProg });
    } catch { toast.error('Failed to save programme'); }
    finally { setSaving(false); }
  };

  const handleAddSession = async (e) => {
    e.preventDefault(); setSaving(true);
    try {
      const res = await outreachApi.createSession({ ...sessionForm, attendees: parseInt(sessionForm.attendees) || 0 });
      setSessions(prev => [res.data, ...prev]);
      const prog = programs.find(p => p.id === sessionForm.program_id);
      if (prog) setPrograms(prev => prev.map(p => p.id === prog.id ? { ...p, sessions_count: (p.sessions_count || 0) + 1, total_reached: (p.total_reached || 0) + (parseInt(sessionForm.attendees) || 0) } : p));
      setShowSession(false);
      setSessionForm({ program_id: '', date: new Date().toISOString().split('T')[0], time: '', location: '', attendees: '', notes: '', led_by: '' });
      toast.success('Session recorded!');
    } catch { toast.error('Failed to record session'); }
    finally { setSaving(false); }
  };

  const editProgram = (p) => {
    setEditingProg(p);
    setProgForm({ name: p.name, description: p.description || '', category: p.category || 'community', status: p.status || 'active', location: p.location || '', location_id: p.location_id || activeCampus, venue_id: p.venue_id || '', start_date: p.start_date || '', target: p.target || '', is_recurring: p.is_recurring || false, recurrence_pattern: p.recurrence_pattern || 'saturday', recurrence_day: p.recurrence_day || 1, recurrence_time: p.recurrence_time || '09:00', recurrence_end_time: p.recurrence_end_time || '12:00' });
    if (p.location_id) loadVenues(p.location_id);
    setShowProgram(true);
  };

  const duplicateProgram = async (p) => {
    try { const res = await outreachApi.duplicateProgram(p.id); setPrograms(prev => [res.data, ...prev]); toast.success(`Duplicated as "${res.data.name}"`); } catch { toast.error('Failed to duplicate'); }
  };

  const deleteProgram = async (id) => {
    if (!window.confirm('Delete this programme?')) return;
    await outreachApi.deleteProgram(id); setPrograms(prev => prev.filter(p => p.id !== id)); toast.success('Deleted');
  };

  const generateRecurring = async () => {
    if (!showRecurring) return;
    // Validate end_date isn't before start_date (was producing 1 event then bailing
    // out of the backend loop — common cause of "only 1 event generated").
    if (recurForm.end_date && recurForm.start_date && recurForm.end_date < recurForm.start_date) {
      toast.error('End date must be after start date');
      return;
    }
    if (!recurForm.start_date) {
      toast.error('Pick a start date');
      return;
    }
    const occurrences = Math.max(1, Math.min(104, parseInt(recurForm.occurrences) || 12));
    setSaving(true);
    try {
      const res = await outreachApi.generateRecurring({
        title: showRecurring.name,
        type: 'outreach',
        location: showRecurring.location || '',
        location_id: showRecurring.location_id || '',
        pattern: recurForm.pattern || 'weekly',
        occurrences,
        interval: parseInt(recurForm.interval) || 1,
        start_date: recurForm.start_date,
        end_date: recurForm.end_date || undefined,
        time: recurForm.time || '09:00',
        end_time: recurForm.end_time || '',
        day_of_week: parseInt(recurForm.day_of_week) || 0,
        nth_week: parseInt(recurForm.nth_week) || 1,
        day_of_month: parseInt(recurForm.day_of_month) || 1,
      });
      const count = res.data?.created || 0;
      if (count === 0) {
        toast.error('No events generated — check that the end date is after the start date');
      } else if (count === 1 && occurrences > 1) {
        // The backend bailed on iteration 2 — almost always end_date too close to start
        toast.warning(`Only 1 event generated. Did you pick an end date too close to ${recurForm.start_date}?`);
      } else {
        toast.success(`Generated ${count} recurring events`);
      }
      setShowRecurring(null);
    } catch (e) { toast.error(e?.response?.data?.detail || 'Failed to generate events'); }
    finally { setSaving(false); }
  };

  const addCategory = async () => {
    if (!newCatName.trim()) return;
    try { const r = await outreachApi.createCategory({ name: newCatName, label: newCatName, color: newCatColor }); setCategories(prev => [...prev, r.data]); setNewCatName(''); toast.success('Category added'); } catch { toast.error('Failed'); }
  };

  const deleteCategory = async (id) => {
    try { await outreachApi.deleteCategory(id); setCategories(prev => prev.filter(c => c.id !== id)); toast.success('Deleted'); } catch { toast.error('Failed'); }
  };

  const totalReached = programs.reduce((s, p) => s + (p.total_reached || 0), 0);

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Programmes & Outreach</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{programs.length} programmes · {totalReached.toLocaleString()} reached</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setShowCatManager(true)}>Categories</Button>
          <Button variant="outline" size="sm" onClick={fetchAll}><RefreshCw size={14} /></Button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {[{ label: 'Active', value: programs.filter(p => p.status === 'active').length, color: 'text-green-600' }, { label: 'Sessions', value: sessions.length, color: 'text-blue-600' }, { label: 'Reached', value: totalReached.toLocaleString(), color: 'text-primary' }].map((s, i) => (
          <Card key={s.label || i} className="shadow-soft rounded-xl"><CardContent className="p-4 text-center"><p className={`text-2xl font-bold ${s.color}`}>{s.value}</p><p className="text-xs text-muted-foreground mt-1">{s.label}</p></CardContent></Card>
        ))}
      </div>

      <Tabs defaultValue="programs">
        <TabsList><TabsTrigger value="programs">Programmes ({programs.length})</TabsTrigger><TabsTrigger value="sessions">Sessions ({sessions.length})</TabsTrigger></TabsList>
        <TabsContent value="programs" className="mt-4">
          <div className="flex justify-end mb-3"><Button size="sm" className="gap-2" onClick={() => { setEditingProg(null); setProgForm({...emptyProg}); setShowProgram(true); }}><Plus size={14} /> New Programme</Button></div>
          {loading ? <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">{[1,2,3].map(i => <div key={i} className="h-48 bg-muted animate-pulse rounded-xl" />)}</div> : programs.length > 0 ? (
            <div>
            {selectedIds.size > 0 && <div className="mb-3"><BulkActionBar selectedIds={selectedIds} onClear={() => setSelectedIds(new Set())} onBulkExport={() => exportToCSV(programs.filter(p => selectedIds.has(p.id)), 'outreach-programs-export.csv')} /></div>}
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {programs.map(p => (
                <Card key={p.id} className={`shadow-soft rounded-xl hover:shadow-soft-lg transition-shadow ${selectedIds.has(p.id) ? 'ring-2 ring-primary/40' : ''}`} data-testid="program-card">
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-start gap-2">
                        <input type="checkbox" className="accent-primary mt-1" checked={selectedIds.has(p.id)} onChange={() => setSelectedIds(prev => { const n = new Set(prev); n.has(p.id) ? n.delete(p.id) : n.add(p.id); return n; })} />
                        <div className="flex-1"><p className="font-semibold text-sm">{p.name}</p>
                        <div className="flex gap-2 mt-1">
                          <span className="text-xs px-2 py-0.5 rounded-full capitalize" style={{ backgroundColor: (catColorMap[p.category] || '#6366f1') + '22', color: catColorMap[p.category] || '#6366f1' }}>{p.category}</span>
                          <Badge variant="outline" className={`text-xs capitalize ${statusColors[p.status] || ''}`}>{p.status}</Badge>
                          {p.is_recurring && <Badge variant="outline" className="text-xs border-purple-300 text-purple-600"><Repeat size={10} className="mr-1" />Recurring</Badge>}
                        </div>
                      </div>
                      </div>
                    </div>
                    {p.description && <p className="text-xs text-muted-foreground mb-3 line-clamp-2">{p.description}</p>}
                    <div className="space-y-1 text-xs text-muted-foreground mb-3">
                      {p.location && <div className="flex items-center gap-1.5"><MapPin size={11} />{p.location}</div>}
                      <div className="flex items-center gap-1.5"><Users size={11} />{p.total_reached || 0} / {p.target || '—'}</div>
                      <div className="flex items-center gap-1.5"><Calendar size={11} />{p.sessions_count || 0} sessions</div>
                    </div>
                    <div className="flex gap-1.5 border-t border-border pt-3">
                      <Button size="sm" variant="ghost" onClick={() => editProgram(p)} title="Edit"><Settings size={13} /></Button>
                      <Button size="sm" variant="ghost" onClick={() => duplicateProgram(p)} title="Duplicate"><Copy size={13} /></Button>
                      <Button size="sm" variant="ghost" onClick={() => {
                        // Open the recurrence dialog with a properly-shaped form.
                        // Pre-fills FROM the programme's stored recurrence_* settings
                        // when present, so editing an existing recurring programme
                        // keeps the user's prior choices. Defaults match the form
                        // schema declared in useState(line 42) — critical to avoid
                        // React's "controlled-to-uncontrolled" warning that hid the
                        // pattern + dates and silently dropped them on submit.
                        const today = new Date().toISOString().split('T')[0];
                        setRecurForm({
                          pattern: p.recurrence_pattern || 'weekly',
                          occurrences: 12,
                          interval: 1,
                          day_of_week: typeof p.recurrence_day === 'number' ? p.recurrence_day : 5,
                          nth_week: 2,
                          day_of_month: 1,
                          time: p.recurrence_time || '09:00',
                          end_time: p.recurrence_end_time || '12:00',
                          start_date: p.start_date || today,
                          end_date: '',
                        });
                        setShowRecurring(p);
                      }} title="Generate Events" data-testid={`outreach-generate-${p.id}`}><Repeat size={13} /></Button>
                      <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => deleteProgram(p.id)}><Trash2 size={13} /></Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
            </div>
          ) : <EmptyState icon={Globe} title="No outreach programmes yet" description="Programmes group recurring community sessions — schools, food drives, prayer circles, etc. Create your first to start logging sessions." testid="outreach-programs-empty" />}
        </TabsContent>
        <TabsContent value="sessions" className="mt-4">
          <div className="flex justify-end mb-3"><Button size="sm" className="gap-2" onClick={() => setShowSession(true)}><Plus size={14} /> Log Session</Button></div>
          <Card className="shadow-soft rounded-xl"><CardContent className="p-5">
            {sessions.length > 0 ? (
              <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b border-border text-left"><th className="pb-2 font-medium text-muted-foreground">Program</th><th className="pb-2 font-medium text-muted-foreground">Date</th><th className="pb-2 font-medium text-muted-foreground">Location</th><th className="pb-2 font-medium text-muted-foreground">Attendees</th><th className="pb-2 font-medium text-muted-foreground">Led by</th></tr></thead>
                <tbody className="divide-y divide-border">{sessions.map(s => { const prog = programs.find(pp => pp.id === s.program_id); return (<tr key={s.id} className="hover:bg-accent/30"><td className="py-3 font-medium">{prog?.name || s.program_id}</td><td className="py-3 text-muted-foreground">{s.date}</td><td className="py-3 text-muted-foreground">{s.location || '—'}</td><td className="py-3 font-semibold text-primary">{s.attendees}</td><td className="py-3 text-muted-foreground">{s.led_by || '—'}</td></tr>); })}</tbody></table></div>
            ) : <EmptyState compact icon={Calendar} title="No sessions logged yet" description="When you log a session it appears here with attendance, location, and leader." action={{ label: 'Log session', onClick: () => setShowSession(true), testid: 'outreach-empty-log-session' }} testid="outreach-sessions-empty" />}
          </CardContent></Card>
        </TabsContent>
      </Tabs>

      {/* Add/Edit Programme */}
      <Dialog open={showProgram} onOpenChange={v => { if (!v) { setShowProgram(false); setEditingProg(null); } }}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editingProg ? 'Edit Programme' : 'New Programme'}</DialogTitle></DialogHeader>
          <form onSubmit={handleAddProgram} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Name *</Label><Input placeholder="Programme name" value={progForm.name} onChange={e => setProgForm({...progForm, name: e.target.value})} required /></div>
            <div className="space-y-2"><Label>Description</Label><Textarea rows={2} value={progForm.description} onChange={e => setProgForm({...progForm, description: e.target.value})} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Category</Label>
                <Select value={progForm.category} onValueChange={v => setProgForm({...progForm, category: v})}><SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{categories.map(c => <SelectItem key={c.id} value={c.name}>{c.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Target</Label><Input type="number" placeholder="500" value={progForm.target} onChange={e => setProgForm({...progForm, target: e.target.value})} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Campus / Location</Label>
                <Select value={progForm.location_id || '_none'} onValueChange={v => { const lid = v === '_none' ? '' : v; setProgForm({...progForm, location_id: lid, venue_id: ''}); loadVenues(lid); }}>
                  <SelectTrigger><SelectValue placeholder="Select campus" /></SelectTrigger>
                  <SelectContent><SelectItem value="_none">-- Select --</SelectItem>{locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Venue</Label>
                <Select value={progForm.venue_id || '_none'} onValueChange={v => { const vid = v === '_none' ? '' : v; const vn = locationVenues.find(lv => lv.id === vid); setProgForm({...progForm, venue_id: vid, location: vn ? vn.name : progForm.location}); }}>
                  <SelectTrigger><SelectValue placeholder="Select venue" /></SelectTrigger>
                  <SelectContent><SelectItem value="_none">-- None --</SelectItem>{locationVenues.map(v => <SelectItem key={v.id} value={v.id}>{v.name} {v.is_external ? '(External)' : ''}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Or type location</Label><Input placeholder="Custom location" value={progForm.location} onChange={e => setProgForm({...progForm, location: e.target.value})} /></div>
              <div className="space-y-2"><Label>Start Date</Label><Input type="date" value={progForm.start_date} onChange={e => setProgForm({...progForm, start_date: e.target.value})} /></div>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg border border-border">
              <div><p className="text-sm font-medium">Recurring Events</p><p className="text-xs text-muted-foreground">Auto-generate events on schedule</p></div>
              <Switch checked={progForm.is_recurring} onCheckedChange={v => setProgForm({...progForm, is_recurring: v})} />
            </div>
            {progForm.is_recurring && (
              <div className="grid grid-cols-2 gap-3 p-3 bg-muted/50 rounded-lg">
                <div className="space-y-2"><Label>Day of Week</Label>
                  <Select value={progForm.recurrence_pattern} onValueChange={v => setProgForm({...progForm, recurrence_pattern: v})}><SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>{['sunday','monday','tuesday','wednesday','thursday','friday','saturday'].map(d => <SelectItem key={d} value={d}>{d.charAt(0).toUpperCase()+d.slice(1)}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-2"><Label>Nth Week</Label>
                  <Select value={String(progForm.recurrence_day)} onValueChange={v => setProgForm({...progForm, recurrence_day: parseInt(v)})}><SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="1">1st</SelectItem><SelectItem value="2">2nd</SelectItem><SelectItem value="3">3rd</SelectItem><SelectItem value="4">4th</SelectItem><SelectItem value="-1">Last</SelectItem></SelectContent>
                  </Select>
                </div>
                <div className="space-y-2"><Label>Time</Label><Input type="time" value={progForm.recurrence_time} onChange={e => setProgForm({...progForm, recurrence_time: e.target.value})} /></div>
                <div className="space-y-2"><Label>End Time</Label><Input type="time" value={progForm.recurrence_end_time} onChange={e => setProgForm({...progForm, recurrence_end_time: e.target.value})} /></div>
              </div>
            )}
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => { setShowProgram(false); setEditingProg(null); }}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving}>{saving ? 'Saving...' : editingProg ? 'Update' : 'Create'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Session Dialog */}
      <Dialog open={showSession} onOpenChange={setShowSession}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Log Session</DialogTitle></DialogHeader>
          <form onSubmit={handleAddSession} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Program *</Label><Select value={sessionForm.program_id} onValueChange={v => setSessionForm({...sessionForm, program_id: v})}><SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger><SelectContent>{programs.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent></Select></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Date</Label><Input type="date" value={sessionForm.date} onChange={e => setSessionForm({...sessionForm, date: e.target.value})} /></div>
              <div className="space-y-2"><Label>Attendees</Label><Input type="number" value={sessionForm.attendees} onChange={e => setSessionForm({...sessionForm, attendees: e.target.value})} /></div>
            </div>
            <div className="space-y-2"><Label>Location</Label><Input value={sessionForm.location} onChange={e => setSessionForm({...sessionForm, location: e.target.value})} /></div>
            <div className="space-y-2"><Label>Led By</Label><Input value={sessionForm.led_by} onChange={e => setSessionForm({...sessionForm, led_by: e.target.value})} /></div>
            <div className="space-y-2"><Label>Notes</Label><Textarea rows={2} value={sessionForm.notes} onChange={e => setSessionForm({...sessionForm, notes: e.target.value})} /></div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowSession(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving || !sessionForm.program_id}>{saving ? 'Saving...' : 'Log Session'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Generate Recurring Events */}
      <Dialog open={!!showRecurring} onOpenChange={() => setShowRecurring(null)}>
        <DialogContent className="max-w-sm max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Generate Recurring Events</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">{showRecurring?.name}</p>
          {/* key={} forces a full remount when the dialog opens AFTER recurForm
              is populated — fixes a Radix timing issue where SelectValue rendered
              blank because items hadn't registered yet at the time `value` was set. */}
          <div className="space-y-4 mt-2" key={showRecurring?.id || 'closed'}>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Recurrence Pattern</Label>
                <Select value={recurForm.pattern || 'weekly'} onValueChange={v => setRecurForm({...recurForm, pattern: v})}>
                  <SelectTrigger data-testid="outreach-pattern-select">
                    {/* Explicit label fallback — Radix's value→label mapping is
                        flaky when the dialog opens (SelectItems mount lazily inside
                        SelectContent) and would otherwise show blank. */}
                    {({
                      daily: 'Daily',
                      weekly: 'Weekly',
                      biweekly: 'Bi-weekly',
                      monthly: 'Monthly (same date)',
                      bimonthly: 'Bi-monthly (every 2 months)',
                      quarterly: 'Quarterly (every 3 months)',
                      yearly: 'Yearly',
                      nth_week: 'Nth Weekday of Month',
                      nth_month: 'Nth Day of Month',
                    }[recurForm.pattern] || 'Weekly')}
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="daily">Daily</SelectItem>
                    <SelectItem value="weekly">Weekly</SelectItem>
                    <SelectItem value="biweekly">Bi-weekly</SelectItem>
                    <SelectItem value="monthly">Monthly (same date)</SelectItem>
                    <SelectItem value="bimonthly">Bi-monthly (every 2 months)</SelectItem>
                    <SelectItem value="quarterly">Quarterly (every 3 months)</SelectItem>
                    <SelectItem value="yearly">Yearly</SelectItem>
                    <SelectItem value="nth_week">Nth Weekday of Month</SelectItem>
                    <SelectItem value="nth_month">Nth Day of Month</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Occurrences</Label><Input type="number" min={1} max={52} value={recurForm.occurrences} onChange={e => setRecurForm({...recurForm, occurrences: parseInt(e.target.value) || 1})} data-testid="outreach-occurrences" /></div>
            </div>
            {['daily', 'weekly', 'monthly', 'bimonthly', 'quarterly', 'yearly'].includes(recurForm.pattern) && (
              <div className="space-y-2"><Label>Every N {{ weekly: 'weeks', daily: 'days', yearly: 'years', monthly: 'months', bimonthly: 'intervals (2mo)', quarterly: 'intervals (3mo)' }[recurForm.pattern] || 'units'}</Label>
                <Input type="number" min={1} max={12} value={recurForm.interval} onChange={e => setRecurForm({...recurForm, interval: parseInt(e.target.value) || 1})} />
              </div>
            )}
            {['weekly', 'nth_week'].includes(recurForm.pattern) && (
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2"><Label>Day</Label>
                  <Select value={String(recurForm.day_of_week)} onValueChange={v => setRecurForm({...recurForm, day_of_week: parseInt(v)})}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>{['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'].map((d,i) => <SelectItem key={d} value={String(i)}>{d}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                {recurForm.pattern === 'nth_week' && (
                  <div className="space-y-2"><Label>Which</Label>
                    <Select value={String(recurForm.nth_week)} onValueChange={v => setRecurForm({...recurForm, nth_week: parseInt(v)})}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem value="1">1st</SelectItem><SelectItem value="2">2nd</SelectItem><SelectItem value="3">3rd</SelectItem><SelectItem value="4">4th</SelectItem><SelectItem value="-1">Last</SelectItem></SelectContent>
                    </Select>
                  </div>
                )}
              </div>
            )}
            {recurForm.pattern === 'nth_month' && (
              <div className="space-y-2"><Label>Day of Month</Label>
                <Input type="number" min={1} max={31} value={recurForm.day_of_month} onChange={e => setRecurForm({...recurForm, day_of_month: parseInt(e.target.value) || 1})} />
              </div>
            )}
            <div className="space-y-2"><Label>Start Date</Label>
              <Input type="date" value={recurForm.start_date} onChange={e => setRecurForm({...recurForm, start_date: e.target.value})} data-testid="outreach-start-date" />
            </div>
            <div className="space-y-2"><Label>End Date (optional)</Label>
              <Input type="date" value={recurForm.end_date} onChange={e => setRecurForm({...recurForm, end_date: e.target.value})} />
              <p className="text-xs text-muted-foreground">Events stop at this date</p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Time</Label><Input type="time" value={recurForm.time} onChange={e => setRecurForm({...recurForm, time: e.target.value})} /></div>
              <div className="space-y-2"><Label>End Time</Label><Input type="time" value={recurForm.end_time} onChange={e => setRecurForm({...recurForm, end_time: e.target.value})} /></div>
            </div>
            <div className="flex gap-3"><Button variant="outline" className="flex-1" onClick={() => setShowRecurring(null)}>Cancel</Button><Button className="flex-1" onClick={generateRecurring} disabled={saving} data-testid="generate-recurring-btn">{saving ? 'Generating...' : 'Generate Events'}</Button></div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Category Manager */}
      <Dialog open={showCatManager} onOpenChange={setShowCatManager}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Programme Categories</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            {categories.map(c => (
              <div key={c.id} className="flex items-center justify-between p-2 rounded border border-border">
                <div className="flex items-center gap-2"><div className="w-4 h-4 rounded-full" style={{ backgroundColor: c.color }} /><span className="text-sm font-medium">{c.label}</span></div>
                <Button size="sm" variant="ghost" className="text-destructive h-7" onClick={() => deleteCategory(c.id)}><Trash2 size={13} /></Button>
              </div>
            ))}
            <div className="flex gap-2 pt-2 border-t border-border">
              <Input placeholder="New category" value={newCatName} onChange={e => setNewCatName(e.target.value)} className="flex-1" />
              <input type="color" value={newCatColor} onChange={e => setNewCatColor(e.target.value)} className="w-10 h-9 rounded border cursor-pointer" />
              <Button size="sm" onClick={addCategory} disabled={!newCatName.trim()}>Add</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
