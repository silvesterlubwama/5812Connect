import React, { useState, useEffect } from 'react';
import { User, Phone, Mail, MapPin, AlertTriangle, Save } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { portalApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

export default function PortalProfile() {
  const { user } = useAuth();
  const [profile, setProfile] = useState(null);
  const [member, setMember] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: '', phone: '', address: '', emergency_contact: '', notes: '' });
  const [checkins, setCheckins] = useState({ checkins: [], access_logs: [] });

  useEffect(() => {
    const load = async () => {
      try {
        const [profileRes, checkinsRes] = await Promise.all([
          portalApi.profile(),
          portalApi.checkins(),
        ]);
        setProfile(profileRes.data.user);
        setMember(profileRes.data.member);
        setCheckins(checkinsRes.data);
        const u = profileRes.data.user;
        const m = profileRes.data.member;
        setForm({
          name: m?.name || u?.name || '',
          phone: m?.phone || u?.phone || '',
          address: m?.address || '',
          emergency_contact: m?.emergency_contact || '',
          notes: m?.notes || '',
        });
      } catch { toast.error('Failed to load profile'); }
      finally { setLoading(false); }
    };
    load();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await portalApi.updateProfile(form);
      toast.success('Profile updated');
      setEditing(false);
    } catch (err) { toast.error(err.response?.data?.detail || 'Update failed'); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" /></div>;

  return (
    <div className="space-y-6 max-w-3xl" data-testid="portal-profile">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold font-heading">My Profile</h1>
          <p className="text-sm text-muted-foreground mt-1">Manage your personal information</p>
        </div>
        <Button variant={editing ? 'default' : 'outline'} className="gap-1.5" onClick={() => editing ? handleSave() : setEditing(true)} disabled={saving} data-testid="portal-edit-profile-btn">
          {editing ? <><Save size={14} /> {saving ? 'Saving...' : 'Save'}</> : 'Edit Profile'}
        </Button>
      </div>

      {/* Profile Card */}
      <Card className="shadow-soft rounded-xl">
        <CardHeader>
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-lg">
              {(profile?.name || '?').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase()}
            </div>
            <div>
              <CardTitle className="text-lg">{profile?.name}</CardTitle>
              <div className="flex gap-2 mt-1">
                <Badge variant="outline" className="text-xs">{profile?.role}</Badge>
                <Badge className={`text-xs ${profile?.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>{profile?.status}</Badge>
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="flex items-center gap-1.5"><User size={12} /> Name</Label>
              {editing ? (
                <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} data-testid="profile-name-input" />
              ) : (
                <p className="text-sm">{profile?.name || '—'}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label className="flex items-center gap-1.5"><Mail size={12} /> Email</Label>
              <p className="text-sm">{profile?.email || '—'}</p>
            </div>
            <div className="space-y-2">
              <Label className="flex items-center gap-1.5"><Phone size={12} /> Phone</Label>
              {editing ? (
                <Input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} data-testid="profile-phone-input" />
              ) : (
                <p className="text-sm">{profile?.phone || member?.phone || '—'}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label className="flex items-center gap-1.5"><MapPin size={12} /> Address</Label>
              {editing ? (
                <Input value={form.address} onChange={e => setForm({ ...form, address: e.target.value })} data-testid="profile-address-input" />
              ) : (
                <p className="text-sm">{member?.address || '—'}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label className="flex items-center gap-1.5"><AlertTriangle size={12} /> Emergency Contact</Label>
              {editing ? (
                <Input value={form.emergency_contact} onChange={e => setForm({ ...form, emergency_contact: e.target.value })} data-testid="profile-emergency-input" />
              ) : (
                <p className="text-sm">{member?.emergency_contact || '—'}</p>
              )}
            </div>
          </div>
          {member && (
            <div className="mt-4 pt-4 border-t border-border">
              <p className="text-xs text-muted-foreground mb-2">Member Details</p>
              <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                {member.group && <span>Group: <strong>{member.group}</strong></span>}
                {member.department && <span>Dept: <strong>{member.department}</strong></span>}
                {member.join_date && <span>Joined: <strong>{member.join_date}</strong></span>}
              </div>
              {(member.badges || []).length > 0 && (
                <div className="flex gap-1.5 mt-2">
                  {member.badges.map((b, i) => (
                    <Badge key={i} style={{ backgroundColor: b.badge_color + '20', color: b.badge_color }} className="text-xs">{b.badge_name}</Badge>
                  ))}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Check-in History */}
      <Card className="shadow-soft rounded-xl">
        <CardHeader>
          <CardTitle className="text-sm">Check-in History</CardTitle>
          <CardDescription className="text-xs">Your recent access and attendance records</CardDescription>
        </CardHeader>
        <CardContent>
          {(checkins.checkins || []).length === 0 && (checkins.access_logs || []).length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">No check-in records yet</p>
          ) : (
            <div className="divide-y">
              {(checkins.checkins || []).slice(0, 10).map((c, i) => (
                <div key={i} className="flex items-center justify-between py-2.5">
                  <div>
                    <p className="text-sm">{c.event_name || c.type || 'Check-in'}</p>
                    <p className="text-xs text-muted-foreground">{c.method || 'manual'}</p>
                  </div>
                  <span className="text-xs text-muted-foreground">{new Date(c.check_in_time || c.timestamp).toLocaleString()}</span>
                </div>
              ))}
              {(checkins.access_logs || []).slice(0, 10).map((a, i) => (
                <div key={`a${i}`} className="flex items-center justify-between py-2.5">
                  <div>
                    <p className="text-sm">Access — {a.action || 'scan'}</p>
                    <p className="text-xs text-muted-foreground">{a.access_type || 'access'}</p>
                  </div>
                  <span className="text-xs text-muted-foreground">{new Date(a.timestamp).toLocaleString()}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
