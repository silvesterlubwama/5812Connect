import React, { useEffect, useRef } from 'react';
import JsBarcode from 'jsbarcode';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Printer } from 'lucide-react';
import { escapeHtml as e } from '../utils/htmlEscape';

function BarcodeCanvas({ value, height = 50, width = 1.4, fontSize = 9 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current && value) {
      try {
        JsBarcode(ref.current, String(value), {
          format: 'CODE128', width, height, displayValue: true, fontSize,
          margin: 2, textMargin: 1, font: 'monospace', textAlign: 'center',
        });
      } catch (e) {
        const ctx = ref.current.getContext('2d');
        ctx.font = '10px monospace';
        ctx.fillText(String(value), 4, 14);
      }
    }
  }, [value, height, width, fontSize]);
  return <canvas ref={ref} style={{ display: 'block', maxWidth: '100%' }} />;
}

/**
 * BarcodeLabelDialog — printable resource label.
 * Default size 70mm x 35mm (fits typical thermal label printers + lets longer 5812-* serials fit).
 * Auto-shrinks bar width based on serial length to ensure full barcode prints.
 */
export default function BarcodeLabelDialog({ resource, open, onOpenChange }) {
  if (!resource) return null;
  const code = resource.serial_number || resource.barcode || resource.id;
  // Auto-tune barcode width for the serial length so it fits 70mm
  const len = (code || '').length;
  const barWidth = len > 22 ? 1.0 : len > 18 ? 1.2 : len > 14 ? 1.4 : 1.6;

  const handlePrint = () => {
    const w = window.open('', '_blank', 'width=400,height=400');
    // Render an isolated print page — generate barcode SVG inline so it always shows
    w.document.write(`
      <html><head><title>Label ${e(code)}</title>
        <script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.12.3/dist/JsBarcode.all.min.js"></script>
        <style>
          @page { size: 70mm 35mm; margin: 0; }
          html, body { margin: 0; padding: 0; }
          body { font-family: 'Arial', sans-serif; }
          .label {
            width: 66mm; height: 31mm;
            margin: 2mm; padding: 1.5mm;
            box-sizing: border-box;
            display: flex; flex-direction: column; align-items: center; justify-content: space-between;
          }
          .label .name { font-size: 8px; font-weight: 700; text-align: center; max-width: 66mm; line-height: 1.1; overflow: hidden; }
          .label svg { width: 64mm; height: 16mm; display: block; }
          .label .loc { font-size: 6px; color: #444; text-align: center; line-height: 1.1; }
        </style>
      </head><body>
        <div class="label">
          <div class="name">${e(resource.name || '')}</div>
          <svg id="bc"></svg>
          <div class="loc">58:12 Global · ${e(resource.location_name || '')}</div>
        </div>
        <script>
          try {
            JsBarcode("#bc", ${JSON.stringify(String(code || ''))}, {
              format: "CODE128",
              width: ${barWidth},
              height: 50,
              displayValue: true,
              fontSize: 8,
              textMargin: 1,
              margin: 0,
              font: "monospace"
            });
            setTimeout(() => { window.focus(); window.print(); }, 300);
          } catch (e) {
            document.body.innerHTML += '<p style="color:red">Barcode error: ' + (e && e.message ? e.message : '') + '</p>';
          }
        </script>
      </body></html>
    `);
    w.document.close();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle className="flex items-center gap-2">
          <Printer size={16} /> Barcode Label — {resource.name}
        </DialogTitle></DialogHeader>
        <div className="bg-white border border-dashed border-border rounded-md p-3 flex flex-col items-center justify-center gap-2 min-h-[160px]" data-testid="barcode-label-preview">
          <p className="text-[11px] font-bold text-center max-w-[66mm] leading-tight">{resource.name}</p>
          <BarcodeCanvas value={code} height={48} width={barWidth} fontSize={9} />
          <p className="text-[9px] text-muted-foreground text-center">58:12 Global · {resource.location_name || resource.location_id || ''}</p>
        </div>
        <p className="text-[10px] text-muted-foreground text-center -mt-1">
          {len} chars · auto bar width <span className="font-mono">{barWidth}</span> · prints on 70mm × 35mm thermal label
        </p>
        <div className="flex gap-2 pt-2 border-t border-border">
          <Button onClick={handlePrint} className="flex-1 gap-1.5" data-testid="print-barcode-label-btn">
            <Printer size={14} /> Print Label
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
