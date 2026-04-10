import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { CreditCard, UserCheck, Eye, EyeOff, Search, ScanLine, LogOut, Wifi, WifiOff, Users, Clock, MapPin, Fingerprint, Smartphone, UserPlus, History, Star, X } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { kioskApi, locationsApi, accessApi, nfcApi, biometricApi, authApi } from '../services/api';
import api from '../services/api';
import { toast } from 'sonner';

// ===== Visitor Memory Helpers =====
const KIOSK_VISITORS_KEY = 'kiosk_recent_visitors';
const MAX_RECENT = 8;
const saveRecentVisitor = (v) => {
  try {
    const existing = getRecentVisitors().filter(rv => rv.phone !== v.phone && rv.id !== v.id);
    const updated = [{ ...v, last_visit: new Date().toISOString() }, ...existing].slice(0, MAX_RECENT);
    localStorage.setItem(KIOSK_VISITORS_KEY, JSON.stringify(updated));
  } catch (e) { console.warn(e.message || e); }
};
const getRecentVisitors = () => {
  try { return JSON.parse(localStorage.getItem(KIOSK_VISITORS_KEY) || '[]'); } catch { return []; }
};
const removeRecentVisitor = (id) => {
  try {
    const updated = getRecentVisitors().filter(v => v.id !== id);
    localStorage.setItem(KIOSK_VISITORS_KEY, JSON.stringify(updated));
  } catch (e) { console.warn(e.message || e); }
};

