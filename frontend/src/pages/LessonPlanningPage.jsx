import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import api from '../services/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { SearchSelect, guardPickerEscape } from '../components/SearchSelect';
import { toast } from 'sonner';
import { Plus, Trash2, Copy, Printer, ShoppingCart, Calendar, Music, Gamepad2, Cookie, BookOpen, Mail, Bookmark, Pencil } from 'lucide-react';

const API = '/lesson-planning';
const SLOT_KINDS = ['welcome', 'worship', 'story', 'games', 'snacks', 'offering', 'other'];
const blankSlot = () => ({ start: '', duration_min: 15, title: '', kind: 'other', leader_name: '', leader_id: '', notes: '' });

const Row = ({ children, onRemove, testId }) => (
  <div className="flex flex-wrap sm:flex-nowrap gap-1 items-center" data-testid={testId}>
    {children}
    <Button type="button" size="sm" variant="ghost" className="h-8 w-8 shrink-0 p-0 text-destructive" onClick={onRemove}><Trash2 size={12} /></Button>
  </div>
);

export default function LessonPlanningPage() {
  const [events, setEvents] = useState([]);
  const [themes, setThemes] = useState([]);
  const [people, setPeople] = useState([]);
  const [songs, setSongs] = useState([]);
  const [games, setGames] = useState([]);
  const [plan, setPlan] = useState(null);
  const [mySlots, setMySlots] = useState([]);
  const [themeForm, setThemeForm] = useState(null);
  const [dupFor, setDupFor] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [tplForm, setTplForm] = useState(null);      // save-as-template / rename dialog
  const [startFor, setStartFor] = useState(null);    // "blank or from a template?" dialog
  const [emailing, setEmailing] = useState(false);
  const [tab, setTab] = useState('events');
  const [searchParams] = useSearchParams();
  const deepLinked = useRef(false);

  const load = useCallback(async () => {
    try {
      const [ev, th, sg, gm, ms, tp] = await Promise.all([
        api.get(`${API}/outreach-events`),
        api.get(`${API}/themes`),
        api.get(`${API}/library/songs`),
        api.get(`${API}/library/games`),
        api.get(`${API}/my-slots`),
        api.get(`${API}/templates`),
      ]);
      setEvents(ev.data?.events || []);
      setThemes(th.data?.themes || []);
      setSongs(sg.data?.songs || []);
      setGames(gm.data?.games || []);
      setMySlots(ms.data?.slots || []);
      setTemplates(tp.data?.templates || []);
    } catch (e) { toast.error(e?.response?.data?.detail || 'Could not load the planner'); }
    try {
      const r = await api.get('/admin/users/directory');
      const list = r.data?.users || r.data || [];
      setPeople(Array.isArray(list) ? list : []);
    } catch { /* volunteers can still be typed in free */ }
  }, []);
  useEffect(() => { load(); }, [load]);

  const openPlan = async (ev, templateId = '') => {
    try {
      if (ev.plan_id) {
        const r = await api.get(`${API}/plans/${ev.plan_id}`);
        setPlan(r.data);
      } else {
        const r = await api.post(`${API}/plans`, templateId
          ? { event_id: ev.id, template_id: templateId }
          : { event_id: ev.id, slots: [] });
        setPlan(r.data);
        toast.success(templateId ? 'Plan started from the template' : 'Plan started');
        load();
      }
      setStartFor(null);
      setTab('plan');
    } catch (e) { toast.error(e?.response?.data?.detail || 'Could not open the plan'); }
  };

  // Starting fresh offers the saved templates first; an existing plan just opens.
  const startOrOpen = (ev) => {
    if (!ev.plan_id && templates.length > 0) setStartFor(ev);
    else openPlan(ev);
  };

  // "Plan this" from the calendar deep-links here with ?event=<id>.
  useEffect(() => {
    const wanted = searchParams.get('event');
    if (!wanted || deepLinked.current || events.length === 0) return;
    const ev = events.find(e => e.id === wanted);
    if (ev) { deepLinked.current = true; openPlan(ev); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events, searchParams]);

  const savePlan = async (patch = {}) => {
    const body = { ...plan, ...patch };
    try {
      const r = await api.put(`${API}/plans/${plan.id}`, body);
      setPlan(r.data);
      toast.success('Plan saved');
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Save failed'); }
  };

  const set = (k, v) => setPlan(p => ({ ...p, [k]: v }));
  const setList = (k, i, patch) => setPlan(p => ({ ...p, [k]: (p[k] || []).map((x, j) => j === i ? { ...x, ...patch } : x) }));
  const addTo = (k, item) => setPlan(p => ({ ...p, [k]: [...(p[k] || []), item] }));
  const dropFrom = (k, i) => setPlan(p => ({ ...p, [k]: (p[k] || []).filter((_, j) => j !== i) }));

  const runSheet = async () => {
    try {
      const res = await api.get(`${API}/plans/${plan.id}/run-sheet.pdf`, { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `run-sheet-${(plan.event_title || 'outreach').replace(/\s+/g, '-').toLowerCase()}-${plan.date || ''}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success('Run sheet downloaded');
    } catch (e) { toast.error(e?.response?.data?.detail || 'Could not build the run sheet'); }
  };

  const emailRunSheet = async () => {
    setEmailing(true);
    try {
      const r = await api.post(`${API}/plans/${plan.id}/email-run-sheet`, {});
      const { sent_count, failed = [], no_email = [] } = r.data;
      toast.success(`Run sheet emailed to ${sent_count} leader${sent_count === 1 ? '' : 's'}`);
      if (failed.length) toast.error(`Could not reach: ${failed.join(', ')}`);
      if (no_email.length) toast.warning(`No email on file for: ${no_email.join(', ')}`);
    } catch (e) { toast.error(e?.response?.data?.detail || 'Could not send the run sheet'); }
    setEmailing(false);
  };

  const makePo = async () => {
    try {
      const r = await api.post(`${API}/plans/${plan.id}/purchase-order`);
      toast.success(`${r.data.purchase_order.po_number} raised — ${r.data.lines} line(s), total ${r.data.total}`);
      setPlan(p => ({ ...p, purchase_order_number: r.data.purchase_order.po_number }));
    } catch (e) { toast.error(e?.response?.data?.detail || 'Could not raise the order'); }
  };

  const duplicate = async (targetId) => {
    try {
      await api.post(`${API}/plans/${dupFor.id}/duplicate`, { event_id: targetId });
      toast.success('Plan copied — tweak it for the new date');
      setDupFor(null); load();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Copy failed'); }
  };

  const saveTheme = async () => {
    try {
      if (themeForm.id) await api.put(`${API}/themes/${themeForm.id}`, themeForm);
      else await api.post(`${API}/themes`, themeForm);
      toast.success('Theme saved');
      setThemeForm(null); load();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Save failed'); }
  };

  const saveTemplate = async () => {
    try {
      if (tplForm.id) await api.put(`${API}/templates/${tplForm.id}`, { name: tplForm.name, description: tplForm.description });
      else await api.post(`${API}/templates`, { plan_id: plan.id, name: tplForm.name, description: tplForm.description });
      toast.success(tplForm.id ? 'Template updated' : 'Saved as a template');
      setTplForm(null); load();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Save failed'); }
  };

  const deleteTemplate = async (t) => {
    if (!window.confirm(`Delete the template "${t.name}"?`)) return;
    try {
      await api.delete(`${API}/templates/${t.id}`);
      toast.success('Template deleted');
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Delete failed'); }
  };

  const peopleOptions = people.map(p => ({ value: p.id, label: p.name || p.full_name || p.id, hint: p.position || p.role }));

  return (
    <div className="p-4 sm:p-6 max-w-[1200px] mx-auto space-y-5" data-testid="lesson-planning-page">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Outreach planning</h1>
        <p className="text-sm text-muted-foreground">Yearly theme → topic for the day → a run sheet with a leader on every slot.</p>
      </header>

      <Tabs value={tab} onValueChange={setTab} className="space-y-4">
        <TabsList className="w-full flex gap-1 overflow-x-auto no-scrollbar md:flex-wrap md:h-auto md:py-1">
          <TabsTrigger value="events" className="flex-shrink-0" data-testid="lp-tab-events">Outreach events</TabsTrigger>
          <TabsTrigger value="plan" className="flex-shrink-0" disabled={!plan} data-testid="lp-tab-plan">Session plan</TabsTrigger>
          <TabsTrigger value="themes" className="flex-shrink-0" data-testid="lp-tab-themes">Yearly themes</TabsTrigger>
          <TabsTrigger value="templates" className="flex-shrink-0" data-testid="lp-tab-templates">Templates</TabsTrigger>
          <TabsTrigger value="library" className="flex-shrink-0" data-testid="lp-tab-library">Songs &amp; games</TabsTrigger>
          <TabsTrigger value="mine" className="flex-shrink-0" data-testid="lp-tab-mine">My slots</TabsTrigger>
        </TabsList>

        {/* ── outreach events ── */}
        <TabsContent value="events" className="space-y-2">
          {events.length === 0 && (
            <Card><CardContent className="py-12 text-center text-sm text-muted-foreground" data-testid="lp-no-events">
              No outreach events yet. Create one in Events with an outreach type, then plan it here.
            </CardContent></Card>
          )}
          {events.map(ev => (
            <Card key={ev.id} className="rounded-xl" data-testid={`lp-event-${ev.id}`}>
              <CardContent className="p-3 flex flex-wrap items-center gap-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold">{ev.title}</p>
                  <p className="text-xs text-muted-foreground">
                    <Calendar size={11} className="inline mr-1" />{ev.date}{ev.time ? ` · ${ev.time}` : ''}{ev.location ? ` · ${ev.location}` : ''}
                  </p>
                </div>
                {ev.plan_id
                  ? <Badge className="bg-emerald-100 text-emerald-700 text-[10px]" data-testid={`lp-status-${ev.id}`}>Plan ready{ev.plan_topic ? ` · ${ev.plan_topic}` : ''}</Badge>
                  : <Badge variant="outline" className="text-[10px]" data-testid={`lp-status-${ev.id}`}>No plan yet</Badge>}
                <Button size="sm" onClick={() => startOrOpen(ev)} data-testid={`lp-open-${ev.id}`}>
                  {ev.plan_id ? 'Open plan' : 'Start plan'}
                </Button>
                {ev.plan_id && (
                  <Button size="sm" variant="outline" className="gap-1" onClick={() => setDupFor({ id: ev.plan_id })} data-testid={`lp-duplicate-${ev.id}`}>
                    <Copy size={12} />Copy to…
                  </Button>
                )}
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        {/* ── the plan ── */}
        <TabsContent value="plan" className="space-y-4">
          {plan && (
            <>
              <Card><CardHeader className="pb-2 flex flex-row items-start justify-between gap-3 flex-wrap">
                <div>
                  <CardTitle className="text-base">{plan.event_title} · {plan.date}</CardTitle>
                  <p className="text-xs text-muted-foreground">{plan.status === 'final' ? 'Final' : 'Draft'}{plan.purchase_order_number ? ` · ${plan.purchase_order_number} raised` : ''}</p>
                </div>
                <div className="flex gap-2 flex-wrap">
                  <Button size="sm" variant="outline" className="gap-1" onClick={runSheet} data-testid="lp-print"><Printer size={13} />Run sheet PDF</Button>
                  <Button size="sm" variant="outline" className="gap-1" onClick={emailRunSheet} disabled={emailing} data-testid="lp-email-run-sheet"><Mail size={13} />{emailing ? 'Sending…' : 'Email leaders'}</Button>
                  <Button size="sm" variant="outline" className="gap-1" onClick={() => setTplForm({ name: plan.topic_title || plan.event_title || '', description: '' })} data-testid="lp-save-template"><Bookmark size={13} />Save as template</Button>
                  <Button size="sm" variant="outline" className="gap-1" onClick={makePo} data-testid="lp-make-po"><ShoppingCart size={13} />Raise order</Button>
                  <Button size="sm" onClick={() => savePlan()} data-testid="lp-save">Save plan</Button>
                </div>
              </CardHeader>
                <CardContent className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div><Label className="text-xs">Yearly theme</Label>
                    <SearchSelect testId="lp-theme" value={plan.theme_id || ''}
                      onChange={v => { const t = themes.find(x => x.id === v); setPlan(p => ({ ...p, theme_id: v, theme_name: t?.name || '' })); }}
                      placeholder="Type to find a theme"
                      options={themes.map(t => ({ value: t.id, label: `${t.year} — ${t.name}`, hint: t.scripture }))} />
                  </div>
                  <div><Label className="text-xs">Topic for the day / month</Label>
                    <Input value={plan.topic_title || ''} onChange={e => set('topic_title', e.target.value)} data-testid="lp-topic" /></div>
                  <div><Label className="text-xs">Memory verse</Label>
                    <Input value={plan.memory_verse || ''} onChange={e => set('memory_verse', e.target.value)} data-testid="lp-verse" /></div>
                  <div><Label className="text-xs">Attendance target</Label>
                    <Input type="number" min="0" value={plan.attendance_target || 0} onChange={e => set('attendance_target', e.target.value)} data-testid="lp-target" /></div>
                </CardContent>
              </Card>

              {/* time slots */}
              <Card><CardHeader className="pb-2 flex flex-row items-center justify-between">
                <CardTitle className="text-sm">Running order</CardTitle>
                <Button size="sm" variant="ghost" onClick={() => addTo('slots', blankSlot())} data-testid="lp-add-slot"><Plus size={12} className="mr-1" />Add slot</Button>
              </CardHeader>
                <CardContent className="space-y-2" data-testid="lp-slots">
                  {(plan.slots || []).length === 0 && <p className="text-xs text-muted-foreground">No slots yet — add the welcome, worship, story, games and snacks.</p>}
                  {(plan.slots || []).map((s, i) => (
                    <div key={s.id || i} className="rounded-lg border p-2 space-y-1" data-testid={`lp-slot-${i}`}>
                      <div className="flex flex-wrap sm:flex-nowrap gap-1 items-center">
                        <Input className="w-20 shrink-0 h-8 text-xs" placeholder="09:00" value={s.start} onChange={e => setList('slots', i, { start: e.target.value })} data-testid={`lp-slot-start-${i}`} />
                        <Input className="w-16 shrink-0 h-8 text-xs" type="number" min="0" value={s.duration_min} onChange={e => setList('slots', i, { duration_min: e.target.value })} data-testid={`lp-slot-mins-${i}`} />
                        <Input className="flex-1 min-w-0 h-8 text-xs" placeholder="What happens in this slot" value={s.title} onChange={e => setList('slots', i, { title: e.target.value })} data-testid={`lp-slot-title-${i}`} />
                        <Button type="button" size="sm" variant="ghost" className="h-8 w-8 shrink-0 p-0 text-destructive" onClick={() => dropFrom('slots', i)}><Trash2 size={12} /></Button>
                      </div>
                      <div className="flex flex-wrap sm:flex-nowrap gap-1">
                        <SearchSelect size="sm" className="w-full sm:w-32" testId={`lp-slot-kind-${i}`} value={s.kind}
                          onChange={v => setList('slots', i, { kind: v })}
                          options={SLOT_KINDS.map(k => ({ value: k, label: k }))} />
                        <SearchSelect size="sm" className="w-full sm:flex-1" testId={`lp-slot-leader-${i}`} value={s.leader_id}
                          onChange={v => { const p = people.find(x => x.id === v); setList('slots', i, { leader_id: v, leader_name: p?.name || p?.full_name || '' }); }}
                          placeholder={s.leader_name || 'Leader / volunteer'} allowClear options={peopleOptions} />
                        <Input className="w-full sm:flex-1 min-w-0 h-8 text-xs" placeholder="Notes" value={s.notes} onChange={e => setList('slots', i, { notes: e.target.value })} />
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* worship */}
                <Card><CardHeader className="pb-2 flex flex-row items-center justify-between">
                  <CardTitle className="text-sm flex items-center gap-1.5"><Music size={14} />Worship set</CardTitle>
                  <Button size="sm" variant="ghost" onClick={() => addTo('songs', { name: '', key: '' })} data-testid="lp-add-song"><Plus size={12} /></Button>
                </CardHeader>
                  <CardContent className="space-y-1" data-testid="lp-songs">
                    {(plan.songs || []).map((s, i) => (
                      <Row key={i} onRemove={() => dropFrom('songs', i)} testId={`lp-song-${i}`}>
                        <SearchSelect size="sm" className="flex-1" testId={`lp-song-pick-${i}`} value={s.song_id || ''}
                          onChange={v => { const so = songs.find(x => x.id === v); setList('songs', i, { song_id: v, name: so?.name || '', key: so?.key || s.key }); }}
                          placeholder={s.name || 'Type a song'} options={songs.map(so => ({ value: so.id, label: so.name, hint: so.key }))} />
                        <Input className="w-full sm:w-36 min-w-0 h-8 text-xs" placeholder="Or a new song" value={s.name || ''} onChange={e => setList('songs', i, { name: e.target.value, song_id: '' })} data-testid={`lp-song-name-${i}`} />
                        <Input className="w-16 shrink-0 h-8 text-xs" placeholder="Key" value={s.key || ''} onChange={e => setList('songs', i, { key: e.target.value })} />
                      </Row>
                    ))}
                  </CardContent>
                </Card>

                {/* games */}
                <Card><CardHeader className="pb-2 flex flex-row items-center justify-between">
                  <CardTitle className="text-sm flex items-center gap-1.5"><Gamepad2 size={14} />Games</CardTitle>
                  <Button size="sm" variant="ghost" onClick={() => addTo('games', { name: '', age_range: '', duration_min: 10 })} data-testid="lp-add-game"><Plus size={12} /></Button>
                </CardHeader>
                  <CardContent className="space-y-1" data-testid="lp-games">
                    {(plan.games || []).map((g, i) => (
                      <Row key={i} onRemove={() => dropFrom('games', i)} testId={`lp-game-${i}`}>
                        <SearchSelect size="sm" className="flex-1" testId={`lp-game-pick-${i}`} value={g.game_id || ''}
                          onChange={v => { const ga = games.find(x => x.id === v); setList('games', i, { game_id: v, name: ga?.name || '', age_range: ga?.age_range || '', kit: ga?.kit || '' }); }}
                          placeholder={g.name || 'Type a game'} options={games.map(ga => ({ value: ga.id, label: ga.name, hint: ga.age_range }))} />
                        <Input className="w-full sm:w-32 min-w-0 h-8 text-xs" placeholder="Or a new game" value={g.name || ''} onChange={e => setList('games', i, { name: e.target.value, game_id: '' })} data-testid={`lp-game-name-${i}`} />
                        <Input className="w-20 shrink-0 h-8 text-xs" placeholder="Ages" value={g.age_range || ''} onChange={e => setList('games', i, { age_range: e.target.value })} />
                      </Row>
                    ))}
                  </CardContent>
                </Card>

                {/* story */}
                <Card><CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-1.5"><BookOpen size={14} />Story / teaching</CardTitle></CardHeader>
                  <CardContent className="space-y-2">
                    <Input placeholder="Story title" value={plan.story?.title || ''} onChange={e => set('story', { ...(plan.story || {}), title: e.target.value })} data-testid="lp-story-title" />
                    <Input placeholder="Passage" value={plan.story?.passage || ''} onChange={e => set('story', { ...(plan.story || {}), passage: e.target.value })} data-testid="lp-story-passage" />
                    <Textarea rows={2} placeholder="Main point" value={plan.story?.main_point || ''} onChange={e => set('story', { ...(plan.story || {}), main_point: e.target.value })} data-testid="lp-story-point" />
                    <Textarea rows={2} placeholder="Discussion questions (one per line)" value={(plan.story?.questions || []).join('\n')} onChange={e => set('story', { ...(plan.story || {}), questions: e.target.value.split('\n') })} data-testid="lp-story-questions" />
                  </CardContent>
                </Card>

                {/* snacks + materials + extras */}
                <Card><CardHeader className="pb-2 flex flex-row items-center justify-between">
                  <CardTitle className="text-sm flex items-center gap-1.5"><Cookie size={14} />Snacks, drinks &amp; kit</CardTitle>
                  <div>
                    <Button size="sm" variant="ghost" onClick={() => addTo('snacks', { item: '', servings: '', who: '', cost: '' })} data-testid="lp-add-snack"><Plus size={12} />Snack</Button>
                    <Button size="sm" variant="ghost" onClick={() => addTo('materials', { item: '', cost: '' })} data-testid="lp-add-material"><Plus size={12} />Kit</Button>
                  </div>
                </CardHeader>
                  <CardContent className="space-y-1" data-testid="lp-snacks">
                    {(plan.snacks || []).map((s, i) => (
                      <Row key={i} onRemove={() => dropFrom('snacks', i)} testId={`lp-snack-${i}`}>
                        <Input className="flex-1 min-w-0 h-8 text-xs" placeholder="Snack or drink" value={s.item || ''} onChange={e => setList('snacks', i, { item: e.target.value })} data-testid={`lp-snack-item-${i}`} />
                        <Input className="w-16 shrink-0 h-8 text-xs" type="number" placeholder="Qty" value={s.servings || ''} onChange={e => setList('snacks', i, { servings: e.target.value })} />
                        <Input className="w-24 shrink-0 h-8 text-xs" placeholder="Who brings" value={s.who || ''} onChange={e => setList('snacks', i, { who: e.target.value })} />
                        <Input className="w-20 shrink-0 h-8 text-xs" type="number" placeholder="Cost" value={s.cost || ''} onChange={e => setList('snacks', i, { cost: e.target.value })} />
                      </Row>
                    ))}
                    {(plan.materials || []).map((m, i) => (
                      <Row key={`m${i}`} onRemove={() => dropFrom('materials', i)} testId={`lp-material-${i}`}>
                        <Input className="flex-1 min-w-0 h-8 text-xs" placeholder="Material / kit item" value={m.item || ''} onChange={e => setList('materials', i, { item: e.target.value })} data-testid={`lp-material-item-${i}`} />
                        <Input className="w-20 shrink-0 h-8 text-xs" type="number" placeholder="Cost" value={m.cost || ''} onChange={e => setList('materials', i, { cost: e.target.value })} />
                      </Row>
                    ))}
                    <div className="pt-2 border-t space-y-2">
                      <label className="flex items-center gap-2 text-xs">
                        <input type="checkbox" checked={!!plan.offering?.planned} onChange={e => set('offering', { ...(plan.offering || {}), planned: e.target.checked })} data-testid="lp-offering-toggle" />
                        Offering / donation slot
                      </label>
                      {plan.offering?.planned && (
                        <div className="flex gap-1">
                          <Input className="flex-1 min-w-0 h-8 text-xs" placeholder="Purpose" value={plan.offering?.purpose || ''} onChange={e => set('offering', { ...plan.offering, purpose: e.target.value })} data-testid="lp-offering-purpose" />
                          <Input className="w-24 shrink-0 h-8 text-xs" type="number" placeholder="Target" value={plan.offering?.target || ''} onChange={e => set('offering', { ...plan.offering, target: e.target.value })} />
                        </div>
                      )}
                      <Input className="h-8 text-xs" placeholder="Take-home for the children" value={plan.take_home || ''} onChange={e => set('take_home', e.target.value)} data-testid="lp-take-home" />
                      <Textarea rows={2} placeholder="After the event — what we'd do differently" value={plan.notes_after || ''} onChange={e => set('notes_after', e.target.value)} data-testid="lp-notes-after" />
                    </div>
                  </CardContent>
                </Card>
              </div>

              <div className="flex gap-2 flex-wrap">
                <Button onClick={() => savePlan()} data-testid="lp-save-bottom">Save plan</Button>
                <Button variant="outline" onClick={() => savePlan({ status: plan.status === 'final' ? 'draft' : 'final' })} data-testid="lp-toggle-final">
                  {plan.status === 'final' ? 'Back to draft' : 'Mark final'}
                </Button>
              </div>
            </>
          )}
        </TabsContent>

        {/* ── themes ── */}
        <TabsContent value="themes" className="space-y-2">
          <Button size="sm" onClick={() => setThemeForm({ year: new Date().getFullYear(), name: '', scripture: '', description: '', topics: [] })} data-testid="lp-new-theme"><Plus size={13} className="mr-1" />New yearly theme</Button>
          {themes.map(t => (
            <Card key={t.id} data-testid={`lp-theme-${t.id}`}><CardContent className="p-3">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div><p className="text-sm font-semibold">{t.year} — {t.name}</p>
                  <p className="text-xs text-muted-foreground">{t.scripture} {t.topics?.length ? `· ${t.topics.length} topic(s)` : ''}</p></div>
                <Button size="sm" variant="outline" onClick={() => setThemeForm(t)} data-testid={`lp-edit-theme-${t.id}`}>Edit</Button>
              </div>
            </CardContent></Card>
          ))}
        </TabsContent>

        {/* ── templates ── */}
        <TabsContent value="templates" className="space-y-2">
          <p className="text-xs text-muted-foreground" data-testid="lp-templates-hint">
            Save a favourite session, then start future outreach from it. Templates keep the running order,
            worship set, games, story, snacks and kit — the leaders are left blank for whoever is on that week.
          </p>
          {templates.length === 0 && (
            <Card><CardContent className="py-12 text-center text-sm text-muted-foreground" data-testid="lp-no-templates">
              No templates yet. Open a plan you like and tap "Save as template".
            </CardContent></Card>
          )}
          {templates.map(t => (
            <Card key={t.id} data-testid={`lp-template-${t.id}`}><CardContent className="p-3 flex flex-wrap items-center gap-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold">{t.name}</p>
                <p className="text-xs text-muted-foreground">
                  {t.slot_count} slot(s) · {t.song_count} song(s) · {t.game_count} game(s)
                  {t.used_count ? ` · used ${t.used_count}×` : ''}{t.created_by_name ? ` · by ${t.created_by_name}` : ''}
                </p>
                {t.description && <p className="text-xs text-muted-foreground mt-0.5">{t.description}</p>}
              </div>
              <Button size="sm" variant="outline" className="gap-1" onClick={() => setTplForm({ id: t.id, name: t.name, description: t.description || '' })} data-testid={`lp-edit-template-${t.id}`}><Pencil size={12} />Rename</Button>
              <Button size="sm" variant="ghost" className="text-destructive h-8 w-8 p-0" onClick={() => deleteTemplate(t)} data-testid={`lp-delete-template-${t.id}`}><Trash2 size={13} /></Button>
            </CardContent></Card>
          ))}
        </TabsContent>

        {/* ── libraries ── */}
        <TabsContent value="library" className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Song library ({songs.length})</CardTitle></CardHeader>
            <CardContent className="space-y-1 text-xs" data-testid="lp-song-library">
              {songs.length === 0 && <p className="text-muted-foreground">Songs you type into a plan are remembered here.</p>}
              {songs.map(s => <p key={s.id}>{s.name}{s.key ? ` · ${s.key}` : ''}</p>)}
            </CardContent></Card>
          <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Game library ({games.length})</CardTitle></CardHeader>
            <CardContent className="space-y-1 text-xs" data-testid="lp-game-library">
              {games.length === 0 && <p className="text-muted-foreground">Games you type into a plan are remembered here.</p>}
              {games.map(g => <p key={g.id}>{g.name}{g.age_range ? ` · ${g.age_range}` : ''}</p>)}
            </CardContent></Card>
        </TabsContent>

        {/* ── my slots ── */}
        <TabsContent value="mine">
          <Card><CardHeader className="pb-2"><CardTitle className="text-sm">My slots this week</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm" data-testid="lp-my-slots">
              {mySlots.length === 0 && <p className="text-xs text-muted-foreground">Nothing assigned to you in the next 7 days.</p>}
              {mySlots.map((s, i) => (
                <div key={i} className="rounded-lg border p-2" data-testid={`lp-my-slot-${i}`}>
                  <p className="font-medium">{s.start} · {s.title || s.kind}</p>
                  <p className="text-xs text-muted-foreground">{s.event_title} · {s.date}{s.topic ? ` · ${s.topic}` : ''}</p>
                </div>
              ))}
            </CardContent></Card>
        </TabsContent>
      </Tabs>

      {/* theme editor */}
      <Dialog open={!!themeForm} onOpenChange={o => !o && setThemeForm(null)}>
        <DialogContent className="max-w-lg" onEscapeKeyDown={guardPickerEscape}>
          <DialogHeader><DialogTitle>{themeForm?.id ? 'Edit theme' : 'New yearly theme'}</DialogTitle></DialogHeader>
          {themeForm && (
            <div className="space-y-2">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <div><Label className="text-xs">Year</Label><Input type="number" value={themeForm.year} onChange={e => setThemeForm({ ...themeForm, year: e.target.value })} data-testid="lp-theme-year" /></div>
                <div className="sm:col-span-2"><Label className="text-xs">Theme</Label><Input value={themeForm.name} onChange={e => setThemeForm({ ...themeForm, name: e.target.value })} data-testid="lp-theme-name" /></div>
              </div>
              <div><Label className="text-xs">Scripture</Label><Input value={themeForm.scripture || ''} onChange={e => setThemeForm({ ...themeForm, scripture: e.target.value })} data-testid="lp-theme-scripture" /></div>
              <div className="flex items-center justify-between">
                <Label className="text-xs">Topics through the year</Label>
                <Button size="sm" variant="ghost" onClick={() => setThemeForm({ ...themeForm, topics: [...(themeForm.topics || []), { period: '', title: '', memory_verse: '' }] })} data-testid="lp-theme-add-topic"><Plus size={12} />Add</Button>
              </div>
              {(themeForm.topics || []).map((t, i) => (
                <div key={i} className="flex flex-wrap sm:flex-nowrap gap-1">
                  <Input className="w-full sm:w-28 h-8 text-xs" placeholder="2026-07" value={t.period} onChange={e => setThemeForm({ ...themeForm, topics: themeForm.topics.map((x, j) => j === i ? { ...x, period: e.target.value } : x) })} data-testid={`lp-theme-topic-period-${i}`} />
                  <Input className="flex-1 min-w-0 h-8 text-xs" placeholder="Topic" value={t.title} onChange={e => setThemeForm({ ...themeForm, topics: themeForm.topics.map((x, j) => j === i ? { ...x, title: e.target.value } : x) })} data-testid={`lp-theme-topic-title-${i}`} />
                  <Button size="sm" variant="ghost" className="h-8 w-8 shrink-0 p-0 text-destructive" onClick={() => setThemeForm({ ...themeForm, topics: themeForm.topics.filter((_, j) => j !== i) })}><Trash2 size={12} /></Button>
                </div>
              ))}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setThemeForm(null)}>Cancel</Button>
            <Button onClick={saveTheme} data-testid="lp-theme-save">Save theme</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* save as template / rename */}
      <Dialog open={!!tplForm} onOpenChange={o => !o && setTplForm(null)}>
        <DialogContent className="max-w-md" onEscapeKeyDown={guardPickerEscape}>
          <DialogHeader><DialogTitle>{tplForm?.id ? 'Rename template' : 'Save as template'}</DialogTitle></DialogHeader>
          {tplForm && (
            <div className="space-y-2">
              <div><Label className="text-xs">Template name</Label>
                <Input value={tplForm.name} onChange={e => setTplForm({ ...tplForm, name: e.target.value })} placeholder="e.g. Standard Saturday kids club" data-testid="lp-template-name" /></div>
              <div><Label className="text-xs">When to use it (optional)</Label>
                <Textarea rows={2} value={tplForm.description} onChange={e => setTplForm({ ...tplForm, description: e.target.value })} data-testid="lp-template-description" /></div>
              {!tplForm.id && <p className="text-xs text-muted-foreground">Leaders are not saved — you'll pick them each week.</p>}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setTplForm(null)}>Cancel</Button>
            <Button onClick={saveTemplate} data-testid="lp-template-save">Save template</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* start blank or from a template */}
      <Dialog open={!!startFor} onOpenChange={o => !o && setStartFor(null)}>
        <DialogContent className="max-w-md" onEscapeKeyDown={guardPickerEscape}>
          <DialogHeader><DialogTitle>Start {startFor?.title}</DialogTitle></DialogHeader>
          <div className="space-y-1 max-h-72 overflow-y-auto">
            <Button variant="outline" className="w-full justify-start text-xs" onClick={() => openPlan(startFor)} data-testid="lp-start-blank">
              Start from blank
            </Button>
            {templates.map(t => (
              <Button key={t.id} variant="outline" className="w-full justify-start text-xs" onClick={() => openPlan(startFor, t.id)} data-testid={`lp-start-template-${t.id}`}>
                <Bookmark size={12} className="mr-1.5 shrink-0" />{t.name} · {t.slot_count} slot(s)
              </Button>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      {/* duplicate onto another event */}
      <Dialog open={!!dupFor} onOpenChange={o => !o && setDupFor(null)}>
        <DialogContent className="max-w-md" onEscapeKeyDown={guardPickerEscape}>
          <DialogHeader><DialogTitle>Copy this plan onto…</DialogTitle></DialogHeader>
          <div className="space-y-1 max-h-72 overflow-y-auto">
            {events.filter(e => !e.plan_id).map(e => (
              <Button key={e.id} variant="outline" className="w-full justify-start text-xs" onClick={() => duplicate(e.id)} data-testid={`lp-dup-target-${e.id}`}>
                {e.date} · {e.title}
              </Button>
            ))}
            {events.filter(e => !e.plan_id).length === 0 && <p className="text-xs text-muted-foreground">Every outreach event already has a plan.</p>}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
