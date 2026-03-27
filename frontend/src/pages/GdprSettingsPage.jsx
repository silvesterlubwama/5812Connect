import React, { useState, useEffect } from 'react';
import { Shield, Download, Trash2, Eye, EyeOff, Save, AlertTriangle, FileText, User, Clock, Lock } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Switch } from '../components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { gdprApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

export default function GdprSettingsPage() {
  const { user } = useAuth();
  const isAdmin = ['admin', 'system_admin'].includes(user?.role);
  const [settings, setSettings] = useState({
    data_retention_days: 365,
    allow_data_export: true,
    allow_account_deletion: true,
    consent_required: true,
    anonymize_on_delete: true,
    show_privacy_policy: true,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [showAnonymize, setShowAnonymize] = useState(false);
  const [anonymizeUserId, setAnonymizeUserId] = useState('');

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    setLoading(true);
    try {
      const res = await gdprApi.settings();
      setSettings(prev => ({ ...prev, ...res.data }));
    } catch {
      // Settings might not exist yet
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await gdprApi.updateSettings(settings);
      toast.success('GDPR settings saved');
    } catch {
      toast.error('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleExportMyData = async () => {
    setExporting(true);
    try {
      const res = await gdprApi.exportMyData();
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `my_data_export_${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success('Your data has been exported');
      setShowExport(false);
    } catch {
      toast.error('Failed to export data');
    } finally {
      setExporting(false);
    }
  };

  const handleAnonymize = async () => {
    if (!anonymizeUserId.trim()) {
      toast.error('Please enter a user ID');
      return;
    }
    if (!window.confirm('This action is IRREVERSIBLE. All personal data for this user will be anonymized. Continue?')) return;
    try {
      await gdprApi.anonymize(anonymizeUserId);
      toast.success('User data anonymized');
      setShowAnonymize(false);
      setAnonymizeUserId('');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to anonymize');
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-4xl" data-testid="gdpr-settings-page">
      <div>
        <h1 className="text-2xl font-semibold font-heading flex items-center gap-2">
          <Shield size={24} className="text-primary" /> Privacy & GDPR Settings
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">Manage data privacy, retention, and compliance settings</p>
      </div>

      {/* User Rights Section */}
      <Card className="shadow-soft rounded-xl">
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <User size={16} className="text-blue-600" /> Your Data Rights
          </CardTitle>
          <CardDescription>Exercise your privacy rights under GDPR</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="p-4 rounded-lg border border-border">
              <div className="flex items-center gap-2 mb-2">
                <Download size={18} className="text-green-600" />
                <p className="font-medium text-sm">Export Your Data</p>
              </div>
              <p className="text-xs text-muted-foreground mb-3">Download all personal data we have about you in a machine-readable format.</p>
              <Button size="sm" variant="outline" className="w-full gap-2" onClick={() => setShowExport(true)} data-testid="export-my-data-btn">
                <Download size={14} /> Request Export
              </Button>
            </div>

            <div className="p-4 rounded-lg border border-border">
              <div className="flex items-center gap-2 mb-2">
                <Eye size={18} className="text-blue-600" />
                <p className="font-medium text-sm">Right to Access</p>
              </div>
              <p className="text-xs text-muted-foreground mb-3">View what personal information we store about you.</p>
              <Button size="sm" variant="outline" className="w-full" asChild>
                <a href="/portal/profile">View My Profile</a>
              </Button>
            </div>
          </div>

          <div className="p-4 rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800">
            <div className="flex items-start gap-2">
              <AlertTriangle size={16} className="text-amber-600 mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-medium text-amber-800 dark:text-amber-400">Right to Erasure</p>
                <p className="text-xs text-amber-700 dark:text-amber-500 mt-1">
                  To request deletion of your account and all associated data, please contact an administrator. This action is irreversible.
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Admin Settings */}
      {isAdmin && (
        <>
          <Card className="shadow-soft rounded-xl">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Lock size={16} className="text-purple-600" /> Organization Privacy Settings
              </CardTitle>
              <CardDescription>Configure organization-wide GDPR compliance settings</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {loading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map(i => <div key={i} className="h-16 bg-muted animate-pulse rounded-lg" />)}
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between p-3 rounded-lg border border-border">
                    <div>
                      <p className="text-sm font-medium">Require Consent</p>
                      <p className="text-xs text-muted-foreground">Users must consent to data processing on registration</p>
                    </div>
                    <Switch checked={settings.consent_required} onCheckedChange={v => setSettings({ ...settings, consent_required: v })} data-testid="consent-toggle" />
                  </div>

                  <div className="flex items-center justify-between p-3 rounded-lg border border-border">
                    <div>
                      <p className="text-sm font-medium">Allow Data Export</p>
                      <p className="text-xs text-muted-foreground">Users can export their personal data</p>
                    </div>
                    <Switch checked={settings.allow_data_export} onCheckedChange={v => setSettings({ ...settings, allow_data_export: v })} />
                  </div>

                  <div className="flex items-center justify-between p-3 rounded-lg border border-border">
                    <div>
                      <p className="text-sm font-medium">Allow Account Deletion</p>
                      <p className="text-xs text-muted-foreground">Users can request account deletion</p>
                    </div>
                    <Switch checked={settings.allow_account_deletion} onCheckedChange={v => setSettings({ ...settings, allow_account_deletion: v })} />
                  </div>

                  <div className="flex items-center justify-between p-3 rounded-lg border border-border">
                    <div>
                      <p className="text-sm font-medium">Anonymize on Delete</p>
                      <p className="text-xs text-muted-foreground">Replace personal data with anonymous values instead of hard delete</p>
                    </div>
                    <Switch checked={settings.anonymize_on_delete} onCheckedChange={v => setSettings({ ...settings, anonymize_on_delete: v })} />
                  </div>

                  <div className="flex items-center justify-between p-3 rounded-lg border border-border">
                    <div>
                      <p className="text-sm font-medium">Show Privacy Policy Link</p>
                      <p className="text-xs text-muted-foreground">Display privacy policy in footer and registration</p>
                    </div>
                    <Switch checked={settings.show_privacy_policy} onCheckedChange={v => setSettings({ ...settings, show_privacy_policy: v })} />
                  </div>

                  <div className="p-3 rounded-lg border border-border">
                    <div className="flex items-center justify-between mb-2">
                      <div>
                        <p className="text-sm font-medium flex items-center gap-2"><Clock size={14} /> Data Retention Period</p>
                        <p className="text-xs text-muted-foreground">Days to retain inactive user data</p>
                      </div>
                      <Badge variant="outline">{settings.data_retention_days} days</Badge>
                    </div>
                    <input
                      type="range"
                      min={30}
                      max={730}
                      step={30}
                      value={settings.data_retention_days}
                      onChange={e => setSettings({ ...settings, data_retention_days: parseInt(e.target.value) })}
                      className="w-full"
                    />
                    <div className="flex justify-between text-xs text-muted-foreground mt-1">
                      <span>30 days</span>
                      <span>1 year</span>
                      <span>2 years</span>
                    </div>
                  </div>

                  <Button className="w-full gap-2" onClick={handleSave} disabled={saving} data-testid="save-gdpr-settings-btn">
                    <Save size={14} /> {saving ? 'Saving...' : 'Save Settings'}
                  </Button>
                </>
              )}
            </CardContent>
          </Card>

          {/* Admin Actions */}
          <Card className="shadow-soft rounded-xl border-red-200 dark:border-red-900">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2 text-red-600">
                <AlertTriangle size={16} /> Administrative Actions
              </CardTitle>
              <CardDescription>Destructive actions for data management</CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="destructive" className="gap-2" onClick={() => setShowAnonymize(true)} data-testid="anonymize-user-btn">
                <EyeOff size={14} /> Anonymize User Data
              </Button>
              <p className="text-xs text-muted-foreground mt-2">
                Permanently anonymize a specific user's personal data while preserving their activity history.
              </p>
            </CardContent>
          </Card>
        </>
      )}

      {/* Legal Documents */}
      <Card className="shadow-soft rounded-xl">
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <FileText size={16} className="text-slate-600" /> Legal Documents
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Button variant="outline" className="w-full justify-start gap-2" onClick={() => toast.info('Privacy policy page coming soon')}>
            <FileText size={14} /> Privacy Policy
          </Button>
          <Button variant="outline" className="w-full justify-start gap-2" onClick={() => toast.info('Terms of service page coming soon')}>
            <FileText size={14} /> Terms of Service
          </Button>
          <Button variant="outline" className="w-full justify-start gap-2" onClick={() => toast.info('Cookie policy page coming soon')}>
            <FileText size={14} /> Cookie Policy
          </Button>
        </CardContent>
      </Card>

      {/* Export Dialog */}
      <Dialog open={showExport} onOpenChange={setShowExport}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Download size={18} /> Export Your Data</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <p className="text-sm text-muted-foreground">
              This will generate a JSON file containing all your personal data including profile information, activity history, and preferences.
            </p>
            <div className="p-3 rounded-lg bg-blue-50 dark:bg-blue-950/30 text-xs text-blue-700 dark:text-blue-400">
              The export may take a few moments depending on data volume.
            </div>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => setShowExport(false)}>Cancel</Button>
              <Button className="flex-1 gap-2" onClick={handleExportMyData} disabled={exporting} data-testid="confirm-export-btn">
                <Download size={14} /> {exporting ? 'Exporting...' : 'Export Now'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Anonymize Dialog */}
      <Dialog open={showAnonymize} onOpenChange={setShowAnonymize}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-600"><EyeOff size={18} /> Anonymize User</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="p-3 rounded-lg bg-red-50 dark:bg-red-950/30 text-xs text-red-700 dark:text-red-400">
              <strong>Warning:</strong> This action is IRREVERSIBLE. All personal data will be replaced with anonymous values.
            </div>
            <div className="space-y-2">
              <Label>User ID to Anonymize</Label>
              <input
                type="text"
                className="w-full px-3 py-2 rounded-lg border border-border bg-background"
                placeholder="Enter user ID"
                value={anonymizeUserId}
                onChange={e => setAnonymizeUserId(e.target.value)}
              />
            </div>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => setShowAnonymize(false)}>Cancel</Button>
              <Button variant="destructive" className="flex-1" onClick={handleAnonymize} data-testid="confirm-anonymize-btn">
                Anonymize
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
