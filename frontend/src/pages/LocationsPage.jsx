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
import api from '../services/api';
import { locationsApi, membersApi, venuesApi, groupTypesApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

const CURRENCIES = ['USD','UGX','KES','TZS','RWF','GBP','EUR','ZAR','NGN','GHS','ETB','HTG','THB','CAD','AUD','INR','BRL','MXN'];
const TIMEZONES = [
  'Africa/Kampala', 'Africa/Nairobi', 'Africa/Dar_es_Salaam', 'Africa/Kigali', 'Africa/Bujumbura',
  'Africa/Lagos', 'Africa/Accra', 'Africa/Abidjan', 'Africa/Johannesburg', 'Africa/Cairo',
  'Africa/Addis_Ababa', 'Africa/Lusaka', 'Africa/Harare', 'Africa/Maputo', 'Africa/Kinshasa',
  'Africa/Douala', 'Africa/Dakar', 'Africa/Casablanca', 'Africa/Tunis', 'Africa/Algiers',
  'UTC', 'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Rome', 'Europe/Madrid',
  'Europe/Amsterdam', 'Europe/Brussels', 'Europe/Zurich', 'Europe/Stockholm', 'Europe/Oslo',
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'America/Toronto',
  'America/Vancouver', 'America/Mexico_City', 'America/Bogota', 'America/Lima', 'America/Sao_Paulo',
  'America/Buenos_Aires', 'America/Port-au-Prince', 'America/Havana', 'America/Jamaica',
  'Asia/Dubai', 'Asia/Kolkata', 'Asia/Singapore', 'Asia/Tokyo', 'Asia/Seoul', 'Asia/Shanghai',
  'Asia/Bangkok', 'Asia/Jakarta', 'Asia/Manila', 'Asia/Karachi', 'Asia/Dhaka',
  'Asia/Kuala_Lumpur', 'Asia/Hong_Kong', 'Asia/Taipei', 'Asia/Riyadh', 'Asia/Tehran',
  'Australia/Sydney', 'Australia/Melbourne', 'Australia/Perth', 'Pacific/Auckland', 'Pacific/Fiji',
];

const typeLabels = { main: 'Main', campus: 'Campus', compass: 'Campus', 'sub-location': 'Sub-Location' };
const typeColors = {
  main: 'bg-primary/10 text-primary border-primary/20',
  campus: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-800',
  compass: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-800',
  'sub-location': 'bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:border-slate-700',
};

const emptyForm = {
  name: '', code: '', type: 'campus', parent_id: '', address: '', country: '', country_code: '',
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
  const [venues, setVenues] = useState([]);
  const [groupTypes, setGroupTypes] = useState([]);
  const [showVenueForm, setShowVenueForm] = useState(false);
  const [venueForm, setVenueForm] = useState({ name: '', location_id: '', address: '', capacity: '', is_external: false });
  const [newGroupName, setNewGroupName] = useState('');
  const [newGroupColor, setNewGroupColor] = useState('#6b7280');

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [locRes, staffRes, venueRes, groupRes] = await Promise.all([
        locationsApi.list(),
        membersApi.list({ limit: 200 }),
        venuesApi.list().catch(() => ({ data: [] })),
        groupTypesApi.list().catch(() => ({ data: [] })),
      ]);
      setLocations(locRes.data);
      setAllStaff(staffRes.data?.members || staffRes.data || []);
      setVenues(venueRes.data || []);
      setGroupTypes(groupRes.data || []);
    } catch { toast.error('Failed to load locations'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const toggleExpand = (id) => setExpanded(prev => ({ ...prev, [id]: !prev[id] }));

  const openAdd = (parentId = '', type = 'campus') => {
    setEditing(null);
    setForm({ ...emptyForm, parent_id: parentId, type });
    setDeptInput('');
    setShowModal(true);
  };

  const openEdit = (loc) => {
    setEditing(loc);
    setForm({
      name: loc.name || '', code: loc.code || '', type: loc.type || 'campus',
      parent_id: loc.parent_id || '', address: loc.address || '', country: loc.country || '', country_code: loc.country_code || '',
      currency: loc.currency || 'USD', timezone: loc.timezone || 'Africa/Kampala', contact_name: loc.contact_name || '',
      contact_phone: loc.contact_phone || '', director_id: loc.director_id || '',
      is_venue: loc.is_venue || false, is_bookable: loc.is_bookable || false,
      is_restricted: loc.is_restricted || false, departments: loc.departments || [],
      financial_enabled: loc.financial_enabled !== false, marketplace_enabled: loc.marketplace_enabled !== false,
      financial_apis_enabled: loc.financial_apis_enabled !== false,
      allows_residents: loc.allows_residents !== false,
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
  const campusLocs = locations.filter(l => l.type === 'campus' || l.type === 'compass');
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
          onAddChild={() => openAdd(parent.id, parent.type === 'main' ? 'campus' : 'sub-location')}
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
            {mainLocs.length} main · {campusLocs.length} campuses · {subLocs.length} sub-locations
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

      {/* ===== REASSIGN DATA TOOL (admins only) ===== */}
      {['admin','system_admin','Executive Director'].includes(user?.role) && (
        <ReassignDataTool locations={locations} />
      )}

      {/* ===== VENUE MANAGEMENT ===== */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Venues</h2>
            <p className="text-xs text-muted-foreground">{venues.length} venues ({venues.filter(v => v.is_external).length} external)</p>
          </div>
          <Button size="sm" className="gap-1.5" onClick={() => { setVenueForm({ name: '', location_id: '', address: '', capacity: '', is_external: false }); setShowVenueForm(true); }} data-testid="add-venue-btn"><Plus size={13} /> Add Venue</Button>
        </div>
        {venues.length > 0 && (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {venues.map(v => (
              <Card key={v.id} className="shadow-soft rounded-xl" data-testid={`venue-card-${v.id}`}>
                <CardContent className="p-3 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">{v.name}</p>
                    <p className="text-xs text-muted-foreground">{v.address || locations.find(l => l.id === v.location_id)?.name || 'No location'}</p>
                    <div className="flex gap-1 mt-1">
                      {v.is_external && <Badge variant="outline" className="text-[10px] border-amber-300 text-amber-600">External</Badge>}
                      {v.capacity && <Badge variant="secondary" className="text-[10px]">Cap: {v.capacity}</Badge>}
                    </div>
                  </div>
                  <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={async () => { if (!window.confirm(`Delete venue "${v.name}"?`)) return; await venuesApi.delete(v.id); setVenues(prev => prev.filter(x => x.id !== v.id)); toast.success('Venue deleted'); }} data-testid={`delete-venue-${v.id}`}><Trash2 size={13} /></Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* ===== GROUP TYPES ===== */}
      <div className="space-y-3">
        <h2 className="text-lg font-semibold">Group Types</h2>
        <div className="flex flex-wrap gap-2">
          {groupTypes.map(g => (
            <Badge key={g.id} variant="outline" className="gap-1.5 text-xs cursor-pointer hover:bg-destructive/10" style={{ borderColor: g.color, color: g.color }} onClick={async () => { if (!window.confirm(`Delete group "${g.name}"?`)) return; await groupTypesApi.delete(g.id); setGroupTypes(prev => prev.filter(x => x.id !== g.id)); toast.success('Group deleted'); }} data-testid={`group-type-${g.id}`}>
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: g.color }} /> {g.name} <XCircle size={10} />
            </Badge>
          ))}
        </div>
        <div className="flex gap-2 items-end">
          <div className="flex-1 space-y-1">
            <Label className="text-xs">New Group</Label>
            <Input placeholder="e.g. Elders" value={newGroupName} onChange={e => setNewGroupName(e.target.value)} className="h-8 text-sm" data-testid="new-group-name" />
          </div>
          <Input type="color" value={newGroupColor} onChange={e => setNewGroupColor(e.target.value)} className="w-10 h-8 p-0.5" />
          <Button size="sm" className="h-8" disabled={!newGroupName.trim()} onClick={async () => {
            try { const res = await groupTypesApi.create({ name: newGroupName.trim(), color: newGroupColor }); setGroupTypes(prev => [...prev, res.data]); setNewGroupName(''); toast.success('Group type added'); }
            catch { toast.error('Failed'); }
          }} data-testid="add-group-type-btn">Add</Button>
        </div>
      </div>

      {/* Venue Form Dialog */}
      <Dialog open={showVenueForm} onOpenChange={setShowVenueForm}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Add Venue</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label className="text-xs">Venue Name *</Label><Input value={venueForm.name} onChange={e => setVenueForm({...venueForm, name: e.target.value})} data-testid="venue-name-input" /></div>
            <div className="space-y-1.5"><Label className="text-xs">Campus</Label>
              <Select value={venueForm.location_id || '_none'} onValueChange={v => setVenueForm({...venueForm, location_id: v === '_none' ? '' : v})}>
                <SelectTrigger><SelectValue placeholder="Select campus" /></SelectTrigger>
                <SelectContent><SelectItem value="_none">External (no campus)</SelectItem>{locations.filter(l => l.type !== 'sub-location').map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Address</Label><Input value={venueForm.address} onChange={e => setVenueForm({...venueForm, address: e.target.value})} /></div>
              <div className="space-y-1.5"><Label className="text-xs">Capacity</Label><Input type="number" value={venueForm.capacity} onChange={e => setVenueForm({...venueForm, capacity: e.target.value})} /></div>
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer"><input type="checkbox" className="accent-primary" checked={venueForm.is_external} onChange={e => setVenueForm({...venueForm, is_external: e.target.checked, location_id: e.target.checked ? '' : venueForm.location_id})} /> External venue (not part of any campus)</label>
            <div className="flex gap-3 pt-1">
              <Button variant="outline" className="flex-1" onClick={() => setShowVenueForm(false)}>Cancel</Button>
              <Button className="flex-1" disabled={!venueForm.name.trim()} onClick={async () => {
                try {
                  const payload = { ...venueForm, capacity: venueForm.capacity ? parseInt(venueForm.capacity) : null };
                  const res = await venuesApi.create(payload);
                  setVenues(prev => [...prev, res.data]);
                  setShowVenueForm(false);
                  toast.success('Venue created');
                } catch { toast.error('Failed to create venue'); }
              }} data-testid="save-venue-btn">Create</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>


      {/* Add/Edit Dialog */}
      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit Location' : 'Add Location'}</DialogTitle>
            <DialogDescription>
              {editing ? 'Update location details' : 'Campuses are regional branches. Sub-locations are venues or areas within a campus.'}
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
                    <SelectItem value="campus">Campus</SelectItem>
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

            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-2"><Label>Country</Label>
                <Input placeholder="e.g. Uganda" value={form.country} onChange={e => setForm({...form, country: e.target.value})} />
              </div>
              <div className="space-y-2"><Label>Country Code (ISO)</Label>
                <Input placeholder="e.g. UG" maxLength={2} value={form.country_code} onChange={e => setForm({...form, country_code: e.target.value.toUpperCase()})} data-testid="country-code-input" />
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
                <div className="flex items-center justify-between">
                  <div><p className="text-sm font-medium">Residential</p>
                    <p className="text-xs text-muted-foreground">Allows residents (children, members) to be assigned</p></div>
                  <Switch checked={form.allows_residents !== false} onCheckedChange={v => setForm({...form, allows_residents: v})} data-testid="allows-residents-toggle" />
                </div>
              </div>
            )}

            {/* Feature Toggles (campus level) */}
            {(form.type === 'campus' || form.type === 'main') && (
              <div className="space-y-3 p-3 border border-border rounded-lg">
                <p className="text-xs font-semibold text-muted-foreground uppercase">Feature Access</p>
                <div className="flex items-center justify-between">
                  <div><p className="text-sm font-medium">Financial Module</p>
                    <p className="text-xs text-muted-foreground">Donations, expenses, balance sheets</p></div>
                  <Switch checked={form.financial_enabled !== false} onCheckedChange={v => setForm({...form, financial_enabled: v})} data-testid="financial-toggle" />
                </div>
                <div className="flex items-center justify-between">
                  <div><p className="text-sm font-medium">Marketplace</p>
                    <p className="text-xs text-muted-foreground">Products, sales, POS</p></div>
                  <Switch checked={form.marketplace_enabled !== false} onCheckedChange={v => setForm({...form, marketplace_enabled: v})} data-testid="marketplace-toggle" />
                </div>
                <div className="flex items-center justify-between">
                  <div><p className="text-sm font-medium">HR & Payroll</p>
                    <p className="text-xs text-muted-foreground">Salaries, contracts, payslips</p></div>
                  <Switch checked={form.hr_enabled !== false} onCheckedChange={v => setForm({...form, hr_enabled: v})} data-testid="hr-toggle" />
                </div>
                <div className="flex items-center justify-between">
                  <div><p className="text-sm font-medium">Financial APIs</p>
                    <p className="text-xs text-muted-foreground">Payment gateways, mobile money</p></div>
                  <Switch checked={form.financial_apis_enabled !== false} onCheckedChange={v => setForm({...form, financial_apis_enabled: v})} data-testid="apis-toggle" />
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
             loc.type === 'campus' || loc.type === 'compass' ? <MapPin size={14} className="text-blue-600" /> :
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
            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground" onClick={onAddChild} title={loc.type === 'main' ? 'Add Campus' : 'Add Sub-Location'} data-testid="add-child-btn">
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


// ============== REASSIGN DATA TOOL ==============
function ReassignDataTool({ locations }) {
  const [fromId, setFromId] = useState('');
  const [toId, setToId] = useState('');
  const [preview, setPreview] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);

  const runPreview = async () => {
    if (!fromId) { toast.error('Select source campus'); return; }
    setPreviewing(true); setResult(null);
    try {
      const res = await api.get(`/admin/reassign/preview`, { params: { from_location_id: fromId } });
      setPreview(res.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Preview failed');
    } finally { setPreviewing(false); }
  };

  const runReassign = async () => {
    if (!fromId || !toId) { toast.error('Pick both source and target'); return; }
    if (fromId === toId) { toast.error('Source and target must differ'); return; }
    const total = preview?.total ?? '?';
    if (!window.confirm(`Reassign ${total} records from "${locations.find(l => l.id === fromId)?.name}" → "${locations.find(l => l.id === toId)?.name}"? This cannot be auto-reversed.`)) return;
    setRunning(true);
    try {
      const res = await api.post('/admin/reassign/run', { from_location_id: fromId, to_location_id: toId });
      setResult(res.data);
      toast.success(`Reassigned ${res.data.total} records to ${res.data.target_name}`);
      setPreview(null);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Reassign failed');
    } finally { setRunning(false); }
  };

  const totalRecords = preview ? Object.values(preview.counts).reduce((a, b) => a + b, 0) : 0;

  return (
    <div className="space-y-3 border border-amber-200 dark:border-amber-900/40 rounded-xl p-4 bg-amber-50/40 dark:bg-amber-950/10" data-testid="reassign-tool">
      <div>
        <h2 className="text-lg font-semibold flex items-center gap-2"><Shield size={16} className="text-amber-600" /> Reassign Location Data</h2>
        <p className="text-xs text-muted-foreground">Move all records (events, tasks, sales, HR, members, etc.) from one campus to another. Admin only.</p>
      </div>
      <div className="grid sm:grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs">From Campus</Label>
          <Select value={fromId} onValueChange={(v) => { setFromId(v); setPreview(null); }}>
            <SelectTrigger data-testid="reassign-from-select"><SelectValue placeholder="Select source..." /></SelectTrigger>
            <SelectContent>
              {locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name} <span className="text-muted-foreground text-[10px]">({l.type})</span></SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">To Campus</Label>
          <Select value={toId} onValueChange={setToId}>
            <SelectTrigger data-testid="reassign-to-select"><SelectValue placeholder="Select target..." /></SelectTrigger>
            <SelectContent>
              {locations.filter(l => l.id !== fromId).map(l => <SelectItem key={l.id} value={l.id}>{l.name} <span className="text-muted-foreground text-[10px]">({l.type})</span></SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={runPreview} disabled={!fromId || previewing} data-testid="reassign-preview-btn">
          {previewing ? 'Counting...' : 'Preview Impact'}
        </Button>
        <Button size="sm" onClick={runReassign} disabled={!fromId || !toId || running || totalRecords === 0} data-testid="reassign-run-btn">
          {running ? 'Reassigning...' : `Reassign ${totalRecords || ''} records`}
        </Button>
      </div>
      {preview && (
        <div className="text-xs space-y-1 bg-background/60 rounded-lg p-3 border" data-testid="reassign-preview">
          <p className="font-medium mb-1">Records to be moved (total: {preview.total}):</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-3 gap-y-1">
            {Object.entries(preview.counts).filter(([, n]) => n > 0).map(([k, n]) => (
              <div key={k} className="flex justify-between">
                <span className="text-muted-foreground capitalize">{k.replace(/_/g, ' ')}</span>
                <span className="font-semibold">{n}</span>
              </div>
            ))}
            {preview.total === 0 && <p className="col-span-3 text-muted-foreground">No records to reassign.</p>}
          </div>
        </div>
      )}
      {result && (
        <div className="text-xs space-y-1 bg-emerald-50 dark:bg-emerald-950/20 text-emerald-800 dark:text-emerald-300 rounded-lg p-3 border border-emerald-200 dark:border-emerald-900/30" data-testid="reassign-result">
          <p className="font-medium">✓ Reassigned {result.total} records → {result.target_name}</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-3 gap-y-0.5">
            {Object.entries(result.moved).filter(([, n]) => n > 0).map(([k, n]) => (
              <div key={k} className="flex justify-between">
                <span className="capitalize">{k.replace(/_/g, ' ')}</span>
                <span className="font-semibold">{n}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
