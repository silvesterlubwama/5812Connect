import React, { useState, useEffect } from 'react';
import { MapPin, Plus, Trash2, Edit2, Building2, CheckCircle, XCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { locationsApi } from '../services/api';
import { toast } from 'sonner';

const typeColors = {
  main: 'bg-primary text-primary-foreground',
  branch: 'bg-blue-100 text-blue-700',
  'sub-location': 'bg-slate-100 text-slate-600',
};

const emptyForm = { name: '', code: '', type: 'branch', parent_id: '', address: '', contact_name: '', contact_phone: '' };

export default function LocationsPage() {
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(emptyForm);

  const fetchLocations = async () => {
    setLoading(true);
    try {
      const res = await locationsApi.list();
      setLocations(res.data);
    } catch { toast.error('Failed to load locations'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchLocations(); }, []);

  const openAdd = () => { setEditing(null); setForm(emptyForm); setShowModal(true); };
  const openEdit = (loc) => { setEditing(loc); setForm({ name: loc.name, code: loc.code || '', type: loc.type, parent_id: loc.parent_id || '', address: loc.address || '', contact_name: loc.contact_name || '', contact_phone: loc.contact_phone || '' }); setShowModal(true); };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (editing) {
        const res = await locationsApi.update(editing.id, { ...form, parent_id: form.parent_id || null });
        setLocations(prev => prev.map(l => l.id === editing.id ? res.data : l));
        toast.success('Location updated!');
      } else {
        const res = await locationsApi.create({ ...form, parent_id: form.parent_id || null });
        setLocations(prev => [...prev, res.data]);
        toast.success('Location added!');
      }
      setShowModal(false);
    } catch { toast.error('Failed to save location'); }
    finally { setSaving(false); }
  };

  const deleteLocation = async (id) => {
    if (!window.confirm('Delete this location?')) return;
    await locationsApi.delete(id);
    setLocations(prev => prev.filter(l => l.id !== id));
    toast.success('Location deleted');
  };

  const getParent = (parentId) => locations.find(l => l.id === parentId);
  const mainLocations = locations.filter(l => l.type === 'main');
  const branches = locations.filter(l => l.type === 'branch');
  const subLocations = locations.filter(l => l.type === 'sub-location');

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Locations</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {mainLocations.length} main · {branches.length} branches · {subLocations.length} sub-locations
          </p>
        </div>
        <Button className="gap-2" onClick={openAdd} data-testid="add-location-btn">
          <Plus size={16} /> Add Location
        </Button>
      </div>

      {loading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1,2,3,4].map(i => <div key={i} className="h-48 bg-muted animate-pulse rounded-xl" />)}
        </div>
      ) : (
        <div className="space-y-6">
          {/* Main locations */}
          {mainLocations.map(loc => (
            <div key={loc.id} className="space-y-3">
              <LocationCard loc={loc} onEdit={openEdit} onDelete={deleteLocation} />
              {/* Branches under this main location */}
              {branches.filter(b => b.parent_id === loc.id).map(branch => (
                <div key={branch.id} className="ml-8 space-y-3">
                  <LocationCard loc={branch} onEdit={openEdit} onDelete={deleteLocation} />
                  {/* Sub-locations under this branch */}
                  {subLocations.filter(s => s.parent_id === branch.id).map(sub => (
                    <div key={sub.id} className="ml-8">
                      <LocationCard loc={sub} onEdit={openEdit} onDelete={deleteLocation} />
                    </div>
                  ))}
                </div>
              ))}
              {/* Sub-locations directly under main */}
              {subLocations.filter(s => s.parent_id === loc.id).map(sub => (
                <div key={sub.id} className="ml-8">
                  <LocationCard loc={sub} onEdit={openEdit} onDelete={deleteLocation} />
                </div>
              ))}
            </div>
          ))}
          {/* Orphaned branches/sub-locations */}
          {branches.filter(b => !locations.find(l => l.id === b.parent_id)).map(branch => (
            <LocationCard key={branch.id} loc={branch} onEdit={openEdit} onDelete={deleteLocation} />
          ))}
          {locations.length === 0 && (
            <div className="text-center py-20 text-sm text-muted-foreground">No locations added yet.</div>
          )}
        </div>
      )}

      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{editing ? 'Edit Location' : 'Add Location'}</DialogTitle></DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Name *</Label>
              <Input placeholder="Location name" value={form.name} onChange={e => setForm({...form, name: e.target.value})} required data-testid="location-name-input" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Code</Label>
                <Input placeholder="e.g. MAIN" value={form.code} onChange={e => setForm({...form, code: e.target.value})} />
              </div>
              <div className="space-y-2"><Label>Type</Label>
                <Select value={form.type} onValueChange={v => setForm({...form, type: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="main">Main</SelectItem>
                    <SelectItem value="branch">Branch</SelectItem>
                    <SelectItem value="sub-location">Sub-Location</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            {form.type !== 'main' && (
              <div className="space-y-2"><Label>Parent Location</Label>
                <Select value={form.parent_id} onValueChange={v => setForm({...form, parent_id: v})}>
                  <SelectTrigger><SelectValue placeholder="Select parent" /></SelectTrigger>
                  <SelectContent>
                    {locations.filter(l => l.id !== editing?.id).map(l => (
                      <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="space-y-2"><Label>Address</Label>
              <Input placeholder="Physical address" value={form.address} onChange={e => setForm({...form, address: e.target.value})} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Contact Person</Label>
                <Input placeholder="Name" value={form.contact_name} onChange={e => setForm({...form, contact_name: e.target.value})} />
              </div>
              <div className="space-y-2"><Label>Contact Phone</Label>
                <Input placeholder="+256..." value={form.contact_phone} onChange={e => setForm({...form, contact_phone: e.target.value})} />
              </div>
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowModal(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving} data-testid="save-location-btn">{saving ? 'Saving...' : editing ? 'Update' : 'Add Location'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function LocationCard({ loc, onEdit, onDelete }) {
  const typeColors = {
    main: 'bg-primary/10 text-primary border border-primary/20',
    branch: 'bg-blue-50 text-blue-700 border border-blue-200',
    'sub-location': 'bg-slate-50 text-slate-600 border border-slate-200',
  };

  return (
    <Card className={`shadow-soft rounded-xl ${loc.type === 'main' ? 'border-primary/30' : ''}`} data-testid="location-card">
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-secondary mt-0.5">
              <MapPin size={14} className="text-muted-foreground" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-sm">{loc.name}</h3>
                {loc.code && <span className="text-xs bg-secondary px-1.5 py-0.5 rounded font-mono">{loc.code}</span>}
                <Badge variant="outline" className={`text-xs capitalize ${typeColors[loc.type]}`}>{loc.type}</Badge>
                {loc.active ? (
                  <CheckCircle size={13} className="text-green-500" />
                ) : (
                  <XCircle size={13} className="text-muted-foreground" />
                )}
              </div>
              <div className="space-y-0.5 mt-1.5">
                {loc.address && <p className="text-xs text-muted-foreground">{loc.address}</p>}
                {loc.contact_name && <p className="text-xs text-muted-foreground">{loc.contact_name} {loc.contact_phone && `· ${loc.contact_phone}`}</p>}
              </div>
            </div>
          </div>
          <div className="flex gap-1">
            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground" onClick={() => onEdit(loc)} data-testid="edit-location-btn">
              <Edit2 size={12} />
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={() => onDelete(loc.id)} data-testid="delete-location-btn">
              <Trash2 size={12} />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
