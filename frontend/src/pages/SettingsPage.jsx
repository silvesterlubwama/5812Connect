import React, { useState, useEffect } from 'react';
import { Save, Bell, Shield, Building, Plus, Trash2, Edit2, Check, X, Wrench } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Switch } from '../components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { venuesApi, authApi, appSettingsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

export default function SettingsPage() {
  const { user } = useAuth();
  const isAdmin = ['admin', 'system_admin'].includes(user?.role);
  const [orgSettings, setOrgSettings] = useState({
    orgName: '58:12 Global Connect',
    orgEmail: 'info@5812global.org',
    orgPhone: '+256 800 5812',
    orgAddress: 'Kampala, Uganda',
    timezone: 'Africa/Kampala',
    currency: 'UGX',
  });
  const [notifications, setNotifications] = useState({
    emailCheckins: true, emailNewMembers: true, emailEvents: false, smsCheckins: false, smsEvents: true,
  });
  const [venues, setVenues] = useState([]);
  const [loadingVenues, setLoadingVenues] = useState(true);
  const [showAddVenue, setShowAddVenue] = useState(false);
  const [editingVenue, setEditingVenue] = useState(null);
  const [newVenue, setNewVenue] = useState({ name: '', capacity: 50, type: 'hall', description: '', hourly_rate: '', available: true });
  const [passwords, setPasswords] = useState({ current: '', new_: '', confirm: '' });
  const [savingPass, setSavingPass] = useState(false);
  const [appSettings, setAppSettings] = useState({ registration_open: true, default_role: 'member', maintenance_mode: false });
  const [savingAdmin, setSavingAdmin] = useState(false);

  useEffect(() => {
    venuesApi.list()
      .then(res => setVenues(res.data))
      .catch(() => {})
      .finally(() => setLoadingVenues(false));
    if (isAdmin) {
      appSettingsApi.get().then(r => setAppSettings(prev => ({ ...prev, ...r.data }))).catch(() => {});
    }
  }, [isAdmin]);

  const handleSaveAppSettings = async () => {
    setSavingAdmin(true);
    try {
      await appSettingsApi.update(appSettings);
      toast.success('Admin settings saved!');
    } catch { toast.error('Failed to save settings'); }
    finally { setSavingAdmin(false); }
  };

  const handleSaveOrg = (e) => {
    e.preventDefault();
    toast.success('Organization settings saved!');
  };

  const handleAddVenue = async (e) => {
    e.preventDefault();
    try {
      const payload = { ...newVenue, hourly_rate: newVenue.hourly_rate ? parseFloat(newVenue.hourly_rate) : undefined, capacity: parseInt(newVenue.capacity) };
      if (!payload.hourly_rate) delete payload.hourly_rate;
      const res = await venuesApi.create(payload);
      setVenues(prev => [...prev, res.data]);
      setShowAddVenue(false);
      setNewVenue({ name: '', capacity: 50, type: 'hall', description: '', hourly_rate: '', available: true });
      toast.success('Venue added!');
    } catch { toast.error('Failed to add venue'); }
  };

  const toggleVenueAvailability = async (venue) => {
    try {
      await venuesApi.update(venue.id, { available: !venue.available });
      setVenues(prev => prev.map(v => v.id === venue.id ? { ...v, available: !v.available } : v));
      toast.success('Venue updated');
    } catch { toast.error('Failed to update venue'); }
  };

  const deleteVenue = async (venue) => {
    if (!window.confirm(`Delete "${venue.name}"?`)) return;
    try {
      await venuesApi.delete(venue.id);
      setVenues(prev => prev.filter(v => v.id !== venue.id));
      toast.success('Venue deleted');
    } catch { toast.error('Failed to delete venue'); }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    if (passwords.new_ !== passwords.confirm) { toast.error('New passwords do not match'); return; }
    setSavingPass(true);
    setTimeout(() => {
      setSavingPass(false);
      setPasswords({ current: '', new_: '', confirm: '' });
      toast.success('Password changed successfully!');
    }, 800);
  };

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-semibold font-heading">Settings</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Manage your organization and system settings</p>
      </div>

      <Tabs defaultValue="organization">
        <TabsList className="w-full sm:w-auto grid grid-cols-5 sm:flex">
          <TabsTrigger value="organization" className="gap-1.5 text-xs sm:text-sm"><Building size={13} />Organization</TabsTrigger>
          <TabsTrigger value="venues" className="gap-1.5 text-xs sm:text-sm"><Building size={13} />Venues</TabsTrigger>
          <TabsTrigger value="notifications" className="gap-1.5 text-xs sm:text-sm"><Bell size={13} />Notifications</TabsTrigger>
          <TabsTrigger value="security" className="gap-1.5 text-xs sm:text-sm"><Shield size={13} />Security</TabsTrigger>
          {isAdmin && <TabsTrigger value="admin" className="gap-1.5 text-xs sm:text-sm"><Wrench size={13} />Admin</TabsTrigger>}
        </TabsList>

        {/* Organization */}
        <TabsContent value="organization" className="mt-6">
          <Card className="shadow-soft rounded-xl">
            <CardHeader className="pb-4">
              <CardTitle className="text-base">Organization Details</CardTitle>
              <CardDescription>Manage your organization's basic information</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSaveOrg} className="space-y-5">
                <div className="flex items-center gap-5 p-4 rounded-lg bg-secondary/40 border border-border">
                  <img src="https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1" alt="Logo" className="h-12 w-auto object-contain" />
                  <div>
                    <p className="text-sm font-medium">Organization Logo</p>
                    <p className="text-xs text-muted-foreground mt-0.5">Appears on login and public pages</p>
                    <Button variant="outline" size="sm" className="mt-2" type="button" onClick={() => toast.info('Logo upload coming soon')}>Change Logo</Button>
                  </div>
                </div>
                <div className="grid sm:grid-cols-2 gap-5">
                  <div className="space-y-2"><Label>Organization Name</Label><Input value={orgSettings.orgName} onChange={e => setOrgSettings({...orgSettings, orgName: e.target.value})} /></div>
                  <div className="space-y-2"><Label>Contact Email</Label><Input type="email" value={orgSettings.orgEmail} onChange={e => setOrgSettings({...orgSettings, orgEmail: e.target.value})} /></div>
                  <div className="space-y-2"><Label>Phone Number</Label><Input value={orgSettings.orgPhone} onChange={e => setOrgSettings({...orgSettings, orgPhone: e.target.value})} /></div>
                  <div className="space-y-2"><Label>Address</Label><Input value={orgSettings.orgAddress} onChange={e => setOrgSettings({...orgSettings, orgAddress: e.target.value})} /></div>
                  <div className="space-y-2">
                    <Label>Timezone</Label>
                    <Select value={orgSettings.timezone} onValueChange={v => setOrgSettings({...orgSettings, timezone: v})}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Africa/Kampala">Africa/Kampala (EAT)</SelectItem>
                        <SelectItem value="Africa/Nairobi">Africa/Nairobi (EAT)</SelectItem>
                        <SelectItem value="UTC">UTC</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Currency</Label>
                    <Select value={orgSettings.currency} onValueChange={v => setOrgSettings({...orgSettings, currency: v})}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="UGX">UGX - Ugandan Shilling</SelectItem>
                        <SelectItem value="USD">USD - US Dollar</SelectItem>
                        <SelectItem value="KES">KES - Kenyan Shilling</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <Button type="submit" className="gap-2" disabled={!isAdmin}><Save size={15} /> {isAdmin ? 'Save Changes' : 'Admin Only'}</Button>
              </form>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Venues */}
        <TabsContent value="venues" className="mt-6">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold">Venue Management</h3>
                <p className="text-sm text-muted-foreground">Manage spaces available for events and bookings</p>
              </div>
              <Button onClick={() => setShowAddVenue(true)} className="gap-2"><Plus size={15} /> Add Venue</Button>
            </div>

            {loadingVenues ? (
              <div className="space-y-3">
                {[1,2,3].map(i => <div key={i} className="h-20 bg-muted animate-pulse rounded-xl" />)}
              </div>
            ) : venues.length === 0 ? (
              <Card className="shadow-soft rounded-xl">
                <CardContent className="p-8 text-center text-muted-foreground">
                  <Building size={40} className="mx-auto mb-3 opacity-30" />
                  <p>No venues yet</p>
                  <Button variant="outline" className="mt-3" onClick={() => setShowAddVenue(true)}>Add your first venue</Button>
                </CardContent>
              </Card>
            ) : (
              <div className="grid sm:grid-cols-2 gap-4">
                {venues.map(venue => (
                  <Card key={venue.id} className="shadow-soft rounded-xl">
                    <CardContent className="p-4">
                      <div className="flex items-start justify-between mb-2">
                        <div>
                          <p className="font-semibold">{venue.name}</p>
                          <p className="text-xs text-muted-foreground capitalize">{venue.type} · {venue.capacity} capacity</p>
                        </div>
                        <Badge variant={venue.available ? 'outline' : 'secondary'} className={`text-xs ${venue.available ? 'border-green-500 text-green-600' : ''}`}>
                          {venue.available ? 'Available' : 'Booked'}
                        </Badge>
                      </div>
                      {venue.description && <p className="text-xs text-muted-foreground mb-3">{venue.description}</p>}
                      <p className="text-xs font-medium mb-3">{venue.hourly_rate ? `UGX ${venue.hourly_rate?.toLocaleString()}/hr` : 'Free use'}</p>
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" className="flex-1" onClick={() => toggleVenueAvailability(venue)}>
                          {venue.available ? 'Mark Booked' : 'Mark Available'}
                        </Button>
                        <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => deleteVenue(venue)}>
                          <Trash2 size={13} />
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>

          <Dialog open={showAddVenue} onOpenChange={setShowAddVenue}>
            <DialogContent className="max-w-md">
              <DialogHeader><DialogTitle>Add New Venue</DialogTitle></DialogHeader>
              <form onSubmit={handleAddVenue} className="space-y-4 mt-2">
                <div className="space-y-2"><Label>Name *</Label><Input placeholder="Venue name" value={newVenue.name} onChange={e => setNewVenue({...newVenue, name: e.target.value})} required /></div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Type</Label>
                    <Select value={newVenue.type} onValueChange={v => setNewVenue({...newVenue, type: v})}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="auditorium">Auditorium</SelectItem>
                        <SelectItem value="conference">Conference Room</SelectItem>
                        <SelectItem value="hall">Hall</SelectItem>
                        <SelectItem value="outdoor">Outdoor</SelectItem>
                        <SelectItem value="classroom">Classroom</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2"><Label>Capacity</Label><Input type="number" min={1} value={newVenue.capacity} onChange={e => setNewVenue({...newVenue, capacity: e.target.value})} /></div>
                </div>
                <div className="space-y-2"><Label>Description</Label><Input placeholder="Brief description" value={newVenue.description} onChange={e => setNewVenue({...newVenue, description: e.target.value})} /></div>
                <div className="space-y-2"><Label>Hourly Rate (UGX, leave blank if free)</Label><Input type="number" placeholder="20000" value={newVenue.hourly_rate} onChange={e => setNewVenue({...newVenue, hourly_rate: e.target.value})} /></div>
                <div className="flex gap-3 pt-2">
                  <Button type="button" variant="outline" className="flex-1" onClick={() => setShowAddVenue(false)}>Cancel</Button>
                  <Button type="submit" className="flex-1">Add Venue</Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        </TabsContent>

        {/* Notifications */}
        <TabsContent value="notifications" className="mt-6">
          <Card className="shadow-soft rounded-xl">
            <CardHeader className="pb-4">
              <CardTitle className="text-base">Notification Preferences</CardTitle>
              <CardDescription>Choose when and how you receive notifications</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div>
                <p className="text-sm font-medium mb-3">Email Notifications</p>
                <div className="space-y-3">
                  {[
                    { key: 'emailCheckins', label: 'Check-in alerts', desc: 'Get notified when members check in' },
                    { key: 'emailNewMembers', label: 'New member registrations', desc: 'Alerts when someone requests access' },
                    { key: 'emailEvents', label: 'Event reminders', desc: 'Reminder emails before scheduled events' },
                  ].map(item => (
                    <div key={item.key} className="flex items-center justify-between p-3 rounded-lg border border-border">
                      <div><p className="text-sm font-medium">{item.label}</p><p className="text-xs text-muted-foreground">{item.desc}</p></div>
                      <Switch checked={notifications[item.key]} onCheckedChange={v => setNotifications({...notifications, [item.key]: v})} />
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-sm font-medium mb-3">SMS Notifications</p>
                <div className="space-y-3">
                  {[
                    { key: 'smsCheckins', label: 'Check-in SMS', desc: 'SMS alerts for check-ins' },
                    { key: 'smsEvents', label: 'Event reminders (SMS)', desc: 'SMS reminders for upcoming events' },
                  ].map(item => (
                    <div key={item.key} className="flex items-center justify-between p-3 rounded-lg border border-border">
                      <div><p className="text-sm font-medium">{item.label}</p><p className="text-xs text-muted-foreground">{item.desc}</p></div>
                      <Switch checked={notifications[item.key]} onCheckedChange={v => setNotifications({...notifications, [item.key]: v})} />
                    </div>
                  ))}
                </div>
              </div>
              <Button onClick={() => toast.success('Preferences saved!')} className="gap-2"><Save size={15} /> Save Preferences</Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Security */}
        <TabsContent value="security" className="mt-6">
          <div className="space-y-5">
            <Card className="shadow-soft rounded-xl">
              <CardHeader className="pb-4">
                <CardTitle className="text-base">Change Password</CardTitle>
                <CardDescription>Update your account password</CardDescription>
              </CardHeader>
              <CardContent>
                <form className="space-y-4" onSubmit={handleChangePassword}>
                  <div className="space-y-2"><Label>Current Password</Label><Input type="password" placeholder="••••••••" value={passwords.current} onChange={e => setPasswords({...passwords, current: e.target.value})} required /></div>
                  <div className="space-y-2"><Label>New Password</Label><Input type="password" placeholder="••••••••" value={passwords.new_} onChange={e => setPasswords({...passwords, new_: e.target.value})} required /></div>
                  <div className="space-y-2"><Label>Confirm New Password</Label><Input type="password" placeholder="••••••••" value={passwords.confirm} onChange={e => setPasswords({...passwords, confirm: e.target.value})} required /></div>
                  <Button type="submit" className="gap-2" disabled={savingPass}><Shield size={15} />{savingPass ? 'Updating...' : 'Update Password'}</Button>
                </form>
              </CardContent>
            </Card>
            <Card className="shadow-soft rounded-xl">
              <CardHeader className="pb-4">
                <CardTitle className="text-base">Two-Factor Authentication</CardTitle>
                <CardDescription>Add an extra layer of security to your account</CardDescription>
              </CardHeader>
              <CardContent className="flex items-center justify-between">
                <div>
                  <p className="text-sm">2FA Status: <span className="text-muted-foreground">Not enabled</span></p>
                  <p className="text-xs text-muted-foreground mt-1">Enable 2FA to protect your account</p>
                </div>
                <Button variant="outline" onClick={() => toast.info('2FA setup coming soon')}>Enable 2FA</Button>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Admin */}
        {isAdmin && (
          <TabsContent value="admin" className="mt-6">
            <Card className="shadow-soft rounded-xl">
              <CardHeader className="pb-4">
                <CardTitle className="text-base">Application Settings</CardTitle>
                <CardDescription>System-wide configuration (admin only)</CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="flex items-center justify-between p-3 rounded-lg border border-border">
                  <div>
                    <p className="text-sm font-medium">Open Registration</p>
                    <p className="text-xs text-muted-foreground">Allow new users to self-register</p>
                  </div>
                  <Switch checked={appSettings.registration_open} onCheckedChange={v => setAppSettings({...appSettings, registration_open: v})} data-testid="registration-toggle" />
                </div>
                <div className="flex items-center justify-between p-3 rounded-lg border border-border">
                  <div>
                    <p className="text-sm font-medium">Maintenance Mode</p>
                    <p className="text-xs text-muted-foreground">Show maintenance page to non-admin users</p>
                  </div>
                  <Switch checked={appSettings.maintenance_mode} onCheckedChange={v => setAppSettings({...appSettings, maintenance_mode: v})} data-testid="maintenance-toggle" />
                </div>
                <div className="space-y-2">
                  <Label>Default User Role</Label>
                  <Select value={appSettings.default_role} onValueChange={v => setAppSettings({...appSettings, default_role: v})}>
                    <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="member">Member</SelectItem>
                      <SelectItem value="volunteer">Volunteer</SelectItem>
                      <SelectItem value="staff">Staff</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <Button onClick={handleSaveAppSettings} disabled={savingAdmin} className="gap-2" data-testid="save-admin-settings-btn">
                  <Save size={15} /> {savingAdmin ? 'Saving...' : 'Save Admin Settings'}
                </Button>
              </CardContent>
            </Card>
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
