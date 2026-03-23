import React, { useState, useEffect, useCallback } from 'react';
import { Search, Plus, Filter, UserCheck, UserX, Mail, Phone, ChevronDown, Eye, Trash2, RefreshCw, Download, Upload, Award, Users, FileUp } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Avatar, AvatarFallback } from '../components/ui/avatar';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Switch } from '../components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { membersApi, checkinsApi, approvalsApi, badgesApi, exportApi, importApi, locationsApi } from '../services/api';
import { MOCK_GROUPS, MOCK_ROLES } from '../mock';
import { toast } from 'sonner';

const initials = (name) => (name || '?').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();

export default function MembersPage() {
  const [members, setMembers] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterGroup, setFilterGroup] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [selectedMember, setSelectedMember] = useState(null);
  const [memberDetail, setMemberDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [newMember, setNewMember] = useState({ name: '', email: '', phone: '', national_id: '', role: 'Staff', group: 'Youth', gender: 'male', date_of_birth: '', address: '', notes: '', location_id: '', department: '', is_parent: false, is_customer: false, is_donor: false });
  const [savingMember, setSavingMember] = useState(false);
  const [pendingMembers, setPendingMembers] = useState([]);
  const [badges, setBadges] = useState([]);
  const [showBulkImport, setShowBulkImport] = useState(false);
  const [bulkData, setBulkData] = useState('');
  const [importLoading, setImportLoading] = useState(false);
  const [showBadgeDialog, setShowBadgeDialog] = useState(false);
  const [newBadge, setNewBadge] = useState({ name: '', description: '', color: '#6366f1' });
  const [activeTab, setActiveTab] = useState('all');
  const [showChildImport, setShowChildImport] = useState(false);
  const [childCsvData, setChildCsvData] = useState('');
  const [showStaffImport, setShowStaffImport] = useState(false);
  const [staffCsvData, setStaffCsvData] = useState('');
  const [allLocations, setAllLocations] = useState([]);

  const fetchMembers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await membersApi.list({
        search: search || undefined,
        group: filterGroup !== 'all' ? filterGroup : undefined,
        status: filterStatus !== 'all' ? filterStatus : undefined,
      });
      setMembers(res.data.members);
      setTotal(res.data.total);
    } catch {
      toast.error('Failed to load members');
    } finally {
      setLoading(false);
    }
  }, [search, filterGroup, filterStatus]);

  useEffect(() => {
    const timer = setTimeout(fetchMembers, 300);
    return () => clearTimeout(timer);
  }, [fetchMembers]);

  useEffect(() => {
    approvalsApi.pending().then(r => setPendingMembers(r.data)).catch(() => {});
    badgesApi.list().then(r => setBadges(r.data)).catch(() => {});
    locationsApi.list().then(r => setAllLocations(r.data)).catch(() => {});
  }, []);

  const handleApprove = async (id) => {
    try {
      await approvalsApi.approve(id);
      setPendingMembers(prev => prev.filter(m => m.id !== id));
      toast.success('Member approved');
      fetchMembers();
    } catch { toast.error('Failed to approve'); }
  };

  const handleReject = async (id) => {
    try {
      await approvalsApi.reject(id);
      setPendingMembers(prev => prev.filter(m => m.id !== id));
      toast.success('Member rejected');
    } catch { toast.error('Failed to reject'); }
  };

  const handleBulkImport = async () => {
    if (!bulkData.trim()) return;
    setImportLoading(true);
    try {
      const lines = bulkData.trim().split('\n').map(l => {
        const [name, email, phone, group] = l.split(',').map(s => s.trim());
        return { name, email, phone, group: group || 'Youth', role: 'Member' };
      }).filter(m => m.name);
      const res = await approvalsApi.bulkImport(lines);
      toast.success(`Imported ${res.data.imported || lines.length} members!`);
      setShowBulkImport(false);
      setBulkData('');
      fetchMembers();
    } catch { toast.error('Import failed'); }
    finally { setImportLoading(false); }
  };

  const handleCreateBadge = async () => {
    try {
      const res = await badgesApi.create(newBadge);
      setBadges(prev => [...prev, res.data]);
      setShowBadgeDialog(false);
      setNewBadge({ name: '', description: '', color: '#6366f1' });
      toast.success('Badge created!');
    } catch { toast.error('Failed to create badge'); }
  };

  const handleDeleteBadge = async (id) => {
    if (!window.confirm('Delete this badge?')) return;
    await badgesApi.delete(id);
    setBadges(prev => prev.filter(b => b.id !== id));
    toast.success('Badge deleted');
  };

  const downloadCSV = () => {
    const token = localStorage.getItem('5812_token');
    const url = exportApi.members();
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.blob())
      .then(blob => {
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = 'members.csv';
        link.click();
      }).catch(() => toast.error('Export failed'));
  };

  const handleChildParentImport = async () => {
    if (!childCsvData.trim()) return;
    setImportLoading(true);
    try {
      const lines = childCsvData.trim().split('\n');
      const header = lines[0].toLowerCase().split(',').map(h => h.trim());
      const rows = lines.slice(1).map(line => {
        const vals = line.split(',').map(v => v.trim());
        const row = {};
        header.forEach((h, i) => { row[h] = vals[i] || ''; });
        return row;
      }).filter(r => r.first_name);
      const res = await importApi.childrenParents(rows);
      toast.success(`Imported: ${res.data.imported_children} children, ${res.data.imported_parents} parents, ${res.data.imported_families} families`);
      if (res.data.errors?.length > 0) toast.warning(`${res.data.errors.length} rows had errors`);
      setShowChildImport(false);
      setChildCsvData('');
      fetchMembers();
    } catch { toast.error('Import failed'); }
    finally { setImportLoading(false); }
  };

  const handleStaffImport = async () => {
    if (!staffCsvData.trim()) return;
    setImportLoading(true);
    try {
      const lines = staffCsvData.trim().split('\n');
      const header = lines[0].toLowerCase().split(',').map(h => h.trim());
      const rows = lines.slice(1).map(line => {
        const vals = line.split(',').map(v => v.trim());
        const row = {};
        header.forEach((h, i) => { row[h] = vals[i] || ''; });
        return row;
      }).filter(r => r.name);
      const res = await importApi.staff(rows);
      toast.success(`Imported ${res.data.imported} staff members!`);
      if (res.data.errors?.length > 0) toast.warning(`${res.data.errors.length} rows had errors`);
      setShowStaffImport(false);
      setStaffCsvData('');
      fetchMembers();
    } catch { toast.error('Import failed'); }
    finally { setImportLoading(false); }
  };

  const handleAddMember = async (e) => {
    e.preventDefault();
    setSavingMember(true);
    try {
      const res = await membersApi.create(newMember);
      setMembers(prev => [res.data, ...prev]);
      setShowAddDialog(false);
      setNewMember({ name: '', email: '', phone: '', national_id: '', role: 'Member', group: 'Youth', gender: 'male', date_of_birth: '', address: '', notes: '' });
      toast.success(`Member "${res.data.name}" added!`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to add member');
    } finally {
      setSavingMember(false);
    }
  };

  const toggleStatus = async (member) => {
    const newStatus = member.status === 'active' ? 'inactive' : 'active';
    try {
      await membersApi.update(member.id, { status: newStatus });
      setMembers(prev => prev.map(m => m.id === member.id ? { ...m, status: newStatus } : m));
      toast.success(`Member ${newStatus === 'active' ? 'activated' : 'deactivated'}`);
    } catch {
      toast.error('Failed to update status');
    }
  };

  const deleteMember = async (member) => {
    if (!window.confirm(`Delete ${member.name}? This cannot be undone.`)) return;
    try {
      await membersApi.delete(member.id);
      setMembers(prev => prev.filter(m => m.id !== member.id));
      toast.success('Member deleted');
    } catch {
      toast.error('Failed to delete member');
    }
  };

  const viewMember = async (member) => {
    setSelectedMember(member);
    setLoadingDetail(true);
    try {
      const res = await membersApi.get(member.id);
      setMemberDetail(res.data);
    } catch {
      setMemberDetail(member);
    } finally {
      setLoadingDetail(false);
    }
  };

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Members</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{total} total · {members.filter(m => m.status === 'active').length} active{pendingMembers.length > 0 ? ` · ${pendingMembers.length} pending` : ''}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchMembers} className="gap-1.5"><RefreshCw size={14} /></Button>
          <Button variant="outline" size="sm" onClick={downloadCSV} className="gap-1.5" data-testid="export-members-btn"><Download size={14} /> CSV</Button>
          <Select onValueChange={v => { if (v === 'bulk') setShowBulkImport(true); else if (v === 'children') setShowChildImport(true); else if (v === 'staff') setShowStaffImport(true); }}>
            <SelectTrigger className="w-auto h-8 gap-1.5 text-xs"><FileUp size={14} /><span>Import</span></SelectTrigger>
            <SelectContent>
              <SelectItem value="bulk">Quick Import (CSV)</SelectItem>
              <SelectItem value="children">Children & Parents CSV</SelectItem>
              <SelectItem value="staff">Staff CSV</SelectItem>
            </SelectContent>
          </Select>
          <Button onClick={() => setShowAddDialog(true)} className="gap-2" data-testid="add-member-btn">
            <Plus size={16} /> Add Member
          </Button>
        </div>
      </div>

      {/* Page Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="all" data-testid="tab-all-members">All Members</TabsTrigger>
          <TabsTrigger value="approvals" data-testid="tab-approvals">Approvals {pendingMembers.length > 0 && <Badge variant="destructive" className="ml-1.5 h-5 text-xs px-1.5">{pendingMembers.length}</Badge>}</TabsTrigger>
          <TabsTrigger value="badges" data-testid="tab-badges">Badges ({badges.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="all" className="mt-4 space-y-4">

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input placeholder="Search name, email, phone, ID..." className="pl-9" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <Select value={filterGroup} onValueChange={setFilterGroup}>
          <SelectTrigger className="w-full sm:w-40">
            <Filter size={14} className="mr-1.5 text-muted-foreground shrink-0" />
            <SelectValue placeholder="Group" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Groups</SelectItem>
            {MOCK_GROUPS.map(g => <SelectItem key={g} value={g}>{g}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={filterStatus} onValueChange={setFilterStatus}>
          <SelectTrigger className="w-full sm:w-36">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="inactive">Inactive</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Members grid */}
      {loading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="h-44 bg-card border border-border rounded-xl animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {members.map(member => (
            <Card key={member.id} className="shadow-soft rounded-xl hover:shadow-soft-lg transition-shadow">
              <CardContent className="p-4">
                <div className="flex items-start gap-3 mb-3">
                  <Avatar className="h-10 w-10">
                    <AvatarFallback className={`text-sm font-semibold ${member.status === 'active' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}>
                      {initials(member.name)}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold truncate">{member.name}</p>
                    <p className="text-xs text-muted-foreground">{member.role}</p>
                  </div>
                  <Badge variant={member.status === 'active' ? 'outline' : 'secondary'} className={`text-xs shrink-0 ${member.status === 'active' ? 'border-green-500 text-green-600' : ''}`}>
                    {member.status}
                  </Badge>
                </div>
                <div className="space-y-1.5 text-xs text-muted-foreground mb-3">
                  {member.email && <div className="flex items-center gap-2"><Mail size={12} /><span className="truncate">{member.email}</span></div>}
                  {member.phone && <div className="flex items-center gap-2"><Phone size={12} /><span>{member.phone}</span></div>}
                  {member.join_date && <div className="flex items-center gap-2"><span className="text-muted-foreground/70">Joined:</span><span>{member.join_date}</span></div>}
                </div>
                <div className="flex items-center justify-between mt-2">
                  <div className="flex items-center gap-1 flex-wrap">
                    <Badge variant="secondary" className="text-xs">{member.group}</Badge>
                    {member.is_parent && <Badge variant="outline" className="text-xs border-purple-300 text-purple-600">Parent</Badge>}
                    {member.is_customer && <Badge variant="outline" className="text-xs border-green-300 text-green-600">Customer</Badge>}
                    {member.is_donor && <Badge variant="outline" className="text-xs border-amber-300 text-amber-600">Donor</Badge>}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => viewMember(member)}>
                      <Eye size={13} />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => toggleStatus(member)}>
                      {member.status === 'active' ? <UserX size={13} className="text-muted-foreground" /> : <UserCheck size={13} className="text-green-600" />}
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive hover:text-destructive" onClick={() => deleteMember(member)}>
                      <Trash2 size={13} />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {!loading && members.length === 0 && (
        <div className="text-center py-16 text-muted-foreground">
          <Users size={40} className="mx-auto mb-3 opacity-30" />
          <p>No members found</p>
          <Button variant="outline" className="mt-4" onClick={() => setShowAddDialog(true)}>Add your first member</Button>
        </div>
      )}
        </TabsContent>

        {/* Approvals Tab */}
        <TabsContent value="approvals" className="mt-4">
          {pendingMembers.length === 0 ? (
            <div className="text-center py-16 text-sm text-muted-foreground">
              <UserCheck size={40} className="mx-auto mb-3 opacity-30" />
              No pending approval requests.
            </div>
          ) : (
            <div className="space-y-3">
              {pendingMembers.map(m => (
                <Card key={m.id} className="shadow-soft rounded-xl" data-testid="pending-member-card">
                  <CardContent className="p-4 flex items-center gap-4">
                    <Avatar className="h-10 w-10">
                      <AvatarFallback className="bg-amber-100 text-amber-700 text-sm font-semibold">{initials(m.name)}</AvatarFallback>
                    </Avatar>
                    <div className="flex-1">
                      <p className="text-sm font-semibold">{m.name}</p>
                      <p className="text-xs text-muted-foreground">{m.email || m.phone || 'No contact info'}</p>
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" className="text-green-600 border-green-300 hover:bg-green-50" onClick={() => handleApprove(m.id)} data-testid="approve-btn">
                        <UserCheck size={14} className="mr-1" /> Approve
                      </Button>
                      <Button size="sm" variant="outline" className="text-red-600 border-red-300 hover:bg-red-50" onClick={() => handleReject(m.id)} data-testid="reject-btn">
                        <UserX size={14} className="mr-1" /> Reject
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* Badges Tab */}
        <TabsContent value="badges" className="mt-4">
          <div className="flex justify-end mb-4">
            <Button size="sm" className="gap-2" onClick={() => setShowBadgeDialog(true)} data-testid="create-badge-btn">
              <Plus size={14} /> Create Badge
            </Button>
          </div>
          {badges.length === 0 ? (
            <div className="text-center py-16 text-sm text-muted-foreground">
              <Award size={40} className="mx-auto mb-3 opacity-30" />
              No badges created yet.
            </div>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {badges.map(b => (
                <Card key={b.id} className="shadow-soft rounded-xl" data-testid="badge-card">
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between mb-2">
                      <div className="h-10 w-10 rounded-full flex items-center justify-center" style={{ backgroundColor: b.color + '20', color: b.color }}>
                        <Award size={20} />
                      </div>
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={() => handleDeleteBadge(b.id)}>
                        <Trash2 size={12} />
                      </Button>
                    </div>
                    <p className="font-semibold text-sm">{b.name}</p>
                    {b.description && <p className="text-xs text-muted-foreground mt-1">{b.description}</p>}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Add Member Dialog */}
      <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Add New Member</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleAddMember} className="space-y-4 mt-2">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2 col-span-2">
                <Label>Full Name *</Label>
                <Input placeholder="Full name" value={newMember.name} onChange={e => setNewMember({...newMember, name: e.target.value})} required />
              </div>
              <div className="space-y-2">
                <Label>Email</Label>
                <Input type="email" placeholder="email@example.com" value={newMember.email} onChange={e => setNewMember({...newMember, email: e.target.value})} />
              </div>
              <div className="space-y-2">
                <Label>Phone</Label>
                <Input placeholder="+256 700 000000" value={newMember.phone} onChange={e => setNewMember({...newMember, phone: e.target.value})} />
              </div>
              <div className="space-y-2 col-span-2">
                <Label>National ID</Label>
                <Input placeholder="CM000000000XXXX" value={newMember.national_id} onChange={e => setNewMember({...newMember, national_id: e.target.value})} />
              </div>
              <div className="space-y-2">
                <Label>Role</Label>
                <Select value={newMember.role} onValueChange={v => setNewMember({...newMember, role: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{MOCK_ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Group</Label>
                <Select value={newMember.group} onValueChange={v => setNewMember({...newMember, group: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{MOCK_GROUPS.map(g => <SelectItem key={g} value={g}>{g}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Gender</Label>
                <Select value={newMember.gender} onValueChange={v => setNewMember({...newMember, gender: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="male">Male</SelectItem>
                    <SelectItem value="female">Female</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Date of Birth</Label>
                <Input type="date" value={newMember.date_of_birth} onChange={e => setNewMember({...newMember, date_of_birth: e.target.value})} />
              </div>
              <div className="space-y-2 col-span-2">
                <Label>Address</Label>
                <Input placeholder="Physical address" value={newMember.address} onChange={e => setNewMember({...newMember, address: e.target.value})} />
              </div>
              <div className="space-y-2">
                <Label>Location</Label>
                <Select value={newMember.location_id || '_none'} onValueChange={v => setNewMember({...newMember, location_id: v === '_none' ? '' : v})}>
                  <SelectTrigger><SelectValue placeholder="Select location" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_none">Not assigned</SelectItem>
                    {allLocations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Department</Label>
                <Input placeholder="e.g. Education" value={newMember.department || ''} onChange={e => setNewMember({...newMember, department: e.target.value})} />
              </div>
              <div className="col-span-2 space-y-3 p-3 border border-border rounded-lg">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Additional Roles</p>
                <div className="flex items-center justify-between">
                  <p className="text-sm">Also a Parent</p>
                  <Switch checked={newMember.is_parent} onCheckedChange={v => setNewMember({...newMember, is_parent: v})} />
                </div>
                <div className="flex items-center justify-between">
                  <p className="text-sm">Also a Customer</p>
                  <Switch checked={newMember.is_customer} onCheckedChange={v => setNewMember({...newMember, is_customer: v})} />
                </div>
                <div className="flex items-center justify-between">
                  <p className="text-sm">Also a Donor</p>
                  <Switch checked={newMember.is_donor} onCheckedChange={v => setNewMember({...newMember, is_donor: v})} />
                </div>
              </div>
              <div className="space-y-2 col-span-2">
                <Label>Notes</Label>
                <Input placeholder="Any notes..." value={newMember.notes} onChange={e => setNewMember({...newMember, notes: e.target.value})} />
              </div>
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowAddDialog(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={savingMember}>
                {savingMember ? 'Adding...' : 'Add Member'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Member Detail Dialog */}
      <Dialog open={!!selectedMember} onOpenChange={() => { setSelectedMember(null); setMemberDetail(null); }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Member Profile</DialogTitle>
          </DialogHeader>
          {loadingDetail ? (
            <div className="space-y-3 mt-4">
              {[1,2,3].map(i => <div key={i} className="h-12 bg-muted animate-pulse rounded" />)}
            </div>
          ) : memberDetail && (
            <div className="mt-2">
              <Tabs defaultValue="info">
                <TabsList>
                  <TabsTrigger value="info">Profile Info</TabsTrigger>
                  <TabsTrigger value="checkins">Check-In History ({memberDetail.checkin_history?.length ?? 0})</TabsTrigger>
                </TabsList>

                <TabsContent value="info" className="mt-4">
                  <div className="flex items-start gap-4 mb-5">
                    <Avatar className="h-16 w-16">
                      <AvatarFallback className="bg-primary text-primary-foreground text-xl font-semibold">
                        {initials(memberDetail.name)}
                      </AvatarFallback>
                    </Avatar>
                    <div>
                      <h3 className="text-xl font-semibold">{memberDetail.name}</h3>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge variant="outline" className="text-xs">{memberDetail.role}</Badge>
                        <Badge variant="secondary" className="text-xs">{memberDetail.group}</Badge>
                        <Badge variant={memberDetail.status === 'active' ? 'outline' : 'secondary'} className={`text-xs ${memberDetail.status === 'active' ? 'border-green-500 text-green-600' : ''}`}>
                          {memberDetail.status}
                        </Badge>
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4 text-sm">
                    {[
                      { label: 'Email', value: memberDetail.email },
                      { label: 'Phone', value: memberDetail.phone },
                      { label: 'National ID', value: memberDetail.national_id },
                      { label: 'Gender', value: memberDetail.gender },
                      { label: 'Date of Birth', value: memberDetail.date_of_birth },
                      { label: 'Join Date', value: memberDetail.join_date },
                      { label: 'Address', value: memberDetail.address, full: true },
                      { label: 'Notes', value: memberDetail.notes, full: true },
                    ].filter(f => f.value).map((field, i) => (
                      <div key={i} className={field.full ? 'col-span-2' : ''}>
                        <p className="text-xs text-muted-foreground mb-0.5">{field.label}</p>
                        <p className="font-medium">{field.value}</p>
                      </div>
                    ))}
                  </div>

                  <div className="flex gap-3 mt-5 pt-4 border-t border-border">
                    <Button
                      variant="outline"
                      className="flex-1"
                      onClick={() => { toggleStatus(memberDetail); setSelectedMember(null); }}
                    >
                      {memberDetail.status === 'active' ? 'Deactivate' : 'Activate'}
                    </Button>
                    <Button
                      variant="destructive"
                      onClick={() => { deleteMember(memberDetail); setSelectedMember(null); }}
                    >
                      Delete Member
                    </Button>
                  </div>
                </TabsContent>

                <TabsContent value="checkins" className="mt-4">
                  {(memberDetail.checkin_history ?? []).length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-8">No check-in history</p>
                  ) : (
                    <div className="space-y-2">
                      {memberDetail.checkin_history.map(ci => (
                        <div key={ci.id} className="flex items-center justify-between p-3 rounded-lg border border-border text-sm">
                          <div>
                            <p className="font-medium">{ci.event_name || 'General Check-in'}</p>
                            <p className="text-xs text-muted-foreground">{new Date(ci.check_in_time).toLocaleString()}</p>
                          </div>
                          <Badge variant="outline" className="text-xs capitalize">{ci.method}</Badge>
                        </div>
                      ))}
                    </div>
                  )}
                </TabsContent>
              </Tabs>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Bulk Import Dialog */}
      <Dialog open={showBulkImport} onOpenChange={setShowBulkImport}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Bulk Import Members</DialogTitle>
            <DialogDescription>Paste CSV data: name, email, phone, group (one per line)</DialogDescription>
          </DialogHeader>
          <Textarea
            rows={8}
            placeholder={`John Doe, john@email.com, +256700111222, Youth\nJane Smith, jane@email.com, +256700333444, Women`}
            value={bulkData}
            onChange={e => setBulkData(e.target.value)}
            data-testid="bulk-import-textarea"
          />
          <div className="flex gap-3 pt-2">
            <Button type="button" variant="outline" className="flex-1" onClick={() => setShowBulkImport(false)}>Cancel</Button>
            <Button className="flex-1" disabled={importLoading || !bulkData.trim()} onClick={handleBulkImport} data-testid="import-btn">
              {importLoading ? 'Importing...' : 'Import Members'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Create Badge Dialog */}
      <Dialog open={showBadgeDialog} onOpenChange={setShowBadgeDialog}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Create Badge</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Badge Name *</Label>
              <Input placeholder="e.g. Faithful Volunteer" value={newBadge.name} onChange={e => setNewBadge({...newBadge, name: e.target.value})} data-testid="badge-name-input" />
            </div>
            <div className="space-y-2"><Label>Description</Label>
              <Input placeholder="What this badge represents" value={newBadge.description} onChange={e => setNewBadge({...newBadge, description: e.target.value})} />
            </div>
            <div className="space-y-2"><Label>Color</Label>
              <Input type="color" value={newBadge.color} onChange={e => setNewBadge({...newBadge, color: e.target.value})} className="h-10 w-20 p-1" />
            </div>
            <div className="flex gap-3">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowBadgeDialog(false)}>Cancel</Button>
              <Button className="flex-1" disabled={!newBadge.name} onClick={handleCreateBadge} data-testid="save-badge-btn">Create Badge</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Children + Parents CSV Import */}
      <Dialog open={showChildImport} onOpenChange={setShowChildImport}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Import Children & Parents</DialogTitle>
            <DialogDescription>Paste CSV with header: first_name, last_name, date_of_birth, grade, family_name, fathers_names, fathers_phone, mothers_names, mothers_phone, allergies, medical_notes, special_needs</DialogDescription>
          </DialogHeader>
          <Textarea rows={8} placeholder={`first_name,last_name,date_of_birth,grade,family_name,fathers_names,fathers_phone,mothers_names,mothers_phone,allergies,medical_notes,special_needs\nJohn,Doe,2015-05-10,3,Doe Family,James Doe,+256700111222,Mary Doe,+256700333444,None,None,None`}
            value={childCsvData} onChange={e => setChildCsvData(e.target.value)} data-testid="child-import-textarea" />
          <div className="flex gap-3 pt-2">
            <Button variant="outline" className="flex-1" onClick={() => setShowChildImport(false)}>Cancel</Button>
            <Button className="flex-1" disabled={importLoading || !childCsvData.trim()} onClick={handleChildParentImport} data-testid="import-children-btn">
              {importLoading ? 'Importing...' : 'Import Children & Parents'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Staff CSV Import */}
      <Dialog open={showStaffImport} onOpenChange={setShowStaffImport}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Import Staff</DialogTitle>
            <DialogDescription>Paste CSV with header: name, email, phone, national_id, role, department</DialogDescription>
          </DialogHeader>
          <Textarea rows={8} placeholder={`name,email,phone,national_id,role,department\nJane Smith,jane@example.com,+256700111222,CM12345,Staff,Education\nBob Johnson,bob@example.com,+256700333444,CM67890,Coordinator,Operations`}
            value={staffCsvData} onChange={e => setStaffCsvData(e.target.value)} data-testid="staff-import-textarea" />
          <div className="flex gap-3 pt-2">
            <Button variant="outline" className="flex-1" onClick={() => setShowStaffImport(false)}>Cancel</Button>
            <Button className="flex-1" disabled={importLoading || !staffCsvData.trim()} onClick={handleStaffImport} data-testid="import-staff-btn">
              {importLoading ? 'Importing...' : 'Import Staff'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
