import React, { useState, useEffect, useCallback } from 'react';
import { Search, Plus, Users, Heart, Baby, UserPlus, Filter, Eye, Trash2, Download, Upload, Award, FileUp, Phone, Mail, RefreshCw, ChevronDown, CheckSquare, Key, Printer, X, Home, GraduationCap, Shield } from 'lucide-react';
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
import { BulkActionBar, exportToCSV } from '../components/BulkActions';
import { UnifiedBadge } from '../components/UnifiedBadge';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { MOCK_GROUPS, MOCK_ROLES } from '../mock';
import { toast } from 'sonner';
import { emitDataChanged } from '../services/dataEvents';
import { BulkDeleteConfirm } from '../components/BulkDeleteConfirm';

import MemberForm from '../components/people/MemberForm';

const initials = (name) => (name || '?').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();

export default function UnifiedPeoplePage() {
  const { user } = useAuth();
  const userRole = user?.role || '';
  const isManager = ['admin', 'system_admin', 'Executive Director', 'Director', 'Manager'].includes(userRole);
  const isDirector = ['admin', 'system_admin', 'Executive Director', 'Director'].includes(userRole);
  const isCoordinator = isManager || ['Coordinator', 'Leader'].includes(userRole);
  const canEditStaff = isDirector; // Directors+ can edit staff in their location

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
  const [parentSearch, setParentSearch] = useState('');
  const [uploadingChildPhoto, setUploadingChildPhoto] = useState(false);
  const [childSearch, setChildSearch] = useState('');
  const [guestSearch, setGuestSearch] = useState('');

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
  const [selMembers, setSelMembers] = useState(new Set());
  const [selChildren, setSelChildren] = useState(new Set());
  const [selFamilies, setSelFamilies] = useState(new Set());
  const [selGuests, setSelGuests] = useState(new Set());
  const [showBulkChildEdit, setShowBulkChildEdit] = useState(false);
  const [showResetPw, setShowResetPw] = useState(false);
  const [showBadge, setShowBadge] = useState(false);
  const [badgePerson, setBadgePerson] = useState(null);
  const [resetPwUser, setResetPwUser] = useState(null);
  const [newPassword, setNewPassword] = useState('');
  const [showBulkFamilyEdit, setShowBulkFamilyEdit] = useState(false);
  const [bulkChildForm, setBulkChildForm] = useState({ family_id: '', location_id: '', class_group: '' });
  const [bulkFamilyForm, setBulkFamilyForm] = useState({ location_id: '' });
  const [showFamily, setShowFamily] = useState(false);
  const [showChild, setShowChild] = useState(false);
  const [showGuest, setShowGuest] = useState(false);
  const [familyForm, setFamilyForm] = useState({ family_name: '', primary_contact_name: '', primary_contact_email: '', primary_contact_phone: '', address: '' });
  const [childForm, setChildForm] = useState({ name: '', date_of_birth: '', gender: '', family_id: '', class_group: '', medical_notes: '', allergies: '', location_id: '' });
  const [guestForm, setGuestForm] = useState({ name: '', email: '', phone: '', visit_date: new Date().toISOString().split('T')[0], referred_by: '', address: '', notes: '' });

  // Edit family
  const [editFamily, setEditFamily] = useState(null);
  const [editFamilyForm, setEditFamilyForm] = useState({});
  const [savingFamily, setSavingFamily] = useState(false);

  const [allLocations, setAllLocations] = useState([]);
  const [filterLocation, setFilterLocation] = useState('all');
  const [filterWelfare, setFilterWelfare] = useState('all');  // all|sponsored|restricted_location|welfare_support|multiple|any
  const [activeTab, setActiveTab] = useState('members');
  const [saving, setSaving] = useState(false);
  const [bulkDeleteTarget, setBulkDeleteTarget] = useState(null); // { type, ids, label }
  const [editGuest, setEditGuest] = useState(null);
  const [editGuestForm, setEditGuestForm] = useState({});
  const [savingGuest, setSavingGuest] = useState(false);

  const downloadTemplate = async (type, filename) => {
    try {
      const res = await api.get(`/import/template/${type}`, { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error('Template download failed'); }
  };

  const fetchMembers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await membersApi.list({ search: search || undefined, group: filterGroup !== 'all' ? filterGroup : undefined, status: filterStatus !== 'all' ? filterStatus : undefined, location_id: filterLocation !== 'all' ? filterLocation : undefined, welfare_category: filterWelfare !== 'all' ? filterWelfare : undefined, limit: 100, staff_only: true });
      setMembers(res.data.members || res.data || []);
      setTotal(res.data.total || (res.data.members || res.data || []).length);
    } catch { toast.error('Failed to load members'); }
    finally { setLoading(false); }
  }, [search, filterGroup, filterStatus, filterLocation, filterWelfare]);

  const fetchPeople = useCallback(async () => {
    try {
      const [famRes, chdRes, gstRes] = await Promise.all([
        familiesApi.list(),
        childrenApi.list({ welfare_category: filterWelfare !== 'all' ? filterWelfare : undefined }),
        guestsApi.list(),
      ]);
      setFamilies(famRes.data || []);
      setChildren(chdRes.data || []);
      setGuests(gstRes.data || []);
    } catch (e) { console.warn(e.message || e); }
  }, [filterWelfare]);

  useEffect(() => {
    const load = async () => {
      await Promise.all([fetchMembers(), fetchPeople()]);
      try {
        const [locsRes, pendRes, badgeRes] = await Promise.all([locationsApi.list(), approvalsApi.pending().catch(() => ({ data: [] })), badgesApi.list().catch(() => ({ data: [] }))]);
        setAllLocations(locsRes.data || []);
        const pendData = pendRes.data;
        setPendingMembers(Array.isArray(pendData) ? pendData : pendData?.members || []);
        setBadges(badgeRes.data || []);
      } catch (e) { console.warn(e.message || e); }
    };
    load();
  }, [fetchMembers, fetchPeople]);

  // Bulk selection helpers
  const toggleMemberSelect = (id) => setSelectedMemberIds(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const selectAllMembers = () => setSelectedMemberIds(prev => prev.size === members.length ? new Set() : new Set(members.map(m => m.id)));

  const executeBulk = async () => {
    const ids = [...selectedMemberIds];
    if (!ids.length) return;
    if (bulkActionType === 'delete') {
      setBulkDeleteTarget({ type: 'members', ids, label: 'members' });
      return;
    }
    setSaving(true);
    try {
      if (bulkActionType === 'role' && bulkRole) {
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
    setEditMemberForm({ name: m.name || '', email: m.email || '', phone: m.phone || '', role: m.role || 'Member', group: m.group || '', gender: m.gender || '', date_of_birth: m.date_of_birth || '', national_id: m.national_id || '', address: m.address || '', department: m.department || '', program: m.program || '', pin: m.pin || '', notes: m.notes || '', status: m.status || 'active', location_id: m.location_id || '', is_parent: m.is_parent || false, is_donor: m.is_donor || false, is_admin: m.role === 'admin' || m.role === 'system_admin' });
  };
  const saveEditMember = async () => {
    if (!editMember) return;
    setSavingEdit(true);
    try {
      // Save to both members and users collections
      const res = await membersApi.update(editMember.id, editMemberForm);
      // Also update users collection for flag fields (is_parent, is_guest, etc.)
      const flagFields = { is_parent: editMemberForm.is_parent, is_guest: editMemberForm.is_guest, is_customer: editMemberForm.is_customer, is_donor: editMemberForm.is_donor };
      if (editMemberForm.is_admin) flagFields.role = 'admin';
      try { await adminApi.updateUser(editMember.id, flagFields); } catch (e) { console.warn(e.message || e); }
      setMembers(prev => prev.map(m => m.id === editMember.id ? { ...m, ...res.data, ...flagFields } : m));
      if (selectedMember?.id === editMember.id) setMemberDetail(prev => ({ ...prev, ...res.data, ...flagFields }));
      setEditMember(null);
      toast.success('Profile saved');
    } catch (err) { toast.error(err.response?.data?.detail || 'Save failed'); }
    finally { setSavingEdit(false); }
  };

  // Edit child
  const openEditChild = (c, e) => {
    if (e) e.stopPropagation();
    setEditChild(c);
    setEditChildForm({ name: c.name || '', date_of_birth: c.date_of_birth || '', gender: c.gender || '', family_id: c.family_id || '', class_group: c.class_group || '', grade: c.grade || '', school: c.school || '', medical_notes: c.medical_notes || '', allergies: c.allergies || '', parent_ids: c.parent_ids || [], location_id: c.location_id || '', is_resident: c.is_resident || false, resident_location_id: c.resident_location_id || '', is_sponsored: c.is_sponsored || false, sponsor_first_name: c.sponsor_first_name || '', is_medical: c.is_medical || false, photo_url: c.photo_url || '' });
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
        // Parse CSV client-side and send to the improved bulk-import endpoint
        const text = await childCsvFile.text();
        const lines = text.trim().split('\n');
        const header = lines[0].split(',').map(h => h.trim().toLowerCase().replace(/[\ufeff"]/g, ''));
        const rows = lines.slice(1).filter(l => l.trim()).map(line => {
          const vals = line.split(',').map(v => v.trim().replace(/^"|"$/g, ''));
          const row = {};
          header.forEach((h, i) => { row[h] = vals[i] || ''; });
          // Map common alternate field names
          if (!row.name && (row.first_name || row.last_name)) row.name = `${row.first_name || ''} ${row.last_name || ''}`.trim();
          if (!row.father_name && row.fathers_names) row.father_name = row.fathers_names;
          if (!row.mother_name && row.mothers_names) row.mother_name = row.mothers_names;
          if (!row.father_phone && row.fathers_phone) row.father_phone = row.fathers_phone;
          if (!row.mother_phone && row.mothers_phone) row.mother_phone = row.mothers_phone;
          if (!row.father_email && row.fathers_email) row.father_email = row.fathers_email;
          if (!row.mother_email && row.mothers_email) row.mother_email = row.mothers_email;
          return row;
        });
        const res = await api.post('/children/bulk-import', { children: rows });
        toast.success(`Imported ${res.data.imported} children, ${res.data.parents_created || 0} parents created`);
      } else if (childCsvData.trim()) {
        const lines = childCsvData.trim().split('\n');
        const header = lines[0].toLowerCase().split(',').map(h => h.trim());
        const rows = lines.slice(1).map(line => {
          const vals = line.split(',').map(v => v.trim());
          const row = {};
          header.forEach((h, i) => { row[h] = vals[i] || ''; });
          if (!row.name && (row.first_name || row.last_name)) row.name = `${row.first_name || ''} ${row.last_name || ''}`.trim();
          if (!row.father_name && row.fathers_names) row.father_name = row.fathers_names;
          if (!row.mother_name && row.mothers_names) row.mother_name = row.mothers_names;
          if (!row.father_phone && row.fathers_phone) row.father_phone = row.fathers_phone;
          if (!row.mother_phone && row.mothers_phone) row.mother_phone = row.mothers_phone;
          return row;
        }).filter(r => r.name);
        const res = await api.post('/children/bulk-import', { children: rows });
        toast.success(`Imported ${res.data.imported} children, ${res.data.parents_created || 0} parents`);
      }
      setShowChildImport(false); setChildCsvData(''); setChildCsvFile(null); fetchPeople();
    } catch (err) { toast.error(err.response?.data?.detail || 'Import failed'); }
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

  const openEditGuest = (g) => {
    setEditGuest(g);
    setEditGuestForm({ name: g.name || '', phone: g.phone || '', email: g.email || '', is_parent: g.is_parent || false, is_medical: g.is_medical || false, is_resident: g.is_resident || false, notes: g.notes || '', address: g.address || '', referred_by: g.referred_by || '', location_id: g.location_id || '' });
  };

  const saveEditGuest = async () => {
    if (!editGuest) return;
    setSavingGuest(true);
    try {
      await guestsApi.update(editGuest.id, editGuestForm);
      setGuests(prev => prev.map(g => g.id === editGuest.id ? { ...g, ...editGuestForm } : g));
      setEditGuest(null);
      toast.success('Guest updated');
    } catch (err) { toast.error(err.response?.data?.detail || 'Update failed'); }
    finally { setSavingGuest(false); }
  };


  // Family/Child/Guest handlers
  const handleAddFamily = async (e) => { e.preventDefault(); setSaving(true); try { await familiesApi.create(familyForm); toast.success('Family added!'); setShowFamily(false); setFamilyForm({ family_name: '', primary_contact_name: '', primary_contact_email: '', primary_contact_phone: '', address: '' }); fetchPeople(); } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); } finally { setSaving(false); } };
  const handleAddChild = async (e) => { e.preventDefault(); setSaving(true); try { await childrenApi.create(childForm); toast.success('Child added!'); setShowChild(false); setChildForm({ name: '', date_of_birth: '', gender: '', family_id: '', class_group: '', medical_notes: '', allergies: '', location_id: '' }); fetchPeople(); } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); } finally { setSaving(false); } };
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
                <DropdownMenuSeparator />
                <DropdownMenuItem className="text-xs text-muted-foreground" onClick={() => downloadTemplate('children', 'children_template.csv')}>
                  <Download size={12} className="mr-1.5" /> Children Template
                </DropdownMenuItem>
                <DropdownMenuItem className="text-xs text-muted-foreground" onClick={() => downloadTemplate('staff', 'staff_template.csv')}>
                  <Download size={12} className="mr-1.5" /> Staff Template
                </DropdownMenuItem>
                <DropdownMenuItem className="text-xs text-muted-foreground" onClick={() => downloadTemplate('guests', 'guests_template.csv')}>
                  <Download size={12} className="mr-1.5" /> Guests Template
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
          <Button variant="outline" size="sm" className="gap-2" onClick={handleExportCsv} data-testid="export-csv-btn"><Download size={14} /> Export</Button>
          <Button size="sm" className="gap-2" onClick={() => setShowAddDialog(true)} data-testid="add-member-btn"><Plus size={14} /> Add Person</Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList data-testid="people-tabs">
          <TabsTrigger value="members" className="gap-1.5" data-testid="tab-members"><Users size={13} /> Staff ({total})</TabsTrigger>
          <TabsTrigger value="families" className="gap-1.5" data-testid="tab-families"><Heart size={13} /> Families ({families.length})</TabsTrigger>
          <TabsTrigger value="children" className="gap-1.5" data-testid="tab-children"><Baby size={13} /> Children ({children.length})</TabsTrigger>
          <TabsTrigger value="guests" className="gap-1.5" data-testid="tab-guests"><UserPlus size={13} /> Guests & Parents ({guests.length})</TabsTrigger>
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
            <Select value={filterWelfare} onValueChange={setFilterWelfare}>
              <SelectTrigger className="w-40 h-9" data-testid="member-welfare-filter"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Welfare</SelectItem>
                <SelectItem value="any">Any active case</SelectItem>
                <SelectItem value="sponsored">Sponsored</SelectItem>
                <SelectItem value="restricted_location">In Shelter (Restricted)</SelectItem>
                <SelectItem value="welfare_support">Welfare Support</SelectItem>
                <SelectItem value="multiple">Multiple</SelectItem>
              </SelectContent>
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
                    <Avatar className="h-10 w-10">
                      {m.photo_url ? <img src={m.photo_url} alt="" className="h-10 w-10 rounded-full object-cover" /> : <AvatarFallback className="text-xs bg-primary/10 text-primary">{initials(m.name)}</AvatarFallback>}
                    </Avatar>
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
                    {m.welfare_case && (
                      <Badge variant="outline" className="text-[10px] bg-purple-50 text-purple-700 border-purple-200" title={`Active social-work case (${m.welfare_case.risk_level || 'low'} risk)`}>
                        {(m.welfare_case.category || '').replace(/_/g, ' ')}
                      </Badge>
                    )}
                    <div className="flex gap-1.5">
                      {m.is_medical && <span title="Medical" className="text-red-500"><Heart size={12} /></span>}
                      {m.is_resident && <span title="Resident" className="text-blue-500"><Home size={12} /></span>}
                      {m.has_restricted_access && <span title="Restricted Access" className="text-amber-500"><Shield size={12} /></span>}
                    </div>
                    {isCoordinator && (
                      <div className="flex gap-1" onClick={e => e.stopPropagation()}>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" data-testid={`edit-member-${m.id}`} onClick={async e => { e.stopPropagation(); setDefaultMemberTab('edit'); await handleViewMember(m); }} title="Edit Profile"><Eye size={13} /></Button>
                        {canEditStaff && <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-amber-600" onClick={e => { e.stopPropagation(); setResetPwUser({ ...m, _userId: m.user_id || m.id }); setShowResetPw(true); setNewPassword(''); }} title="Reset Password"><Key size={13} /></Button>}
                        {isCoordinator && <a href={`/admin?user=${m.user_id || m.id}`} className="inline-flex items-center justify-center h-7 w-7 p-0 rounded-md hover:bg-accent text-purple-600" title="Full Admin Edit" onClick={e => e.stopPropagation()}><Shield size={13} /></a>}
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-blue-600" onClick={e => { e.stopPropagation(); setBadgePerson(m); setShowBadge(true); }} title="Badge"><Printer size={13} /></Button>
                        <Button size="sm" variant="ghost" className="text-destructive h-7 w-7 p-0" onClick={e => { e.stopPropagation(); membersApi.delete(m.id).then(() => { toast.success('Deleted'); emitDataChanged('members', m.id); fetchMembers(); }); }}><Trash2 size={13} /></Button>
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
            <div>
            {/* Select All + Bulk Actions for Families */}
            <div className="flex items-center gap-2 mb-2">
              <label className="flex items-center gap-2 text-xs cursor-pointer"><input type="checkbox" className="accent-primary" checked={selFamilies.size > 0 && selFamilies.size === families.length} onChange={() => selFamilies.size === families.length ? setSelFamilies(new Set()) : setSelFamilies(new Set(families.map(f => f.id)))} /> Select All ({families.length})</label>
            </div>
            {selFamilies.size > 0 && <div className="mb-2"><BulkActionBar selectedIds={selFamilies} onClear={() => setSelFamilies(new Set())}
              onBulkEdit={() => setShowBulkFamilyEdit(true)}
              onBulkExport={() => exportToCSV(families.filter(f => selFamilies.has(f.id)), 'families-export.csv')}
              onBulkDelete={async () => { setBulkDeleteTarget({ type: 'families', ids: [...selFamilies], label: 'families' }); }}
            /></div>}
            <div className="space-y-3">
              {families.map(f => (
                <Card key={f.id} className={`shadow-soft rounded-xl ${selFamilies.has(f.id) ? 'ring-2 ring-primary/40' : ''}`} data-testid={`family-card-${f.id}`}>
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <input type="checkbox" className="accent-primary" checked={selFamilies.has(f.id)} onChange={() => setSelFamilies(prev => { const n = new Set(prev); n.has(f.id) ? n.delete(f.id) : n.add(f.id); return n; })} />
                        <div><p className="font-medium">{f.family_name}</p><p className="text-xs text-muted-foreground">{f.primary_contact_name} &middot; {f.primary_contact_phone}</p></div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary" className="text-xs">{childrenForFamily(f.id).length} children</Badge>
                        {isCoordinator && (
                          <div className="flex gap-1">
                            <Button size="sm" variant="ghost" className="h-7 w-7 p-0" data-testid={`edit-family-${f.id}`} onClick={() => openEditFamily(f)} title="Edit"><Eye size={13} /></Button>
                            <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" data-testid={`delete-family-${f.id}`} onClick={() => familiesApi.delete(f.id).then(() => { toast.success('Family deleted'); emitDataChanged('families', f.id); fetchPeople(); }).catch(err => toast.error(err.response?.data?.detail || 'Failed'))}><Trash2 size={13} /></Button>
                          </div>
                        )}
                      </div>
                    </div>
                    {childrenForFamily(f.id).length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">{childrenForFamily(f.id).map(c => <Badge key={c.id} variant="outline" className="text-[10px]">{c.name} ({c.class_group})</Badge>)}</div>
                    )}
                    {(f.guardians || []).length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-1.5">{f.guardians.map(g => <Badge key={g.id} variant="secondary" className="text-[10px]">{g.name} ({g.relationship})</Badge>)}</div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
            </div>
          )}
        </TabsContent>

        {/* CHILDREN TAB */}
        <TabsContent value="children" className="mt-4">
          <div className="flex items-center gap-2 mb-3">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input className="pl-9 h-8 text-sm" placeholder="Search children by name..." value={childSearch} onChange={e => setChildSearch(e.target.value)} data-testid="children-search" />
            </div>
            <Select value={filterWelfare} onValueChange={setFilterWelfare}>
              <SelectTrigger className="w-40 h-8 text-sm" data-testid="children-welfare-filter"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Children</SelectItem>
                <SelectItem value="any">Any active case</SelectItem>
                <SelectItem value="sponsored">Sponsored</SelectItem>
                <SelectItem value="restricted_location">In Shelter (Restricted)</SelectItem>
                <SelectItem value="welfare_support">Welfare Support</SelectItem>
                <SelectItem value="multiple">Multiple</SelectItem>
              </SelectContent>
            </Select>
            <Button size="sm" className="gap-2" onClick={() => setShowChild(true)} data-testid="add-child-btn"><Plus size={14} /> Add Child</Button>
          </div>
          {(() => {
            const filteredChildren = childSearch.trim() ? children.filter(c => (c.name || '').toLowerCase().includes(childSearch.toLowerCase())) : children;
            return filteredChildren.length === 0 ? (
            <Card className="shadow-soft rounded-xl"><CardContent className="py-16 text-center"><Baby size={40} className="mx-auto mb-3 opacity-20" /><p className="text-muted-foreground">{childSearch ? 'No children match search' : 'No children registered'}</p></CardContent></Card>
          ) : (
            <div>
            {/* Select All + Bulk Actions for Children */}
            <div className="flex items-center gap-2 mb-3">
              <label className="flex items-center gap-2 text-xs cursor-pointer"><input type="checkbox" className="accent-primary" checked={selChildren.size > 0 && selChildren.size === children.length} onChange={() => selChildren.size === children.length ? setSelChildren(new Set()) : setSelChildren(new Set(children.map(c => c.id)))} /> Select All ({children.length})</label>
            </div>
            {selChildren.size > 0 && <div className="mb-3"><BulkActionBar selectedIds={selChildren} onClear={() => setSelChildren(new Set())}
              onBulkEdit={() => setShowBulkChildEdit(true)}
              onBulkExport={() => exportToCSV(children.filter(c => selChildren.has(c.id)), 'children-export.csv')}
              onBulkDelete={async () => { setBulkDeleteTarget({ type: 'children', ids: [...selChildren], label: 'children' }); }}
            /></div>}
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {children.length > 0 && filteredChildren.map(c => {
                const isRestricted = c.is_resident || allLocations.find(l => l.id === c.location_id)?.is_restricted;
                // Children of staff with restricted access also get badges
                const parentHasAccess = !isRestricted && (c.parent_ids || []).some(pid => {
                  const parentMember = members.find(m => m.id === pid);
                  return parentMember && (parentMember.role === 'Staff' || parentMember.role === 'Director' || parentMember.role === 'Manager' || parentMember.role === 'Coordinator');
                });
                const canGetBadge = isRestricted || parentHasAccess || c.is_sponsored;
                return (
                <Card key={c.id} className={`shadow-soft rounded-xl ${selChildren.has(c.id) ? 'ring-2 ring-primary/40' : ''}`} data-testid={`child-card-${c.id}`}>
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-start gap-2 flex-1">
                        <input type="checkbox" className="accent-primary mt-1" checked={selChildren.has(c.id)} onChange={() => setSelChildren(prev => { const n = new Set(prev); n.has(c.id) ? n.delete(c.id) : n.add(c.id); return n; })} />
                        <div className="w-9 h-9 rounded-full shrink-0 mt-0.5 overflow-hidden border border-border">
                          {c.photo_url ? <img src={c.photo_url} alt="" className="w-full h-full object-cover" /> : <div className="w-full h-full bg-emerald-50 flex items-center justify-center text-emerald-600 text-xs font-bold">{(c.name || '?')[0]}</div>}
                        </div>
                        <div className="flex-1">
                          <p className="font-medium text-sm">{c.name}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {c.class_group || c.grade ? `${c.grade || ''} ${c.class_group || ''}`.trim() : 'No class'} &middot; DOB: {c.date_of_birth || 'N/A'}
                          </p>
                          {c.school && <p className="text-xs text-muted-foreground">School: {c.school}</p>}
                          <div className="flex flex-wrap gap-1 mt-1">
                            {c.allergies && <Badge variant="destructive" className="text-[10px]">{c.allergies}</Badge>}
                            {c.is_sponsored && <Badge className="text-[10px] bg-purple-100 text-purple-700">Sponsored{c.sponsor_first_name ? ` by ${c.sponsor_first_name}` : ''}</Badge>}
                            {c.is_resident && <Badge className="text-[10px] bg-blue-100 text-blue-700">Resident</Badge>}
                            {isRestricted && <Badge className="text-[10px] bg-amber-100 text-amber-700">Tracked</Badge>}
                            {c.welfare_case && (
                              <Badge variant="outline" className="text-[10px] bg-rose-50 text-rose-700 border-rose-200" title={`Active social-work case (${c.welfare_case.risk_level || 'low'} risk)`}>
                                {(c.welfare_case.category || '').replace(/_/g, ' ')}
                              </Badge>
                            )}
                          </div>
                          <div className="flex gap-1.5 mt-1">
                            {c.is_medical && <span title="Medical enabled" className="text-red-500"><Heart size={12} /></span>}
                            {c.is_resident && <span title="Resident" className="text-blue-500"><Home size={12} /></span>}
                            {c.is_sponsored && <span title="Sponsored" className="text-purple-500"><GraduationCap size={12} /></span>}
                          </div>
                          {c.parent_ids?.length > 0 && <p className="text-[10px] text-muted-foreground mt-1">Parents: {c.parent_ids.map(pid => { const p = guests.find(g => g.id === pid) || members.find(s => s.id === pid); return p?.name; }).filter(Boolean).join(', ') || c.parent_ids.length}</p>}
                        </div>
                      </div>
                      {isCoordinator && (
                        <div className="flex gap-1">
                          {canGetBadge && <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-blue-600" onClick={() => {
                            const loc = allLocations.find(l => l.id === c.location_id);
                            const cParents = (c.parent_ids || []).map(pid => guests.find(g => g.id === pid) || members.find(s => s.id === pid)).filter(Boolean).map(p => ({ name: p.name, phone: p.phone || '' }));
                            setBadgePerson({ ...c, role: 'child', country: loc?.country, country_code: loc?.country_code, location_name: loc?.name, campus_phone: loc?.contact_phone, parents: cParents, is_medical: c.is_medical, is_resident: c.is_resident, is_sponsored: c.is_sponsored });
                            setShowBadge(true);
                          }} title="Print Badge" data-testid={`badge-child-${c.id}`}><Printer size={13} /></Button>}
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0" data-testid={`edit-child-${c.id}`} onClick={() => openEditChild(c)} title="Edit"><Eye size={13} /></Button>
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" onClick={() => childrenApi.delete(c.id).then(() => { toast.success('Deleted'); emitDataChanged('children', c.id); fetchPeople(); })}><Trash2 size={13} /></Button>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
                );
              })}
            </div>
            </div>
          );
          })()}
        </TabsContent>

        {/* GUESTS TAB */}
        <TabsContent value="guests" className="mt-4">
          <div className="flex items-center gap-2 mb-3">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input className="pl-9 h-8 text-sm" placeholder="Search guests by name or phone..." value={guestSearch} onChange={e => setGuestSearch(e.target.value)} data-testid="guests-search" />
            </div>
            <Button size="sm" className="gap-2" onClick={() => setShowGuest(true)} data-testid="add-guest-btn"><Plus size={14} /> Record Guest</Button>
          </div>
          {(() => {
            const filteredGuests = guestSearch.trim() ? guests.filter(g => (g.name || '').toLowerCase().includes(guestSearch.toLowerCase()) || (g.phone || '').includes(guestSearch)) : guests;
            return filteredGuests.length === 0 ? (
            <Card className="shadow-soft rounded-xl"><CardContent className="py-16 text-center"><UserPlus size={40} className="mx-auto mb-3 opacity-20" /><p className="text-muted-foreground">{guestSearch ? 'No guests match search' : 'No guest visits recorded'}</p></CardContent></Card>
          ) : (
            <div>
            {/* Select All + Bulk Actions for Guests */}
            <div className="flex items-center gap-2 mb-2">
              <label className="flex items-center gap-2 text-xs cursor-pointer"><input type="checkbox" className="accent-primary" checked={selGuests.size > 0 && selGuests.size === guests.length} onChange={() => selGuests.size === guests.length ? setSelGuests(new Set()) : setSelGuests(new Set(guests.map(g => g.id)))} /> Select All ({guests.length})</label>
            </div>
            {selGuests.size > 0 && <div className="mb-2"><BulkActionBar selectedIds={selGuests} onClear={() => setSelGuests(new Set())}
              onBulkExport={() => exportToCSV(guests.filter(g => selGuests.has(g.id)), 'guests-export.csv')}
              onBulkDelete={async () => { setBulkDeleteTarget({ type: 'guests', ids: [...selGuests], label: 'guests' }); }}
            /></div>}
            <div className="space-y-2">
              {filteredGuests.map(g => (
                <Card key={g.id} className={`shadow-soft rounded-xl ${selGuests.has(g.id) ? 'ring-2 ring-primary/40' : ''}`} data-testid={`guest-card-${g.id}`}>
                  <CardContent className="p-3 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <input type="checkbox" className="accent-primary" checked={selGuests.has(g.id)} onChange={() => setSelGuests(prev => { const n = new Set(prev); n.has(g.id) ? n.delete(g.id) : n.add(g.id); return n; })} />
                      <div><p className="text-sm font-medium">{g.name}</p><p className="text-xs text-muted-foreground">{g.visit_date} &middot; {g.phone || g.email || ''}</p></div>
                    </div>
                    <div className="flex items-center gap-2">
                      {g.is_parent && <Badge variant="outline" className="text-[10px] border-green-300 text-green-600">Parent</Badge>}
                      {g.referred_by && <Badge variant="secondary" className="text-[10px]">Ref: {g.referred_by}</Badge>}
                      {g.is_medical && <span title="Medical" className="text-red-500"><Heart size={11} /></span>}
                      {g.is_resident && <span title="Resident" className="text-blue-500"><Home size={11} /></span>}
                      <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => openEditGuest(g)} title="Edit" data-testid={`edit-guest-${g.id}`}><Eye size={13} /></Button>
                      <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" data-testid={`delete-guest-${g.id}`} onClick={async (e) => {
                        e.stopPropagation();
                        if (!window.confirm(`Delete guest "${g.name}"?`)) return;
                        try { await guestsApi.delete(g.id); toast.success('Guest deleted'); emitDataChanged('guests', g.id); fetchPeople(); } catch (err) { toast.error(err.response?.data?.detail || 'Delete failed'); }
                      }}><Trash2 size={13} /></Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
            </div>
          );
          })()}
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
              <TabsList><TabsTrigger value="info">Info</TabsTrigger>{canEditStaff && <TabsTrigger value="edit">Edit Profile</TabsTrigger>}<TabsTrigger value="documents">Documents</TabsTrigger></TabsList>
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
            <div className="space-y-1.5"><Label>Campus / Location</Label>
              <Select value={childForm.location_id || ''} onValueChange={v => setChildForm({ ...childForm, location_id: v })}>
                <SelectTrigger><SelectValue placeholder="Select campus" /></SelectTrigger>
                <SelectContent>{allLocations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
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
      <Dialog open={!!editChild} onOpenChange={(o) => { if (!o) { setEditChild(null); setParentSearch(''); } }}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Edit Child: {editChild?.name}</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            {/* Child Photo */}
            <div className="flex items-center gap-3">
              <div className="relative group cursor-pointer" onClick={() => document.getElementById('child-photo-input')?.click()}>
                {editChildForm.photo_url ? (
                  <img src={editChildForm.photo_url} alt="" className="w-14 h-14 rounded-full object-cover border-2 border-border" />
                ) : (
                  <div className="w-14 h-14 rounded-full bg-emerald-50 flex items-center justify-center text-emerald-600 font-bold text-base border-2 border-border">
                    {(editChild?.name || '').split(' ')[0]?.[0] || '?'}
                  </div>
                )}
                <div className="absolute inset-0 rounded-full bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                  <Upload size={14} className="text-white" />
                </div>
                <input id="child-photo-input" type="file" className="hidden" accept="image/*" onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (!file || !editChild) return;
                  setUploadingChildPhoto(true);
                  try {
                    const fd = new FormData(); fd.append('file', file);
                    const res = await api.post(`/children/${editChild.id}/photo`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
                    setEditChildForm(prev => ({ ...prev, photo_url: res.data.photo_url }));
                    toast.success('Photo uploaded');
                  } catch { toast.error('Photo upload failed'); }
                  finally { setUploadingChildPhoto(false); e.target.value = ''; }
                }} />
              </div>
              <div>
                <p className="text-sm font-medium">{editChild?.name}</p>
                <button className="text-xs text-primary hover:underline" onClick={() => document.getElementById('child-photo-input')?.click()} disabled={uploadingChildPhoto}>
                  {uploadingChildPhoto ? 'Uploading...' : 'Change photo'}
                </button>
              </div>
            </div>
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
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>School</Label><Input value={editChildForm.school || ''} onChange={e => setEditChildForm({ ...editChildForm, school: e.target.value })} placeholder="School name" /></div>
              <div className="space-y-1.5"><Label>Grade</Label><Input value={editChildForm.grade || ''} onChange={e => setEditChildForm({ ...editChildForm, grade: e.target.value })} placeholder="e.g. 5th" /></div>
            </div>
            <div className="space-y-1.5"><Label>Campus / Location</Label>
              <Select value={editChildForm.location_id || '__none__'} onValueChange={v => setEditChildForm({ ...editChildForm, location_id: v === '__none__' ? '' : v })}>
                <SelectTrigger><SelectValue placeholder="Select campus" /></SelectTrigger>
                <SelectContent><SelectItem value="__none__">None</SelectItem>{allLocations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            {/* Residency (for restricted locations) */}
            <div className="p-3 border border-border rounded-lg space-y-2">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" className="accent-primary" checked={editChildForm.is_resident || false} onChange={e => setEditChildForm({ ...editChildForm, is_resident: e.target.checked })} />
                Resident of a restricted location
              </label>
              {editChildForm.is_resident && (
                <Select value={editChildForm.resident_location_id || '__none__'} onValueChange={v => setEditChildForm({ ...editChildForm, resident_location_id: v === '__none__' ? '' : v })}>
                  <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="Select restricted location" /></SelectTrigger>
                  <SelectContent><SelectItem value="__none__">None</SelectItem>{allLocations.filter(l => l.is_restricted).map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
                </Select>
              )}
            </div>
            {/* Sponsorship */}
            <div className="p-3 border border-border rounded-lg space-y-2">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" className="accent-primary" checked={editChildForm.is_sponsored || false} onChange={e => setEditChildForm({ ...editChildForm, is_sponsored: e.target.checked, sponsor_first_name: e.target.checked ? editChildForm.sponsor_first_name : '' })} data-testid="child-sponsored-toggle" />
                Sponsored / Supported
              </label>
              {editChildForm.is_sponsored && (
                <Input className="h-8 text-xs" placeholder="Sponsor first name (staff-only visible)" value={editChildForm.sponsor_first_name || ''} onChange={e => setEditChildForm({ ...editChildForm, sponsor_first_name: e.target.value })} data-testid="sponsor-name-input" />
              )}
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" className="accent-primary" checked={editChildForm.is_medical || false} onChange={e => setEditChildForm({ ...editChildForm, is_medical: e.target.checked })} data-testid="child-medical-toggle" />
                Medical Enabled
              </label>
            </div>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label>Parents / Guardians</Label>
                <Button size="sm" variant="outline" className="h-6 text-xs gap-1" onClick={() => setParentSearch(parentSearch ? '' : ' ')} data-testid="add-parent-btn"><Plus size={11} /> Add Parent</Button>
              </div>
              {/* Selected parents */}
              {(editChildForm.parent_ids || []).length > 0 && (
                <div className="space-y-1.5">
                  {(editChildForm.parent_ids || []).map(pid => {
                    const p = guests.find(g => g.id === pid) || members.find(s => s.id === pid);
                    if (!p) return null;
                    return (
                      <div key={pid} className="flex items-center justify-between p-2 rounded-lg border border-border bg-accent/20">
                        <div>
                          <p className="text-sm font-medium">{p.name}</p>
                          <p className="text-[10px] text-muted-foreground">{p.phone || p.email || ''} {p.role ? `(${p.role})` : p.is_parent ? '(Parent)' : ''}</p>
                        </div>
                        <button className="text-destructive" onClick={() => setEditChildForm({ ...editChildForm, parent_ids: (editChildForm.parent_ids || []).filter(id => id !== pid) })}><X size={14} /></button>
                      </div>
                    );
                  })}
                </div>
              )}
              {/* Search to add parents */}
              {parentSearch !== '' && (
                <div className="space-y-1.5">
                  <Input
                    placeholder="Search staff or guests by name or phone..."
                    value={parentSearch.trim() ? parentSearch : ''}
                    onChange={e => setParentSearch(e.target.value)}
                    className="h-8 text-xs"
                    data-testid="parent-search-input"
                    autoFocus
                  />
                  <div className="max-h-36 overflow-y-auto border rounded-lg p-1 space-y-0.5">
                    {(() => {
                      const q = parentSearch.trim().toLowerCase();
                      const currentIds = new Set(editChildForm.parent_ids || []);
                      // Search guests (parents) + all staff
                      const guestMatches = guests.filter(g => !currentIds.has(g.id) && (q.length < 2 || (g.name || '').toLowerCase().includes(q) || (g.phone || '').includes(q)));
                      const staffMatches = members.filter(s => !currentIds.has(s.id) && (q.length < 2 || (s.name || '').toLowerCase().includes(q) || (s.phone || '').includes(q)));
                      const results = [...guestMatches.map(g => ({ ...g, _type: g.is_parent ? 'parent' : 'guest' })), ...staffMatches.map(s => ({ ...s, _type: 'staff' }))].slice(0, 20);
                      if (results.length === 0) return <p className="text-xs text-muted-foreground text-center py-2">No matches found</p>;
                      return results.map(r => (
                        <button key={r.id} type="button" className="w-full text-left p-2 rounded hover:bg-accent/50 text-sm flex items-center justify-between"
                          onClick={() => { setEditChildForm(prev => ({ ...prev, parent_ids: [...(prev.parent_ids || []), r.id] })); setParentSearch(''); }}>
                          <span>{r.name} {r.phone ? <span className="text-muted-foreground text-xs">({r.phone})</span> : ''}</span>
                          <Badge variant="outline" className="text-[9px] capitalize">{r._type}</Badge>
                        </button>
                      ));
                    })()}
                  </div>
                </div>
              )}
              {(editChildForm.parent_ids || []).length === 0 && parentSearch === '' && (
                <p className="text-xs text-muted-foreground py-2">No parents linked. Click "Add Parent" to search.</p>
              )}
            </div>
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
          <div className="space-y-4">
            <button className="text-xs text-primary hover:underline flex items-center gap-1" onClick={() => downloadTemplate('staff', 'members_template.csv')} data-testid="download-members-template"><Download size={12} /> Download CSV Template</button>
            <div className="space-y-2"><Label>CSV File</Label><Input type="file" accept=".csv" onChange={e => setCsvFile(e.target.files?.[0] || null)} data-testid="bulk-csv-file-input" /></div><div className="text-xs text-muted-foreground text-center">— or paste —</div><Textarea rows={5} placeholder="John Doe, john@email.com, +256..." value={bulkData} onChange={e => setBulkData(e.target.value)} /></div>
          <div className="flex gap-3 pt-2"><Button variant="outline" className="flex-1" onClick={() => setShowBulkImport(false)}>Cancel</Button><Button className="flex-1" disabled={importLoading || (!bulkData.trim() && !csvFile)} onClick={handleBulkImport}>{importLoading ? 'Importing...' : 'Import'}</Button></div>
        </DialogContent>
      </Dialog>

      <Dialog open={showChildImport} onOpenChange={setShowChildImport}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto"><DialogHeader><DialogTitle>Import Children & Parents</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <button className="text-xs text-primary hover:underline flex items-center gap-1" onClick={() => downloadTemplate('children', 'children_template.csv')} data-testid="download-children-template"><Download size={12} /> Download CSV Template (includes parent & campus fields)</button>
            <div className="space-y-2"><Label>CSV File</Label><Input type="file" accept=".csv" onChange={e => setChildCsvFile(e.target.files?.[0] || null)} /></div><div className="text-xs text-muted-foreground text-center">— or paste —</div><Textarea rows={5} placeholder="first_name,last_name,..." value={childCsvData} onChange={e => setChildCsvData(e.target.value)} /></div>
          <div className="flex gap-3 pt-2"><Button variant="outline" className="flex-1" onClick={() => setShowChildImport(false)}>Cancel</Button><Button className="flex-1" disabled={importLoading || (!childCsvData.trim() && !childCsvFile)} onClick={handleChildImport}>{importLoading ? 'Importing...' : 'Import'}</Button></div>
        </DialogContent>
      </Dialog>

      <Dialog open={showStaffImport} onOpenChange={setShowStaffImport}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto"><DialogHeader><DialogTitle>Import Staff</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <button className="text-xs text-primary hover:underline flex items-center gap-1" onClick={() => downloadTemplate('staff', 'staff_template.csv')} data-testid="download-staff-template"><Download size={12} /> Download CSV Template</button>
            <div className="space-y-2"><Label>CSV File</Label><Input type="file" accept=".csv" onChange={e => setStaffCsvFile(e.target.files?.[0] || null)} /></div><div className="text-xs text-muted-foreground text-center">— or paste —</div><Textarea rows={5} placeholder="name,email,phone,..." value={staffCsvData} onChange={e => setStaffCsvData(e.target.value)} /></div>
          <div className="flex gap-3 pt-2"><Button variant="outline" className="flex-1" onClick={() => setShowStaffImport(false)}>Cancel</Button><Button className="flex-1" disabled={importLoading || (!staffCsvData.trim() && !staffCsvFile)} onClick={handleStaffImport}>{importLoading ? 'Importing...' : 'Import'}</Button></div>
        </DialogContent>
      </Dialog>


      {/* Edit Guest Dialog */}
      <Dialog open={!!editGuest} onOpenChange={(o) => { if (!o) setEditGuest(null); }}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Edit Guest: {editGuest?.name}</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label>Name *</Label><Input value={editGuestForm.name || ''} onChange={e => setEditGuestForm({...editGuestForm, name: e.target.value})} data-testid="edit-guest-name" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Phone</Label><Input value={editGuestForm.phone || ''} onChange={e => setEditGuestForm({...editGuestForm, phone: e.target.value})} /></div>
              <div className="space-y-1.5"><Label>Email</Label><Input type="email" value={editGuestForm.email || ''} onChange={e => setEditGuestForm({...editGuestForm, email: e.target.value})} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Campus</Label>
                <Select value={editGuestForm.location_id || '_none'} onValueChange={v => setEditGuestForm({...editGuestForm, location_id: v === '_none' ? '' : v})}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent><SelectItem value="_none">None</SelectItem>{allLocations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label>Group</Label>
                <Select value={editGuestForm.group || ''} onValueChange={v => setEditGuestForm({...editGuestForm, group: v})}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>{MOCK_GROUPS.map(g => <SelectItem key={g} value={g}>{g}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" className="accent-primary" checked={editGuestForm.is_parent || false} onChange={e => setEditGuestForm({...editGuestForm, is_parent: e.target.checked})} /> Is Parent
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" className="accent-primary" checked={editGuestForm.is_medical || false} onChange={e => setEditGuestForm({...editGuestForm, is_medical: e.target.checked})} /> Medical Enabled
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" className="accent-primary" checked={editGuestForm.is_resident || false} onChange={e => setEditGuestForm({...editGuestForm, is_resident: e.target.checked})} /> Resident
            </label>
            {editGuestForm.is_resident && (
              <div className="space-y-1.5 pl-4 border-l-2 border-blue-200">
                <Label className="text-xs text-muted-foreground">Restricted Sub-Location</Label>
                <Select value={editGuestForm.resident_location_id || ''} onValueChange={v => setEditGuestForm({...editGuestForm, resident_location_id: v})}>
                  <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="Select location" /></SelectTrigger>
                  <SelectContent>{allLocations.filter(l => l.is_restricted || l.type === 'sub-location').map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            )}
            <div className="space-y-1.5"><Label>Referred By</Label><Input value={editGuestForm.referred_by || ''} onChange={e => setEditGuestForm({...editGuestForm, referred_by: e.target.value})} /></div>
            <div className="space-y-1.5"><Label>Address</Label><Input value={editGuestForm.address || ''} onChange={e => setEditGuestForm({...editGuestForm, address: e.target.value})} /></div>
            <div className="space-y-1.5"><Label>Notes</Label><Textarea rows={2} value={editGuestForm.notes || ''} onChange={e => setEditGuestForm({...editGuestForm, notes: e.target.value})} /></div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setEditGuest(null)}>Cancel</Button>
              <Button className="flex-1" onClick={saveEditGuest} disabled={savingGuest} data-testid="save-guest-btn">{savingGuest ? 'Saving...' : 'Save'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>


      {/* Bulk Edit Children Dialog */}
      <Dialog open={showBulkChildEdit} onOpenChange={setShowBulkChildEdit}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Bulk Edit {selChildren.size} Children</DialogTitle><DialogDescription>Only changed fields will be updated</DialogDescription></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2"><Label className="text-xs">Family</Label>
              <Select value={bulkChildForm.family_id} onValueChange={v => setBulkChildForm(prev => ({...prev, family_id: v === "__none__" ? "" : v}))}>
                <SelectTrigger><SelectValue placeholder="No change" /></SelectTrigger>
                <SelectContent><SelectItem value="__none__">No change</SelectItem>{families.map(f => <SelectItem key={f.id} value={f.id}>{f.family_name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-2"><Label className="text-xs">Campus / Location</Label>
              <Select value={bulkChildForm.location_id} onValueChange={v => setBulkChildForm(prev => ({...prev, location_id: v === "__none__" ? "" : v}))}>
                <SelectTrigger><SelectValue placeholder="No change" /></SelectTrigger>
                <SelectContent><SelectItem value="__none__">No change</SelectItem>{allLocations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-2"><Label className="text-xs">Class / Group</Label>
              <Input placeholder="No change" value={bulkChildForm.class_group} onChange={e => setBulkChildForm(prev => ({...prev, class_group: e.target.value}))} />
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowBulkChildEdit(false)}>Cancel</Button>
              <Button className="flex-1" onClick={async () => {
                const updates = {};
                if (bulkChildForm.family_id) updates.family_id = bulkChildForm.family_id;
                if (bulkChildForm.location_id) updates.location_id = bulkChildForm.location_id;
                if (bulkChildForm.class_group) updates.class_group = bulkChildForm.class_group;
                if (!Object.keys(updates).length) { toast.error('No changes selected'); return; }
                try { await childrenApi.bulkUpdate([...selChildren], updates); toast.success(`Updated ${selChildren.size} children`); setShowBulkChildEdit(false); setSelChildren(new Set()); setBulkChildForm({ family_id: '', location_id: '', class_group: '' }); fetchPeople(); }
                catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
              }}>Apply to {selChildren.size} Children</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Bulk Edit Families Dialog */}
      <Dialog open={showBulkFamilyEdit} onOpenChange={setShowBulkFamilyEdit}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Bulk Edit {selFamilies.size} Families</DialogTitle><DialogDescription>Only changed fields will be updated</DialogDescription></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2"><Label className="text-xs">Campus / Location</Label>
              <Select value={bulkFamilyForm.location_id} onValueChange={v => setBulkFamilyForm(prev => ({...prev, location_id: v === "__none__" ? "" : v}))}>
                <SelectTrigger><SelectValue placeholder="No change" /></SelectTrigger>
                <SelectContent><SelectItem value="__none__">No change</SelectItem>{allLocations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowBulkFamilyEdit(false)}>Cancel</Button>
              <Button className="flex-1" onClick={async () => {
                const updates = {};
                if (bulkFamilyForm.location_id) updates.location_id = bulkFamilyForm.location_id;
                if (!Object.keys(updates).length) { toast.error('No changes selected'); return; }
                try { await familiesApi.bulkUpdate([...selFamilies], updates); toast.success(`Updated ${selFamilies.size} families`); setShowBulkFamilyEdit(false); setSelFamilies(new Set()); setBulkFamilyForm({ location_id: '' }); fetchPeople(); }
                catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
              }}>Apply to {selFamilies.size} Families</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Badge Dialog */}
      <Dialog open={showBadge} onOpenChange={setShowBadge}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Badge — {badgePerson?.name}</DialogTitle></DialogHeader>
          {badgePerson && <div className="mt-2"><UnifiedBadge person={{ ...badgePerson, country: allLocations.find(l => l.id === badgePerson.location_id)?.country, country_code: allLocations.find(l => l.id === badgePerson.location_id)?.country_code }} canWriteNfc={isDirector} /></div>}
        </DialogContent>
      </Dialog>

      {/* Reset Password Dialog */}
      <Dialog open={showResetPw} onOpenChange={setShowResetPw}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Reset Password</DialogTitle>
            <DialogDescription>Set a new password for {resetPwUser?.name}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>New Password</Label>
              <Input type="password" placeholder="Min 6 characters" value={newPassword} onChange={e => setNewPassword(e.target.value)} data-testid="reset-pw-input" />
            </div>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => { setShowResetPw(false); setNewPassword(''); }}>Cancel</Button>
              <Button className="flex-1" disabled={newPassword.length < 6} onClick={async () => {
                try {
                  const res = await adminApi.resetPassword(resetPwUser._userId || resetPwUser.user_id || resetPwUser.id, newPassword);
                  const emailSent = res.data?.email_sent;
                  toast.success(emailSent ? `Password reset and email sent to ${resetPwUser.email}` : `Password reset to: ${newPassword} (share manually)`, { duration: 8000 });
                  setShowResetPw(false); setNewPassword('');
                } catch (err) { toast.error(err.response?.data?.detail || 'Reset failed'); }
              }} data-testid="confirm-reset-pw">Reset Password</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Bulk Delete Confirmation */}
      <BulkDeleteConfirm
        open={!!bulkDeleteTarget}
        onOpenChange={(o) => { if (!o) setBulkDeleteTarget(null); }}
        count={bulkDeleteTarget?.ids?.length || 0}
        itemType={bulkDeleteTarget?.label || 'items'}
        onConfirm={async () => {
          if (!bulkDeleteTarget) return;
          const { type, ids } = bulkDeleteTarget;
          try {
            if (type === 'members') { await adminApi.bulkDeleteMembers(ids); emitDataChanged('members'); fetchMembers(); }
            else if (type === 'children') { await childrenApi.bulkDelete(ids); emitDataChanged('children'); fetchPeople(); }
            else if (type === 'families') { await familiesApi.bulkDelete(ids); emitDataChanged('families'); fetchPeople(); }
            else if (type === 'guests') { await guestsApi.bulkDelete(ids); emitDataChanged('guests'); fetchPeople(); }
            toast.success(`Deleted ${ids.length} ${bulkDeleteTarget.label}`);
            setSelectedMemberIds(new Set()); setSelChildren(new Set()); setSelFamilies(new Set()); setSelGuests(new Set());
          } catch (e) { toast.error(e.message || 'Delete failed'); }
          setBulkDeleteTarget(null);
        }}
      />
    </div>
  );
}
