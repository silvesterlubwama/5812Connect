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
import { accessApi, locationsApi, membersApi, biometricApi, nfcApi } from '../services/api';
import { toast } from 'sonner';
import { Fingerprint, Smartphone } from 'lucide-react';

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
    setSaving(true);
    try {
      await accessApi.assignResident({ member_id: residentForm.member_id, location_id: selectedLocation, tags: residentForm.tags.split(',').map(t => t.trim()).filter(Boolean) });
      toast.success('Resident assigned');
      setShowAssignResident(false);
      setResidentForm({ member_id: '', tags: '' });
      fetchLocationData();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
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
            <Label className="text-sm font-medium whitespace-nowrap">Location:</Label>
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
            <TabsList>
              <TabsTrigger value="residents" data-testid="tab-residents"><Users size={13} className="mr-1.5" /> Residents</TabsTrigger>
              <TabsTrigger value="staff" data-testid="tab-staff"><KeyRound size={13} className="mr-1.5" /> Staff Access</TabsTrigger>
              <TabsTrigger value="guests" data-testid="tab-guests"><UserPlus size={13} className="mr-1.5" /> Guest Requests</TabsTrigger>
              <TabsTrigger value="passes" data-testid="tab-passes"><QrCode size={13} className="mr-1.5" /> Guest Passes</TabsTrigger>
              <TabsTrigger value="log" data-testid="tab-scan-log"><Clock size={13} className="mr-1.5" /> Scan Log</TabsTrigger>
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
                          <Badge variant={g.status === 'approved' ? 'outline' : g.status === 'rejected' ? 'destructive' : 'secondary'}
                            className={`text-xs ${g.status === 'approved' ? 'border-green-500 text-green-600' : ''}`}>
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
                            className={`text-xs ${gp.status === 'active' ? 'border-green-500 text-green-600' : gp.status === 'expired' ? 'border-red-400 text-red-500' : 'border-border'}`}>
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
      <Dialog open={showScanDialog} onOpenChange={setShowScanDialog}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Scan In/Out</DialogTitle></DialogHeader>
          <form onSubmit={handleScan} className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Scan Type</Label>
              <Select value={scanMode} onValueChange={v => { setScanMode(v); setScanForm({ member_id: '', action: scanForm.action, guest_request_id: '', guest_name: '' }); }}>
                <SelectTrigger data-testid="scan-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="member">Resident / Staff</SelectItem>
                  <SelectItem value="guest">Approved Guest</SelectItem>
                  <SelectItem value="nfc">NFC Tag</SelectItem>
                  <SelectItem value="biometric">Biometric</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {scanMode === 'member' ? (
              <div className="space-y-2">
                <Label>Member</Label>
                <Select value={scanForm.member_id} onValueChange={v => setScanForm({ ...scanForm, member_id: v })}>
                  <SelectTrigger data-testid="scan-member-select"><SelectValue placeholder="Select person" /></SelectTrigger>
                  <SelectContent>{members.map(m => <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            ) : scanMode === 'guest' ? (
              <>
                <div className="space-y-2">
                  <Label>Approved Guest Request</Label>
                  <Select value={scanForm.guest_request_id} onValueChange={v => {
                    const gr = guestRequests.find(g => g.id === v);
                    setScanForm({ ...scanForm, guest_request_id: v, guest_name: gr?.guest_name || '' });
                  }}>
                    <SelectTrigger data-testid="scan-guest-select"><SelectValue placeholder="Select approved guest" /></SelectTrigger>
                    <SelectContent>{guestRequests.filter(g => g.status === 'approved').map(g => <SelectItem key={g.id} value={g.id}>{g.guest_name} — {g.visit_date}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </>
            ) : scanMode === 'nfc' ? (
              <div className="space-y-3">
                <div className="p-6 rounded-xl border-2 border-dashed border-primary/30 bg-primary/5 text-center">
                  <Smartphone size={40} className="mx-auto mb-2 text-primary opacity-60" />
                  <p className="text-sm font-medium">Place NFC tag on device</p>
                  <p className="text-xs text-muted-foreground mt-1">Or enter serial number manually</p>
                </div>
                <div className="space-y-2">
                  <Label>NFC Serial Number</Label>
                  <Input placeholder="e.g. 04:A2:B3:C4:D5" value={scanForm.member_id} onChange={e => setScanForm({ ...scanForm, member_id: e.target.value })} data-testid="nfc-serial-input" />
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="p-6 rounded-xl border-2 border-dashed border-primary/30 bg-primary/5 text-center">
                  <Fingerprint size={40} className="mx-auto mb-2 text-primary opacity-60" />
                  <p className="text-sm font-medium">Touch the fingerprint sensor</p>
                  <p className="text-xs text-muted-foreground mt-1">Or enter credential ID manually</p>
                </div>
                <div className="space-y-2">
                  <Label>Credential ID</Label>
                  <Input placeholder="Credential identifier" value={scanForm.member_id} onChange={e => setScanForm({ ...scanForm, member_id: e.target.value })} data-testid="biometric-credential-input" />
                </div>
              </div>
            )}
            <div className="space-y-2">
              <Label>Action</Label>
              <Select value={scanForm.action} onValueChange={v => setScanForm({ ...scanForm, action: v })}>
                <SelectTrigger data-testid="scan-action-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="in">Scan IN</SelectItem>
                  <SelectItem value="out">Scan OUT</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-3">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowScanDialog(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving || (scanMode === 'member' ? !scanForm.member_id : scanMode === 'guest' ? !scanForm.guest_request_id : !scanForm.member_id)} data-testid="execute-scan-btn">
                {saving ? 'Processing...' : scanForm.action === 'in' ? 'Scan IN' : 'Scan OUT'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

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
    </div>
  );
}
