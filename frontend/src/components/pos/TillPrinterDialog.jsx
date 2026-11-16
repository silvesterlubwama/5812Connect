import React, { useEffect, useState } from 'react';
import { Bluetooth, Loader2, Network, Printer, Usb, Wifi, X, Info } from 'lucide-react';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Switch } from '../ui/switch';
import { toast } from 'sonner';
import {
  capabilities, connectBluetooth, connectUsb, getTillConfig, isReady,
  openDrawer, paperFor, saveTillConfig, storePaper, testPrint, testPrintViaBrowser,
} from '../../utils/tillPrinter';
import { unpairRole } from '../../utils/deviceRoles';
import { ShopPrintHelper } from './ShopPrintHelper';

const CONNECTIONS = [
  { id: 'usb', label: 'USB cable', icon: Usb, blurb: 'Plugged into this computer' },
  { id: 'bluetooth', label: 'Bluetooth', icon: Bluetooth, blurb: 'Portable printer paired over Bluetooth' },
  { id: 'network', label: 'Network / Wi-Fi', icon: Network, blurb: "Printer's own address, via the shop helper" },
  { id: 'none', label: "This computer's printer", icon: Printer, blurb: 'Whatever is installed in Windows — can print silently' },
];

const BAUD_RATES = [9600, 19200, 38400, 57600, 115200];

