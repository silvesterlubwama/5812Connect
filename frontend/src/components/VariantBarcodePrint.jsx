import React, { useState, useEffect, useRef } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Input } from './ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Printer, X } from 'lucide-react';
import JsBarcode from 'jsbarcode';

const LAYOUTS = [
  { value: 'grid_4x6', label: '4 × 6 grid (24 per page, Avery-style)', cols: 4, rows: 6 },
  { value: 'grid_3x8', label: '3 × 8 grid (24 per page)', cols: 3, rows: 8 },
  { value: 'grid_2x5', label: '2 × 5 grid (10 per page, larger)', cols: 2, rows: 5 },
  { value: 'single', label: 'One per page (full size)', cols: 1, rows: 1 },
];

function BarcodeCanvas({ value, displayValue = true, height = 60, width = 1.8 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current && value) {
      try {
        JsBarcode(ref.current, String(value), {
          format: 'CODE128',
          width,
          height,
          displayValue,
          fontSize: 12,
          margin: 4,
        });
      } catch (e) {
        // Fallback: render as plain text
        const ctx = ref.current.getContext('2d');
        ctx.font = '12px monospace';
        ctx.fillText(String(value), 4, 20);
      }
    }
  }, [value, displayValue, height, width]);
  return <canvas ref={ref} />;
}

export default function VariantBarcodePrint({ open, onOpenChange, product, currency = 'UGX' }) {
  const [layout, setLayout] = useState('grid_4x6');
  const [copies, setCopies] = useState(1);
  const [showPrice, setShowPrice] = useState(true);
  const [showName, setShowName] = useState(true);

  const variants = product?.variants || [];
  const cfg = LAYOUTS.find(l => l.value === layout) || LAYOUTS[0];
  const perPage = cfg.cols * cfg.rows;

  // Build the print list (with copies)
  const printList = [];
  variants.forEach(v => {
    for (let i = 0; i < copies; i++) {
      printList.push(v);
    }
  });

  // Fill pages
  const pages = [];
  for (let i = 0; i < printList.length; i += perPage) {
    pages.push(printList.slice(i, i + perPage));
  }

  const handlePrint = () => {
    // Trigger print on the preview area only
    const printContents = document.getElementById('variant-barcode-print-area')?.innerHTML;
    if (!printContents) return;
    const w = window.open('', '_blank', 'width=900,height=700');
    w.document.write(`
      <html>
        <head>
          <title>Variant Barcodes - ${product?.name || 'Product'}</title>
          <style>
            @page { size: A4; margin: 10mm; }
            body { font-family: Arial, sans-serif; margin: 0; padding: 0; }
            .barcode-page { page-break-after: always; display: grid; gap: 4mm; padding: 4mm; }
            .barcode-page:last-child { page-break-after: auto; }
            .barcode-cell { border: 1px dashed #ccc; padding: 6px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; overflow: hidden; }
            .barcode-cell canvas { max-width: 100%; }
            .barcode-name { font-size: 11px; font-weight: 600; margin-bottom: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
            .barcode-price { font-size: 10px; color: #555; margin-top: 2px; }
            @media print {
              .barcode-cell { border: none; }
            }
          </style>
        </head>
        <body>${printContents}</body>
      </html>
    `);
    w.document.close();
    setTimeout(() => { w.focus(); w.print(); }, 400);
  };

  if (!product) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Printer size={16} /> Print Variant Barcodes — {product.name}
          </DialogTitle>
        </DialogHeader>

        <div className="flex gap-4 items-end border-b pb-3">
          <div className="space-y-1 flex-1">
            <Label className="text-xs">Layout</Label>
            <Select value={layout} onValueChange={setLayout}>
              <SelectTrigger data-testid="barcode-layout-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                {LAYOUTS.map(l => <SelectItem key={l.value} value={l.value}>{l.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1 w-24">
            <Label className="text-xs">Copies / variant</Label>
            <Input type="number" min={1} max={100} value={copies}
              onChange={e => setCopies(Math.max(1, Math.min(100, parseInt(e.target.value) || 1)))}
              data-testid="barcode-copies-input" />
          </div>
          <div className="flex items-center gap-3 text-xs">
            <label className="flex items-center gap-1 cursor-pointer"><input type="checkbox" checked={showName} onChange={e => setShowName(e.target.checked)} /> Name</label>
            <label className="flex items-center gap-1 cursor-pointer"><input type="checkbox" checked={showPrice} onChange={e => setShowPrice(e.target.checked)} /> Price</label>
          </div>
          <Button onClick={handlePrint} className="gap-1.5" disabled={pages.length === 0} data-testid="print-barcodes-btn">
            <Printer size={14} /> Print ({pages.length} page{pages.length === 1 ? '' : 's'})
          </Button>
        </div>

        {variants.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground py-8">
            No variants to print. Add variants to the product first.
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto bg-muted/30 p-2 rounded">
            <div id="variant-barcode-print-area">
              {pages.map((pageItems, pi) => (
                <div
                  key={pi}
                  className="barcode-page bg-white mx-auto mb-4 shadow-sm"
                  style={{
                    width: '210mm',
                    minHeight: '297mm',
                    gridTemplateColumns: `repeat(${cfg.cols}, 1fr)`,
                    gridTemplateRows: `repeat(${cfg.rows}, 1fr)`,
                    display: 'grid',
                    gap: '4mm',
                    padding: '4mm',
                    boxSizing: 'border-box',
                  }}
                >
                  {pageItems.map((v, vi) => (
                    <div
                      key={`${pi}-${vi}-${v.id || v.barcode}`}
                      className="barcode-cell"
                      style={{ border: '1px dashed #ccc', padding: '6px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', overflow: 'hidden' }}
                    >
                      {showName && <div className="barcode-name" style={{ fontSize: '11px', fontWeight: 600, marginBottom: '2px', maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{product.name}{v.name ? ` — ${v.name}` : ''}</div>}
                      <BarcodeCanvas
                        value={v.barcode || v.id || v.name}
                        height={cfg.value === 'single' ? 120 : 50}
                        width={cfg.value === 'single' ? 3 : 1.5}
                      />
                      {showPrice && v.price != null && <div className="barcode-price" style={{ fontSize: '10px', color: '#555', marginTop: '2px' }}>{currency} {Number(v.price || 0).toLocaleString()}</div>}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
