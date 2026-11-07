import React, { useEffect, useState } from 'react';
import { Bluetooth, Loader2, Network, Printer, Usb, Wifi, X } from 'lucide-react';
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
  openDrawer, saveTillConfig, testPrint,
} from '../../utils/tillPrinter';
import { unpairRole } from '../../utils/deviceRoles';

const CONNECTIONS = [
  { id: 'usb', label: 'USB cable', icon: Usb, blurb: 'Plugged into this computer' },
  { id: 'bluetooth', label: 'Bluetooth', icon: Bluetooth, blurb: 'Portable printer paired over Bluetooth' },
  { id: 'network', label: 'Network / Wi-Fi', icon: Network, blurb: 'Printer has its own address on your network' },
  { id: 'none', label: 'Browser print dialog', icon: Printer, blurb: 'The usual Print window — works everywhere' },
];

export default function TillPrinterDialog({ open, onOpenChange }) {
  const [cfg, setCfg] = useState(getTillConfig);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState('');
  const caps = capabilities();

  useEffect(() => { if (open) { setCfg(getTillConfig()); isReady().then(setReady); } }, [open]);

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
    const r = await testPrint();
    setBusy('');
    if (r.printed) toast.success('Test receipt sent — check the printer');
    else toast.error(r.reason || 'The printer did not take the job');
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
                    onClick={() => update({ connection: c.id })}
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

          {cfg.connection === 'network' && (
            <div className="grid grid-cols-3 gap-2">
              <div className="col-span-2 space-y-1">
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
              <p className="col-span-3 text-[11px] text-muted-foreground">
                Printed from the server, so the printer must be on the same network as it.
              </p>
            </div>
          )}

          {needsPairing && !unsupported && (
            <Button onClick={handleConnect} disabled={busy === 'connect'} className="w-full gap-2" data-testid="till-connect-btn">
              {busy === 'connect' ? <Loader2 size={14} className="animate-spin" /> : <Wifi size={14} />}
              {cfg.bluetoothName && cfg.connection === 'bluetooth' ? `Reconnect ${cfg.bluetoothName}` : 'Choose the printer'}
            </Button>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Paper width</Label>
              <Select value={cfg.paper} onValueChange={v => update({ paper: v })}>
                <SelectTrigger data-testid="till-paper-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="80mm">80mm (48 characters)</SelectItem>
                  <SelectItem value="58mm">58mm (32 characters)</SelectItem>
                </SelectContent>
              </Select>
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

          <div className="flex flex-wrap gap-2 pt-1">
            <Button variant="outline" size="sm" onClick={handleTest} disabled={busy === 'test' || cfg.connection === 'none'} className="gap-2" data-testid="till-test-btn">
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
