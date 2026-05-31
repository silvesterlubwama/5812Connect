import React, { useEffect, useState } from 'react';
import { Camera, ScanLine, ShieldAlert, Smartphone, CheckCircle2, X, Wifi } from 'lucide-react';
import { Button } from './ui/button';
import {
  detectPeripheralAvailability,
  getPermissionState,
  requestCameraAccess,
  requestNfcAccess,
  wasAsked,
  markAsked,
} from '../utils/peripheralPermissions';

/**
 * Banner that probes for cameras / NFC on mount and offers explicit "Enable …" buttons
 * when permission isn't yet granted. Used by the Security Checkpoint, Check-in Kiosk,
 * and POS — anywhere we need a camera or scanner.
 *
 * Props:
 *   - needs: array of capability ids to show. e.g. ['camera', 'nfc', 'scanner']
 *           'scanner' is informational (USB HID via keyboard always works) — we don't
 *           require permission for it; we just remind operators to connect one.
 *   - className: optional wrapper class.
 *   - testid: optional data-testid.
 *   - onCameraGranted: optional callback fired when camera permission flips to granted.
 *   - onNfcGranted: optional callback (Chrome-Android only).
 *   - context: optional label ('Security Checkpoint' | 'Check-in Kiosk' | 'POS') used
 *              in user-facing copy.
 */
