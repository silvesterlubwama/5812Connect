import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Users, Search, RefreshCw, Shield, Key, Trash2, Edit, UserCog, Printer, X, Plus, Download } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Card, CardContent } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Checkbox } from '../components/ui/checkbox';
import { adminApi, documentsApi, locationsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import { BadgePrintView } from '../components/admin/BadgePrintView';
import { UnifiedBadge } from '../components/UnifiedBadge';
import { UserCreateDialog } from '../components/admin/UserCreateDialog';
import { UserImportDialog } from '../components/admin/UserImportDialog';
import { UserEditDialog } from '../components/admin/UserEditDialog';

const ROLES = ['Executive Director', 'Adviser', 'Director', 'Manager', 'Coordinator', 'Staff', 'HR', 'Volunteer', 'Member', 'Parent', 'Customer', 'Guest'];

export default function AdminPage() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [selectedUser, setSelectedUser] = useState(null);
  const [showEdit, setShowEdit] = useState(false);
  const [showResetPw, setShowResetPw] = useState(false);
  const [showBulk, setShowBulk] = useState(false);
  const [showBadge, setShowBadge] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [editForm, setEditForm] = useState({});
  const [newPassword, setNewPassword] = useState('');
  const [bulkAction, setBulkAction] = useState('');
  const [bulkRole, setBulkRole] = useState('');
  const [saving, setSaving] = useState(false);
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [createForm, setCreateForm] = useState({ name: '', email: '', phone: '', role: 'Staff', department: '', location_id: '', also_create_member: true, is_admin: false });
  const [createdUser, setCreatedUser] = useState(null);
  const [showImport, setShowImport] = useState(false);
  const [importJson, setImportJson] = useState('');
  const [importLoading, setImportLoading] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [memberDocs, setMemberDocs] = useState([]);
  const [docRequests, setDocRequests] = useState([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const importFileRef = useRef(null);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const [usersRes, locsRes] = await Promise.all([
        adminApi.users({ search: search || undefined, role: roleFilter !== 'all' ? roleFilter : undefined }),
        locationsApi.list().catch(() => ({ data: [] })),
      ]);
      setUsers(usersRes.data);
      setLocations(locsRes.data || []);
    } catch { toast.error('Failed to load users'); }
    finally { setLoading(false); }
  }, [search, roleFilter]);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const handleCreateUser = async () => {
    if (!createForm.name.trim() || !createForm.email.trim()) { toast.error('Name and email are required'); return; }
    try {
      const payload = { ...createForm };
      if (payload.is_admin) payload.role = 'admin';
      delete payload.is_admin;
      const res = await adminApi.createUser(payload);
      setCreatedUser(res.data);
      setUsers(prev => [res.data, ...prev]);
      toast.success(`User "${res.data.name}" created`);
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to create user'); }
  };

  const handleImportUsers = async () => {
    if (!importJson.trim()) { toast.error('Paste JSON or upload a file'); return; }
    setImportLoading(true);
    try {
      let parsed;
      try { parsed = JSON.parse(importJson); } catch { toast.error('Invalid JSON format'); setImportLoading(false); return; }
      const usersArr = Array.isArray(parsed) ? parsed : (parsed.users || [parsed]);
      const res = await adminApi.importUsers(usersArr);
      setImportResult(res.data);
      await fetchUsers();
      toast.success(`Imported ${res.data.created} users, skipped ${res.data.skipped}`);
    } catch (err) { toast.error(err.response?.data?.detail || 'Import failed'); }
    finally { setImportLoading(false); }
  };

  const handleImportFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    if (file.name.endsWith('.csv')) {
      reader.onload = (ev) => {
        const lines = ev.target.result.split('\n').filter(Boolean);
        const headers = lines[0].split(',').map(h => h.trim().toLowerCase().replace(/\s+/g, '_'));
        const rows = lines.slice(1).map(line => {
          const vals = line.split(',').map(v => v.trim().replace(/^"|"$/g, ''));
          return Object.fromEntries(headers.map((h, i) => [h, vals[i] || '']));
        });
        setImportJson(JSON.stringify(rows, null, 2));
      };
      reader.readAsText(file);
    } else { reader.onload = (ev) => setImportJson(ev.target.result); reader.readAsText(file); }
  };

  const openEdit = async (user) => {
    setSelectedUser(user);
    try {
      const res = await adminApi.getUserFullProfile(user.id);
      const p = res.data;
      setEditForm({
        name: p.name || '', email: p.email || '', phone: p.phone || '',
        role: (p.role === 'admin' || p.role === 'system_admin') ? (p.secondary_roles?.[0] || 'Staff') : (p.role || 'Member'),
        status: p.status || 'active', department: p.department || '', notes: p.notes || '',
        is_parent: p.is_parent || false, is_customer: p.is_customer || false, is_donor: p.is_donor || false,
        is_admin: p.role === 'admin' || p.role === 'system_admin', secondary_roles: p.secondary_roles || [],
        pin: p.pin || '', gender: p.gender || '', date_of_birth: p.date_of_birth || '',
        national_id: p.national_id || '', address: p.address || '', emergency_contact: p.emergency_contact || '',
        group: p.group || '', location_id: p.location_id || '',
        location_ids: p.location_ids || (p.location_id ? [p.location_id] : []),
        program: p.program || '', member_id: p.member_id || '', title: p.title || '',
      });
    } catch {
      setEditForm({ name: user.name || '', email: user.email || '', phone: user.phone || '',
        role: (user.role === 'admin' || user.role === 'system_admin') ? 'Staff' : (user.role || 'Member'),
        status: user.status || 'active', department: user.department || '', notes: user.notes || '',
        is_parent: user.is_parent || false, is_customer: user.is_customer || false, is_donor: user.is_donor || false,
        is_admin: user.role === 'admin' || user.role === 'system_admin', pin: user.pin || '',
        gender: '', date_of_birth: '', national_id: '', address: '', emergency_contact: '',
        group: '', location_id: user.location_id || '', program: '', member_id: '',
      });
    }
    setShowEdit(true);
    // Load docs
    setDocsLoading(true);
    try {
      const [docsRes, reqsRes] = await Promise.all([
        documentsApi.list(user.id).catch(() => ({ data: [] })),
        documentsApi.listRequests({ member_id: user.id }).catch(() => ({ data: [] })),
      ]);
      setMemberDocs(docsRes.data || []);
      setDocRequests(reqsRes.data || []);
    } finally { setDocsLoading(false); }
  };

  const saveEdit = async () => {
    if (!selectedUser) return;
    setSaving(true);
    try {
      const payload = { ...editForm };
      delete payload.member_id;
      if (payload.is_admin) payload.role = 'admin';
      delete payload.is_admin;
      if (!payload.location_ids?.length && payload.location_id) payload.location_ids = [payload.location_id];
      const res = await adminApi.updateUser(selectedUser.id, payload);
      setUsers(prev => prev.map(u => u.id === selectedUser.id ? { ...u, ...res.data } : u));
      toast.success('Profile updated');
      setShowEdit(false);
      fetchUsers();
    } catch (err) { toast.error(err.response?.data?.detail || 'Update failed'); }
    finally { setSaving(false); }
  };

  const resetPassword = async () => {
    if (!selectedUser || !newPassword) return;
    setSaving(true);
    try { await adminApi.resetPassword(selectedUser.id, newPassword); setShowResetPw(false); setNewPassword(''); toast.success('Password reset'); }
    catch (err) { toast.error(err.response?.data?.detail || 'Reset failed'); }
    finally { setSaving(false); }
  };

  const deleteUser = async (user) => {
    if (!window.confirm(`Delete "${user.name}"?`)) return;
    try { await adminApi.deleteUser(user.id); setUsers(prev => prev.filter(u => u.id !== user.id)); toast.success('User deleted'); }
    catch (err) { toast.error(err.response?.data?.detail || 'Delete failed'); }
  };

  const executeBulk = async () => {
    const ids = [...selectedIds];
    if (!ids.length) return;
    setSaving(true);
    try {
      if (bulkAction === 'delete') { const res = await adminApi.bulkDeleteUsers(ids); toast.success(`Deleted ${res.data.deleted} users`); }
      else if (bulkAction === 'role' && bulkRole) { const res = await adminApi.bulkUpdateUsers(ids, { role: bulkRole }); toast.success(`Updated ${res.data.updated} users`); }
      else if (bulkAction === 'activate') { const res = await adminApi.bulkUpdateUsers(ids, { status: 'active' }); toast.success(`Activated ${res.data.updated} users`); }
      else if (bulkAction === 'deactivate') { const res = await adminApi.bulkUpdateUsers(ids, { status: 'inactive' }); toast.success(`Deactivated ${res.data.updated} users`); }
      setSelectedIds(new Set()); setShowBulk(false); fetchUsers();
    } catch (err) { toast.error(err.response?.data?.detail || 'Bulk action failed'); }
    finally { setSaving(false); }
  };

  const toggleSelect = (id) => setSelectedIds(prev => { const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next; });
  const selectAll = () => setSelectedIds(selectedIds.size === users.length ? new Set() : new Set(users.map(u => u.id)));

  const roleColor = (role) => {
    const colors = { admin: 'bg-red-100 text-red-700', 'Executive Director': 'bg-purple-100 text-purple-700', Adviser: 'bg-violet-100 text-violet-700', Director: 'bg-indigo-100 text-indigo-700', Manager: 'bg-blue-100 text-blue-700', Staff: 'bg-teal-100 text-teal-700', HR: 'bg-orange-100 text-orange-700', Volunteer: 'bg-green-100 text-green-700', Member: 'bg-slate-100 text-slate-700' };
    return colors[role] || 'bg-slate-100 text-slate-600';
  };

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold font-heading flex items-center gap-2"><Shield size={24} /> Staff Administration</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{users.length} staff members</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          {selectedIds.size > 0 && <Button variant="outline" onClick={() => setShowBulk(true)} className="gap-2"><UserCog size={16} /> Bulk ({selectedIds.size})</Button>}
          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => { setShowImport(true); setImportResult(null); setImportJson(''); }}><Download size={14} /> Import</Button>
          <Button size="sm" className="gap-1.5" onClick={() => { setShowCreateUser(true); setCreatedUser(null); setCreateForm({ name: '', email: '', phone: '', role: 'Staff', department: '', location_id: '', also_create_member: true, is_admin: false }); }} data-testid="create-user-btn"><Plus size={14} /> New User</Button>
          <Button variant="outline" size="sm" onClick={fetchUsers}><RefreshCw size={14} /></Button>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input data-testid="admin-user-search" placeholder="Search users..." className="pl-9" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <Select value={roleFilter} onValueChange={setRoleFilter}>
          <SelectTrigger className="w-full sm:w-44"><SelectValue placeholder="All Roles" /></SelectTrigger>
          <SelectContent><SelectItem value="all">All Roles</SelectItem>{ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Checkbox checked={selectedIds.size > 0 && selectedIds.size === users.length} onCheckedChange={selectAll} /><span>Select all</span>
      </div>

      {loading ? (
        <div className="space-y-3">{[...Array(5)].map((_, i) => <div key={i} className="h-16 bg-card border border-border rounded-xl animate-pulse" />)}</div>
      ) : (
        <div className="space-y-2">
          {users.map(user => (
            <Card key={user.id} data-testid={`admin-user-${user.id}`} className={`rounded-xl transition-colors ${selectedIds.has(user.id) ? 'ring-2 ring-primary/40' : ''}`}>
              <CardContent className="p-4 flex items-center gap-4">
                <Checkbox checked={selectedIds.has(user.id)} onCheckedChange={() => toggleSelect(user.id)} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-medium text-sm">{user.name}</p>
                    <Badge className={`text-xs ${roleColor(user.role)}`}>{user.role === 'admin' || user.role === 'system_admin' ? 'Admin' : user.role}</Badge>
                    {(user.role === 'admin' || user.role === 'system_admin') && <Badge className="text-xs bg-red-500 text-white"><Shield size={10} className="mr-0.5" /> System Admin</Badge>}
                    {user.status === 'inactive' && <Badge variant="secondary" className="text-xs">Inactive</Badge>}
                    {user.has_member_profile && <Badge variant="outline" className="text-xs border-indigo-300 text-indigo-600 bg-indigo-50">People</Badge>}
                  </div>
                  <p className="text-xs text-muted-foreground truncate">{user.email} {user.phone ? `· ${user.phone}` : ''} {user.location_id ? `· ${locations.find(l => l.id === user.location_id)?.name || ''}` : ''}</p>
                </div>
                <div className="flex gap-1.5">
                  <Button data-testid={`edit-user-${user.id}`} size="sm" variant="ghost" onClick={() => openEdit(user)} title="Edit"><Edit size={14} /></Button>
                  <Button size="sm" variant="ghost" onClick={() => { setSelectedUser(user); setShowBadge(true); }} title="Badge"><Printer size={14} /></Button>
                  <Button size="sm" variant="ghost" onClick={() => { setSelectedUser(user); setShowResetPw(true); }} title="Password"><Key size={14} /></Button>
                  <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => deleteUser(user)} title="Delete"><Trash2 size={14} /></Button>
                </div>
              </CardContent>
            </Card>
          ))}
          {users.length === 0 && <div className="text-center py-12 text-muted-foreground"><Users size={40} className="mx-auto mb-3 opacity-30" /><p>No users found</p></div>}
        </div>
      )}

      {/* Extracted Dialog Components */}
      <UserCreateDialog open={showCreateUser} onOpenChange={o => { setShowCreateUser(o); if (!o) setCreatedUser(null); }} form={createForm} setForm={setCreateForm} locations={locations} createdUser={createdUser} onCreateUser={handleCreateUser} />
      <UserImportDialog open={showImport} onOpenChange={o => { setShowImport(o); if (!o) { setImportResult(null); setImportJson(''); } }} importJson={importJson} setImportJson={setImportJson} importLoading={importLoading} importResult={importResult} onImport={handleImportUsers} onImportFile={handleImportFile} />
      <UserEditDialog open={showEdit} onOpenChange={setShowEdit} selectedUser={selectedUser} editForm={editForm} setEditForm={setEditForm} locations={locations} saving={saving} onSave={saveEdit} memberDocs={memberDocs} setMemberDocs={setMemberDocs} docRequests={docRequests} setDocRequests={setDocRequests} docsLoading={docsLoading} currentUserRole={currentUser?.role} />

      {/* Reset Password Dialog */}
      <Dialog open={showResetPw} onOpenChange={setShowResetPw}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Reset Password</DialogTitle><DialogDescription>Set a new password for {selectedUser?.name}</DialogDescription></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2"><Label>New Password</Label><Input type="password" placeholder="Min 6 characters" value={newPassword} onChange={e => setNewPassword(e.target.value)} /></div>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => { setShowResetPw(false); setNewPassword(''); }}>Cancel</Button>
              <Button className="flex-1" onClick={resetPassword} disabled={saving || newPassword.length < 6}>{saving ? 'Resetting...' : 'Reset Password'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Bulk Action Dialog */}
      <Dialog open={showBulk} onOpenChange={setShowBulk}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Bulk Action ({selectedIds.size} users)</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Action</Label>
              <Select value={bulkAction} onValueChange={setBulkAction}><SelectTrigger><SelectValue placeholder="Select action" /></SelectTrigger>
                <SelectContent><SelectItem value="role">Change Role</SelectItem><SelectItem value="activate">Activate</SelectItem><SelectItem value="deactivate">Deactivate</SelectItem><SelectItem value="delete">Delete</SelectItem></SelectContent>
              </Select>
            </div>
            {bulkAction === 'role' && (
              <div className="space-y-2"><Label>New Role</Label>
                <Select value={bulkRole} onValueChange={setBulkRole}><SelectTrigger><SelectValue placeholder="Select role" /></SelectTrigger>
                  <SelectContent>{ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            )}
            {bulkAction === 'delete' && <p className="text-sm text-destructive font-medium">This will permanently delete {selectedIds.size} users!</p>}
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => setShowBulk(false)}>Cancel</Button>
              <Button className="flex-1" variant={bulkAction === 'delete' ? 'destructive' : 'default'} onClick={executeBulk} disabled={saving || !bulkAction}>{saving ? 'Processing...' : 'Execute'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Badge Print Dialog */}
      <Dialog open={showBadge} onOpenChange={setShowBadge}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Print Badge - {selectedUser?.name}</DialogTitle></DialogHeader>
          {selectedUser && <UnifiedBadge person={{ ...selectedUser, country: locations.find(l => l.id === selectedUser.location_id)?.country }} canWriteNfc={['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director'].includes(currentUser?.role)} />}
        </DialogContent>
      </Dialog>
    </div>
  );
}
