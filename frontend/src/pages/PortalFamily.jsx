import React, { useState, useEffect, useCallback } from 'react';
import { Heart, Baby, UserPlus, Plus, Edit, Trash2, Shield, Phone, Mail, RefreshCw } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Textarea } from '../components/ui/textarea';
import { portalApi, childrenApi } from '../services/api';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

const RELATIONSHIPS = ['Spouse', 'Guardian', 'Grandparent', 'Aunt/Uncle', 'Sibling', 'Nanny', 'Emergency contact', 'Other'];

export default function PortalFamily() {
  const { user } = useAuth();
  const [familyData, setFamilyData] = useState(null);
  const [loading, setLoading] = useState(true);

  // Add child dialog
  const [showAddChild, setShowAddChild] = useState(false);
  const [childForm, setChildForm] = useState({ name: '', date_of_birth: '', gender: '', class_group: '', medical_notes: '', allergies: '' });
  const [savingChild, setSavingChild] = useState(false);

  // Add guardian dialog
  const [showAddGuardian, setShowAddGuardian] = useState(false);
  const [guardianForm, setGuardianForm] = useState({ name: '', phone: '', email: '', relationship: 'Guardian' });
  const [savingGuardian, setSavingGuardian] = useState(false);

  // Edit child dialog
  const [editChild, setEditChild] = useState(null);
  const [editChildForm, setEditChildForm] = useState({});
  const [savingEditChild, setSavingEditChild] = useState(false);

  // Edit family
  const [editingFamily, setEditingFamily] = useState(false);
  const [familyEditForm, setFamilyEditForm] = useState({});

  // Household member edit
  const [editGuardian, setEditGuardian] = useState(null);
  const [editGuardianForm, setEditGuardianForm] = useState({});

  // Self-service household creation
  const [creating, setCreating] = useState(false);

  const fetchFamily = useCallback(async () => {
    setLoading(true);
    try {
      const res = await portalApi.family();
      setFamilyData(res.data);
    } catch { toast.error('Failed to load family'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchFamily(); }, [fetchFamily]);

  const handleAddChild = async (e) => {
    e.preventDefault();
    setSavingChild(true);
    try {
      await portalApi.addChild(childForm);
      toast.success('Child added!');
      setShowAddChild(false);
      setChildForm({ name: '', date_of_birth: '', gender: '', class_group: '', medical_notes: '', allergies: '' });
      fetchFamily();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to add child'); }
    finally { setSavingChild(false); }
  };

  const handleAddGuardian = async (e) => {
    e.preventDefault();
    setSavingGuardian(true);
    try {
      await portalApi.addGuardian(guardianForm);
      toast.success('Guardian added!');
      setShowAddGuardian(false);
      setGuardianForm({ name: '', phone: '', email: '', relationship: 'Guardian' });
      fetchFamily();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to add guardian'); }
    finally { setSavingGuardian(false); }
  };

  const handleEditChild = async () => {
    if (!editChild) return;
    setSavingEditChild(true);
    try {
      await childrenApi.update(editChild.id, editChildForm);
      toast.success('Child updated');
      setEditChild(null);
      fetchFamily();
    } catch (err) { toast.error(err.response?.data?.detail || 'Update failed'); }
    finally { setSavingEditChild(false); }
  };

  const handleRemoveGuardian = async (guardianId) => {
    try {
      await portalApi.removeGuardian(guardianId);
      toast.success('Removed from your household');
      fetchFamily();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to remove'); }
  };

  const handleSaveGuardian = async () => {
    if (!editGuardian) return;
    try {
      await portalApi.updateGuardian(editGuardian.id, editGuardianForm);
      toast.success('Household member updated');
      setEditGuardian(null);
      fetchFamily();
    } catch (err) { toast.error(err.response?.data?.detail || 'Update failed'); }
  };

  const handleCreateFamily = async () => {
    setCreating(true);
    try {
      await portalApi.createFamily({});
      toast.success('Household created — add your spouse, children and guardians');
      fetchFamily();
    } catch (err) { toast.error(err.response?.data?.detail || 'Could not create your household'); }
    finally { setCreating(false); }
  };

  const handleUpdateFamily = async () => {
    try {
      await portalApi.updateFamily(familyEditForm);
      toast.success('Family updated');
      setEditingFamily(false);
      fetchFamily();
    } catch (err) { toast.error(err.response?.data?.detail || 'Update failed'); }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        <div className="h-40 bg-muted animate-pulse rounded-xl" />
      </div>
    );
  }

  const family = familyData?.family;
  const children = familyData?.children || [];
  const parents = familyData?.parents || [];
  const guardians = family?.guardians || [];
  // iter343 guest-portal lockdown — unapproved users must not add/remove
  // family members. The screen still renders in read-only mode so they
  // can view what's on file while an admin approves them.
  const isPending = (user?.status || '').toLowerCase() === 'pending';
  const isApproved = !isPending;

  if (!family) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold font-heading" data-testid="portal-family-title">My Family</h1>
        <Card className="shadow-soft rounded-xl">
          <CardContent className="py-14 text-center">
            <Heart size={44} className="mx-auto mb-4 opacity-20" />
            <p className="text-muted-foreground font-medium">No household on file yet</p>
            <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">
              {familyData?.can_create
                ? 'Create your household and you can add your spouse, children, guardians and emergency contacts yourself.'
                : 'Your account is pending approval — household setup unlocks once an admin approves you.'}
            </p>
            {familyData?.can_create && (
              <Button className="mt-5 gap-2" onClick={handleCreateFamily} disabled={creating} data-testid="create-family-btn">
                <Plus size={15} /> {creating ? 'Creating…' : 'Create my household'}
              </Button>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading" data-testid="portal-family-title">My Family</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{family.family_name}</p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchFamily} data-testid="refresh-family"><RefreshCw size={14} /></Button>
      </div>
      {isPending && (
        <Card className="border-amber-200 bg-amber-50/40" data-testid="family-pending-banner">
          <CardContent className="p-3 text-sm text-amber-800">
            Your account is pending approval — you can view your family details but can&apos;t edit them yet.
          </CardContent>
        </Card>
      )}
      {isApproved && (
        <Card className="border-blue-200 bg-blue-50/40" data-testid="family-review-notice">
          <CardContent className="p-3 text-xs text-blue-800">
            Note: adding a child or guardian creates a pending record — an admin reviews it before badges or check-ins are enabled.
          </CardContent>
        </Card>
      )}

      {/* Family Info Card */}
      <Card className="shadow-soft rounded-xl" data-testid="family-info-card">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2"><Heart size={16} className="text-rose-500" /> Family Details</CardTitle>
            <Button size="sm" variant="ghost" onClick={() => { setEditingFamily(true); setFamilyEditForm({ family_name: family.family_name, address: family.address || '', notes: family.notes || '', primary_contact_phone: family.primary_contact_phone || '' }); }} data-testid="edit-family-btn" disabled={!isApproved} title={!isApproved ? 'Available after your account is approved' : ''}><Edit size={13} /></Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div><span className="text-xs text-muted-foreground">Family Name</span><p className="font-medium">{family.family_name}</p></div>
            <div><span className="text-xs text-muted-foreground">Primary Contact</span><p>{family.primary_contact_name}</p></div>
            <div><span className="text-xs text-muted-foreground">Phone</span><p>{family.primary_contact_phone || '—'}</p></div>
            <div><span className="text-xs text-muted-foreground">Address</span><p>{family.address || '—'}</p></div>
          </div>
        </CardContent>
      </Card>

      {/* Parents Section */}
      <Card className="shadow-soft rounded-xl" data-testid="parents-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><UserPlus size={16} className="text-blue-500" /> Parents ({parents.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {parents.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">No parents linked</p>
          ) : (
            <div className="space-y-2">
              {parents.map(p => (
                <div key={p.id} className="flex items-center justify-between p-3 rounded-lg bg-accent/30" data-testid={`parent-${p.id}`}>
                  <div>
                    <p className="text-sm font-medium">{p.name}</p>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                      {p.phone && <span className="flex items-center gap-1"><Phone size={10} />{p.phone}</span>}
                      {p.email && <span className="flex items-center gap-1"><Mail size={10} />{p.email}</span>}
                    </div>
                  </div>
                  <Badge variant="secondary" className="text-[10px]">Parent</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Children Section */}
      <Card className="shadow-soft rounded-xl" data-testid="children-card">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2"><Baby size={16} className="text-emerald-500" /> Children ({children.length})</CardTitle>
            {isApproved && <Button size="sm" className="gap-1.5" onClick={() => setShowAddChild(true)} data-testid="add-child-btn"><Plus size={13} /> Add Child</Button>}
          </div>
        </CardHeader>
        <CardContent>
          {children.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">No children registered</p>
          ) : (
            <div className="space-y-2">
              {children.map(c => (
                <div key={c.id} className="flex items-center justify-between p-3 rounded-lg bg-accent/30" data-testid={`child-${c.id}`}>
                  <div>
                    <p className="text-sm font-medium">{c.name}</p>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                      <span>DOB: {c.date_of_birth || 'N/A'}</span>
                      {c.class_group && <span>Class: {c.class_group}</span>}
                      {c.gender && <Badge variant="outline" className="text-[10px] capitalize">{c.gender}</Badge>}
                    </div>
                    {c.allergies && <Badge variant="destructive" className="text-[10px] mt-1">{c.allergies}</Badge>}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button size="sm" variant="outline" className="h-7 gap-1 text-[11px]" onClick={async () => {
                      try {
                        const r = await api.post(`/portal/children/${c.id}/wallet-badge`);
                        if (r.data?.token) window.open(`/badge/${r.data.token}`, '_blank');
                      } catch (e) { toast.error(e?.response?.data?.detail || 'Badge issuance failed'); }
                    }} data-testid={`child-badge-${c.id}`}>Badge</Button>
                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => { setEditChild(c); setEditChildForm({ name: c.name, date_of_birth: c.date_of_birth || '', gender: c.gender || '', class_group: c.class_group || '', medical_notes: c.medical_notes || '', allergies: c.allergies || '' }); }} data-testid={`edit-child-${c.id}`} disabled={!isApproved} title={!isApproved ? 'Available after your account is approved' : ''}><Edit size={13} /></Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Household members (spouse / guardians / emergency contacts) */}
      <Card className="shadow-soft rounded-xl" data-testid="guardians-card">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2"><Shield size={16} className="text-amber-500" /> Spouse &amp; Guardians ({guardians.length})</CardTitle>
            {isApproved && <Button size="sm" className="gap-1.5" onClick={() => setShowAddGuardian(true)} data-testid="add-guardian-btn"><Plus size={13} /> Add Person</Button>}
          </div>
        </CardHeader>
        <CardContent>
          {guardians.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">Nobody added yet. Add your spouse, a grandparent, or anyone allowed to collect your children.</p>
          ) : (
            <div className="space-y-2">
              {guardians.map(g => (
                <div key={g.id} className="flex items-center justify-between p-3 rounded-lg bg-accent/30" data-testid={`guardian-${g.id}`}>
                  <div>
                    <p className="text-sm font-medium">{g.name}</p>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                      {g.phone && <span className="flex items-center gap-1"><Phone size={10} />{g.phone}</span>}
                      {g.email && <span className="flex items-center gap-1"><Mail size={10} />{g.email}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {g.approval_status === 'pending' && <Badge variant="outline" className="text-[10px] border-amber-300 text-amber-700">Pending review</Badge>}
                    <Badge variant="outline" className="text-[10px]">{g.relationship}</Badge>
                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0" disabled={!isApproved}
                      onClick={() => { setEditGuardian(g); setEditGuardianForm({ name: g.name || '', phone: g.phone || '', email: g.email || '', relationship: g.relationship || 'Guardian' }); }}
                      data-testid={`edit-guardian-${g.id}`}><Edit size={13} /></Button>
                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" onClick={() => handleRemoveGuardian(g.id)} data-testid={`remove-guardian-${g.id}`} disabled={!isApproved} title={!isApproved ? 'Available after your account is approved' : ''}><Trash2 size={13} /></Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Add Child Dialog */}
      <Dialog open={showAddChild} onOpenChange={setShowAddChild}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Add Child</DialogTitle><DialogDescription>Add a child to your family</DialogDescription></DialogHeader>
          <form onSubmit={handleAddChild} className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label>Name *</Label><Input value={childForm.name} onChange={e => setChildForm({ ...childForm, name: e.target.value })} required data-testid="child-name-input" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Date of Birth</Label><Input type="date" value={childForm.date_of_birth} onChange={e => setChildForm({ ...childForm, date_of_birth: e.target.value })} /></div>
              <div className="space-y-1.5"><Label>Gender</Label>
                <Select value={childForm.gender} onValueChange={v => setChildForm({ ...childForm, gender: v })}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent><SelectItem value="male">Male</SelectItem><SelectItem value="female">Female</SelectItem></SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5"><Label>Class / Group</Label><Input value={childForm.class_group} onChange={e => setChildForm({ ...childForm, class_group: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Medical Notes</Label><Textarea rows={2} value={childForm.medical_notes} onChange={e => setChildForm({ ...childForm, medical_notes: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Allergies</Label><Input value={childForm.allergies} onChange={e => setChildForm({ ...childForm, allergies: e.target.value })} /></div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowAddChild(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={savingChild || !childForm.name} data-testid="save-child-btn">{savingChild ? 'Saving...' : 'Add Child'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Add household member Dialog */}
      <Dialog open={showAddGuardian} onOpenChange={setShowAddGuardian}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Add to my household</DialogTitle><DialogDescription>Your spouse, a guardian, or anyone authorised to collect your children</DialogDescription></DialogHeader>
          <form onSubmit={handleAddGuardian} className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label>Name *</Label><Input value={guardianForm.name} onChange={e => setGuardianForm({ ...guardianForm, name: e.target.value })} required data-testid="guardian-name-input" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Phone</Label><Input value={guardianForm.phone} onChange={e => setGuardianForm({ ...guardianForm, phone: e.target.value })} /></div>
              <div className="space-y-1.5"><Label>Email</Label><Input type="email" value={guardianForm.email} onChange={e => setGuardianForm({ ...guardianForm, email: e.target.value })} /></div>
            </div>
            <div className="space-y-1.5"><Label>Relationship</Label>
              <Select value={guardianForm.relationship} onValueChange={v => setGuardianForm({ ...guardianForm, relationship: v })}>
                <SelectTrigger data-testid="guardian-relationship-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {RELATIONSHIPS.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowAddGuardian(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={savingGuardian || !guardianForm.name} data-testid="save-guardian-btn">{savingGuardian ? 'Saving...' : 'Add'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit household member Dialog */}
      <Dialog open={!!editGuardian} onOpenChange={(o) => { if (!o) setEditGuardian(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Edit {editGuardian?.name}</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label>Name *</Label><Input value={editGuardianForm.name || ''} onChange={e => setEditGuardianForm({ ...editGuardianForm, name: e.target.value })} data-testid="edit-guardian-name" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Phone</Label><Input value={editGuardianForm.phone || ''} onChange={e => setEditGuardianForm({ ...editGuardianForm, phone: e.target.value })} /></div>
              <div className="space-y-1.5"><Label>Email</Label><Input type="email" value={editGuardianForm.email || ''} onChange={e => setEditGuardianForm({ ...editGuardianForm, email: e.target.value })} /></div>
            </div>
            <div className="space-y-1.5"><Label>Relationship</Label>
              <Select value={editGuardianForm.relationship || 'Guardian'} onValueChange={v => setEditGuardianForm({ ...editGuardianForm, relationship: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{RELATIONSHIPS.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setEditGuardian(null)}>Cancel</Button>
              <Button className="flex-1" onClick={handleSaveGuardian} data-testid="save-guardian-edit-btn">Save</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Child Dialog */}
      <Dialog open={!!editChild} onOpenChange={(o) => { if (!o) setEditChild(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Edit Child: {editChild?.name}</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label>Name *</Label><Input value={editChildForm.name || ''} onChange={e => setEditChildForm({ ...editChildForm, name: e.target.value })} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Date of Birth</Label><Input type="date" value={editChildForm.date_of_birth || ''} onChange={e => setEditChildForm({ ...editChildForm, date_of_birth: e.target.value })} /></div>
              <div className="space-y-1.5"><Label>Gender</Label>
                <Select value={editChildForm.gender || ''} onValueChange={v => setEditChildForm({ ...editChildForm, gender: v })}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent><SelectItem value="male">Male</SelectItem><SelectItem value="female">Female</SelectItem></SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5"><Label>Class / Group</Label><Input value={editChildForm.class_group || ''} onChange={e => setEditChildForm({ ...editChildForm, class_group: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Medical Notes</Label><Textarea rows={2} value={editChildForm.medical_notes || ''} onChange={e => setEditChildForm({ ...editChildForm, medical_notes: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Allergies</Label><Input value={editChildForm.allergies || ''} onChange={e => setEditChildForm({ ...editChildForm, allergies: e.target.value })} /></div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setEditChild(null)}>Cancel</Button>
              <Button className="flex-1" onClick={handleEditChild} disabled={savingEditChild}>{savingEditChild ? 'Saving...' : 'Save'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Family Dialog */}
      <Dialog open={editingFamily} onOpenChange={setEditingFamily}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Edit Family Details</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label>Family Name</Label><Input value={familyEditForm.family_name || ''} onChange={e => setFamilyEditForm({ ...familyEditForm, family_name: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Phone</Label><Input value={familyEditForm.primary_contact_phone || ''} onChange={e => setFamilyEditForm({ ...familyEditForm, primary_contact_phone: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Address</Label><Input value={familyEditForm.address || ''} onChange={e => setFamilyEditForm({ ...familyEditForm, address: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Notes</Label><Textarea rows={2} value={familyEditForm.notes || ''} onChange={e => setFamilyEditForm({ ...familyEditForm, notes: e.target.value })} /></div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setEditingFamily(false)}>Cancel</Button>
              <Button className="flex-1" onClick={handleUpdateFamily} data-testid="save-family-edit-btn">Save</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
