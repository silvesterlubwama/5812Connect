/**
 * LicenseManager — admin card on /admin for self-hosted license configuration.
 *
 * Renders TWO different UIs depending on what the deploy is:
 *   • If `system_admin` AND the deploy looks like the HQ instance (has any
 *     records in db.licenses already, OR the user explicitly toggles to HQ
 *     mode), shows the LICENSE ROSTER + ISSUE form.
 *   • Otherwise (every other deploy), shows the LOCAL CONFIG form — paste a
 *     license key + HQ URL + telemetry opt-in checkbox. Read-only banner shows
 *     the current license status.
 *
 * The LICENSE ROSTER + ISSUE form lets HQ admins:
 *   - Generate a new license key tied to an org_name + plan + expires_at
 *   - See all issued licenses + their install count + status
 *   - Block / unblock a license (soft-revoke — heartbeat returns 'blocked')
 *   - Delete a license entirely
 *
 * The LOCAL CONFIG form pastes the issued key into this install. The desktop
 * cron sends a daily heartbeat using these credentials.
 */
import React, { useEffect, useState } from 'react';
import { KeyRound, Plus, Copy, Trash2, Ban, RefreshCw } from 'lucide-react';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { Switch } from './ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import api from '../services/api';
import { toast } from 'sonner';

const STATUS_BADGE = {
  valid: 'bg-emerald-100 text-emerald-700',
  expired: 'bg-amber-100 text-amber-700',
  invalid: 'bg-rose-100 text-rose-700',
  blocked: 'bg-rose-100 text-rose-700',
  unlicensed: 'bg-slate-100 text-slate-600',
};

