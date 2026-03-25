import React, { useState, useEffect, useCallback } from 'react';
import { Search, Plus, Users, Heart, Baby, UserPlus, Filter, Eye, Trash2, Download, Upload, Award, FileUp, Phone, Mail, RefreshCw, ChevronDown, CheckSquare } from 'lucide-react';
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
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from '../components/ui/dropdown-menu';
import { Checkbox } from '../components/ui/checkbox';
import { membersApi, checkinsApi, approvalsApi, badgesApi, exportApi, importApi, locationsApi, csvUploadApi, familiesApi, childrenApi, guestsApi, adminApi } from '../services/api';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { MOCK_GROUPS, MOCK_ROLES } from '../mock';
import { toast } from 'sonner';

const initials = (name) => (name || '?').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();

// Shared form for members/staff (consolidate duplicated logic)
function MemberForm({ data, onChange, locations, showDepartment }) {
  const departmentOptions = (() => {
    if (!data.location_id) return [];
    const loc = locations.find(l => l.id === data.location_id);
    if (!loc) return [];
    const deps = loc.departments || [];
    if (deps.length === 0 && loc.name) return [loc.name];
    return deps;
  })();

  const isNonDeptRole = ['Parent', 'Customer', 'Guest', 'Child'].includes(data.role);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5"><Label className="text-xs">Name *</Label><Input value={data.name} onChange={e => onChange({ ...data, name: e.target.value })} required data-testid="member-name-input" /></div>
        <div className="space-y-1.5"><Label className="text-xs">Email</Label><Input type="email" value={data.email} onChange={e => onChange({ ...data, email: e.target.value })} data-testid="member-email-input" /></div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5"><Label className="text-xs">Phone</Label><Input value={data.phone} onChange={e => onChange({ ...data, phone: e.target.value })} data-testid="member-phone-input" /></div>
        <div className="space-y-1.5"><Label className="text-xs">National ID</Label><Input value={data.national_id} onChange={e => onChange({ ...data, national_id: e.target.value })} /></div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5"><Label className="text-xs">Gender *</Label>
          <Select value={data.gender} onValueChange={v => onChange({ ...data, gender: v })}>
            <SelectTrigger data-testid="member-gender-select"><SelectValue placeholder="Select" /></SelectTrigger>
            <SelectContent><SelectItem value="male">Male</SelectItem><SelectItem value="female">Female</SelectItem></SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5"><Label className="text-xs">Role</Label>
          <Select value={data.role} onValueChange={v => onChange({ ...data, role: v })}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>{MOCK_ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
          </Select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5"><Label className="text-xs">Group</Label>
          <Select value={data.group} onValueChange={v => onChange({ ...data, group: v })}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>{MOCK_GROUPS.map(g => <SelectItem key={g} value={g}>{g}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5"><Label className="text-xs">Location</Label>
          <Select value={data.location_id || ''} onValueChange={v => onChange({ ...data, location_id: v, department: '' })}>
            <SelectTrigger><SelectValue placeholder="Select location" /></SelectTrigger>
            <SelectContent>{locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
          </Select>
        </div>
      </div>
      {showDepartment && !isNonDeptRole && departmentOptions.length > 0 && (
        <div className="space-y-1.5"><Label className="text-xs">Department</Label>
          <Select value={data.department || ''} onValueChange={v => onChange({ ...data, department: v })}>
            <SelectTrigger><SelectValue placeholder="Select department" /></SelectTrigger>
            <SelectContent>{departmentOptions.map(d => <SelectItem key={d} value={d}>{d}</SelectItem>)}</SelectContent>
          </Select>
        </div>
      )}
      {isNonDeptRole && (
        <div className="space-y-1.5"><Label className="text-xs">Programme</Label>
          <Input placeholder="e.g. Children's Church" value={data.program || ''} onChange={e => onChange({ ...data, program: e.target.value })} />
        </div>
      )}
      <div className="space-y-1.5"><Label className="text-xs">Date of Birth</Label><Input type="date" value={data.date_of_birth || ''} onChange={e => onChange({ ...data, date_of_birth: e.target.value })} /></div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5"><Label className="text-xs">PIN Code</Label><Input placeholder="4-digit PIN" maxLength={10} value={data.pin || ''} onChange={e => onChange({ ...data, pin: e.target.value })} /></div>
        <div className="space-y-1.5 flex flex-col justify-end gap-2">
          <div className="flex items-center gap-2"><Switch checked={data.is_parent || false} onCheckedChange={v => onChange({ ...data, is_parent: v })} /><Label className="text-xs">Parent</Label></div>
          <div className="flex items-center gap-2"><Switch checked={data.is_donor || false} onCheckedChange={v => onChange({ ...data, is_donor: v })} /><Label className="text-xs">Donor</Label></div>
        </div>
      </div>
      <div className="space-y-1.5"><Label className="text-xs">Notes</Label><Textarea rows={2} value={data.notes || ''} onChange={e => onChange({ ...data, notes: e.target.value })} /></div>
    </div>
  );
}

export default function UnifiedPeoplePage() {
  const { user } = useAuth();
  const userRole = user?.role || '';
  const isManager = ['admin', 'system_admin', 'Executive Director', 'Director', 'Manager'].includes(userRole);
  const isCoordinator = isManager || userRole === 'Coordinator';

  // Members state
  const [members, setMembers] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterGroup, setFilterGroup] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [selectedMember, setSelectedMember] = useState(null);
  const [memberDetail, setMemberDetail] = useState(null);
  const [newMember, setNewMember] = useState({ name: '', email: '', phone: '', national_id: '', role: 'Staff', group: 'Youth', gender: 'male', date_of_birth: '', address: '', notes: '', location_id: '', department: '', program: '' });
  const [savingMember, setSavingMember] = useState(false);
  const [pendingMembers, setPendingMembers] = useState([]);
  const [badges, setBadges] = useState([]);

  // Import state
  const [showBulkImport, setShowBulkImport] = useState(false);
  const [bulkData, setBulkData] = useState('');
  const [importLoading, setImportLoading] = useState(false);
  const [showChildImport, setShowChildImport] = useState(false);
  const [childCsvData, setChildCsvData] = useState('');
  const [showStaffImport, setShowStaffImport] = useState(false);
  const [staffCsvData, setStaffCsvData] = useState('');
  const [csvFile, setCsvFile] = useState(null);
  const [childCsvFile, setChildCsvFile] = useState(null);
  const [staffCsvFile, setStaffCsvFile] = useState(null);

  // Bulk operations
  const [selectedMemberIds, setSelectedMemberIds] = useState(new Set());
  const [showBulkAction, setShowBulkAction] = useState(false);
  const [bulkActionType, setBulkActionType] = useState('');
  const [bulkRole, setBulkRole] = useState('');

  // Track default tab when opening member view
  const [defaultMemberTab, setDefaultMemberTab] = useState('info');
  const [editMember, setEditMember] = useState(null);
  const [editMemberForm, setEditMemberForm] = useState({});
  const [savingEdit, setSavingEdit] = useState(false);

  // Inline edit for children
  const [editChild, setEditChild] = useState(null);
  const [editChildForm, setEditChildForm] = useState({});
  const [savingChild, setSavingChild] = useState(false);

  // Documents
  const [memberDocuments, setMemberDocuments] = useState([]);
  const [docFile, setDocFile] = useState(null);
  const [docType, setDocType] = useState('id_scan');
  const [docLabel, setDocLabel] = useState('');
  const [docUploading, setDocUploading] = useState(false);

  // Families
  const [families, setFamilies] = useState([]);
  const [children, setChildren] = useState([]);
  const [guests, setGuests] = useState([]);
  const [showFamily, setShowFamily] = useState(false);
  const [showChild, setShowChild] = useState(false);
  const [showGuest, setShowGuest] = useState(false);
  const [familyForm, setFamilyForm] = useState({ family_name: '', primary_contact_name: '', primary_contact_email: '', primary_contact_phone: '', address: '' });
  const [childForm, setChildForm] = useState({ name: '', date_of_birth: '', gender: '', family_id: '', class_group: '', medical_notes: '', allergies: '' });
  const [guestForm, setGuestForm] = useState({ name: '', email: '', phone: '', visit_date: new Date().toISOString().split('T')[0], referred_by: '', address: '', notes: '' });

  // Edit family
  const [editFamily, setEditFamily] = useState(null);
  const [editFamilyForm, setEditFamilyForm] = useState({});
  const [savingFamily, setSavingFamily] = useState(false);

  const [allLocations, setAllLocations] = useState([]);
  const [activeTab, setActiveTab] = useState('members');
  const [saving, setSaving] = useState(false);

  const fetchMembers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await membersApi.list({ search: search || undefined, group: filterGroup !== 'all' ? filterGroup : undefined, status: filterStatus !== 'all' ? filterStatus : undefined, limit: 100 });
      setMembers(res.data.members || res.data || []);
      setTotal(res.data.total || (res.data.members || res.data || []).length);
    } catch { toast.error('Failed to load members'); }
    finally { setLoading(false); }
  }, [search, filterGroup, filterStatus]);

  const fetchPeople = useCallback(async () => {
    try {
      const [famRes, chdRes, gstRes] = await Promise.all([familiesApi.list(), childrenApi.list(), guestsApi.list()]);
      setFamilies(famRes.data || []);
      setChildren(chdRes.data || []);
      setGuests(gstRes.data || []);
    } catch {}
  }, []);

  useEffect(() => {
    const load = async () => {
      await Promise.all([fetchMembers(), fetchPeople()]);
      try {
        const [locsRes, pendRes, badgeRes] = await Promise.all([locationsApi.list(), approvalsApi.pending().catch(() => ({ data: [] })), badgesApi.list().catch(() => ({ data: [] }))]);
        setAllLocations(locsRes.data || []);
        const pendData = pendRes.data;
        setPendingMembers(Array.isArray(pendData) ? pendData : pendData?.members || []);
        setBadges(badgeRes.data || []);
      } catch {}
    };
    load();
  }, [fetchMembers, fetchPeople]);

  // Bulk selection helpers
  const toggleMemberSelect = (id) => setSelectedMemberIds(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const selectAllMembers = () => setSelectedMemberIds(prev => prev.size === members.length ? new Set() : new Set(members.map(m => m.id)));

  const executeBulk = async () => {
    const ids = [...selectedMemberIds];
    if (!ids.length) return;
    setSaving(true);
    try {
      if (bulkActionType === 'delete') {
        await adminApi.bulkDeleteMembers(ids);
        toast.success(`Deleted ${ids.length} members`);
        fetchMembers();
      } else if (bulkActionType === 'role' && bulkRole) {
        await adminApi.bulkUpdateMembers(ids, { role: bulkRole });
        toast.success(`Role updated for ${ids.length} members`);
        fetchMembers();
      } else if (bulkActionType === 'activate') {
        await adminApi.bulkUpdateMembers(ids, { status: 'active' });
        toast.success(`Activated ${ids.length} members`);
        fetchMembers();
      } else if (bulkActionType === 'deactivate') {
        await adminApi.bulkUpdateMembers(ids, { status: 'inactive' });
        toast.success(`Deactivated ${ids.length} members`);
        fetchMembers();
      }
      setSelectedMemberIds(new Set()); setShowBulkAction(false);
    } catch (err) { toast.error(err.response?.data?.detail || 'Bulk action failed'); }
    finally { setSaving(false); }
  };

  // Edit member
  const openEditMember = (m, e) => {
    if (e) e.stopPropagation();
    setEditMember(m);
    setEditMemberForm({ name: m.name || '', email: m.email || '', phone: m.phone || '', role: m.role || 'Member', group: m.group || '', gender: m.gender || '', date_of_birth: m.date_of_birth || '', national_id: m.national_id || '', address: m.address || '', department: m.department || '', program: m.program || '', pin: m.pin || '', notes: m.notes || '', status: m.status || 'active', location_id: m.location_id || '', is_parent: m.is_parent || false, is_donor: m.is_donor || false });
  };
  const saveEditMember = async () => {
    if (!editMember) return;
    setSavingEdit(true);
    try {
      const res = await membersApi.update(editMember.id, editMemberForm);
      setMembers(prev => prev.map(m => m.id === editMember.id ? { ...m, ...res.data } : m));
      // Also update in selectedMember view if open
      if (selectedMember?.id === editMember.id) setMemberDetail(prev => ({ ...prev, ...res.data }));
      setEditMember(null);
      toast.success('Profile saved');
    } catch (err) { toast.error(err.response?.data?.detail || 'Save failed'); }
    finally { setSavingEdit(false); }
  };

  // Edit child
  const openEditChild = (c, e) => {
    if (e) e.stopPropagation();
    setEditChild(c);
    setEditChildForm({ name: c.name || '', date_of_birth: c.date_of_birth || '', gender: c.gender || '', family_id: c.family_id || '', class_group: c.class_group || '', medical_notes: c.medical_notes || '', allergies: c.allergies || '' });
  };
  const saveEditChild = async () => {
    if (!editChild) return;
    setSavingChild(true);
    try {
      await childrenApi.update(editChild.id, editChildForm);
      setChildren(prev => prev.map(c => c.id === editChild.id ? { ...c, ...editChildForm } : c));
      setEditChild(null);
      toast.success('Child profile saved');
    } catch (err) { toast.error(err.response?.data?.detail || 'Save failed'); }
    finally { setSavingChild(false); }
  };

  // Member CRUD
  const handleAddMember = async (e) => {
    e.preventDefault();
    setSavingMember(true);
    try {
      await membersApi.create(newMember);
      toast.success('Member added!');
      setShowAddDialog(false);
      setNewMember({ name: '', email: '', phone: '', national_id: '', role: 'Staff', group: 'Youth', gender: 'male', date_of_birth: '', address: '', notes: '', location_id: '', department: '', program: '' });
      fetchMembers();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to add member'); }
    finally { setSavingMember(false); }
  };

  const handleViewMember = async (member) => {
    setSelectedMember(member);
    // Pre-initialize edit form when viewing
    setEditMember(member);
    setEditMemberForm({ name: member.name || '', email: member.email || '', phone: member.phone || '', role: member.role || 'Member', group: member.group || '', gender: member.gender || '', date_of_birth: member.date_of_birth || '', national_id: member.national_id || '', address: member.address || '', department: member.department || '', program: member.program || '', pin: member.pin || '', notes: member.notes || '', status: member.status || 'active', location_id: member.location_id || '', is_parent: member.is_parent || false, is_donor: member.is_donor || false });
    try {
      const [detRes, docRes] = await Promise.all([membersApi.get(member.id), api.get(`/members/${member.id}/documents`).catch(() => ({ data: [] }))]);
      setMemberDetail(detRes.data);
      const detailed = detRes.data;
      setEditMemberForm({ name: detailed.name || '', email: detailed.email || '', phone: detailed.phone || '', role: detailed.role || 'Member', group: detailed.group || '', gender: detailed.gender || '', date_of_birth: detailed.date_of_birth || '', national_id: detailed.national_id || '', address: detailed.address || '', department: detailed.department || '', program: detailed.program || '', pin: detailed.pin || '', notes: detailed.notes || '', status: detailed.status || 'active', location_id: detailed.location_id || '', is_parent: detailed.is_parent || false, is_donor: detailed.is_donor || false });
      setMemberDocuments(docRes.data || []);
    } catch { setMemberDetail(member); }
  };

  const handleDocUpload = async () => {
    if (!docFile || !selectedMember) return;
    setDocUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', docFile);
      formData.append('doc_type', docType);
      formData.append('label', docLabel || docType.replace('_', ' '));
      await api.post(`/members/${selectedMember.id}/documents`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success('Document uploaded!');
      const docRes = await api.get(`/members/${selectedMember.id}/documents`);
      setMemberDocuments(docRes.data || []);
      setDocFile(null); setDocLabel('');
    } catch (err) { toast.error(err.response?.data?.detail || 'Upload failed'); }
    finally { setDocUploading(false); }
  };

  // Import handlers
  const handleBulkImport = async () => {
    setImportLoading(true);
    try {
      if (csvFile) {
        const fd = new FormData(); fd.append('file', csvFile);
        const res = await csvUploadApi.uploadMembers(fd);
        toast.success(`Imported ${res.data.imported} from CSV!`);
        if (res.data.errors?.length) toast.warning(`${res.data.errors.length} errors`);
      } else if (bulkData.trim()) {
        const lines = bulkData.trim().split('\n').map(l => { const [name, email, phone, group] = l.split(',').map(s => s.trim()); return { name, email, phone, group: group || 'Youth', role: 'Member' }; }).filter(m => m.name);
        await approvalsApi.bulkImport(lines);
        toast.success('Members imported!');
      }
      setShowBulkImport(false); setBulkData(''); setCsvFile(null); fetchMembers();
    } catch { toast.error('Import failed'); }
    finally { setImportLoading(false); }
  };

  const handleChildImport = async () => {
    setImportLoading(true);
    try {
      if (childCsvFile) {
        const fd = new FormData(); fd.append('file', childCsvFile);
        const res = await csvUploadApi.uploadChildrenParents(fd);
        toast.success(`Imported ${res.data.imported_children} children`);
      } else if (childCsvData.trim()) {
        const lines = childCsvData.trim().split('\n');
        const header = lines[0].toLowerCase().split(',').map(h => h.trim());
        const rows = lines.slice(1).map(line => { const vals = line.split(',').map(v => v.trim()); const row = {}; header.forEach((h, i) => { row[h] = vals[i] || ''; }); return row; }).filter(r => r.first_name);
        await importApi.childrenParents(rows);
        toast.success('Children imported!');
      }
      setShowChildImport(false); setChildCsvData(''); setChildCsvFile(null); fetchPeople();
    } catch { toast.error('Import failed'); }
    finally { setImportLoading(false); }
  };

  const handleStaffImport = async () => {
    setImportLoading(true);
    try {
      if (staffCsvFile) {
        const fd = new FormData(); fd.append('file', staffCsvFile);
        const res = await csvUploadApi.uploadStaff(fd);
        toast.success(`Imported ${res.data.imported} staff`);
      } else if (staffCsvData.trim()) {
        const lines = staffCsvData.trim().split('\n');
        const header = lines[0].toLowerCase().split(',').map(h => h.trim());
        const rows = lines.slice(1).map(line => { const vals = line.split(',').map(v => v.trim()); const row = {}; header.forEach((h, i) => { row[h] = vals[i] || ''; }); return row; }).filter(r => r.name);
        await importApi.staff(rows);
        toast.success('Staff imported!');
      }
      setShowStaffImport(false); setStaffCsvData(''); setStaffCsvFile(null); fetchMembers();
    } catch { toast.error('Import failed'); }
    finally { setImportLoading(false); }
  };

  // Family/Child/Guest handlers
  const handleAddFamily = async (e) => { e.preventDefault(); setSaving(true); try { await familiesApi.create(familyForm); toast.success('Family added!'); setShowFamily(false); setFamilyForm({ family_name: '', primary_contact_name: '', primary_contact_email: '', primary_contact_phone: '', address: '' }); fetchPeople(); } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); } finally { setSaving(false); } };
  const handleAddChild = async (e) => { e.preventDefault(); setSaving(true); try { await childrenApi.create(childForm); toast.success('Child added!'); setShowChild(false); setChildForm({ name: '', date_of_birth: '', gender: '', family_id: '', class_group: '', medical_notes: '', allergies: '' }); fetchPeople(); } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); } finally { setSaving(false); } };
  const handleAddGuest = async (e) => { e.preventDefault(); setSaving(true); try { await guestsApi.create(guestForm); toast.success('Guest recorded!'); setShowGuest(false); setGuestForm({ name: '', email: '', phone: '', visit_date: new Date().toISOString().split('T')[0], referred_by: '', address: '', notes: '' }); fetchPeople(); } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); } finally { setSaving(false); } };

  const openEditFamily = (f) => {
    setEditFamily(f);
    setEditFamilyForm({ family_name: f.family_name || '', primary_contact_name: f.primary_contact_name || '', primary_contact_email: f.primary_contact_email || '', primary_contact_phone: f.primary_contact_phone || '', address: f.address || '', notes: f.notes || '' });
  };
  const saveEditFamily = async () => {
    if (!editFamily) return;
    setSavingFamily(true);
    try {
      await familiesApi.update(editFamily.id, editFamilyForm);
      setFamilies(prev => prev.map(f => f.id === editFamily.id ? { ...f, ...editFamilyForm } : f));
      setEditFamily(null);
      toast.success('Family updated');
    } catch (err) { toast.error(err.response?.data?.detail || 'Save failed'); }
    finally { setSavingFamily(false); }
  };

  const handleExportCsv = async () => { try { const url = exportApi.members(); const a = document.createElement('a'); a.href = url; a.download = 'members.csv'; a.click(); toast.success('Exporting members CSV...'); } catch { toast.error('Export failed'); } };

  const filteredMembers = members;
  const childrenForFamily = (fid) => children.filter(c => c.family_id === fid);

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading" data-testid="unified-people-title">People</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{total} members &middot; {families.length} families &middot; {children.length} children &middot; {guests.length} guests</p>
        </div>
        <div className="flex gap-2">
          {isManager && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild><Button variant="outline" size="sm" className="gap-2" data-testid="import-dropdown"><Upload size={14} /> Import <ChevronDown size={12} /></Button></DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setShowBulkImport(true)}>Members (CSV / Paste)</DropdownMenuItem>
                <DropdownMenuItem onClick={() => setShowChildImport(true)}>Children & Parents</DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => setShowStaffImport(true)}>Staff</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
          <Button variant="outline" size="sm" className="gap-2" onClick={handleExportCsv} data-testid="export-csv-btn"><Download size={14} /> Export</Button>
          <Button size="sm" className="gap-2" onClick={() => setShowAddDialog(true)} data-testid="add-member-btn"><Plus size={14} /> Add Person</Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList data-testid="people-tabs">
          <TabsTrigger value="members" className="gap-1.5" data-testid="tab-members"><Users size={13} /> Members ({total})</TabsTrigger>
          <TabsTrigger value="families" className="gap-1.5" data-testid="tab-families"><Heart size={13} /> Families ({families.length})</TabsTrigger>
          <TabsTrigger value="children" className="gap-1.5" data-testid="tab-children"><Baby size={13} /> Children ({children.length})</TabsTrigger>
          <TabsTrigger value="guests" className="gap-1.5" data-testid="tab-guests"><UserPlus size={13} /> Guests ({guests.length})</TabsTrigger>
          {pendingMembers.length > 0 && <TabsTrigger value="pending" className="gap-1.5" data-testid="tab-pending"><Award size={13} /> Pending ({pendingMembers.length})</TabsTrigger>}
        </TabsList>

        {/* MEMBERS TAB */}
        <TabsContent value="members" className="mt-4">
          <div className="flex gap-3 mb-4 flex-wrap">
            <div className="relative flex-1 min-w-[200px]">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input className="pl-9 h-9" placeholder="Search by name, email, phone..." value={search} onChange={e => setSearch(e.target.value)} data-testid="member-search-input" />
            </div>
            <Select value={filterGroup} onValueChange={setFilterGroup}>
              <SelectTrigger className="w-36 h-9"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="all">All Groups</SelectItem>{MOCK_GROUPS.map(g => <SelectItem key={g} value={g}>{g}</SelectItem>)}</SelectContent>
            </Select>
            <Select value={filterStatus} onValueChange={setFilterStatus}>
              <SelectTrigger className="w-32 h-9"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="all">All Status</SelectItem><SelectItem value="active">Active</SelectItem><SelectItem value="inactive">Inactive</SelectItem></SelectContent>
            </Select>
            <Button variant="ghost" size="sm" className="gap-1.5" onClick={fetchMembers}><RefreshCw size={13} /> Refresh</Button>
          </div>
          {/* Bulk bar */}
          {selectedMemberIds.size > 0 && (
            <div className="flex items-center gap-3 p-3 bg-primary/5 rounded-xl border border-primary/20 mb-3">
              <Checkbox checked={selectedMemberIds.size === members.length} onCheckedChange={selectAllMembers} />
              <span className="text-sm font-medium">{selectedMemberIds.size} selected</span>
              <div className="flex gap-2 ml-auto">
                <Button size="sm" variant="outline" className="h-7" onClick={() => { setBulkActionType('activate'); setShowBulkAction(true); }}>Activate</Button>
                <Button size="sm" variant="outline" className="h-7" onClick={() => { setBulkActionType('deactivate'); setShowBulkAction(true); }}>Deactivate</Button>
                <Button size="sm" variant="outline" className="h-7" onClick={() => { setBulkActionType('role'); setShowBulkAction(true); }}>Change Role</Button>
                <Button size="sm" variant="destructive" className="h-7" onClick={() => { setBulkActionType('delete'); setShowBulkAction(true); }}>Delete</Button>
                <Button size="sm" variant="ghost" className="h-7" onClick={() => setSelectedMemberIds(new Set())}>Clear</Button>
              </div>
            </div>
          )}
          {/* Select all row */}
          <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
            <Checkbox checked={selectedMemberIds.size > 0 && selectedMemberIds.size === members.length} onCheckedChange={selectAllMembers} data-testid="select-all-members" />
            <span>Select all</span>
          </div>
          {loading ? (
            <div className="space-y-2">{[1,2,3,4,5].map(i => <div key={i} className="h-16 bg-muted animate-pulse rounded-xl" />)}</div>
          ) : filteredMembers.length === 0 ? (
            <Card className="shadow-soft rounded-xl"><CardContent className="py-16 text-center"><Users size={40} className="mx-auto mb-3 opacity-20" /><p className="text-muted-foreground">No members found</p></CardContent></Card>
          ) : (
            <div className="space-y-2">
              {filteredMembers.map(m => (
                <Card key={m.id} className={`shadow-soft rounded-xl cursor-pointer hover:bg-accent/40 transition-colors ${selectedMemberIds.has(m.id) ? 'ring-2 ring-primary/30' : ''}`} onClick={() => { setDefaultMemberTab('info'); handleViewMember(m); }} data-testid={`member-card-${m.id}`}>
                  <CardContent className="p-3 flex items-center gap-3">
                    <Checkbox checked={selectedMemberIds.has(m.id)} onCheckedChange={() => toggleMemberSelect(m.id)} onClick={e => e.stopPropagation()} data-testid={`select-member-${m.id}`} />
                    <Avatar className="h-10 w-10"><AvatarFallback className="text-xs bg-primary/10 text-primary">{initials(m.name)}</AvatarFallback></Avatar>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{m.name}</p>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        {m.email && <span className="flex items-center gap-1"><Mail size={10} />{m.email}</span>}
                        {m.phone && <span className="flex items-center gap-1"><Phone size={10} />{m.phone}</span>}
                      </div>
                    </div>
                    <Badge variant="outline" className="text-[10px] capitalize">{m.role}</Badge>
                    <Badge variant="secondary" className="text-[10px]">{m.group}</Badge>
                    <Badge className={`text-[10px] ${m.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>{m.status || 'active'}</Badge>
                    {isCoordinator && (
                      <div className="flex gap-1" onClick={e => e.stopPropagation()}>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" data-testid={`edit-member-${m.id}`} onClick={async e => { e.stopPropagation(); setDefaultMemberTab('edit'); await handleViewMember(m); }} title="Edit Profile"><Eye size={13} /></Button>
                        <Button size="sm" variant="ghost" className="text-destructive h-7 w-7 p-0" onClick={e => { e.stopPropagation(); membersApi.delete(m.id).then(() => { toast.success('Deleted'); fetchMembers(); }); }}><Trash2 size={13} /></Button>
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* FAMILIES TAB */}
        <TabsContent value="families" className="mt-4">
          <div className="flex justify-end mb-3">
            <Button size="sm" className="gap-2" onClick={() => setShowFamily(true)} data-testid="add-family-btn"><Plus size={14} /> Add Family</Button>
          </div>
          {families.length === 0 ? (
            <Card className="shadow-soft rounded-xl"><CardContent className="py-16 text-center"><Heart size={40} className="mx-auto mb-3 opacity-20" /><p className="text-muted-foreground">No families yet</p></CardContent></Card>
          ) : (
            <div className="space-y-3">
              {families.map(f => (
                <Card key={f.id} className="shadow-soft rounded-xl" data-testid={`family-card-${f.id}`}>
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div><p className="font-medium">{f.family_name}</p><p className="text-xs text-muted-foreground">{f.primary_contact_name} &middot; {f.primary_contact_phone}</p></div>
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary" className="text-xs">{childrenForFamily(f.id).length} children</Badge>
                        {isCoordinator && (
                          <div className="flex gap-1">
                            <Button size="sm" variant="ghost" className="h-7 w-7 p-0" data-testid={`edit-family-${f.id}`} onClick={() => openEditFamily(f)} title="Edit"><Eye size={13} /></Button>
                            <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" data-testid={`delete-family-${f.id}`} onClick={() => familiesApi.delete(f.id).then(() => { toast.success('Family deleted'); fetchPeople(); }).catch(err => toast.error(err.response?.data?.detail || 'Failed'))}><Trash2 size={13} /></Button>
                          </div>
                        )}
                      </div>
                    </div>
                    {childrenForFamily(f.id).length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">{childrenForFamily(f.id).map(c => <Badge key={c.id} variant="outline" className="text-[10px]">{c.name} ({c.class_group})</Badge>)}</div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* CHILDREN TAB */}
        <TabsContent value="children" className="mt-4">
          <div className="flex justify-end mb-3">
            <Button size="sm" className="gap-2" onClick={() => setShowChild(true)} data-testid="add-child-btn"><Plus size={14} /> Add Child</Button>
          </div>
          {children.length === 0 ? (
            <Card className="shadow-soft rounded-xl"><CardContent className="py-16 text-center"><Baby size={40} className="mx-auto mb-3 opacity-20" /><p className="text-muted-foreground">No children registered</p></CardContent></Card>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {children.map(c => (
                <Card key={c.id} className="shadow-soft rounded-xl" data-testid={`child-card-${c.id}`}>
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1">
                        <p className="font-medium text-sm">{c.name}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">{c.class_group} &middot; DOB: {c.date_of_birth || 'N/A'}</p>
                        {c.allergies && <Badge variant="destructive" className="text-[10px] mt-1.5">{c.allergies}</Badge>}
                      </div>
                      {isCoordinator && (
                        <div className="flex gap-1">
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0" data-testid={`edit-child-${c.id}`} onClick={() => openEditChild(c)} title="Edit"><Eye size={13} /></Button>
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" onClick={() => childrenApi.delete(c.id).then(() => { toast.success('Deleted'); fetchPeople(); })}><Trash2 size={13} /></Button>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* GUESTS TAB */}
        <TabsContent value="guests" className="mt-4">
          <div className="flex justify-end mb-3">
            <Button size="sm" className="gap-2" onClick={() => setShowGuest(true)} data-testid="add-guest-btn"><Plus size={14} /> Record Guest</Button>
          </div>
          {guests.length === 0 ? (
            <Card className="shadow-soft rounded-xl"><CardContent className="py-16 text-center"><UserPlus size={40} className="mx-auto mb-3 opacity-20" /><p className="text-muted-foreground">No guest visits recorded</p></CardContent></Card>
          ) : (
            <div className="space-y-2">
              {guests.map(g => (
                <Card key={g.id} className="shadow-soft rounded-xl" data-testid={`guest-card-${g.id}`}>
                  <CardContent className="p-3 flex items-center justify-between">
                    <div><p className="text-sm font-medium">{g.name}</p><p className="text-xs text-muted-foreground">{g.visit_date} &middot; {g.phone || g.email || ''}</p></div>
                    {g.referred_by && <Badge variant="secondary" className="text-[10px]">Ref: {g.referred_by}</Badge>}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* PENDING TAB */}
        {pendingMembers.length > 0 && (
          <TabsContent value="pending" className="mt-4">
            <div className="space-y-2">
              {pendingMembers.map(m => (
                <Card key={m.id} className="shadow-soft rounded-xl" data-testid={`pending-card-${m.id}`}>
                  <CardContent className="p-3 flex items-center justify-between">
                    <div><p className="text-sm font-medium">{m.name}</p><p className="text-xs text-muted-foreground">{m.email}</p></div>
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" className="text-green-600 h-7" onClick={async () => { await approvalsApi.approve(m.id); toast.success('Approved'); setPendingMembers(prev => prev.filter(p => p.id !== m.id)); fetchMembers(); }}>Approve</Button>
                      <Button size="sm" variant="outline" className="text-red-600 h-7" onClick={async () => { await approvalsApi.reject(m.id); toast.success('Rejected'); setPendingMembers(prev => prev.filter(p => p.id !== m.id)); }}>Reject</Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>
        )}
      </Tabs>

      {/* ADD MEMBER DIALOG */}
      <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Add Person</DialogTitle></DialogHeader>
          <form onSubmit={handleAddMember}>
            <MemberForm data={newMember} onChange={setNewMember} locations={allLocations} showDepartment={true} />
            <div className="flex gap-3 pt-4"><Button type="button" variant="outline" className="flex-1" onClick={() => setShowAddDialog(false)}>Cancel</Button><Button type="submit" className="flex-1" disabled={savingMember || !newMember.name} data-testid="save-member-btn">{savingMember ? 'Saving...' : 'Save'}</Button></div>
          </form>
        </DialogContent>
      </Dialog>

      {/* MEMBER DETAIL DIALOG */}
      <Dialog open={!!selectedMember} onOpenChange={(o) => { if (!o) { setSelectedMember(null); setMemberDetail(null); setDefaultMemberTab('info'); } }}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{memberDetail?.name || 'Member Detail'}</DialogTitle></DialogHeader>
          {memberDetail && (
            <Tabs defaultValue={defaultMemberTab} key={defaultMemberTab}>
              <TabsList><TabsTrigger value="info">Info</TabsTrigger>{isCoordinator && <TabsTrigger value="edit">Edit Profile</TabsTrigger>}<TabsTrigger value="documents">Documents</TabsTrigger></TabsList>
              <TabsContent value="info" className="space-y-4 mt-3">
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div><span className="text-xs text-muted-foreground">Name</span><p className="font-medium">{memberDetail.name}</p></div>
                  <div><span className="text-xs text-muted-foreground">Email</span><p>{memberDetail.email || '—'}</p></div>
                  <div><span className="text-xs text-muted-foreground">Phone</span><p>{memberDetail.phone || '—'}</p></div>
                  <div><span className="text-xs text-muted-foreground">National ID</span><p>{memberDetail.national_id || '—'}</p></div>
                  <div><span className="text-xs text-muted-foreground">Gender</span><p className="capitalize">{memberDetail.gender || '—'}</p></div>
                  <div><span className="text-xs text-muted-foreground">Role</span><p>{memberDetail.role}</p></div>
                  <div><span className="text-xs text-muted-foreground">Group</span><p>{memberDetail.group}</p></div>
                  <div><span className="text-xs text-muted-foreground">Department</span><p>{memberDetail.department || '—'}</p></div>
                  <div><span className="text-xs text-muted-foreground">Status</span><Badge className={memberDetail.status === 'active' ? 'bg-green-100 text-green-700' : ''}>{memberDetail.status}</Badge></div>
                  <div><span className="text-xs text-muted-foreground">Joined</span><p>{memberDetail.join_date || '—'}</p></div>
                </div>
                {memberDetail.notes && <div><span className="text-xs text-muted-foreground">Notes</span><p className="text-sm mt-0.5">{memberDetail.notes}</p></div>}
              </TabsContent>
              {isCoordinator && (
                <TabsContent value="edit" className="space-y-4 mt-3">
                  <MemberForm
                    data={editMemberForm}
                    onChange={setEditMemberForm}
                    locations={allLocations}
                    showDepartment={true}
                  />
                  <div className="flex gap-3">
                    <Button variant="outline" className="flex-1" onClick={() => setSelectedMember(null)}>Cancel</Button>
                    <Button className="flex-1" data-testid="save-member-edit-btn" onClick={saveEditMember} disabled={savingEdit}>{savingEdit ? 'Saving...' : 'Save Profile'}</Button>
                  </div>
                </TabsContent>
              )}
              <TabsContent value="documents" className="space-y-4 mt-3">
                {memberDetail.role !== 'Child' && (
                  <div className="p-4 rounded-xl border border-dashed border-border space-y-3">
                    <p className="text-sm font-medium">Upload ID Document (JPG/PNG)</p>
                    <div className="grid grid-cols-2 gap-3">
                      <Select value={docType} onValueChange={setDocType}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="id_scan">ID Scan</SelectItem><SelectItem value="passport">Passport</SelectItem><SelectItem value="other">Other</SelectItem></SelectContent></Select>
                      <Input placeholder="Label" value={docLabel} onChange={e => setDocLabel(e.target.value)} />
                    </div>
                    <Input type="file" accept=".jpg,.jpeg,.png" onChange={e => setDocFile(e.target.files?.[0] || null)} data-testid="doc-upload-input" />
                    <Button size="sm" disabled={!docFile || docUploading} onClick={handleDocUpload} data-testid="upload-doc-btn">{docUploading ? 'Uploading...' : 'Upload'}</Button>
                  </div>
                )}
                {memberDocuments.length === 0 ? <p className="text-sm text-muted-foreground text-center py-6">No documents uploaded.</p> : (
                  <div className="space-y-2">{memberDocuments.map(d => (
                    <div key={d.id} className="flex items-center justify-between p-3 rounded-lg border text-sm" data-testid={`doc-${d.id}`}>
                      <div><p className="font-medium">{d.label}</p><p className="text-xs text-muted-foreground">{d.original_filename} &middot; {d.created_at?.slice(0, 10)}</p></div>
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" className="h-7" onClick={() => window.open(`${process.env.REACT_APP_BACKEND_URL}/api/documents/${d.id}/file`, '_blank')}>View</Button>
                        <Button size="sm" variant="ghost" className="text-destructive h-7" onClick={async () => { await api.put(`/documents/${d.id}/archive`); toast.success('Archived'); setMemberDocuments(prev => prev.filter(p => p.id !== d.id)); }}>Archive</Button>
                      </div>
                    </div>
                  ))}</div>
                )}
              </TabsContent>
            </Tabs>
          )}
        </DialogContent>
      </Dialog>

      {/* FAMILY DIALOG */}
      <Dialog open={showFamily} onOpenChange={setShowFamily}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Add Family</DialogTitle></DialogHeader>
          <form onSubmit={handleAddFamily} className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label>Family Name *</Label><Input value={familyForm.family_name} onChange={e => setFamilyForm({ ...familyForm, family_name: e.target.value })} required /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Contact Name</Label><Input value={familyForm.primary_contact_name} onChange={e => setFamilyForm({ ...familyForm, primary_contact_name: e.target.value })} /></div>
              <div className="space-y-1.5"><Label>Contact Phone</Label><Input value={familyForm.primary_contact_phone} onChange={e => setFamilyForm({ ...familyForm, primary_contact_phone: e.target.value })} /></div>
            </div>
            <div className="space-y-1.5"><Label>Contact Email</Label><Input type="email" value={familyForm.primary_contact_email} onChange={e => setFamilyForm({ ...familyForm, primary_contact_email: e.target.value })} /></div>
            <div className="flex gap-3 pt-2"><Button type="button" variant="outline" className="flex-1" onClick={() => setShowFamily(false)}>Cancel</Button><Button type="submit" className="flex-1" disabled={saving}>{saving ? 'Saving...' : 'Add Family'}</Button></div>
          </form>
        </DialogContent>
      </Dialog>

      {/* CHILD DIALOG */}
      <Dialog open={showChild} onOpenChange={setShowChild}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Add Child</DialogTitle></DialogHeader>
          <form onSubmit={handleAddChild} className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label>Name *</Label><Input value={childForm.name} onChange={e => setChildForm({ ...childForm, name: e.target.value })} required /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Date of Birth</Label><Input type="date" value={childForm.date_of_birth} onChange={e => setChildForm({ ...childForm, date_of_birth: e.target.value })} /></div>
              <div className="space-y-1.5"><Label>Gender</Label>
                <Select value={childForm.gender} onValueChange={v => setChildForm({ ...childForm, gender: v })}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent><SelectItem value="male">Male</SelectItem><SelectItem value="female">Female</SelectItem></SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Family</Label>
                <Select value={childForm.family_id} onValueChange={v => setChildForm({ ...childForm, family_id: v })}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>{families.map(f => <SelectItem key={f.id} value={f.id}>{f.family_name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label>Class / Group</Label><Input value={childForm.class_group} onChange={e => setChildForm({ ...childForm, class_group: e.target.value })} /></div>
            </div>
            <div className="space-y-1.5"><Label>Medical Notes</Label><Textarea rows={2} value={childForm.medical_notes} onChange={e => setChildForm({ ...childForm, medical_notes: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Allergies</Label><Input value={childForm.allergies} onChange={e => setChildForm({ ...childForm, allergies: e.target.value })} /></div>
            <div className="flex gap-3 pt-2"><Button type="button" variant="outline" className="flex-1" onClick={() => setShowChild(false)}>Cancel</Button><Button type="submit" className="flex-1" disabled={saving}>{saving ? 'Saving...' : 'Add Child'}</Button></div>
          </form>
        </DialogContent>
      </Dialog>

      {/* GUEST DIALOG */}
      <Dialog open={showGuest} onOpenChange={setShowGuest}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Record Guest Visit</DialogTitle></DialogHeader>
          <form onSubmit={handleAddGuest} className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label>Name *</Label><Input value={guestForm.name} onChange={e => setGuestForm({ ...guestForm, name: e.target.value })} required /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Email</Label><Input type="email" value={guestForm.email} onChange={e => setGuestForm({ ...guestForm, email: e.target.value })} /></div>
              <div className="space-y-1.5"><Label>Phone</Label><Input value={guestForm.phone} onChange={e => setGuestForm({ ...guestForm, phone: e.target.value })} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Visit Date</Label><Input type="date" value={guestForm.visit_date} onChange={e => setGuestForm({ ...guestForm, visit_date: e.target.value })} /></div>
              <div className="space-y-1.5"><Label>Referred By</Label><Input value={guestForm.referred_by} onChange={e => setGuestForm({ ...guestForm, referred_by: e.target.value })} /></div>
            </div>
            <div className="space-y-1.5"><Label>Notes</Label><Textarea rows={2} value={guestForm.notes} onChange={e => setGuestForm({ ...guestForm, notes: e.target.value })} /></div>
            <div className="flex gap-3 pt-2"><Button type="button" variant="outline" className="flex-1" onClick={() => setShowGuest(false)}>Cancel</Button><Button type="submit" className="flex-1" disabled={saving}>{saving ? 'Saving...' : 'Record Visit'}</Button></div>
          </form>
        </DialogContent>
      </Dialog>

      {/* BULK ACTION DIALOG */}
      <Dialog open={showBulkAction} onOpenChange={setShowBulkAction}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Bulk Action ({selectedMemberIds.size} members)</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            {bulkActionType === 'role' && (
              <div className="space-y-2"><Label>New Role</Label>
                <Select value={bulkRole} onValueChange={setBulkRole}>
                  <SelectTrigger><SelectValue placeholder="Select role" /></SelectTrigger>
                  <SelectContent>{MOCK_ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            )}
            {bulkActionType === 'delete' && <p className="text-sm text-destructive font-medium">This will permanently delete {selectedMemberIds.size} members!</p>}
            {(bulkActionType === 'activate' || bulkActionType === 'deactivate') && <p className="text-sm">This will {bulkActionType} {selectedMemberIds.size} members.</p>}
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => setShowBulkAction(false)}>Cancel</Button>
              <Button className="flex-1" variant={bulkActionType === 'delete' ? 'destructive' : 'default'} onClick={executeBulk} disabled={saving || (bulkActionType === 'role' && !bulkRole)} data-testid="confirm-bulk-action-btn">{saving ? 'Processing...' : 'Execute'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* EDIT CHILD DIALOG */}
      <Dialog open={!!editChild} onOpenChange={(o) => { if (!o) setEditChild(null); }}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Edit Child: {editChild?.name}</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label>Name *</Label><Input data-testid="edit-child-name" value={editChildForm.name || ''} onChange={e => setEditChildForm({ ...editChildForm, name: e.target.value })} required /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Date of Birth</Label><Input type="date" value={editChildForm.date_of_birth || ''} onChange={e => setEditChildForm({ ...editChildForm, date_of_birth: e.target.value })} /></div>
              <div className="space-y-1.5"><Label>Gender</Label>
                <Select value={editChildForm.gender || ''} onValueChange={v => setEditChildForm({ ...editChildForm, gender: v })}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent><SelectItem value="male">Male</SelectItem><SelectItem value="female">Female</SelectItem></SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Family</Label>
                <Select value={editChildForm.family_id || ''} onValueChange={v => setEditChildForm({ ...editChildForm, family_id: v })}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>{families.map(f => <SelectItem key={f.id} value={f.id}>{f.family_name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label>Class / Group</Label><Input value={editChildForm.class_group || ''} onChange={e => setEditChildForm({ ...editChildForm, class_group: e.target.value })} /></div>
            </div>
            <div className="space-y-1.5"><Label>Medical Notes</Label><Textarea rows={2} value={editChildForm.medical_notes || ''} onChange={e => setEditChildForm({ ...editChildForm, medical_notes: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Allergies</Label><Input value={editChildForm.allergies || ''} onChange={e => setEditChildForm({ ...editChildForm, allergies: e.target.value })} /></div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setEditChild(null)}>Cancel</Button>
              <Button className="flex-1" data-testid="save-child-btn" onClick={saveEditChild} disabled={savingChild}>{savingChild ? 'Saving...' : 'Save'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* EDIT FAMILY DIALOG */}
      <Dialog open={!!editFamily} onOpenChange={(o) => { if (!o) setEditFamily(null); }}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Edit Family: {editFamily?.family_name}</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label>Family Name *</Label><Input data-testid="edit-family-name" value={editFamilyForm.family_name || ''} onChange={e => setEditFamilyForm({ ...editFamilyForm, family_name: e.target.value })} required /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Contact Name</Label><Input value={editFamilyForm.primary_contact_name || ''} onChange={e => setEditFamilyForm({ ...editFamilyForm, primary_contact_name: e.target.value })} /></div>
              <div className="space-y-1.5"><Label>Contact Phone</Label><Input value={editFamilyForm.primary_contact_phone || ''} onChange={e => setEditFamilyForm({ ...editFamilyForm, primary_contact_phone: e.target.value })} /></div>
            </div>
            <div className="space-y-1.5"><Label>Contact Email</Label><Input type="email" value={editFamilyForm.primary_contact_email || ''} onChange={e => setEditFamilyForm({ ...editFamilyForm, primary_contact_email: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Address</Label><Input value={editFamilyForm.address || ''} onChange={e => setEditFamilyForm({ ...editFamilyForm, address: e.target.value })} /></div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setEditFamily(null)}>Cancel</Button>
              <Button className="flex-1" data-testid="save-family-btn" onClick={saveEditFamily} disabled={savingFamily}>{savingFamily ? 'Saving...' : 'Save'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* IMPORT DIALOGS */}
      <Dialog open={showBulkImport} onOpenChange={setShowBulkImport}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto"><DialogHeader><DialogTitle>Import Members</DialogTitle><DialogDescription>Upload CSV or paste data (name, email, phone, group per line)</DialogDescription></DialogHeader>
          <div className="space-y-4"><div className="space-y-2"><Label>CSV File</Label><Input type="file" accept=".csv" onChange={e => setCsvFile(e.target.files?.[0] || null)} data-testid="bulk-csv-file-input" /></div><div className="text-xs text-muted-foreground text-center">— or paste —</div><Textarea rows={5} placeholder="John Doe, john@email.com, +256..." value={bulkData} onChange={e => setBulkData(e.target.value)} /></div>
          <div className="flex gap-3 pt-2"><Button variant="outline" className="flex-1" onClick={() => setShowBulkImport(false)}>Cancel</Button><Button className="flex-1" disabled={importLoading || (!bulkData.trim() && !csvFile)} onClick={handleBulkImport}>{importLoading ? 'Importing...' : 'Import'}</Button></div>
        </DialogContent>
      </Dialog>

      <Dialog open={showChildImport} onOpenChange={setShowChildImport}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto"><DialogHeader><DialogTitle>Import Children & Parents</DialogTitle></DialogHeader>
          <div className="space-y-4"><div className="space-y-2"><Label>CSV File</Label><Input type="file" accept=".csv" onChange={e => setChildCsvFile(e.target.files?.[0] || null)} /></div><div className="text-xs text-muted-foreground text-center">— or paste —</div><Textarea rows={5} placeholder="first_name,last_name,..." value={childCsvData} onChange={e => setChildCsvData(e.target.value)} /></div>
          <div className="flex gap-3 pt-2"><Button variant="outline" className="flex-1" onClick={() => setShowChildImport(false)}>Cancel</Button><Button className="flex-1" disabled={importLoading || (!childCsvData.trim() && !childCsvFile)} onClick={handleChildImport}>{importLoading ? 'Importing...' : 'Import'}</Button></div>
        </DialogContent>
      </Dialog>

      <Dialog open={showStaffImport} onOpenChange={setShowStaffImport}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto"><DialogHeader><DialogTitle>Import Staff</DialogTitle></DialogHeader>
          <div className="space-y-4"><div className="space-y-2"><Label>CSV File</Label><Input type="file" accept=".csv" onChange={e => setStaffCsvFile(e.target.files?.[0] || null)} /></div><div className="text-xs text-muted-foreground text-center">— or paste —</div><Textarea rows={5} placeholder="name,email,phone,..." value={staffCsvData} onChange={e => setStaffCsvData(e.target.value)} /></div>
          <div className="flex gap-3 pt-2"><Button variant="outline" className="flex-1" onClick={() => setShowStaffImport(false)}>Cancel</Button><Button className="flex-1" disabled={importLoading || (!staffCsvData.trim() && !staffCsvFile)} onClick={handleStaffImport}>{importLoading ? 'Importing...' : 'Import'}</Button></div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
