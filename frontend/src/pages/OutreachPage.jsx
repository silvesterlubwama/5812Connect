import React, { useState, useEffect } from 'react';
import { Globe, Plus, Trash2, Users, Calendar, MapPin, RefreshCw } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { outreachApi } from '../services/api';
import { toast } from 'sonner';

const categoryColors = {
  community: 'bg-blue-100 text-blue-700',
  health: 'bg-green-100 text-green-700',
  education: 'bg-purple-100 text-purple-700',
  welfare: 'bg-amber-100 text-amber-700',
  evangelism: 'bg-red-100 text-red-700',
};

const statusColors = { active: 'border-green-500 text-green-600', completed: 'border-slate-400 text-slate-500', paused: 'border-amber-500 text-amber-600' };

export default function OutreachPage() {
  const [programs, setPrograms] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showProgram, setShowProgram] = useState(false);
  const [showSession, setShowSession] = useState(false);
  const [saving, setSaving] = useState(false);
  const [progForm, setProgForm] = useState({ name: '', description: '', category: 'community', status: 'active', location: '', start_date: new Date().toISOString().split('T')[0], target: '' });
  const [sessionForm, setSessionForm] = useState({ program_id: '', date: new Date().toISOString().split('T')[0], time: '', location: '', attendees: '', notes: '', led_by: '' });

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [progRes, sessRes] = await Promise.all([outreachApi.programs(), outreachApi.sessions()]);
      setPrograms(progRes.data);
      setSessions(sessRes.data);
    } catch { toast.error('Failed to load outreach data'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); }, []);

  const handleAddProgram = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await outreachApi.createProgram({ ...progForm, target: progForm.target ? parseInt(progForm.target) : null });
      setPrograms(prev => [res.data, ...prev]);
      setShowProgram(false);
      setProgForm({ name: '', description: '', category: 'community', status: 'active', location: '', start_date: new Date().toISOString().split('T')[0], target: '' });
      toast.success('Program created!');
    } catch { toast.error('Failed to create program'); }
    finally { setSaving(false); }
  };

  const handleAddSession = async (e) => {
    e.preventDefault();
    setSaving(true);
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

  const deleteProgram = async (id) => {
    if (!window.confirm('Delete this program?')) return;
    await outreachApi.deleteProgram(id);
    setPrograms(prev => prev.filter(p => p.id !== id));
    toast.success('Program deleted');
  };

  const totalReached = programs.reduce((s, p) => s + (p.total_reached || 0), 0);

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Outreach</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{programs.length} programs · {totalReached.toLocaleString()} people reached</p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchAll}><RefreshCw size={14} /></Button>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Active Programs', value: programs.filter(p => p.status === 'active').length, color: 'text-green-600' },
          { label: 'Total Sessions', value: sessions.length, color: 'text-blue-600' },
          { label: 'People Reached', value: totalReached.toLocaleString(), color: 'text-primary' },
        ].map((s, i) => (
          <Card key={i} className="shadow-soft rounded-xl">
            <CardContent className="p-4 text-center">
              <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
              <p className="text-xs text-muted-foreground mt-1">{s.label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Tabs defaultValue="programs">
        <TabsList>
          <TabsTrigger value="programs" data-testid="tab-programs">Programs ({programs.length})</TabsTrigger>
          <TabsTrigger value="sessions" data-testid="tab-sessions">Sessions ({sessions.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="programs" className="mt-4">
          <div className="flex justify-end mb-3">
            <Button size="sm" className="gap-2" onClick={() => setShowProgram(true)} data-testid="add-program-btn"><Plus size={14} /> New Program</Button>
          </div>
          {loading ? (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">{[1,2,3].map(i => <div key={i} className="h-48 bg-muted animate-pulse rounded-xl" />)}</div>
          ) : programs.length > 0 ? (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {programs.map(p => (
                <Card key={p.id} className="shadow-soft rounded-xl hover:shadow-soft-lg transition-shadow" data-testid="program-card">
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex-1">
                        <p className="font-semibold text-sm">{p.name}</p>
                        <div className="flex gap-2 mt-1">
                          <Badge variant="outline" className={`text-xs capitalize ${categoryColors[p.category] || ''} border-0`}>{p.category}</Badge>
                          <Badge variant="outline" className={`text-xs capitalize ${statusColors[p.status] || ''}`}>{p.status}</Badge>
                        </div>
                      </div>
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive shrink-0" onClick={() => deleteProgram(p.id)}><Trash2 size={12} /></Button>
                    </div>
                    {p.description && <p className="text-xs text-muted-foreground mb-3 line-clamp-2">{p.description}</p>}
                    <div className="space-y-1 text-xs text-muted-foreground">
                      {p.location && <div className="flex items-center gap-1.5"><MapPin size={11} />{p.location}</div>}
                      <div className="flex items-center gap-1.5"><Users size={11} />{p.total_reached || 0} reached / {p.target || '—'} target</div>
                      <div className="flex items-center gap-1.5"><Calendar size={11} />{p.sessions_count || 0} sessions</div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : <p className="text-center text-sm text-muted-foreground py-12">No programs yet.</p>}
        </TabsContent>

        <TabsContent value="sessions" className="mt-4">
          <div className="flex justify-end mb-3">
            <Button size="sm" className="gap-2" onClick={() => setShowSession(true)} data-testid="add-session-btn"><Plus size={14} /> Log Session</Button>
          </div>
          <Card className="shadow-soft rounded-xl">
            <CardContent className="p-5">
              {loading ? <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-12 bg-muted animate-pulse rounded" />)}</div> :
                sessions.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead><tr className="border-b border-border text-left">
                        <th className="pb-2 font-medium text-muted-foreground">Program</th>
                        <th className="pb-2 font-medium text-muted-foreground">Date</th>
                        <th className="pb-2 font-medium text-muted-foreground">Location</th>
                        <th className="pb-2 font-medium text-muted-foreground">Attendees</th>
                        <th className="pb-2 font-medium text-muted-foreground">Led by</th>
                      </tr></thead>
                      <tbody className="divide-y divide-border">
                        {sessions.map(s => {
                          const prog = programs.find(p => p.id === s.program_id);
                          return (
                            <tr key={s.id} className="hover:bg-accent/30" data-testid="session-row">
                              <td className="py-3 font-medium">{prog?.name || s.program_id}</td>
                              <td className="py-3 text-muted-foreground">{s.date}</td>
                              <td className="py-3 text-muted-foreground">{s.location || '—'}</td>
                              <td className="py-3 font-semibold text-primary">{s.attendees}</td>
                              <td className="py-3 text-muted-foreground">{s.led_by || '—'}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : <p className="text-sm text-muted-foreground text-center py-10">No sessions logged yet.</p>}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={showProgram} onOpenChange={setShowProgram}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New Outreach Program</DialogTitle></DialogHeader>
          <form onSubmit={handleAddProgram} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Program Name *</Label><Input placeholder="Program name" value={progForm.name} onChange={e => setProgForm({...progForm, name: e.target.value})} required data-testid="program-name-input" /></div>
            <div className="space-y-2"><Label>Description</Label><Textarea placeholder="What does this program do?" rows={2} value={progForm.description} onChange={e => setProgForm({...progForm, description: e.target.value})} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Category</Label>
                <Select value={progForm.category} onValueChange={v => setProgForm({...progForm, category: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="community">Community</SelectItem>
                    <SelectItem value="health">Health</SelectItem>
                    <SelectItem value="education">Education</SelectItem>
                    <SelectItem value="welfare">Welfare</SelectItem>
                    <SelectItem value="evangelism">Evangelism</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Target (people)</Label><Input type="number" placeholder="500" value={progForm.target} onChange={e => setProgForm({...progForm, target: e.target.value})} /></div>
            </div>
            <div className="space-y-2"><Label>Location</Label><Input placeholder="Where is this based?" value={progForm.location} onChange={e => setProgForm({...progForm, location: e.target.value})} /></div>
            <div className="space-y-2"><Label>Start Date</Label><Input type="date" value={progForm.start_date} onChange={e => setProgForm({...progForm, start_date: e.target.value})} /></div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowProgram(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving} data-testid="save-program-btn">{saving ? 'Creating...' : 'Create Program'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={showSession} onOpenChange={setShowSession}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Log Outreach Session</DialogTitle></DialogHeader>
          <form onSubmit={handleAddSession} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Program *</Label>
              <Select value={sessionForm.program_id} onValueChange={v => setSessionForm({...sessionForm, program_id: v})}>
                <SelectTrigger><SelectValue placeholder="Select program" /></SelectTrigger>
                <SelectContent>{programs.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Date</Label><Input type="date" value={sessionForm.date} onChange={e => setSessionForm({...sessionForm, date: e.target.value})} /></div>
              <div className="space-y-2"><Label>Attendees</Label><Input type="number" placeholder="0" value={sessionForm.attendees} onChange={e => setSessionForm({...sessionForm, attendees: e.target.value})} /></div>
            </div>
            <div className="space-y-2"><Label>Location</Label><Input placeholder="Session location" value={sessionForm.location} onChange={e => setSessionForm({...sessionForm, location: e.target.value})} /></div>
            <div className="space-y-2"><Label>Led By</Label><Input placeholder="Session leader name" value={sessionForm.led_by} onChange={e => setSessionForm({...sessionForm, led_by: e.target.value})} /></div>
            <div className="space-y-2"><Label>Notes</Label><Textarea rows={2} placeholder="Session highlights..." value={sessionForm.notes} onChange={e => setSessionForm({...sessionForm, notes: e.target.value})} /></div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowSession(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving || !sessionForm.program_id} data-testid="save-session-btn">{saving ? 'Saving...' : 'Log Session'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
