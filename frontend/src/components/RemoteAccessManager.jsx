/**
 * RemoteAccessManager — admin card on /admin (desktop bundle only).
 *
 * Renders a Cloudflare Tunnel config editor + start/stop buttons. Only mounts when
 * the app is running inside the Tauri shell (`window.__TAURI__` present). On the
 * cloud preview / production deployments this returns null silently.
 */
import React, { useEffect, useState } from 'react';
import { Cloud, Play, Square, RefreshCw } from 'lucide-react';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog';
import { toast } from 'sonner';

const SAMPLE_CONFIG = `tunnel: <TUNNEL-UUID-FROM-CLOUDFLARE>
credentials-file: <ABSOLUTE-PATH-TO-CREDENTIALS.JSON>
ingress:
  - hostname: desktop.5812-global.org
    service: http://127.0.0.1:8001
  - service: http_status:404`;

function isTauri() {
  return typeof window !== 'undefined' && (window.__TAURI_INTERNALS__ || window.__TAURI__);
}

async function invoke(cmd, args = {}) {
  // Tauri v2 invoke surface
  const fn = window.__TAURI_INTERNALS__?.invoke || window.__TAURI__?.core?.invoke;
  if (!fn) throw new Error('Tauri runtime not available');
  return fn(cmd, args);
}

export default function RemoteAccessManager() {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState({ mongo: false, backend: false, cloudflared: false, backend_url: '' });
  const [config, setConfig] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    try {
      const s = await invoke('services_status');
      setStatus(s);
    } catch (e) {
      console.warn(e?.message || e);
    }
  };

  useEffect(() => {
    if (!isTauri()) return;
    refresh();
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (open) {
      const saved = localStorage.getItem('5812_cloudflared_config');
      setConfig(saved || SAMPLE_CONFIG);
    }
  }, [open]);

  if (!isTauri()) return null;

  const startTunnel = async () => {
    setBusy(true);
    try {
      const msg = await invoke('start_cloudflare_tunnel', { configYaml: config });
      localStorage.setItem('5812_cloudflared_config', config);
      toast.success(msg || 'Tunnel started');
      setTimeout(refresh, 1500);
    } catch (e) {
      toast.error(String(e?.message || e));
    } finally { setBusy(false); }
  };

  const stopTunnel = async () => {
    setBusy(true);
    try {
      await invoke('stop_cloudflare_tunnel');
      toast.success('Tunnel stopped');
      setTimeout(refresh, 800);
    } catch (e) {
      toast.error(String(e?.message || e));
    } finally { setBusy(false); }
  };

  return (
    <>
      <Card className="rounded-xl mt-4 cursor-pointer hover:border-primary/40" onClick={() => setOpen(true)} data-testid="remote-access-card">
        <CardContent className="p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Cloud size={18} className="text-primary" />
            <div>
              <p className="font-medium text-sm">Remote Access (Cloudflare Tunnel)</p>
              <p className="text-xs text-muted-foreground">Expose this desktop instance over a public Cloudflare hostname without opening firewall ports.</p>
            </div>
          </div>
          <Badge className={status.cloudflared ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'}>
            {status.cloudflared ? 'Running' : 'Stopped'}
          </Badge>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl max-h-[88vh] overflow-y-auto" data-testid="remote-access-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Cloud size={16} /> Remote Access</DialogTitle>
            <DialogDescription className="text-xs">
              Paste a Cloudflare Tunnel YAML config below. The `cloudflared` daemon bundled with this build will spawn with this config and proxy your local backend to a public hostname.
            </DialogDescription>
          </DialogHeader>

          {/* Service status row */}
          <div className="grid grid-cols-3 gap-2 my-3 text-xs">
            <div className="p-2 rounded border" data-testid="rmt-status-mongo">
              <p className="text-muted-foreground">MongoDB</p>
              <Badge className={status.mongo ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}>{status.mongo ? 'Running' : 'Down'}</Badge>
            </div>
            <div className="p-2 rounded border" data-testid="rmt-status-backend">
              <p className="text-muted-foreground">Backend</p>
              <Badge className={status.backend ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}>{status.backend ? 'Running' : 'Down'}</Badge>
            </div>
            <div className="p-2 rounded border" data-testid="rmt-status-tunnel">
              <p className="text-muted-foreground">Tunnel</p>
              <Badge className={status.cloudflared ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'}>{status.cloudflared ? 'Running' : 'Stopped'}</Badge>
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-xs">Tunnel config (YAML)</Label>
            <Textarea
              value={config}
              onChange={e => setConfig(e.target.value)}
              rows={12}
              className="font-mono text-xs"
              placeholder={SAMPLE_CONFIG}
              data-testid="rmt-config-yaml"
            />
            <p className="text-[10px] text-muted-foreground">
              Get the tunnel UUID + credentials JSON from{' '}
              <a className="underline text-primary" href="https://one.dash.cloudflare.com" target="_blank" rel="noreferrer">one.dash.cloudflare.com</a>{' '}
              → Networks → Tunnels → Create.
            </p>
          </div>

          <div className="flex gap-2 pt-3 sticky bottom-0 bg-background pb-1">
            <Button variant="ghost" size="sm" onClick={refresh}><RefreshCw size={12} className="mr-1" /> Refresh</Button>
            <div className="flex-1" />
            {status.cloudflared ? (
              <Button variant="destructive" size="sm" onClick={stopTunnel} disabled={busy} data-testid="rmt-stop-btn"><Square size={12} className="mr-1" /> Stop tunnel</Button>
            ) : (
              <Button size="sm" onClick={startTunnel} disabled={busy || !config.trim()} data-testid="rmt-start-btn"><Play size={12} className="mr-1" /> Start tunnel</Button>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
