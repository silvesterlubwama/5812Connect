import React, { useEffect, useRef, useState } from 'react';
import { Html5Qrcode } from 'html5-qrcode';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Camera, Keyboard, X } from 'lucide-react';
import { Input } from './ui/input';

/**
 * BarcodeScanDialog — opens camera, scans CODE128/QR/etc.
 * onScan(value) is called with the decoded text; scanner auto-closes after successful scan.
 * Also offers a manual-entry fallback for keyboard-wedge scanners that type into fields.
 */
export default function BarcodeScanDialog({ open, onOpenChange, onScan, title = 'Scan barcode' }) {
  const scannerRef = useRef(null);
  const containerId = 'barcode-scanner-view';
  const [mode, setMode] = useState('camera');
  const [manualValue, setManualValue] = useState('');
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open || mode !== 'camera') return;
    let active = true;
    (async () => {
      try {
        setError(null);
        const el = document.getElementById(containerId);
        if (!el) return;
        const scanner = new Html5Qrcode(containerId, { verbose: false });
        scannerRef.current = scanner;
        const cameras = await Html5Qrcode.getCameras();
        if (!cameras || cameras.length === 0) throw new Error('No camera available');
        const cam = cameras.find(c => /back|rear|environment/i.test(c.label)) || cameras[0];
        await scanner.start(
          cam.id,
          { fps: 10, qrbox: { width: 260, height: 160 } },
          (decoded) => {
            if (!active) return;
            active = false;
            // Stop after first successful scan
            scanner.stop().then(() => scanner.clear()).catch(() => {});
            onScan(decoded);
            onOpenChange(false);
          },
          () => { /* ignore per-frame decode errors */ }
        );
      } catch (e) {
        setError(e?.message || 'Camera unavailable');
      }
    })();
    return () => {
      active = false;
      const s = scannerRef.current;
      if (s) {
        s.stop().then(() => s.clear()).catch(() => {});
        scannerRef.current = null;
      }
    };
  }, [open, mode, onScan, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle className="flex items-center gap-2">
          <Camera size={16} /> {title}
        </DialogTitle></DialogHeader>
        <div className="flex gap-2 justify-center pb-2">
          <Button size="sm" variant={mode === 'camera' ? 'default' : 'outline'} onClick={() => setMode('camera')} className="h-8 gap-1.5"><Camera size={13} /> Camera</Button>
          <Button size="sm" variant={mode === 'manual' ? 'default' : 'outline'} onClick={() => setMode('manual')} className="h-8 gap-1.5"><Keyboard size={13} /> Type / Keyboard wedge</Button>
        </div>
        {mode === 'camera' ? (
          <div>
            <div id={containerId} className="w-full rounded-lg overflow-hidden bg-black min-h-[220px] flex items-center justify-center" data-testid="barcode-scanner-view">
              {error && <p className="text-sm text-white p-4 text-center">{error}</p>}
            </div>
            <p className="text-[10px] text-muted-foreground mt-2 text-center">Point camera at a barcode. Auto-closes on first successful scan.</p>
          </div>
        ) : (
          <form onSubmit={(e) => {
            e.preventDefault();
            if (!manualValue.trim()) return;
            onScan(manualValue.trim());
            setManualValue('');
            onOpenChange(false);
          }} className="space-y-3">
            <Input
              autoFocus
              placeholder="Scan or type barcode, press Enter"
              value={manualValue}
              onChange={(e) => setManualValue(e.target.value)}
              className="font-mono text-center text-lg h-12"
              data-testid="manual-barcode-input"
            />
            <Button type="submit" className="w-full" disabled={!manualValue.trim()}>Submit</Button>
            <p className="text-[10px] text-muted-foreground text-center">USB / Bluetooth keyboard-wedge scanners will type here and auto-submit on Enter.</p>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
