import React, { useRef, useState, useEffect } from 'react';
import { X, Plus, Upload, Download, FileText, AlertCircle, Bluetooth, Wifi, Monitor } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Badge } from '../ui/badge';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Textarea } from '../ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog';
import { documentsApi } from '../../services/api';
import api from '../../services/api';
import { toast } from 'sonner';
import { useUnsavedWarning, useFormDirty } from '../../hooks/useUnsavedWarning';
import ActivityFeed from '../ActivityFeed';

const ROLES = ['Executive Director', 'Adviser', 'Director', 'Manager', 'Coordinator', 'Staff', 'HR', 'Volunteer', 'Security Contractor', 'Member', 'Parent', 'Customer', 'Guest'];
const GROUPS = ['General', 'Staff', 'Volunteers', 'Youth', 'Women', 'Men', 'Children', 'Leadership'];
const ID_TYPE_LABELS = {
  national_id: 'National ID', state_id: 'State ID', drivers_license: "Driver's Licence",
  passport: 'Passport', birth_certificate: 'Birth Certificate', refugee_id: 'Refugee ID',
  alien_id: 'Alien ID', voter_card: 'Voter Card', student_id: 'Student ID',
  employee_id: 'Employee ID', other: 'Other',
};

export function UserEditDialog({ open, onOpenChange, selectedUser, editForm, setEditForm, locations, saving, onSave, memberDocs, setMemberDocs, docRequests, setDocRequests, docsLoading, currentUserRole }) {
  const fileInputRef = useRef(null);
  const photoInputRef = useRef(null);
  const [uploadDocType, setUploadDocType] = useState('other');
  const [uploadingDoc, setUploadingDoc] = useState(false);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const [showScanner, setShowScanner] = useState(false);
  const [scannerStatus, setScannerStatus] = useState('idle');
  const [showDocRequest, setShowDocRequest] = useState(false);
  const [docRequestForm, setDocRequestForm] = useState({ doc_type: 'national_id', message: '' });

  // NFC Tag management
  const [nfcTags, setNfcTags] = useState([]);
  const [nfcLoading, setNfcLoading] = useState(false);
  const [nfcSerial, setNfcSerial] = useState('');
  const [nfcLabel, setNfcLabel] = useState('');
  const [nfcScanning, setNfcScanning] = useState(false);

  useEffect(() => {
    if (open && selectedUser?.member_id) {
      api.get(`/members/${selectedUser.member_id}/nfc-tags`).then(res => setNfcTags(res.data || [])).catch(() => setNfcTags([]));
    } else if (open && selectedUser?.id) {
      api.get(`/members/${selectedUser.id}/nfc-tags`).then(res => setNfcTags(res.data || [])).catch(() => setNfcTags([]));
    }
  }, [open, selectedUser?.member_id, selectedUser?.id]);

  const addNfcTag = async () => {
    if (!nfcSerial.trim()) { toast.error('NFC serial number is required'); return; }
    const memberId = selectedUser?.member_id || selectedUser?.id;
    if (!memberId) return;
    setNfcLoading(true);
    try {
      const res = await api.post(`/members/${memberId}/nfc-tags`, { serial_number: nfcSerial.trim(), label: nfcLabel.trim() });
      setNfcTags(prev => [...prev, res.data]);
      setNfcSerial(''); setNfcLabel('');
      toast.success('NFC tag added');
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to add NFC tag'); }
    finally { setNfcLoading(false); }
  };

  const removeNfcTag = async (tagId) => {
    const memberId = selectedUser?.member_id || selectedUser?.id;
    if (!memberId) return;
    try {
      await api.delete(`/members/${memberId}/nfc-tags/${tagId}`);
      setNfcTags(prev => prev.filter(t => t.id !== tagId));
      toast.success('NFC tag removed');
    } catch { toast.error('Failed to remove NFC tag'); }
  };

  const scanNfcDevice = async () => {
    if (!('NDEFReader' in window)) { toast.error('NFC not supported on this device/browser. Enter the serial number manually.'); return; }
    setNfcScanning(true);
    try {
      const ndef = new window.NDEFReader();
      await ndef.scan();
      toast.info('Hold NFC tag near device...');
      ndef.addEventListener('reading', ({ serialNumber }) => {
        setNfcSerial(serialNumber || '');
        setNfcScanning(false);
        toast.success(`NFC tag read: ${serialNumber}`);
      });
      ndef.addEventListener('readingerror', () => { setNfcScanning(false); toast.error('NFC read error'); });
      setTimeout(() => setNfcScanning(false), 15000);
    } catch (err) {
      setNfcScanning(false);
      toast.error('NFC scan failed: ' + (err.message || err));
    }
  };

  const isDirectorPlus = ['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director'].includes(currentUserRole);
  const [nfcWriteStatus, setNfcWriteStatus] = useState('idle');
  const formDirty = useFormDirty(editForm, { name: selectedUser?.name || '', email: selectedUser?.email || '' });
  useUnsavedWarning(open && formDirty);

  const writeNfcTag = async () => {
    if (!('NDEFReader' in window)) { toast.error('NFC not supported. Use Chrome on Android.'); return; }
    const memberId = selectedUser?.member_id || selectedUser?.id;
    if (!memberId) return;
    setNfcWriteStatus('writing');
    try {
      const ndef = new window.NDEFReader();
      // Get signed encrypted payload from backend
      const payloadRes = await api.post(`/members/${memberId}/nfc-payload`);
      const signedPayload = payloadRes.data.payload;
      toast.info('Hold a blank NFC tag near the device to write...');
      // Write signed payload
      await ndef.write({
        records: [
          { recordType: 'text', data: signedPayload },
        ]
      });
      // Lock tag as read-only (permanent)
      try {
        await ndef.makeReadOnly();
        toast.info('Tag locked as read-only');
      } catch { /* some tags don't support locking */ }
      // Read the serial after writing
      let serial = 'written-tag';
      try {
        await ndef.scan();
        serial = await new Promise((resolve) => {
          ndef.addEventListener('reading', ({ serialNumber }) => resolve(serialNumber || 'written-tag'), { once: true });
          setTimeout(() => resolve('written-tag'), 3000);
        });
      } catch { /* fallback serial */ }
      // Log on backend
      await api.post(`/members/${memberId}/nfc-write`, {
        serial_number: serial,
        written_data: signedPayload,
        label: `Written for ${selectedUser?.name}`,
      });
      // Refresh tags list
      const res = await api.get(`/members/${memberId}/nfc-tags`);
      setNfcTags(res.data || []);
      setNfcWriteStatus('success');
      toast.success(`NFC tag written, encrypted, and locked for ${selectedUser?.name}!`);
      setTimeout(() => setNfcWriteStatus('idle'), 3000);
    } catch (err) {
      setNfcWriteStatus('idle');
      if (err.name === 'NotAllowedError') toast.error('NFC permission denied');
      else toast.error('NFC write failed: ' + (err.response?.data?.detail || err.message || err));
    }
  };

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

  const handlePhotoUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !selectedUser) return;
    setUploadingPhoto(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      // Prefer the member-photo endpoint when a member_id exists (writes to both
      // members + linked users). Fall back to /users/{id}/photo for staff-only
      // accounts that don't have a member record.
      const memberId = selectedUser.member_id || (selectedUser.role === 'member' ? selectedUser.id : null);
      const endpoint = memberId
        ? `/members/${memberId}/photo`
        : `/users/${selectedUser.id}/photo`;
      const res = await api.post(endpoint, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setEditForm(prev => ({ ...prev, photo_url: res.data.photo_url }));
      toast.success('Photo uploaded');
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : JSON.stringify(detail || {}) || err.message;
      toast.error(`Photo upload failed: ${msg}`);
      console.error('Photo upload error:', err.response?.data || err);
    }
    finally { setUploadingPhoto(false); if (photoInputRef.current) photoInputRef.current.value = ''; }
  };

  const deleteDoc = async (docId) => {
    if (!window.confirm('Delete this document?')) return;
    try { await documentsApi.delete(docId); setMemberDocs(prev => prev.filter(d => d.id !== docId)); toast.success('Document deleted'); } catch { toast.error('Delete failed'); }
  };

  const downloadProfilePdf = async () => {
    const memberId = selectedUser?.member_id || selectedUser?.id;
    if (!memberId) return;
    try {
      const res = await api.get(`/members/${memberId}/profile-pdf`, { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const a = document.createElement('a'); a.href = url; a.download = `profile-${(selectedUser?.name || 'user').replace(/\s/g, '_')}.pdf`; a.click();
      URL.revokeObjectURL(url);
      toast.success('Profile PDF downloaded');
    } catch { toast.error('PDF download failed'); }
  };


  const submitDocRequest = async () => {
    if (!selectedUser) return;
    try {
      const res = await documentsApi.createRequest({ member_id: selectedUser.id, doc_type: docRequestForm.doc_type, message: docRequestForm.message });
      setDocRequests(prev => [res.data, ...prev]);
      setShowDocRequest(false);
      setDocRequestForm({ doc_type: 'national_id', message: '' });
      toast.success('Document request sent');
    } catch (err) { toast.error(err.response?.data?.detail || 'Request failed'); }
  };

  const cancelRequest = async (reqId) => {
    try { await documentsApi.cancelRequest(reqId); setDocRequests(prev => prev.map(r => r.id === reqId ? { ...r, status: 'cancelled' } : r)); toast.success('Request cancelled'); } catch { toast.error('Cancel failed'); }
  };

  const tryConnectScanner = async () => {
    setScannerStatus('connecting');
    try {
      if (navigator.bluetooth) {
        const device = await navigator.bluetooth.requestDevice({ acceptAllDevices: true, optionalServices: ['generic_access'] });
        setScannerStatus(`connected:${device.name || 'Bluetooth Device'}`);
        toast.success(`Connected: ${device.name || 'Bluetooth Device'}`);
      } else if (navigator.serial) {
        const port = await navigator.serial.requestPort();
        await port.open({ baudRate: 9600 });
        setScannerStatus('connected:Serial Device');
        toast.success('Serial scanner connected.');
        setTimeout(() => port.close(), 5000);
      } else {
        setScannerStatus('unsupported');
        toast.warning('Web Bluetooth and Web Serial are not supported. Upload the file manually.');
      }
    } catch (err) { if (err.name !== 'NotFoundError') { setScannerStatus('error'); toast.error(`Scanner: ${err.message}`); } }
  };

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[92vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <div>
              <DialogTitle>Edit Profile: {selectedUser?.name}</DialogTitle>
              <DialogDescription>Full member profile, account settings, and documents</DialogDescription>
            </div>
            <Button size="sm" variant="outline" className="gap-1.5 text-xs shrink-0" onClick={downloadProfilePdf} data-testid="download-profile-pdf"><Download size={12} /> PDF</Button>
          </div>
        </DialogHeader>
        <Tabs defaultValue="profile" className="mt-2">
          <TabsList className="w-full grid grid-cols-6">
            <TabsTrigger value="profile">Profile</TabsTrigger>
            <TabsTrigger value="account">Account</TabsTrigger>
            <TabsTrigger value="flags">Flags</TabsTrigger>
            <TabsTrigger value="nfc">NFC Tags</TabsTrigger>
            <TabsTrigger value="documents">Documents</TabsTrigger>
            <TabsTrigger value="activity" data-testid="user-tab-activity">Activity</TabsTrigger>
          </TabsList>

          <TabsContent value="profile" className="space-y-4 mt-4">
            {/* Profile Photo */}
            <div className="flex items-center gap-4">
              <div className="relative group cursor-pointer" onClick={() => photoInputRef.current?.click()}>
                {editForm.photo_url || selectedUser?.photo_url ? (
                  <img src={editForm.photo_url || selectedUser?.photo_url} alt="" className="w-16 h-16 rounded-full object-cover border-2 border-border" data-testid="profile-photo" />
                ) : (
                  <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-lg border-2 border-border" data-testid="profile-photo-placeholder">
                    {(selectedUser?.name || '').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
                  </div>
                )}
                <div className="absolute inset-0 rounded-full bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                  <Upload size={16} className="text-white" />
                </div>
                <input ref={photoInputRef} type="file" className="hidden" accept="image/*" onChange={handlePhotoUpload} />
              </div>
              <div>
                <p className="text-sm font-medium">{selectedUser?.name}</p>
                <button className="text-xs text-primary hover:underline" onClick={() => photoInputRef.current?.click()} disabled={uploadingPhoto} data-testid="upload-photo-btn">
                  {uploadingPhoto ? 'Uploading...' : 'Change photo'}
                </button>
              </div>
            </div>
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
                  <SelectContent><SelectItem value="Male">Male</SelectItem><SelectItem value="Female">Female</SelectItem><SelectItem value="Other">Other</SelectItem></SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>ID Number</Label><Input value={editForm.national_id || ''} onChange={e => setEditForm({...editForm, national_id: e.target.value})} /></div>
            </div>
            <div className="space-y-2"><Label>Address</Label><Textarea rows={2} value={editForm.address || ''} onChange={e => setEditForm({...editForm, address: e.target.value})} /></div>
            <div className="space-y-2"><Label>Emergency Contact</Label><Input value={editForm.emergency_contact || ''} onChange={e => setEditForm({...editForm, emergency_contact: e.target.value})} /></div>
            <div className="space-y-2"><Label>Programme</Label><Input value={editForm.program || ''} onChange={e => setEditForm({...editForm, program: e.target.value})} /></div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>Cancel</Button>
              <Button className="flex-1" data-testid="save-profile-btn" onClick={onSave} disabled={saving}>{saving ? 'Saving...' : 'Save Profile'}</Button>
            </div>
          </TabsContent>

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
                  <SelectContent><SelectItem value="active">Active</SelectItem><SelectItem value="inactive">Inactive</SelectItem><SelectItem value="pending">Pending</SelectItem></SelectContent>
                </Select>
              </div>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg border border-amber-200 bg-amber-50/50">
              <div><Label className="text-sm font-medium">System Admin Access</Label><p className="text-xs text-muted-foreground mt-0.5">Grants full cross-campus visibility</p></div>
              <Switch data-testid="admin-access-toggle" checked={editForm.is_admin === true} onCheckedChange={v => setEditForm({...editForm, is_admin: v})} />
            </div>
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
              <div className="space-y-2"><Label>PIN Code (also voicemail PIN)</Label><Input maxLength={6} placeholder="4-6 digit PIN" value={editForm.pin || ''} onChange={e => setEditForm({...editForm, pin: e.target.value})} /></div>
            </div>
            {/* Extension (admin-only) */}
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide pt-2">Extension</p>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2"><Label>Extension</Label><Input maxLength={6} placeholder="e.g. 1001" value={editForm.extension || ''} onChange={e => setEditForm({...editForm, extension: e.target.value})} data-testid="edit-extension" /></div>
              <div className="space-y-2"><Label>Call Forward To</Label><Input placeholder="Phone number" value={editForm.forward_to || ''} onChange={e => setEditForm({...editForm, forward_to: e.target.value})} /></div>
            </div>
            <div className="space-y-2">
              <Label>Title <span className="text-xs text-muted-foreground">(auto-suggested, editable)</span></Label>
              <Input data-testid="edit-title-input" value={editForm.title || ''} onChange={e => setEditForm({...editForm, title: e.target.value})} placeholder={`e.g. ${editForm.role || 'Staff'} of ${locations.find(l => l.id === (editForm.location_ids || [])[0])?.name || 'Location'}`} />
            </div>
            <div className="space-y-2"><Label>Notes</Label><Textarea rows={2} value={editForm.notes || ''} onChange={e => setEditForm({...editForm, notes: e.target.value})} /></div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>Cancel</Button>
              <Button className="flex-1" onClick={onSave} disabled={saving}>{saving ? 'Saving...' : 'Save Account'}</Button>
            </div>
          </TabsContent>

          <TabsContent value="flags" className="space-y-4 mt-4">
            <div className="space-y-3 p-3 rounded-lg border border-border">
              <p className="text-sm font-medium">Role Flags</p>
              <div className="flex items-center justify-between"><Label className="text-sm">Is Parent</Label><Switch data-testid="flag-is_parent" checked={editForm.is_parent || false} onCheckedChange={v => setEditForm({...editForm, is_parent: v})} /></div>
              <div className="flex items-center justify-between"><Label className="text-sm">Is Guest</Label><Switch checked={editForm.is_guest || false} onCheckedChange={v => setEditForm({...editForm, is_guest: v})} /></div>
              <div className="flex items-center justify-between"><Label className="text-sm">Is Customer</Label><Switch checked={editForm.is_customer || false} onCheckedChange={v => setEditForm({...editForm, is_customer: v})} /></div>
              <div className="flex items-center justify-between"><Label className="text-sm">Medical Enabled</Label><Switch checked={editForm.is_medical || false} onCheckedChange={v => setEditForm({...editForm, is_medical: v})} data-testid="flag-is_medical" /></div>
              <div className="flex items-center justify-between"><Label className="text-sm">Resident</Label><Switch checked={editForm.is_resident || false} onCheckedChange={v => setEditForm({...editForm, is_resident: v})} data-testid="flag-is_resident" /></div>
              {editForm.is_resident && (
                <div className="space-y-1.5 pl-4 border-l-2 border-blue-200">
                  <Label className="text-xs text-muted-foreground">Restricted Sub-Location</Label>
                  <Select value={editForm.resident_location_id || ''} onValueChange={v => setEditForm({...editForm, resident_location_id: v})}>
                    <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="Select restricted location" /></SelectTrigger>
                    <SelectContent>{locations.filter(l => l.is_restricted || l.type === 'sub-location').map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              )}
              <div className="flex items-center justify-between"><Label className="text-sm">Restricted Access</Label><Switch checked={editForm.has_restricted_access || false} onCheckedChange={v => setEditForm({...editForm, has_restricted_access: v})} data-testid="flag-restricted_access" /></div>
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>Cancel</Button>
              <Button className="flex-1" onClick={onSave} disabled={saving}>{saving ? 'Saving...' : 'Save Flags'}</Button>
            </div>
          </TabsContent>

          <TabsContent value="nfc" className="space-y-4 mt-4">
            <div className="space-y-1">
              <p className="text-sm font-medium">NFC Tags</p>
              <p className="text-xs text-muted-foreground">Assign NFC tags/cards to this user for contactless check-in and access control.</p>
            </div>

            {nfcTags.length > 0 ? (
              <div className="space-y-2">
                {nfcTags.map(tag => (
                  <div key={tag.id} className="flex items-center gap-3 p-3 rounded-lg border border-border" data-testid={`nfc-tag-${tag.id}`}>
                    <Wifi size={16} className="text-blue-500 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium font-mono">{tag.serial_number}</p>
                      {tag.label && <p className="text-xs text-muted-foreground">{tag.label}</p>}
                      <p className="text-[10px] text-muted-foreground">Added {new Date(tag.added_at).toLocaleDateString()}</p>
                    </div>
                    <Button size="sm" variant="ghost" className="text-destructive h-7 px-2" onClick={() => removeNfcTag(tag.id)} data-testid={`remove-nfc-${tag.id}`}>
                      <X size={13} />
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-6 rounded-lg border border-dashed border-border">
                <Wifi size={24} className="mx-auto mb-2 text-muted-foreground opacity-30" />
                <p className="text-sm text-muted-foreground">No NFC tags assigned</p>
              </div>
            )}

            <div className="p-3 rounded-lg border border-border space-y-3">
              <p className="text-xs font-semibold text-muted-foreground uppercase">Add NFC Tag</p>
              <div className="flex gap-2">
                <Input
                  className="flex-1 font-mono"
                  placeholder="Serial number (e.g. 04:A2:B3:C4:D5:E6:F7)"
                  value={nfcSerial}
                  onChange={e => setNfcSerial(e.target.value)}
                  data-testid="nfc-serial-input"
                />
                <Button size="sm" variant="outline" className="gap-1.5 shrink-0" onClick={scanNfcDevice} disabled={nfcScanning} data-testid="scan-nfc-btn">
                  <Wifi size={13} /> {nfcScanning ? 'Scanning...' : 'Scan'}
                </Button>
              </div>
              <Input
                placeholder="Label (optional, e.g. Blue Keycard)"
                value={nfcLabel}
                onChange={e => setNfcLabel(e.target.value)}
                data-testid="nfc-label-input"
              />
              <Button className="w-full gap-1.5" onClick={addNfcTag} disabled={nfcLoading || !nfcSerial.trim()} data-testid="add-nfc-tag-btn">
                <Plus size={13} /> {nfcLoading ? 'Adding...' : 'Add NFC Tag'}
              </Button>
            </div>

            {nfcScanning && (
              <div className="p-4 rounded-lg bg-blue-50 border border-blue-200 text-center">
                <Wifi size={28} className="mx-auto mb-2 text-blue-500 animate-pulse" />
                <p className="text-sm font-medium text-blue-800">Waiting for NFC tag...</p>
                <p className="text-xs text-blue-600 mt-1">Hold the NFC card near your device</p>
                <Button size="sm" variant="outline" className="mt-3" onClick={() => setNfcScanning(false)}>Cancel</Button>
              </div>
            )}

            {/* Write NFC Tag - Director+ only */}
            {isDirectorPlus && (
              <div className="p-3 rounded-lg border-2 border-dashed border-blue-200 bg-blue-50/30 space-y-3">
                <div className="flex items-center gap-2">
                  <Wifi size={16} className="text-blue-600" />
                  <div>
                    <p className="text-sm font-medium">Write NFC Tag</p>
                    <p className="text-xs text-muted-foreground">Write this member's ID to a blank NFC card</p>
                  </div>
                </div>
                {nfcWriteStatus === 'success' ? (
                  <div className="p-3 rounded-lg bg-green-50 border border-green-200 text-center">
                    <p className="text-sm font-medium text-green-700">NFC tag written successfully!</p>
                  </div>
                ) : (
                  <Button
                    className="w-full gap-2 bg-blue-600 hover:bg-blue-700"
                    onClick={writeNfcTag}
                    disabled={nfcWriteStatus === 'writing'}
                    data-testid="write-nfc-tag-btn"
                  >
                    <Wifi size={14} />
                    {nfcWriteStatus === 'writing' ? 'Hold NFC tag near device...' : `Write NFC for ${selectedUser?.name?.split(' ')[0] || 'Member'}`}
                  </Button>
                )}
              </div>
            )}
          </TabsContent>


          <TabsContent value="documents" className="space-y-4 mt-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">Documents on File</p>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setShowScanner(true)}><Bluetooth size={13} /> Scanner</Button>
                <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setShowDocRequest(true)}><Plus size={13} /> Request Doc</Button>
                <div className="relative">
                  <Button size="sm" className="gap-1.5" onClick={() => fileInputRef.current?.click()} disabled={uploadingDoc}><Upload size={13} /> {uploadingDoc ? 'Uploading...' : 'Upload'}</Button>
                  <input ref={fileInputRef} type="file" className="hidden" accept=".jpg,.jpeg,.png,.pdf,.doc,.docx" onChange={handleDocUpload} />
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Label className="text-xs whitespace-nowrap">Upload as:</Label>
              <Select value={uploadDocType} onValueChange={setUploadDocType}>
                <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>{Object.entries(ID_TYPE_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            {docRequests.filter(r => r.status === 'pending').length > 0 && (
              <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-3 space-y-2">
                <p className="text-xs font-medium text-yellow-800 flex items-center gap-1"><AlertCircle size={12} /> Pending Requests</p>
                {docRequests.filter(r => r.status === 'pending').map(req => (
                  <div key={req.id} className="flex items-center justify-between text-xs">
                    <span className="text-yellow-900">{ID_TYPE_LABELS[req.doc_type] || req.doc_type} {req.message && `- ${req.message}`}</span>
                    <Button size="sm" variant="ghost" className="h-6 text-xs text-red-600" onClick={() => cancelRequest(req.id)}>Cancel</Button>
                  </div>
                ))}
              </div>
            )}
            {docsLoading ? (<div className="h-24 animate-pulse bg-muted rounded-lg" />) : memberDocs.length === 0 ? (
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
                      <a href={documentsApi.fileUrl(doc.id)} target="_blank" rel="noopener noreferrer" className="p-1.5 rounded-md hover:bg-accent" title="View/Download"><Download size={13} /></a>
                      <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive hover:text-destructive" onClick={() => deleteDoc(doc.id)}><X size={13} /></Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value="activity" className="space-y-4 mt-4">
            {selectedUser && <ActivityFeed subjectKind="user" subjectId={selectedUser.id} showAddNote={true} showDownload={true} />}
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>

    {/* Document Request sub-dialog */}
    <Dialog open={showDocRequest} onOpenChange={setShowDocRequest}>
      <DialogContent className="max-w-sm">
        <DialogHeader><DialogTitle>Request Document</DialogTitle><DialogDescription>Request a document from {selectedUser?.name}</DialogDescription></DialogHeader>
        <div className="space-y-4 mt-2">
          <div className="space-y-2"><Label>Document Type</Label>
            <Select value={docRequestForm.doc_type} onValueChange={v => setDocRequestForm({...docRequestForm, doc_type: v})}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>{Object.entries(ID_TYPE_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-2"><Label>Message (optional)</Label><Textarea rows={2} placeholder="e.g. Required for renewal" value={docRequestForm.message} onChange={e => setDocRequestForm({...docRequestForm, message: e.target.value})} /></div>
          <div className="flex gap-3"><Button variant="outline" className="flex-1" onClick={() => setShowDocRequest(false)}>Cancel</Button><Button className="flex-1" onClick={submitDocRequest}>Send Request</Button></div>
        </div>
      </DialogContent>
    </Dialog>

    {/* Scanner sub-dialog */}
    <Dialog open={showScanner} onOpenChange={setShowScanner}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Document Scanner</DialogTitle></DialogHeader>
        <div className="space-y-4 mt-2">
          <div className="grid grid-cols-3 gap-3">
            <button onClick={tryConnectScanner} className="flex flex-col items-center gap-2 p-4 rounded-xl border border-border hover:bg-accent transition-colors text-sm font-medium" data-testid="connect-bluetooth-scanner"><Bluetooth size={22} className="text-blue-500" />Bluetooth</button>
            <button onClick={tryConnectScanner} className="flex flex-col items-center gap-2 p-4 rounded-xl border border-border hover:bg-accent transition-colors text-sm font-medium"><Monitor size={22} className="text-green-500" />USB/Serial</button>
            <button onClick={() => { setShowScanner(false); fileInputRef.current?.click(); }} className="flex flex-col items-center gap-2 p-4 rounded-xl border border-border hover:bg-accent transition-colors text-sm font-medium"><Upload size={22} className="text-primary" />Upload File</button>
          </div>
          {scannerStatus === 'connecting' && <div className="flex items-center gap-2 text-sm text-muted-foreground"><div className="h-4 w-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />Connecting...</div>}
          {scannerStatus.startsWith('connected:') && <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 p-3 rounded-lg"><Wifi size={14} /> Connected: {scannerStatus.replace('connected:', '')}</div>}
          {scannerStatus === 'unsupported' && <div className="text-sm text-amber-700 bg-amber-50 p-3 rounded-lg"><p className="font-medium">Browser not supported</p><p className="text-xs mt-0.5">Use Chrome/Edge on Desktop, or upload manually.</p></div>}
          <Button variant="outline" className="w-full" onClick={() => setShowScanner(false)}>Close</Button>
        </div>
      </DialogContent>
    </Dialog>
    </>
  );
}
