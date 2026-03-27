import React, { useState, useEffect } from 'react';
import { Settings, Save, Globe, DollarSign, Phone, Mail, MapPin, Building2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { adminApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

export default function AppSettingsPage() {
  const { user } = useAuth();
  const [settings, setSettings] = useState({
    app_name: '', currency: 'UGX', main_currency: 'USD',
    footer_text: '', contact_email: '', contact_phone: '', contact_address: '', logo_url: '',
  });
  const [currencies, setCurrencies] = useState([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([adminApi.globalSettings(), adminApi.currencies()])
      .then(([sRes, cRes]) => {
        setSettings(prev => ({ ...prev, ...sRes.data }));
        setCurrencies(cRes.data || []);
      })
      .catch(() => toast.error('Failed to load settings'))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await adminApi.updateGlobalSettings(settings);
      toast.success('Settings saved');
    } catch { toast.error('Save failed'); }
    finally { setSaving(false); }
  };

  const isAdmin = ['admin', 'system_admin'].includes(user?.role);

  if (loading) return <div className="p-6"><div className="h-64 bg-muted animate-pulse rounded-xl" /></div>;

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6 max-w-3xl" data-testid="app-settings-page">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-primary/10"><Settings size={18} className="text-primary" /></div>
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold font-heading">App Settings</h1>
          <p className="text-sm text-muted-foreground">Customize your organization's app</p>
        </div>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base flex items-center gap-2"><Globe size={16} /> Branding</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>App / Organization Name</Label>
            <Input data-testid="setting-app-name" value={settings.app_name} onChange={e => setSettings({...settings, app_name: e.target.value})} disabled={!isAdmin} />
          </div>
          <div className="space-y-2">
            <Label>Footer Text</Label>
            <Input data-testid="setting-footer" value={settings.footer_text} onChange={e => setSettings({...settings, footer_text: e.target.value})} disabled={!isAdmin} />
          </div>
          <div className="space-y-2">
            <Label>Logo URL</Label>
            <Input placeholder="https://..." value={settings.logo_url || ''} onChange={e => setSettings({...settings, logo_url: e.target.value})} disabled={!isAdmin} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base flex items-center gap-2"><DollarSign size={16} /> Currency</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Default Currency</Label>
              <Select value={settings.currency || 'UGX'} onValueChange={v => setSettings({...settings, currency: v})} disabled={!isAdmin}>
                <SelectTrigger data-testid="setting-currency"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {currencies.map(c => <SelectItem key={c.code} value={c.code}>{c.symbol} {c.name} ({c.code})</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Main Location Currency (auto-exchange base)</Label>
              <Select value={settings.main_currency || 'USD'} onValueChange={v => setSettings({...settings, main_currency: v})} disabled={!isAdmin}>
                <SelectTrigger data-testid="setting-main-currency"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {currencies.map(c => <SelectItem key={c.code} value={c.code}>{c.symbol} {c.name} ({c.code})</SelectItem>)}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">All location financials auto-convert to this currency at the main campus level</p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base flex items-center gap-2"><Phone size={16} /> Contact Information</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2"><Label>Contact Email</Label><Input data-testid="setting-email" type="email" value={settings.contact_email || ''} onChange={e => setSettings({...settings, contact_email: e.target.value})} disabled={!isAdmin} /></div>
            <div className="space-y-2"><Label>Contact Phone</Label><Input data-testid="setting-phone" value={settings.contact_phone || ''} onChange={e => setSettings({...settings, contact_phone: e.target.value})} disabled={!isAdmin} /></div>
          </div>
          <div className="space-y-2"><Label>Address</Label><Textarea rows={2} value={settings.contact_address || ''} onChange={e => setSettings({...settings, contact_address: e.target.value})} disabled={!isAdmin} /></div>
        </CardContent>
      </Card>

      {isAdmin && (
        <Button onClick={handleSave} disabled={saving} className="gap-2" data-testid="save-settings-btn">
          <Save size={14} /> {saving ? 'Saving...' : 'Save Settings'}
        </Button>
      )}
    </div>
  );
}
