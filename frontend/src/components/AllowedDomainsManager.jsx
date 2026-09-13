/**
 * AllowedDomainsManager — the browser origins allowed to call this API
 * (CORS allowlist), editable without a redeploy.
 *
 * The deployment's own domains (Emergent preview + *.emergent.host) are always
 * allowed in the backend; this list is for custom domains. The API picks up
 * changes within 60s.
 */
import React, { useEffect, useState } from 'react';
import { ShieldCheck, Plus, X } from 'lucide-react';
import api from '../services/api';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { toast } from 'sonner';

export default function AllowedDomainsManager() {
  const [origins, setOrigins] = useState([]);
  const [newOrigin, setNewOrigin] = useState('');
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const r = await api.get('/admin/system-settings');
      setOrigins(r.data?.security?.cors_origins || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to load allowed domains');
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const save = async (list) => {
    setSaving(true);
    try {
      const r = await api.put('/admin/system-settings', { security: { cors_origins: list } });
      setOrigins(r.data?.security?.cors_origins || []);
      toast.success('Allowed domains saved — live within a minute, no redeploy');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Save failed');
    } finally { setSaving(false); }
  };

  const add = async () => {
    const v = newOrigin.trim();
    if (!v) return;
    if (origins.some(o => o === v || o === `https://${v.toLowerCase()}`)) {
      toast.info('That domain is already allowed');
      setNewOrigin('');
      return;
    }
    await save([...origins, v]);
    setNewOrigin('');
  };

  return (
    <Card data-testid="allowed-domains-manager">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-start gap-3">
          <ShieldCheck size={16} className="text-emerald-600 mt-0.5 shrink-0" />
          <div className="space-y-1">
            <h3 className="text-sm font-semibold">Allowed Web Domains</h3>
            <p className="text-xs text-muted-foreground">
              Browsers may only call this API from the domains listed here. Your Emergent
              preview and <code>*.emergent.host</code> deployment domains are always allowed —
              add your own below. Changes go live within a minute, no redeploy.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5" data-testid="cors-origins-list">
          {loading && <span className="text-[11px] text-muted-foreground italic">Loading…</span>}
          {!loading && origins.length === 0 && (
            <span className="text-[11px] text-muted-foreground italic">No extra domains yet.</span>
          )}
          {origins.map(o => (
            <span
              key={o}
              className="inline-flex items-center gap-1 pl-2.5 pr-1 py-1 rounded-full border bg-muted/40 text-[11px] font-mono"
              data-testid={`cors-origin-${o}`}
            >
              {o}
              <button
                type="button"
                className="p-0.5 rounded-full hover:bg-destructive/15 hover:text-destructive transition-colors"
                onClick={() => save(origins.filter(x => x !== o))}
                disabled={saving}
                aria-label={`Remove ${o}`}
                data-testid={`cors-remove-${o}`}
              ><X size={11} /></button>
            </span>
          ))}
        </div>

        <div className="flex gap-2 max-w-xl">
          <Input
            value={newOrigin}
            onChange={e => setNewOrigin(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
            placeholder="app.yourdomain.org"
            className="h-9 text-sm font-mono"
            data-testid="cors-origin-input"
          />
          <Button onClick={add} disabled={saving || !newOrigin.trim()} className="gap-1 shrink-0" data-testid="cors-origin-add-btn">
            <Plus size={14} /> Add
          </Button>
        </div>
        <p className="text-[10px] text-muted-foreground">
          One host per entry — <code>app.example.org</code> (https is assumed). No paths, no wildcards;
          add <code>www.</code> separately if you use it.
        </p>
      </CardContent>
    </Card>
  );
}
