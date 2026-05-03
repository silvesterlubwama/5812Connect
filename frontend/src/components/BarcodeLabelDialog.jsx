import React, { useEffect, useRef } from 'react';
import JsBarcode from 'jsbarcode';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Printer } from 'lucide-react';

function BarcodeCanvas({ value, height = 80, width = 2 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current && value) {
      try {
        JsBarcode(ref.current, String(value), {
          format: 'CODE128', width, height, displayValue: true, fontSize: 11, margin: 4,
        });
      } catch (e) {
        const ctx = ref.current.getContext('2d');
        ctx.font = '12px monospace';
        ctx.fillText(String(value), 4, 20);
      }
    }
  }, [value, height, width]);
  return <canvas ref={ref} />;
}

/**
 * BarcodeLabelDialog — printable resource label with name, serial, barcode, location.
 * Optimized for small thermal labels (54mm x 30mm) but can also print on A4 grid.
 */
export default function BarcodeLabelDialog({ resource, open, onOpenChange }) {
  const handlePrint = () => {
    const area = document.getElementById('barcode-print-area')?.innerHTML;
    if (!area) return;
    const w = window.open('', '_blank', 'width=400,height=400');
    w.document.write(`
      <html><head><title>Label ${resource?.serial_number || ''}</title>
        <style>
          @page { size: 60mm 30mm; margin: 0; }
          body { margin: 0; padding: 2mm; font-family: 'Arial', sans-serif; }
          .label { width: 56mm; height: 26mm; padding: 1mm; box-sizing: border-box; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1mm; }
          .label canvas { max-width: 56mm; }
          .name { font-size: 8px; font-weight: 600; text-align: center; max-width: 56mm; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
          .loc { font-size: 6px; color: #666; }
        </style>
      </head><body>${area}</body></html>
    `);
    w.document.close();
    setTimeout(() => { w.focus(); w.print(); }, 400);
  };

  if (!resource) return null;
  const code = resource.serial_number || resource.barcode || resource.id;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle className="flex items-center gap-2">
          <Printer size={16} /> Barcode Label — {resource.name}
        </DialogTitle></DialogHeader>
        <div id="barcode-print-area" className="bg-white">
          <div className="label" style={{ width: '56mm', minHeight: '30mm', padding: '2mm', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '2mm', border: '1px dashed #ccc', margin: '0 auto' }}>
            <div className="name" style={{ fontSize: 9, fontWeight: 600, textAlign: 'center', maxWidth: '56mm' }}>{resource.name}</div>
            <BarcodeCanvas value={code} height={50} width={1.6} />
            <div className="loc" style={{ fontSize: 7, color: '#666' }}>58:12 Global · Property of {resource.location_name || resource.location_id || ''}</div>
          </div>
        </div>
        <div className="flex gap-2 pt-3 border-t border-border">
          <Button onClick={handlePrint} className="flex-1 gap-1.5" data-testid="print-barcode-label-btn">
            <Printer size={14} /> Print Label
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
