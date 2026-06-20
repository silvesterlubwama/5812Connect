import React, { useState, useEffect } from 'react';
import { Calendar, Clock, Users, Plus, Trash2, Edit2, UserPlus, Check, X, MapPin, RefreshCw, Sparkles } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { volunteerApi, locationsApi, eventsApi, adminApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import { BulkActionBar, exportToCSV, SelectCheckbox } from '../components/BulkActions';

const ROLES = ['General', 'Greeter', 'Usher', 'Worship', 'Children Ministry', 'Media/Tech', 'Security', 'Hospitality', 'Parking'];

export default function VolunteerSchedulingPage() {
  const { user } = useAuth();
  const [shifts, setShifts] = useState([]);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [myShifts, setMyShifts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showAssign, setShowAssign] = useState(null);
  const [locations, setLocations] = useState([]);
  const [events, setEvents] = useState([]);
  const [members, setMembers] = useState([]);
  const [dateFilter, setDateFilter] = useState('');
  const [locationFilter, setLocationFilter] = useState('');

  const [form, setForm] = useState({
    title: '',
    event_id: '',
    location_id: '',
    date: new Date().toISOString().split('T')[0],
    start_time: '09:00',
    end_time: '12:00',
    role: 'General',
    slots: 5,
    notes: '',
  });

  const [assignForm, setAssignForm] = useState({ member_id: '', name: '' });

  // ---- Auto-generate-from-event state ----
  const [showAutoGen, setShowAutoGen] = useState(false);
  const [autoGenEventId, setAutoGenEventId] = useState('');
  const [autoGenRoles, setAutoGenRoles] = useState([]); // [{role, slots}]
  const [autoGenReplace, setAutoGenReplace] = useState(false);
  const [autoGenLoading, setAutoGenLoading] = useState(false);
  const [autoRoleOptions, setAutoRoleOptions] = useState(ROLES);

  useEffect(() => {
    fetchAll();
  }, [dateFilter, locationFilter]);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const params = {};
      if (dateFilter) params.date = dateFilter;
      if (locationFilter) params.location_id = locationFilter;

      // Promise.allSettled — same hardening as iter-172. Volunteer scheduling
      // touches 5 different modules; any one can 403 without taking down the page.
      const results = await Promise.allSettled([
        volunteerApi.shifts(params),
        volunteerApi.myShifts(),
        locationsApi.list(),
        eventsApi.list({ status: 'upcoming' }),
        adminApi.userDirectory(),
      ]);
      const data = (i, fb = []) => results[i].status === 'fulfilled' ? (results[i].value?.data ?? fb) : fb;
      setShifts(data(0));
      setMyShifts(data(1));
      setLocations(data(2));
      setEvents(data(3));
      // Directory returns campus-scoped staff only
      setMembers(data(4));
    } catch {
      toast.error('Failed to load shifts');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!form.title || !form.date) {
      toast.error('Please fill required fields');
      return;
    }
    try {
      const res = await volunteerApi.createShift(form);
      setShifts(prev => [res.data, ...prev]);
      setShowCreate(false);
      resetForm();
      toast.success('Shift created');
    } catch {
      toast.error('Failed to create shift');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this shift?')) return;
    try {
      await volunteerApi.deleteShift(id);
      setShifts(prev => prev.filter(s => s.id !== id));
      toast.success('Shift deleted');
    } catch {
      toast.error('Failed to delete');
    }
  };

  const handleAssign = async () => {
    if (!showAssign?.id || !assignForm.member_id) {
      toast.error('Please select a volunteer');
      return;
    }
    try {
      const member = members.find(m => m.id === assignForm.member_id);
      await volunteerApi.assignVolunteer(showAssign.id, { member_id: assignForm.member_id, name: member?.name || assignForm.name });
      setShifts(prev => prev.map(s => s.id === showAssign.id ? {
        ...s,
        assigned: [...(s.assigned || []), { member_id: assignForm.member_id, name: member?.name || assignForm.name }]
      } : s));
      setShowAssign(null);
      setAssignForm({ member_id: '', name: '' });
      toast.success('Volunteer assigned');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to assign');
    }
  };

  const handleUnassign = async (shiftId, memberId) => {
    try {
      await volunteerApi.unassignVolunteer(shiftId, memberId);
      setShifts(prev => prev.map(s => s.id === shiftId ? {
        ...s,
        assigned: (s.assigned || []).filter(a => a.member_id !== memberId)
      } : s));
      toast.success('Volunteer removed');
    } catch {
      toast.error('Failed to remove');
    }
  };

  const resetForm = () => {
    setForm({
      title: '',
      event_id: '',
      location_id: '',
      date: new Date().toISOString().split('T')[0],
      start_time: '09:00',
      end_time: '12:00',
      role: 'General',
      slots: 5,
      notes: '',
    });
  };

  const getLocationName = (id) => locations.find(l => l.id === id)?.name || 'Unknown';
  const getEventName = (id) => events.find(e => e.id === id)?.title || '';

  // ---- Auto-generate handlers ----
  const openAutoGen = async (eventId) => {
    setShowAutoGen(true);
    setAutoGenEventId(eventId || '');
    setAutoGenReplace(false);
    setAutoGenRoles([]);
    if (eventId) await loadRoleDefaults(eventId);
  };

  const loadRoleDefaults = async (eventId) => {
    const ev = events.find(e => e.id === eventId);
    try {
      const r = await volunteerApi.roleDefaults(ev?.type || '');
      setAutoGenRoles(r.data?.roles || []);
      if (Array.isArray(r.data?.all_role_options) && r.data.all_role_options.length) {
        setAutoRoleOptions(r.data.all_role_options);
      }
    } catch {
      setAutoGenRoles([{ role: 'General', slots: 4 }]);
    }
  };

  const updateAutoRole = (idx, patch) => {
    setAutoGenRoles(prev => prev.map((r, i) => i === idx ? { ...r, ...patch } : r));
  };

  const removeAutoRole = (idx) => {
    setAutoGenRoles(prev => prev.filter((_, i) => i !== idx));
  };

  const addAutoRole = () => {
    setAutoGenRoles(prev => [...prev, { role: 'General', slots: 2 }]);
  };

  const handleAutoGenerate = async () => {
    if (!autoGenEventId) { toast.error('Pick an event first'); return; }
    if (!autoGenRoles.length) { toast.error('Add at least one role'); return; }
    setAutoGenLoading(true);
    try {
      const r = await volunteerApi.generateFromEvent({
        event_id: autoGenEventId,
        roles: autoGenRoles,
        replace: autoGenReplace,
      });
      const created = r.data?.total_created || 0;
      const updated = r.data?.total_updated || 0;
      const skipped = r.data?.total_skipped || 0;
      toast.success(`Generated ${created} new shift(s)${updated ? `, updated ${updated}` : ''}${skipped ? `, skipped ${skipped}` : ''}`);
      setShowAutoGen(false);
      setAutoGenEventId('');
      setAutoGenRoles([]);
      await fetchAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to generate shifts');
    } finally {
      setAutoGenLoading(false);
    }
  };

  return (
    <div className="p-6 space-y-6" data-testid="volunteer-scheduling-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Volunteer Scheduling</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Manage volunteer shifts and assignments</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchAll}><RefreshCw size={14} /></Button>
          <Button variant="outline" className="gap-2" onClick={() => openAutoGen('')} data-testid="auto-generate-shifts-btn">
            <Sparkles size={16} /> Generate from Event
          </Button>
          <Button className="gap-2" onClick={() => setShowCreate(true)} data-testid="create-shift-btn">
            <Plus size={16} /> New Shift
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <Input
          type="date"
          className="w-40"
          value={dateFilter}
          onChange={e => setDateFilter(e.target.value)}
          data-testid="shift-date-filter"
        />
        <Select value={locationFilter || '_all'} onValueChange={v => setLocationFilter(v === '_all' ? '' : v)} className="hidden">
          <SelectTrigger className="w-48 hidden"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="_all">All</SelectItem></SelectContent>
        </Select>
        {dateFilter && (
          <Button variant="ghost" size="sm" onClick={() => setDateFilter('')}>Clear</Button>
        )}
      </div>

      <Tabs defaultValue="all">
        <TabsList>
          <TabsTrigger value="all" data-testid="tab-all-shifts">All Shifts ({shifts.length})</TabsTrigger>
          <TabsTrigger value="my" data-testid="tab-my-shifts">My Shifts ({myShifts.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="all" className="mt-4">
          {loading ? (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {[1, 2, 3].map(i => <div key={i} className="h-40 bg-muted animate-pulse rounded-xl" />)}
            </div>
          ) : shifts.length === 0 ? (
            <Card className="shadow-soft rounded-xl">
              <CardContent className="py-16 text-center">
                <Calendar size={48} className="mx-auto mb-3 opacity-30 text-muted-foreground" />
                <p className="text-muted-foreground mb-4">No shifts scheduled</p>
                <Button onClick={() => setShowCreate(true)} className="gap-2"><Plus size={14} /> Create Shift</Button>
              </CardContent>
            </Card>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {shifts.map(shift => (
                <Card key={shift.id} className="shadow-soft rounded-xl" data-testid={`shift-card-${shift.id}`}>
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <p className="font-semibold">{shift.title}</p>
                        <Badge variant="outline" className="text-xs mt-1">{shift.role}</Badge>
                      </div>
                      <div className="flex gap-1">
                        <Button size="sm" variant="ghost" onClick={() => handleDelete(shift.id)}><Trash2 size={12} /></Button>
                      </div>
                    </div>

                    <div className="space-y-1.5 text-sm text-muted-foreground mb-3">
                      <div className="flex items-center gap-2">
                        <Calendar size={12} /> {shift.date}
                      </div>
                      <div className="flex items-center gap-2">
                        <Clock size={12} /> {shift.start_time} - {shift.end_time}
                      </div>
                      {shift.location_id && (
                        <div className="flex items-center gap-2">
                          <MapPin size={12} /> {getLocationName(shift.location_id)}
                        </div>
                      )}
                    </div>

                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs text-muted-foreground">
                        {(shift.assigned || []).length} / {shift.slots} volunteers
                      </span>
                      <Badge variant={(shift.assigned?.length || 0) >= shift.slots ? 'default' : 'secondary'} className="text-xs">
                        {(shift.assigned?.length || 0) >= shift.slots ? 'Full' : `${shift.slots - (shift.assigned?.length || 0)} spots`}
                      </Badge>
                    </div>

                    {(shift.assigned || []).length > 0 && (
                      <div className="space-y-1 mb-3">
                        {shift.assigned.map(v => (
                          <div key={v.member_id} className="flex items-center justify-between text-xs p-1.5 rounded bg-muted/50">
                            <span>{v.name || v.member_id}</span>
                            <Button size="sm" variant="ghost" className="h-5 w-5 p-0 text-muted-foreground hover:text-destructive" onClick={() => handleUnassign(shift.id, v.member_id)}>
                              <X size={10} />
                            </Button>
                          </div>
                        ))}
                      </div>
                    )}

                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full gap-2"
                      onClick={() => setShowAssign(shift)}
                      disabled={(shift.assigned?.length || 0) >= shift.slots}
                      data-testid={`assign-btn-${shift.id}`}
                    >
                      <UserPlus size={12} /> Assign Volunteer
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="my" className="mt-4">
          {myShifts.length === 0 ? (
            <Card className="shadow-soft rounded-xl">
              <CardContent className="py-16 text-center">
                <Users size={48} className="mx-auto mb-3 opacity-30 text-muted-foreground" />
                <p className="text-muted-foreground">You haven't been assigned to any shifts</p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {myShifts.map(shift => (
                <Card key={shift.id} className="shadow-soft rounded-xl border-primary/30">
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Check size={14} className="text-primary" />
                      <p className="font-semibold">{shift.title}</p>
                    </div>
                    <Badge variant="outline" className="text-xs mb-3">{shift.role}</Badge>
                    <div className="space-y-1.5 text-sm text-muted-foreground">
                      <div className="flex items-center gap-2"><Calendar size={12} /> {shift.date}</div>
                      <div className="flex items-center gap-2"><Clock size={12} /> {shift.start_time} - {shift.end_time}</div>
                      {shift.location_id && <div className="flex items-center gap-2"><MapPin size={12} /> {getLocationName(shift.location_id)}</div>}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Create Shift Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Create Volunteer Shift</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Shift Title *</Label>
              <Input placeholder="e.g., Sunday Morning Ushers" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} data-testid="shift-title-input" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label>Date *</Label>
                <Input type="date" value={form.date} onChange={e => setForm({ ...form, date: e.target.value })} />
              </div>
              <div className="space-y-2">
                <Label>Role</Label>
                <Select value={form.role} onValueChange={v => setForm({ ...form, role: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label>Start Time</Label>
                <Input type="time" value={form.start_time} onChange={e => setForm({ ...form, start_time: e.target.value })} />
              </div>
              <div className="space-y-2">
                <Label>End Time</Label>
                <Input type="time" value={form.end_time} onChange={e => setForm({ ...form, end_time: e.target.value })} />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label>Location</Label>
                <Select value={form.location_id || '_none'} onValueChange={v => setForm({ ...form, location_id: v === '_none' ? '' : v })}>
                  <SelectTrigger><SelectValue placeholder="Select..." /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_none">Select location</SelectItem>
                    {locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Slots Needed</Label>
                <Input type="number" min={1} value={form.slots} onChange={e => setForm({ ...form, slots: parseInt(e.target.value) || 1 })} />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Linked Event (optional)</Label>
              <Select value={form.event_id || '_none'} onValueChange={v => {
                if (v === '_none') { setForm({ ...form, event_id: '' }); return; }
                const ev = events.find(x => x.id === v);
                if (ev) {
                  setForm(prev => ({
                    ...prev,
                    event_id: v,
                    title: prev.title || ev.title || '',
                    date: ev.date || prev.date,
                    start_time: ev.time || prev.start_time,
                    end_time: ev.end_time || prev.end_time,
                    location_id: ev.location_id || prev.location_id,
                  }));
                } else {
                  setForm({ ...form, event_id: v });
                }
              }}>
                <SelectTrigger data-testid="shift-event-select"><SelectValue placeholder="Select event..." /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">No linked event</SelectItem>
                  {events.map(e => <SelectItem key={e.id} value={e.id}>{e.title} ({e.date})</SelectItem>)}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Notes</Label>
              <Input placeholder="Special instructions..." value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
            </div>

            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowCreate(false)}>Cancel</Button>
              <Button className="flex-1" onClick={handleCreate} data-testid="save-shift-btn">Create Shift</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Assign Volunteer Dialog */}
      <Dialog open={!!showAssign} onOpenChange={() => setShowAssign(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Assign Volunteer</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <p className="text-sm text-muted-foreground">Assigning to: <strong>{showAssign?.title}</strong></p>

            <div className="space-y-2">
              <Label>Select Member</Label>
              <Select value={assignForm.member_id || '_none'} onValueChange={v => setAssignForm({ ...assignForm, member_id: v === '_none' ? '' : v })}>
                <SelectTrigger data-testid="assign-member-select"><SelectValue placeholder="Select member..." /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">Select member...</SelectItem>
                  {Array.isArray(members) && members.filter(m => !showAssign?.assigned?.some(a => a.member_id === m.id)).map(m => (
                    <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => setShowAssign(null)}>Cancel</Button>
              <Button className="flex-1" onClick={handleAssign} data-testid="confirm-assign-btn">Assign</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Auto-Generate from Event Dialog */}
      <Dialog open={showAutoGen} onOpenChange={(o) => { setShowAutoGen(o); if (!o) { setAutoGenEventId(''); setAutoGenRoles([]); } }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Sparkles size={18} /> Generate Shifts from Event</DialogTitle>
            <DialogDescription>
              Pick an upcoming event — we will auto-create one shift per role using the event's date, time and location.
              Existing shifts for the same event/role are skipped unless you tick "Update existing".
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-5 mt-2" data-testid="auto-generate-dialog-body">
            <div className="space-y-2">
              <Label>Event *</Label>
              <Select value={autoGenEventId || '_none'} onValueChange={async (v) => {
                const id = v === '_none' ? '' : v;
                setAutoGenEventId(id);
                if (id) await loadRoleDefaults(id);
                else setAutoGenRoles([]);
              }}>
                <SelectTrigger data-testid="autogen-event-select"><SelectValue placeholder="Select event..." /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">Select event...</SelectItem>
                  {events.map(e => (
                    <SelectItem key={e.id} value={e.id}>
                      {e.title} — {e.date} {e.time ? `· ${e.time}` : ''}{e.is_public ? ' · public' : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {autoGenEventId && (() => {
                const ev = events.find(e => e.id === autoGenEventId);
                if (!ev) return null;
                return (
                  <div className="text-xs text-muted-foreground flex flex-wrap gap-3 mt-1">
                    <span className="inline-flex items-center gap-1"><Calendar size={11} /> {ev.date}</span>
                    {ev.time && <span className="inline-flex items-center gap-1"><Clock size={11} /> {ev.time}{ev.end_time ? ` – ${ev.end_time}` : ''}</span>}
                    {ev.location_id && <span className="inline-flex items-center gap-1"><MapPin size={11} /> {getLocationName(ev.location_id)}</span>}
                    {ev.type && <Badge variant="outline" className="text-xs h-5">{ev.type}</Badge>}
                  </div>
                );
              })()}
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>Roles & Slots</Label>
                <Button type="button" size="sm" variant="ghost" className="gap-1" onClick={addAutoRole} data-testid="autogen-add-role-btn">
                  <Plus size={12} /> Add role
                </Button>
              </div>
              {autoGenRoles.length === 0 ? (
                <div className="text-sm text-muted-foreground italic px-1">
                  Pick an event above and we'll suggest a sensible role list automatically.
                </div>
              ) : (
                <div className="space-y-2 max-h-72 overflow-y-auto pr-1" data-testid="autogen-roles-list">
                  {autoGenRoles.map((r, idx) => (
                    <div key={idx} className="flex items-center gap-2 p-2 rounded-md border bg-muted/30">
                      <div className="flex-1">
                        <Select value={r.role} onValueChange={v => updateAutoRole(idx, { role: v })}>
                          <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {autoRoleOptions.map(opt => <SelectItem key={opt} value={opt}>{opt}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="w-24">
                        <Input
                          type="number"
                          min={1}
                          max={200}
                          value={r.slots}
                          onChange={e => updateAutoRole(idx, { slots: parseInt(e.target.value) || 1 })}
                          aria-label="Slots"
                        />
                      </div>
                      <Button type="button" size="sm" variant="ghost" className="h-9 w-9 p-0 text-muted-foreground hover:text-destructive" onClick={() => removeAutoRole(idx)}>
                        <X size={14} />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="rounded"
                checked={autoGenReplace}
                onChange={e => setAutoGenReplace(e.target.checked)}
                data-testid="autogen-replace-checkbox"
              />
              <span>Update existing shifts for this event (refresh slot counts + times)</span>
            </label>

            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowAutoGen(false)}>Cancel</Button>
              <Button
                className="flex-1"
                onClick={handleAutoGenerate}
                disabled={autoGenLoading || !autoGenEventId || autoGenRoles.length === 0}
                data-testid="autogen-confirm-btn"
              >
                {autoGenLoading ? 'Generating…' : `Generate ${autoGenRoles.length} shift${autoGenRoles.length === 1 ? '' : 's'}`}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
