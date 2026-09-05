import React from 'react';
import { X, Trash2, Edit2, Download, Archive, Printer } from 'lucide-react';
import { Button } from './ui/button';
import { Badge } from './ui/badge';

/**
 * Reusable bulk action bar — shows when items are selected
 * @param {Set} selectedIds - Set of selected item IDs
 * @param {Function} onClear - Clear selection
 * @param {Function} onBulkEdit - Open bulk edit dialog
 * @param {Function} onBulkDelete - Delete selected items
 * @param {Function} onBulkExport - Export selected as CSV
 * @param {Function} onBulkArchive - Archive selected (optional)
 * @param {Function} onBulkPrintBarcodes - Bulk-print variant barcodes (optional)
 * @param {number} totalCount - Total items in list (for "select all" context)
 */
export function BulkActionBar({ selectedIds, onClear, onBulkEdit, onBulkDelete, onBulkExport, onBulkArchive, onBulkPrintBarcodes, totalCount }) {
  if (!selectedIds || selectedIds.size === 0) return null;

  return (
    <div className="flex items-center gap-3 px-4 py-2.5 bg-primary/5 border border-primary/20 rounded-lg flex-wrap" data-testid="bulk-action-bar">
      <Badge className="text-xs">{selectedIds.size} selected</Badge>
      {onBulkEdit && (
        <Button size="sm" variant="outline" className="gap-1.5 text-xs h-7" onClick={onBulkEdit} data-testid="bulk-edit-btn">
          <Edit2 size={12} /> Edit
        </Button>
      )}
      {onBulkPrintBarcodes && (
        <Button size="sm" variant="outline" className="gap-1.5 text-xs h-7" onClick={onBulkPrintBarcodes} data-testid="bulk-print-barcodes-btn">
          <Printer size={12} /> Print barcodes
        </Button>
      )}
      {onBulkExport && (
        <Button size="sm" variant="outline" className="gap-1.5 text-xs h-7" onClick={onBulkExport} data-testid="bulk-export-btn">
          <Download size={12} /> Export CSV
        </Button>
      )}
      {onBulkArchive && (
        <Button size="sm" variant="outline" className="gap-1.5 text-xs h-7" onClick={onBulkArchive} data-testid="bulk-archive-btn">
          <Archive size={12} /> Archive
        </Button>
      )}
      {onBulkDelete && (
        <Button size="sm" variant="destructive" className="gap-1.5 text-xs h-7" onClick={onBulkDelete} data-testid="bulk-delete-btn">
          <Trash2 size={12} /> Delete
        </Button>
      )}
      <div className="flex-1" />
      <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={onClear}><X size={14} /></Button>
    </div>
  );
}

/**
 * Export array of objects as CSV file download
 */
export function exportToCSV(data, filename = 'export.csv') {
  if (!data || data.length === 0) return;
  const headers = Object.keys(data[0]);
  const csvRows = [
    headers.join(','),
    ...data.map(row => headers.map(h => {
      const val = row[h];
      if (val === null || val === undefined) return '';
      const str = String(val).replace(/"/g, '""');
      return str.includes(',') || str.includes('"') || str.includes('\n') ? `"${str}"` : str;
    }).join(','))
  ];
  const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/**
 * Checkbox for row selection
 */
export function SelectCheckbox({ checked, onChange, id }) {
  return (
    <input
      type="checkbox"
      checked={checked}
      onChange={onChange}
      className="h-4 w-4 rounded border-border text-primary accent-primary cursor-pointer"
      data-testid={`select-${id}`}
    />
  );
}
