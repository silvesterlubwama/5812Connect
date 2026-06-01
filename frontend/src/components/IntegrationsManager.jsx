/**
 * IntegrationsManager — admin tool to configure runtime integrations:
 *   • Resend / SMTP email (used by overdue-task emails, customer statements, etc.)
 *   • Sentry DSN (error tracking, requires server restart to fully apply)
 *   • Org primary country/currency
 *
 * All secrets are masked when reading — the operator types the new value to replace.
 * "Send test email" verifies the config end-to-end before saving.
 */
import React, { useEffect, useState } from 'react';
import { Settings2, Mail, Bug, Globe, Eye, EyeOff, Send, CheckCircle2 } from 'lucide-react';
import api from '../services/api';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { toast } from 'sonner';

export default function IntegrationsManager() {
  const [open, setOpen] = useState(false);
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showKey, setShowKey] = useState(false);
  // Mutable form state — separate from `settings` so we can detect dirty fields
  const [emailDraft, setEmailDraft] = useState({});
  const [sentryDraft, setSentryDraft] = useState({});
  const [orgDraft, setOrgDraft] = useState({});

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get('/admin/system-settings');
      setSettings(r.data);
      // Pre-fill drafts with non-secret fields; secrets stay blank so we don't overwrite
      setEmailDraft({
        provider: r.data?.email?.provider || 'resend',
        sender_email: r.data?.email?.sender_email || '',
        sender_name: r.data?.email?.sender_name || '58:12 Connect',
        smtp_host: r.data?.email?.smtp_host || '',
        smtp_port: r.data?.email?.smtp_port || 587,
        smtp_user: r.data?.email?.smtp_user || '',
        smtp_tls: r.data?.email?.smtp_tls !== false,
        resend_api_key: '',
        smtp_password: '',
      });
      setSentryDraft({
        enabled: r.data?.sentry?.enabled || false,
        dsn: '',
        environment: r.data?.sentry?.environment || 'production',
        traces_sample_rate: r.data?.sentry?.traces_sample_rate ?? 0.1,
      });
      setOrgDraft({
        primary_country: r.data?.org?.primary_country || 'Uganda',
        primary_currency: r.data?.org?.primary_currency || 'UGX',
      });
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to load settings');
    } finally { setLoading(false); }
  };
  useEffect(() => { if (open) load(); }, [open]);

  const saveEmail = async () => {
    setSaving(true);
    try {
      // Only send the API key if the operator typed something — blank = keep current
      const payload = { email: { ...emailDraft } };
      if (!emailDraft.resend_api_key) delete payload.email.resend_api_key;
      if (!emailDraft.smtp_password) delete payload.email.smtp_password;
      await api.put('/admin/system-settings', payload);
      toast.success('Email settings saved');
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Save failed');
    } finally { setSaving(false); }
  };

  const saveSentry = async () => {
    setSaving(true);
    try {
      const payload = { sentry: { ...sentryDraft } };
      if (!sentryDraft.dsn) delete payload.sentry.dsn;
      await api.put('/admin/system-settings', payload);
      toast.success('Sentry settings saved — restart the backend to apply');
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Save failed');
    } finally { setSaving(false); }
  };

  const saveOrg = async () => {
    setSaving(true);
    try {
      await api.put('/admin/system-settings', { org: { ...orgDraft } });
      toast.success('Organisation settings saved');
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Save failed');
    } finally { setSaving(false); }
  };

  const sendTest = async () => {
    setTesting(true);
    try {
      const r = await api.post('/admin/system-settings/test-email', {});
      toast.success(`Test email sent via ${r.data.provider} to ${r.data.to}${r.data.message_id ? ` · id ${r.data.message_id}` : ''}`, { duration: 8000 });
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Test send failed', { duration: 8000 });
    } finally { setTesting(false); }
  };

  return (
    <>
      <Card className="rounded-xl mt-4 cursor-pointer hover:border-primary/40" onClick={() => setOpen(true)} data-testid="integrations-card">
        <CardContent className="p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Settings2 size={18} className="text-primary" />
            <div>
              <p className="font-medium text-sm">Integrations &amp; Email</p>
              <p className="text-xs text-muted-foreground">
                Configure Resend / SMTP email + Sentry error tracking from the UI — no redeploy needed. Travels with the backup.
              </p>
            </div>
          </div>
          <Button size="sm" variant="outline">Configure</Button>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl max-h-[88vh] overflow-y-auto" data-testid="integrations-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Settings2 size={16} /> Integrations</DialogTitle>
            <DialogDescription className="text-xs">
              Settings live in the database, so they get backed up and travel with deployments. Secrets are masked when read — type to replace.
            </DialogDescription>
          </DialogHeader>

          {loading || !settings ? (
            <p className="text-sm text-muted-foreground py-8 text-center">Loading…</p>
          ) : (
            <div className="space-y-5 mt-2">
              {/* EMAIL */}
              <section className="space-y-3 p-3 rounded-lg border" data-testid="integrations-email-section">
                <h3 className="text-sm font-semibold flex items-center gap-2"><Mail size={14} className="text-emerald-600" /> Email
                  {settings.email?.resend_api_key_set || settings.email?.smtp_password_set
                    ? <Badge className="bg-emerald-100 text-emerald-700 text-[10px]">Configured</Badge>
                    : <Badge variant="outline" className="text-[10px]">Not configured</Badge>}
                </h3>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label className="text-xs">Provider</Label>
                    <select className="h-9 w-full rounded border bg-background px-2 text-sm" value={emailDraft.provider} onChange={e => setEmailDraft({ ...emailDraft, provider: e.target.value })} data-testid="email-provider-select">
                      <option value="resend">Resend (recommended)</option>
                      <option value="smtp">Generic SMTP</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Sender name</Label>
                    <Input value={emailDraft.sender_name} onChange={e => setEmailDraft({ ...emailDraft, sender_name: e.target.value })} placeholder="58:12 Connect" />
                  </div>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Sender email (must be verified with your provider)</Label>
                  <Input value={emailDraft.sender_email} onChange={e => setEmailDraft({ ...emailDraft, sender_email: e.target.value })} placeholder="noreply@yourdomain.org" data-testid="email-sender-input" />
                </div>

                {emailDraft.provider === 'resend' && (
                  <div className="space-y-1">
                    <Label className="text-xs flex items-center gap-2">
                      Resend API key
                      {settings.email?.resend_api_key_set && <span className="text-[10px] text-muted-foreground">Current: {settings.email.resend_api_key_masked}</span>}
                    </Label>
                    <div className="flex gap-2">
                      <Input
                        type={showKey ? 'text' : 'password'}
                        value={emailDraft.resend_api_key}
                        onChange={e => setEmailDraft({ ...emailDraft, resend_api_key: e.target.value })}
                        placeholder={settings.email?.resend_api_key_set ? 'Leave blank to keep current' : 're_xxxxxxxxxxxxxxxx'}
                        data-testid="email-resend-key-input"
                      />
                      <Button type="button" size="sm" variant="outline" onClick={() => setShowKey(s => !s)}>
                        {showKey ? <EyeOff size={12} /> : <Eye size={12} />}
                      </Button>
                    </div>
                    <p className="text-[10px] text-muted-foreground">Get one at <a href="https://resend.com/api-keys" target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">resend.com/api-keys</a></p>
                  </div>
                )}

                {emailDraft.provider === 'smtp' && (
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1"><Label className="text-xs">SMTP host</Label><Input value={emailDraft.smtp_host} onChange={e => setEmailDraft({ ...emailDraft, smtp_host: e.target.value })} placeholder="smtp.example.com" /></div>
                    <div className="space-y-1"><Label className="text-xs">Port</Label><Input type="number" value={emailDraft.smtp_port} onChange={e => setEmailDraft({ ...emailDraft, smtp_port: parseInt(e.target.value || '587', 10) })} /></div>
                    <div className="space-y-1"><Label className="text-xs">Username</Label><Input value={emailDraft.smtp_user} onChange={e => setEmailDraft({ ...emailDraft, smtp_user: e.target.value })} /></div>
                    <div className="space-y-1"><Label className="text-xs">Password</Label><Input type="password" value={emailDraft.smtp_password} onChange={e => setEmailDraft({ ...emailDraft, smtp_password: e.target.value })} placeholder={settings.email?.smtp_password_set ? 'Leave blank to keep current' : '·····'} /></div>
                    <label className="flex items-center gap-2 text-xs col-span-2"><input type="checkbox" checked={emailDraft.smtp_tls} onChange={e => setEmailDraft({ ...emailDraft, smtp_tls: e.target.checked })} /> Use STARTTLS</label>
                  </div>
                )}

                <div className="flex gap-2 pt-1">
                  <Button onClick={saveEmail} disabled={saving} data-testid="email-save-btn">{saving ? 'Saving…' : 'Save'}</Button>
                  <Button variant="outline" onClick={sendTest} disabled={testing || !settings.email?.resend_api_key_set} title={!settings.email?.resend_api_key_set ? 'Save the key first, then test' : ''} data-testid="email-test-btn">
                    <Send size={12} className="mr-1" /> {testing ? 'Sending…' : 'Send test email'}
                  </Button>
                </div>
              </section>

              {/* SENTRY */}
              <section className="space-y-3 p-3 rounded-lg border" data-testid="integrations-sentry-section">
                <h3 className="text-sm font-semibold flex items-center gap-2"><Bug size={14} className="text-amber-600" /> Sentry (error tracking)
                  {settings.sentry?.dsn_set
                    ? <Badge className="bg-emerald-100 text-emerald-700 text-[10px]">Configured</Badge>
                    : <Badge variant="outline" className="text-[10px]">Not configured</Badge>}
                </h3>
                <label className="flex items-center gap-2 text-xs">
                  <input type="checkbox" checked={sentryDraft.enabled} onChange={e => setSentryDraft({ ...sentryDraft, enabled: e.target.checked })} data-testid="sentry-enabled-toggle" />
                  Enable Sentry error reporting
                </label>
                <div className="space-y-1">
                  <Label className="text-xs">DSN {settings.sentry?.dsn_set && <span className="text-[10px] text-muted-foreground ml-1">Current: {settings.sentry.dsn_masked}</span>}</Label>
                  <Input
                    type="password"
                    value={sentryDraft.dsn}
                    onChange={e => setSentryDraft({ ...sentryDraft, dsn: e.target.value })}
                    placeholder={settings.sentry?.dsn_set ? 'Leave blank to keep current' : 'https://...@o0.ingest.sentry.io/...'}
                    data-testid="sentry-dsn-input"
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1"><Label className="text-xs">Environment</Label><Input value={sentryDraft.environment} onChange={e => setSentryDraft({ ...sentryDraft, environment: e.target.value })} placeholder="production" /></div>
                  <div className="space-y-1"><Label className="text-xs">Sample rate (0.0 – 1.0)</Label><Input type="number" step="0.1" min="0" max="1" value={sentryDraft.traces_sample_rate} onChange={e => setSentryDraft({ ...sentryDraft, traces_sample_rate: parseFloat(e.target.value) })} /></div>
                </div>
                <Button onClick={saveSentry} disabled={saving} data-testid="sentry-save-btn">{saving ? 'Saving…' : 'Save'}</Button>
                <p className="text-[10px] text-muted-foreground italic">Sentry reads its config on backend boot — restart the backend (or wait for the next deploy) for changes to take effect.</p>
              </section>

              {/* ORG */}
              <section className="space-y-3 p-3 rounded-lg border" data-testid="integrations-org-section">
                <h3 className="text-sm font-semibold flex items-center gap-2"><Globe size={14} className="text-blue-600" /> Organisation</h3>
                <p className="text-[11px] text-muted-foreground">Drives the default currency on Finance dashboards and per-country VAT/compliance logic. Picked up on every page load — no redeploy needed.</p>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label className="text-xs">Primary country</Label>
                    <select className="h-9 w-full rounded border bg-background px-2 text-sm" value={orgDraft.primary_country} onChange={e => setOrgDraft({ ...orgDraft, primary_country: e.target.value })} data-testid="org-country-select">
                      {['Uganda', 'Kenya', 'Tanzania', 'Rwanda', 'Burundi', 'Haiti', 'Thailand', 'USA', 'United Kingdom', 'South Africa', 'Nigeria', 'Ghana', 'Ethiopia'].map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Primary currency</Label>
                    <select className="h-9 w-full rounded border bg-background px-2 text-sm" value={orgDraft.primary_currency} onChange={e => setOrgDraft({ ...orgDraft, primary_currency: e.target.value })} data-testid="org-currency-select">
                      {['UGX', 'KES', 'TZS', 'RWF', 'BIF', 'HTG', 'THB', 'USD', 'GBP', 'EUR', 'ZAR', 'NGN', 'GHS', 'ETB'].map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </div>
                </div>
                <Button onClick={saveOrg} disabled={saving} data-testid="org-save-btn">{saving ? 'Saving…' : 'Save organisation'}</Button>
              </section>

              <p className="text-[10px] text-muted-foreground italic">
                <CheckCircle2 size={10} className="inline mr-1" /> These settings live in <code>db.system_settings</code> and are included in the backup tarball, so they travel with deployments.
              </p>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