export default function LicenseManager() {
  const [open, setOpen] = useState(false);
  const [self, setSelf] = useState(null);
  const [licenses, setLicenses] = useState([]);
  const [installs, setInstalls] = useState([]);
  const [loadingHq, setLoadingHq] = useState(false);
  const [tab, setTab] = useState('local');
  // Local-config form
  const [licenseKey, setLicenseKey] = useState('');
  const [hqUrl, setHqUrl] = useState('https://hq.5812-global.org');
  const [telemetryEnabled, setTelemetryEnabled] = useState(true);
  // HQ issue form
  const [issueForm, setIssueForm] = useState({ org_name: '', plan: 'standard', expires_at: '' });

  const loadSelf = async () => {
    try {
      const r = await api.get('/license/self');
      setSelf(r.data);
      setLicenseKey(r.data?.license_key || '');
      setHqUrl(r.data?.hq_url || 'https://hq.5812-global.org');
      setTelemetryEnabled(r.data?.telemetry_enabled !== false);
    } catch (e) { console.warn(e?.message || e); }
  };

  const loadHq = async () => {
    setLoadingHq(true);
    try {
      const [licRes, instRes] = await Promise.all([
        api.get('/admin/licenses'),
        api.get('/admin/telemetry/installs'),
      ]);
      setLicenses(licRes.data || []);
      setInstalls(instRes.data?.installs || []);
    } catch (e) { console.warn(e?.message || e); }
    finally { setLoadingHq(false); }
  };

  useEffect(() => { if (open) { loadSelf(); loadHq(); } }, [open]);

  const saveLocal = async () => {
    try {
      await api.post('/license/configure', {
        license_key: licenseKey.trim(),
        hq_url: hqUrl.trim(),
        telemetry_enabled: telemetryEnabled,
      });
      toast.success('License saved — next heartbeat will use it');
      await loadSelf();
    } catch (e) { toast.error(e.response?.data?.detail || 'Save failed'); }
  };

  const issueLicense = async () => {
    if (!issueForm.org_name.trim()) { toast.error('Org name required'); return; }
    try {
      const r = await api.post('/admin/licenses', {
        org_name: issueForm.org_name.trim(),
        plan: issueForm.plan,
        expires_at: issueForm.expires_at || null,
      });
      toast.success(`License issued for ${r.data.org_name}`);
      setIssueForm({ org_name: '', plan: 'standard', expires_at: '' });
      await loadHq();
    } catch (e) { toast.error(e.response?.data?.detail || 'Issue failed'); }
  };

  const blockLicense = async (lic) => {
    const reason = window.prompt('Reason for blocking?');
    if (reason === null) return;
    try {
      await api.put(`/admin/licenses/${lic.id}`, { blocked: true, blocked_reason: reason || 'Revoked' });
      toast.success('License blocked');
      await loadHq();
    } catch (e) { toast.error(e.response?.data?.detail || 'Block failed'); }
  };

  const unblockLicense = async (lic) => {
    try {
      await api.put(`/admin/licenses/${lic.id}`, { blocked: false, blocked_reason: '' });
      toast.success('License unblocked');
      await loadHq();
    } catch (e) { toast.error(e.response?.data?.detail || 'Unblock failed'); }
  };

  const deleteLicense = async (lic) => {
    if (!window.confirm(`Permanently delete license for "${lic.org_name}"? Cannot be undone.`)) return;
    try {
      await api.delete(`/admin/licenses/${lic.id}`);
      toast.success('License deleted');
      await loadHq();
    } catch (e) { toast.error(e.response?.data?.detail || 'Delete failed'); }
  };

  const copyKey = (key) => {
    navigator.clipboard.writeText(key);
    toast.success('Copied to clipboard');
  };

  const localStatus = self?.license_status || 'unlicensed';

  return (
    <>
      <Card className="rounded-xl mt-4 cursor-pointer hover:border-primary/40" onClick={() => setOpen(true)} data-testid="license-card">
        <CardContent className="p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <KeyRound size={18} className="text-primary" />
            <div>
              <p className="font-medium text-sm">License & Telemetry</p>
              <p className="text-xs text-muted-foreground">Configure this install's license key + opt-in to anonymous health heartbeats. HQ admins can also issue keys here.</p>
            </div>
          </div>
          <Badge className={STATUS_BADGE[localStatus] || 'bg-slate-100'}>{localStatus}</Badge>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto" data-testid="license-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><KeyRound size={16} /> License & Telemetry</DialogTitle>
            <DialogDescription className="text-xs">
              Self-hosted installs report a daily anonymous health heartbeat to HQ. License keys are soft-enforced — invalid keys show a banner but never crash the app.
            </DialogDescription>
          </DialogHeader>

          <Tabs value={tab} onValueChange={setTab} className="mt-3">
            <TabsList>
              <TabsTrigger value="local" data-testid="license-tab-local">This install</TabsTrigger>
              <TabsTrigger value="hq" data-testid="license-tab-hq">HQ ({licenses.length} key{licenses.length === 1 ? '' : 's'})</TabsTrigger>
              <TabsTrigger value="installs" data-testid="license-tab-installs">Installs ({installs.length})</TabsTrigger>
            </TabsList>

            {/* LOCAL */}
            <TabsContent value="local" className="space-y-3 mt-3">
              <div className="p-3 rounded-lg border space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">Status</p>
                    <p className="text-[11px] text-muted-foreground">{self?.last_heartbeat_at ? `Last heartbeat ${new Date(self.last_heartbeat_at).toLocaleString()}` : 'No heartbeat sent yet'}</p>
                  </div>
                  <Badge className={STATUS_BADGE[localStatus] || 'bg-slate-100'} data-testid="license-self-status">{localStatus}</Badge>
                </div>
                {self?.install_id && (
                  <div className="text-[11px] text-muted-foreground font-mono">install_id: {self.install_id}</div>
                )}
                {self?.license_message && (
                  <p className="text-xs text-rose-600">{self.license_message}</p>
                )}
              </div>

              <div className="p-3 rounded-lg border space-y-3">
                <div className="space-y-1">
                  <Label className="text-xs">License key (paste from HQ)</Label>
                  <Input value={licenseKey} onChange={e => setLicenseKey(e.target.value)} placeholder="leave blank for unlicensed" className="font-mono text-xs" data-testid="license-key-input" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">HQ heartbeat URL</Label>
                  <Input value={hqUrl} onChange={e => setHqUrl(e.target.value)} placeholder="https://hq.5812-global.org" className="font-mono text-xs" data-testid="license-hq-url-input" />
                </div>
                <div className="flex items-center justify-between p-2 rounded border bg-muted/30">
                  <div>
                    <p className="text-sm font-medium">Send anonymous health heartbeat</p>
                    <p className="text-[11px] text-muted-foreground">Daily POST with install_id, version, user_count. No PII. Disable anytime.</p>
                  </div>
                  <Switch checked={telemetryEnabled} onCheckedChange={setTelemetryEnabled} data-testid="license-telemetry-switch" />
                </div>
                <div className="flex justify-end">
                  <Button size="sm" onClick={saveLocal} data-testid="license-save-btn">Save</Button>
                </div>
              </div>
            </TabsContent>

            {/* HQ — issue / list licenses */}
            <TabsContent value="hq" className="space-y-3 mt-3">
              <div className="p-3 rounded-lg border space-y-3">
                <p className="text-sm font-semibold">Issue a new license</p>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label className="text-xs">Organisation name</Label>
                    <Input value={issueForm.org_name} onChange={e => setIssueForm({ ...issueForm, org_name: e.target.value })} placeholder="Hope Centre Uganda" data-testid="license-issue-org" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Plan</Label>
                    <select className="border rounded h-9 px-2 text-sm w-full" value={issueForm.plan} onChange={e => setIssueForm({ ...issueForm, plan: e.target.value })} data-testid="license-issue-plan">
                      <option value="standard">Standard</option>
                      <option value="extended">Extended</option>
                      <option value="trial">Trial</option>
                    </select>
                  </div>
                  <div className="space-y-1 col-span-2">
                    <Label className="text-xs">Expires (optional, ISO date)</Label>
                    <Input type="date" value={issueForm.expires_at} onChange={e => setIssueForm({ ...issueForm, expires_at: e.target.value })} data-testid="license-issue-expires" />
                  </div>
                </div>
                <Button size="sm" onClick={issueLicense} data-testid="license-issue-btn"><Plus size={12} className="mr-1" /> Issue license</Button>
              </div>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold">Issued licenses</p>
                  <Button size="sm" variant="ghost" onClick={loadHq} disabled={loadingHq}><RefreshCw size={12} className={loadingHq ? 'animate-spin' : ''} /></Button>
                </div>
                {licenses.length === 0 ? (
                  <p className="text-xs text-muted-foreground text-center py-4">No licenses issued yet</p>
                ) : licenses.map(lic => (
                  <div key={lic.id} className="p-3 rounded border text-xs space-y-1" data-testid={`license-row-${lic.id}`}>
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <p className="font-medium text-sm">{lic.org_name}</p>
                      <div className="flex items-center gap-1.5">
                        <Badge variant="outline" className="text-[10px]">{lic.plan || 'standard'}</Badge>
                        {lic.blocked && <Badge className="bg-rose-100 text-rose-700 text-[10px]">blocked</Badge>}
                        <span className="text-[10px] text-muted-foreground">{lic.installs_using} install{lic.installs_using === 1 ? '' : 's'}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <code className="text-[10px] bg-muted px-1.5 py-0.5 rounded">{lic.key}</code>
                      <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => copyKey(lic.key)} title="Copy key"><Copy size={10} /></Button>
                      {lic.expires_at && <span className="text-[10px] text-muted-foreground">expires {String(lic.expires_at).slice(0, 10)}</span>}
                    </div>
                    <div className="flex justify-end gap-1.5 pt-1">
                      {lic.blocked ? (
                        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => unblockLicense(lic)}>Unblock</Button>
                      ) : (
                        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => blockLicense(lic)}><Ban size={10} className="mr-1" />Block</Button>
                      )}
                      <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive" onClick={() => deleteLicense(lic)}><Trash2 size={10} /></Button>
                    </div>
                  </div>
                ))}
              </div>
            </TabsContent>

            {/* Installs roster */}
            <TabsContent value="installs" className="space-y-2 mt-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold">Active installs</p>
                <Button size="sm" variant="ghost" onClick={loadHq} disabled={loadingHq}><RefreshCw size={12} className={loadingHq ? 'animate-spin' : ''} /></Button>
              </div>
              {installs.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-4">No heartbeats received yet</p>
              ) : installs.map(inst => (
                <div key={inst.install_id} className="p-3 rounded border text-xs space-y-1" data-testid={`install-row-${inst.install_id}`}>
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <p className="font-medium text-sm">{inst.org_id || 'Unnamed install'}</p>
                    <Badge className={STATUS_BADGE[inst.license_status_obj?.license_status] || 'bg-slate-100'}>{inst.license_status_obj?.license_status || 'unknown'}</Badge>
                  </div>
                  <div className="flex items-center gap-3 text-[10px] text-muted-foreground flex-wrap">
                    <span>v{inst.version || '?'}</span>
                    <span>{inst.user_count} users</span>
                    <span>{inst.env}</span>
                    <span>last seen {inst.days_since_last_seen != null ? `${inst.days_since_last_seen}d ago` : '?'}</span>
                    <code className="font-mono">{inst.install_id?.slice(0, 8)}…</code>
                  </div>
                </div>
              ))}
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>
    </>
  );
}
