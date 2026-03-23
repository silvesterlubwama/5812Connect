import React, { useState } from 'react';
import { Save, Bell, Shield, Globe, Users, Building } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Switch } from '../components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { toast } from 'sonner';

export default function SettingsPage() {
  const [orgSettings, setOrgSettings] = useState({
    orgName: '58:12 Global Connect',
    orgEmail: 'info@5812global.org',
    orgPhone: '+256 800 5812',
    orgAddress: 'Kampala, Uganda',
    timezone: 'Africa/Kampala',
    currency: 'UGX',
  });

  const [notifications, setNotifications] = useState({
    emailCheckins: true,
    emailNewMembers: true,
    emailEvents: false,
    smsCheckins: false,
    smsEvents: true,
  });

  const handleSaveOrg = (e) => {
    e.preventDefault();
    toast.success('Organization settings saved!');
  };

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-semibold font-heading">Settings</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Manage your organization and system settings</p>
      </div>

      <Tabs defaultValue="organization">
        <TabsList className="w-full sm:w-auto">
          <TabsTrigger value="organization" className="gap-2"><Building size={14} />Organization</TabsTrigger>
          <TabsTrigger value="notifications" className="gap-2"><Bell size={14} />Notifications</TabsTrigger>
          <TabsTrigger value="security" className="gap-2"><Shield size={14} />Security</TabsTrigger>
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
                {/* Logo */}
                <div className="flex items-center gap-5 p-4 rounded-lg bg-secondary/40 border border-border">
                  <img
                    src="https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1"
                    alt="Logo"
                    className="h-12 w-auto object-contain"
                  />
                  <div>
                    <p className="text-sm font-medium">Organization Logo</p>
                    <p className="text-xs text-muted-foreground mt-0.5">Appears on login page and public pages</p>
                    <Button variant="outline" size="sm" className="mt-2" type="button">Change Logo</Button>
                  </div>
                </div>

                <div className="grid sm:grid-cols-2 gap-5">
                  <div className="space-y-2">
                    <Label>Organization Name</Label>
                    <Input value={orgSettings.orgName} onChange={e => setOrgSettings({...orgSettings, orgName: e.target.value})} />
                  </div>
                  <div className="space-y-2">
                    <Label>Contact Email</Label>
                    <Input type="email" value={orgSettings.orgEmail} onChange={e => setOrgSettings({...orgSettings, orgEmail: e.target.value})} />
                  </div>
                  <div className="space-y-2">
                    <Label>Phone Number</Label>
                    <Input value={orgSettings.orgPhone} onChange={e => setOrgSettings({...orgSettings, orgPhone: e.target.value})} />
                  </div>
                  <div className="space-y-2">
                    <Label>Address</Label>
                    <Input value={orgSettings.orgAddress} onChange={e => setOrgSettings({...orgSettings, orgAddress: e.target.value})} />
                  </div>
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

                <Button type="submit" className="gap-2">
                  <Save size={15} /> Save Changes
                </Button>
              </form>
            </CardContent>
          </Card>
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
                    { key: 'emailNewMembers', label: 'New member registrations', desc: 'Alerts when someone requests account access' },
                    { key: 'emailEvents', label: 'Event reminders', desc: 'Reminder emails before scheduled events' },
                  ].map(item => (
                    <div key={item.key} className="flex items-center justify-between p-3 rounded-lg border border-border">
                      <div>
                        <p className="text-sm font-medium">{item.label}</p>
                        <p className="text-xs text-muted-foreground">{item.desc}</p>
                      </div>
                      <Switch
                        checked={notifications[item.key]}
                        onCheckedChange={v => setNotifications({...notifications, [item.key]: v})}
                      />
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
                      <div>
                        <p className="text-sm font-medium">{item.label}</p>
                        <p className="text-xs text-muted-foreground">{item.desc}</p>
                      </div>
                      <Switch
                        checked={notifications[item.key]}
                        onCheckedChange={v => setNotifications({...notifications, [item.key]: v})}
                      />
                    </div>
                  ))}
                </div>
              </div>

              <Button onClick={() => toast.success('Notification settings saved!')} className="gap-2">
                <Save size={15} /> Save Preferences
              </Button>
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
                <form className="space-y-4" onSubmit={e => { e.preventDefault(); toast.success('Password changed successfully!'); }}>
                  <div className="space-y-2">
                    <Label>Current Password</Label>
                    <Input type="password" placeholder="••••••••" />
                  </div>
                  <div className="space-y-2">
                    <Label>New Password</Label>
                    <Input type="password" placeholder="••••••••" />
                  </div>
                  <div className="space-y-2">
                    <Label>Confirm New Password</Label>
                    <Input type="password" placeholder="••••••••" />
                  </div>
                  <Button type="submit" className="gap-2">
                    <Shield size={15} /> Update Password
                  </Button>
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
                <Button variant="outline" onClick={() => toast.info('2FA setup would open here')}>Enable 2FA</Button>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
