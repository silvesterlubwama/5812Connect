import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Users, Search, RefreshCw, Shield, Key, Trash2, Edit, UserCog, Printer, X, Plus, Download, Clock } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Card, CardContent } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Checkbox } from '../components/ui/checkbox';
import api, { adminApi, documentsApi, locationsApi, securityCheckpointApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import { BadgePrintView } from '../components/admin/BadgePrintView';
import { UnifiedBadge } from '../components/UnifiedBadge';
import { dataEvents, emitDataChanged } from '../services/dataEvents';
import { UserCreateDialog } from '../components/admin/UserCreateDialog';
import { UserImportDialog } from '../components/admin/UserImportDialog';
import { UserEditDialog } from '../components/admin/UserEditDialog';
import KioskLinksManager from '../components/KioskLinksManager';
import BackupRestoreManager from '../components/BackupRestoreManager';
import IntegrationsManager from '../components/IntegrationsManager';

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

  // Refresh when data changes in other pages
  useEffect(() => {
    const unsub = dataEvents.on('data-changed', (e) => {
      if (['users', 'members', 'guests'].includes(e?.collection)) fetchUsers();
    });
    return unsub;
  }, [fetchUsers]);

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
    try {
      const res = await adminApi.resetPassword(selectedUser.id, newPassword);
      const emailSent = res.data?.email_sent;
      const msg = emailSent
        ? `Password reset and email sent to ${selectedUser.email}`
        : `Password reset to: ${newPassword} (email not sent — share manually)`;
      toast.success(msg, { duration: 8000 });
      setShowResetPw(false); setNewPassword('');
    }
    catch (err) { toast.error(err.response?.data?.detail || 'Reset failed'); }
    finally { setSaving(false); }
  };

  const deleteUser = async (user) => {
    if (!window.confirm(`Delete "${user.name}"?`)) return;
    try { await adminApi.deleteUser(user.id); setUsers(prev => prev.filter(u => u.id !== user.id)); emitDataChanged('users', user.id); toast.success('User deleted'); }
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

      {/* Access Expiring Soon banner — visible to admins+ if any explicit grant expires within 7 days */}
      <ExpiringGrantsBanner />

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
          {selectedUser && <UnifiedBadge person={{ ...selectedUser, country: locations.find(l => l.id === selectedUser.location_id)?.country, country_code: locations.find(l => l.id === selectedUser.location_id)?.country_code }} canWriteNfc={['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director'].includes(currentUser?.role)} />}
        </DialogContent>
      </Dialog>

      {/* Module Access Management — admin only — finance, HR, sales, banking, accounting, social work, restricted */}
      {['admin', 'system_admin', 'Executive Director'].includes(currentUser?.role) && (
        <>
          <ModuleAccessManager />
          <SecurityCheckpointsManager />
          <KioskLinksManager />
          <BackupRestoreManager />
          <IntegrationsManager />
        </>
      )}
    </div>
  );
}

