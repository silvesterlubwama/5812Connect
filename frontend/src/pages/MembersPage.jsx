import { secureStorage } from '../services/secureStorage';
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
import { membersApi, checkinsApi, approvalsApi, badgesApi, exportApi, importApi, locationsApi, csvUploadApi, adminApi } from '../services/api';
import { BulkActionBar, exportToCSV, SelectCheckbox } from '../components/BulkActions';
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
  const [newMember, setNewMember] = useState({ name: '', email: '', phone: '', national_id: '', role: 'Staff', group: 'Youth', gender: 'male', date_of_birth: '', address: '', notes: '', location_id: '', department: '', program: '', is_parent: false, is_customer: false, is_donor: false });
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
  const [importCountry, setImportCountry] = useState('');
  const [allLocations, setAllLocations] = useState([]);
  const [memberDocuments, setMemberDocuments] = useState([]);
  const [docFile, setDocFile] = useState(null);
  const [docType, setDocType] = useState('id_scan');
  const [docLabel, setDocLabel] = useState('');
  const [docLoading, setDocLoading] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [showBulkEdit, setShowBulkEdit] = useState(false);
  const [bulkEditForm, setBulkEditForm] = useState({ status: '', group: '', role: '', location_id: '' });
  const [docUploading, setDocUploading] = useState(false);
  const [csvFile, setCsvFile] = useState(null);
  const [childCsvFile, setChildCsvFile] = useState(null);
  const [staffCsvFile, setStaffCsvFile] = useState(null);

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
    approvalsApi.pending().then(r => setPendingMembers(r.data.members || [])).catch(() => {});
    badgesApi.list().then(r => setBadges(r.data)).catch(() => {});
    locationsApi.list().then(r => setAllLocations(r.data)).catch(() => {});
  }, []);

  const selectedLocation = allLocations.find(l => l.id === newMember.location_id);
  const departmentOptions = selectedLocation
    ? (selectedLocation.departments?.length ? selectedLocation.departments : [selectedLocation.name])
    : [];
  const primaryProgramRole = ['Parent', 'Customer', 'Guest', 'Child'].includes(newMember.role);
  const showProgramField = primaryProgramRole || newMember.is_parent;
  const showDepartmentField = !primaryProgramRole;

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
    setImportLoading(true);
    try {
      if (csvFile) {
        const formData = new FormData();
        formData.append('file', csvFile);
        const res = await csvUploadApi.uploadMembers(formData);
        toast.success(`Imported ${res.data.imported} members from CSV file!`);
        if (res.data.errors?.length > 0) toast.warning(`${res.data.errors.length} rows had errors`);
      } else if (bulkData.trim()) {
        const lines = bulkData.trim().split('\n').map(l => {
          const [name, email, phone, group] = l.split(',').map(s => s.trim());
          return { name, email, phone, group: group || 'Youth', role: 'Member' };
        }).filter(m => m.name);
        const res = await approvalsApi.bulkImport(lines);
        toast.success(`Imported ${res.data.imported || lines.length} members!`);
      } else return;
      setShowBulkImport(false);
      setBulkData('');
      setCsvFile(null);
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
    const token = secureStorage.getToken();
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
    setImportLoading(true);
    try {
      if (childCsvFile) {
        const formData = new FormData();
        formData.append('file', childCsvFile);
        const res = await csvUploadApi.uploadChildrenParents(formData);
        toast.success(`Imported: ${res.data.imported_children} children, ${res.data.imported_parents} parents, ${res.data.imported_families} families`);
        if (res.data.errors?.length > 0) toast.warning(`${res.data.errors.length} rows had errors`);
      } else if (childCsvData.trim()) {
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
      } else return;
      setShowChildImport(false);
      setChildCsvData('');
      setChildCsvFile(null);
      fetchMembers();
    } catch { toast.error('Import failed'); }
    finally { setImportLoading(false); }
  };

  const handleStaffImport = async () => {
    setImportLoading(true);
    try {
      if (staffCsvFile) {
        const formData = new FormData();
        formData.append('file', staffCsvFile);
        const res = await csvUploadApi.uploadStaff(formData);
        toast.success(`Imported ${res.data.imported} staff members from CSV file!`);
        if (res.data.errors?.length > 0) toast.warning(`${res.data.errors.length} rows had errors`);
      } else if (staffCsvData.trim()) {
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
      } else return;
      setShowStaffImport(false);
      setStaffCsvData('');
      setStaffCsvFile(null);
      fetchMembers();
    } catch { toast.error('Import failed'); }
    finally { setImportLoading(false); }
  };

  const fetchDocuments = async (memberId) => {
    setDocLoading(true);
    try {
      const res = await membersApi.documents(memberId);
      setMemberDocuments(res.data);
    } catch {
      setMemberDocuments([]);
    } finally {
      setDocLoading(false);
    }
  };

  const handleUploadDocument = async () => {
    if (!docFile || !selectedMember) return;
    setDocUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', docFile);
      formData.append('doc_type', docType);
      if (docLabel) formData.append('label', docLabel);
      const res = await membersApi.uploadDocument(selectedMember.id, formData);
      setMemberDocuments(prev => [res.data, ...prev]);
      setDocFile(null);
      setDocLabel('');
      toast.success('Document uploaded');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed');
    } finally {
      setDocUploading(false);
    }
  };

  const handleDownloadDocument = async (doc) => {
    try {
      const res = await membersApi.downloadDocument(doc.id);
      const blobUrl = URL.createObjectURL(res.data);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = doc.original_filename || 'document';
      link.click();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
    } catch {
      toast.error('Download failed');
    }
  };

  const handleArchiveDocument = async (docId) => {
    try {
      await membersApi.archiveDocument(docId);
      setMemberDocuments(prev => prev.filter(d => d.id !== docId));
      toast.success('Document archived');
    } catch {
      toast.error('Archive failed');
    }
  };

  const handleLocationChange = (value) => {
    const locationId = value === '_none' ? '' : value;
    const location = allLocations.find(l => l.id === locationId);
    let nextDepartment = showDepartmentField ? (newMember.department || '') : '';
    if (location && showDepartmentField) {
      const allowedDepartments = location.departments?.length ? location.departments : [location.name];
      if (!allowedDepartments.includes(nextDepartment)) {
        nextDepartment = location.type === 'sub-location' ? location.name : '';
      }
    } else if (!location) {
      nextDepartment = '';
    }
    setNewMember({ ...newMember, location_id: locationId, department: nextDepartment });
  };

  const handleAddMember = async (e) => {
    e.preventDefault();
    setSavingMember(true);
    try {
      const res = await membersApi.create(newMember);
      setMembers(prev => [res.data, ...prev]);
      setShowAddDialog(false);
      setNewMember({ name: '', email: '', phone: '', national_id: '', role: 'Member', group: 'Youth', gender: 'male', date_of_birth: '', address: '', notes: '', location_id: '', department: '', program: '', is_parent: false, is_customer: false, is_donor: false });
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
    fetchDocuments(member.id);
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
          <Button variant="outline" size="sm" onClick={fetchMembers} className="gap-1.5" data-testid="refresh-members-btn"><RefreshCw size={14} /></Button>
          <Button variant="outline" size="sm" onClick={downloadCSV} className="gap-1.5" data-testid="export-members-btn"><Download size={14} /> CSV</Button>
          <Select onValueChange={v => { if (v === 'bulk') setShowBulkImport(true); else if (v === 'children') setShowChildImport(true); else if (v === 'staff') setShowStaffImport(true); }}>
            <SelectTrigger className="w-auto h-8 gap-1.5 text-xs" data-testid="members-import-select"><FileUp size={14} /><span>Import</span></SelectTrigger>
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
          <Input placeholder="Search name, email, phone, ID..." className="pl-9" value={search} onChange={e => setSearch(e.target.value)} data-testid="member-search-input" />
        </div>
        <Select value={filterGroup} onValueChange={setFilterGroup}>
          <SelectTrigger className="w-full sm:w-40" data-testid="member-group-filter-select">
            <Filter size={14} className="mr-1.5 text-muted-foreground shrink-0" />
            <SelectValue placeholder="Group" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Groups</SelectItem>
            {MOCK_GROUPS.map(g => <SelectItem key={g} value={g}>{g}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={filterStatus} onValueChange={setFilterStatus}>
          <SelectTrigger className="w-full sm:w-36" data-testid="member-status-filter-select">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="inactive">Inactive</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Bulk Action Bar */}
      <BulkActionBar selectedIds={selectedIds} onClear={() => setSelectedIds(new Set())}
        onBulkEdit={() => setShowBulkEdit(true)}
        onBulkDelete={async () => {
          if (!window.confirm(`Delete ${selectedIds.size} members?`)) return;
          try { await adminApi.bulkDeleteMembers([...selectedIds]); toast.success(`Deleted ${selectedIds.size} members`); setSelectedIds(new Set()); fetchMembers(); }
          catch (e) { toast.error(e.message || 'Failed'); }
        }}
        onBulkExport={async () => {
          try { const res = await membersApi.bulkExport([...selectedIds]); exportToCSV(res.data, 'members-export.csv'); toast.success('Exported!'); }
          catch (e) { toast.error(e.message || 'Export failed'); }
        }}
      />

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
            <Card key={member.id} className="shadow-soft rounded-xl hover:shadow-soft-lg transition-shadow" data-testid={`member-card-${member.id}`}>
              <CardContent className="p-4">
                <div className="flex items-start gap-3 mb-3">
                  <SelectCheckbox id={member.id} checked={selectedIds.has(member.id)} onChange={() => setSelectedIds(prev => { const next = new Set(prev); next.has(member.id) ? next.delete(member.id) : next.add(member.id); return next; })} />
                  <Avatar className="h-10 w-10">
                    <AvatarFallback className={`text-sm font-semibold ${member.status === 'active' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}>
                      {initials(member.name)}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold truncate" data-testid={`member-name-${member.id}`}>{member.name}</p>
                    <p className="text-xs text-muted-foreground" data-testid={`member-role-${member.id}`}>{member.role}</p>
                  </div>
                  <Badge variant={member.status === 'active' ? 'outline' : 'secondary'} className={`text-xs shrink-0 ${member.status === 'active' ? 'border-green-500 text-green-600' : ''}`} data-testid={`member-status-${member.id}`}>
                    {member.status}
                  </Badge>
                </div>
                <div className="space-y-1.5 text-xs text-muted-foreground mb-3">
                  {member.email && <div className="flex items-center gap-2" data-testid={`member-email-${member.id}`}><Mail size={12} /><span className="truncate">{member.email}</span></div>}
                  {member.phone && <div className="flex items-center gap-2" data-testid={`member-phone-${member.id}`}><Phone size={12} /><span>{member.phone}</span></div>}
                  {member.join_date && <div className="flex items-center gap-2" data-testid={`member-join-date-${member.id}`}><span className="text-muted-foreground/70">Joined:</span><span>{member.join_date}</span></div>}
                </div>
                <div className="flex items-center justify-between mt-2">
                  <div className="flex items-center gap-1 flex-wrap">
                    <Badge variant="secondary" className="text-xs" data-testid={`member-group-${member.id}`}>{member.group}</Badge>
                    {member.is_parent && <Badge variant="outline" className="text-xs border-purple-300 text-purple-600" data-testid={`member-flag-parent-${member.id}`}>Parent</Badge>}
                    {member.is_customer && <Badge variant="outline" className="text-xs border-green-300 text-green-600" data-testid={`member-flag-customer-${member.id}`}>Customer</Badge>}
                    {member.is_donor && <Badge variant="outline" className="text-xs border-amber-300 text-amber-600" data-testid={`member-flag-donor-${member.id}`}>Donor</Badge>}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => viewMember(member)} data-testid={`view-member-${member.id}`}>
                      <Eye size={13} />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => toggleStatus(member)} data-testid={`toggle-member-${member.id}`}>
                      {member.status === 'active' ? <UserX size={13} className="text-muted-foreground" /> : <UserCheck size={13} className="text-green-600" />}
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive hover:text-destructive" onClick={() => deleteMember(member)} data-testid={`delete-member-${member.id}`}>
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
          <Button variant="outline" className="mt-4" onClick={() => setShowAddDialog(true)} data-testid="add-first-member-btn">Add your first member</Button>
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
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={() => handleDeleteBadge(b.id)} data-testid={`delete-badge-${b.id}`}>
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
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Add New Member</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleAddMember} className="space-y-4 mt-2">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2 col-span-2">
                <Label>Full Name *</Label>
                <Input placeholder="Full name" value={newMember.name} onChange={e => setNewMember({...newMember, name: e.target.value})} required data-testid="member-name-input" />
              </div>
              <div className="space-y-2">
                <Label>Email</Label>
                <Input type="email" placeholder="email@example.com" value={newMember.email} onChange={e => setNewMember({...newMember, email: e.target.value})} data-testid="member-email-input" />
              </div>
              <div className="space-y-2">
                <Label>Phone</Label>
                <Input placeholder="+256 700 000000" value={newMember.phone} onChange={e => setNewMember({...newMember, phone: e.target.value})} data-testid="member-phone-input" />
              </div>
              <div className="space-y-2 col-span-2">
                <Label>National ID</Label>
                <Input placeholder="CM000000000XXXX" value={newMember.national_id} onChange={e => setNewMember({...newMember, national_id: e.target.value})} data-testid="member-national-id-input" />
              </div>
              <div className="space-y-2">
                <Label>Role</Label>
                <Select value={newMember.role} onValueChange={v => {
                  const isPrimaryProgramRole = ['Parent', 'Customer', 'Guest', 'Child'].includes(v);
                  setNewMember({ ...newMember, role: v, department: isPrimaryProgramRole ? '' : newMember.department });
                }}>
                  <SelectTrigger data-testid="member-role-select"><SelectValue /></SelectTrigger>
                  <SelectContent>{MOCK_ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Group</Label>
                <Select value={newMember.group} onValueChange={v => setNewMember({...newMember, group: v})}>
                  <SelectTrigger data-testid="member-group-select"><SelectValue /></SelectTrigger>
                  <SelectContent>{MOCK_GROUPS.map(g => <SelectItem key={g} value={g}>{g}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Gender</Label>
                <Select value={newMember.gender} onValueChange={v => setNewMember({...newMember, gender: v})}>
                  <SelectTrigger data-testid="member-gender-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="male">Male</SelectItem>
                    <SelectItem value="female">Female</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Date of Birth</Label>
                <Input type="date" value={newMember.date_of_birth} onChange={e => setNewMember({...newMember, date_of_birth: e.target.value})} data-testid="member-dob-input" />
              </div>
              <div className="space-y-2 col-span-2">
                <Label>Address</Label>
                <Input placeholder="Physical address" value={newMember.address} onChange={e => setNewMember({...newMember, address: e.target.value})} data-testid="member-address-input" />
              </div>
              <div className="space-y-2">
                <Label>Location</Label>
                <Select value={newMember.location_id || '_none'} onValueChange={handleLocationChange}>
                  <SelectTrigger data-testid="member-location-select"><SelectValue placeholder="Select location" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_none">Not assigned</SelectItem>
                    {allLocations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              {showProgramField && (
                <div className="space-y-2">
                  <Label>Program</Label>
                  <Input placeholder="e.g. Outreach Programme" value={newMember.program || ''} onChange={e => setNewMember({ ...newMember, program: e.target.value })} data-testid="member-program-input" />
                </div>
              )}
              {showDepartmentField && (
                <div className="space-y-2">
                  <Label>Department</Label>
                  <Select value={newMember.department || '_none'} onValueChange={v => setNewMember({ ...newMember, department: v === '_none' ? '' : v })}>
                    <SelectTrigger data-testid="member-department-select"><SelectValue placeholder="Select department" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="_none">No department</SelectItem>
                      {departmentOptions.map(dep => <SelectItem key={dep} value={dep}>{dep}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              )}
              <div className="col-span-2 space-y-3 p-3 border border-border rounded-lg">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Additional Roles</p>
                <div className="flex items-center justify-between">
                  <p className="text-sm">Also a Parent</p>
                  <Switch checked={newMember.is_parent} onCheckedChange={v => setNewMember({ ...newMember, is_parent: v })} data-testid="member-is-parent-switch" />
                </div>
                <div className="flex items-center justify-between">
                  <p className="text-sm">Also a Customer</p>
                  <Switch checked={newMember.is_customer} onCheckedChange={v => setNewMember({ ...newMember, is_customer: v })} data-testid="member-is-customer-switch" />
                </div>
                <div className="flex items-center justify-between">
                  <p className="text-sm">Also a Donor</p>
                  <Switch checked={newMember.is_donor} onCheckedChange={v => setNewMember({ ...newMember, is_donor: v })} data-testid="member-is-donor-switch" />
                </div>
              </div>
              <div className="space-y-2 col-span-2">
                <Label>Notes</Label>
                <Input placeholder="Any notes..." value={newMember.notes} onChange={e => setNewMember({...newMember, notes: e.target.value})} data-testid="member-notes-input" />
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
      <Dialog open={!!selectedMember} onOpenChange={() => { setSelectedMember(null); setMemberDetail(null); setMemberDocuments([]); setDocFile(null); setDocLabel(''); setDocType('id_scan'); }}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
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
                  <TabsTrigger value="info" data-testid="member-profile-tab">Profile Info</TabsTrigger>
                  <TabsTrigger value="checkins" data-testid="member-checkins-tab">Check-In History ({memberDetail.checkin_history?.length ?? 0})</TabsTrigger>
                  <TabsTrigger value="documents" data-testid="member-documents-tab">Documents ({memberDocuments.length})</TabsTrigger>
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
                      { label: 'Department', value: memberDetail.department },
                      { label: 'Program', value: memberDetail.program },
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

                <TabsContent value="documents" className="mt-4">
                  <div className="space-y-4">
                    <div className="p-4 border border-border rounded-lg space-y-3" data-testid="member-documents-upload-card">
                      <div>
                        <p className="text-sm font-semibold">Upload Document</p>
                        <p className="text-xs text-muted-foreground">ID scans required for all except children. JPG/PNG only.</p>
                      </div>
                      <div className="grid sm:grid-cols-2 gap-3">
                        <div className="space-y-2">
                          <Label>Document Type</Label>
                          <Select value={docType} onValueChange={setDocType}>
                            <SelectTrigger data-testid="doc-type-select"><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="id_scan">ID Scan</SelectItem>
                              <SelectItem value="contract">Contract</SelectItem>
                              <SelectItem value="certificate">Certificate</SelectItem>
                              <SelectItem value="other">Other</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="space-y-2">
                          <Label>Label</Label>
                          <Input value={docLabel} onChange={e => setDocLabel(e.target.value)} placeholder="Optional label" data-testid="doc-label-input" />
                        </div>
                        <div className="space-y-2 sm:col-span-2">
                          <Label>Document File (JPG/PNG)</Label>
                          <Input type="file" accept=".jpg,.jpeg,.png" onChange={e => setDocFile(e.target.files?.[0] || null)} data-testid="doc-file-input" />
                        </div>
                      </div>
                      <div className="flex justify-end">
                        <Button onClick={handleUploadDocument} disabled={!docFile || docUploading} data-testid="upload-document-btn">
                          {docUploading ? 'Uploading...' : 'Upload Document'}
                        </Button>
                      </div>
                    </div>

                    <div>
                      <p className="text-sm font-semibold mb-2">Documents</p>
                      {docLoading ? (
                        <div className="space-y-2">
                          {[1, 2].map(i => <div key={i} className="h-12 bg-muted animate-pulse rounded" />)}
                        </div>
                      ) : memberDocuments.length === 0 ? (
                        <p className="text-sm text-muted-foreground text-center py-6" data-testid="no-documents-text">No documents uploaded yet.</p>
                      ) : (
                        <div className="space-y-2">
                          {memberDocuments.map(doc => (
                            <div key={doc.id} className="flex items-center justify-between p-3 rounded-lg border border-border" data-testid={`member-document-${doc.id}`}>
                              <div>
                                <p className="text-sm font-medium">{doc.label || doc.doc_type}</p>
                                <p className="text-xs text-muted-foreground">{doc.original_filename} · {new Date(doc.created_at).toLocaleString()}</p>
                              </div>
                              <div className="flex gap-2">
                                <Button size="sm" variant="outline" onClick={() => handleDownloadDocument(doc)} data-testid={`doc-download-${doc.id}`}>Download</Button>
                                <Button size="sm" variant="ghost" onClick={() => handleArchiveDocument(doc.id)} data-testid={`doc-archive-${doc.id}`}>Archive</Button>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
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
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Bulk Import Members</DialogTitle>
            <DialogDescription>Upload a CSV file or paste data below (name, email, phone, group per line)</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label>Upload CSV File</Label>
                <Input type="file" accept=".csv" onChange={e => setCsvFile(e.target.files?.[0] || null)} data-testid="bulk-csv-file-input" />
              </div>
              <div className="space-y-2">
                <Label>Country</Label>
                <Select value={importCountry} onValueChange={setImportCountry}>
                  <SelectTrigger><SelectValue placeholder="Select country..." /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">Not specified</SelectItem>
                    <SelectItem value="UG">Uganda</SelectItem>
                    <SelectItem value="US">United States</SelectItem>
                    <SelectItem value="KE">Kenya</SelectItem>
                    <SelectItem value="TH">Thailand</SelectItem>
                    <SelectItem value="HT">Haiti</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="text-xs text-muted-foreground text-center">— or paste below —</div>
            <Textarea
              rows={6}
              placeholder={`John Doe, john@email.com, +256700111222, Youth\nJane Smith, jane@email.com, +256700333444, Women`}
              value={bulkData}
              onChange={e => setBulkData(e.target.value)}
              data-testid="bulk-import-textarea"
            />
          </div>
          <div className="flex gap-3 pt-2">
            <Button type="button" variant="outline" className="flex-1" onClick={() => setShowBulkImport(false)}>Cancel</Button>
            <Button className="flex-1" disabled={importLoading || (!bulkData.trim() && !csvFile)} onClick={handleBulkImport} data-testid="import-btn">
              {importLoading ? 'Importing...' : 'Import Members'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Create Badge Dialog */}
      <Dialog open={showBadgeDialog} onOpenChange={setShowBadgeDialog}>
        <DialogContent className="max-w-sm max-h-[85vh] overflow-y-auto">
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
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Import Children & Parents</DialogTitle>
            <DialogDescription>Upload a CSV file or paste data with header: first_name, last_name, date_of_birth, grade, family_name, fathers_names, fathers_phone, mothers_names, mothers_phone, allergies, medical_notes, special_needs</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label>Upload CSV File</Label>
                <Input type="file" accept=".csv" onChange={e => setChildCsvFile(e.target.files?.[0] || null)} data-testid="child-csv-file-input" />
              </div>
              <div className="space-y-2">
                <Label>Country</Label>
                <Select value={importCountry} onValueChange={setImportCountry}>
                  <SelectTrigger><SelectValue placeholder="Select country..." /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">Not specified</SelectItem>
                    <SelectItem value="UG">Uganda</SelectItem>
                    <SelectItem value="US">United States</SelectItem>
                    <SelectItem value="KE">Kenya</SelectItem>
                    <SelectItem value="TH">Thailand</SelectItem>
                    <SelectItem value="HT">Haiti</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="text-xs text-muted-foreground text-center">— or paste below —</div>
            <Textarea rows={6} placeholder={`first_name,last_name,date_of_birth,grade,family_name,...\nJohn,Doe,2015-05-10,3,Doe Family,...`}
              value={childCsvData} onChange={e => setChildCsvData(e.target.value)} data-testid="child-import-textarea" />
          </div>
          <div className="flex gap-3 pt-2">
            <Button variant="outline" className="flex-1" onClick={() => setShowChildImport(false)}>Cancel</Button>
            <Button className="flex-1" disabled={importLoading || (!childCsvData.trim() && !childCsvFile)} onClick={handleChildParentImport} data-testid="import-children-btn">
              {importLoading ? 'Importing...' : 'Import Children & Parents'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Staff CSV Import */}
      <Dialog open={showStaffImport} onOpenChange={setShowStaffImport}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Import Staff</DialogTitle>
            <DialogDescription>Upload a CSV file or paste data with header: name, email, phone, national_id, role, department</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label>Upload CSV File</Label>
                <Input type="file" accept=".csv" onChange={e => setStaffCsvFile(e.target.files?.[0] || null)} data-testid="staff-csv-file-input" />
              </div>
              <div className="space-y-2">
                <Label>Country</Label>
                <Select value={importCountry} onValueChange={setImportCountry}>
                  <SelectTrigger><SelectValue placeholder="Select country..." /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">Not specified</SelectItem>
                    <SelectItem value="UG">Uganda</SelectItem>
                    <SelectItem value="US">United States</SelectItem>
                    <SelectItem value="KE">Kenya</SelectItem>
                    <SelectItem value="TH">Thailand</SelectItem>
                    <SelectItem value="HT">Haiti</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="text-xs text-muted-foreground text-center">— or paste below —</div>
            <Textarea rows={6} placeholder={`name,email,phone,national_id,role,department\nJane Smith,jane@example.com,...`}
              value={staffCsvData} onChange={e => setStaffCsvData(e.target.value)} data-testid="staff-import-textarea" />
          </div>
          <div className="flex gap-3 pt-2">
            <Button variant="outline" className="flex-1" onClick={() => setShowStaffImport(false)}>Cancel</Button>
            <Button className="flex-1" disabled={importLoading || (!staffCsvData.trim() && !staffCsvFile)} onClick={handleStaffImport} data-testid="import-staff-btn">
              {importLoading ? 'Importing...' : 'Import Staff'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Bulk Edit Dialog */}
      <Dialog open={showBulkEdit} onOpenChange={setShowBulkEdit}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Bulk Edit {selectedIds.size} Members</DialogTitle>
            <DialogDescription>Only fields you change will be updated. Leave blank to keep current values.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label className="text-xs">Status</Label>
                <Select value={bulkEditForm.status} onValueChange={v => setBulkEditForm(prev => ({...prev, status: v}))}>
                  <SelectTrigger><SelectValue placeholder="No change" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">No change</SelectItem>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="inactive">Inactive</SelectItem>
                    <SelectItem value="pending">Pending</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-xs">Role</Label>
                <Select value={bulkEditForm.role} onValueChange={v => setBulkEditForm(prev => ({...prev, role: v}))}>
                  <SelectTrigger><SelectValue placeholder="No change" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">No change</SelectItem>
                    {(MOCK_ROLES || ['Staff','Volunteer','Member','Parent','Customer','Guest']).map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label className="text-xs">Group</Label>
                <Select value={bulkEditForm.group} onValueChange={v => setBulkEditForm(prev => ({...prev, group: v}))}>
                  <SelectTrigger><SelectValue placeholder="No change" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">No change</SelectItem>
                    {(MOCK_GROUPS || ['General','Youth','Women','Men','Children','Leadership']).map(g => <SelectItem key={g} value={g}>{g}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-xs">Location</Label>
                <Select value={bulkEditForm.location_id} onValueChange={v => setBulkEditForm(prev => ({...prev, location_id: v}))}>
                  <SelectTrigger><SelectValue placeholder="No change" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">No change</SelectItem>
                    {allLocations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowBulkEdit(false)}>Cancel</Button>
              <Button className="flex-1" data-testid="apply-bulk-edit" onClick={async () => {
                const updates = {};
                if (bulkEditForm.status) updates.status = bulkEditForm.status;
                if (bulkEditForm.role) updates.role = bulkEditForm.role;
                if (bulkEditForm.group) updates.group = bulkEditForm.group;
                if (bulkEditForm.location_id) updates.location_id = bulkEditForm.location_id;
                if (Object.keys(updates).length === 0) { toast.error('No changes selected'); return; }
                try {
                  const res = await adminApi.bulkUpdateMembers([...selectedIds], updates);
                  toast.success(`Updated ${res.data.updated || selectedIds.size} members`);
                  setShowBulkEdit(false);
                  setSelectedIds(new Set());
                  setBulkEditForm({ status: '', group: '', role: '', location_id: '' });
                  fetchMembers();
                } catch (e) { toast.error(e.response?.data?.detail || 'Bulk update failed'); }
              }}>Apply to {selectedIds.size} Members</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
