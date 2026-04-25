import React, { useState, useEffect, useCallback } from 'react';
import { Shield, ScanLine, UserPlus, KeyRound, Users, Clock, CheckCircle, XCircle, AlertTriangle, QrCode, Timer } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { accessApi, locationsApi, membersApi, biometricApi, nfcApi, configApi } from '../services/api';
import api from '../services/api';
import { toast } from 'sonner';
import { Fingerprint, Smartphone } from 'lucide-react';
import { ScanDialog } from '../components/access/ScanDialog';

const STATUS_VARIANT = { approved: 'outline', rejected: 'destructive', pending: 'secondary' };
const STATUS_CLASS = { approved: 'border-green-500 text-green-600', rejected: '', pending: '' };
const PASS_STATUS_CLASS = { active: 'border-green-500 text-green-600', expired: 'border-red-400 text-red-500' };
const CHECKIN_TYPE_MAP = { staff: 'Staff Check-in (with children)', parent: 'Parent Check-in (with children)', guest: 'Guest Check-in (with children)', child_self: 'Child Self Check-in' };

export default function AccessPage() {
  const [locations, setLocations] = useState([]);
  const [restrictedLocations, setRestrictedLocations] = useState([]);
  const [selectedLocation, setSelectedLocation] = useState('');
  const [residents, setResidents] = useState([]);
  const [staffPasses, setStaffPasses] = useState([]);
  const [guestRequests, setGuestRequests] = useState([]);
  const [scanLog, setScanLog] = useState([]);
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);

  const [showAssignResident, setShowAssignResident] = useState(false);
  const [showAssignStaff, setShowAssignStaff] = useState(false);
  const [showGuestRequest, setShowGuestRequest] = useState(false);
  const [showScanDialog, setShowScanDialog] = useState(false);
  const [guestPasses, setGuestPasses] = useState([]);
  const [showQrPass, setShowQrPass] = useState(null);
  const [showExtendPass, setShowExtendPass] = useState(null);
  const [extendDays, setExtendDays] = useState('7');
  const [validateResult, setValidateResult] = useState(null);
  const [showValidateResult, setShowValidateResult] = useState(false);

  const [residentForm, setResidentForm] = useState({ member_id: '', tags: '' });
  const [staffForm, setStaffForm] = useState({ staff_id: '' });
  const [guestForm, setGuestForm] = useState({ guest_name: '', guest_phone: '', guest_id_number: '', purpose: '', visit_date: new Date().toISOString().split('T')[0], visit_time: '' });
  const [scanForm, setScanForm] = useState({ member_id: '', action: 'in', guest_request_id: '', guest_name: '' });
  const [scanMode, setScanMode] = useState('member');
  const [saving, setSaving] = useState(false);

  // Access Control API connections
  const [apiConnections, setApiConnections] = useState([]);
  const [showApiConnForm, setShowApiConnForm] = useState(false);
  const [apiConnForm, setApiConnForm] = useState({ name: '', type: 'door', api_url: '', api_key: '', provider: 'generic', location_id: '', sublocation_id: '', door_name: '', enabled: true });
  // Guest access links
  const [guestLinks, setGuestLinks] = useState([]);
  const [showGuestLinkForm, setShowGuestLinkForm] = useState(false);
  const [guestLinkForm, setGuestLinkForm] = useState({ space_name: '', location_id: '', max_uses: 0, requires_approval: true, expires_at: '' });
  const isAdmin = true; // This page is already admin-restricted

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [locsRes, membersRes] = await Promise.all([
        locationsApi.list(),
        membersApi.list({ limit: 500 }),
      ]);
      const allLocs = locsRes.data;
      setLocations(allLocs);
      const restricted = allLocs.filter(l => l.is_restricted);
      setRestrictedLocations(restricted);
      setMembers(membersRes.data.members || []);
      if (restricted.length > 0 && !selectedLocation) {
        setSelectedLocation(restricted[0].id);
      }
    } catch { toast.error('Failed to load data'); }
    finally { setLoading(false); }
    // Load API connections and guest links
    try {
      const [connRes, linksRes] = await Promise.all([
        accessApi.listApiConnections().catch(() => ({ data: [] })),
        accessApi.listGuestLinks().catch(() => ({ data: [] })),
      ]);
      setApiConnections(connRes.data || []);
      setGuestLinks(linksRes.data || []);
    } catch (e) { console.warn(e.message || e); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const fetchLocationData = useCallback(async () => {
    if (!selectedLocation) return;
    try {
      const [resRes, staffRes, guestRes, scanRes, passRes] = await Promise.all([
        accessApi.residents({ location_id: selectedLocation }),
        accessApi.staffPasses({ location_id: selectedLocation }),
        accessApi.guestRequests({ location_id: selectedLocation }),
        accessApi.scanLog({ location_id: selectedLocation }),
        accessApi.guestPasses({ location_id: selectedLocation }),
      ]);
      setResidents(resRes.data);
      setStaffPasses(staffRes.data);
      setGuestRequests(guestRes.data);
      setScanLog(scanRes.data);
      setGuestPasses(passRes.data || []);
    } catch { toast.error('Failed to load access data'); }
  }, [selectedLocation]);

  useEffect(() => { fetchLocationData(); }, [fetchLocationData]);

  const handleAssignResident = async (e) => {
    e.preventDefault();
    if (!residentForm.member_id) { toast.error('Select a person'); return; }
    setSaving(true);
    try {
      await configApi.addResidents(selectedLocation, [residentForm.member_id]);
      toast.success('Resident added');
      setShowAssignResident(false);
      setResidentForm({ member_id: '', search: '', searchResults: [] });
      fetchLocationData();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
  };

  const searchResidents = async (q) => {
    if (q.length < 2) { setResidentForm(prev => ({ ...prev, searchResults: [] })); return; }
    try {
      const [childRes, guestRes, memberRes] = await Promise.all([
        api.get('/children', { params: { search: q, limit: 10 } }),
        api.get('/guests', { params: { search: q, limit: 10 } }),
        api.get('/members', { params: { search: q, limit: 10 } }),
      ]);
      const results = [
        ...(childRes.data || []).map(c => ({ id: c.id, name: c.name, type: 'child' })),
        ...(guestRes.data || []).map(g => ({ id: g.id, name: g.name, type: 'guest' })),
        ...((memberRes.data?.members || memberRes.data || []).map(m => ({ id: m.id, name: m.name, type: m.role || 'member' }))),
      ];
      setResidentForm(prev => ({ ...prev, searchResults: results }));
    } catch (e) { console.warn(e.message || e); }
  };

  const handleAssignStaff = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await accessApi.assignStaffPass({ staff_id: staffForm.staff_id, location_id: selectedLocation });
      toast.success('Staff access granted');
      setShowAssignStaff(false);
      setStaffForm({ staff_id: '' });
      fetchLocationData();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
  };

  const handleGuestRequest = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await accessApi.requestGuestVisit({ ...guestForm, location_id: selectedLocation });
      toast.success('Guest visit request submitted');
      setShowGuestRequest(false);
      setGuestForm({ guest_name: '', guest_phone: '', guest_id_number: '', purpose: '', visit_date: new Date().toISOString().split('T')[0], visit_time: '' });
      fetchLocationData();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
  };

  const handleScan = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      let memberId = scanForm.member_id;

      // NFC mode: resolve serial number to member first
      if (scanMode === 'nfc') {
        const nfcRes = await nfcApi.scan({ serial_number: scanForm.member_id });
        memberId = nfcRes.data.member?.id;
        if (!memberId) throw new Error('NFC tag not linked to a member');
      }

      // Biometric mode: verify credential to get member
      if (scanMode === 'biometric') {
        const bioRes = await biometricApi.verify({ credential_id: scanForm.member_id });
        memberId = bioRes.data.member?.id;
        if (!memberId) throw new Error('Biometric credential not recognized');
      }

      const payload = { location_id: selectedLocation, action: scanForm.action };
      if (scanMode === 'guest') {
        payload.guest_request_id = scanForm.guest_request_id;
        payload.guest_name = scanForm.guest_name;
        payload.member_id = scanForm.member_id || 'guest';
      } else {
        payload.member_id = memberId;
      }
      const res = await accessApi.scan(payload);
      toast.success(`${scanForm.action === 'in' ? 'Scanned In' : 'Scanned Out'} — ${res.data.access_type}`);
      setShowScanDialog(false);
      setScanForm({ member_id: '', action: 'in', guest_request_id: '', guest_name: '' });
      fetchLocationData();
    } catch (err) { toast.error(err.response?.data?.detail || err.message || 'No access authorization'); }
    finally { setSaving(false); }
  };

  const approveGuest = async (id) => {
    try { await accessApi.approveGuest(id); toast.success('Guest approved'); fetchLocationData(); }
    catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
  };

  const rejectGuest = async (id) => {
    try { await accessApi.rejectGuest(id); toast.success('Guest rejected'); fetchLocationData(); }
    catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
  };

  const validateGuestPass = async (passId) => {
    try {
      const res = await accessApi.validateGuestPass(passId);
      setValidateResult(res.data);
      setShowValidateResult(true);
    } catch { toast.error('Validation failed'); }
  };

  const handleExtendPass = async () => {
    if (!showExtendPass) return;
    try {
      await accessApi.extendGuestPass(showExtendPass.id, { valid_days: parseInt(extendDays) || 7 });
      toast.success(`Pass extended by ${extendDays} days`);
      setShowExtendPass(null);
      fetchLocationData();
    } catch { toast.error('Extension failed'); }
  };

  const generateQrDataUrl = (value) => {
    // Simple QR-like visual using SVG with the pass ID
    const size = 200;
    const encoded = encodeURIComponent(value);
    return `https://api.qrserver.com/v1/create-qr-code/?size=${size}x${size}&data=${encoded}`;
  };

  const locName = (id) => locations.find(l => l.id === id)?.name || id;

  if (loading) return <div className="p-6"><div className="space-y-4">{[1,2,3].map(i => <div key={i} className="h-24 bg-muted animate-pulse rounded-xl" />)}</div></div>;

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading" data-testid="access-page-title">Restricted Access</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{restrictedLocations.length} restricted locations</p>
        </div>
        <div className="flex gap-2">
          <Button variant="default" className="gap-2" onClick={() => setShowScanDialog(true)} data-testid="scan-btn">
            <ScanLine size={16} /> Scan In/Out
          </Button>
        </div>
      </div>

      {restrictedLocations.length === 0 ? (
        <Card className="shadow-soft rounded-xl">
          <CardContent className="py-16 text-center">
            <Shield size={48} className="mx-auto mb-3 opacity-30 text-muted-foreground" />
            <p className="text-muted-foreground">No restricted locations configured.</p>
            <p className="text-xs text-muted-foreground mt-1">Mark a sub-location as "restricted" in Locations to enable access control.</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="flex items-center gap-3">
            <Label className="text-sm font-medium whitespace-nowrap">Restricted Space:</Label>
            <Select value={selectedLocation} onValueChange={setSelectedLocation}>
              <SelectTrigger className="w-64" data-testid="access-location-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                {restrictedLocations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <Card className="shadow-soft rounded-xl"><CardContent className="p-4"><p className="text-xs text-muted-foreground">Residents</p><p className="text-2xl font-semibold mt-1" data-testid="resident-count">{residents.length}</p></CardContent></Card>
            <Card className="shadow-soft rounded-xl"><CardContent className="p-4"><p className="text-xs text-muted-foreground">Staff Access</p><p className="text-2xl font-semibold mt-1" data-testid="staff-pass-count">{staffPasses.length}</p></CardContent></Card>
            <Card className="shadow-soft rounded-xl"><CardContent className="p-4"><p className="text-xs text-muted-foreground">Pending Guests</p><p className="text-2xl font-semibold mt-1" data-testid="pending-guest-count">{guestRequests.filter(g => g.status === 'pending').length}</p></CardContent></Card>
            <Card className="shadow-soft rounded-xl"><CardContent className="p-4"><p className="text-xs text-muted-foreground">Scans Today</p><p className="text-2xl font-semibold mt-1" data-testid="scans-today">{scanLog.filter(s => s.timestamp?.startsWith(new Date().toISOString().split('T')[0])).length}</p></CardContent></Card>
          </div>

          <Tabs defaultValue="residents">
            <TabsList className="flex-wrap">
              <TabsTrigger value="residents" data-testid="tab-residents"><Users size={13} className="mr-1.5" /> Residents</TabsTrigger>
              <TabsTrigger value="staff" data-testid="tab-staff"><KeyRound size={13} className="mr-1.5" /> Staff Access</TabsTrigger>
              <TabsTrigger value="guests" data-testid="tab-guests"><UserPlus size={13} className="mr-1.5" /> Guest Requests</TabsTrigger>
              <TabsTrigger value="passes" data-testid="tab-passes"><QrCode size={13} className="mr-1.5" /> Guest Passes</TabsTrigger>
              <TabsTrigger value="log" data-testid="tab-scan-log"><Clock size={13} className="mr-1.5" /> Scan Log</TabsTrigger>
              <TabsTrigger value="doors" data-testid="tab-doors"><Shield size={13} className="mr-1.5" /> Door APIs</TabsTrigger>
              <TabsTrigger value="links" data-testid="tab-links"><KeyRound size={13} className="mr-1.5" /> Guest Links</TabsTrigger>
            </TabsList>

            <TabsContent value="residents" className="mt-4">
              <div className="flex justify-end mb-3">
                <Button size="sm" className="gap-2" onClick={() => setShowAssignResident(true)} data-testid="assign-resident-btn"><UserPlus size={14} /> Assign Resident</Button>
              </div>
              {residents.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-10">No residents assigned to this location.</p>
              ) : (
                <div className="space-y-2">
                  {residents.map(r => (
                    <Card key={r.id} className="shadow-soft rounded-xl" data-testid={`resident-card-${r.id}`}>
                      <CardContent className="p-4 flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium">{r.member_name || r.member_id}</p>
                          <div className="flex gap-1 mt-1">{(r.tags || []).map(t => <Badge key={t} variant="secondary" className="text-xs">{t}</Badge>)}</div>
                        </div>
                        <Button size="sm" variant="ghost" className="text-destructive" onClick={async () => { await accessApi.removeResident(r.id); toast.success('Removed'); fetchLocationData(); }}>Remove</Button>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </TabsContent>

            <TabsContent value="staff" className="mt-4">
              <div className="flex justify-end mb-3">
                <Button size="sm" className="gap-2" onClick={() => setShowAssignStaff(true)} data-testid="assign-staff-btn"><KeyRound size={14} /> Grant Access</Button>
              </div>
              {staffPasses.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-10">No staff access passes for this location.</p>
              ) : (
                <div className="space-y-2">
                  {staffPasses.map(p => (
                    <Card key={p.id} className="shadow-soft rounded-xl" data-testid={`staff-pass-${p.id}`}>
                      <CardContent className="p-4 flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium">{p.staff_name || p.staff_id}</p>
                          <p className="text-xs text-muted-foreground">{p.staff_role}</p>
                        </div>
                        <Button size="sm" variant="ghost" className="text-destructive" onClick={async () => { await accessApi.revokeStaffPass(p.id); toast.success('Revoked'); fetchLocationData(); }}>Revoke</Button>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </TabsContent>

            <TabsContent value="guests" className="mt-4">
              <div className="flex justify-end mb-3">
                <Button size="sm" className="gap-2" onClick={() => setShowGuestRequest(true)} data-testid="request-guest-btn"><UserPlus size={14} /> Request Guest Visit</Button>
              </div>
              {guestRequests.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-10">No guest visit requests.</p>
              ) : (
                <div className="space-y-2">
                  {guestRequests.map(g => (
                    <Card key={g.id} className="shadow-soft rounded-xl" data-testid={`guest-request-${g.id}`}>
                      <CardContent className="p-4 flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium">{g.guest_name}</p>
                          <p className="text-xs text-muted-foreground">{g.visit_date} {g.visit_time && `at ${g.visit_time}`} — {g.purpose}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant={STATUS_VARIANT[g.status] || 'secondary'}
                            className={`text-xs ${STATUS_CLASS[g.status] || ''}`}>
                            {g.status}
                          </Badge>
                          {g.status === 'pending' && (
                            <>
                              <Button size="sm" variant="outline" className="text-green-600 border-green-300 h-7" onClick={() => approveGuest(g.id)} data-testid={`approve-guest-${g.id}`}>
                                <CheckCircle size={13} className="mr-1" /> Approve
                              </Button>
                              <Button size="sm" variant="outline" className="text-red-600 border-red-300 h-7" onClick={() => rejectGuest(g.id)} data-testid={`reject-guest-${g.id}`}>
                                <XCircle size={13} className="mr-1" /> Reject
                              </Button>
                            </>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* Guest Passes Tab */}
            <TabsContent value="passes" className="mt-4">
              {guestPasses.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-10">No guest passes issued yet. Approve a guest request to generate a pass.</p>
              ) : (
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {guestPasses.map(gp => (
                    <Card key={gp.id} className={`shadow-soft rounded-xl border-2 ${gp.status === 'active' ? 'border-green-200' : 'border-border'}`} data-testid={`guest-pass-${gp.id}`}>
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between mb-2">
                          <div>
                            <p className="font-semibold text-sm">{gp.guest_name}</p>
                            <p className="text-xs text-muted-foreground">{gp.guest_phone}</p>
                          </div>
                          <Badge variant={gp.status === 'active' ? 'outline' : 'secondary'}
                            className={`text-xs ${PASS_STATUS_CLASS[gp.status] || 'border-border'}`}>
                            {gp.status}
                          </Badge>
                        </div>
                        <div className="text-xs text-muted-foreground space-y-0.5 mb-3">
                          <p className="flex items-center gap-1"><Clock size={10} /> Valid: {gp.valid_from} to {gp.valid_until}</p>
                          {gp.valid_from_time && <p className="flex items-center gap-1"><Timer size={10} /> Time: {gp.valid_from_time} - {gp.valid_until_time || '22:00'}</p>}
                          <p>Pass ID: <span className="font-mono text-primary">{gp.id}</span></p>
                          {gp.has_existing_badge && (
                            <p className="text-green-600 flex items-center gap-1"><CheckCircle size={10} /> Has existing badge{gp.existing_badge_name ? ` (${gp.existing_badge_name})` : ''}</p>
                          )}
                        </div>
                        <div className="flex gap-2">
                          <Button size="sm" variant="outline" className="flex-1 gap-1 text-xs" onClick={() => setShowQrPass(gp)} data-testid={`view-qr-${gp.id}`}>
                            <QrCode size={12} /> View QR
                          </Button>
                          <Button size="sm" variant="outline" className="flex-1 gap-1 text-xs" onClick={() => validateGuestPass(gp.id)} data-testid={`validate-pass-${gp.id}`}>
                            <CheckCircle size={12} /> Validate
                          </Button>
                          {gp.status === 'active' && (
                            <Button size="sm" variant="outline" className="text-xs gap-1" onClick={() => { setShowExtendPass(gp); setExtendDays('7'); }} data-testid={`extend-pass-${gp.id}`}>
                              <Timer size={12} /> Extend
                            </Button>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </TabsContent>

            <TabsContent value="log" className="mt-4">
              {scanLog.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-10">No scan records yet.</p>
              ) : (
                <div className="space-y-2">
                  {scanLog.map(s => (
                    <div key={s.id} className="flex items-center justify-between p-3 rounded-lg border border-border text-sm" data-testid={`scan-log-${s.id}`}>
                      <div className="flex items-center gap-3">
                        <Badge variant={s.action === 'in' ? 'outline' : 'secondary'} className={`text-xs ${s.action === 'in' ? 'border-green-500 text-green-600' : 'border-red-400 text-red-500'}`}>
                          {s.action === 'in' ? 'IN' : 'OUT'}
                        </Badge>
                        <div>
                          <p className="font-medium">{s.member_name || s.guest_name || s.member_id}</p>
                          <p className="text-xs text-muted-foreground">{s.access_type} — {new Date(s.timestamp).toLocaleString()}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* Door/Access Control API Connections */}
            <TabsContent value="doors" className="mt-4">
              <div className="flex justify-between items-center mb-4">
                <p className="text-sm text-muted-foreground">{apiConnections.length} connections configured</p>
                <Button size="sm" className="gap-1.5" onClick={() => { setApiConnForm({ name: '', type: 'door', api_url: '', api_key: '', provider: 'generic', location_id: selectedLocation, sublocation_id: '', door_name: '', enabled: true }); setShowApiConnForm(true); }} data-testid="add-api-conn-btn"><UserPlus size={13} /> Add Connection</Button>
              </div>
              {apiConnections.length === 0 ? (
                <p className="text-center py-8 text-muted-foreground text-sm">No access control APIs configured. Connect door systems (Kisi, Salto, Brivo, OpenPath) to manage physical access.</p>
              ) : (
                <div className="space-y-2">
                  {apiConnections.map(conn => (
                    <Card key={conn.id} className="rounded-xl">
                      <CardContent className="p-4 flex items-center gap-4">
                        <Shield size={18} className="text-primary shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-sm">{conn.name} <Badge variant="outline" className="text-[10px] ml-1">{conn.type}</Badge> <Badge variant="outline" className="text-[10px] ml-1">{conn.provider}</Badge></p>
                          <p className="text-xs text-muted-foreground truncate">{conn.api_url} {conn.door_name ? `| ${conn.door_name}` : ''}</p>
                        </div>
                        <Badge className={`text-[10px] ${conn.enabled ? 'bg-green-100 text-green-700' : 'bg-slate-100'}`}>{conn.enabled ? 'Active' : 'Off'}</Badge>
                        <Button size="sm" variant="ghost" className="text-destructive" onClick={async () => { if (window.confirm('Remove?')) { await accessApi.deleteApiConnection(conn.id); setApiConnections(prev => prev.filter(c => c.id !== conn.id)); toast.success('Removed'); } }}><XCircle size={13} /></Button>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* Shareable Guest Access Links */}
            <TabsContent value="links" className="mt-4">
              <div className="flex justify-between items-center mb-4">
                <p className="text-sm text-muted-foreground">{guestLinks.length} active links</p>
                <Button size="sm" className="gap-1.5" onClick={() => { setGuestLinkForm({ space_name: '', location_id: selectedLocation, max_uses: 0, requires_approval: true, expires_at: '' }); setShowGuestLinkForm(true); }} data-testid="create-guest-link-btn"><KeyRound size={13} /> Create Link</Button>
              </div>
              {guestLinks.length === 0 ? (
                <p className="text-center py-8 text-muted-foreground text-sm">No guest access links. Create shareable links for guests to request access to restricted spaces.</p>
              ) : (
                <div className="space-y-2">
                  {guestLinks.map(link => (
                    <Card key={link.id} className="rounded-xl">
                      <CardContent className="p-4">
                        <div className="flex items-center gap-4">
                          <KeyRound size={16} className="text-amber-500 shrink-0" />
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-sm">{link.space_name || 'Access Link'}</p>
                            <p className="text-xs text-muted-foreground">Uses: {link.uses}/{link.max_uses || 'unlimited'} {link.expires_at ? `| Expires: ${link.expires_at.slice(0, 10)}` : ''}</p>
                          </div>
                          <Badge variant={link.requires_approval ? 'secondary' : 'default'} className="text-[10px]">{link.requires_approval ? 'Needs Approval' : 'Auto-Approve'}</Badge>
                          <Button size="sm" variant="outline" className="text-xs" onClick={() => { const url = `${window.location.origin}/public-access/${link.token}`; navigator.clipboard.writeText(url); toast.success('Link copied!'); }} data-testid="copy-guest-link">Copy Link</Button>
                          <Button size="sm" variant="ghost" className="text-destructive" onClick={async () => { if (!window.confirm('Delete this guest link?')) return; await accessApi.deleteGuestLink(link.id); setGuestLinks(prev => prev.filter(l => l.id !== link.id)); toast.success('Deleted'); }}><XCircle size={13} /></Button>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </TabsContent>
          </Tabs>
        </>
      )}

      {/* Assign Resident Dialog */}
      <Dialog open={showAssignResident} onOpenChange={setShowAssignResident}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Assign Resident</DialogTitle></DialogHeader>
          <form onSubmit={handleAssignResident} className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Member</Label>
              <Select value={residentForm.member_id} onValueChange={v => setResidentForm({ ...residentForm, member_id: v })}>
                <SelectTrigger data-testid="resident-member-select"><SelectValue placeholder="Select member" /></SelectTrigger>
                <SelectContent>{members.map(m => <SelectItem key={m.id} value={m.id}>{m.name} ({m.role})</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Tags (comma separated)</Label>
              <Input placeholder="e.g. special_needs, shelter" value={residentForm.tags} onChange={e => setResidentForm({ ...residentForm, tags: e.target.value })} data-testid="resident-tags-input" />
            </div>
            <div className="flex gap-3"><Button type="button" variant="outline" className="flex-1" onClick={() => setShowAssignResident(false)}>Cancel</Button><Button type="submit" className="flex-1" disabled={saving || !residentForm.member_id} data-testid="save-resident-btn">{saving ? 'Saving...' : 'Assign'}</Button></div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Assign Staff Dialog */}
      <Dialog open={showAssignStaff} onOpenChange={setShowAssignStaff}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Grant Staff Access</DialogTitle></DialogHeader>
          <form onSubmit={handleAssignStaff} className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Staff Member</Label>
              <Select value={staffForm.staff_id} onValueChange={v => setStaffForm({ ...staffForm, staff_id: v })}>
                <SelectTrigger data-testid="staff-member-select"><SelectValue placeholder="Select staff" /></SelectTrigger>
                <SelectContent>{members.filter(m => ['Staff', 'Coordinator', 'Manager', 'Director'].includes(m.role)).map(m => <SelectItem key={m.id} value={m.id}>{m.name} ({m.role})</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="flex gap-3"><Button type="button" variant="outline" className="flex-1" onClick={() => setShowAssignStaff(false)}>Cancel</Button><Button type="submit" className="flex-1" disabled={saving || !staffForm.staff_id} data-testid="save-staff-btn">{saving ? 'Saving...' : 'Grant Access'}</Button></div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Guest Request Dialog */}
      <Dialog open={showGuestRequest} onOpenChange={setShowGuestRequest}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Request Guest Visit</DialogTitle></DialogHeader>
          <form onSubmit={handleGuestRequest} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Guest Name *</Label><Input value={guestForm.guest_name} onChange={e => setGuestForm({ ...guestForm, guest_name: e.target.value })} required data-testid="guest-visit-name" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Phone</Label><Input value={guestForm.guest_phone} onChange={e => setGuestForm({ ...guestForm, guest_phone: e.target.value })} /></div>
              <div className="space-y-2"><Label>ID Number</Label><Input value={guestForm.guest_id_number} onChange={e => setGuestForm({ ...guestForm, guest_id_number: e.target.value })} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Visit Date</Label><Input type="date" value={guestForm.visit_date} onChange={e => setGuestForm({ ...guestForm, visit_date: e.target.value })} /></div>
              <div className="space-y-2"><Label>Visit Time</Label><Input type="time" value={guestForm.visit_time} onChange={e => setGuestForm({ ...guestForm, visit_time: e.target.value })} /></div>
            </div>
            <div className="space-y-2"><Label>Purpose</Label><Input value={guestForm.purpose} onChange={e => setGuestForm({ ...guestForm, purpose: e.target.value })} placeholder="Reason for visit" /></div>
            <div className="flex gap-3"><Button type="button" variant="outline" className="flex-1" onClick={() => setShowGuestRequest(false)}>Cancel</Button><Button type="submit" className="flex-1" disabled={saving || !guestForm.guest_name} data-testid="submit-guest-request-btn">{saving ? 'Submitting...' : 'Submit Request'}</Button></div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Scan In/Out Dialog */}
      <ScanDialog
        open={showScanDialog}
        onOpenChange={setShowScanDialog}
        scanMode={scanMode}
        setScanMode={setScanMode}
        scanForm={scanForm}
        setScanForm={setScanForm}
        members={members}
        guestRequests={guestRequests}
        saving={saving}
        onScan={handleScan}
      />

      {/* QR Pass View Modal */}
      <Dialog open={!!showQrPass} onOpenChange={() => setShowQrPass(null)}>
        <DialogContent className="max-w-xs">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><QrCode size={16} /> Guest Pass QR</DialogTitle></DialogHeader>
          {showQrPass && (
            <div className="text-center space-y-4">
              <div className="bg-white p-4 rounded-xl inline-block">
                <img src="https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1" alt="58:12 Global" className="h-6 mx-auto mb-3" data-testid="pass-logo" />
                <img src={generateQrDataUrl(showQrPass.id)} alt="Guest Pass QR Code" className="w-48 h-48 mx-auto" data-testid="guest-pass-qr-image" />
              </div>
              <div className="space-y-1">
                <p className="font-semibold">{showQrPass.guest_name}</p>
                <p className="text-xs text-muted-foreground font-mono">{showQrPass.id}</p>
                <p className="text-xs text-muted-foreground">{locName(showQrPass.location_id)}</p>
                <p className="text-xs">Valid: {showQrPass.valid_from} to {showQrPass.valid_until}</p>
                {showQrPass.valid_from_time && (
                  <p className="text-xs">Time: {showQrPass.valid_from_time} - {showQrPass.valid_until_time || '22:00'}</p>
                )}
              </div>
              <Badge variant={showQrPass.status === 'active' ? 'outline' : 'secondary'}
                className={showQrPass.status === 'active' ? 'border-green-500 text-green-600' : 'border-red-400 text-red-500'}>
                {showQrPass.status?.toUpperCase()}
              </Badge>
              <p className="text-xs text-muted-foreground">Scan this QR code at the entry gate</p>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Validate Result Modal */}
      <Dialog open={showValidateResult} onOpenChange={setShowValidateResult}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Pass Validation Result</DialogTitle></DialogHeader>
          {validateResult && (
            <div className="text-center space-y-4 py-4">
              <div className={`w-20 h-20 rounded-full mx-auto flex items-center justify-center ${validateResult.valid ? 'bg-green-100' : 'bg-red-100'}`}>
                {validateResult.valid ? <CheckCircle size={40} className="text-green-600" /> : <XCircle size={40} className="text-red-500" />}
              </div>
              <p className={`text-lg font-bold ${validateResult.valid ? 'text-green-600' : 'text-red-500'}`}>
                {validateResult.message}
              </p>
              {validateResult.pass && (
                <div className="text-sm space-y-1 text-muted-foreground">
                  <p>Guest: <span className="font-medium text-foreground">{validateResult.pass.guest_name}</span></p>
                  <p>Location: <span className="font-medium text-foreground">{validateResult.location_name}</span></p>
                  <p>Valid: {validateResult.pass.valid_from} to {validateResult.pass.valid_until}</p>
                  <p>Status: <Badge variant="outline" className="text-xs">{validateResult.pass.status}</Badge></p>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Extend Pass Modal */}
      <Dialog open={!!showExtendPass} onOpenChange={() => setShowExtendPass(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Extend Guest Pass</DialogTitle></DialogHeader>
          {showExtendPass && (
            <div className="space-y-4 mt-2">
              <p className="text-sm">Extend pass for <span className="font-semibold">{showExtendPass.guest_name}</span></p>
              <p className="text-xs text-muted-foreground">Currently valid until: {showExtendPass.valid_until}</p>
              <div className="space-y-2">
                <Label>Extend by (days)</Label>
                <Input type="number" min={1} max={365} value={extendDays} onChange={e => setExtendDays(e.target.value)} data-testid="extend-days-input" />
              </div>
              <div className="flex gap-3">
                <Button variant="outline" className="flex-1" onClick={() => setShowExtendPass(null)}>Cancel</Button>
                <Button className="flex-1" onClick={handleExtendPass} data-testid="confirm-extend-btn">Extend Pass</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* API Connection Form */}
      <Dialog open={showApiConnForm} onOpenChange={setShowApiConnForm}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Add Access Control API</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Name *</Label><Input value={apiConnForm.name} onChange={e => setApiConnForm({...apiConnForm, name: e.target.value})} placeholder="Front Door" /></div>
              <div className="space-y-1.5"><Label className="text-xs">Type</Label>
                <Select value={apiConnForm.type} onValueChange={v => setApiConnForm({...apiConnForm, type: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="door">Door</SelectItem><SelectItem value="gate">Gate</SelectItem><SelectItem value="turnstile">Turnstile</SelectItem><SelectItem value="barrier">Barrier</SelectItem></SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Provider</Label>
              <Select value={apiConnForm.provider} onValueChange={v => setApiConnForm({...apiConnForm, provider: v})}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="generic">Generic</SelectItem><SelectItem value="kisi">Kisi</SelectItem><SelectItem value="salto">Salto</SelectItem><SelectItem value="brivo">Brivo</SelectItem><SelectItem value="openpath">OpenPath</SelectItem><SelectItem value="unifi">Unifi Access</SelectItem></SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">API URL *</Label><Input value={apiConnForm.api_url} onChange={e => setApiConnForm({...apiConnForm, api_url: e.target.value})} placeholder="https://api.kisi.io/v1" /></div>
            <div className="space-y-1.5"><Label className="text-xs">API Key</Label><Input type="password" value={apiConnForm.api_key} onChange={e => setApiConnForm({...apiConnForm, api_key: e.target.value})} /></div>
            <div className="space-y-1.5"><Label className="text-xs">Door/Device Name</Label><Input value={apiConnForm.door_name} onChange={e => setApiConnForm({...apiConnForm, door_name: e.target.value})} placeholder="Main Entrance" /></div>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => setShowApiConnForm(false)}>Cancel</Button>
              <Button className="flex-1" onClick={async () => {
                if (!apiConnForm.name || !apiConnForm.api_url) { toast.error('Name and API URL required'); return; }
                try { const res = await accessApi.createApiConnection(apiConnForm); setApiConnections(prev => [...prev, res.data]); setShowApiConnForm(false); toast.success('Connection added'); }
                catch { toast.error('Failed'); }
              }} data-testid="save-api-conn">Add</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Guest Link Form */}
      <Dialog open={showGuestLinkForm} onOpenChange={setShowGuestLinkForm}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Create Guest Access Link</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label className="text-xs">Space / Room Name *</Label><Input value={guestLinkForm.space_name} onChange={e => setGuestLinkForm({...guestLinkForm, space_name: e.target.value})} placeholder="Conference Room A" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Max Uses (0=unlimited)</Label><Input type="number" min={0} value={guestLinkForm.max_uses} onChange={e => setGuestLinkForm({...guestLinkForm, max_uses: parseInt(e.target.value) || 0})} /></div>
              <div className="space-y-1.5"><Label className="text-xs">Expires</Label><Input type="date" value={guestLinkForm.expires_at} onChange={e => setGuestLinkForm({...guestLinkForm, expires_at: e.target.value})} /></div>
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer"><input type="checkbox" checked={guestLinkForm.requires_approval} onChange={e => setGuestLinkForm({...guestLinkForm, requires_approval: e.target.checked})} /> Requires admin approval</label>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => setShowGuestLinkForm(false)}>Cancel</Button>
              <Button className="flex-1" onClick={async () => {
                if (!guestLinkForm.space_name) { toast.error('Space name required'); return; }
                try { const res = await accessApi.createGuestLink({...guestLinkForm, location_id: selectedLocation}); setGuestLinks(prev => [...prev, res.data]); setShowGuestLinkForm(false); toast.success('Link created! Click "Copy Link" to share.'); }
                catch { toast.error('Failed'); }
              }} data-testid="save-guest-link">Create Link</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