export default function KioskPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState('home');
  const [authenticated, setAuthenticated] = useState(false);
  const [staffUser, setStaffUser] = useState(null);
  const [token, setToken] = useState('');

  const [visitorName, setVisitorName] = useState('');
  const [visitorPhone, setVisitorPhone] = useState('');
  const [lookupId, setLookupId] = useState('');
  const [foundMember, setFoundMember] = useState(null);
  const [lookupLoading, setLookupLoading] = useState(false);

  // Recent visitors & guest registration
  const [recentVisitors, setRecentVisitors] = useState([]);
  const [showGuestRegister, setShowGuestRegister] = useState(false);
  const [guestForm, setGuestForm] = useState({ name: '', phone: '', role: 'visitor', notes: '' });
  const [guestLoading, setGuestLoading] = useState(false);
  const [registeredGuest, setRegisteredGuest] = useState(null);

  // Access scan mode
  const [locations, setLocations] = useState([]);
  const [selectedLocation, setSelectedLocation] = useState('');
  const [scanAction, setScanAction] = useState('in');
  const [scanMemberId, setScanMemberId] = useState('');
  const [scanResult, setScanResult] = useState(null);
  const [recentScans, setRecentScans] = useState([]);
  const [todayStats, setTodayStats] = useState({ checkIns: 0, visitors: 0, scans: 0 });
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [scanType, setScanType] = useState('manual'); // manual, nfc, biometric
  const [lockMode, setLockMode] = useState(false);
  const [showSignup, setShowSignup] = useState(false);
  const [signupForm, setSignupForm] = useState({ name: '', phone: '', email: '', role: 'Member' });

  // Sound effects for check-in result
  const playSound = (success) => {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      if (success) {
        osc.frequency.value = 880; gain.gain.value = 0.3;
        osc.start(); setTimeout(() => { osc.frequency.value = 1100; }, 100);
        setTimeout(() => { osc.stop(); ctx.close(); }, 250);
      } else {
        osc.frequency.value = 200; osc.type = 'square'; gain.gain.value = 0.3;
        osc.start(); setTimeout(() => { osc.stop(); ctx.close(); }, 400);
      }
    } catch (e) { console.warn(e.message || e); }
  };

  // QR/ID scanning via device camera
  const handleIdScan = async (qrData) => {
    if (!qrData) return;
    setLookupLoading(true);
    try {
      const authHeader = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await api.post('/checkins/qr-scan', { qr_data: qrData }, { headers: authHeader });
      setFoundMember(res.data.member);
      playSound(true);
      toast.success(`${res.data.member?.name} checked in!`);
      setTodayStats(prev => ({ ...prev, checkIns: prev.checkIns + 1 }));
    } catch (err) {
      playSound(false);
      toast.error(err.response?.data?.detail || 'Check-in failed - try signup');
      setShowSignup(true);
    }
    finally { setLookupLoading(false); }
  };

  const handleQuickSignup = async () => {
    if (!signupForm.name.trim()) { toast.error('Name is required'); return; }
    try {
      const res = await api.post('/auth/visitor-register', signupForm);
      toast.success(`${signupForm.name} registered! PIN: ${res.data.pin}`);
      playSound(true);
      setShowSignup(false);
      setSignupForm({ name: '', phone: '', email: '', role: 'Member' });
    } catch (err) { toast.error(err.response?.data?.detail || 'Signup failed'); }
  };

  useEffect(() => {
    const goOnline = () => setIsOnline(true);
    const goOffline = () => { setIsOnline(false); toast.warning('Offline — check-ins will be queued'); };
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    // Load recent visitors from local storage
    setRecentVisitors(getRecentVisitors());
    return () => { window.removeEventListener('online', goOnline); window.removeEventListener('offline', goOffline); };
  }, []);

  const handleStaffLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await api.post('/auth/login', { identifier: email, password });
      const t = res.data.token;
      setToken(t);
      api.defaults.headers.common['Authorization'] = `Bearer ${t}`;
      const meRes = await api.get('/auth/me');
      setStaffUser(meRes.data);
      setAuthenticated(true);
      setView('dashboard');
      toast.success(`Welcome, ${meRes.data.name}`);
      // Load locations for access scanning
      try {
        const locsRes = await locationsApi.list();
        const restricted = (locsRes.data || []).filter(l => l.is_restricted);
        setLocations(restricted);
        if (restricted.length > 0) setSelectedLocation(restricted[0].id);
      } catch (e) { console.warn(e.message || e); }
    } catch (err) { toast.error(err.response?.data?.detail || 'Login failed'); }
    finally { setLoading(false); }
  };

  const handleVisitorCheckin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await kioskApi.checkin({ member_name: visitorName, type: 'visitor', method: 'manual', phone: visitorPhone });
      toast.success(`Visitor "${visitorName}" checked in!`);
      // Save to recent visitors memory
      const vid = `visitor_${Date.now()}`;
      saveRecentVisitor({ id: vid, name: visitorName, phone: visitorPhone, type: 'visitor' });
      setRecentVisitors(getRecentVisitors());
      setTodayStats(prev => ({ ...prev, visitors: prev.visitors + 1, checkIns: prev.checkIns + 1 }));
      setVisitorName(''); setVisitorPhone('');
      setView(authenticated ? 'dashboard' : 'home');
    } catch { toast.error('Check-in failed'); }
  };

  const quickCheckinVisitor = async (visitor) => {
    try {
      await kioskApi.checkin({ member_name: visitor.name, type: visitor.type || 'visitor', method: 'quick', phone: visitor.phone });
      toast.success(`${visitor.name} checked in!`);
      saveRecentVisitor(visitor);
      setRecentVisitors(getRecentVisitors());
      setTodayStats(prev => ({ ...prev, visitors: prev.visitors + 1, checkIns: prev.checkIns + 1 }));
    } catch { toast.error('Check-in failed'); }
  };

  const handleGuestRegister = async () => {
    if (!guestForm.name.trim()) { toast.error('Name is required'); return; }
    setGuestLoading(true);
    try {
      const res = await authApi.visitorRegister(guestForm);
      const guest = res.data;
      setRegisteredGuest(guest);
      // Save to recent visitors
      saveRecentVisitor({ id: guest.user.id, name: guest.user.name, phone: guest.user.phone, type: guestForm.role });
      setRecentVisitors(getRecentVisitors());
      toast.success(`${guestForm.role === 'parent' ? 'Parent' : 'Visitor'} "${guestForm.name}" registered!`);
      // Also check them in
      await kioskApi.checkin({ member_name: guestForm.name, type: guestForm.role, method: 'guest_register', phone: guestForm.phone });
    } catch (err) { toast.error(err.response?.data?.detail || 'Registration failed'); }
    finally { setGuestLoading(false); }
  };

  const handleIdLookup = async (e) => {
    e.preventDefault();
    setLookupLoading(true);
    setFoundMember(null);
    try {
      const res = await kioskApi.lookup(lookupId);
      setFoundMember(res.data);
    } catch { toast.error('Member not found'); }
    finally { setLookupLoading(false); }
  };

  const handleMemberCheckin = async (member) => {
    setLoading(true);
    try {
      await kioskApi.checkin({ member_id: member.id, member_name: member.name, type: member.role === 'Staff' ? 'staff' : 'member', method: 'id' });
      toast.success(`${member.name} checked in!`);
      setTodayStats(prev => ({ ...prev, checkIns: prev.checkIns + 1 }));
      setFoundMember(null); setLookupId('');
      setView(authenticated ? 'dashboard' : 'home');
    } catch { toast.error('Check-in failed'); }
    finally { setLoading(false); }
  };

  const handleAccessScan = async () => {
    if (!scanMemberId || !selectedLocation) return;
    setLoading(true);
    setScanResult(null);
    try {
      let memberId = scanMemberId;

      // NFC mode: resolve serial number to member
      if (scanType === 'nfc') {
        const nfcRes = await nfcApi.scan({ serial_number: scanMemberId });
        memberId = nfcRes.data.member?.id;
        if (!memberId) throw new Error('NFC tag not linked to a member');
      }

      // Biometric mode: verify credential to get member
      if (scanType === 'biometric') {
        const bioRes = await biometricApi.verify({ credential_id: scanMemberId });
        memberId = bioRes.data.member?.id;
        if (!memberId) throw new Error('Biometric credential not recognized');
      }

      const res = await accessApi.scan({ member_id: memberId, location_id: selectedLocation, action: scanAction });
      setScanResult({ success: true, ...res.data });
      setTodayStats(prev => ({ ...prev, scans: prev.scans + 1 }));
      setRecentScans(prev => [{ id: Date.now(), member_id: memberId, action: scanAction, timestamp: new Date().toISOString(), ...res.data }, ...prev.slice(0, 9)]);
      toast.success(`${scanAction === 'in' ? 'Scanned IN' : 'Scanned OUT'}`);
      setScanMemberId('');
    } catch (err) { setScanResult({ success: false, detail: err.response?.data?.detail || err.message || 'No access' }); toast.error(err.response?.data?.detail || err.message || 'Access denied'); }
    finally { setLoading(false); }
  };

  const handleLogout = () => {
    setAuthenticated(false);
    setStaffUser(null);
    setToken('');
    delete api.defaults.headers.common['Authorization'];
    setView('home');
  };

  // ---- AUTHENTICATED DASHBOARD ----
  if (authenticated && view === 'dashboard') {
    return (
      <div className="min-h-screen bg-gradient-to-b from-background to-secondary/20 p-4 sm:p-6">
        <div className="max-w-3xl mx-auto">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <img src="https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1" alt="58:12 Global" className="h-10 w-auto" />
              <div>
                <p className="font-semibold">{staffUser?.name}</p>
                <p className="text-xs text-muted-foreground">{staffUser?.role} &middot; Kiosk {lockMode ? '(Locked)' : ''}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button variant={lockMode ? 'default' : 'outline'} size="sm" className="text-xs h-8" onClick={() => setLockMode(!lockMode)} data-testid="kiosk-lock-btn">{lockMode ? 'Unlock' : 'Lock'}</Button>
              <Badge variant={isOnline ? 'outline' : 'destructive'} className={`text-[10px] gap-1 ${isOnline ? 'border-green-300 text-green-600' : ''}`}>
                {isOnline ? <Wifi size={10} /> : <WifiOff size={10} />} {isOnline ? 'Online' : 'Offline'}
              </Badge>
              {!lockMode && <Button variant="ghost" size="sm" onClick={handleLogout} data-testid="kiosk-logout"><LogOut size={14} /></Button>}
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-3 mb-6">
            <Card className="shadow-soft rounded-xl"><CardContent className="p-4 text-center"><p className="text-xs text-muted-foreground">Check-ins</p><p className="text-3xl font-bold mt-1" data-testid="kiosk-checkins-count">{todayStats.checkIns}</p></CardContent></Card>
            <Card className="shadow-soft rounded-xl"><CardContent className="p-4 text-center"><p className="text-xs text-muted-foreground">Visitors</p><p className="text-3xl font-bold mt-1">{todayStats.visitors}</p></CardContent></Card>
            <Card className="shadow-soft rounded-xl"><CardContent className="p-4 text-center"><p className="text-xs text-muted-foreground">Access Scans</p><p className="text-3xl font-bold mt-1">{todayStats.scans}</p></CardContent></Card>
          </div>

          {/* Action Buttons */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mb-6">
            <Button className="h-20 text-lg gap-3 flex-col" onClick={() => setView('id')} data-testid="kiosk-id-checkin-btn">
              <CreditCard size={28} />
              <span className="text-xs">ID / QR Check-In</span>
            </Button>
            <Button variant="outline" className="h-20 text-lg gap-3 flex-col" onClick={() => setView('visitor')} data-testid="kiosk-visitor-btn">
              <UserCheck size={28} />
              <span className="text-xs">Visitor</span>
            </Button>
            <Button variant="outline" className="h-20 text-lg gap-3 flex-col border-primary/30 text-primary" onClick={() => setShowSignup(true)} data-testid="kiosk-signup-btn">
              <UserPlus size={28} />
              <span className="text-xs">Quick Signup</span>
            </Button>
            <Button variant="secondary" className="h-20 text-lg gap-3 flex-col" onClick={() => { setScanType('manual'); setView('scan'); }} data-testid="kiosk-scan-btn">
              <ScanLine size={28} />
              <span className="text-xs">Access Scan</span>
            </Button>
            <Button variant="outline" className="h-20 text-lg gap-3 flex-col" onClick={() => setShowGuestRegister(true)} data-testid="kiosk-guest-register-btn">
              <UserPlus size={28} />
              <span className="text-xs">Register Guest</span>
            </Button>
            <Button variant="outline" className="h-20 text-lg gap-3 flex-col text-amber-600 border-amber-200" onClick={() => setView('checkout')} data-testid="kiosk-checkout-btn">
              <LogOut size={28} />
              <span className="text-xs">Check Out</span>
            </Button>
          </div>

          {/* Quick Signup Dialog */}
          <Dialog open={showSignup} onOpenChange={setShowSignup}>
            <DialogContent className="max-w-sm">
              <DialogHeader><DialogTitle>Quick Signup</DialogTitle></DialogHeader>
              <div className="space-y-3 mt-2">
                <div className="space-y-1.5"><Label className="text-xs">Full Name *</Label><Input value={signupForm.name} onChange={e => setSignupForm({...signupForm, name: e.target.value})} data-testid="signup-name" /></div>
                <div className="space-y-1.5"><Label className="text-xs">Phone</Label><Input value={signupForm.phone} onChange={e => setSignupForm({...signupForm, phone: e.target.value})} /></div>
                <div className="space-y-1.5"><Label className="text-xs">Email (optional)</Label><Input value={signupForm.email} onChange={e => setSignupForm({...signupForm, email: e.target.value})} /></div>
                <div className="flex gap-3">
                  <Button variant="outline" className="flex-1" onClick={() => setShowSignup(false)}>Cancel</Button>
                  <Button className="flex-1" onClick={handleQuickSignup} data-testid="signup-submit-btn">Sign Up</Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>

          {/* Recent Visitors Quick Check-In */}
          {recentVisitors.length > 0 && (
            <Card className="shadow-soft rounded-xl mb-4">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <History size={14} /> Quick Check-In — Recent Visitors
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {recentVisitors.map(v => (
                    <div key={v.id} className="relative group">
                      <button
                        className="w-full p-2.5 rounded-lg border border-border hover:border-primary/50 hover:bg-primary/5 transition-colors text-left"
                        onClick={() => quickCheckinVisitor(v)}
                        data-testid={`quick-checkin-${v.id}`}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <div className="h-7 w-7 rounded-full bg-primary/10 flex items-center justify-center text-[10px] font-bold text-primary flex-shrink-0">
                            {v.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
                          </div>
                          <span className="text-xs font-medium truncate">{v.name}</span>
                        </div>
                        {v.phone && <p className="text-[10px] text-muted-foreground truncate">{v.phone}</p>}
                        <p className="text-[9px] text-muted-foreground capitalize">{v.type || 'visitor'}</p>
                      </button>
                      <button
                        className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive"
                        onClick={() => { removeRecentVisitor(v.id); setRecentVisitors(getRecentVisitors()); }}
                        title="Remove from list"
                      >
                        <X size={10} />
                      </button>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Recent scans */}
          {recentScans.length > 0 && (
            <Card className="shadow-soft rounded-xl">
              <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold flex items-center gap-2"><Clock size={14} /> Recent Scans</CardTitle></CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {recentScans.slice(0, 5).map(s => (
                    <div key={s.id} className="flex items-center justify-between text-sm p-2 rounded-lg bg-secondary/50">
                      <span>{s.member_name || s.member_id}</span>
                      <Badge variant={s.action === 'in' ? 'outline' : 'secondary'} className={s.action === 'in' ? 'border-green-400 text-green-600' : 'text-red-500'}>{s.action.toUpperCase()}</Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          <div className="mt-6 text-center">
            <Link to="/login" className="text-sm text-muted-foreground hover:text-primary">Exit to main login</Link>
          </div>
        </div>

        {/* Guest Registration Dialog */}
        <Dialog open={showGuestRegister} onOpenChange={o => { setShowGuestRegister(o); if (!o) { setRegisteredGuest(null); setGuestForm({ name: '', phone: '', role: 'visitor', notes: '' }); } }}>
          <DialogContent className="max-w-sm">
            <DialogHeader>
              <DialogTitle>{registeredGuest ? 'Guest Registered!' : 'Register Guest/Visitor'}</DialogTitle>
            </DialogHeader>
            {registeredGuest ? (
              <div className="space-y-4 text-center">
                <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center mx-auto">
                  <UserCheck size={28} className="text-green-600" />
                </div>
                <p className="font-semibold text-lg">{registeredGuest.user?.name}</p>
                <p className="text-sm text-muted-foreground capitalize">{registeredGuest.user?.role}</p>
                {registeredGuest.pin && (
                  <div className="bg-muted rounded-lg p-3">
                    <p className="text-xs text-muted-foreground mb-1">Access PIN (save this)</p>
                    <p className="text-2xl font-mono font-bold tracking-widest">{registeredGuest.pin}</p>
                  </div>
                )}
                <p className="text-xs text-muted-foreground">Guest checked in and added to quick check-in list</p>
                <Button className="w-full" onClick={() => { setShowGuestRegister(false); setRegisteredGuest(null); setGuestForm({ name: '', phone: '', role: 'visitor', notes: '' }); }}>Done</Button>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label className="text-xs">Guest Type</Label>
                  <div className="flex gap-2">
                    {[['visitor', 'Visitor'], ['parent', 'Parent/Guardian']].map(([v, l]) => (
                      <button key={v} onClick={() => setGuestForm({ ...guestForm, role: v })}
                        className={`flex-1 py-2 rounded-lg border text-xs font-medium transition-colors ${guestForm.role === v ? 'border-primary bg-primary/10 text-primary' : 'border-border text-muted-foreground hover:border-primary/50'}`}>
                        {l}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Full Name *</Label>
                  <Input placeholder="Enter full name" value={guestForm.name} onChange={e => setGuestForm({ ...guestForm, name: e.target.value })} data-testid="guest-name-input" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Phone Number</Label>
                  <Input placeholder="+256..." value={guestForm.phone} onChange={e => setGuestForm({ ...guestForm, phone: e.target.value })} data-testid="guest-phone-input" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Notes (optional)</Label>
                  <Input placeholder="e.g. Parent of John Doe" value={guestForm.notes} onChange={e => setGuestForm({ ...guestForm, notes: e.target.value })} />
                </div>
                <div className="flex gap-3">
                  <Button variant="outline" className="flex-1" onClick={() => setShowGuestRegister(false)}>Cancel</Button>
                  <Button className="flex-1 gap-2" onClick={handleGuestRegister} disabled={guestLoading || !guestForm.name.trim()} data-testid="confirm-guest-register">
                    <UserPlus size={14} /> {guestLoading ? 'Registering...' : 'Register & Check In'}
                  </Button>
                </div>
              </div>
            )}
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  // ---- ACCESS SCAN VIEW ----
  if (view === 'scan' && authenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-background to-secondary/30 p-4">
        <Card className="w-full max-w-md shadow rounded-xl">
          <CardHeader className="text-center space-y-3">
            <div className="mx-auto w-20 h-20 rounded-full bg-primary flex items-center justify-center">
              {scanType === 'nfc' ? <Smartphone size={36} className="text-primary-foreground" /> : scanType === 'biometric' ? <Fingerprint size={36} className="text-primary-foreground" /> : <ScanLine size={36} className="text-primary-foreground" />}
            </div>
            <CardTitle className="text-2xl font-heading">{scanType === 'nfc' ? 'NFC Scan' : scanType === 'biometric' ? 'Biometric Scan' : 'Access Scan'}</CardTitle>
            <CardDescription>{scanType === 'nfc' ? 'Place NFC tag on device to scan' : scanType === 'biometric' ? 'Use fingerprint sensor to verify' : 'Scan residents/staff in or out of restricted areas'}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Scan type picker */}
            <div className="flex gap-2">
              <Button size="sm" variant={scanType === 'manual' ? 'default' : 'outline'} className="flex-1 gap-1.5" onClick={() => setScanType('manual')} data-testid="kiosk-scan-type-manual">
                <ScanLine size={14} /> Manual
              </Button>
              <Button size="sm" variant={scanType === 'nfc' ? 'default' : 'outline'} className="flex-1 gap-1.5" onClick={() => setScanType('nfc')} data-testid="kiosk-scan-type-nfc">
                <Smartphone size={14} /> NFC
              </Button>
              <Button size="sm" variant={scanType === 'biometric' ? 'default' : 'outline'} className="flex-1 gap-1.5" onClick={() => setScanType('biometric')} data-testid="kiosk-scan-type-biometric">
                <Fingerprint size={14} /> Biometric
              </Button>
            </div>

            <div className="space-y-2">
              <Label className="text-base">Location</Label>
              <Select value={selectedLocation} onValueChange={setSelectedLocation}>
                <SelectTrigger className="h-12 text-base" data-testid="kiosk-scan-location"><SelectValue /></SelectTrigger>
                <SelectContent>{locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>

            {scanType === 'nfc' ? (
              <div className="space-y-3">
                <div className="p-8 rounded-xl border-2 border-dashed border-primary/30 bg-primary/5 text-center">
                  <Smartphone size={48} className="mx-auto mb-2 text-primary opacity-50 animate-pulse" />
                  <p className="text-sm font-medium">Place NFC tag on device</p>
                  <p className="text-xs text-muted-foreground mt-1">Or enter serial number below</p>
                </div>
                <Input className="h-12 text-lg" placeholder="NFC Serial (e.g. 04:A2:B3:C4:D5)" value={scanMemberId} onChange={e => setScanMemberId(e.target.value)} data-testid="kiosk-nfc-input" />
              </div>
            ) : scanType === 'biometric' ? (
              <div className="space-y-3">
                <div className="p-8 rounded-xl border-2 border-dashed border-primary/30 bg-primary/5 text-center">
                  <Fingerprint size={48} className="mx-auto mb-2 text-primary opacity-50 animate-pulse" />
                  <p className="text-sm font-medium">Touch the fingerprint sensor</p>
                  <p className="text-xs text-muted-foreground mt-1">Or enter credential ID below</p>
                </div>
                <Input className="h-12 text-lg" placeholder="Credential ID" value={scanMemberId} onChange={e => setScanMemberId(e.target.value)} data-testid="kiosk-biometric-input" />
              </div>
            ) : (
              <div className="space-y-2">
                <Label className="text-base">Member ID / National ID</Label>
                <Input className="h-12 text-lg" placeholder="Enter ID..." value={scanMemberId} onChange={e => setScanMemberId(e.target.value)} data-testid="kiosk-scan-member-input" />
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <Button className={`h-14 text-lg ${scanAction === 'in' ? 'bg-green-600 hover:bg-green-700' : 'bg-secondary text-foreground'}`} onClick={() => setScanAction('in')} data-testid="kiosk-scan-in-toggle">
                SCAN IN
              </Button>
              <Button className={`h-14 text-lg ${scanAction === 'out' ? 'bg-red-600 hover:bg-red-700 text-white' : 'bg-secondary text-foreground'}`} onClick={() => setScanAction('out')} data-testid="kiosk-scan-out-toggle">
                SCAN OUT
              </Button>
            </div>
            <Button className="w-full h-14 text-lg" disabled={loading || !scanMemberId} onClick={handleAccessScan} data-testid="kiosk-execute-scan-btn">
              {loading ? 'Processing...' : `Confirm ${scanAction.toUpperCase()}`}
            </Button>
            {scanResult && (
              <div className={`p-4 rounded-xl text-center font-semibold ${scanResult.success ? 'bg-green-50 text-green-700 border-2 border-green-300' : 'bg-red-50 text-red-700 border-2 border-red-300'}`} data-testid="scan-result-msg">
                {scanResult.success ? `Access granted (${scanResult.access_type || scanAction})` : scanResult.detail}
              </div>
            )}
            <Button variant="ghost" className="w-full" onClick={() => setView('dashboard')}>Back to Dashboard</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ---- VISITOR VIEW ----
  if (view === 'visitor') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-background to-secondary/30 p-4">
        <Card className="w-full max-w-md shadow rounded-xl">
          <CardHeader className="text-center space-y-3">
            <div className="mx-auto w-20 h-20 rounded-full bg-primary flex items-center justify-center"><span className="text-primary-foreground font-bold text-xl">58:12</span></div>
            <CardTitle className="text-2xl font-heading">Visitor Check-In</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleVisitorCheckin} className="space-y-4">
              <div className="space-y-2"><Label className="text-base">Full Name *</Label><Input className="h-12 text-lg" placeholder="Your full name" value={visitorName} onChange={e => setVisitorName(e.target.value)} required data-testid="kiosk-visitor-name" /></div>
              <div className="space-y-2"><Label className="text-base">Phone</Label><Input className="h-12 text-lg" placeholder="+256 700 000000" value={visitorPhone} onChange={e => setVisitorPhone(e.target.value)} data-testid="kiosk-visitor-phone" /></div>
              <Button type="submit" className="w-full h-14 text-lg" disabled={loading}>{loading ? 'Checking in...' : 'Check In'}</Button>
              <Button type="button" variant="ghost" className="w-full" onClick={() => setView(authenticated ? 'dashboard' : 'home')}>Back</Button>
            </form>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ---- ID LOOKUP VIEW ----
  if (view === 'id') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-background to-secondary/30 p-4">
        <Card className="w-full max-w-md shadow rounded-xl">
          <CardHeader className="text-center space-y-3">
            <div className="mx-auto w-20 h-20 rounded-full bg-primary flex items-center justify-center"><CreditCard size={36} className="text-primary-foreground" /></div>
            <CardTitle className="text-2xl font-heading">ID Check-In</CardTitle>
            <CardDescription>Enter National ID, phone, or email</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form onSubmit={handleIdLookup} className="space-y-3">
              <Input className="h-12 text-lg" placeholder="ID, phone, or email" value={lookupId} onChange={e => setLookupId(e.target.value)} required data-testid="kiosk-id-input" />
              <Button type="submit" className="w-full h-12 gap-2" disabled={lookupLoading}><Search size={18} /> {lookupLoading ? 'Looking...' : 'Find'}</Button>
            </form>
            {foundMember && (
              <div className="p-4 rounded-xl border-2 border-primary bg-primary/5">
                <p className="font-semibold text-lg">{foundMember.name}</p>
                <p className="text-sm text-muted-foreground">{foundMember.role} &middot; {foundMember.group}</p>
                <Button className="w-full mt-3 h-12 text-base gap-2" onClick={() => handleMemberCheckin(foundMember)} disabled={loading}>
                  <UserCheck size={18} /> {loading ? 'Checking in...' : 'Confirm Check-In'}
                </Button>
              </div>
            )}
            <Button variant="ghost" className="w-full" onClick={() => { setView(authenticated ? 'dashboard' : 'home'); setFoundMember(null); setLookupId(''); }}>Back</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ---- HOME / LOGIN ----
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-background to-secondary/30 p-4">
      <Card className="w-full max-w-md shadow rounded-xl">
        <CardHeader className="text-center space-y-4">
          <div className="mx-auto w-24 h-24 rounded-full bg-primary flex items-center justify-center">
            <span className="text-primary-foreground font-bold text-2xl font-heading">58:12</span>
          </div>
          <div>
            <CardTitle className="text-3xl font-heading">Field Kiosk</CardTitle>
            <CardDescription className="text-lg mt-2">Mobile check-in & access scanning</CardDescription>
          </div>
          <Badge variant={isOnline ? 'outline' : 'destructive'} className={`text-xs gap-1 ${isOnline ? 'border-green-300 text-green-600' : ''}`}>
            {isOnline ? <Wifi size={12} /> : <WifiOff size={12} />} {isOnline ? 'Online' : 'Offline'}
          </Badge>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Quick actions (no auth required) */}
          <div className="rounded-2xl border border-primary/20 bg-primary/5 p-4 space-y-3">
            <p className="text-sm font-medium">Quick Check-In</p>
            <div className="grid grid-cols-2 gap-3">
              <Button variant="outline" className="h-16 gap-3 flex-col" onClick={() => setView('id')} data-testid="kiosk-quick-id-btn">
                <CreditCard size={22} />
                <span className="text-xs font-medium">ID Check-In</span>
              </Button>
              <Button className="h-16 gap-3 flex-col" onClick={() => setView('visitor')} data-testid="kiosk-quick-visitor-btn">
                <UserCheck size={22} />
                <span className="text-xs font-medium">Visitor</span>
              </Button>
            </div>
          </div>

          <div className="relative my-2"><div className="absolute inset-0 flex items-center"><span className="w-full border-t" /></div><div className="relative flex justify-center text-xs uppercase"><span className="bg-card px-2 text-muted-foreground">Staff sign-in for full access</span></div></div>

          <form onSubmit={handleStaffLogin} className="space-y-4">
            <div className="space-y-2"><Label className="text-base">Email</Label><Input className="h-12 text-lg" type="email" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} required data-testid="kiosk-email" /></div>
            <div className="space-y-2"><Label className="text-base">Password</Label>
              <div className="relative">
                <Input className="h-12 text-lg pr-12" type={showPassword ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} required data-testid="kiosk-password" />
                <button type="button" className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground" onClick={() => setShowPassword(!showPassword)}>{showPassword ? <EyeOff size={20} /> : <Eye size={20} />}</button>
              </div>
            </div>
            <Button type="submit" className="w-full h-14 text-lg" disabled={loading} data-testid="kiosk-login-btn">{loading ? 'Signing in...' : 'Sign In'}</Button>
          </form>
          <div className="text-center"><Link to="/login" className="text-sm text-muted-foreground hover:text-primary">Back to main login</Link></div>
        </CardContent>
      </Card>
    </div>
  );
}