// ============== MODULE ACCESS MANAGER ==============
// Generic access-grant UI for any module gated by the appointment-only pattern:
// Director+ have implicit access; everyone else needs an explicit, optionally
// time-limited grant. Modules: finance, hr, sales, banking, accounting, social_work, restricted.
function ModuleAccessManager() {
  const [open, setOpen] = useState(false);
  const [modules, setModules] = useState([]);
  const [activeModule, setActiveModule] = useState('finance');
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [grantingUser, setGrantingUser] = useState(null);
  const [ttlDays, setTtlDays] = useState('');

  // Load module catalogue once
  useEffect(() => {
    if (!open) return;
    api.get('/admin/module-access/modules').then(r => setModules(r.data || []))
      .catch(() => setModules([
        { key: 'finance', label: 'Finance' },
        { key: 'hr', label: 'HR & Payroll' },
        { key: 'sales', label: 'Sales / Marketplace' },
        { key: 'banking', label: 'Banking' },
        { key: 'accounting', label: 'Accounting' },
        { key: 'social_work', label: 'Social Work' },
        { key: 'restricted', label: 'Restricted Access' },
      ]));
  }, [open]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get('/admin/module-access/users', { params: { module: activeModule } });
      setUsers(r.data || []);
    } catch (e) { toast.error('Failed to load users'); }
    finally { setLoading(false); }
  }, [activeModule]);
  useEffect(() => { if (open) load(); }, [open, load]);

  const grant = async (u, days) => {
    try {
      const body = { module: activeModule, granted: true };
      if (days && parseInt(days) > 0) body.ttl_days = parseInt(days);
      await api.put(`/admin/module-access/users/${u.id}`, body);
      toast.success(`Granted ${activeModule} access ${days ? `for ${days} days` : 'permanently'} to ${u.name}`);
      setGrantingUser(null); setTtlDays('');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };
  const revoke = async (u) => {
    try {
      await api.put(`/admin/module-access/users/${u.id}`, { module: activeModule, granted: false });
      toast.success(`Revoked ${activeModule} access for ${u.name}`);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const filtered = users.filter(u => !search || (u.name || '').toLowerCase().includes(search.toLowerCase()) || (u.email || '').toLowerCase().includes(search.toLowerCase()));
  const activeModuleLabel = modules.find(m => m.key === activeModule)?.label || activeModule;

  return (
    <>
      <Card className="rounded-xl mt-4 cursor-pointer hover:border-primary/40" onClick={() => setOpen(true)} data-testid="module-access-manager-card">
        <CardContent className="p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Shield size={18} className="text-primary" />
            <div>
              <p className="font-medium text-sm">Module Access</p>
              <p className="text-xs text-muted-foreground">Grant or revoke per-module access (Finance, HR, Sales, Banking, Accounting, Social Work, Restricted) with optional expiry. Director+ have implicit access; everyone else is by appointment only.</p>
            </div>
          </div>
          <Button size="sm" variant="outline">Manage</Button>
        </CardContent>
      </Card>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Module Access Management</DialogTitle>
            <DialogDescription className="text-xs">
              Director and above (Executive Director, Adviser, Director, Admin, System Admin) always have access automatically.
              Managers and below need an explicit grant per module — permanent or time-limited.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            {/* Module picker chips */}
            <div className="flex flex-wrap gap-1.5" data-testid="module-picker">
              {modules.map(m => (
                <Button
                  key={m.key}
                  size="sm"
                  variant={activeModule === m.key ? 'default' : 'outline'}
                  className="h-7 text-xs"
                  onClick={() => setActiveModule(m.key)}
                  data-testid={`module-chip-${m.key}`}
                >
                  {m.label.split('(')[0].trim()}
                </Button>
              ))}
            </div>
            <p className="text-[10px] text-muted-foreground">
              Managing: <strong>{activeModuleLabel}</strong>
            </p>

            <Input placeholder="Search by name or email..." value={search} onChange={e => setSearch(e.target.value)} className="h-9" data-testid="module-access-search" />
            {loading ? <div className="space-y-2">{[1,2,3].map(i => <div key={i} className="h-12 bg-muted animate-pulse rounded" />)}</div> : (
              <div className="space-y-1.5">
                {filtered.map(u => {
                  const implicit = u.access_implicit;
                  const granted = u.access_effective;
                  const expires = u[`${activeModule}_access_expires_at`];
                  const expired = u.access_expired;
                  return (
                    <div key={u.id} className="flex items-center justify-between p-2 rounded border" data-testid={`module-access-row-${u.id}`}>
                      <div>
                        <p className="text-sm font-medium">{u.name} <span className="text-xs text-muted-foreground">({u.role})</span></p>
                        <p className="text-[10px] text-muted-foreground">{u.email} · {u.department || '—'}</p>
                        {expires && !implicit && (
                          <p className="text-[10px] text-amber-700">Expires {String(expires).slice(0, 10)}</p>
                        )}
                        {expired && (
                          <p className="text-[10px] text-red-700">⚠ Grant expired</p>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        {implicit ? (
                          <Badge className="bg-emerald-100 text-emerald-700 text-[10px]">Implicit (role)</Badge>
                        ) : granted ? (
                          <>
                            <Badge className="bg-blue-100 text-blue-700 text-[10px]">Explicit grant</Badge>
                            <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive" onClick={() => revoke(u)} data-testid={`module-revoke-${u.id}`}>Revoke</Button>
                          </>
                        ) : (
                          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => { setGrantingUser(u); setTtlDays(''); }} data-testid={`module-grant-${u.id}`}>Grant</Button>
                        )}
                      </div>
                    </div>
                  );
                })}
                {!filtered.length && <p className="text-xs text-muted-foreground text-center py-6">No users match</p>}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* GRANT (with optional TTL) */}
      <Dialog open={!!grantingUser} onOpenChange={(o) => { if (!o) { setGrantingUser(null); setTtlDays(''); } }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Grant {activeModule} access</DialogTitle>
            <DialogDescription className="text-xs">Granting <strong>{activeModuleLabel}</strong> to <strong>{grantingUser?.name}</strong> ({grantingUser?.role})</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Duration</Label>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { d: '', label: 'Permanent' },
                  { d: '30', label: '30 days' },
                  { d: '90', label: '90 days' },
                ].map(opt => (
                  <Button key={opt.label} type="button" size="sm" variant={ttlDays === opt.d ? 'default' : 'outline'} className="h-8 text-xs" onClick={() => setTtlDays(opt.d)}>{opt.label}</Button>
                ))}
              </div>
              <Input type="number" placeholder="Custom days (1-365)" value={ttlDays && !['','30','90'].includes(ttlDays) ? ttlDays : ''} onChange={e => setTtlDays(e.target.value)} className="h-8 mt-1" data-testid="module-grant-ttl" />
              <p className="text-[10px] text-muted-foreground">Leave blank for permanent. Temp grants auto-revoke at end-of-day on the expiry date.</p>
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => { setGrantingUser(null); setTtlDays(''); }}>Cancel</Button>
              <Button className="flex-1" onClick={() => grant(grantingUser, ttlDays)} data-testid="module-grant-confirm">Grant</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

// Legacy alias kept for the (very few) other consumers — opens the same dialog default-tabbed to Finance.
// eslint-disable-next-line no-unused-vars
function FinanceAccessManager() {
  return <ModuleAccessManager />;
}


// ============== EXPIRING GRANTS BANNER ==============
// Lightweight banner above the admin page that lists module grants expiring in the
// next 7 days. One-click re-issue (30d default) or jump to the full Module Access dialog.
function ExpiringGrantsBanner() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [reissuing, setReissuing] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get('/admin/module-access/expiring-soon', { params: { days: 7 } });
      setRows(r.data?.rows || []);
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const reissue = async (row, days = 30) => {
    const key = `${row.user_id}:${row.module}`;
    setReissuing(prev => ({ ...prev, [key]: true }));
    try {
      await api.put(`/admin/module-access/users/${row.user_id}`, {
        module: row.module, granted: true, ttl_days: days,
      });
      toast.success(`Re-issued ${row.module} access for ${row.name} (${days}d)`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed');
    } finally {
      setReissuing(prev => ({ ...prev, [key]: false }));
    }
  };

  if (loading || rows.length === 0) return null;
  return (
    <div className="rounded-xl border border-amber-200 dark:border-amber-900/40 bg-amber-50/60 dark:bg-amber-950/20 p-3" data-testid="expiring-grants-banner">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Clock size={15} className="text-amber-600" />
          <p className="text-sm font-medium text-amber-900 dark:text-amber-200">
            {rows.length} module {rows.length === 1 ? 'grant' : 'grants'} expiring in the next 7 days
          </p>
        </div>
      </div>
      <div className="space-y-1.5 max-h-48 overflow-y-auto">
        {rows.map(r => {
          const key = `${r.user_id}:${r.module}`;
          const daysLeft = Math.max(0, Math.ceil((new Date(r.expires_at).getTime() - Date.now()) / 86400000));
          return (
            <div key={key} className="flex items-center justify-between text-xs bg-background/60 rounded p-1.5 border border-amber-100 dark:border-amber-900/30" data-testid={`expiring-row-${key}`}>
              <div className="min-w-0 flex-1">
                <span className="font-medium">{r.name}</span>
                <span className="text-muted-foreground"> · {r.role || '—'}</span>
                <span className="ml-1 px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200 text-[10px] capitalize">
                  {r.module.replace('_', ' ')}
                </span>
                <span className="ml-2 text-[10px] text-amber-700 dark:text-amber-400">
                  {daysLeft === 0 ? 'expires today' : `${daysLeft}d left`} · {String(r.expires_at).slice(0, 10)}
                </span>
              </div>
              <Button
                size="sm"
                variant="outline"
                className="h-6 px-2 text-[10px]"
                onClick={() => reissue(r, 30)}
                disabled={!!reissuing[key]}
                data-testid={`reissue-${key}`}
              >
                {reissuing[key] ? '…' : 'Renew 30d'}
              </Button>
            </div>
          );
        })}
      </div>
    </div>
  );
}


// ============== SECURITY CHECKPOINTS MANAGER ==============
function SecurityCheckpointsManager() {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState([]);
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: '', location_id: '', description: '', requires_id_for_one_time: true, kind: 'strict', device_mode: 'dual_device' });
  const [logbookFor, setLogbookFor] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, locs] = await Promise.all([securityCheckpointApi.list(), locationsApi.list()]);
      setRows(r.data || []);
      setLocations(locs.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed to load checkpoints'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (open) load(); }, [open, load]);

  const create = async (e) => {
    e?.preventDefault?.();
    if (!form.name.trim() || !form.location_id) { toast.error('Name and location are required'); return; }
    setCreating(true);
    try {
      await securityCheckpointApi.create(form);
      toast.success(`Checkpoint created. PIN visible in the list.`);
      setForm({ name: '', location_id: '', description: '', requires_id_for_one_time: true, kind: 'strict', device_mode: 'dual_device' });
      load();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
    finally { setCreating(false); }
  };

  const rotate = async (cp) => {
    if (!window.confirm(`Rotate PIN for "${cp.name}"? Paired devices will need to re-pair.`)) return;
    try {
      const r = await securityCheckpointApi.rotatePin(cp.id);
      toast.success(`New PIN: ${r.data.pairing_pin}`);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const remove = async (cp) => {
    if (!window.confirm(`Delete checkpoint "${cp.name}"? All paired devices will be revoked.`)) return;
    try {
      await securityCheckpointApi.remove(cp.id);
      toast.success('Deleted');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  return (
    <>
      <Card className="rounded-xl mt-4 cursor-pointer hover:border-primary/40" onClick={() => setOpen(true)} data-testid="security-checkpoints-card">
        <CardContent className="p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Shield size={18} className="text-emerald-600" />
            <div>
              <p className="font-medium text-sm">Security Checkpoints</p>
              <p className="text-xs text-muted-foreground">Create gate-access kiosks for restricted locations. Each checkpoint has a 6-digit pairing PIN for the guest + security devices.</p>
            </div>
          </div>
          <Button size="sm" variant="outline">Manage</Button>
        </CardContent>
      </Card>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Shield size={16} className="text-emerald-600" /> Security Checkpoints</DialogTitle>
            <DialogDescription className="text-xs">
              Each checkpoint pairs a guest-facing display with a security-contractor console using the same 6-digit PIN.
              Open <code className="px-1 rounded bg-muted">/security-checkpoint</code> on each device to pair.
            </DialogDescription>
          </DialogHeader>

          {/* Create form */}
          <form onSubmit={create} className="space-y-3 p-3 rounded border bg-muted/30 mt-3" data-testid="cp-create-form">
            <p className="text-xs font-semibold">Create new checkpoint</p>
            <div className="grid sm:grid-cols-2 gap-2">
              <div className="space-y-1"><Label className="text-xs">Name *</Label><Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Shelter Main Gate" required data-testid="cp-create-name" /></div>
              <div className="space-y-1">
                <Label className="text-xs">Location (restricted) *</Label>
                <select className="h-9 w-full rounded border bg-background px-2 text-sm" value={form.location_id} onChange={e => setForm({ ...form, location_id: e.target.value })} required data-testid="cp-create-location">
                  <option value="">Select location…</option>
                  {locations.map(l => <option key={l.id} value={l.id}>{l.name}{l.is_restricted ? ' (restricted)' : ''}</option>)}
                </select>
              </div>
              <div className="space-y-1 sm:col-span-2"><Label className="text-xs">Description</Label><Input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} /></div>
              <div className="space-y-1">
                <Label className="text-xs">Checkpoint mode</Label>
                <select className="h-9 w-full rounded border bg-background px-2 text-sm" value={form.kind} onChange={e => setForm({ ...form, kind: e.target.value })} data-testid="cp-create-kind">
                  <option value="strict">Strict — restricted location access only</option>
                  <option value="hybrid">Hybrid — also accepts event tickets + checks attendees in</option>
                  <option value="check_in_only">Check-in only — no access gate, just log presence</option>
                </select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Device layout</Label>
                <select className="h-9 w-full rounded border bg-background px-2 text-sm" value={form.device_mode} onChange={e => setForm({ ...form, device_mode: e.target.value })} data-testid="cp-create-device-mode">
                  <option value="dual_device">Dual device — guest tablet + security console</option>
                  <option value="single_device">Single device — operator scans on behalf of visitor</option>
                </select>
              </div>
              <label className="flex items-center gap-2 text-xs sm:col-span-2">
                <input type="checkbox" checked={form.requires_id_for_one_time} onChange={e => setForm({ ...form, requires_id_for_one_time: e.target.checked })} />
                <span>Require ID photo when granting one-time entries</span>
              </label>
            </div>
            <Button type="submit" size="sm" disabled={creating} data-testid="cp-create-submit">{creating ? 'Creating…' : 'Create checkpoint + PIN'}</Button>
          </form>

          {/* List */}
          <div className="space-y-2 mt-3">
            {loading ? <div className="space-y-2">{[1, 2].map(i => <div key={i} className="h-16 bg-muted animate-pulse rounded" />)}</div> : rows.length === 0 ? (
              <p className="text-xs text-muted-foreground text-center py-6">No checkpoints yet — create one above.</p>
            ) : rows.map(cp => (
              <div key={cp.id} className="p-3 rounded border bg-card" data-testid={`cp-row-${cp.id}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold flex items-center gap-1 flex-wrap">{cp.name} <Badge variant="outline" className="text-[10px]">{cp.location_name}</Badge></div>
                    {cp.description && <p className="text-[11px] text-muted-foreground">{cp.description}</p>}
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <Badge variant="outline" className="text-[9px] capitalize">{(cp.kind || 'strict').replace('_', ' ')}</Badge>
                      <Badge variant="outline" className="text-[9px]">{cp.device_mode === 'single_device' ? 'Single device' : 'Dual device'}</Badge>
                      <span className="text-[10px] uppercase text-muted-foreground">Pairing PIN</span>
                      <code className="px-2 py-0.5 rounded bg-emerald-50 dark:bg-emerald-950/30 text-emerald-800 dark:text-emerald-300 text-sm font-mono tracking-widest">{cp.pairing_pin}</code>
                      <span className="text-[10px] text-muted-foreground">· {cp.paired_devices ?? 0} paired device{cp.paired_devices === 1 ? '' : 's'}</span>
                    </div>
                  </div>
                  <div className="flex flex-col gap-1.5 shrink-0">
                    <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={() => setLogbookFor(cp)} data-testid={`cp-logbook-${cp.id}`}>📋 Logbook</Button>
                    <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={() => rotate(cp)} data-testid={`cp-rotate-${cp.id}`}><Key size={11} className="mr-1" /> Rotate PIN</Button>
                    <Button size="sm" variant="ghost" className="h-7 text-[11px] text-destructive" onClick={() => remove(cp)} data-testid={`cp-delete-${cp.id}`}><Trash2 size={11} className="mr-1" /> Delete</Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      {/* ADMIN LOGBOOK DIALOG */}
      <AdminLogbookDialog cp={logbookFor} onClose={() => setLogbookFor(null)} />
    </>
  );
}

// ============== ADMIN LOGBOOK DIALOG ==============
function AdminLogbookDialog({ cp, onClose }) {
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [includeResidents, setIncludeResidents] = useState(false);
  const [rows, setRows] = useState([]);
  const [counts, setCounts] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!cp) return;
    setLoading(true);
    securityCheckpointApi.visitorLogAdmin(cp.id, date, includeResidents)
      .then(r => { setRows(r.data?.rows || []); setCounts(r.data?.counts || null); })
      .catch(e => toast.error(e.response?.data?.detail || 'Failed to load logbook'))
      .finally(() => setLoading(false));
  }, [cp, date, includeResidents]);

  return (
    <Dialog open={!!cp} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto" data-testid="admin-logbook-dialog">
        <DialogHeader>
          <DialogTitle>{cp?.name} — Visitor Logbook</DialogTitle>
          <DialogDescription className="text-xs">
            Entry / exit times per person, by day. Residents are filtered out by default — they live at this location so they aren't tracked as daily guests.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 mt-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Label className="text-xs">Date</Label>
            <Input type="date" value={date} onChange={e => setDate(e.target.value)} className="h-8 w-44" data-testid="admin-logbook-date" />
            <label className="flex items-center gap-1.5 text-[11px] cursor-pointer ml-2">
              <input type="checkbox" checked={includeResidents} onChange={e => setIncludeResidents(e.target.checked)} data-testid="admin-logbook-residents-toggle" />
              <span>Include residents</span>
            </label>
            {counts && (
              <div className="ml-auto flex gap-1.5">
                <Badge variant="outline" className="text-[10px]">{counts.visitors_entered} visitors</Badge>
                <Badge variant="outline" className="text-[10px] bg-blue-50 text-blue-700 border-blue-200">{counts.residents_entered} residents</Badge>
                <Badge className="bg-emerald-100 text-emerald-700 text-[10px]">{counts.visitors_inside + counts.residents_inside} inside now</Badge>
              </div>
            )}
          </div>
          {loading ? <div className="space-y-2">{[1, 2, 3].map(i => <div key={i} className="h-10 bg-muted animate-pulse rounded" />)}</div>
            : rows.length === 0 ? <p className="text-xs text-muted-foreground text-center py-6">No {includeResidents ? 'entries' : 'visitors'} logged for this date.</p>
              : (
                <table className="w-full text-xs">
                  <thead className="text-[10px] uppercase text-muted-foreground border-b">
                    <tr><th className="text-left py-2">Person</th><th className="text-left">Type</th><th className="text-left">In</th><th className="text-left">Out</th><th className="text-left">Status</th></tr>
                  </thead>
                  <tbody>
                    {rows.map(r => (
                      <tr key={r.entry_event_id} className="border-b last:border-b-0" data-testid={`logbook-row-${r.entry_event_id}`}>
                        <td className="py-1.5">
                          <div className="font-medium flex items-center gap-1">{r.name}
                            {r.subject_type === 'resident' && <Badge variant="outline" className="text-[9px] bg-blue-50 text-blue-700 border-blue-200">RESIDENT</Badge>}
                          </div>
                          {(r.role || r.phone) && <div className="text-[10px] text-muted-foreground">{[r.role, r.phone].filter(Boolean).join(' · ')}</div>}
                          {r.event_title && <div className="text-[10px] text-blue-700 dark:text-blue-400">🎟 {r.event_title}</div>}
                        </td>
                        <td className="capitalize text-[10px]">{r.subject_kind?.replace('_', ' ') || '—'}</td>
                        <td className="font-mono text-[10px]">{r.entry_at?.slice(11, 16) || '—'}</td>
                        <td className="font-mono text-[10px]">{r.exit_at?.slice(11, 16) || '—'}</td>
                        <td>{r.still_inside ? <Badge className="bg-emerald-100 text-emerald-700 text-[9px]">Inside</Badge> : <Badge variant="outline" className="text-[9px]">Departed</Badge>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