export default function PeripheralPermissionBanner({
  needs = ['camera'],
  className = '',
  testid = 'peripheral-permission-banner',
  onCameraGranted,
  onNfcGranted,
  context = 'this kiosk',
}) {
  const [avail, setAvail] = useState(null);
  const [cameraPerm, setCameraPerm] = useState('unknown');
  const [nfcPerm, setNfcPerm] = useState('unknown');
  const [busy, setBusy] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  const needCamera = needs.includes('camera');
  const needNfc = needs.includes('nfc');
  const needScanner = needs.includes('scanner');

  // Silent probe on mount
  useEffect(() => {
    let alive = true;
    (async () => {
      const a = await detectPeripheralAvailability();
      if (!alive) return;
      setAvail(a);
      if (needCamera) setCameraPerm(await getPermissionState('camera'));
      if (needNfc) setNfcPerm(a.nfcSupported ? await getPermissionState('nfc').catch(() => 'unknown') : 'unsupported');
    })();
    return () => { alive = false; };
  }, [needCamera, needNfc]);

  // Listen for permission changes (Chrome supports this — Firefox doesn't yet)
  useEffect(() => {
    if (!needCamera || typeof navigator === 'undefined' || !navigator.permissions?.query) return;
    let status;
    (async () => {
      try {
        status = await navigator.permissions.query({ name: 'camera' });
        status.onchange = () => setCameraPerm(status.state);
      } catch { /* ignore */ }
    })();
    return () => { if (status) status.onchange = null; };
  }, [needCamera]);

  const enableCamera = async () => {
    setBusy(true);
    try {
      const r = await requestCameraAccess();
      setCameraPerm(r.state);
      if (r.state === 'granted') onCameraGranted?.();
    } finally {
      setBusy(false);
    }
  };

  const enableNfc = async () => {
    setBusy(true);
    try {
      const r = await requestNfcAccess();
      setNfcPerm(r.state);
      if (r.state === 'granted') onNfcGranted?.(r.reader);
    } finally {
      setBusy(false);
    }
  };

  if (dismissed || !avail) return null;

  // Build the items we still need to surface
  const items = [];
  if (needCamera) {
    const cams = avail.cameras.length;
    if (cams === 0) {
      items.push({ key: 'no-camera', icon: Camera, tone: 'warn', text: `No camera detected. Connect a webcam or use a phone with a camera to scan QR codes.` });
    } else if (cameraPerm === 'prompt' || (cameraPerm === 'unknown' && !wasAsked('camera'))) {
      items.push({
        key: 'camera-ask', icon: Camera, tone: 'info',
        text: `${cams} camera${cams === 1 ? '' : 's'} detected — ${context} needs permission to scan QR codes.`,
        action: { label: busy ? 'Asking…' : 'Enable camera', onClick: enableCamera, testid: 'enable-camera-btn' },
      });
    } else if (cameraPerm === 'denied') {
      items.push({
        key: 'camera-denied', icon: ShieldAlert, tone: 'error',
        text: 'Camera access was blocked. Click the camera icon in the address bar to re-allow, then refresh.',
      });
    }
  }
  if (needNfc) {
    if (!avail.nfcSupported) {
      items.push({
        key: 'no-nfc', icon: Smartphone, tone: 'subtle',
        text: 'NFC tap reading only works on Chrome for Android. Use QR scan or barcode reader on this device.',
      });
    } else if (nfcPerm === 'prompt' || (nfcPerm === 'unknown' && !wasAsked('nfc'))) {
      items.push({
        key: 'nfc-ask', icon: Wifi, tone: 'info',
        text: `${context} can read NFC badges on this device — tap to enable.`,
        action: { label: busy ? 'Asking…' : 'Enable NFC reader', onClick: enableNfc, testid: 'enable-nfc-btn' },
      });
    } else if (nfcPerm === 'denied') {
      items.push({
        key: 'nfc-denied', icon: ShieldAlert, tone: 'error',
        text: 'NFC reading was blocked. Adjust site permissions in the browser to re-allow.',
      });
    }
  }
  if (needScanner && !avail.cameras.length && !avail.serialSupported && !avail.hidSupported) {
    items.push({
      key: 'no-scanner', icon: ScanLine, tone: 'subtle',
      text: 'No scanner detected. Connect a USB barcode scanner (keyboard-emulating) or use the manual entry field below.',
    });
  }

  if (items.length === 0) {
    // Everything we need is ready — show a brief, dismissible confirmation only the first time.
    if (wasAsked('all-ready') || !needCamera) return null;
    markAsked('all-ready');
    return (
      <div className={`flex items-center gap-2 p-2.5 rounded-lg bg-emerald-50 border border-emerald-200 dark:bg-emerald-950/20 dark:border-emerald-900/40 text-xs text-emerald-800 dark:text-emerald-300 ${className}`} data-testid={`${testid}-ok`}>
        <CheckCircle2 size={14} /> Peripherals ready.
        <button className="ml-auto" onClick={() => setDismissed(true)}><X size={12} /></button>
      </div>
    );
  }

  const toneClasses = {
    info:    'bg-blue-50 border-blue-200 text-blue-900 dark:bg-blue-950/30 dark:border-blue-900/40 dark:text-blue-200',
    warn:    'bg-amber-50 border-amber-200 text-amber-900 dark:bg-amber-950/30 dark:border-amber-900/40 dark:text-amber-200',
    error:   'bg-rose-50 border-rose-200 text-rose-900 dark:bg-rose-950/30 dark:border-rose-900/40 dark:text-rose-200',
    subtle:  'bg-slate-50 border-slate-200 text-slate-700 dark:bg-slate-900/40 dark:border-slate-700 dark:text-slate-300',
  };

  return (
    <div className={`space-y-1.5 ${className}`} data-testid={testid}>
      {items.map(it => {
        const Icon = it.icon;
        return (
          <div
            key={it.key}
            className={`flex items-start gap-2 p-2.5 rounded-lg border text-xs ${toneClasses[it.tone] || toneClasses.subtle}`}
            data-testid={`${testid}-${it.key}`}
          >
            <Icon size={14} className="shrink-0 mt-0.5" />
            <span className="flex-1">{it.text}</span>
            {it.action && (
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-[11px] shrink-0"
                disabled={busy}
                onClick={it.action.onClick}
                data-testid={it.action.testid}
              >
                {it.action.label}
              </Button>
            )}
          </div>
        );
      })}
    </div>
  );
}
