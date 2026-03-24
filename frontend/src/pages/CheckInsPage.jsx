import React, { useState, useEffect } from 'react';
import { Search, Plus, UserCheck, RefreshCw, KeyRound, LogOut, Wifi } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Card, CardContent } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { checkinsApi, eventsApi, membersApi } from '../services/api';
import { toast } from 'sonner';

const methodStyle = { qr: 'bg-blue-100 text-blue-700', manual: 'bg-slate-100 text-slate-700', id: 'bg-purple-100 text-purple-700', pin: 'bg-green-100 text-green-700', biometric: 'bg-indigo-100 text-indigo-700', nfc: 'bg-cyan-100 text-cyan-700' };
const typeStyle = { member: 'border-green-500 text-green-600', staff: 'border-blue-500 text-blue-600', visitor: 'border-orange-500 text-orange-600' };

export default function CheckInsPage() {
  const [checkins, setCheckins] = useState([]);
  const [stats, setStats] = useState({ total: 0, today: 0, members: 0, visitors: 0, staff: 0 });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
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

  const fetchData = async () => {
    setLoading(true);
    try {
      const [ciRes, statsRes] = await Promise.all([
        checkinsApi.list({ search: search || undefined, type: typeFilter !== 'all' ? typeFilter : undefined }),
        checkinsApi.stats(),
      ]);
      setCheckins(ciRes.data);
      setStats(statsRes.data);
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
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <Card className="shadow-soft rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-secondary/50 border-b border-border">
              <tr>
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
                <tr key={ci.id} className="hover:bg-accent/30 transition-colors">
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
    </div>
  );
}