export default function TillPrinterDialog({ open, onOpenChange, storeSettings = {} }) {
  const [cfg, setCfg] = useState(getTillConfig);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState('');
  const [lastFail, setLastFail] = useState('');
  const [showSilentHelp, setShowSilentHelp] = useState(false);
  const caps = capabilities();

  useEffect(() => { if (open) { setCfg(getTillConfig()); isReady().then(setReady); setLastFail(''); } }, [open]);

  const update = (patch) => { setCfg(saveTillConfig(patch)); isReady().then(setReady); };

  const handleConnect = async () => {
    setBusy('connect');
    const res = cfg.connection === 'bluetooth' ? await connectBluetooth() : await connectUsb();
    setBusy('');
    if (res.ok) { toast.success(`${res.name} connected`); setCfg(getTillConfig()); setReady(true); }
    else toast.error(res.reason || 'Could not connect to the printer');
  };

  const handleTest = async () => {
    setBusy('test');
    setLastFail('');
    if (cfg.connection === 'none') {
      testPrintViaBrowser(storeSettings);
      setBusy('');
      toast.success('Test receipt sent to the print window');
      return;
    }
    const r = await testPrint(storeSettings);
    setBusy('');
    if (r.printed) {
      toast.success(`Test receipt sent over ${r.transport} — check the printer`);
      // "Sent" only means the printer took the bytes. Nothing coming out after
      // that is almost always the wrong speed on a serial printer (iter421).
      if (cfg.connection === 'usb') {
        setLastFail('If nothing came out, the printer is listening at another speed — try the next one down the Speed list.');
      }
    } else {
      toast.error(r.reason || 'The printer did not take the job');
      setLastFail(r.reason || '');
    }
  };

  const handleDrawer = async () => {
    setBusy('drawer');
    const r = await openDrawer();
    setBusy('');
    if (!r.printed) toast.error(r.reason || 'Could not reach the drawer');
  };

  const handleForget = async () => {
    try { await unpairRole('receipt_printer'); } catch { /* nothing paired */ }
    update({ connection: 'none', bluetoothName: '' });
    toast.success('Printer forgotten on this till');
  };

  const needsPairing = cfg.connection === 'usb' || cfg.connection === 'bluetooth';
  const unsupported = (cfg.connection === 'usb' && !caps.usbSerial && !caps.usbRaw)
    || (cfg.connection === 'bluetooth' && !caps.bluetooth);
  const resolvedPaper = paperFor(cfg, storeSettings);
  const saved = storePaper(storeSettings);
  const sheetShop = saved === 'A4' || saved === 'A5';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="till-printer-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <Printer size={16} /> Till printer
            {ready
              ? <Badge className="bg-green-100 text-green-700 text-[10px]" data-testid="till-printer-ready">Ready</Badge>
              : <Badge variant="outline" className="text-[10px]" data-testid="till-printer-not-ready">Not set up</Badge>}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wide text-muted-foreground">How is it connected?</Label>
            <div className="grid grid-cols-2 gap-2 mt-2">
              {CONNECTIONS.map(c => {
                const Icon = c.icon;
                const active = cfg.connection === c.id;
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => { update({ connection: c.id }); setLastFail(''); }}
                    data-testid={`till-conn-${c.id}`}
                    className={`text-left p-3 rounded-lg border transition-colors ${active ? 'border-primary bg-primary/5' : 'border-border hover:bg-accent/40'}`}
                  >
                    <div className="flex items-center gap-2"><Icon size={14} /><span className="text-sm font-medium">{c.label}</span></div>
                    <p className="text-[11px] text-muted-foreground mt-0.5 leading-snug">{c.blurb}</p>
                  </button>
                );
              })}
            </div>
          </div>

          {unsupported && (
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-2.5" data-testid="till-unsupported-note">
              This device can't talk to that kind of printer — iPhones and iPads never can.
              Receipts will keep using the browser's Print window instead.
            </p>
          )}

          {cfg.connection === 'usb' && !unsupported && (
            <div className="space-y-1">
              <Label className="text-xs">Speed</Label>
              <Select value={String(cfg.baudRate || 9600)} onValueChange={v => update({ baudRate: Number(v) })}>
                <SelectTrigger data-testid="till-baud-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {BAUD_RATES.map(b => <SelectItem key={b} value={String(b)}>{b} baud{b === 9600 ? ' (most common)' : ''}</SelectItem>)}
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground">
                Only matters for printers on a serial/COM cable. If the test says it sent but no
                paper moves, this is nearly always why — work down the list.
              </p>
            </div>
          )}

          {cfg.connection === 'network' && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <div className="sm:col-span-2 space-y-1">
                <Label className="text-xs">Printer address</Label>
                <Input
                  value={cfg.network?.host || ''}
                  onChange={e => update({ network: { ...cfg.network, host: e.target.value.trim() } })}
                  placeholder="192.168.1.50"
                  data-testid="till-network-host"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Port</Label>
                <Input
                  value={cfg.network?.port ?? 9100}
                  onChange={e => update({ network: { ...cfg.network, port: e.target.value.replace(/\D/g, '') } })}
                  data-testid="till-network-port"
                />
              </div>
              <p className="sm:col-span-3 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-2" data-testid="till-network-warning">
                A printer with its own address sits on the shop's network, which the app server
                cannot see from the cloud. Set up the <strong>shop print helper</strong> below and
                receipts reach it anyway — otherwise use <strong>This computer's printer</strong>.
              </p>
            </div>
          )}

          {cfg.connection === 'network' && (
            <ShopPrintHelper locationId={storeSettings.location_id} />
          )}

          {cfg.connection === 'none' && (
            <div className="rounded-lg border border-border p-2.5 space-y-1.5" data-testid="till-silent-help">
              <p className="text-[11px] text-muted-foreground">
                Receipts go to whichever printer this computer prints to — including a Wi-Fi
                printer installed in Windows. Chrome shows its Print window each time unless
                it is started in silent mode.
              </p>
              <button type="button" onClick={() => setShowSilentHelp(v => !v)}
                className="text-[11px] text-primary hover:underline flex items-center gap-1"
                data-testid="till-silent-help-toggle">
                <Info size={11} /> {showSilentHelp ? 'Hide' : 'How do I stop the Print window appearing?'}
              </button>
              {showSilentHelp && (
                <ol className="text-[11px] text-muted-foreground list-decimal pl-4 space-y-1">
                  <li>Set the receipt printer as the <strong>default printer</strong> in Windows, with the right roll width in its own settings.</li>
                  <li>Right-click the Chrome shortcut on the till → <strong>Properties</strong>.</li>
                  <li>At the end of <strong>Target</strong>, after a space, add:
                    <code className="block bg-muted rounded px-1.5 py-0.5 mt-0.5 select-all">--kiosk-printing</code>
                  </li>
                  <li>Open 58:12 from that shortcut. Receipts then print straight away, no window.</li>
                  <li>Turn on <strong>Print each sale automatically</strong> in Store settings.</li>
                </ol>
              )}
            </div>
          )}

          {/* A kitchen printer is almost always a network box of its own. Leave
              it blank and tickets come off the counter roll instead (iter418). */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 rounded-lg border border-amber-200 dark:border-amber-900/40 p-2.5">
            <p className="sm:col-span-3 text-xs font-semibold">Kitchen printer (optional)</p>
            <div className="sm:col-span-2 space-y-1">
              <Label className="text-xs">Address</Label>
              <Input
                value={cfg.kitchenNetwork?.host || ''}
                onChange={e => update({ kitchenNetwork: { ...cfg.kitchenNetwork, host: e.target.value.trim() } })}
                placeholder="192.168.1.60"
                data-testid="till-kitchen-host"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Port</Label>
              <Input
                value={cfg.kitchenNetwork?.port ?? 9100}
                onChange={e => update({ kitchenNetwork: { ...cfg.kitchenNetwork, port: e.target.value.replace(/\D/g, '') } })}
                data-testid="till-kitchen-port"
              />
            </div>
            <p className="sm:col-span-3 text-[11px] text-muted-foreground">
              Kitchen tickets go here, sent by the server like any network printer. Leave it
              empty — or if this printer is off — and they come off the counter roll instead, so
              no order is ever lost.
            </p>
          </div>

          {needsPairing && !unsupported && (
            <Button onClick={handleConnect} disabled={busy === 'connect'} className="w-full gap-2" data-testid="till-connect-btn">
              {busy === 'connect' ? <Loader2 size={14} className="animate-spin" /> : <Wifi size={14} />}
              {cfg.bluetoothName && cfg.connection === 'bluetooth' ? `Reconnect ${cfg.bluetoothName}` : 'Choose the printer'}
            </Button>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Paper width</Label>
              <Select value={cfg.paper || 'auto'} onValueChange={v => update({ paper: v })}>
                <SelectTrigger data-testid="till-paper-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Follow the shop's setting</SelectItem>
                  <SelectItem value="80mm">80mm (48 characters)</SelectItem>
                  <SelectItem value="58mm">58mm (32 characters)</SelectItem>
                </SelectContent>
              </Select>
              {(cfg.paper || 'auto') === 'auto' && (
                sheetShop ? (
                  <p className="text-[11px] text-amber-700" data-testid="till-paper-resolved">
                    This shop is saved as {saved}, a full sheet. Slips sent straight to the printer
                    use {resolvedPaper} columns, but a receipt printed through Windows comes out as a
                    whole page — which is what squashes it on a roll. Set the shop to 80mm or 58mm in
                    Store settings, or pick the width here for this till only.
                  </p>
                ) : (
                  <p className="text-[11px] text-muted-foreground" data-testid="till-paper-resolved">
                    This shop is set to {resolvedPaper}.
                  </p>
                )
              )}
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Cash drawer</Label>
              <div className="flex items-center gap-2 h-9">
                <Switch
                  checked={cfg.openDrawerOnCash}
                  onCheckedChange={v => update({ openDrawerOnCash: v })}
                  data-testid="till-drawer-toggle"
                />
                <span className="text-xs text-muted-foreground">Open on cash sales</span>
              </div>
            </div>
          </div>

          {lastFail && (
            <p className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-2" data-testid="till-test-reason">
              {lastFail}
            </p>
          )}

          <div className="flex flex-wrap gap-2 pt-1">
            <Button variant="outline" size="sm" onClick={handleTest} disabled={busy === 'test'} className="gap-2" data-testid="till-test-btn">
              {busy === 'test' ? <Loader2 size={13} className="animate-spin" /> : <Printer size={13} />} Print test receipt
            </Button>
            <Button variant="outline" size="sm" onClick={handleDrawer} disabled={busy === 'drawer' || cfg.connection === 'none'} className="gap-2" data-testid="till-open-drawer-btn">
              Open drawer
            </Button>
            {cfg.connection !== 'none' && (
              <Button variant="ghost" size="sm" onClick={handleForget} className="gap-2 text-muted-foreground" data-testid="till-forget-btn">
                <X size={13} /> Forget printer
              </Button>
            )}
          </div>

          <p className="text-[11px] text-muted-foreground border-t border-border pt-3">
            Set up per till — each computer keeps its own printer. When it's ready, receipts go
            straight to the roll with no Print window; anything it can't reach falls back to the
            browser dialog so a sale is never stuck.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
