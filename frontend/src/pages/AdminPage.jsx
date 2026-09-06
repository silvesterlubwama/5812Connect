import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Users, Search, RefreshCw, Shield, Key, Trash2, Edit, UserCog, Printer, X, Plus, Download, Clock, AlertTriangle, Settings } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Card, CardContent } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Label } from '../components/ui/label';
import { Checkbox } from '../components/ui/checkbox';
import api, { adminApi, documentsApi, locationsApi, securityCheckpointApi, securityCompaniesApi, socialWorkOrphansApi, departmentsApi } from '../services/api';
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
import { DepartmentsManager } from '../components/admin/DepartmentsManager';
import IntegrationsManager from '../components/IntegrationsManager';
import BrandingEditor from '../components/BrandingEditor';
import RemoteAccessManager from '../components/RemoteAccessManager';
import DevicePairingDialog from '../components/DevicePairingDialog';

const ROLES = ['Executive Director', 'Adviser', 'Director', 'Manager', 'Coordinator', 'Staff', 'HR', 'Volunteer', 'Member', 'Parent', 'Customer', 'Guest'];

export default function AdminPage({ mode = 'system' }) {
  // iter306 — this page renders in two modes:
  //   mode='system'  → the /admin route: shows only system-level cards
  //                    (integrations, backup, branding, security infra,
  //                    module access, finance danger zone…). Header labelled
  //                    "System Console" to reflect what the tools actually do.
  //   mode='staff'   → embedded inside the HR page as the "Staff & Users"
  //                    tab: shows only the staff/user directory + edit +
  //                    reset-password + badge + bulk actions. HR owns the
  //                    people admin surface now that HR & Payroll is the
  //                    day-to-day admin's home.
  const showStaff = mode === 'staff';
  const showSystem = mode === 'system';
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
  const [bulkDepartment, setBulkDepartment] = useState('');
  const [bulkDeptMode, setBulkDeptMode] = useState('add');
  const [availableDepartments, setAvailableDepartments] = useState([]);
  useEffect(() => {
    departmentsApi.list({ include_inactive: false }).then(r => setAvailableDepartments(r.data || [])).catch(() => {});
  }, []);
  const [saving, setSaving] = useState(false);
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [createForm, setCreateForm] = useState({ name: '', email: '', phone: '', role: 'Staff', department: '', location_id: '', also_create_member: true, is_admin: false, will_sign_in: true });
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
    if (!createForm.name.trim()) { toast.error('Name is required'); return; }
    if (createForm.will_sign_in && !createForm.email.trim()) { toast.error('Email is required for users who will sign in'); return; }
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
        // Preserve the true underlying role — including system_admin — so that
        // saveEdit doesn't accidentally demote a system_admin back to 'admin'
        // when the admin-tier toggle is left on (bug: iter-user-hydrate).
        role: (p.role === 'admin' || p.role === 'system_admin') ? (p.secondary_roles?.[0] || 'Staff') : (p.role || 'Member'),
        underlying_role: p.role || '',    // hidden — used by saveEdit to preserve system_admin
        status: p.status || 'active', department: p.department || '',
        departments: p.departments || [],
        notes: p.notes || '',
        // Flags — hydrate every toggle rendered in the "Flags" tab so their
        // Switch components reflect the real DB state and a save round-trip
        // doesn't silently overwrite fields the admin never touched.
        is_parent: p.is_parent || false, is_customer: p.is_customer || false, is_donor: p.is_donor || false,
        is_guest: p.is_guest || false, is_medical: p.is_medical || false, is_resident: p.is_resident || false,
        has_restricted_access: p.has_restricted_access || false,
        resident_location_id: p.resident_location_id || '',
        is_admin: p.role === 'admin' || p.role === 'system_admin', secondary_roles: p.secondary_roles || [],
        pin: p.pin || '', gender: p.gender || '', date_of_birth: p.date_of_birth || '',
        national_id: p.national_id || '', address: p.address || '', emergency_contact: p.emergency_contact || '',
        group: p.group || '', location_id: p.location_id || '',
        location_ids: p.location_ids || (p.location_id ? [p.location_id] : []),
        program: p.program || '', member_id: p.member_id || '', title: p.title || '',
        // PBX + badge + security-contractor fields (bug fix: previously
        // dropped from hydration so edits nuked existing values on save).
        extension: p.extension || '', extension_pin: p.extension_pin || '', forward_to: p.forward_to || '',
        security_company_id: p.security_company_id || '', security_rank: p.security_rank || '',
        badge_id: p.badge_id || '', photo_url: p.photo_url || '',
      });
    } catch {
      setEditForm({ name: user.name || '', email: user.email || '', phone: user.phone || '',
        role: (user.role === 'admin' || user.role === 'system_admin') ? 'Staff' : (user.role || 'Member'),
        underlying_role: user.role || '',
        status: user.status || 'active', department: user.department || '', notes: user.notes || '',
        is_parent: user.is_parent || false, is_customer: user.is_customer || false, is_donor: user.is_donor || false,
        is_guest: user.is_guest || false, is_medical: user.is_medical || false, is_resident: user.is_resident || false,
        has_restricted_access: user.has_restricted_access || false,
        resident_location_id: user.resident_location_id || '',
        is_admin: user.role === 'admin' || user.role === 'system_admin', pin: user.pin || '',
        gender: '', date_of_birth: '', national_id: '', address: '', emergency_contact: '',
        group: '', location_id: user.location_id || '', location_ids: user.location_ids || [], program: '', member_id: '',
        extension: user.extension || '', extension_pin: '', forward_to: user.forward_to || '',
        security_company_id: '', security_rank: '', badge_id: user.badge_id || '', photo_url: user.photo_url || '',
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
      // iter-user-hydrate: preserve system_admin. The role Select shows a
      // downgraded label (Staff / secondary role) for admin-tier users, so
      // we must fold `is_admin` back into the admin-tier role explicitly,
      // and refuse to demote a system_admin unless the admin-tier toggle
      // is being turned off deliberately.
      const wasSystemAdmin = payload.underlying_role === 'system_admin';
      const wasAdmin = payload.underlying_role === 'admin' || wasSystemAdmin;
      if (payload.is_admin) {
        // Keep whatever admin tier they were on. Regular admin stays admin,
        // system_admin stays system_admin — no accidental demotion.
        payload.role = wasSystemAdmin ? 'system_admin' : (wasAdmin ? payload.underlying_role : 'admin');
      }
      delete payload.is_admin;
      delete payload.underlying_role;
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
      else if (bulkAction === 'department' && bulkDepartment) {
        // iter-bulk-tag: assign a department to N users at once. `add` mode
        // keeps existing tags; `replace` clobbers to just the picked one.
        const res = await departmentsApi.bulkTagUsers(ids, bulkDepartment, bulkDeptMode);
        toast.success(`Tagged ${res.data.updated} users with ${res.data.department?.name || 'department'}`);
      }
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
    <div className={mode === 'staff' ? 'space-y-5' : 'p-6 space-y-5'}>
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          {showSystem ? (
            <>
              <h1 className="text-2xl font-semibold font-heading flex items-center gap-2"><Shield size={24} /> System Console</h1>
              <p className="text-sm text-muted-foreground mt-0.5">Platform-wide settings — integrations, backups, branding, security infrastructure, module access.</p>
            </>
          ) : (
            <>
              <h1 className="text-2xl font-semibold font-heading flex items-center gap-2"><Shield size={24} /> Staff & Users</h1>
              <p className="text-sm text-muted-foreground mt-0.5">{users.length} staff members</p>
            </>
          )}
        </div>
        {showStaff && (
          <div className="flex gap-2 flex-wrap">
          {selectedIds.size > 0 && <Button variant="outline" onClick={() => setShowBulk(true)} className="gap-2"><UserCog size={16} /> Bulk ({selectedIds.size})</Button>}
          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => { setShowImport(true); setImportResult(null); setImportJson(''); }}><Download size={14} /> Import</Button>
          <Button size="sm" className="gap-1.5" onClick={() => { setShowCreateUser(true); setCreatedUser(null); setCreateForm({ name: '', email: '', phone: '', role: 'Staff', department: '', location_id: '', also_create_member: true, is_admin: false, will_sign_in: true }); }} data-testid="create-user-btn"><Plus size={14} /> New User</Button>
          <Button variant="outline" size="sm" onClick={fetchUsers}><RefreshCw size={14} /></Button>
        </div>
        )}
      </div>

      {/* Access Expiring Soon banner — moved into System Console tabs below */}

      {showStaff && (<>
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
      </>)}

      {/* Danger Zone — moved into the Data & Backup tab below */}

      {showStaff && (<>

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
                <SelectContent><SelectItem value="role">Change Role</SelectItem><SelectItem value="department" data-testid="bulk-action-department">Assign Department</SelectItem><SelectItem value="activate">Activate</SelectItem><SelectItem value="deactivate">Deactivate</SelectItem><SelectItem value="delete">Delete</SelectItem></SelectContent>
              </Select>
            </div>
            {bulkAction === 'role' && (
              <div className="space-y-2"><Label>New Role</Label>
                <Select value={bulkRole} onValueChange={setBulkRole}><SelectTrigger><SelectValue placeholder="Select role" /></SelectTrigger>
                  <SelectContent>{ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            )}
            {bulkAction === 'department' && (
              <>
                <div className="space-y-2"><Label>Department</Label>
                  <Select value={bulkDepartment} onValueChange={setBulkDepartment}>
                    <SelectTrigger data-testid="bulk-dept-select"><SelectValue placeholder="Pick department…" /></SelectTrigger>
                    <SelectContent>
                      {availableDepartments.map(d => (
                        <SelectItem key={d.id} value={d.id}>
                          <span className="inline-flex items-center gap-1.5">
                            {d.color && <span className="w-2 h-2 rounded-full" style={{ background: d.color }} />}{d.name}
                          </span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2"><Label>Mode</Label>
                  <Select value={bulkDeptMode} onValueChange={setBulkDeptMode}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="add">Add (keep existing tags)</SelectItem>
                      <SelectItem value="replace">Replace (only this department)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </>
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

      {/* System Console — grouped into tabs so scrolling doesn't get tiring */}
      </>)}
      {showSystem && ['admin', 'system_admin', 'Executive Director'].includes(currentUser?.role) && (
        <Tabs defaultValue="access" className="w-full">
          <TabsList className="w-full flex overflow-x-auto no-scrollbar md:inline-flex md:w-auto md:flex-wrap" data-testid="system-console-tabs">
            <TabsTrigger value="access" data-testid="sysconsole-tab-access"><Key size={13} className="mr-1" /> Access</TabsTrigger>
            <TabsTrigger value="departments" data-testid="sysconsole-tab-departments"><Users size={13} className="mr-1" /> Departments</TabsTrigger>
            <TabsTrigger value="security" data-testid="sysconsole-tab-security"><Shield size={13} className="mr-1" /> Security</TabsTrigger>
            <TabsTrigger value="data" data-testid="sysconsole-tab-data"><Download size={13} className="mr-1" /> Data & Backup</TabsTrigger>
            <TabsTrigger value="integrations" data-testid="sysconsole-tab-integrations"><Plus size={13} className="mr-1" /> Integrations</TabsTrigger>
            <TabsTrigger value="branding" data-testid="sysconsole-tab-branding"><Edit size={13} className="mr-1" /> Branding</TabsTrigger>
          </TabsList>

          {/* Access: expiring-grants banner + per-module access grants. */}
          <TabsContent value="access" className="mt-4 space-y-4">
            <ExpiringGrantsBanner />
            <ModuleAccessManager />
          </TabsContent>

          {/* Departments: cost-centre dimension. Not a physical location —
              used for staff tagging, split-funded salaries, and dept P&L. */}
          <TabsContent value="departments" className="mt-4 space-y-4">
            <DepartmentsManager />
          </TabsContent>

          {/* Security: checkpoints, vendor firms, kiosks, remote access, device pairing. */}
          <TabsContent value="security" className="mt-4 space-y-4">
            <SecurityCheckpointsManager />
            <SecurityCompaniesManager />
            <KioskLinksManager />
            <RemoteAccessManager />
            <DevicePairingDialog />
          </TabsContent>

          {/* Data & Backup: snapshot/restore, orphan case repair, finance danger zone. */}
          <TabsContent value="data" className="mt-4 space-y-4">
            <BackupRestoreManager />
            <OrphanCaseRepairCard />
            {(currentUser?.role === 'admin' || currentUser?.role === 'system_admin') && (
              <>
                <FinanceResetCard />
                <HrResetCard />
              </>
            )}
          </TabsContent>

          {/* Integrations: 3rd-party API keys (Resend, Wave, Alpha Vantage, etc.). */}
          <TabsContent value="integrations" className="mt-4 space-y-4">
            <IntegrationsManager />
          </TabsContent>

          {/* Branding: logo, colours, sender name shown on emails + badges. */}
          <TabsContent value="branding" className="mt-4 space-y-4">
            <BrandingEditor />
          </TabsContent>
        </Tabs>
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
            Entry / exit times per person, by day. Residents are filtered out by default — they live at this location so they aren&apos;t tracked as daily guests.
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


// ============== SECURITY COMPANIES MANAGER ==============
// Contractor firms whose personnel man the checkpoint kiosk. Each company
// has a name, phone, and optional logo. Individual Security Contractor users
// link to a company via `security_company_id` on their user record.
function SecurityCompaniesManager() {
  const [companies, setCompanies] = useState([]);
  const [showManager, setShowManager] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ name: '', phone: '', contact_email: '', address: '' });
  const [saving, setSaving] = useState(false);

  const load = () => securityCompaniesApi.list().then(r => setCompanies(r.data || [])).catch(() => {});
  useEffect(() => { if (showManager) load(); }, [showManager]);

  const startAdd = () => { setEditing(null); setForm({ name: '', phone: '', contact_email: '', address: '' }); };
  const startEdit = (c) => { setEditing(c); setForm({ name: c.name, phone: c.phone || '', contact_email: c.contact_email || '', address: c.address || '' }); };
  const save = async () => {
    if (!form.name.trim()) { toast.error('Name is required'); return; }
    setSaving(true);
    try {
      if (editing) { await securityCompaniesApi.update(editing.id, form); toast.success('Company updated'); }
      else { await securityCompaniesApi.create(form); toast.success('Company added'); }
      startAdd();
      load();
    } catch (err) { toast.error(err.response?.data?.detail || 'Save failed'); }
    finally { setSaving(false); }
  };
  const remove = async (id) => {
    if (!window.confirm('Delete this security company? If any users are linked, it will be deactivated instead.')) return;
    try { const r = await securityCompaniesApi.remove(id); toast.success(r.data?.deactivated ? 'Deactivated (users still linked)' : 'Deleted'); load(); }
    catch { toast.error('Delete failed'); }
  };
  const uploadLogo = async (companyId, file) => {
    if (!file) return;
    try {
      const fd = new FormData(); fd.append('file', file);
      await securityCompaniesApi.uploadLogo(companyId, fd);
      toast.success('Logo uploaded');
      load();
    } catch (err) { toast.error(err.response?.data?.detail || 'Logo upload failed'); }
  };
  const toggleActive = async (c) => {
    try { await securityCompaniesApi.update(c.id, { active: !c.active }); load(); }
    catch { toast.error('Failed to toggle'); }
  };

  return (
    <>
      <Card className="mt-6"><CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2"><Shield size={18} /> Security Companies</h2>
            <p className="text-sm text-muted-foreground mt-1">External firms whose personnel man the security checkpoint. Their logo appears on personnel badges.</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => setShowManager(true)} data-testid="open-security-companies">Manage</Button>
        </div>
      </CardContent></Card>

      <Dialog open={showManager} onOpenChange={setShowManager}>
        <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Shield size={18} /> Security Companies</DialogTitle>
            <DialogDescription>Manage the vendor firms whose personnel are contracted to secure your locations.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="rounded-lg border p-3 space-y-2 bg-muted/30">
              <p className="text-xs font-semibold uppercase text-muted-foreground tracking-wide">{editing ? 'Edit Company' : 'Add New Company'}</p>
              <div className="grid grid-cols-2 gap-2">
                <Input placeholder="Company name *" value={form.name} onChange={e => setForm({...form, name: e.target.value})} data-testid="sec-co-name" />
                <Input placeholder="Phone" value={form.phone} onChange={e => setForm({...form, phone: e.target.value})} data-testid="sec-co-phone" />
                <Input placeholder="Contact email" value={form.contact_email} onChange={e => setForm({...form, contact_email: e.target.value})} />
                <Input placeholder="Address" value={form.address} onChange={e => setForm({...form, address: e.target.value})} />
              </div>
              <div className="flex gap-2 justify-end">
                {editing && <Button size="sm" variant="ghost" onClick={startAdd}>Cancel</Button>}
                <Button size="sm" onClick={save} disabled={saving} data-testid="sec-co-save">{saving ? 'Saving...' : (editing ? 'Update' : 'Add Company')}</Button>
              </div>
            </div>

            <div className="space-y-2">
              {companies.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-6">No security companies yet</p>
              ) : companies.map(c => (
                <div key={c.id} className="flex items-center gap-3 p-3 rounded-lg border" data-testid={`sec-co-row-${c.id}`}>
                  <div className="w-12 h-12 rounded bg-muted flex items-center justify-center overflow-hidden shrink-0 border">
                    {c.logo_url ? <img src={c.logo_url} alt={c.name} className="w-full h-full object-contain" /> : <Shield size={20} className="text-muted-foreground" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium truncate">{c.name}</p>
                      {c.active === false && <Badge variant="secondary" className="text-[10px]">Deactivated</Badge>}
                    </div>
                    <p className="text-xs text-muted-foreground">{[c.phone, c.contact_email].filter(Boolean).join(' · ') || '—'}</p>
                  </div>
                  <div className="flex gap-1">
                    <input type="file" accept="image/*" className="hidden" id={`logo-upload-${c.id}`} onChange={e => uploadLogo(c.id, e.target.files?.[0])} />
                    <Button size="sm" variant="ghost" onClick={() => document.getElementById(`logo-upload-${c.id}`).click()} title="Upload logo"><Plus size={13} /></Button>
                    <Button size="sm" variant="ghost" onClick={() => startEdit(c)} title="Edit"><Edit size={13} /></Button>
                    <Button size="sm" variant="ghost" onClick={() => toggleActive(c)} title={c.active === false ? 'Reactivate' : 'Deactivate'}><Key size={13} /></Button>
                    <Button size="sm" variant="ghost" onClick={() => remove(c.id)} title="Delete" className="text-destructive"><Trash2 size={13} /></Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ============== ORPHAN CASE REPAIR ==============
// Legacy social-work cases whose subject_id is empty can't upload scans or
// auto-populate the child profile. This card lists them with the top-3
// similarity-matched child suggestions and offers a "Repair all ≥90%"
// bulk action so directors can clear the backlog in one click.
function OrphanCaseRepairCard() {
  const [orphans, setOrphans] = useState(null);
  const [busy, setBusy] = useState(false);
  const [threshold, setThreshold] = useState(90);

  const load = () => socialWorkOrphansApi.list().then(r => setOrphans(r.data || [])).catch(() => setOrphans([]));

  const linkOne = async (caseId, childId) => {
    try {
      await api.put(`/social-work/cases/${caseId}`, { subject_id: childId, subject_kind: 'child' });
      toast.success('Case linked');
      load();
    } catch (err) { toast.error(err.response?.data?.detail || 'Link failed'); }
  };
  const autoRepair = async () => {
    setBusy(true);
    try {
      const r = await socialWorkOrphansApi.autoRepair(threshold / 100);
      toast.success(`Repaired ${r.data.repaired_count} · skipped ${r.data.skipped_count}`);
      load();
    } catch (err) { toast.error(err.response?.data?.detail || 'Auto-repair failed'); }
    finally { setBusy(false); }
  };

  return (
    <Card className="mt-6"><CardContent className="pt-6">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2"><AlertTriangle size={18} className="text-red-500" /> Unlinked Social Cases</h2>
          <p className="text-sm text-muted-foreground mt-1">Legacy cases without a linked child record. Click the best match to repair, or auto-repair everything above the confidence threshold.</p>
        </div>
        <Button variant="outline" size="sm" onClick={load} data-testid="load-orphans">{orphans === null ? 'Load' : `Refresh (${orphans.length})`}</Button>
      </div>
      {orphans !== null && orphans.length === 0 && <p className="text-sm text-emerald-700 py-3">✓ No orphaned cases — everything linked cleanly.</p>}
      {orphans !== null && orphans.length > 0 && (
        <>
          <div className="flex items-center gap-2 mb-3 p-2 bg-muted/40 rounded-lg">
            <span className="text-xs">Auto-repair threshold:</span>
            <Input type="number" min="50" max="100" step="5" value={threshold} onChange={e => setThreshold(+e.target.value || 90)} className="w-20 h-7 text-xs" data-testid="orphan-threshold" />
            <span className="text-xs text-muted-foreground">%</span>
            <Button size="sm" onClick={autoRepair} disabled={busy} className="ml-auto" data-testid="orphan-auto-repair">
              {busy ? 'Repairing…' : `Repair All ≥${threshold}%`}
            </Button>
          </div>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {orphans.map(o => (
              <div key={o.id} className="p-3 rounded-lg border flex items-start gap-3" data-testid={`orphan-row-${o.id}`}>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">{o.subject_name || '(no name)'}</p>
                  <p className="text-[10px] text-muted-foreground">Case {o.id} · opened {(o.opened_at || '').slice(0, 10)}</p>
                  {(o.suggestions || []).length === 0 ? (
                    <p className="text-xs text-red-600 mt-1">No name match found — link manually via the case dialog.</p>
                  ) : (
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {(o.suggestions || []).map(s => (
                        <button
                          key={s.child_id}
                          onClick={() => linkOne(o.id, s.child_id)}
                          className="inline-flex items-center gap-1.5 rounded-full border border-red-300 bg-white px-2 py-1 text-[11px] font-medium text-red-800 hover:bg-red-50"
                          data-testid={`orphan-suggest-${o.id}-${s.child_id}`}
                        >
                          {s.name}
                          {s.date_of_birth && <span className="text-[9px] text-red-600/70">· {s.date_of_birth.slice(0, 10)}</span>}
                          <span className="text-[9px] rounded bg-red-600/10 px-1 py-0.5 text-red-700">{s.score}%</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </CardContent></Card>
  );
}



// ── Danger Zone: Finance Reset ────────────────────────────────────────────────
// Wipes and archives every finance/marketplace collection (ledger, financial
// records, banking, donors, vendors, products, sales, cash drops, approvals,
// budgets). HR data is intentionally preserved. Every wiped doc lands in
// `<collection>_archive_<timestamp>` so recovery is always possible.
function FinanceResetCard() {
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(null);

  useEffect(() => {
    if (!open) return;
    (async () => {
      try { const r = await api.get('/finance/admin/status'); setStatus(r.data); }
      catch { setStatus(null); }
    })();
  }, [open]);

  const submit = async () => {
    setBusy(true);
    try {
      const r = await api.post('/finance/admin/reset', { confirm });
      if (r.data?.error) { toast.error(r.data.error); setBusy(false); return; }
      const wiped = Object.entries(r.data.archived || {})
        .filter(([, n]) => n > 0)
        .reduce((s, [, n]) => s + n, 0);
      toast.success(`Reset complete · ${wiped} records archived · ${r.data.seeded_accounts} accounts seeded`);
      setOpen(false); setConfirm('');
    }
    catch (e) { toast.error(e?.response?.data?.detail || 'Reset failed'); }
    setBusy(false);
  };

  return (
    <Card className="border-red-300/60 bg-red-50/40" data-testid="admin-danger-zone">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center gap-2 text-red-700">
          <AlertTriangle size={16} />
          <h3 className="font-semibold text-sm">Danger Zone</h3>
        </div>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex-1 min-w-[240px]">
            <p className="text-sm font-medium">Reset Finance & Marketplace</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Archives and clears the ledger, financial records, banking, donors, vendors, products, marketplace postings, sales, cash drops, approvals, and budgets. HR (salaries and payslips) is preserved. Recoverable from timestamped archive collections.
            </p>
          </div>
          <Button
            variant="outline" size="sm"
            className="text-red-700 border-red-300 hover:bg-red-100"
            onClick={() => setOpen(true)}
            data-testid="finance-reset-open"
          >
            <AlertTriangle size={14} className="mr-1" /> Reset Finance
          </Button>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle className="text-red-700">Reset Finance & Marketplace</DialogTitle>
              <DialogDescription>
                This archives every finance and marketplace collection into <code>_archive_&lt;timestamp&gt;</code> tables and re-seeds a fresh chart of accounts. HR payslips and salaries are left untouched.
              </DialogDescription>
            </DialogHeader>
            {status?.collections && (
              <div className="max-h-56 overflow-auto rounded border border-border bg-background text-xs">
                <table className="w-full">
                  <thead className="bg-muted/60 sticky top-0"><tr><th className="text-left px-2 py-1 font-medium">Collection</th><th className="text-right px-2 py-1 font-medium">Records</th></tr></thead>
                  <tbody>
                    {Object.entries(status.collections)
                      .sort((a, b) => (b[1] || 0) - (a[1] || 0))
                      .map(([k, v]) => (
                        <tr key={k} className="border-t border-border/60"><td className="px-2 py-1 font-mono text-[11px]">{k}</td><td className="px-2 py-1 text-right">{v}</td></tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="text-sm mt-1">Type <strong>RESET FINANCE</strong> to confirm.</p>
            <Input value={confirm} onChange={e => setConfirm(e.target.value)} placeholder="RESET FINANCE" data-testid="finance-reset-input" />
            <div className="flex gap-3 justify-end">
              <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>Cancel</Button>
              <Button variant="destructive" onClick={submit} disabled={busy || confirm !== 'RESET FINANCE'} data-testid="finance-reset-confirm">
                {busy ? 'Resetting…' : 'Reset Finance'}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  );
}

// ============== HR RESET CARD (moved out of HR page — iter-hr-reset-move) ==============
// Same danger-zone flow that used to live on HRPage. Two-step preview → confirm.
// Sitting next to Finance reset so ops folks don't stumble onto it inside HR.
function HrResetCard() {
  const { user } = useAuth();
  const [modal, setModal] = useState(null); // { open, scope, campus_scope, ledger, preview, busy, confirmText }

  const openModal = () => setModal({
    open: true, scope: 'payslips', campus_scope: 'active',
    ledger: 'reverse', preview: null, busy: false, confirmText: '',
  });

  const runPreview = async () => {
    if (!modal) return;
    setModal({ ...modal, busy: true });
    try {
      const params = { scope: modal.scope, campus_scope: modal.campus_scope, ledger: modal.ledger };
      const res = await api.delete('/hr/reset', { params });
      setModal({ ...modal, busy: false, preview: res.data });
    } catch (e) {
      setModal({ ...modal, busy: false });
      toast.error(e.response?.data?.detail || 'Preview failed');
    }
  };

  const runApply = async () => {
    if (!modal) return;
    setModal({ ...modal, busy: true });
    try {
      const params = { scope: modal.scope, campus_scope: modal.campus_scope, ledger: modal.ledger, confirm: 'RESET-HR' };
      const res = await api.delete('/hr/reset', { params });
      const summary = Object.entries(res.data.deleted || {}).map(([k, v]) => `${k}: ${v}`).join(', ');
      toast.success(`HR reset complete. ${summary}`);
      setModal(null);
    } catch (e) {
      setModal({ ...modal, busy: false });
      toast.error(e.response?.data?.detail || 'Reset failed');
    }
  };

  return (
    <Card className="border-red-300/60 bg-red-50/40" data-testid="admin-hr-danger-zone">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center gap-2 text-red-700">
          <AlertTriangle size={16} />
          <h3 className="font-semibold text-sm">Danger Zone</h3>
        </div>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex-1 min-w-[240px]">
            <p className="text-sm font-medium">Reset HR Module</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Wipes payslips (or the entire HR module including salaries, contracts, timesheets, leave, and documents). Records land in the Recycle Bin; paid payroll ledger entries can be reversed as offsetting JEs or hard-deleted.
            </p>
          </div>
          <Button
            variant="outline" size="sm"
            className="text-red-700 border-red-300 hover:bg-red-100"
            onClick={openModal}
            data-testid="hr-reset-open"
          >
            <Trash2 size={14} className="mr-1" /> Reset HR
          </Button>
        </div>

        <Dialog open={!!modal?.open} onOpenChange={(o) => !o && setModal(null)}>
          <DialogContent className="max-w-md" data-testid="hr-reset-dialog">
            <DialogHeader>
              <DialogTitle className="text-red-700 flex items-center gap-2"><Trash2 size={16} /> Reset HR Module</DialogTitle>
              <DialogDescription>Preview counts first, then type <code>RESET-HR</code> to apply.</DialogDescription>
            </DialogHeader>
            {modal && (
              <div className="space-y-3 text-sm">
                <div className="rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-800">
                  <strong>Danger zone.</strong> Deleted records go to the Recycle Bin. Paid-payroll ledger postings must be either reversed (offsetting JE) or hard-deleted.
                </div>

                <div>
                  <Label className="text-xs">What to reset</Label>
                  <Select value={modal.scope} onValueChange={(v) => setModal({ ...modal, scope: v, preview: null, confirmText: '' })}>
                    <SelectTrigger data-testid="reset-scope-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="payslips" data-testid="reset-scope-payslips">Payslips only</SelectItem>
                      <SelectItem value="all" data-testid="reset-scope-all">Entire HR module (payslips + salaries + contracts + timesheets + leave + docs)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label className="text-xs">Campus scope</Label>
                  <Select value={modal.campus_scope} onValueChange={(v) => setModal({ ...modal, campus_scope: v, preview: null, confirmText: '' })}>
                    <SelectTrigger data-testid="reset-campus-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="active" data-testid="reset-campus-active">Active campus only</SelectItem>
                      {user?.role === 'system_admin' && <SelectItem value="all" data-testid="reset-campus-all">All campuses (system_admin only)</SelectItem>}
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label className="text-xs">Ledger action for paid payroll</Label>
                  <Select value={modal.ledger} onValueChange={(v) => setModal({ ...modal, ledger: v, preview: null, confirmText: '' })}>
                    <SelectTrigger data-testid="reset-ledger-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="reverse" data-testid="reset-ledger-reverse">Reverse (post offsetting JEs — auditable)</SelectItem>
                      <SelectItem value="delete" data-testid="reset-ledger-delete">Delete (hard-remove expenses + JEs — no trail)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {modal.preview && (
                  <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-xs space-y-1">
                    <p className="font-semibold text-amber-800">Preview (nothing deleted yet)</p>
                    {Object.entries(modal.preview.counts || {}).map(([k, v]) => (
                      <p key={k}><span className="text-muted-foreground">{k}:</span> <strong>{v}</strong></p>
                    ))}
                  </div>
                )}

                {modal.preview && (
                  <div>
                    <Label className="text-xs">Type <code className="bg-red-100 px-1 rounded">RESET-HR</code> to confirm</Label>
                    <Input
                      value={modal.confirmText}
                      onChange={(e) => setModal({ ...modal, confirmText: e.target.value })}
                      placeholder="RESET-HR"
                      data-testid="reset-confirm-input"
                    />
                  </div>
                )}
              </div>
            )}
            <div className="flex gap-3 justify-end">
              <Button variant="outline" onClick={() => setModal(null)} data-testid="reset-cancel-btn">Cancel</Button>
              {!modal?.preview ? (
                <Button variant="destructive" disabled={modal?.busy} onClick={runPreview} data-testid="reset-preview-btn">
                  {modal?.busy ? 'Loading…' : 'Preview count'}
                </Button>
              ) : (
                <Button
                  variant="destructive"
                  disabled={modal?.busy || modal?.confirmText !== 'RESET-HR'}
                  onClick={runApply}
                  data-testid="reset-apply-btn"
                >
                  {modal?.busy ? 'Resetting…' : 'Permanently reset'}
                </Button>
              )}
            </div>
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  );
}

