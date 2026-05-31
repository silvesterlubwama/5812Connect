/**
 * DeviceDiagnosticsDialog — a complete hardware/runtime panel for any kiosk.
 *
 * Use anywhere there's a `Diagnostics` button (Security Console, Check-in Kiosk,
 * POS, Admin Kiosk Links). Renders sections for Cameras / Mic / Speakers, NFC,
 * Web Serial / HID / USB / Bluetooth (with paired devices), Geolocation,
 * Battery, Network, Storage, Screen, runtime flags.
 *
 * Includes "Pair USB device" actions that delegate to navigator.{serial|hid|usb}.requestDevice()
 * — these need a user gesture so we trigger from explicit button clicks.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Camera, Mic, Volume2, Wifi, Smartphone, Usb, Bluetooth, MapPin, Battery, Globe, HardDrive, Monitor, Lock as LockIcon, ShieldAlert, CheckCircle2, AlertTriangle, RefreshCw, X, Cable } from 'lucide-react';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import {
  detectFullDiagnostics,
  requestCameraAccess,
  requestNfcAccess,
  requestGeoAccess,
} from '../utils/peripheralPermissions';
import { toast } from 'sonner';

const Pill = ({ tone, label }) => {
  const tones = {
    ok: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    info: 'bg-blue-100 text-blue-700 border-blue-200',
    warn: 'bg-amber-100 text-amber-700 border-amber-200',
    error: 'bg-rose-100 text-rose-700 border-rose-200',
    muted: 'bg-slate-100 text-slate-600 border-slate-200',
  };
  return <span className={`text-[10px] px-1.5 py-0.5 rounded border ${tones[tone] || tones.muted}`}>{label}</span>;
};

function Row({ icon: Icon, label, status, statusTone = 'muted', meta, action, testid }) {
  return (
    <div className="flex items-start gap-3 p-2.5 rounded border bg-card" data-testid={testid}>
      <Icon size={16} className="shrink-0 mt-0.5 text-muted-foreground" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium">{label}</p>
          {status && <Pill tone={statusTone} label={status} />}
        </div>
        {meta && <div className="text-[11px] text-muted-foreground mt-0.5">{meta}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export default function DeviceDiagnosticsDialog({ open, onClose }) {
  const [diag, setDiag] = useState(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try { setDiag(await detectFullDiagnostics()); }
    catch (e) { toast.error('Diagnostics failed: ' + (e?.message || e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (open) refresh(); }, [open, refresh]);

  const requestSerial = async () => {
    if (!navigator.serial) { toast.error('Web Serial not supported'); return; }
    try {
      await navigator.serial.requestPort();
      toast.success('Serial port paired');
      refresh();
    } catch (e) { toast.error(e?.message || 'Serial pairing canceled'); }
  };
  const requestHid = async () => {
    if (!navigator.hid) { toast.error('Web HID not supported'); return; }
    try {
      await navigator.hid.requestDevice({ filters: [] });
      toast.success('HID device paired');
      refresh();
    } catch (e) { toast.error(e?.message || 'HID pairing canceled'); }
  };
  const requestUsb = async () => {
    if (!navigator.usb) { toast.error('Web USB not supported'); return; }
    try {
      await navigator.usb.requestDevice({ filters: [] });
      toast.success('USB device paired');
      refresh();
    } catch (e) { toast.error(e?.message || 'USB pairing canceled'); }
  };
  const requestBt = async () => {
    if (!navigator.bluetooth) { toast.error('Web Bluetooth not supported'); return; }
    try {
      await navigator.bluetooth.requestDevice({ acceptAllDevices: true });
      toast.success('Bluetooth device paired');
      refresh();
    } catch (e) { toast.error(e?.message || 'Bluetooth pairing canceled'); }
  };

  if (!diag) {
    return (
      <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Device Diagnostics</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground py-8 text-center">Probing peripherals…</p>
        </DialogContent>
      </Dialog>
    );
  }

  const r = diag;
  // Helper to map permission state → tone+label
  const permTone = (perm, supported = true) => {
    if (!supported) return { tone: 'muted', label: 'Unsupported' };
    if (perm === 'granted') return { tone: 'ok', label: 'Granted' };
    if (perm === 'denied') return { tone: 'error', label: 'Denied' };
    if (perm === 'prompt') return { tone: 'info', label: 'Ready (no permission yet)' };
    return { tone: 'muted', label: 'Not checked' };
  };

  const camPerm = permTone(r.media.cameraPermission, r.media.cameras.length > 0);
  const micPerm = permTone(r.media.microphonePermission, r.media.microphones > 0);
  const nfcPerm = permTone(r.nfc.permission, r.nfc.supported);
  const geoPerm = permTone(r.geolocation.permission, r.geolocation.supported);

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto" data-testid="device-diagnostics-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Cable size={16} /> Device Diagnostics</DialogTitle>
          <DialogDescription className="text-xs">
            Everything this browser can see right now. {!r.runtime.isHttps && <span className="text-amber-700">⚠ Non-HTTPS context — most permission-gated APIs will be blocked.</span>}
          </DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-2 mb-3">
          <Button size="sm" variant="outline" onClick={refresh} disabled={loading} data-testid="diag-refresh">
            <RefreshCw size={11} className={`mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </Button>
          <span className="text-[10px] text-muted-foreground">Probed {new Date(r.detectedAt).toLocaleTimeString()}</span>
        </div>

        {/* MEDIA */}
        <section className="space-y-2 mb-4">
          <h3 className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">Media</h3>
          <Row
            icon={Camera}
            label={`Cameras (${r.media.cameras.length})`}
            status={camPerm.label}
            statusTone={camPerm.tone}
            meta={r.media.cameras.length > 0 ? r.media.cameras.map(c => c.label || c.deviceId.slice(0, 8) + '…').join(' · ') : 'No video input detected'}
            action={r.media.cameras.length > 0 && r.media.cameraPermission !== 'granted' && (
              <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={async () => { await requestCameraAccess(); refresh(); }} data-testid="diag-camera-grant">
                Enable
              </Button>
            )}
            testid="diag-row-cameras"
          />
          <Row
            icon={Mic}
            label={`Microphones (${r.media.microphones})`}
            status={micPerm.label}
            statusTone={micPerm.tone}
            meta={r.media.microphones === 0 ? 'No audio input detected' : null}
            testid="diag-row-microphones"
          />
          <Row
            icon={Volume2}
            label={`Speakers (${r.media.speakers})`}
            status={r.media.speakers > 0 ? 'OK' : 'Unknown'}
            statusTone={r.media.speakers > 0 ? 'ok' : 'muted'}
            testid="diag-row-speakers"
          />
        </section>

        {/* WIRELESS */}
        <section className="space-y-2 mb-4">
          <h3 className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">Wireless</h3>
          <Row
            icon={Smartphone}
            label="NFC tap reader"
            status={nfcPerm.label}
            statusTone={nfcPerm.tone}
            meta={r.nfc.supported ? 'Web NDEFReader available — Chrome on Android' : 'This browser/OS does not expose NFC'}
            action={r.nfc.supported && r.nfc.permission !== 'granted' && (
              <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={async () => { await requestNfcAccess(); refresh(); }} data-testid="diag-nfc-grant">Enable</Button>
            )}
            testid="diag-row-nfc"
          />
          <Row
            icon={Bluetooth}
            label="Bluetooth"
            status={r.bluetooth.supported ? `${(r.bluetooth.pairedDevices || []).length} paired` : 'Unsupported'}
            statusTone={r.bluetooth.supported ? ((r.bluetooth.pairedDevices || []).length > 0 ? 'ok' : 'info') : 'muted'}
            meta={(r.bluetooth.pairedDevices || []).map(d => d.name || d.id?.slice(0, 8)).join(' · ') || null}
            action={r.bluetooth.supported && (
              <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={requestBt} data-testid="diag-bt-pair">Pair</Button>
            )}
            testid="diag-row-bluetooth"
          />
        </section>

        {/* WIRED USB */}
        <section className="space-y-2 mb-4">
          <h3 className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">USB / Serial</h3>
          <Row
            icon={Cable}
            label="Web Serial (receipt printers, scales, weight indicators)"
            status={r.serial.supported ? `${(r.serial.pairedPorts || []).length} paired` : 'Unsupported'}
            statusTone={r.serial.supported ? ((r.serial.pairedPorts || []).length > 0 ? 'ok' : 'info') : 'muted'}
            meta={(r.serial.pairedPorts || []).map(p => `Vendor ${p.vendorId || '?'} / Product ${p.productId || '?'}`).join(' · ') || null}
            action={r.serial.supported && (
              <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={requestSerial} data-testid="diag-serial-pair">Pair port</Button>
            )}
            testid="diag-row-serial"
          />
          <Row
            icon={Usb}
            label="Web HID (barcode scanners, signature pads, cash drawers)"
            status={r.hid.supported ? `${(r.hid.pairedDevices || []).length} paired` : 'Unsupported'}
            statusTone={r.hid.supported ? ((r.hid.pairedDevices || []).length > 0 ? 'ok' : 'info') : 'muted'}
            meta={(r.hid.pairedDevices || []).map(d => d.productName || `${d.vendorId}/${d.productId}`).filter(Boolean).join(' · ') || null}
            action={r.hid.supported && (
              <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={requestHid} data-testid="diag-hid-pair">Pair HID</Button>
            )}
            testid="diag-row-hid"
          />
          <Row
            icon={Usb}
            label="Web USB (printers, mag stripe readers, custom hardware)"
            status={r.usb.supported ? `${(r.usb.pairedDevices || []).length} paired` : 'Unsupported'}
            statusTone={r.usb.supported ? ((r.usb.pairedDevices || []).length > 0 ? 'ok' : 'info') : 'muted'}
            meta={(r.usb.pairedDevices || []).map(d => [d.manufacturerName, d.productName].filter(Boolean).join(' ') || `${d.vendorId}/${d.productId}`).join(' · ') || null}
            action={r.usb.supported && (
              <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={requestUsb} data-testid="diag-usb-pair">Pair USB</Button>
            )}
            testid="diag-row-usb"
          />
        </section>

        {/* RUNTIME */}
        <section className="space-y-2 mb-4">
          <h3 className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">Runtime</h3>
          <Row
            icon={MapPin}
            label="Geolocation"
            status={geoPerm.label}
            statusTone={geoPerm.tone}
            action={r.geolocation.supported && r.geolocation.permission !== 'granted' && (
              <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={async () => { await requestGeoAccess(); refresh(); }} data-testid="diag-geo-grant">Enable</Button>
            )}
            testid="diag-row-geo"
          />
          <Row
            icon={Battery}
            label="Battery"
            status={r.battery ? (r.battery.charging ? 'Charging' : 'On battery') : 'Unsupported'}
            statusTone={r.battery ? (r.battery.charging || r.battery.level > 0.3 ? 'ok' : 'warn') : 'muted'}
            meta={r.battery ? `${Math.round(r.battery.level * 100)}%` : null}
            testid="diag-row-battery"
          />
          <Row
            icon={Globe}
            label="Network"
            status={r.network?.online ? 'Online' : 'Offline'}
            statusTone={r.network?.online ? 'ok' : 'error'}
            meta={r.network ? `${r.network.effectiveType || '?'} · ${r.network.downlinkMbps ?? '?'} Mb/s · ${r.network.rttMs ?? '?'} ms RTT` : null}
            testid="diag-row-network"
          />
          <Row
            icon={HardDrive}
            label="Storage quota"
            status={r.storage ? `${r.storage.usedMB} / ${r.storage.quotaMB} MB` : 'Unknown'}
            statusTone={r.storage ? 'info' : 'muted'}
            testid="diag-row-storage"
          />
          <Row
            icon={Monitor}
            label={`Screen ${r.screen?.width || '?'}×${r.screen?.height || '?'}`}
            status={r.screen?.touch ? 'Touchscreen' : 'Mouse/keyboard'}
            statusTone={r.screen?.touch ? 'info' : 'muted'}
            meta={`${r.screen?.pixelRatio || 1}× DPI${r.screen?.standalone ? ' · standalone PWA' : ''}`}
            testid="diag-row-screen"
          />
          <Row
            icon={LockIcon}
            label="Wake Lock (keep screen on)"
            status={r.wakeLockSupported ? 'Supported' : 'Unsupported'}
            statusTone={r.wakeLockSupported ? 'ok' : 'muted'}
            testid="diag-row-wakelock"
          />
          <Row
            icon={ShieldAlert}
            label="Secure context (HTTPS)"
            status={r.runtime.isHttps ? 'Yes' : 'No (HTTP)'}
            statusTone={r.runtime.isHttps ? 'ok' : 'error'}
            meta={!r.runtime.isHttps ? 'Most permission-gated APIs (camera, NFC, geo) need HTTPS.' : null}
            testid="diag-row-https"
          />
        </section>

        <p className="text-[10px] text-muted-foreground italic">
          Some entries (Web Serial / HID / USB / Bluetooth) only list devices you've previously paired in this browser profile.
          Click <strong>Pair</strong> to grant access to a new device — the browser will show its picker.
        </p>
      </DialogContent>
    </Dialog>
  );
}
