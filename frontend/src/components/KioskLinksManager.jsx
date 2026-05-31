/**
 * KioskLinksManager — admin tool that centralizes every kiosk/portal URL in one
 * dialog. Each section has a copyable URL, a QR code (so an admin can scan it
 * with the kiosk device), open-in-new-tab, and setup notes.
 *
 * Used as a card on /admin alongside the other admin tools.
 */
import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { Link2, Copy, ExternalLink, ShieldCheck, ShoppingBag, ScanLine, Globe, Briefcase, UserCircle, RefreshCw, Eye, EyeOff, Cable } from 'lucide-react';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Badge } from './ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { QRCode } from 'react-qrcode-logo';
import { toast } from 'sonner';
import { locationsApi, securityCheckpointApi } from '../services/api';
import DeviceDiagnosticsDialog from './DeviceDiagnosticsDialog';

const _origin = () => {
  if (typeof window === 'undefined') return '';
  // Prefer the configured backend host so deployed URLs match what kiosk operators expect.
  // process.env.REACT_APP_BACKEND_URL points at the API; for browser-facing kiosk pages
  // the canonical origin is window.location.origin (same as the staff is currently on).
  return window.location.origin;
};

function LinkRow({ label, url, qrSize = 96, hint, badgePillText, copyTestId, qrTestId }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      toast.success(`Copied: ${label}`);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error('Could not copy — select the URL manually');
    }
  };
  return (
    <div className="flex items-start gap-3 p-3 rounded-lg border bg-card" data-testid={`kiosk-link-${label.replace(/\s+/g, '-').toLowerCase()}`}>
      <div className="shrink-0 bg-white p-1 rounded border">
        <QRCode value={url} size={qrSize} ecLevel="M" quietZone={2} qrStyle="dots" eyeRadius={4} />
      </div>
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex items-center gap-2">
          <p className="text-sm font-semibold">{label}</p>
          {badgePillText && <Badge variant="outline" className="text-[10px]">{badgePillText}</Badge>}
        </div>
        {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
        <div className="flex items-center gap-2">
          <code className="flex-1 text-[11px] bg-muted px-2 py-1 rounded font-mono truncate" title={url}>{url}</code>
          <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={copy} data-testid={copyTestId || `copy-${label.replace(/\s+/g, '-').toLowerCase()}`}>
            <Copy size={11} className="mr-1" /> {copied ? 'Copied' : 'Copy'}
          </Button>
          <Button size="sm" variant="outline" className="h-7 text-[11px]" asChild>
            <a href={url} target="_blank" rel="noopener noreferrer" data-testid={qrTestId || `open-${label.replace(/\s+/g, '-').toLowerCase()}`}>
              <ExternalLink size={11} className="mr-1" /> Open
            </a>
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function KioskLinksManager() {
  const [open, setOpen] = useState(false);
  const [locations, setLocations] = useState([]);
  const [checkpoints, setCheckpoints] = useState([]);
  const [showPins, setShowPins] = useState(false);
  const [showDiag, setShowDiag] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [locs, cps] = await Promise.all([
        locationsApi.list(),
        securityCheckpointApi.list().catch(() => ({ data: [] })),
      ]);
      setLocations(locs.data || []);
      setCheckpoints(cps.data || []);
    } catch (e) { toast.error('Failed to load kiosk data'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (open) load(); }, [open, load]);

  const origin = _origin();
  // Stores with POS marketplace enabled. If the flag isn't present, we show every
  // active location since /pos/:storeId works for any location_id today.
  const posLocations = useMemo(() => locations.filter(l => l.active !== false), [locations]);

  return (
    <>
      <Card className="rounded-xl mt-4 cursor-pointer hover:border-primary/40" onClick={() => setOpen(true)} data-testid="kiosk-links-card">
        <CardContent className="p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link2 size={18} className="text-primary" />
            <div>
              <p className="font-medium text-sm">Kiosk Links &amp; Setup</p>
              <p className="text-xs text-muted-foreground">
                Every kiosk + portal URL in one place — copy, open, or scan the QR with the device. Includes Security Checkpoint pairing PINs.
              </p>
            </div>
          </div>
          <Button size="sm" variant="outline">Open</Button>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto" data-testid="kiosk-links-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Link2 size={16} /> Kiosk Links &amp; Setup</DialogTitle>
            <DialogDescription className="text-xs">
              Open the right link on each device. For Security Checkpoints, the pairing PIN below joins a device to a specific checkpoint.
            </DialogDescription>
          </DialogHeader>

          <div className="flex items-center gap-2 mt-2 mb-4 flex-wrap">
            <Button size="sm" variant="outline" onClick={load} disabled={loading}>
              <RefreshCw size={11} className={`mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </Button>
            <Button size="sm" variant="outline" onClick={() => setShowPins(s => !s)} data-testid="kiosk-links-toggle-pins">
              {showPins ? <EyeOff size={11} className="mr-1" /> : <Eye size={11} className="mr-1" />} {showPins ? 'Hide' : 'Show'} pairing PINs
            </Button>
            <Button size="sm" variant="outline" onClick={() => setShowDiag(true)} data-testid="kiosk-links-diagnostics-btn">
              <Cable size={11} className="mr-1" /> Device diagnostics
            </Button>
          </div>

          {/* SECURITY CHECKPOINT */}
          <section className="space-y-3 mb-5">
            <div className="flex items-center gap-2">
              <ShieldCheck size={14} className="text-emerald-600" />
              <h3 className="text-sm font-semibold">Security Checkpoint</h3>
              <Badge variant="outline" className="text-[10px]">{checkpoints.length} configured</Badge>
            </div>
            <LinkRow
              label="Security Checkpoint Device"
              url={`${origin}/security-checkpoint`}
              hint="Open on each gate device — guest tablet AND security console use this same URL. Enter the 6-digit pairing PIN of the checkpoint they belong to."
            />
            {checkpoints.length > 0 ? (
              <div className="ml-4 space-y-2">
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Pairing PINs (also scannable as unlock QR)</p>
                {checkpoints.map(cp => (
                  <div key={cp.id} className="flex items-center justify-between p-2 rounded border bg-muted/30 gap-3" data-testid={`kiosk-cp-pin-${cp.id}`}>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-medium truncate">{cp.name}</p>
                      <p className="text-[10px] text-muted-foreground">{cp.location_name} · {(cp.kind || 'strict').replace('_', ' ')} · {cp.device_mode === 'single_device' ? 'single device' : 'dual device'}</p>
                    </div>
                    <code className="px-2 py-0.5 rounded bg-emerald-50 dark:bg-emerald-950/30 text-emerald-800 dark:text-emerald-300 text-sm font-mono tracking-widest">
                      {showPins ? cp.pairing_pin : '••••••'}
                    </code>
                    {showPins && (
                      <div className="shrink-0 bg-white p-0.5 rounded border" title="Scan to unlock kiosk">
                        <QRCode value={`CPK_UNLOCK:${cp.pairing_pin}`} size={48} ecLevel="L" quietZone={1} qrStyle="squares" />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-muted-foreground italic ml-4">
                No checkpoints yet — create one via the Security Checkpoints card above.
              </p>
            )}
          </section>

          {/* CHECK-IN KIOSK */}
          <section className="space-y-3 mb-5">
            <div className="flex items-center gap-2">
              <ScanLine size={14} className="text-primary" />
              <h3 className="text-sm font-semibold">Check-in Kiosk</h3>
            </div>
            <LinkRow
              label="Check-in Kiosk"
              url={`${origin}/kiosk`}
              hint="Tablet-friendly check-in surface for members + guests. Use the in-kiosk Setup screen (PIN-protected) to bind a campus + lock the screen."
            />
          </section>

          {/* POS */}
          <section className="space-y-3 mb-5">
            <div className="flex items-center gap-2">
              <ShoppingBag size={14} className="text-amber-600" />
              <h3 className="text-sm font-semibold">POS Kiosk</h3>
              <Badge variant="outline" className="text-[10px]">{posLocations.length} location{posLocations.length === 1 ? '' : 's'}</Badge>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Each location has its own slim POS shell. Open the URL on the cashier device and log in with a cashier PIN.
            </p>
            {posLocations.length > 0 ? (
              <div className="space-y-2">
                {posLocations.map(loc => (
                  <LinkRow
                    key={loc.id}
                    label={`POS — ${loc.name}`}
                    url={`${origin}/pos/${loc.id}`}
                    qrSize={72}
                    hint={`Slim POS shell scoped to ${loc.name}. Tabs other than POS are hidden in this URL.`}
                    badgePillText={loc.is_restricted ? 'restricted' : null}
                  />
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-muted-foreground italic">No locations configured.</p>
            )}
          </section>

          {/* PUBLIC SURFACES */}
          <section className="space-y-3 mb-5">
            <div className="flex items-center gap-2">
              <Globe size={14} className="text-blue-600" />
              <h3 className="text-sm font-semibold">Public Surfaces</h3>
            </div>
            <LinkRow
              label="Public Marketplace"
              url={`${origin}/marketplace`}
              hint="Public-facing event tickets, space booking, and resource booking. Share with anyone."
            />
            <LinkRow
              label="Sales Portal"
              url={`${origin}/sales-portal`}
              hint="Members-only sales portal for purchasing products + viewing receipts."
            />
          </section>

          {/* AUTH'D PORTALS */}
          <section className="space-y-3">
            <div className="flex items-center gap-2">
              <UserCircle size={14} className="text-violet-600" />
              <h3 className="text-sm font-semibold">User Portals</h3>
            </div>
            <LinkRow
              label="Member / Parent Portal"
              url={`${origin}/portal`}
              hint="Logged-in members + parents land here. Read-only views of their own data + child accounts."
            />
            <div className="p-3 rounded-lg border bg-muted/30 text-[11px] text-muted-foreground">
              <div className="flex items-start gap-2">
                <Briefcase size={12} className="mt-0.5 shrink-0" />
                <div>
                  <p className="font-medium text-foreground">Sponsor &amp; School portals</p>
                  <p className="mt-1">Per-recipient tokenised URLs — issued from <code className="bg-background px-1 rounded">Social Work</code> (sponsor) and from each school record (school portal). They live at <code className="bg-background px-1 rounded">/sponsor-portal/&lt;token&gt;</code> and <code className="bg-background px-1 rounded">/school-portal/&lt;token&gt;</code>.</p>
                </div>
              </div>
            </div>
          </section>
        </DialogContent>
      </Dialog>
      <DeviceDiagnosticsDialog open={showDiag} onClose={() => setShowDiag(false)} />
    </>
  );
}
