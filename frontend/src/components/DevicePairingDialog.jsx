/**
 * DevicePairingDialog — admin UI for assigning paired USB / Serial / HID
 * peripherals to functional roles (receipt printer, NFC reader, scale, …).
 *
 * Workflow:
 *   1. Admin opens the dialog (from /admin or DeviceDiagnostics).
 *   2. For each role, sees current pairing status + a Pair button per
 *      supported transport (serial / hid / usb).
 *   3. Clicking Pair fires the browser's native picker. The selected device
 *      is persisted in localStorage keyed by role.
 *   4. After pairing, the green "available" badge confirms the device is
 *      actually present (browser still remembers the permission across
 *      reloads, so this works on the next page load too).
 *
 * The actual transport protocol (ESC/POS for receipts, NDEF for NFC, ZPL for
 * labels, etc.) is the consumer's responsibility — this dialog only handles
 * the device <-> role assignment.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Usb, Cable, CircuitBoard, Trash2, RefreshCw, CheckCircle2, AlertTriangle } from 'lucide-react';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { toast } from 'sonner';
import {
  DEVICE_ROLES,
  listRoles,
  pairDeviceForRole,
  unpairRole,
  probeAllRoles,
} from '../utils/deviceRoles';

const TRANSPORT_ICON = { serial: Cable, hid: CircuitBoard, usb: Usb };
const TRANSPORT_LABEL = { serial: 'Serial', hid: 'HID', usb: 'USB' };

function transportSupported(t) {
  if (typeof navigator === 'undefined') return false;
  if (t === 'serial') return 'serial' in navigator;
  if (t === 'hid') return 'hid' in navigator;
  if (t === 'usb') return 'usb' in navigator;
  return false;
}

export default function DevicePairingDialog({ trigger }) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState({});
  const [busy, setBusy] = useState(null);  // role currently being paired

  const refresh = useCallback(async () => {
    setStatus(await probeAllRoles());
  }, []);

  useEffect(() => { if (open) refresh(); }, [open, refresh]);

  const pair = async (role, transport) => {
    setBusy(role);
    try {
      const rec = await pairDeviceForRole(role, transport);
      toast.success(`Paired ${DEVICE_ROLES[role].label}${rec.product_name ? ` — ${rec.product_name}` : ''}`);
      await refresh();
    } catch (e) {
      const msg = String(e?.message || e);
      // The browser throws NotFoundError when the user cancels the picker.
      if (/cancel|no device/i.test(msg)) {
        toast.info('Pairing cancelled');
      } else {
        toast.error(msg);
      }
    } finally { setBusy(null); }
  };

  const unpair = (role) => {
    if (!window.confirm(`Unpair ${DEVICE_ROLES[role].label}? Consumers will fall back to no-device mode.`)) return;
    unpairRole(role);
    toast.success('Unpaired');
    refresh();
  };

  const roles = listRoles();
  const supportedTransports = ['serial', 'hid', 'usb'].filter(transportSupported);

  return (
    <>
      {trigger ? (
        React.cloneElement(trigger, { onClick: () => setOpen(true), 'data-testid': 'device-pairing-open' })
      ) : (
        <Card className="rounded-xl mt-4 cursor-pointer hover:border-primary/40" onClick={() => setOpen(true)} data-testid="device-pairing-card">
          <CardContent className="p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Usb size={18} className="text-primary" />
              <div>
                <p className="font-medium text-sm">USB Devices &amp; Roles</p>
                <p className="text-xs text-muted-foreground">Pair a printer / NFC reader / scanner / scale once and tag what it&apos;s for. Consumers automatically pick the right device.</p>
              </div>
            </div>
            <Button size="sm" variant="outline">Manage</Button>
          </CardContent>
        </Card>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto" data-testid="device-pairing-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Usb size={16} /> USB Devices &amp; Roles</DialogTitle>
            <DialogDescription className="text-xs">
              Pair each peripheral once and tell the app what it&apos;s for. Pairings survive page reloads as long as the device stays plugged in and the browser remembers the permission.
            </DialogDescription>
          </DialogHeader>

          {supportedTransports.length === 0 ? (
            <div className="my-4 p-3 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-900 flex items-start gap-2">
              <AlertTriangle size={14} className="shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">Your browser doesn&apos;t expose Web Serial / HID / USB.</p>
                <p className="opacity-80">Use Chrome / Edge / Opera on a desktop OS. Safari does not yet support these APIs. Mobile browsers expose only NFC (Android Chrome) and the camera.</p>
              </div>
            </div>
          ) : (
            <div className="mb-3 text-[11px] text-muted-foreground flex items-center gap-2">
              <span>Available transports:</span>
              {supportedTransports.map(t => (
                <Badge key={t} variant="outline" className="text-[10px]">{TRANSPORT_LABEL[t]}</Badge>
              ))}
            </div>
          )}

          <div className="flex justify-end mb-2">
            <Button size="sm" variant="ghost" onClick={refresh} data-testid="device-pairing-refresh">
              <RefreshCw size={12} className="mr-1" /> Refresh
            </Button>
          </div>

          <div className="space-y-2.5">
            {roles.map(r => {
              const st = status[r.key] || { paired: false, available: false };
              const pairing = st.pairing;
              return (
                <div key={r.key} className="p-3 rounded-lg border" data-testid={`device-role-${r.key}`}>
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="font-medium text-sm">{r.label}</p>
                        {st.paired && st.available && <Badge className="bg-emerald-100 text-emerald-700 text-[10px]" data-testid={`device-role-${r.key}-available`}><CheckCircle2 size={10} className="mr-0.5" />Available</Badge>}
                        {st.paired && !st.available && <Badge className="bg-amber-100 text-amber-700 text-[10px]" data-testid={`device-role-${r.key}-unplugged`}>Paired (unplugged)</Badge>}
                        {!st.paired && <Badge variant="outline" className="text-[10px]" data-testid={`device-role-${r.key}-unpaired`}>Not paired</Badge>}
                      </div>
                      <p className="text-[11px] text-muted-foreground mt-0.5">{r.description}</p>
                      {pairing && (
                        <p className="text-[10px] text-muted-foreground mt-1 font-mono">
                          {TRANSPORT_LABEL[pairing.transport]} · {pairing.product_name || '(no name)'}
                          {pairing.vendor_id != null && ` · v=${pairing.vendor_id} p=${pairing.product_id}`}
                          {pairing.serial_number && ` · sn=${pairing.serial_number}`}
                        </p>
                      )}
                      <p className="text-[10px] text-muted-foreground mt-1 italic">{r.hint}</p>
                    </div>
                    <div className="flex flex-col gap-1.5 items-end">
                      <div className="flex gap-1.5 flex-wrap">
                        {r.transports.map(t => {
                          if (!transportSupported(t)) return null;
                          const Icon = TRANSPORT_ICON[t];
                          return (
                            <Button
                              key={t}
                              size="sm"
                              variant="outline"
                              className="h-7 text-[11px]"
                              onClick={() => pair(r.key, t)}
                              disabled={busy === r.key}
                              data-testid={`device-pair-${r.key}-${t}`}
                            >
                              <Icon size={11} className="mr-1" />
                              Pair {TRANSPORT_LABEL[t]}
                            </Button>
                          );
                        })}
                      </div>
                      {st.paired && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-6 text-[11px] text-destructive"
                          onClick={() => unpair(r.key)}
                          data-testid={`device-unpair-${r.key}`}
                        >
                          <Trash2 size={10} className="mr-1" /> Unpair
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-3 p-2.5 rounded-lg bg-muted/40 text-[11px] text-muted-foreground">
            <p><strong>How it works:</strong> Pairing uses the browser&apos;s built-in permission picker. We persist only the device&apos;s vendor/product IDs + name in localStorage. Consumers call <code>getDeviceForRole(&apos;receipt_printer&apos;)</code> and get back a live device handle — no re-pairing needed across reloads.</p>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
