import React, { useState, useEffect, useCallback } from 'react';
import { MapPin, Plus, Trash2, Edit2, CheckCircle, XCircle, Users, DollarSign, Building2, Shield, Globe, ChevronRight, ChevronDown, Clock } from 'lucide-react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Switch } from '../components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { locationsApi, membersApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

const CURRENCIES = ['USD','UGX','KES','TZS','RWF','GBP','EUR','ZAR','NGN','GHS','ETB','HTG'];
const TIMEZONES = [
  'Africa/Kampala', 'Africa/Nairobi', 'Africa/Dar_es_Salaam', 'Africa/Kigali', 'Africa/Bujumbura',
  'Africa/Lagos', 'Africa/Accra', 'Africa/Abidjan', 'Africa/Johannesburg', 'Africa/Cairo',
  'Africa/Addis_Ababa', 'Africa/Lusaka', 'Africa/Harare',
  'UTC', 'Europe/London', 'Europe/Paris', 'Europe/Berlin',
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'America/Toronto',
  'Asia/Dubai', 'Asia/Kolkata', 'Asia/Singapore', 'Asia/Tokyo',
  'Australia/Sydney', 'Pacific/Auckland',
];

const typeLabels = { main: 'Main', compass: 'Compass', 'sub-location': 'Sub-Location' };
const typeColors = {
  main: 'bg-primary/10 text-primary border-primary/20',
  compass: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-800',
  'sub-location': 'bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:border-slate-700',
};

const emptyForm = {
  name: '', code: '', type: 'compass', parent_id: '', address: '', country: '',
  currency: 'USD', timezone: 'Africa/Kampala', contact_name: '', contact_phone: '', director_id: '',
  is_venue: false, is_bookable: false, is_restricted: false, departments: [],
};

export default function LocationsPage() {
  const { user } = useAuth();
  const [locations, setLocations] = useState([]);
  const [allStaff, setAllStaff] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [deptInput, setDeptInput] = useState('');
  const [expanded, setExpanded] = useState({});

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [locRes, staffRes] = await Promise.all([
        locationsApi.list(),
        membersApi.list({ limit: 200 }),
      ]);
      setLocations(locRes.data);
      setAllStaff(staffRes.data?.members || staffRes.data || []);
    } catch { toast.error('Failed to load locations'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const toggleExpand = (id) => setExpanded(prev => ({ ...prev, [id]: !prev[id] }));

  const openAdd = (parentId = '', type = 'compass') => {
    setEditing(null);
    setForm({ ...emptyForm, parent_id: parentId, type });
    setDeptInput('');
    setShowModal(true);
  };

  const openEdit = (loc) => {
    setEditing(loc);
    setForm({
      name: loc.name || '', code: loc.code || '', type: loc.type || 'compass',
      parent_id: loc.parent_id || '', address: loc.address || '', country: loc.country || '',
      currency: loc.currency || 'USD', timezone: loc.timezone || 'Africa/Kampala', contact_name: loc.contact_name || '',
      contact_phone: loc.contact_phone || '', director_id: loc.director_id || '',
      is_venue: loc.is_venue || false, is_bookable: loc.is_bookable || false,
      is_restricted: loc.is_restricted || false, departments: loc.departments || [],
    });
    setDeptInput('');
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = { ...form, parent_id: form.parent_id || null, director_id: form.director_id || null };
      if (editing) {
        const res = await locationsApi.update(editing.id, payload);
        setLocations(prev => prev.map(l => l.id === editing.id ? res.data : l));
        toast.success('Location updated!');
      } else {
        const res = await locationsApi.create(payload);
        setLocations(prev => [...prev, res.data]);
        toast.success('Location added!');
      }
      setShowModal(false);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save');
    } finally { setSaving(false); }
  };

  const deleteLocation = async (id) => {
    const children = locations.filter(l => l.parent_id === id);
    if (children.length > 0) {
      toast.error('Remove child locations first');
      return;
    }
    if (!window.confirm('Delete this location?')) return;
    try {
      await locationsApi.delete(id);
      setLocations(prev => prev.filter(l => l.id !== id));
      toast.success('Location deleted');
    } catch { toast.error('Failed to delete'); }
  };

  const addDept = () => {
    if (deptInput.trim() && !form.departments.includes(deptInput.trim())) {
      setForm(prev => ({ ...prev, departments: [...prev.departments, deptInput.trim()] }));
      setDeptInput('');
    }
  };

  const removeDept = (d) => setForm(prev => ({ ...prev, departments: prev.departments.filter(x => x !== d) }));

  const getDirectorName = (dirId) => {
    const s = allStaff.find(m => m.id === dirId);
    return s ? s.name : '';
  };

  const mainLocs = locations.filter(l => l.type === 'main');
  const compassLocs = locations.filter(l => l.type === 'compass');
  const subLocs = locations.filter(l => l.type === 'sub-location');

  const renderLocationTree = (parent, depth = 0) => {
    const children = locations.filter(l => l.parent_id === parent.id);
    const isExpanded = expanded[parent.id] !== false; // default open
    return (
      <div key={parent.id} className={depth > 0 ? 'ml-6 border-l-2 border-border pl-4' : ''}>
        <LocationCard
          loc={parent}
          childCount={children.length}
          isExpanded={isExpanded}
          onToggle={() => toggleExpand(parent.id)}
          onEdit={() => openEdit(parent)}
          onDelete={() => deleteLocation(parent.id)}
          onAddChild={() => openAdd(parent.id, parent.type === 'main' ? 'compass' : 'sub-location')}
          directorName={getDirectorName(parent.director_id)}
        />
        {isExpanded && children.length > 0 && (
          <div className="mt-2 space-y-2">
            {children.map(child => renderLocationTree(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  // Find root locations (main, or orphans)
  const roots = locations.filter(l => !l.parent_id || !locations.find(p => p.id === l.parent_id));

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading" data-testid="locations-title">Locations</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {mainLocs.length} main · {compassLocs.length} compasses · {subLocs.length} sub-locations
          </p>
        </div>
        <Button className="gap-2" onClick={() => openAdd()} data-testid="add-location-btn">
          <Plus size={16} /> Add Location
        </Button>
      </div>

      {loading ? (
        <div className="space-y-4">
          {[1,2,3].map(i => <div key={i} className="h-24 bg-muted animate-pulse rounded-xl" />)}
        </div>
      ) : locations.length === 0 ? (
        <div className="text-center py-20 text-sm text-muted-foreground">
          <MapPin size={40} className="mx-auto mb-3 opacity-30" />
          No locations added yet.
        </div>
      ) : (
        <div className="space-y-3">
          {roots.map(root => renderLocationTree(root))}
        </div>
      )}

      {/* Add/Edit Dialog */}
      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit Location' : 'Add Location'}</DialogTitle>
            <DialogDescription>
              {editing ? 'Update location details' : 'Compasses are regional branches. Sub-locations are venues or areas within a compass.'}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4 mt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2 col-span-2"><Label>Name *</Label>
                <Input placeholder="Location name" value={form.name} onChange={e => setForm({...form, name: e.target.value})} required data-testid="location-name-input" />
              </div>
              <div className="space-y-2"><Label>Code</Label>
                <Input placeholder="e.g. ETB" value={form.code} onChange={e => setForm({...form, code: e.target.value.toUpperCase()})} />
              </div>
              <div className="space-y-2"><Label>Type</Label>
                <Select value={form.type} onValueChange={v => setForm({...form, type: v})}>
                  <SelectTrigger data-testid="location-type-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="main">Main Organisation</SelectItem>
                    <SelectItem value="compass">Compass</SelectItem>
                    <SelectItem value="sub-location">Sub-Location</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {form.type !== 'main' && (
              <div className="space-y-2"><Label>Parent Location</Label>
                <Select value={form.parent_id || '_none'} onValueChange={v => setForm({...form, parent_id: v === '_none' ? '' : v})}>
                  <SelectTrigger><SelectValue placeholder="Select parent" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_none">None</SelectItem>
                    {locations.filter(l => l.id !== editing?.id).map(l => (
                      <SelectItem key={l.id} value={l.id}>{l.name} ({typeLabels[l.type]})</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Country</Label>
                <Input placeholder="e.g. Uganda" value={form.country} onChange={e => setForm({...form, country: e.target.value})} />
              </div>
              <div className="space-y-2"><Label>Currency</Label>
                <Select value={form.currency} onValueChange={v => setForm({...form, currency: v})}>
                  <SelectTrigger data-testid="currency-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {CURRENCIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Timezone</Label>
                <Select value={form.timezone || 'Africa/Kampala'} onValueChange={v => setForm({...form, timezone: v})}>
                  <SelectTrigger data-testid="timezone-select"><SelectValue /></SelectTrigger>
                  <SelectContent className="max-h-60">
                    {TIMEZONES.map(tz => <SelectItem key={tz} value={tz}>{tz}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2"><Label>Address</Label>
              <Input placeholder="Physical address" value={form.address} onChange={e => setForm({...form, address: e.target.value})} />
            </div>

            <div className="space-y-2"><Label>Location Director (Contact Person)</Label>
              <Select value={form.director_id || '_none'} onValueChange={v => setForm({...form, director_id: v === '_none' ? '' : v, contact_name: v === '_none' ? form.contact_name : (allStaff.find(s => s.id === v)?.name || '')})}>
                <SelectTrigger data-testid="director-select"><SelectValue placeholder="Select from staff" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">Manual entry</SelectItem>
                  {allStaff.map(s => (
                    <SelectItem key={s.id} value={s.id}>{s.name} {s.role ? `(${s.role})` : ''}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {!form.director_id && (
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2"><Label>Contact Name</Label>
                  <Input placeholder="Name" value={form.contact_name} onChange={e => setForm({...form, contact_name: e.target.value})} />
                </div>
                <div className="space-y-2"><Label>Contact Phone</Label>
                  <Input placeholder="+256..." value={form.contact_phone} onChange={e => setForm({...form, contact_phone: e.target.value})} />
                </div>
              </div>
            )}

            {form.type === 'sub-location' && (
              <div className="space-y-3 p-3 rounded-lg border border-border">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Sub-Location Properties</p>
                <div className="flex items-center justify-between">
                  <div><p className="text-sm font-medium">Is a Venue</p>
                    <p className="text-xs text-muted-foreground">This sub-location functions as a venue</p></div>
                  <Switch checked={form.is_venue} onCheckedChange={v => setForm({...form, is_venue: v})} data-testid="is-venue-toggle" />
                </div>
                <div className="flex items-center justify-between">
                  <div><p className="text-sm font-medium">Bookable</p>
                    <p className="text-xs text-muted-foreground">Can be booked for events (1hr buffer between bookings)</p></div>
                  <Switch checked={form.is_bookable} onCheckedChange={v => setForm({...form, is_bookable: v})} data-testid="is-bookable-toggle" />
                </div>
                <div className="flex items-center justify-between">
                  <div><p className="text-sm font-medium">Restricted Access</p>
                    <p className="text-xs text-muted-foreground">Only assigned staff can access</p></div>
                  <Switch checked={form.is_restricted} onCheckedChange={v => setForm({...form, is_restricted: v})} data-testid="is-restricted-toggle" />
                </div>
              </div>
            )}

            {/* Departments */}
            <div className="space-y-2">
              <Label>Departments</Label>
              <div className="flex gap-2">
                <Input placeholder="Add department..." value={deptInput} onChange={e => setDeptInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addDept(); } }} />
                <Button type="button" variant="outline" size="sm" onClick={addDept}>Add</Button>
              </div>
              {form.departments.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {form.departments.map(d => (
                    <Badge key={d} variant="secondary" className="text-xs gap-1 cursor-pointer" onClick={() => removeDept(d)}>
                      {d} <XCircle size={10} />
                    </Badge>
                  ))}
                </div>
              )}
            </div>

            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowModal(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving} data-testid="save-location-btn">
                {saving ? 'Saving...' : editing ? 'Update Location' : 'Add Location'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function LocationCard({ loc, childCount, isExpanded, onToggle, onEdit, onDelete, onAddChild, directorName }) {
  return (
    <Card className={`shadow-soft rounded-xl transition-all hover:shadow-md ${loc.type === 'main' ? 'border-primary/30 border-2' : ''}`} data-testid="location-card">
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          {childCount > 0 && (
            <button onClick={onToggle} className="mt-1.5 p-0.5 rounded hover:bg-accent" data-testid="expand-toggle">
              {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>
          )}
          <div className="p-2 rounded-lg bg-secondary mt-0.5">
            {loc.type === 'main' ? <Globe size={14} className="text-primary" /> :
             loc.type === 'compass' ? <MapPin size={14} className="text-blue-600" /> :
             loc.is_venue ? <Building2 size={14} className="text-amber-600" /> :
             <MapPin size={14} className="text-muted-foreground" />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-semibold text-sm">{loc.name}</h3>
              {loc.code && <span className="text-xs bg-secondary px-1.5 py-0.5 rounded font-mono">{loc.code}</span>}
              <Badge variant="outline" className={`text-xs capitalize border ${typeColors[loc.type]}`}>
                {typeLabels[loc.type] || loc.type}
              </Badge>
              {loc.currency && <Badge variant="outline" className="text-xs gap-1"><DollarSign size={9} />{loc.currency}</Badge>}
              {loc.timezone && <Badge variant="outline" className="text-xs gap-1"><Clock size={9} />{loc.timezone}</Badge>}
              {loc.is_venue && <Badge variant="outline" className="text-xs bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300">Venue</Badge>}
              {loc.is_bookable && <Badge variant="outline" className="text-xs bg-green-50 text-green-700 border-green-200 dark:bg-green-950 dark:text-green-300">Bookable</Badge>}
              {loc.is_restricted && <Badge variant="outline" className="text-xs bg-red-50 text-red-700 border-red-200 dark:bg-red-950 dark:text-red-300"><Shield size={9} className="mr-0.5" />Restricted</Badge>}
              {loc.active ? <CheckCircle size={13} className="text-green-500" /> : <XCircle size={13} className="text-muted-foreground" />}
            </div>
            <div className="space-y-0.5 mt-1.5">
              {loc.address && <p className="text-xs text-muted-foreground">{loc.address}{loc.country ? ` · ${loc.country}` : ''}</p>}
              {(directorName || loc.contact_name) && (
                <p className="text-xs text-muted-foreground">
                  Director: {directorName || loc.contact_name} {loc.contact_phone && `· ${loc.contact_phone}`}
                </p>
              )}
              {loc.departments?.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {loc.departments.map(d => (
                    <span key={d} className="text-[10px] bg-accent px-1.5 py-0.5 rounded">{d}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
          <div className="flex gap-1 shrink-0">
            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground" onClick={onAddChild} title={loc.type === 'main' ? 'Add Compass' : 'Add Sub-Location'} data-testid="add-child-btn">
              <Plus size={12} />
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground" onClick={onEdit} data-testid="edit-location-btn">
              <Edit2 size={12} />
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={onDelete} data-testid="delete-location-btn">
              <Trash2 size={12} />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
