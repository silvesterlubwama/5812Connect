import React, { useEffect, useRef, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Input } from './ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Printer, Download, RefreshCw } from 'lucide-react';
import JsBarcode from 'jsbarcode';
import api from '../services/api';
import { toast } from 'sonner';

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

export default function VariantBarcodePrint({ open, onOpenChange, product, products, currency = 'UGX', onProductUpdated }) {
  const [layout, setLayout] = useState('grid_4x6');
  const [copies, setCopies] = useState(1);
  const [showPrice, setShowPrice] = useState(true);
  const [showName, setShowName] = useState(true);
  const [regenBusy, setRegenBusy] = useState(false);

  // Bulk mode: caller passed `products` (array). Flatten every variant across
  // every product into a single labelled list. Falls back to the single-product
  // path when only `product` is provided.
  const isBulk = Array.isArray(products) && products.length > 0;
  const bulkVariants = isBulk
    ? products.flatMap(p => (p.variants || []).map(v => ({
        ...v,
        _productName: p.name,
        _productCurrency: p.currency || currency,
      })))
    : [];
  const variants = isBulk ? bulkVariants : (product?.variants || []);
  const cfg = LAYOUTS.find(l => l.value === layout) || LAYOUTS[0];
  const perPage = cfg.cols * cfg.rows;
  const headerTitle = isBulk
    ? `Bulk barcodes — ${products.length} product${products.length === 1 ? '' : 's'} · ${variants.length} variant${variants.length === 1 ? '' : 's'}`
    : `Print Variant Barcodes — ${product?.name || ''}`;

  // CSV export — variant name, barcode, price, units/pack
  const exportCsv = () => {
    if (variants.length === 0) { toast.error('No variants to export'); return; }
    const header = 'product,variant,barcode,price,currency,stock,units_per_pack,sku';
    const lines = variants.map(v => {
      const fields = [
        isBulk ? (v._productName || '') : (product.name || ''),
        v.name || '',
        v.barcode || '',
        v.price ?? '',
        isBulk ? (v._productCurrency || currency) : currency,
        v.stock ?? '',
        v.units_per_pack ?? 1,
        v.sku || '',
      ];
      return fields.map(f => {
        const s = String(f).replace(/"/g, '""');
        return /[",\n]/.test(s) ? `"${s}"` : s;
      }).join(',');
    });
    const csv = [header, ...lines].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const safeName = isBulk ? 'bulk' : (product.name || 'product').replace(/[^a-z0-9-_]+/gi, '_').toLowerCase();
    a.href = url;
    a.download = `barcodes-${safeName}.csv`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success(`Exported ${variants.length} barcode${variants.length === 1 ? '' : 's'}`);
  };

  // Regenerate ALL barcodes (force=true) — useful after a collision or a printer mis-print.
  const regenerateAll = async () => {
    if (!product?.id) { toast.error('Save the product first'); return; }
    if (!window.confirm(`Regenerate barcodes for all ${variants.length} variants? Old barcodes will be replaced — make sure no live labels are still in use.`)) return;
    setRegenBusy(true);
    try {
      const r = await api.post(`/products/${product.id}/generate-barcodes?force=true`);
      toast.success(r.data?.message || 'Regenerated');
      onProductUpdated?.();
    } catch (err) { toast.error(err.response?.data?.detail || 'Regenerate failed'); }
    finally { setRegenBusy(false); }
  };

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
        const productLabel = isBulk ? (v._productName || '') : (product?.name || '');
        const cur = isBulk ? (v._productCurrency || currency) : currency;
        const safeName = (productLabel + (v.name ? ` — ${v.name}` : '')).replace(/[<>&]/g, '');
        const priceStr = showPrice && v.price != null ? `${cur} ${Number(v.price || 0).toLocaleString()}` : '';
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
      <html><head><title>${isBulk ? 'Bulk Barcodes' : (product?.name || 'Variant Barcodes')}</title>
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
            } catch (err) {
              const span = document.createElement('span');
              span.style.color = 'red';
              span.style.fontSize = '8px';
              span.textContent = svg.getAttribute('data-code') || '';
              svg.replaceWith(span);
            }
          });
          setTimeout(() => { window.focus(); window.print(); }, 300);
        });
      </script>
      </body></html>
    `);
    w.document.close();
  };

  if (!product && !isBulk) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Printer size={16} /> {headerTitle}
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
          <Button onClick={exportCsv} variant="outline" className="gap-1.5" disabled={variants.length === 0} data-testid="export-barcodes-csv-btn">
            <Download size={14} /> Export CSV
          </Button>
          {product?.id && !isBulk && (
            <Button onClick={regenerateAll} variant="outline" className="gap-1.5" disabled={variants.length === 0 || regenBusy} data-testid="regenerate-barcodes-btn">
              <RefreshCw size={14} className={regenBusy ? 'animate-spin' : ''} /> {regenBusy ? 'Regenerating…' : 'Regenerate all'}
            </Button>
          )}
        </div>

        {variants.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground py-8">
            {isBulk ? 'None of the selected products have variants.' : 'No variants to print. Add variants to the product first.'}
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto bg-muted/30 p-2 rounded">
            {/* In-app preview — uses canvas, mirrors what the print window will produce */}
            <div className="bg-white mx-auto" style={{ width: '210mm', minHeight: '297mm', display: 'grid', gridTemplateColumns: `repeat(${cfg.cols}, 1fr)`, gridTemplateRows: `repeat(${cfg.rows}, 1fr)`, gap: '4mm', padding: '4mm', boxSizing: 'border-box' }}>
              {pages[0]?.map((v, vi) => {
                const productLabel = isBulk ? (v._productName || '') : (product?.name || '');
                const cur = isBulk ? (v._productCurrency || currency) : currency;
                return (
                  <div key={vi} style={{ border: '1px dashed #ccc', padding: '4px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', overflow: 'hidden' }}>
                    {showName && <div style={{ fontSize: '10px', fontWeight: 600, maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginBottom: '2px' }}>{productLabel}{v.name ? ` — ${v.name}` : ''}</div>}
                    <BarcodeCanvas value={v.barcode || v.id || v.name} height={cfg.value === 'single' ? 120 : 50} width={barWidth} />
                    {showPrice && v.price != null && <div style={{ fontSize: '9px', color: '#555', marginTop: '2px' }}>{cur} {Number(v.price || 0).toLocaleString()}</div>}
                  </div>
                );
              })}
            </div>
            {pages.length > 1 && <p className="text-center text-xs text-muted-foreground mt-2">+ {pages.length - 1} more page(s) on print</p>}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
