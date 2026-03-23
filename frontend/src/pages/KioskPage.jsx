import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { CreditCard, UserCheck, Eye, EyeOff, Search } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { kioskApi } from '../services/api';
import { toast } from 'sonner';

export default function KioskPage() {
  const [deviceId, setDeviceId] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState('home');
  const [visitorName, setVisitorName] = useState('');
  const [visitorPhone, setVisitorPhone] = useState('');
  const [lookupId, setLookupId] = useState('');
  const [foundMember, setFoundMember] = useState(null);
  const [lookupLoading, setLookupLoading] = useState(false);

  const handleStaffLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      toast.success('Signed in to Kiosk mode');
    }, 1000);
  };

  const handleVisitorCheckin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await kioskApi.checkin({ member_name: visitorName, type: 'visitor', method: 'manual' });
      toast.success(`Visitor "${visitorName}" checked in!`);
      setVisitorName('');
      setVisitorPhone('');
      setView('home');
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
    } catch {
      toast.error('Member not found. Proceed as visitor or check details.');
    } finally { setLookupLoading(false); }
  };

  const handleMemberCheckin = async (member) => {
    setLoading(true);
    try {
      await kioskApi.checkin({ member_id: member.id, member_name: member.name, type: member.role === 'Staff' ? 'staff' : 'member', method: 'id' });
      toast.success(`${member.name} checked in successfully!`);
      setView('home');
      setFoundMember(null);
      setLookupId('');
    } catch { toast.error('Check-in failed'); }
    finally { setLoading(false); }
  };

  if (view === 'visitor') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-background to-secondary/30 p-4">
        <Card className="w-full max-w-md shadow rounded-xl">
          <CardHeader className="text-center space-y-3">
            <div className="mx-auto w-20 h-20 rounded-full bg-primary flex items-center justify-center">
              <span className="text-primary-foreground font-bold text-xl">58:12</span>
            </div>
            <CardTitle className="text-2xl font-heading">Visitor Check-In</CardTitle>
            <CardDescription>Please enter your details to check in</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleVisitorCheckin} className="space-y-4">
              <div className="space-y-2">
                <Label className="text-base">Full Name *</Label>
                <Input className="h-12 text-lg" placeholder="Your full name" value={visitorName} onChange={e => setVisitorName(e.target.value)} required />
              </div>
              <div className="space-y-2">
                <Label className="text-base">Phone Number</Label>
                <Input className="h-12 text-lg" placeholder="+256 700 000000" value={visitorPhone} onChange={e => setVisitorPhone(e.target.value)} />
              </div>
              <Button type="submit" className="w-full h-14 text-lg" disabled={loading}>{loading ? 'Checking in...' : 'Check In as Visitor'}</Button>
              <Button type="button" variant="ghost" className="w-full" onClick={() => setView('home')}>← Back</Button>
            </form>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (view === 'id') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-background to-secondary/30 p-4">
        <Card className="w-full max-w-md shadow rounded-xl">
          <CardHeader className="text-center space-y-3">
            <div className="mx-auto w-20 h-20 rounded-full bg-primary flex items-center justify-center">
              <span className="text-primary-foreground font-bold text-xl">58:12</span>
            </div>
            <CardTitle className="text-2xl font-heading">ID / QR Check-In</CardTitle>
            <CardDescription>Enter your National ID, phone, or email</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form onSubmit={handleIdLookup} className="space-y-3">
              <div className="space-y-2">
                <Label className="text-base">National ID, Phone, or Email</Label>
                <Input className="h-12 text-lg" placeholder="e.g. CM900001000XXXX" value={lookupId} onChange={e => setLookupId(e.target.value)} required />
              </div>
              <Button type="submit" className="w-full h-12 gap-2" disabled={lookupLoading}>
                <Search size={18} />{lookupLoading ? 'Looking up...' : 'Find Member'}
              </Button>
            </form>

            {foundMember && (
              <div className="p-4 rounded-lg border-2 border-primary bg-primary/5">
                <p className="font-semibold text-lg">{foundMember.name}</p>
                <p className="text-sm text-muted-foreground">{foundMember.role} · {foundMember.group}</p>
                <p className="text-sm text-muted-foreground">{foundMember.phone}</p>
                <Button className="w-full mt-3 h-12 text-base gap-2" onClick={() => handleMemberCheckin(foundMember)} disabled={loading}>
                  <UserCheck size={18} />{loading ? 'Checking in...' : 'Confirm Check-In'}
                </Button>
              </div>
            )}

            <Button type="button" variant="ghost" className="w-full" onClick={() => { setView('home'); setFoundMember(null); setLookupId(''); }}>← Back</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-background to-secondary/30 p-4">
      <Card className="w-full max-w-md shadow rounded-xl">
        <CardHeader className="text-center space-y-4">
          <div className="mx-auto w-24 h-24 rounded-full bg-primary flex items-center justify-center">
            <span className="text-primary-foreground font-bold text-2xl font-heading">58:12</span>
          </div>
          <div>
            <CardTitle className="text-3xl font-heading">Guest Check-In</CardTitle>
            <CardDescription className="text-lg mt-2">Check in families, children, staff, and visitors</CardDescription>
          </div>
        </CardHeader>

        <CardContent className="space-y-5">
          {/* Device ID */}
          <div className="p-3 rounded-lg border border-dashed border-primary/30 bg-primary/5">
            <Label className="text-sm font-medium">Kiosk Device ID (optional)</Label>
            <div className="mt-2 flex gap-2">
              <Input placeholder="kiosk_abc12345" value={deviceId} onChange={e => setDeviceId(e.target.value)} className="text-sm" />
              <Button variant="outline" type="button" onClick={() => toast.success('Device linked!')}>Link</Button>
            </div>
            <p className="text-xs text-muted-foreground mt-2">Unlinked devices can still login, but venue will not be statically locked.</p>
          </div>

          {/* Quick actions */}
          <div className="rounded-2xl border border-primary/20 bg-primary/5 p-4 space-y-3">
            <div>
              <p className="text-sm font-medium">Fastest front-desk check-in</p>
              <p className="text-xs text-muted-foreground">Scan or enter your government ID, or use visitor check-in.</p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Button variant="outline" className="h-16 gap-3 justify-start px-4 text-left" onClick={() => setView('id')}>
                <CreditCard size={20} className="shrink-0" />
                <span>
                  <span className="block font-medium text-sm">ID / QR Check-In</span>
                  <span className="block text-xs text-muted-foreground">National ID or badge QR code</span>
                </span>
              </Button>
              <Button className="h-16 gap-3 justify-start px-4 text-left" onClick={() => setView('visitor')}>
                <UserCheck size={20} className="shrink-0" />
                <span>
                  <span className="block font-medium text-sm">Visitor Check-In</span>
                  <span className="block text-xs text-primary-foreground/80">Anyone can be checked in as a visitor.</span>
                </span>
              </Button>
            </div>
          </div>

          {/* Divider */}
          <div className="relative my-2">
            <div className="absolute inset-0 flex items-center"><span className="w-full border-t" /></div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-card px-2 text-muted-foreground">Staff / manager sign-in</span>
            </div>
          </div>

          {/* Staff login */}
          <form onSubmit={handleStaffLogin} className="space-y-4">
            <div className="space-y-2">
              <Label className="text-base">Email</Label>
              <Input className="h-12 text-lg" type="email" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label className="text-base">Password</Label>
              <div className="relative">
                <Input className="h-12 text-lg pr-12" type={showPassword ? 'text' : 'password'} placeholder="--------" value={password} onChange={e => setPassword(e.target.value)} required />
                <button type="button" className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground" onClick={() => setShowPassword(!showPassword)}>
                  {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                </button>
              </div>
            </div>
            <Button type="submit" className="w-full h-14 text-lg" disabled={loading}>{loading ? 'Signing in...' : 'Sign In to Kiosk'}</Button>
          </form>

          <div className="mt-6 pt-4 border-t border-border text-center">
            <Link to="/login" className="text-sm text-muted-foreground hover:text-primary">← Back to main login</Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
