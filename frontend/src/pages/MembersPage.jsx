import React, { useState } from 'react';
import { Search, Plus, Filter, UserCheck, UserX, Mail, Phone } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Card, CardContent } from '../components/ui/card';
import { Avatar, AvatarFallback } from '../components/ui/avatar';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { MOCK_MEMBERS, MOCK_GROUPS, MOCK_ROLES } from '../mock';
import { toast } from 'sonner';

export default function MembersPage() {
  const [members, setMembers] = useState(MOCK_MEMBERS);
  const [search, setSearch] = useState('');
  const [filterGroup, setFilterGroup] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [newMember, setNewMember] = useState({ name: '', email: '', phone: '', nationalId: '', role: 'Member', group: 'Youth', gender: 'male' });

  const filtered = members.filter(m => {
    const matchSearch = !search || m.name.toLowerCase().includes(search.toLowerCase()) || m.email.toLowerCase().includes(search.toLowerCase()) || m.phone.includes(search);
    const matchGroup = filterGroup === 'all' || m.group === filterGroup;
    const matchStatus = filterStatus === 'all' || m.status === filterStatus;
    return matchSearch && matchGroup && matchStatus;
  });

  const handleAddMember = (e) => {
    e.preventDefault();
    const member = {
      ...newMember,
      id: `mem_${Date.now()}`,
      status: 'active',
      joinDate: new Date().toISOString().split('T')[0],
    };
    setMembers(prev => [member, ...prev]);
    setShowAddDialog(false);
    setNewMember({ name: '', email: '', phone: '', nationalId: '', role: 'Member', group: 'Youth', gender: 'male' });
    toast.success(`Member "${member.name}" added successfully!`);
  };

  const toggleStatus = (id) => {
    setMembers(prev => prev.map(m => m.id === id ? { ...m, status: m.status === 'active' ? 'inactive' : 'active' } : m));
  };

  const initials = (name) => name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Members</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{members.length} total members · {members.filter(m => m.status === 'active').length} active</p>
        </div>
        <Button onClick={() => setShowAddDialog(true)} className="gap-2">
          <Plus size={16} /> Add Member
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search by name, email, or phone..."
            className="pl-9"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <Select value={filterGroup} onValueChange={setFilterGroup}>
          <SelectTrigger className="w-full sm:w-40">
            <Filter size={14} className="mr-1.5 text-muted-foreground" />
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
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {filtered.map(member => (
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

              <div className="space-y-1.5 text-xs text-muted-foreground">
                <div className="flex items-center gap-2">
                  <Mail size={12} />
                  <span className="truncate">{member.email}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Phone size={12} />
                  <span>{member.phone}</span>
                </div>
              </div>

              <div className="flex items-center justify-between mt-3">
                <Badge variant="secondary" className="text-xs">{member.group}</Badge>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => toggleStatus(member.id)}
                >
                  {member.status === 'active' ? <><UserX size={12} className="mr-1" />Deactivate</> : <><UserCheck size={12} className="mr-1" />Activate</>}
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          <Users size={40} className="mx-auto mb-3 opacity-30" />
          <p>No members found</p>
        </div>
      )}

      {/* Add Member Dialog */}
      <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Add New Member</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleAddMember} className="space-y-4 mt-2">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2 col-span-2">
                <Label>Full Name</Label>
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
                <Input placeholder="CM000000000XXXX" value={newMember.nationalId} onChange={e => setNewMember({...newMember, nationalId: e.target.value})} />
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
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowAddDialog(false)}>Cancel</Button>
              <Button type="submit" className="flex-1">Add Member</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
