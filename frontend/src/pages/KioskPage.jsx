import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { CreditCard, UserCheck, Eye, EyeOff, Search, ScanLine, LogOut, Wifi, WifiOff, Users, Clock, MapPin } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { kioskApi, locationsApi, accessApi } from '../services/api';
import api from '../services/api';
import { toast } from 'sonner';

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

  // Access scan mode
  const [locations, setLocations] = useState([]);
  const [selectedLocation, setSelectedLocation] = useState('');
  const [scanAction, setScanAction] = useState('in');
  const [scanMemberId, setScanMemberId] = useState('');
  const [scanResult, setScanResult] = useState(null);
  const [recentScans, setRecentScans] = useState([]);
  const [todayStats, setTodayStats] = useState({ checkIns: 0, visitors: 0, scans: 0 });
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  useEffect(() => {
    const goOnline = () => setIsOnline(true);
    const goOffline = () => { setIsOnline(false); toast.warning('Offline — check-ins will be queued'); };
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
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
      toast.success(`Welcome, ${meRes.data.name}`);
      // Load locations for access scanning
      try {
        const locsRes = await locationsApi.list();
        const restricted = (locsRes.data || []).filter(l => l.is_restricted);
        setLocations(restricted);
        if (restricted.length > 0) setSelectedLocation(restricted[0].id);
      } catch {}
    } catch (err) { toast.error(err.response?.data?.detail || 'Login failed'); }
    finally { setLoading(false); }
  };

  const handleVisitorCheckin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await kioskApi.checkin({ member_name: visitorName, type: 'visitor', method: 'manual', phone: visitorPhone });
      toast.success(`Visitor "${visitorName}" checked in!`);
      setTodayStats(prev => ({ ...prev, visitors: prev.visitors + 1, checkIns: prev.checkIns + 1 }));
      setVisitorName(''); setVisitorPhone('');
      setView(authenticated ? 'dashboard' : 'home');
    } catch { toast.error('Check-in failed'); }
    finally { setLoading(false); }
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
      const res = await accessApi.scan({ member_id: scanMemberId, location_id: selectedLocation, action: scanAction });
      setScanResult({ success: true, ...res.data });
      setTodayStats(prev => ({ ...prev, scans: prev.scans + 1 }));
      setRecentScans(prev => [{ id: Date.now(), member_id: scanMemberId, action: scanAction, timestamp: new Date().toISOString(), ...res.data }, ...prev.slice(0, 9)]);
      toast.success(`${scanAction === 'in' ? 'Scanned IN' : 'Scanned OUT'}`);
      setScanMemberId('');
    } catch (err) { setScanResult({ success: false, detail: err.response?.data?.detail || 'No access' }); toast.error(err.response?.data?.detail || 'Access denied'); }
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
              <div className="w-12 h-12 rounded-full bg-primary flex items-center justify-center">
                <span className="text-primary-foreground font-bold text-sm">58:12</span>
              </div>
              <div>
                <p className="font-semibold">{staffUser?.name}</p>
                <p className="text-xs text-muted-foreground">{staffUser?.role} &middot; Kiosk Mode</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={isOnline ? 'outline' : 'destructive'} className={`text-[10px] gap-1 ${isOnline ? 'border-green-300 text-green-600' : ''}`}>
                {isOnline ? <Wifi size={10} /> : <WifiOff size={10} />} {isOnline ? 'Online' : 'Offline'}
              </Badge>
              <Button variant="ghost" size="sm" onClick={handleLogout} data-testid="kiosk-logout"><LogOut size={14} /></Button>
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-3 mb-6">
            <Card className="shadow-soft rounded-xl"><CardContent className="p-4 text-center"><p className="text-xs text-muted-foreground">Check-ins</p><p className="text-3xl font-bold mt-1" data-testid="kiosk-checkins-count">{todayStats.checkIns}</p></CardContent></Card>
            <Card className="shadow-soft rounded-xl"><CardContent className="p-4 text-center"><p className="text-xs text-muted-foreground">Visitors</p><p className="text-3xl font-bold mt-1">{todayStats.visitors}</p></CardContent></Card>
            <Card className="shadow-soft rounded-xl"><CardContent className="p-4 text-center"><p className="text-xs text-muted-foreground">Access Scans</p><p className="text-3xl font-bold mt-1">{todayStats.scans}</p></CardContent></Card>
          </div>

          {/* Action Buttons */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
            <Button className="h-20 text-lg gap-3 flex-col" onClick={() => setView('id')} data-testid="kiosk-id-checkin-btn">
              <CreditCard size={28} />
              <span>ID Check-In</span>
            </Button>
            <Button variant="outline" className="h-20 text-lg gap-3 flex-col" onClick={() => setView('visitor')} data-testid="kiosk-visitor-btn">
              <UserCheck size={28} />
              <span>Visitor</span>
            </Button>
            <Button variant="secondary" className="h-20 text-lg gap-3 flex-col" onClick={() => setView('scan')} data-testid="kiosk-scan-btn">
              <ScanLine size={28} />
              <span>Access Scan</span>
            </Button>
          </div>

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
              <ScanLine size={36} className="text-primary-foreground" />
            </div>
            <CardTitle className="text-2xl font-heading">Access Scan</CardTitle>
            <CardDescription>Scan residents/staff in or out of restricted areas</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label className="text-base">Location</Label>
              <Select value={selectedLocation} onValueChange={setSelectedLocation}>
                <SelectTrigger className="h-12 text-base" data-testid="kiosk-scan-location"><SelectValue /></SelectTrigger>
                <SelectContent>{locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-base">Member ID / National ID</Label>
              <Input className="h-12 text-lg" placeholder="Enter ID..." value={scanMemberId} onChange={e => setScanMemberId(e.target.value)} data-testid="kiosk-scan-member-input" />
            </div>
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
