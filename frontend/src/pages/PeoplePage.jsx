import React, { useState, useEffect } from 'react';
import { Plus, Trash2, Search, Heart, Baby, Users } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { familiesApi, childrenApi, guestsApi } from '../services/api';
import { toast } from 'sonner';

export default function PeoplePage() {
  const [families, setFamilies] = useState([]);
  const [children, setChildren] = useState([]);
  const [guests, setGuests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showFamily, setShowFamily] = useState(false);
  const [showChild, setShowChild] = useState(false);
  const [showGuest, setShowGuest] = useState(false);
  const [saving, setSaving] = useState(false);
  const [familyForm, setFamilyForm] = useState({ family_name: '', primary_contact_name: '', primary_contact_email: '', primary_contact_phone: '', address: '' });
  const [childForm, setChildForm] = useState({ name: '', date_of_birth: '', gender: '', family_id: '', class_group: '', medical_notes: '', allergies: '' });
  const [guestForm, setGuestForm] = useState({ name: '', email: '', phone: '', visit_date: '', referred_by: '', address: '', notes: '' });

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [famRes, chdRes, gstRes] = await Promise.all([
        familiesApi.list(),
        childrenApi.list(),
        guestsApi.list(),
      ]);
      setFamilies(famRes.data);
      setChildren(chdRes.data);
      setGuests(gstRes.data);
    } catch { toast.error('Failed to load people data'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); }, []);

  const getChildrenForFamily = (fid) => children.filter(c => c.family_id === fid);

  const handleAddFamily = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await familiesApi.create(familyForm);
      setFamilies(prev => [res.data, ...prev]);
      setShowFamily(false);
      setFamilyForm({ family_name: '', primary_contact_name: '', primary_contact_email: '', primary_contact_phone: '', address: '' });
      toast.success('Family added!');
    } catch { toast.error('Failed to add family'); }
    finally { setSaving(false); }
  };

  const handleAddChild = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await childrenApi.create(childForm);
      setChildren(prev => [res.data, ...prev]);
      setShowChild(false);
      setChildForm({ name: '', date_of_birth: '', gender: '', family_id: '', class_group: '', medical_notes: '', allergies: '' });
      toast.success('Child added!');
    } catch { toast.error('Failed to add child'); }
    finally { setSaving(false); }
  };

  const handleAddGuest = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await guestsApi.create(guestForm);
      setGuests(prev => [res.data, ...prev]);
      setShowGuest(false);
      setGuestForm({ name: '', email: '', phone: '', visit_date: '', referred_by: '', address: '', notes: '' });
      toast.success('Guest recorded!');
    } catch { toast.error('Failed to record guest'); }
    finally { setSaving(false); }
  };

  const deleteFamily = async (id) => {
    if (!window.confirm('Delete this family?')) return;
    await familiesApi.delete(id);
    setFamilies(prev => prev.filter(f => f.id !== id));
    toast.success('Family deleted');
  };

  const deleteChild = async (id) => {
    if (!window.confirm('Delete this child record?')) return;
    await childrenApi.delete(id);
    setChildren(prev => prev.filter(c => c.id !== id));
    toast.success('Deleted');
  };

  const deleteGuest = async (id) => {
    await guestsApi.delete(id);
    setGuests(prev => prev.filter(g => g.id !== id));
    toast.success('Guest removed');
  };

  const filteredFamilies = families.filter(f =>
    f.family_name?.toLowerCase().includes(search.toLowerCase()) ||
    f.primary_contact_name?.toLowerCase().includes(search.toLowerCase())
  );
  const filteredGuests = guests.filter(g =>
    g.name?.toLowerCase().includes(search.toLowerCase()) ||
    g.email?.toLowerCase().includes(search.toLowerCase())
  );

  const getAge = (dob) => {
    if (!dob) return '';
    const diff = Date.now() - new Date(dob).getTime();
    return Math.floor(diff / (365.25 * 24 * 3600 * 1000)) + ' yrs';
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">People</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {families.length} families · {children.length} children · {guests.length} guests
          </p>
        </div>
        <div className="relative w-64">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input className="pl-9" placeholder="Search..." value={search} onChange={e => setSearch(e.target.value)} data-testid="people-search" />
        </div>
      </div>

      <Tabs defaultValue="families">
        <TabsList>
          <TabsTrigger value="families" data-testid="tab-families">
            <Heart size={13} className="mr-1.5" /> Families ({families.length})
          </TabsTrigger>
          <TabsTrigger value="children" data-testid="tab-children">
            <Baby size={13} className="mr-1.5" /> Children ({children.length})
          </TabsTrigger>
          <TabsTrigger value="guests" data-testid="tab-guests">
            <Users size={13} className="mr-1.5" /> Guests ({guests.length})
          </TabsTrigger>
        </TabsList>

        {/* FAMILIES */}
        <TabsContent value="families" className="mt-4">
          <div className="flex justify-end mb-3">
            <Button size="sm" className="gap-2" onClick={() => setShowFamily(true)} data-testid="add-family-btn">
              <Plus size={14} /> Add Family
            </Button>
          </div>
          {loading ? (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {[1,2,3].map(i => <div key={i} className="h-40 bg-muted animate-pulse rounded-xl" />)}
            </div>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredFamilies.map(fam => {
                const kids = getChildrenForFamily(fam.id);
                return (
                  <Card key={fam.id} className="shadow-soft rounded-xl hover:shadow-soft-lg transition-shadow">
                    <CardContent className="p-5">
                      <div className="flex items-start justify-between mb-3">
                        <div>
                          <h3 className="font-semibold text-sm">{fam.family_name}</h3>
                          <p className="text-xs text-muted-foreground">{fam.primary_contact_name}</p>
                        </div>
                        <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={() => deleteFamily(fam.id)}>
                          <Trash2 size={12} />
                        </Button>
                      </div>
                      <div className="space-y-1 text-xs text-muted-foreground">
                        {fam.primary_contact_phone && <p>{fam.primary_contact_phone}</p>}
                        {fam.primary_contact_email && <p>{fam.primary_contact_email}</p>}
                        {fam.address && <p>{fam.address}</p>}
                      </div>
                      <div className="mt-3 pt-3 border-t border-border flex items-center gap-2">
                        <Baby size={12} className="text-muted-foreground" />
                        <span className="text-xs text-muted-foreground">{kids.length} {kids.length === 1 ? 'child' : 'children'}</span>
                        {kids.length > 0 && (
                          <div className="flex gap-1 flex-wrap">
                            {kids.map(k => <Badge key={k.id} variant="outline" className="text-xs py-0">{k.name.split(' ')[0]}</Badge>)}
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
              {filteredFamilies.length === 0 && (
                <div className="col-span-3 text-center py-16 text-sm text-muted-foreground">No families found.</div>
              )}
            </div>
          )}
        </TabsContent>

        {/* CHILDREN */}
        <TabsContent value="children" className="mt-4">
          <div className="flex justify-end mb-3">
            <Button size="sm" className="gap-2" onClick={() => setShowChild(true)} data-testid="add-child-btn">
              <Plus size={14} /> Add Child
            </Button>
          </div>
          <Card className="shadow-soft rounded-xl">
            <CardContent className="p-5">
              {loading ? (
                <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-12 bg-muted animate-pulse rounded" />)}</div>
              ) : children.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="text-left border-b border-border">
                      <th className="pb-2 font-medium text-muted-foreground">Name</th>
                      <th className="pb-2 font-medium text-muted-foreground">Age</th>
                      <th className="pb-2 font-medium text-muted-foreground">Class</th>
                      <th className="pb-2 font-medium text-muted-foreground">Family</th>
                      <th className="pb-2 font-medium text-muted-foreground">Medical</th>
                      <th className="pb-2"></th>
                    </tr></thead>
                    <tbody className="divide-y divide-border">
                      {children.map(c => {
                        const fam = families.find(f => f.id === c.family_id);
                        return (
                          <tr key={c.id} className="hover:bg-accent/30 transition-colors">
                            <td className="py-3 font-medium">{c.name}</td>
                            <td className="py-3 text-muted-foreground">{getAge(c.date_of_birth)}</td>
                            <td className="py-3">{c.class_group || '—'}</td>
                            <td className="py-3 text-muted-foreground">{fam?.family_name || '—'}</td>
                            <td className="py-3">
                              {c.medical_notes ? (
                                <Badge variant="destructive" className="text-xs">{c.medical_notes.slice(0, 20)}{c.medical_notes.length > 20 ? '...' : ''}</Badge>
                              ) : <span className="text-muted-foreground text-xs">—</span>}
                            </td>
                            <td className="py-3">
                              <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={() => deleteChild(c.id)}>
                                <Trash2 size={12} />
                              </Button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-10">No children records yet.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* GUESTS */}
        <TabsContent value="guests" className="mt-4">
          <div className="flex justify-end mb-3">
            <Button size="sm" className="gap-2" onClick={() => setShowGuest(true)} data-testid="add-guest-btn">
              <Plus size={14} /> Record Guest Visit
            </Button>
          </div>
          <Card className="shadow-soft rounded-xl">
            <CardContent className="p-5">
              {loading ? (
                <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-12 bg-muted animate-pulse rounded" />)}</div>
              ) : filteredGuests.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="text-left border-b border-border">
                      <th className="pb-2 font-medium text-muted-foreground">Name</th>
                      <th className="pb-2 font-medium text-muted-foreground">Contact</th>
                      <th className="pb-2 font-medium text-muted-foreground">Visit Date</th>
                      <th className="pb-2 font-medium text-muted-foreground">Referred By</th>
                      <th className="pb-2"></th>
                    </tr></thead>
                    <tbody className="divide-y divide-border">
                      {filteredGuests.map(g => (
                        <tr key={g.id} className="hover:bg-accent/30 transition-colors">
                          <td className="py-3 font-medium">{g.name}</td>
                          <td className="py-3 text-muted-foreground">{g.phone || g.email || '—'}</td>
                          <td className="py-3">{g.visit_date || '—'}</td>
                          <td className="py-3 text-muted-foreground">{g.referred_by || '—'}</td>
                          <td className="py-3">
                            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={() => deleteGuest(g.id)}>
                              <Trash2 size={12} />
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-10">No guest records yet.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Add Family Dialog */}
      <Dialog open={showFamily} onOpenChange={setShowFamily}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Add Family</DialogTitle></DialogHeader>
          <form onSubmit={handleAddFamily} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Family Name *</Label>
              <Input placeholder="e.g. Nakato Family" value={familyForm.family_name} onChange={e => setFamilyForm({...familyForm, family_name: e.target.value})} required data-testid="family-name-input" />
            </div>
            <div className="space-y-2"><Label>Primary Contact *</Label>
              <Input placeholder="Contact person name" value={familyForm.primary_contact_name} onChange={e => setFamilyForm({...familyForm, primary_contact_name: e.target.value})} required data-testid="family-contact-input" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Email</Label>
                <Input type="email" placeholder="email@example.com" value={familyForm.primary_contact_email} onChange={e => setFamilyForm({...familyForm, primary_contact_email: e.target.value})} />
              </div>
              <div className="space-y-2"><Label>Phone</Label>
                <Input placeholder="+256..." value={familyForm.primary_contact_phone} onChange={e => setFamilyForm({...familyForm, primary_contact_phone: e.target.value})} />
              </div>
            </div>
            <div className="space-y-2"><Label>Address</Label>
              <Input placeholder="Address" value={familyForm.address} onChange={e => setFamilyForm({...familyForm, address: e.target.value})} />
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowFamily(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving} data-testid="save-family-btn">{saving ? 'Saving...' : 'Add Family'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Add Child Dialog */}
      <Dialog open={showChild} onOpenChange={setShowChild}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Add Child</DialogTitle></DialogHeader>
          <form onSubmit={handleAddChild} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Name *</Label>
              <Input placeholder="Child's name" value={childForm.name} onChange={e => setChildForm({...childForm, name: e.target.value})} required data-testid="child-name-input" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Date of Birth</Label>
                <Input type="date" value={childForm.date_of_birth} onChange={e => setChildForm({...childForm, date_of_birth: e.target.value})} />
              </div>
              <div className="space-y-2"><Label>Gender</Label>
                <Select value={childForm.gender} onValueChange={v => setChildForm({...childForm, gender: v})}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="male">Male</SelectItem>
                    <SelectItem value="female">Female</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Family</Label>
                <Select value={childForm.family_id} onValueChange={v => setChildForm({...childForm, family_id: v})}>
                  <SelectTrigger><SelectValue placeholder="Select family" /></SelectTrigger>
                  <SelectContent>
                    {families.map(f => <SelectItem key={f.id} value={f.id}>{f.family_name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Class Group</Label>
                <Input placeholder="e.g. Primary 4" value={childForm.class_group} onChange={e => setChildForm({...childForm, class_group: e.target.value})} />
              </div>
            </div>
            <div className="space-y-2"><Label>Medical Notes</Label>
              <Input placeholder="Allergies, conditions, etc." value={childForm.medical_notes} onChange={e => setChildForm({...childForm, medical_notes: e.target.value})} />
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowChild(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving} data-testid="save-child-btn">{saving ? 'Saving...' : 'Add Child'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Add Guest Dialog */}
      <Dialog open={showGuest} onOpenChange={setShowGuest}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Record Guest Visit</DialogTitle></DialogHeader>
          <form onSubmit={handleAddGuest} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Name *</Label>
              <Input placeholder="Guest name" value={guestForm.name} onChange={e => setGuestForm({...guestForm, name: e.target.value})} required data-testid="guest-name-input" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Phone</Label>
                <Input placeholder="+256..." value={guestForm.phone} onChange={e => setGuestForm({...guestForm, phone: e.target.value})} />
              </div>
              <div className="space-y-2"><Label>Visit Date</Label>
                <Input type="date" value={guestForm.visit_date} onChange={e => setGuestForm({...guestForm, visit_date: e.target.value})} />
              </div>
            </div>
            <div className="space-y-2"><Label>Referred By</Label>
              <Input placeholder="Who invited them?" value={guestForm.referred_by} onChange={e => setGuestForm({...guestForm, referred_by: e.target.value})} />
            </div>
            <div className="space-y-2"><Label>Address</Label>
              <Input placeholder="Where they're from" value={guestForm.address} onChange={e => setGuestForm({...guestForm, address: e.target.value})} />
            </div>
            <div className="space-y-2"><Label>Notes</Label>
              <Input placeholder="Prayer requests, follow-up needed..." value={guestForm.notes} onChange={e => setGuestForm({...guestForm, notes: e.target.value})} />
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowGuest(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving} data-testid="save-guest-btn">{saving ? 'Saving...' : 'Record Visit'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
