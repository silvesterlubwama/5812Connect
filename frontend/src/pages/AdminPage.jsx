import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Users, Search, RefreshCw, Shield, Key, Trash2, Edit, CheckSquare,
  Square, UserCog, FileText, Upload, Printer, X, Plus, ChevronDown,
  Download, AlertCircle, Bluetooth, Wifi, Monitor
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Switch } from '../components/ui/switch';
import { Checkbox } from '../components/ui/checkbox';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Textarea } from '../components/ui/textarea';
import { adminApi, documentsApi, membersApi, locationsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

const ROLES = ['Executive Director', 'Adviser', 'Director', 'Manager', 'Coordinator', 'Staff', 'HR', 'Volunteer', 'Member', 'Parent', 'Customer', 'Guest'];
const SYSTEM_ADMIN_ROLES = ['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director'];
const GROUPS = ['General', 'Staff', 'Volunteers', 'Youth', 'Women', 'Men', 'Children', 'Leadership'];
const ID_TYPE_LABELS = {
  national_id: 'National ID',
  state_id: 'State ID',
  drivers_license: "Driver's Licence",
  passport: 'Passport',
  birth_certificate: 'Birth Certificate',
  refugee_id: 'Refugee ID',
  alien_id: 'Alien ID',
  voter_card: 'Voter Card',
  student_id: 'Student ID',
  employee_id: 'Employee ID',
  other: 'Other',
};

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
  const [showDocRequest, setShowDocRequest] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [editForm, setEditForm] = useState({});
  const [newPassword, setNewPassword] = useState('');
  const [bulkAction, setBulkAction] = useState('');
  const [bulkRole, setBulkRole] = useState('');
  const [saving, setSaving] = useState(false);
  // New User
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [createForm, setCreateForm] = useState({ name: '', email: '', phone: '', role: 'Staff', department: '', location_id: '', also_create_member: true, is_admin: false });
  const [createdUser, setCreatedUser] = useState(null);
  // Import Users
  const [showImport, setShowImport] = useState(false);
  const [importJson, setImportJson] = useState('');
  const [importLoading, setImportLoading] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const importFileRef = useRef(null);
  // Documents
  const [memberDocs, setMemberDocs] = useState([]);
  const [docRequests, setDocRequests] = useState([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [docRequestForm, setDocRequestForm] = useState({ doc_type: 'national_id', message: '' });
  const [uploadingDoc, setUploadingDoc] = useState(false);
  const fileInputRef = useRef(null);
  const [uploadDocType, setUploadDocType] = useState('other');
  // Scanner
  const [showScanner, setShowScanner] = useState(false);
  const [scannerStatus, setScannerStatus] = useState('idle');

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
      if (payload.is_admin) {
        payload.role = 'admin';
      }
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
      const users = Array.isArray(parsed) ? parsed : (parsed.users || [parsed]);
      const res = await adminApi.importUsers(users);
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
    } else {
      reader.onload = (ev) => setImportJson(ev.target.result);
      reader.readAsText(file);
    }
  };

  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next;
    });
  };
  const selectAll = () => {
    setSelectedIds(selectedIds.size === users.length ? new Set() : new Set(users.map(u => u.id)));
  };

  const openEdit = async (user) => {
    setSelectedUser(user);
    // Load full profile (merged users + members)
    try {
      const res = await adminApi.getUserFullProfile(user.id);
      const profile = res.data;
      setEditForm({
        name: profile.name || '',
        email: profile.email || '',
        phone: profile.phone || '',
        role: (profile.role === 'admin' || profile.role === 'system_admin') ? (profile.secondary_roles?.[0] || 'Staff') : (profile.role || 'Member'),
        status: profile.status || 'active',
        department: profile.department || '',
        notes: profile.notes || '',
        is_parent: profile.is_parent || false,
        is_customer: profile.is_customer || false,
        is_donor: profile.is_donor || false,
        is_admin: profile.role === 'admin' || profile.role === 'system_admin',
        secondary_roles: profile.secondary_roles || [],
        pin: profile.pin || '',
        gender: profile.gender || '',
        date_of_birth: profile.date_of_birth || '',
        national_id: profile.national_id || '',
        address: profile.address || '',
        emergency_contact: profile.emergency_contact || '',
        group: profile.group || '',
        location_id: profile.location_id || '',
        location_ids: profile.location_ids || (profile.location_id ? [profile.location_id] : []),
        program: profile.program || '',
        member_id: profile.member_id || '',
        title: profile.title || '',
      });
    } catch {
      // Fallback to basic user data
      setEditForm({
        name: user.name || '', email: user.email || '', phone: user.phone || '',
        role: (user.role === 'admin' || user.role === 'system_admin') ? 'Staff' : (user.role || 'Member'),
        status: user.status || 'active',
        department: user.department || '', notes: user.notes || '',
        is_parent: user.is_parent || false, is_customer: user.is_customer || false,
        is_donor: user.is_donor || false, is_admin: user.role === 'admin' || user.role === 'system_admin',
        pin: user.pin || '',
        gender: '', date_of_birth: '', national_id: '', address: '',
        emergency_contact: '', group: '', location_id: user.location_id || '', program: '', member_id: '',
      });
    }
    setShowEdit(true);
    // Load documents for this user
    loadMemberDocs(user.id);
  };

  const loadMemberDocs = async (userId) => {
    setDocsLoading(true);
    try {
      const [docsRes, reqsRes] = await Promise.all([
        documentsApi.list(userId).catch(() => ({ data: [] })),
        documentsApi.listRequests({ member_id: userId }).catch(() => ({ data: [] })),
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
      if (payload.is_admin) {
        payload.role = 'admin';
      }
      delete payload.is_admin;
      // Ensure location_ids is sent
      if (!payload.location_ids?.length && payload.location_id) {
        payload.location_ids = [payload.location_id];
      }
      const res = await adminApi.updateUser(selectedUser.id, payload);
      setUsers(prev => prev.map(u => u.id === selectedUser.id ? { ...u, ...res.data } : u));
      toast.success('Profile updated');
    } catch (err) { toast.error(err.response?.data?.detail || 'Update failed'); }
    finally { setSaving(false); }
  };

  const resetPassword = async () => {
    if (!selectedUser || !newPassword) return;
    setSaving(true);
    try {
      await adminApi.resetPassword(selectedUser.id, newPassword);
      setShowResetPw(false); setNewPassword('');
      toast.success('Password reset');
    } catch (err) { toast.error(err.response?.data?.detail || 'Reset failed'); }
    finally { setSaving(false); }
  };

  const deleteUser = async (user) => {
    if (!window.confirm(`Delete "${user.name}"? This cannot be undone.`)) return;
    try {
      await adminApi.deleteUser(user.id);
      setUsers(prev => prev.filter(u => u.id !== user.id));
      toast.success('User deleted');
    } catch (err) { toast.error(err.response?.data?.detail || 'Delete failed'); }
  };

  const executeBulk = async () => {
    const ids = [...selectedIds];
    if (!ids.length) return;
    setSaving(true);
    try {
      if (bulkAction === 'delete') {
        const res = await adminApi.bulkDeleteUsers(ids);
        toast.success(`Deleted ${res.data.deleted} users`);
      } else if (bulkAction === 'role' && bulkRole) {
        const res = await adminApi.bulkUpdateUsers(ids, { role: bulkRole });
        toast.success(`Updated ${res.data.updated} users`);
      } else if (bulkAction === 'activate') {
        const res = await adminApi.bulkUpdateUsers(ids, { status: 'active' });
        toast.success(`Activated ${res.data.updated} users`);
      } else if (bulkAction === 'deactivate') {
        const res = await adminApi.bulkUpdateUsers(ids, { status: 'inactive' });
        toast.success(`Deactivated ${res.data.updated} users`);
      }
      setSelectedIds(new Set()); setShowBulk(false); fetchUsers();
    } catch (err) { toast.error(err.response?.data?.detail || 'Bulk action failed'); }
    finally { setSaving(false); }
  };

  // ---- Document upload ----
  const handleDocUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !selectedUser) return;
    setUploadingDoc(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('doc_type', uploadDocType);
      const res = await documentsApi.upload(selectedUser.id, fd);
      setMemberDocs(prev => [res.data, ...prev]);
      toast.success('Document uploaded');
    } catch (err) { toast.error(err.response?.data?.detail || 'Upload failed'); }
    finally { setUploadingDoc(false); if (fileInputRef.current) fileInputRef.current.value = ''; }
  };

  const deleteDoc = async (docId) => {
    if (!window.confirm('Delete this document?')) return;
    try {
      await documentsApi.delete(docId);
      setMemberDocs(prev => prev.filter(d => d.id !== docId));
      toast.success('Document deleted');
    } catch { toast.error('Delete failed'); }
  };

  // ---- Document request ----
  const submitDocRequest = async () => {
    if (!selectedUser) return;
    setSaving(true);
    try {
      const res = await documentsApi.createRequest({
        member_id: selectedUser.id,
        doc_type: docRequestForm.doc_type,
        message: docRequestForm.message,
      });
      setDocRequests(prev => [res.data, ...prev]);
      setShowDocRequest(false);
      setDocRequestForm({ doc_type: 'national_id', message: '' });
      toast.success('Document request sent');
    } catch (err) { toast.error(err.response?.data?.detail || 'Request failed'); }
    finally { setSaving(false); }
  };

  const cancelRequest = async (reqId) => {
    try {
      await documentsApi.cancelRequest(reqId);
      setDocRequests(prev => prev.map(r => r.id === reqId ? { ...r, status: 'cancelled' } : r));
      toast.success('Request cancelled');
    } catch { toast.error('Cancel failed'); }
  };

  // ---- Scanner (Web Bluetooth / Web Serial) ----
  const tryConnectScanner = async () => {
    setScannerStatus('connecting');
    try {
      if (navigator.bluetooth) {
        const device = await navigator.bluetooth.requestDevice({
          acceptAllDevices: true,
          optionalServices: ['generic_access'],
        });
        setScannerStatus(`connected:${device.name || 'Bluetooth Device'}`);
        toast.success(`Connected: ${device.name || 'Bluetooth Device'}. Use your scanner software to capture the document, then upload the saved file.`);
      } else if (navigator.serial) {
        const port = await navigator.serial.requestPort();
        await port.open({ baudRate: 9600 });
        setScannerStatus('connected:Serial Device');
        toast.success('Serial scanner connected. Initiate scan from your scanner device.');
        setTimeout(() => port.close(), 5000);
      } else {
        setScannerStatus('unsupported');
        toast.warning('Web Bluetooth and Web Serial are not supported in this browser. Please scan the document separately and upload the file.');
      }
    } catch (err) {
      setScannerStatus('error');
      if (err.name !== 'NotFoundError') {
        toast.error(`Scanner connection failed: ${err.message}`);
      }
    }
  };

  const roleColor = (role) => {
    const colors = { admin: 'bg-red-100 text-red-700', 'Executive Director': 'bg-purple-100 text-purple-700', Adviser: 'bg-violet-100 text-violet-700', Director: 'bg-indigo-100 text-indigo-700', Manager: 'bg-blue-100 text-blue-700', Staff: 'bg-teal-100 text-teal-700', HR: 'bg-orange-100 text-orange-700', Volunteer: 'bg-green-100 text-green-700', Member: 'bg-slate-100 text-slate-700' };
    return colors[role] || 'bg-slate-100 text-slate-600';
  };

  const statusBadge = (s) => s === 'pending' ? 'bg-yellow-100 text-yellow-700' : s === 'fulfilled' ? 'bg-green-100 text-green-700' : s === 'cancelled' ? 'bg-red-100 text-red-700' : 'bg-slate-100 text-slate-600';

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold font-heading flex items-center gap-2"><Shield size={24} /> Staff Administration</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{users.length} staff members · Manage profiles, roles, passwords & documents</p>
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
          <SelectContent>
            <SelectItem value="all">All Roles</SelectItem>
            {ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Checkbox checked={selectedIds.size > 0 && selectedIds.size === users.length} onCheckedChange={selectAll} />
        <span>Select all</span>
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
                    {user.has_member_profile && <Badge variant="outline" className="text-xs border-indigo-300 text-indigo-600 bg-indigo-50" title="Has People profile">People</Badge>}
                    {user.is_parent && <Badge variant="outline" className="text-xs border-pink-300 text-pink-600">Parent</Badge>}
                    {user.is_donor && <Badge variant="outline" className="text-xs border-green-300 text-green-600">Donor</Badge>}
                    {user.is_customer && <Badge variant="outline" className="text-xs border-blue-300 text-blue-600">Customer</Badge>}
                  </div>
                  <p className="text-xs text-muted-foreground truncate">{user.email} {user.phone ? `· ${user.phone}` : ''} {user.location_id ? `· Loc: ${locations.find(l => l.id === user.location_id)?.name || user.location_id}` : ''}</p>
                </div>
                <div className="flex gap-1.5">
                  <Button data-testid={`edit-user-${user.id}`} size="sm" variant="ghost" onClick={() => openEdit(user)} title="Edit Profile"><Edit size={14} /></Button>
                  <Button size="sm" variant="ghost" onClick={() => { setSelectedUser(user); setShowBadge(true); }} title="Print Badge"><Printer size={14} /></Button>
                  <Button size="sm" variant="ghost" onClick={() => { setSelectedUser(user); setShowResetPw(true); }} title="Reset Password"><Key size={14} /></Button>
                  <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => deleteUser(user)} title="Delete"><Trash2 size={14} /></Button>
                </div>
              </CardContent>
            </Card>
          ))}
          {users.length === 0 && <div className="text-center py-12 text-muted-foreground"><Users size={40} className="mx-auto mb-3 opacity-30" /><p>No users found</p></div>}
        </div>
      )}

      {/* ===== CREATE USER DIALOG ===== */}
      <Dialog open={showCreateUser} onOpenChange={o => { setShowCreateUser(o); if (!o) setCreatedUser(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{createdUser ? 'User Created!' : 'Create New User'}</DialogTitle>
            <DialogDescription>{createdUser ? 'Share these credentials with the new user.' : 'Add a staff member or user account.'}</DialogDescription>
          </DialogHeader>
          {createdUser ? (
            <div className="space-y-4">
              <div className="flex items-center gap-3 p-4 bg-green-50 rounded-xl border border-green-200">
                <div className="h-10 w-10 rounded-full bg-green-100 flex items-center justify-center font-bold text-green-700">{createdUser.name?.[0]}</div>
                <div>
                  <p className="font-semibold">{createdUser.name}</p>
                  <p className="text-sm text-muted-foreground">{createdUser.email} · {createdUser.role}</p>
                </div>
              </div>
              {createdUser.temp_password && (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">Temporary Password (share securely)</p>
                  <div className="flex items-center gap-2 p-3 bg-muted rounded-lg font-mono text-sm">
                    <span className="flex-1">{createdUser.temp_password}</span>
                    <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={() => { navigator.clipboard.writeText(createdUser.temp_password); toast.success('Copied!'); }}>Copy</Button>
                  </div>
                </div>
              )}
              {createdUser.has_member_profile && <p className="text-xs text-indigo-600 flex items-center gap-1.5"><Users size={12} /> Also added to People directory</p>}
              <Button className="w-full" onClick={() => { setShowCreateUser(false); setCreatedUser(null); }}>Done</Button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2 space-y-1.5"><Label className="text-xs">Full Name *</Label><Input value={createForm.name} onChange={e => setCreateForm({ ...createForm, name: e.target.value })} data-testid="create-user-name" /></div>
                <div className="col-span-2 space-y-1.5"><Label className="text-xs">Email *</Label><Input type="email" value={createForm.email} onChange={e => setCreateForm({ ...createForm, email: e.target.value })} data-testid="create-user-email" /></div>
                <div className="space-y-1.5"><Label className="text-xs">Phone</Label><Input value={createForm.phone} onChange={e => setCreateForm({ ...createForm, phone: e.target.value })} /></div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Role</Label>
                  <Select value={createForm.role} onValueChange={v => setCreateForm({ ...createForm, role: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>{ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5"><Label className="text-xs">Department</Label><Input value={createForm.department} onChange={e => setCreateForm({ ...createForm, department: e.target.value })} /></div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Location</Label>
                  <Select value={createForm.location_id || '_none'} onValueChange={v => setCreateForm({ ...createForm, location_id: v === '_none' ? '' : v })}>
                    <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="_none">None</SelectItem>
                      {locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              {/* Admin Access Toggle */}
              <div className="flex items-center justify-between p-3 rounded-lg border border-amber-200 bg-amber-50/50">
                <div>
                  <Label className="text-xs font-medium">System Admin Access</Label>
                  <p className="text-[10px] text-muted-foreground">Full cross-campus visibility</p>
                </div>
                <Switch data-testid="create-admin-toggle" checked={createForm.is_admin || false} onCheckedChange={v => setCreateForm({ ...createForm, is_admin: v })} />
              </div>
              <label className="flex items-center gap-2 cursor-pointer text-sm">
                <input type="checkbox" className="accent-primary" checked={createForm.also_create_member} onChange={e => setCreateForm({ ...createForm, also_create_member: e.target.checked })} />
                Also add to People directory (recommended)
              </label>
              <div className="flex gap-3">
                <Button variant="outline" className="flex-1" onClick={() => setShowCreateUser(false)}>Cancel</Button>
                <Button className="flex-1 gap-2" onClick={handleCreateUser} data-testid="confirm-create-user"><Plus size={14} /> Create User</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ===== IMPORT USERS DIALOG ===== */}
      <Dialog open={showImport} onOpenChange={o => { setShowImport(o); if (!o) { setImportResult(null); setImportJson(''); } }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Import Users</DialogTitle>
            <DialogDescription>Upload a CSV or paste JSON array. Each row: name, email, role, phone, department, location_id</DialogDescription>
          </DialogHeader>
          {importResult ? (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-3 text-center">
                <div className="p-3 bg-green-50 rounded-lg border border-green-200"><p className="text-2xl font-bold text-green-700">{importResult.created}</p><p className="text-xs text-muted-foreground">Created</p></div>
                <div className="p-3 bg-amber-50 rounded-lg border border-amber-200"><p className="text-2xl font-bold text-amber-700">{importResult.skipped}</p><p className="text-xs text-muted-foreground">Skipped</p></div>
                <div className="p-3 bg-red-50 rounded-lg border border-red-200"><p className="text-2xl font-bold text-red-700">{importResult.errors?.length || 0}</p><p className="text-xs text-muted-foreground">Errors</p></div>
              </div>
              {importResult.errors?.length > 0 && <div className="text-xs text-red-600 bg-red-50 rounded-lg p-3 space-y-1">{importResult.errors.map((e, i) => <p key={i}>{e}</p>)}</div>}
              <Button className="w-full" onClick={() => setShowImport(false)}>Done</Button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <Label className="text-xs">JSON / CSV Data</Label>
                  <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" onClick={() => importFileRef.current?.click()}><Upload size={11} /> Upload CSV/JSON</Button>
                  <input ref={importFileRef} type="file" className="hidden" accept=".csv,.json" onChange={handleImportFile} />
                </div>
                <Textarea rows={6} placeholder={'[{"name":"Jane Doe","email":"jane@example.com","role":"Staff","phone":"+256..."},...]'}
                  className="text-xs font-mono" value={importJson} onChange={e => setImportJson(e.target.value)} data-testid="import-json-input" />
              </div>
              <div className="text-xs text-muted-foreground bg-muted/50 rounded-lg p-3 space-y-1">
                <p className="font-medium">CSV column headers:</p>
                <p className="font-mono">name, email, role, phone, department, location_id</p>
                <p className="mt-1">All imported users are also added to the People directory.</p>
              </div>
              <div className="flex gap-3">
                <Button variant="outline" className="flex-1" onClick={() => setShowImport(false)}>Cancel</Button>
                <Button className="flex-1 gap-2" onClick={handleImportUsers} disabled={importLoading || !importJson.trim()} data-testid="import-users-btn">
                  <Download size={14} /> {importLoading ? 'Importing...' : 'Import Users'}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ===== FULL PROFILE EDIT DIALOG ===== */}
      <Dialog open={showEdit} onOpenChange={setShowEdit}>
        <DialogContent className="max-w-2xl max-h-[92vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit Profile: {selectedUser?.name}</DialogTitle>
            <DialogDescription>Full member profile, account settings, and documents</DialogDescription>
          </DialogHeader>

          <Tabs defaultValue="profile" className="mt-2">
            <TabsList className="w-full grid grid-cols-4">
              <TabsTrigger value="profile">Profile</TabsTrigger>
              <TabsTrigger value="account">Account</TabsTrigger>
              <TabsTrigger value="flags">Flags</TabsTrigger>
              <TabsTrigger value="documents">Documents</TabsTrigger>
            </TabsList>

            {/* ---- Profile Tab ---- */}
            <TabsContent value="profile" className="space-y-4 mt-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2"><Label>Full Name *</Label><Input data-testid="edit-name" value={editForm.name || ''} onChange={e => setEditForm({...editForm, name: e.target.value})} /></div>
                <div className="space-y-2"><Label>Email</Label><Input data-testid="edit-email" type="email" value={editForm.email || ''} onChange={e => setEditForm({...editForm, email: e.target.value})} /></div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2"><Label>Phone</Label><Input value={editForm.phone || ''} onChange={e => setEditForm({...editForm, phone: e.target.value})} /></div>
                <div className="space-y-2"><Label>Date of Birth</Label><Input type="date" value={editForm.date_of_birth || ''} onChange={e => setEditForm({...editForm, date_of_birth: e.target.value})} /></div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2"><Label>Gender</Label>
                  <Select value={editForm.gender || ''} onValueChange={v => setEditForm({...editForm, gender: v})}>
                    <SelectTrigger><SelectValue placeholder="Select gender" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Male">Male</SelectItem>
                      <SelectItem value="Female">Female</SelectItem>
                      <SelectItem value="Other">Other</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2"><Label>National ID / Passport No.</Label><Input value={editForm.national_id || ''} onChange={e => setEditForm({...editForm, national_id: e.target.value})} /></div>
              </div>
              <div className="space-y-2"><Label>Address</Label><Textarea rows={2} value={editForm.address || ''} onChange={e => setEditForm({...editForm, address: e.target.value})} /></div>
              <div className="space-y-2"><Label>Emergency Contact</Label><Input value={editForm.emergency_contact || ''} onChange={e => setEditForm({...editForm, emergency_contact: e.target.value})} /></div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2"><Label>Group</Label>
                  <Select value={editForm.group || ''} onValueChange={v => setEditForm({...editForm, group: v})}>
                    <SelectTrigger><SelectValue placeholder="Select group" /></SelectTrigger>
                    <SelectContent>{GROUPS.map(g => <SelectItem key={g} value={g}>{g}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-2"><Label>Programme</Label><Input value={editForm.program || ''} onChange={e => setEditForm({...editForm, program: e.target.value})} /></div>
              </div>
              <div className="flex gap-3 pt-2">
                <Button variant="outline" className="flex-1" onClick={() => setShowEdit(false)}>Cancel</Button>
                <Button className="flex-1" data-testid="save-profile-btn" onClick={saveEdit} disabled={saving}>{saving ? 'Saving...' : 'Save Profile'}</Button>
              </div>
            </TabsContent>

            {/* ---- Account Tab ---- */}
            <TabsContent value="account" className="space-y-4 mt-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2"><Label>Primary Role</Label>
                  <Select value={editForm.role === 'admin' || editForm.role === 'system_admin' ? 'Staff' : (editForm.role || 'Member')} onValueChange={v => setEditForm({...editForm, role: v})}>
                    <SelectTrigger data-testid="edit-role-select"><SelectValue /></SelectTrigger>
                    <SelectContent>{ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-2"><Label>Status</Label>
                  <Select value={editForm.status || 'active'} onValueChange={v => setEditForm({...editForm, status: v})}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="active">Active</SelectItem>
                      <SelectItem value="inactive">Inactive</SelectItem>
                      <SelectItem value="pending">Pending</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="flex items-center justify-between p-3 rounded-lg border border-amber-200 bg-amber-50/50">
                <div>
                  <Label className="text-sm font-medium">System Admin Access</Label>
                  <p className="text-xs text-muted-foreground mt-0.5">Grants full cross-campus visibility and admin privileges</p>
                </div>
                <Switch data-testid="admin-access-toggle" checked={editForm.is_admin === true} onCheckedChange={v => setEditForm({...editForm, is_admin: v})} />
              </div>
              {/* Multi-Location Assignment */}
              <div className="space-y-2">
                <Label>Campuses / Locations</Label>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {(editForm.location_ids || []).map(lid => {
                    const loc = locations.find(l => l.id === lid);
                    return loc ? <Badge key={lid} variant="secondary" className="gap-1 text-xs cursor-pointer" onClick={() => { const nl = editForm.location_ids.filter(l => l !== lid); setEditForm({...editForm, location_ids: nl, location_id: nl[0] || ''}); }}>{loc.name} <X size={10} /></Badge> : null;
                  })}
                </div>
                <Select value="" onValueChange={v => { if (v && !(editForm.location_ids || []).includes(v)) { const nl = [...(editForm.location_ids || []), v]; setEditForm({...editForm, location_ids: nl, location_id: nl[0] || v}); } }}>
                  <SelectTrigger data-testid="edit-location-select"><SelectValue placeholder="Add campus..." /></SelectTrigger>
                  <SelectContent>{locations.filter(l => !(editForm.location_ids || []).includes(l.id)).map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2"><Label>Department</Label>
                  {(() => { const pl = locations.find(l => l.id === (editForm.location_ids || [])[0] || l.id === editForm.location_id); const depts = pl?.departments || [];
                    return depts.length > 0 ? (<Select value={editForm.department || ''} onValueChange={v => setEditForm({...editForm, department: v})}><SelectTrigger><SelectValue placeholder="Select dept" /></SelectTrigger><SelectContent>{depts.map(d => <SelectItem key={d} value={d}>{d}</SelectItem>)}<SelectItem value="_other">Other...</SelectItem></SelectContent></Select>) : (<Input value={editForm.department || ''} onChange={e => setEditForm({...editForm, department: e.target.value})} placeholder="Department" />);
                  })()}
                </div>
                <div className="space-y-2"><Label>PIN Code</Label><Input maxLength={6} placeholder="4-6 digit PIN" value={editForm.pin || ''} onChange={e => setEditForm({...editForm, pin: e.target.value})} /></div>
              </div>
              <div className="space-y-2">
                <Label>Title <span className="text-xs text-muted-foreground">(auto-suggested, editable)</span></Label>
                <Input data-testid="edit-title-input" value={editForm.title || ''} onChange={e => setEditForm({...editForm, title: e.target.value})} placeholder={`e.g. ${editForm.role || 'Staff'} of ${locations.find(l => l.id === (editForm.location_ids || [])[0])?.name || 'Location'}`} />
              </div>
              <div className="space-y-2"><Label>Notes</Label><Textarea rows={2} value={editForm.notes || ''} onChange={e => setEditForm({...editForm, notes: e.target.value})} /></div>
              <div className="flex gap-3 pt-2">
                <Button variant="outline" className="flex-1" onClick={() => setShowEdit(false)}>Cancel</Button>
                <Button className="flex-1" onClick={saveEdit} disabled={saving}>{saving ? 'Saving...' : 'Save Account'}</Button>
              </div>
            </TabsContent>

            {/* ---- Flags Tab ---- */}
            <TabsContent value="flags" className="space-y-4 mt-4">
              <div className="space-y-3 p-3 rounded-lg border border-border">
                <p className="text-sm font-medium">Role Flags</p>
                <div className="flex items-center justify-between"><Label className="text-sm">Is Parent</Label><Switch data-testid="flag-is_parent" checked={editForm.is_parent || false} onCheckedChange={v => setEditForm({...editForm, is_parent: v})} /></div>
                <div className="flex items-center justify-between"><Label className="text-sm">Is Customer</Label><Switch checked={editForm.is_customer || false} onCheckedChange={v => setEditForm({...editForm, is_customer: v})} /></div>
                <div className="flex items-center justify-between"><Label className="text-sm">Is Donor</Label><Switch checked={editForm.is_donor || false} onCheckedChange={v => setEditForm({...editForm, is_donor: v})} /></div>
              </div>
              <div className="flex gap-3 pt-2">
                <Button variant="outline" className="flex-1" onClick={() => setShowEdit(false)}>Cancel</Button>
                <Button className="flex-1" onClick={saveEdit} disabled={saving}>{saving ? 'Saving...' : 'Save Flags'}</Button>
              </div>
            </TabsContent>

            {/* ---- Documents Tab ---- */}
            <TabsContent value="documents" className="space-y-4 mt-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">Documents on File</p>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setShowScanner(true)}>
                    <Bluetooth size={13} /> Scanner
                  </Button>
                  <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setShowDocRequest(true)}>
                    <Plus size={13} /> Request Doc
                  </Button>
                  <div className="relative">
                    <Button size="sm" className="gap-1.5" onClick={() => fileInputRef.current?.click()} disabled={uploadingDoc}>
                      <Upload size={13} /> {uploadingDoc ? 'Uploading...' : 'Upload'}
                    </Button>
                    <input ref={fileInputRef} type="file" className="hidden" accept=".jpg,.jpeg,.png,.pdf,.doc,.docx" onChange={handleDocUpload} />
                  </div>
                </div>
              </div>

              {/* Upload type selector */}
              <div className="flex items-center gap-2">
                <Label className="text-xs whitespace-nowrap">Upload as:</Label>
                <Select value={uploadDocType} onValueChange={setUploadDocType}>
                  <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>{Object.entries(ID_TYPE_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
                </Select>
              </div>

              {/* Pending requests */}
              {docRequests.filter(r => r.status === 'pending').length > 0 && (
                <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-3 space-y-2">
                  <p className="text-xs font-medium text-yellow-800 flex items-center gap-1"><AlertCircle size={12} /> Pending Requests</p>
                  {docRequests.filter(r => r.status === 'pending').map(req => (
                    <div key={req.id} className="flex items-center justify-between text-xs">
                      <span className="text-yellow-900">{ID_TYPE_LABELS[req.doc_type] || req.doc_type} {req.message && `— ${req.message}`}</span>
                      <Button size="sm" variant="ghost" className="h-6 text-xs text-red-600" onClick={() => cancelRequest(req.id)}>Cancel</Button>
                    </div>
                  ))}
                </div>
              )}

              {/* Documents list */}
              {docsLoading ? (
                <div className="h-24 animate-pulse bg-muted rounded-lg" />
              ) : memberDocs.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground text-sm"><FileText size={28} className="mx-auto mb-2 opacity-30" /><p>No documents uploaded yet</p></div>
              ) : (
                <div className="space-y-2">
                  {memberDocs.map(doc => (
                    <div key={doc.id} data-testid={`doc-${doc.id}`} className="flex items-center justify-between p-3 rounded-lg border border-border bg-card">
                      <div className="flex items-center gap-2.5">
                        <div className="p-1.5 rounded-md bg-primary/10"><FileText size={14} className="text-primary" /></div>
                        <div>
                          <p className="text-sm font-medium">{ID_TYPE_LABELS[doc.doc_type] || doc.label}</p>
                          <p className="text-xs text-muted-foreground">{doc.original_filename} · {new Date(doc.created_at).toLocaleDateString()}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <a href={documentsApi.fileUrl(doc.id)} target="_blank" rel="noopener noreferrer" className="p-1.5 rounded-md hover:bg-accent" title="View/Download">
                          <Download size={13} />
                        </a>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive hover:text-destructive" onClick={() => deleteDoc(doc.id)}><X size={13} /></Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>

      {/* ===== RESET PASSWORD DIALOG ===== */}
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

      {/* ===== BULK ACTION DIALOG ===== */}
      <Dialog open={showBulk} onOpenChange={setShowBulk}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Bulk Action ({selectedIds.size} users)</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Action</Label>
              <Select value={bulkAction} onValueChange={setBulkAction}><SelectTrigger><SelectValue placeholder="Select action" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="role">Change Role</SelectItem>
                  <SelectItem value="activate">Activate</SelectItem>
                  <SelectItem value="deactivate">Deactivate</SelectItem>
                  <SelectItem value="delete">Delete</SelectItem>
                </SelectContent>
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

      {/* ===== BADGE PRINT DIALOG ===== */}
      <Dialog open={showBadge} onOpenChange={setShowBadge}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Print Badge — {selectedUser?.name}</DialogTitle></DialogHeader>
          {selectedUser && <BadgePrintView user={selectedUser} onClose={() => setShowBadge(false)} />}
        </DialogContent>
      </Dialog>

      {/* ===== DOCUMENT REQUEST DIALOG ===== */}
      <Dialog open={showDocRequest} onOpenChange={setShowDocRequest}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Request Document</DialogTitle><DialogDescription>Request a specific document from {selectedUser?.name}</DialogDescription></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Document Type</Label>
              <Select value={docRequestForm.doc_type} onValueChange={v => setDocRequestForm({...docRequestForm, doc_type: v})}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{Object.entries(ID_TYPE_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-2"><Label>Message (optional)</Label>
              <Textarea rows={2} placeholder="e.g. Required for annual membership renewal" value={docRequestForm.message} onChange={e => setDocRequestForm({...docRequestForm, message: e.target.value})} />
            </div>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => setShowDocRequest(false)}>Cancel</Button>
              <Button className="flex-1" onClick={submitDocRequest} disabled={saving}>{saving ? 'Sending...' : 'Send Request'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* ===== SCANNER DIALOG ===== */}
      <Dialog open={showScanner} onOpenChange={setShowScanner}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Document Scanner</DialogTitle><DialogDescription>Connect a networked or Bluetooth scanner</DialogDescription></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="grid grid-cols-3 gap-3">
              <button
                onClick={tryConnectScanner}
                className="flex flex-col items-center gap-2 p-4 rounded-xl border border-border hover:bg-accent transition-colors text-sm font-medium"
                data-testid="connect-bluetooth-scanner"
              >
                <Bluetooth size={22} className="text-blue-500" />
                Bluetooth
              </button>
              <button
                onClick={tryConnectScanner}
                className="flex flex-col items-center gap-2 p-4 rounded-xl border border-border hover:bg-accent transition-colors text-sm font-medium"
              >
                <Monitor size={22} className="text-green-500" />
                USB/Serial
              </button>
              <button
                onClick={() => { setShowScanner(false); fileInputRef.current?.click(); }}
                className="flex flex-col items-center gap-2 p-4 rounded-xl border border-border hover:bg-accent transition-colors text-sm font-medium"
              >
                <Upload size={22} className="text-primary" />
                Upload File
              </button>
            </div>

            {scannerStatus === 'connecting' && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <div className="h-4 w-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                Connecting to scanner...
              </div>
            )}
            {scannerStatus.startsWith('connected:') && (
              <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 p-3 rounded-lg">
                <Wifi size={14} /> Connected: {scannerStatus.replace('connected:', '')}
              </div>
            )}
            {scannerStatus === 'unsupported' && (
              <div className="flex items-start gap-2 text-sm text-amber-700 bg-amber-50 p-3 rounded-lg">
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                <div>
                  <p className="font-medium">Browser not supported</p>
                  <p className="text-xs mt-0.5">Web Bluetooth/Serial requires Chrome or Edge on Desktop. Please scan with your device and upload the file manually.</p>
                </div>
              </div>
            )}

            <p className="text-xs text-muted-foreground">
              After connecting, trigger a scan from your physical scanner. The scanned document will appear in the scanner software — save it and use "Upload File" to attach it to this member's profile.
            </p>
            <Button variant="outline" className="w-full" onClick={() => setShowScanner(false)}>Close</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}


// ===== BADGE PRINT COMPONENT =====
function BadgePrintView({ user, onClose }) {
  const badgeRef = useRef(null);
  const [btStatus, setBtStatus] = useState('idle');
  const [btDevice, setBtDevice] = useState(null);
  const [showZpl, setShowZpl] = useState(false);

  const initials = user.name ? user.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase() : 'XX';
  const memberId = user.id?.slice(-8).toUpperCase() || 'N/A';

  const printBadge = () => {
    const printContents = badgeRef.current?.innerHTML;
    const win = window.open('', '_blank', 'width=400,height=300');
    win.document.write(`
      <html>
        <head>
          <title>Badge — ${user.name}</title>
          <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: Arial, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; background: #fff; }
            .badge { width: 3.375in; height: 2.125in; border: 2px solid #1a1a2e; border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; background: #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.15); }
            @media print { body { height: auto; } .badge { box-shadow: none; } }
          </style>
        </head>
        <body>${printContents}</body>
      </html>
    `);
    win.document.close();
    setTimeout(() => { win.focus(); win.print(); win.close(); }, 300);
  };

  const generateZpl = () => {
    const nameLines = (user.name || '').split(' ');
    const firstName = nameLines[0] || '';
    const lastName = nameLines.slice(1).join(' ') || '';
    return `^XA
^FO20,20^A0N,28,28^FD58:12 Global Connect^FS
^FO20,55^A0N,18,18^FDCENTRAL SYSTEM^FS
^FO20,90^A0N,36,36^FD${firstName}^FS
^FO20,130^A0N,36,36^FD${lastName}^FS
^FO20,175^A0N,22,22^FD${(user.role || '').toUpperCase()}^FS
^FO20,205^A0N,18,18^FDID: ${memberId}^FS
^FO400,80^BQN,2,4^FDQA,${user.id || 'N/A'}^FS
^FO20,230^GB570,2,2^FS
^FO20,238^A0N,16,16^FD58:12 Global · ${new Date().getFullYear()}^FS
^XZ`;
  };

  const connectBluetooth = async () => {
    if (!navigator.bluetooth) {
      toast.error('Web Bluetooth is not supported in this browser. Use Chrome or Edge on desktop.');
      return;
    }
    setBtStatus('connecting');
    try {
      const device = await navigator.bluetooth.requestDevice({
        acceptAllDevices: true,
        optionalServices: [
          '000018f0-0000-1000-8000-00805f9b34fb',
          '49535343-fe7d-4ae5-8fa9-9fafd205e455',
          '6e400001-b5a3-f393-e0a9-e50e24dcca9e',
        ],
      });
      setBtDevice(device);
      setBtStatus('connected');
      toast.success(`Connected: ${device.name || 'Bluetooth Printer'}.`);
    } catch (err) {
      if (err.name !== 'NotFoundError') {
        setBtStatus('error');
        toast.error(`Bluetooth error: ${err.message}`);
      } else {
        setBtStatus('idle');
      }
    }
  };

  const zpl = generateZpl();

  return (
    <div className="space-y-4">
      <div ref={badgeRef}>
        <div style={{ width: '324px', height: '204px', border: '2px solid #1a1a2e', borderRadius: '12px', overflow: 'hidden', display: 'flex', flexDirection: 'column', background: '#fff', boxShadow: '0 2px 8px rgba(0,0,0,0.15)', margin: '0 auto' }}>
          <div style={{ background: '#1a1a2e', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <img src="https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1" alt="58:12 Global"
              style={{ height: '18px', filter: 'brightness(0) invert(1)' }} />
            <span style={{ color: '#fbbf24', fontSize: '8px', fontWeight: 700, letterSpacing: '1px', marginLeft: 'auto' }}>STAFF</span>
          </div>
          <div style={{ flex: 1, padding: '8px 12px', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
              <div style={{ width: '46px', height: '46px', borderRadius: '50%', background: '#e8e8f0', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '16px', fontWeight: 700, color: '#1a1a2e', border: '2px solid #1a1a2e' }}>{initials}</div>
              <svg id="qr-staff" style={{ width: '48px', height: '48px' }} />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '14px', fontWeight: 700, color: '#1a1a2e', lineHeight: 1.2 }}>{user.name}</div>
              <div style={{ fontSize: '10px', color: '#555', marginTop: '2px', textTransform: 'uppercase', letterSpacing: '0.8px' }}>{user.role}</div>
              {user.department && <div style={{ fontSize: '9px', color: '#888', marginTop: '2px' }}>{user.department}</div>}
              <div style={{ fontSize: '9px', color: '#aaa', marginTop: '4px' }}>ID: {memberId}</div>
            </div>
          </div>
          <div style={{ background: '#f0f0f0', padding: '4px 12px', textAlign: 'center', fontSize: '7px', color: '#777', borderTop: '1px solid #ddd' }}>
            58:12 Global Connect · {user.location_name || 'Headquarters'} · {new Date().getFullYear()}
          </div>
        </div>
      </div>

      <p className="text-xs text-muted-foreground text-center">Badge preview (3.375" × 2.125" — CR80 card size)</p>

      {/* Printer Options */}
      <div className="grid grid-cols-3 gap-2">
        <Button className="gap-1.5 text-xs" onClick={printBadge} data-testid="print-badge-btn">
          <Printer size={13} /> Browser Print
        </Button>
        <Button variant="outline" className="gap-1.5 text-xs"
          onClick={connectBluetooth}
          disabled={btStatus === 'connecting'}>
          <Bluetooth size={13} className={btStatus === 'connected' ? 'text-blue-500' : ''} />
          {btStatus === 'connecting' ? 'Connecting...' : btStatus === 'connected' ? `${btDevice?.name?.slice(0,10) || 'Connected'}` : 'Bluetooth'}
        </Button>
        <Button variant="outline" className="gap-1.5 text-xs" onClick={() => setShowZpl(!showZpl)}>
          <Monitor size={13} /> ZPL Code
        </Button>
      </div>

      {showZpl && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium">ZPL for Zebra Printers</p>
            <Button size="sm" variant="ghost" className="h-6 text-xs gap-1"
              onClick={() => { navigator.clipboard.writeText(zpl); toast.success('ZPL copied to clipboard'); }}>
              Copy
            </Button>
          </div>
          <pre className="text-[10px] bg-muted p-3 rounded-lg overflow-x-auto text-muted-foreground font-mono leading-relaxed">{zpl}</pre>
          <p className="text-xs text-muted-foreground">Send this ZPL code to your networked Zebra printer via its web interface or Zebra Designer software.</p>
        </div>
      )}

      <Button variant="ghost" className="w-full text-sm" onClick={onClose}>Close</Button>
    </div>
  );
}
