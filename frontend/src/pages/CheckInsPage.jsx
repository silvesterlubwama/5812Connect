import React, { useState, useEffect, useRef } from 'react';
import { Search, Plus, UserCheck, RefreshCw, KeyRound, LogOut, Wifi, Baby, QrCode, Phone, Printer } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Card, CardContent } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Checkbox } from '../components/ui/checkbox';
import { ChildTag, ParentBadge } from '../components/PrintableBadges';
import { checkinsApi, eventsApi, membersApi, locationsApi } from '../services/api';
import { toast } from 'sonner';
import { BulkActionBar, exportToCSV, SelectCheckbox } from '../components/BulkActions';

const methodStyle = { qr: 'bg-blue-100 text-blue-700', manual: 'bg-slate-100 text-slate-700', id: 'bg-purple-100 text-purple-700', pin: 'bg-green-100 text-green-700', biometric: 'bg-indigo-100 text-indigo-700', nfc: 'bg-cyan-100 text-cyan-700', parent_id: 'bg-pink-100 text-pink-700' };
const typeStyle = { member: 'border-green-500 text-green-600', staff: 'border-blue-500 text-blue-600', visitor: 'border-orange-500 text-orange-600', child: 'border-emerald-500 text-emerald-600' };

export default function CheckInsPage() {
  const [checkins, setCheckins] = useState([]);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [stats, setStats] = useState({ total: 0, today: 0, members: 0, visitors: 0, staff: 0 });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [locationFilter, setLocationFilter] = useState('');
  const [allLocations, setAllLocations] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
  const [events, setEvents] = useState([]);
  const [saving, setSaving] = useState(false);
  const [newCI, setNewCI] = useState({ member_name: '', type: 'member', event_id: '', event_name: '', method: 'manual' });
  const [showPin, setShowPin] = useState(false);
  const [pinCode, setPinCode] = useState('');
  const [pinEvent, setPinEvent] = useState('');
  const [showNfc, setShowNfc] = useState(false);
  const [nfcStatus, setNfcStatus] = useState('idle'); // idle | scanning | connected | unsupported | success | error
  const [nfcMember, setNfcMember] = useState(null);
  const [nfcEventId, setNfcEventId] = useState('');

  // Parent check-in state
  const [showParentCheckin, setShowParentCheckin] = useState(false);
  const [parentLookup, setParentLookup] = useState('');
  const [parentEventId, setParentEventId] = useState('');
  const [parentData, setParentData] = useState(null);
  const [parentChildren, setParentChildren] = useState([]);
  const [selectedChildIds, setSelectedChildIds] = useState([]);
  const [lookingUp, setLookingUp] = useState(false);
  const [checkingInChildren, setCheckingInChildren] = useState(false);
  const [showQrScanner, setShowQrScanner] = useState(false);
  const [showChildTags, setShowChildTags] = useState(false);
  const [checkedInData, setCheckedInData] = useState(null);
  const [showParentBadge, setShowParentBadge] = useState(false);
  const videoRef = useRef(null);
  const streamRef = useRef(null);

  const handleNfcScan = async () => {
    if (!('NDEFReader' in window)) {
      setNfcStatus('unsupported');
      return;
    }
    setNfcStatus('scanning');
    try {
      const reader = new window.NDEFReader();
      await reader.scan();
      reader.onreading = async ({ serialNumber, message }) => {
        setNfcStatus('connected');
        // Try to decode member ID from NDEF records
        let memberId = null;
        if (message && message.records.length > 0) {
          for (const record of message.records) {
            if (record.recordType === 'text') {
              const decoder = new TextDecoder(record.encoding || 'utf-8');
              memberId = decoder.decode(record.data);
              break;
            } else if (record.recordType === 'url') {
              const url = new TextDecoder().decode(record.data);
              memberId = url.split('/').pop();
              break;
            }
          }
        }
        // Fallback: use tag serial as lookup key
        const lookupKey = memberId || serialNumber || '';
        try {
          const res = await membersApi.list({ search: lookupKey, limit: 1 });
          const found = (res.data.members || res.data || [])[0];
          if (found) {
            setNfcMember(found);
            setNfcStatus('success');
          } else {
            toast.warning(`NFC tag read (${serialNumber}) — member not found. Tag ID: ${serialNumber}`);
            setNfcStatus('idle');
          }
        } catch {
          toast.error('Failed to look up member from NFC tag');
          setNfcStatus('idle');
        }
      };
      reader.onerror = (err) => {
        setNfcStatus('error');
        toast.error(`NFC error: ${err.message}`);
      };
    } catch (err) {
      if (err.name === 'NotAllowedError') {
        toast.error('NFC permission denied. Please allow NFC in browser settings.');
      } else if (err.name === 'NotSupportedError') {
        setNfcStatus('unsupported');
      } else {
        setNfcStatus('error');
        toast.error(`NFC scan failed: ${err.message}`);
      }
    }
  };

  const confirmNfcCheckin = async () => {
    if (!nfcMember) return;
    const eventObj = events.find(ev => ev.id === nfcEventId);
    try {
      await checkinsApi.create({ member_name: nfcMember.name, type: 'member', event_id: nfcEventId || '', event_name: eventObj?.title || '', method: 'nfc' });
      toast.success(`${nfcMember.name} checked in via NFC!`);
      setShowNfc(false); setNfcMember(null); setNfcStatus('idle'); fetchData();
    } catch { toast.error('Check-in failed'); }
  };

  // Parent check-in handlers
  const handleParentLookup = async () => {
    if (!parentLookup.trim()) return;
    setLookingUp(true);
    setParentData(null);
    setParentChildren([]);
    try {
      const res = await checkinsApi.parentLookup({ lookup: parentLookup.trim(), event_id: parentEventId });
      setParentData(res.data.parent);
      setParentChildren(res.data.children || []);
      setSelectedChildIds((res.data.children || []).map(c => c.id)); // select all by default
      if ((res.data.children || []).length === 0) {
        toast.info('No children found for this parent');
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Parent not found');
    } finally { setLookingUp(false); }
  };

  const handleCheckinChildren = async () => {
    if (!parentData || selectedChildIds.length === 0) return;
    setCheckingInChildren(true);
    const eventObj = events.find(ev => ev.id === parentEventId);
    try {
      const res = await checkinsApi.parentLookup({
        lookup: parentData.id || parentData.phone || parentData.email,
        event_id: parentEventId,
        event_name: eventObj?.title || '',
        checkin: true,
        child_ids: selectedChildIds,
      });
      const count = (res.data.checked_in || []).length;
      toast.success(`${count} child${count > 1 ? 'ren' : ''} checked in!`);
      setCheckedInData({
        parent: res.data.parent,
        children: parentChildren.filter(c => selectedChildIds.includes(c.id)),
        eventName: eventObj?.title || '',
      });
      setShowParentCheckin(false);
      setShowChildTags(true);
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Check-in failed');
    } finally { setCheckingInChildren(false); }
  };

  const resetParentCheckin = () => {
    setParentLookup('');
    setParentData(null);
    setParentChildren([]);
    setSelectedChildIds([]);
  };

  const toggleChildSelection = (childId) => {
    setSelectedChildIds(prev =>
      prev.includes(childId) ? prev.filter(id => id !== childId) : [...prev, childId]
    );
  };

  const startQrScan = async () => {
    setShowQrScanner(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play();
      }
      // Use BarcodeDetector API if available
      if ('BarcodeDetector' in window) {
        const detector = new window.BarcodeDetector({ formats: ['qr_code'] });
        const scanLoop = async () => {
          if (!videoRef.current || videoRef.current.readyState !== 4) {
            requestAnimationFrame(scanLoop);
            return;
          }
          try {
            const barcodes = await detector.detect(videoRef.current);
            if (barcodes.length > 0) {
              const code = barcodes[0].rawValue;
              stopQrScan();
              setParentLookup(code);
              // Auto-lookup
              setLookingUp(true);
              try {
                const res = await checkinsApi.parentLookup({ lookup: code, event_id: parentEventId });
                setParentData(res.data.parent);
                setParentChildren(res.data.children || []);
                setSelectedChildIds((res.data.children || []).map(c => c.id));
              } catch (err) { toast.error(err.response?.data?.detail || 'Not found'); }
              finally { setLookingUp(false); }
              return;
            }
          } catch (e) { console.warn(e.message || e); }
          requestAnimationFrame(scanLoop);
        };
        requestAnimationFrame(scanLoop);
      } else {
        toast.info('QR scanning requires BarcodeDetector API. Try entering phone/ID manually.');
        stopQrScan();
      }
    } catch (err) {
      toast.error('Camera access denied');
      setShowQrScanner(false);
    }
  };

  const stopQrScan = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    setShowQrScanner(false);
  };

  const fetchData = async () => {
    setLoading(true);
    try {
      const [ciRes, statsRes, locsRes] = await Promise.all([
        checkinsApi.list({ search: search || undefined, type: typeFilter !== 'all' ? typeFilter : undefined, location_id: locationFilter || undefined }),
        checkinsApi.stats(),
        locationsApi.list().catch(() => ({ data: [] })),
      ]);
      setCheckins(ciRes.data);
      setStats(statsRes.data);
      setAllLocations(locsRes.data || []);
    } catch { toast.error('Failed to load check-ins'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchData(); }, [search, typeFilter]);

  useEffect(() => {
    eventsApi.list({ status: 'upcoming' }).then(res => setEvents(res.data)).catch(() => {});
  }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    setSaving(true);
    const eventObj = events.find(ev => ev.id === newCI.event_id);
    try {
      const payload = { ...newCI, event_name: eventObj?.title || newCI.event_name };
      const res = await checkinsApi.create(payload);
      setCheckins(prev => [res.data, ...prev]);
      setStats(s => ({ ...s, total: s.total + 1, today: s.today + 1, [res.data.type + 's']: (s[res.data.type + 's'] || 0) + 1 }));
      setShowAdd(false);
      setNewCI({ member_name: '', type: 'member', event_id: '', event_name: '', method: 'manual' });
      toast.success(`${res.data.member_name} checked in!`);
    } catch { toast.error('Failed to check in'); }
    finally { setSaving(false); }
  };

  const formatTime = (iso) => new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });

  const handlePinCheckin = async () => {
    if (!pinCode.trim()) return;
    const eventObj = events.find(ev => ev.id === pinEvent);
    try {
      const res = await checkinsApi.pinCheckin({ pin: pinCode, event_id: pinEvent || undefined, event_name: eventObj?.title || '', action: 'checkin' });
      toast.success(`${res.data.member?.name || 'Member'} checked in via PIN!`);
      setPinCode(''); setShowPin(false); fetchData();
    } catch (err) { toast.error(err.response?.data?.detail || 'Invalid PIN'); }
  };

  const handleCheckout = async (ci) => {
    try {
      await checkinsApi.checkout(ci.id);
      toast.success(`${ci.member_name} checked out`);
      fetchData();
    } catch (err) { toast.error(err.response?.data?.detail || 'Checkout failed'); }
  };

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Check-Ins</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{stats.total} total · {stats.today} today</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" asChild><a href="/kiosk" target="_blank" className="gap-2 flex items-center"><UserCheck size={15} />Kiosk</a></Button>
          <Button variant="outline" onClick={() => setShowPin(true)} className="gap-2"><KeyRound size={15} /> PIN</Button>
          <Button variant="outline" onClick={() => { setShowNfc(true); setNfcStatus('idle'); setNfcMember(null); }} className="gap-2" data-testid="nfc-scan-btn"><Wifi size={15} /> NFC</Button>
          <Button variant="outline" onClick={() => { setShowParentCheckin(true); resetParentCheckin(); }} className="gap-2" data-testid="parent-checkin-btn"><Baby size={15} /> Parent Check-In</Button>
          <Button variant="outline" size="sm" onClick={fetchData}><RefreshCw size={14} /></Button>
          <Button onClick={() => setShowAdd(true)} className="gap-2"><Plus size={16} /> Manual Check-In</Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'Total', value: stats.total, color: 'text-foreground' },
          { label: 'Today', value: stats.today, color: 'text-primary' },
          { label: 'Members', value: stats.members, color: 'text-green-600' },
          { label: 'Visitors', value: stats.visitors, color: 'text-orange-500' },
          { label: 'Children', value: stats.children || 0, color: 'text-emerald-500' },
        ].map(s => (
          <Card key={s.label} className="shadow-soft rounded-xl">
            <CardContent className="p-4 text-center">
              <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
              <p className="text-xs text-muted-foreground mt-0.5">{s.label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input placeholder="Search check-ins..." className="pl-9" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-36"><SelectValue placeholder="Type" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            <SelectItem value="member">Member</SelectItem>
            <SelectItem value="staff">Staff</SelectItem>
            <SelectItem value="visitor">Visitor</SelectItem>
            <SelectItem value="child">Child</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <Card className="shadow-soft rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          {selectedIds.size > 0 && <BulkActionBar selectedIds={selectedIds} onClear={() => setSelectedIds(new Set())} onBulkExport={() => { const sel = checkins.filter(c => selectedIds.has(c.id)); exportToCSV(sel.length ? sel : checkins, 'checkins-export.csv'); }} />}
          <table className="w-full text-sm">
            <thead className="bg-secondary/50 border-b border-border">
              <tr>
                <th className="px-2 py-3 w-8"><input type="checkbox" className="accent-primary" checked={selectedIds.size > 0 && checkins.every(c => selectedIds.has(c.id))} onChange={() => { if (selectedIds.size === checkins.length) setSelectedIds(new Set()); else setSelectedIds(new Set(checkins.map(c => c.id))); }} /></th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Person</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Type</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Event</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Method</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Time</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {loading ? (
                [...Array(5)].map((_, i) => (
                  <tr key={i}><td colSpan={5} className="px-4 py-3"><div className="h-5 bg-muted animate-pulse rounded" /></td></tr>
                ))
              ) : checkins.map(ci => (
                <tr key={ci.id} className={`hover:bg-accent/30 transition-colors ${selectedIds.has(ci.id) ? 'bg-primary/5' : ''}`}>
                  <td className="px-2 py-3"><input type="checkbox" className="accent-primary" checked={selectedIds.has(ci.id)} onChange={() => setSelectedIds(prev => { const n = new Set(prev); n.has(ci.id) ? n.delete(ci.id) : n.add(ci.id); return n; })} /></td>
                  <td className="px-4 py-3 font-medium">{ci.member_name}</td>
                  <td className="px-4 py-3">
                    <Badge variant="outline" className={`text-xs capitalize ${typeStyle[ci.type] || ''}`}>{ci.type}</Badge>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{ci.event_name || '—'}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium uppercase ${methodStyle[ci.method] || ''}`}>{ci.method}</span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">{formatTime(ci.check_in_time)}</td>
                  <td className="px-4 py-3">
                    {ci.check_out_time ? (
                      <Badge className="bg-green-100 text-green-700 text-xs">Out {new Date(ci.check_out_time).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}</Badge>
                    ) : (
                      <Button data-testid={`checkout-${ci.id}`} size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => handleCheckout(ci)}><LogOut size={12} />Check Out</Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!loading && checkins.length === 0 && (
            <p className="text-center py-12 text-muted-foreground">No check-ins found</p>
          )}
        </div>
      </Card>

      {/* Manual Check-In Dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Manual Check-In</DialogTitle></DialogHeader>
          <form onSubmit={handleAdd} className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Person Name *</Label>
              <Input placeholder="Full name" value={newCI.member_name} onChange={e => setNewCI({...newCI, member_name: e.target.value})} required />
            </div>
            <div className="space-y-2">
              <Label>Type</Label>
              <Select value={newCI.type} onValueChange={v => setNewCI({...newCI, type: v})}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="member">Member</SelectItem>
                  <SelectItem value="staff">Staff</SelectItem>
                  <SelectItem value="visitor">Visitor</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Event</Label>
              <Select value={newCI.event_id} onValueChange={v => setNewCI({...newCI, event_id: v})}>
                <SelectTrigger><SelectValue placeholder="Select event (optional)" /></SelectTrigger>
                <SelectContent>
                  {events.map(e => <SelectItem key={e.id} value={e.id}>{e.title}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Method</Label>
              <Select value={newCI.method} onValueChange={v => setNewCI({...newCI, method: v})}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="manual">Manual</SelectItem>
                  <SelectItem value="qr">QR Code</SelectItem>
                  <SelectItem value="id">ID Scan</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowAdd(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving}>{saving ? 'Checking in...' : 'Check In'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* PIN Check-In Dialog */}
      <Dialog open={showPin} onOpenChange={setShowPin}>
        <DialogContent className="max-w-xs">
          <DialogHeader><DialogTitle>PIN Check-In</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Event (optional)</Label>
              <Select value={pinEvent} onValueChange={setPinEvent}>
                <SelectTrigger><SelectValue placeholder="Select event" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">No event</SelectItem>
                  {events.map(e => <SelectItem key={e.id} value={e.id}>{e.title}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Enter PIN *</Label>
              <Input data-testid="pin-input" placeholder="4-digit PIN" value={pinCode} onChange={e => setPinCode(e.target.value)} maxLength={10} className="text-center text-2xl tracking-[0.3em] font-mono" />
            </div>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => { setShowPin(false); setPinCode(''); }}>Cancel</Button>
              <Button className="flex-1" onClick={handlePinCheckin} disabled={!pinCode.trim()}>Check In</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
      {/* NFC Check-In Dialog */}
      <Dialog open={showNfc} onOpenChange={(o) => { if (!o) { setShowNfc(false); setNfcStatus('idle'); setNfcMember(null); } }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>NFC Check-In</DialogTitle>
            <DialogDescription>Tap an NFC tag to check in a member</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            {nfcStatus === 'idle' && (
              <div className="space-y-3">
                <div className="space-y-2">
                  <Label>Event (optional)</Label>
                  <Select value={nfcEventId || '_none'} onValueChange={v => setNfcEventId(v === '_none' ? '' : v)}>
                    <SelectTrigger><SelectValue placeholder="Select event" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="_none">No event</SelectItem>
                      {events.map(e => <SelectItem key={e.id} value={e.id}>{e.title}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <Button className="w-full gap-2" onClick={handleNfcScan} data-testid="start-nfc-scan">
                  <Wifi size={16} /> Start NFC Scan
                </Button>
              </div>
            )}
            {nfcStatus === 'scanning' && (
              <div className="flex flex-col items-center gap-4 py-6">
                <div className="relative">
                  <div className="h-20 w-20 rounded-full border-4 border-primary/30 flex items-center justify-center">
                    <Wifi size={32} className="text-primary animate-pulse" />
                  </div>
                  <div className="absolute inset-0 rounded-full border-4 border-primary border-t-transparent animate-spin" />
                </div>
                <p className="text-sm font-medium">Waiting for NFC tag...</p>
                <p className="text-xs text-muted-foreground text-center">Hold the NFC card or phone near the reader</p>
                <Button variant="outline" size="sm" onClick={() => setNfcStatus('idle')}>Cancel</Button>
              </div>
            )}
            {nfcStatus === 'success' && nfcMember && (
              <div className="space-y-4">
                <div className="p-4 rounded-xl bg-green-50 border border-green-200 text-center">
                  <p className="text-xs text-green-600 mb-1">NFC Tag Detected</p>
                  <p className="font-semibold text-green-900">{nfcMember.name}</p>
                  <p className="text-xs text-green-700">{nfcMember.role} · {nfcMember.group}</p>
                </div>
                <div className="flex gap-3">
                  <Button variant="outline" className="flex-1" onClick={() => { setNfcStatus('idle'); setNfcMember(null); }}>Cancel</Button>
                  <Button className="flex-1" onClick={confirmNfcCheckin} data-testid="confirm-nfc-checkin">Confirm Check-In</Button>
                </div>
              </div>
            )}
            {nfcStatus === 'unsupported' && (
              <div className="space-y-3">
                <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-sm text-amber-800">
                  <p className="font-medium mb-1">NFC Not Supported</p>
                  <p className="text-xs">Web NFC (NDEFReader) requires Chrome on Android. Desktop browsers and Safari are not supported.</p>
                  <p className="text-xs mt-2">Please use PIN check-in or manual entry instead.</p>
                </div>
                <Button variant="outline" className="w-full" onClick={() => setShowNfc(false)}>Close</Button>
              </div>
            )}
            {nfcStatus === 'error' && (
              <div className="space-y-3">
                <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-sm text-red-800">NFC scan failed. Please try again.</div>
                <div className="flex gap-3">
                  <Button variant="outline" className="flex-1" onClick={() => setShowNfc(false)}>Close</Button>
                  <Button className="flex-1" onClick={() => { setNfcStatus('idle'); handleNfcScan(); }}>Retry</Button>
                </div>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Parent Check-In Dialog */}
      <Dialog open={showParentCheckin} onOpenChange={(o) => { if (!o) { setShowParentCheckin(false); stopQrScan(); } }}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Baby size={18} className="text-emerald-500" /> Parent Check-In</DialogTitle>
            <DialogDescription>Look up a parent by phone, email, ID, or QR code to check in their children</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Event (optional)</Label>
              <Select value={parentEventId || '_none'} onValueChange={v => setParentEventId(v === '_none' ? '' : v)}>
                <SelectTrigger data-testid="parent-event-select"><SelectValue placeholder="Select event" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">No event</SelectItem>
                  {events.map(e => <SelectItem key={e.id} value={e.id}>{e.title}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>

            {!parentData && (
              <>
                <div className="space-y-2">
                  <Label>Parent Phone, Email, or ID *</Label>
                  <div className="flex gap-2">
                    <Input
                      data-testid="parent-lookup-input"
                      placeholder="e.g. +256 700 123456"
                      value={parentLookup}
                      onChange={e => setParentLookup(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); handleParentLookup(); } }}
                      className="flex-1"
                    />
                    <Button variant="outline" size="icon" onClick={startQrScan} title="Scan QR" data-testid="qr-scan-btn"><QrCode size={16} /></Button>
                  </div>
                </div>

                {showQrScanner && (
                  <div className="relative rounded-lg overflow-hidden border border-border bg-black">
                    <video ref={videoRef} className="w-full h-48 object-cover" muted playsInline />
                    <div className="absolute inset-0 flex items-center justify-center">
                      <div className="w-40 h-40 border-2 border-white/60 rounded-lg" />
                    </div>
                    <Button size="sm" variant="secondary" className="absolute bottom-2 right-2" onClick={stopQrScan}>Close</Button>
                  </div>
                )}

                <Button className="w-full gap-2" onClick={handleParentLookup} disabled={lookingUp || !parentLookup.trim()} data-testid="lookup-parent-btn">
                  <Phone size={14} /> {lookingUp ? 'Looking up...' : 'Find Children'}
                </Button>
              </>
            )}

            {parentData && (
              <>
                <div className="p-3 rounded-lg bg-accent/30 border border-border">
                  <p className="text-xs text-muted-foreground">Parent Found</p>
                  <p className="font-medium">{parentData.name}</p>
                  <div className="flex gap-3 text-xs text-muted-foreground mt-0.5">
                    {parentData.phone && <span>{parentData.phone}</span>}
                    {parentData.email && <span>{parentData.email}</span>}
                  </div>
                </div>

                {parentChildren.length > 0 ? (
                  <div className="space-y-2">
                    <Label>Select Children to Check In</Label>
                    {parentChildren.map(child => (
                      <div key={child.id} className="flex items-center gap-3 p-3 rounded-lg border border-border hover:bg-accent/20 transition-colors" data-testid={`parent-child-${child.id}`}>
                        <Checkbox
                          checked={selectedChildIds.includes(child.id)}
                          onCheckedChange={() => toggleChildSelection(child.id)}
                          data-testid={`select-child-${child.id}`}
                        />
                        <div className="flex-1">
                          <p className="text-sm font-medium">{child.name}</p>
                          <div className="flex gap-2 text-xs text-muted-foreground">
                            {child.class_group && <span>{child.class_group}</span>}
                            {child.gender && <span className="capitalize">{child.gender}</span>}
                          </div>
                          {child.allergies && <Badge variant="destructive" className="text-[10px] mt-1">{child.allergies}</Badge>}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground text-center py-4">No children found for this parent</p>
                )}

                <div className="flex gap-3 pt-2">
                  <Button variant="outline" className="flex-1" onClick={resetParentCheckin} data-testid="parent-checkin-back">Back</Button>
                  <Button
                    className="flex-1 gap-1.5"
                    onClick={handleCheckinChildren}
                    disabled={checkingInChildren || selectedChildIds.length === 0}
                    data-testid="checkin-children-btn"
                  >
                    <UserCheck size={14} />
                    {checkingInChildren ? 'Checking in...' : `Check In ${selectedChildIds.length} Child${selectedChildIds.length > 1 ? 'ren' : ''}`}
                  </Button>
                </div>
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>
      {/* Child Tags Print Dialog */}
      <Dialog open={showChildTags} onOpenChange={(o) => { if (!o) { setShowChildTags(false); setCheckedInData(null); } }}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Printer size={18} /> Print Child Tags</DialogTitle>
            <DialogDescription>{checkedInData?.children?.length || 0} child tag{(checkedInData?.children?.length || 0) > 1 ? 's' : ''} ready to print</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            {(checkedInData?.children || []).map(child => (
              <ChildTag
                key={child.id}
                child={child}
                parentPhone={checkedInData?.parent?.phone}
                eventName={checkedInData?.eventName}
              />
            ))}
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => { setShowChildTags(false); setCheckedInData(null); }}>Done</Button>
              <Button className="flex-1 gap-1.5" onClick={() => setShowParentBadge(true)} data-testid="show-parent-badge-btn"><QrCode size={13} /> Print Parent Badge</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Parent Badge Dialog */}
      <Dialog open={showParentBadge} onOpenChange={setShowParentBadge}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Parent Badge</DialogTitle></DialogHeader>
          {checkedInData?.parent && (
            <ParentBadge parent={checkedInData.parent} children={checkedInData.children} />
          )}
          <Button variant="outline" className="w-full mt-2" onClick={() => setShowParentBadge(false)}>Close</Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
