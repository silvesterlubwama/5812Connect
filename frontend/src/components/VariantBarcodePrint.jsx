import React, { useEffect, useRef, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Input } from './ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Printer } from 'lucide-react';
import JsBarcode from 'jsbarcode';
import { escapeHtml as e } from '../utils/htmlEscape';

const LAYOUTS = [
  { value: 'grid_4x6', label: '4 × 6 grid (24/page, Avery-style)', cols: 4, rows: 6 },
  { value: 'grid_3x8', label: '3 × 8 grid (24/page)', cols: 3, rows: 8 },
  { value: 'grid_2x5', label: '2 × 5 grid (10/page)', cols: 2, rows: 5 },
  { value: 'single', label: 'One per page (large)', cols: 1, rows: 1 },
];

function BarcodeCanvas({ value, height = 50, width = 1.5 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current && value) {
      try {
        JsBarcode(ref.current, String(value), {
          format: 'CODE128', width, height, displayValue: true, fontSize: 10, margin: 2, font: 'monospace',
        });
      } catch (e) {
        const ctx = ref.current.getContext('2d');
        ctx.font = '11px monospace';
        ctx.fillText(String(value), 4, 18);
      }
    }
  }, [value, height, width]);
  return <canvas ref={ref} style={{ display: 'block', maxWidth: '100%' }} />;
}

export default function VariantBarcodePrint({ open, onOpenChange, product, currency = 'UGX' }) {
  const [layout, setLayout] = useState('grid_4x6');
  const [copies, setCopies] = useState(1);
  const [showPrice, setShowPrice] = useState(true);
  const [showName, setShowName] = useState(true);

  const variants = product?.variants || [];
  const cfg = LAYOUTS.find(l => l.value === layout) || LAYOUTS[0];
  const perPage = cfg.cols * cfg.rows;

  // Build print list with copies
  const printList = [];
  variants.forEach(v => { for (let i = 0; i < copies; i++) printList.push(v); });
  const pages = [];
  for (let i = 0; i < printList.length; i += perPage) pages.push(printList.slice(i, i + perPage));

  // Auto-tune barcode width based on max code length
  const maxLen = variants.reduce((m, v) => Math.max(m, (v.barcode || v.id || v.name || '').length), 10);
  const barWidth = cfg.value === 'single' ? 2.4 : maxLen > 22 ? 0.9 : maxLen > 18 ? 1.1 : 1.4;

  const handlePrint = () => {
    if (variants.length === 0) return;
    const w = window.open('', '_blank', 'width=900,height=700');
    // Build the page HTML — barcodes are regenerated INLINE in the new window
    const cellsHtml = pages.map((pageItems, pi) => {
      const cellsRows = pageItems.map((v, vi) => {
        const code = String(v.barcode || v.id || v.name || '');
        const safeName = ((product?.name || '') + (v.name ? ` — ${v.name}` : '')).replace(/[<>&]/g, '');
        const priceStr = showPrice && v.price != null ? `${currency} ${Number(v.price || 0).toLocaleString()}` : '';
        return `
          <div class="cell">
            ${showName ? `<div class="name">${safeName}</div>` : ''}
            <svg class="bc" data-code="${code.replace(/"/g, '&quot;')}"></svg>
            ${priceStr ? `<div class="price">${priceStr}</div>` : ''}
          </div>
        `;
      }).join('');
      return `<div class="page" style="grid-template-columns: repeat(${cfg.cols}, 1fr); grid-template-rows: repeat(${cfg.rows}, 1fr);">${cellsRows}</div>`;
    }).join('');

    w.document.write(`
      <html><head><title>${product?.name || 'Variant Barcodes'}</title>
        <script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.12.3/dist/JsBarcode.all.min.js"></script>
        <style>
          @page { size: A4; margin: 8mm; }
          html, body { margin: 0; padding: 0; font-family: Arial, sans-serif; }
          .page { display: grid; gap: 4mm; padding: 4mm; box-sizing: border-box; page-break-after: always; width: 100%; min-height: 270mm; }
          .page:last-child { page-break-after: auto; }
          .cell { border: 1px dashed #ccc; padding: 4px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; overflow: hidden; box-sizing: border-box; }
          .cell .name { font-size: 10px; font-weight: 600; line-height: 1.1; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-bottom: 2px; }
          .cell .bc { width: 90%; height: ${cfg.value === 'single' ? '70mm' : '18mm'}; display: block; }
          .cell .price { font-size: 9px; color: #555; margin-top: 2px; }
          @media print { .cell { border: none; } }
        </style>
      </head><body>${cellsHtml}
      <script>
        window.addEventListener('load', () => {
          document.querySelectorAll('svg.bc').forEach(svg => {
            try {
              JsBarcode(svg, svg.getAttribute('data-code'), {
                format: 'CODE128',
                width: ${barWidth},
                height: ${cfg.value === 'single' ? 140 : 50},
                displayValue: true,
                fontSize: ${cfg.value === 'single' ? 14 : 9},
                font: 'monospace',
                textMargin: 1,
                margin: 0,
              });
            } catch (e) { svg.outerHTML = '<span style="color:red;font-size:8px">' + svg.getAttribute('data-code') + '</span>'; }
          });
          setTimeout(() => { window.focus(); window.print(); }, 300);
        });
      </script>
      </body></html>
    `);
    w.document.close();
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
        <div className="flex gap-4 items-end border-b pb-3 flex-wrap">
          <div className="space-y-1 flex-1 min-w-[220px]">
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
          <Button onClick={handlePrint} className="gap-1.5" disabled={variants.length === 0} data-testid="print-barcodes-btn">
            <Printer size={14} /> Print ({pages.length} page{pages.length === 1 ? '' : 's'})
          </Button>
        </div>

        {variants.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground py-8">
            No variants to print. Add variants to the product first.
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto bg-muted/30 p-2 rounded">
            {/* In-app preview — uses canvas, mirrors what the print window will produce */}
            <div className="bg-white mx-auto" style={{ width: '210mm', minHeight: '297mm', display: 'grid', gridTemplateColumns: `repeat(${cfg.cols}, 1fr)`, gridTemplateRows: `repeat(${cfg.rows}, 1fr)`, gap: '4mm', padding: '4mm', boxSizing: 'border-box' }}>
              {pages[0]?.map((v, vi) => (
                <div key={vi} style={{ border: '1px dashed #ccc', padding: '4px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', overflow: 'hidden' }}>
                  {showName && <div style={{ fontSize: '10px', fontWeight: 600, maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginBottom: '2px' }}>{product.name}{v.name ? ` — ${v.name}` : ''}</div>}
                  <BarcodeCanvas value={v.barcode || v.id || v.name} height={cfg.value === 'single' ? 120 : 50} width={barWidth} />
                  {showPrice && v.price != null && <div style={{ fontSize: '9px', color: '#555', marginTop: '2px' }}>{currency} {Number(v.price || 0).toLocaleString()}</div>}
                </div>
              ))}
            </div>
            {pages.length > 1 && <p className="text-center text-xs text-muted-foreground mt-2">+ {pages.length - 1} more page(s) on print</p>}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
