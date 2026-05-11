import React, { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Input } from './ui/input';
import { Printer } from 'lucide-react';
import { escapeHtml as e } from '../utils/htmlEscape';

const LAYOUTS = [
  { value: 'grid_3x8', label: '3×8 grid (24/page) — 70mm × 35mm labels', cols: 3, rows: 8 },
  { value: 'grid_2x5', label: '2×5 grid (10/page) — large readable labels', cols: 2, rows: 5 },
  { value: 'sheet_a4', label: '5×13 grid (65/page) — Avery L7651 small', cols: 5, rows: 13 },
  { value: 'single', label: 'One per page (full)', cols: 1, rows: 1 },
];

/**
 * BulkBarcodeLabelDialog — print barcode labels for a *batch* of items.
 * Each item shape: { name, code, location_name, price? } — works for products variants AND resources.
 */
export default function BulkBarcodeLabelDialog({ items, open, onOpenChange, title = 'Print barcode labels' }) {
  const [layout, setLayout] = useState('grid_3x8');
  const [copies, setCopies] = useState(1);
  const [showName, setShowName] = useState(true);
  const [showLoc, setShowLoc] = useState(true);

  const cfg = LAYOUTS.find(l => l.value === layout) || LAYOUTS[0];
  const perPage = cfg.cols * cfg.rows;

  // Build print list with copies
  const printList = [];
  (items || []).forEach(it => { for (let i = 0; i < copies; i++) printList.push(it); });
  const pages = [];
  for (let i = 0; i < printList.length; i += perPage) pages.push(printList.slice(i, i + perPage));

  // Auto-tune barcode width for the longest code
  const maxLen = (items || []).reduce((m, it) => Math.max(m, (it.code || '').length), 10);
  const barWidth = cfg.value === 'single' ? 2.4 : maxLen > 22 ? 0.9 : maxLen > 18 ? 1.1 : 1.4;
  const barHeight = cfg.value === 'single' ? 140 : cfg.value === 'sheet_a4' ? 30 : 50;

  const handlePrint = () => {
    if (!items || items.length === 0) return;
    const w = window.open('', '_blank', 'width=900,height=700');
    const cellsHtml = pages.map(pageItems => {
      const cells = pageItems.map(it => {
        const code = String(it.code || '');
        const safeName = e(it.name || '');
        const loc = e(it.location_name || '');
        return `
          <div class="cell">
            ${showName ? `<div class="name">${safeName}</div>` : ''}
            <svg class="bc" data-code="${e(code)}"></svg>
            ${showLoc && loc ? `<div class="loc">58:12 · ${loc}</div>` : ''}
          </div>`;
      }).join('');
      return `<div class="page" style="grid-template-columns: repeat(${cfg.cols}, 1fr); grid-template-rows: repeat(${cfg.rows}, 1fr);">${cells}</div>`;
    }).join('');

    w.document.write(`
      <html><head><title>${e(title)}</title>
        <script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.12.3/dist/JsBarcode.all.min.js"></script>
        <style>
          @page { size: A4; margin: 6mm; }
          html, body { margin: 0; padding: 0; font-family: Arial, sans-serif; }
          .page { display: grid; gap: 3mm; padding: 4mm; box-sizing: border-box; page-break-after: always; min-height: 270mm; }
          .page:last-child { page-break-after: auto; }
          .cell { border: 1px dashed #ddd; padding: 2px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; overflow: hidden; box-sizing: border-box; }
          .cell .name { font-size: 8px; font-weight: 600; line-height: 1.1; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-bottom: 1px; }
          .cell .bc { width: 92%; height: ${cfg.value === 'single' ? '70mm' : cfg.value === 'sheet_a4' ? '8mm' : '14mm'}; display: block; }
          .cell .loc { font-size: 6px; color: #555; line-height: 1; }
          @media print { .cell { border: none; } }
        </style>
      </head><body>${cellsHtml}
      <script>
        window.addEventListener('load', () => {
          document.querySelectorAll('svg.bc').forEach(svg => {
            try {
              JsBarcode(svg, svg.getAttribute('data-code'), {
                format: 'CODE128', width: ${barWidth}, height: ${barHeight}, displayValue: true,
                fontSize: ${cfg.value === 'single' ? 14 : cfg.value === 'sheet_a4' ? 6 : 8},
                font: 'monospace', textMargin: 1, margin: 0,
              });
            } catch (e) { svg.outerHTML = '<span style="color:red;font-size:7px">' + svg.getAttribute('data-code') + '</span>'; }
          });
          setTimeout(() => { window.focus(); window.print(); }, 350);
        });
      </script>
      </body></html>
    `);
    w.document.close();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader><DialogTitle className="flex items-center gap-2">
          <Printer size={16} /> {title} — {items?.length || 0} items
        </DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Layout</Label>
              <Select value={layout} onValueChange={setLayout}>
                <SelectTrigger data-testid="bulk-barcode-layout"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {LAYOUTS.map(l => <SelectItem key={l.value} value={l.value}>{l.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Copies per item</Label>
              <Input type="number" min={1} max={50} value={copies}
                onChange={e => setCopies(Math.max(1, Math.min(50, parseInt(e.target.value) || 1)))} />
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <label className="flex items-center gap-1.5 cursor-pointer"><input type="checkbox" checked={showName} onChange={e => setShowName(e.target.checked)} /> Show name</label>
            <label className="flex items-center gap-1.5 cursor-pointer"><input type="checkbox" checked={showLoc} onChange={e => setShowLoc(e.target.checked)} /> Show location footer</label>
          </div>
          <div className="bg-muted/30 rounded-md p-3 text-xs space-y-1 max-h-40 overflow-y-auto">
            <p className="font-semibold">Items in batch ({items?.length || 0}):</p>
            {(items || []).slice(0, 30).map((it, i) => (
              <div key={i} className="flex items-center justify-between">
                <span className="truncate flex-1">{it.name}</span>
                <code className="font-mono text-[10px] text-muted-foreground ml-2">{it.code}</code>
              </div>
            ))}
            {(items?.length || 0) > 30 && <p className="text-muted-foreground">+ {items.length - 30} more...</p>}
          </div>
          <p className="text-[10px] text-muted-foreground">
            {pages.length} page{pages.length === 1 ? '' : 's'} · auto bar width {barWidth} · longest code {maxLen} chars
          </p>
          <Button onClick={handlePrint} className="w-full gap-1.5" disabled={!items || items.length === 0} data-testid="bulk-print-btn">
            <Printer size={14} /> Print {pages.length} page{pages.length === 1 ? '' : 's'} ({printList.length} labels)
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
