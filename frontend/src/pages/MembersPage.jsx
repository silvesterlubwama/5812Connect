import React, { useState, useEffect, useCallback } from 'react';
import { Search, Plus, Filter, UserCheck, UserX, Mail, Phone, ChevronDown, Eye, Trash2, RefreshCw, Download } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Avatar, AvatarFallback } from '../components/ui/avatar';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { membersApi, checkinsApi } from '../services/api';
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
  const [newMember, setNewMember] = useState({ name: '', email: '', phone: '', national_id: '', role: 'Member', group: 'Youth', gender: 'male', date_of_birth: '', address: '', notes: '' });
  const [savingMember, setSavingMember] = useState(false);

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
          <p className="text-sm text-muted-foreground mt-0.5">{total} total · {members.filter(m => m.status === 'active').length} active</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchMembers} className="gap-1.5"><RefreshCw size={14} /></Button>
          <Button onClick={() => setShowAddDialog(true)} className="gap-2">
            <Plus size={16} /> Add Member
          </Button>
        </div>
      </div>

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
                  <Badge variant="secondary" className="text-xs">{member.group}</Badge>
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
    </div>
  );
}
