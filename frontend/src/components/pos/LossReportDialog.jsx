import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { PackageX, Printer } from 'lucide-react';

/** Where the stock is going when it isn't being sold. */
export const LossReportDialog = ({ report, range, setRange, loading, open, onOpenChange, onRefresh, onPrint, currency = 'UGX' }) => {
  const money = (n) => `${currency} ${Number(n || 0).toLocaleString()}`;
  const products = report?.by_product || [];
  const reasons = report?.by_reason || [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid="loss-report-dialog">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2">
            <PackageX size={16} className="text-destructive" />
            Stock written off{report?.store_name ? ` — ${report.store_name}` : ''}
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-wrap items-end gap-2">
          <div>
            <Label className="text-xs">From</Label>
            <Input type="date" value={range.start} className="h-8 w-auto"
              onChange={(e) => setRange(r => ({ ...r, start: e.target.value }))} data-testid="loss-start-input" />
          </div>
          <div>
            <Label className="text-xs">To</Label>
            <Input type="date" value={range.end} className="h-8 w-auto"
              onChange={(e) => setRange(r => ({ ...r, end: e.target.value }))} data-testid="loss-end-input" />
          </div>
          <Button size="sm" variant="outline" onClick={() => onRefresh(range)} disabled={loading}
            data-testid="loss-refresh-btn">{loading ? 'Working…' : 'Show'}</Button>
          {onPrint && report && (
            <Button size="sm" variant="outline" className="gap-1" onClick={onPrint} data-testid="loss-print-btn">
              <Printer size={13} /> Print
            </Button>
          )}
        </div>

        {report && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
              <div className="rounded-lg border border-border py-2">
                <p className="text-lg font-bold" data-testid="loss-count">{report.losses_count}</p>
                <p className="text-xs text-muted-foreground">write-offs</p>
              </div>
              <div className="rounded-lg border border-border py-2">
                <p className="text-lg font-bold" data-testid="loss-items">{report.items_lost}</p>
                <p className="text-xs text-muted-foreground">items gone</p>
              </div>
              <div className="rounded-lg border border-border py-2">
                <p className="text-lg font-bold text-destructive" data-testid="loss-value">{money(report.value_lost)}</p>
                <p className="text-xs text-muted-foreground">value lost</p>
              </div>
              <div className="rounded-lg border border-border py-2">
                <p className="text-lg font-bold text-amber-600" data-testid="loss-recover">{money(report.to_recover)}</p>
                <p className="text-xs text-muted-foreground">to come off pay</p>
              </div>
            </div>

            {report.worst && (
              <p className="text-sm bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2"
                 data-testid="loss-worst">
                Biggest loss: <span className="font-semibold">{report.worst.name}</span> — {report.worst.qty} gone,
                {' '}{money(report.worst.value)}.
              </p>
            )}

            <div className="grid md:grid-cols-2 gap-4 max-h-80 overflow-y-auto">
              <div>
                <p className="text-xs font-semibold uppercase text-muted-foreground mb-1">By product</p>
                {products.length ? products.map((p, i) => (
                  <div key={p.product_id || p.name} className="flex justify-between text-sm border-b border-border/60 py-1.5"
                       data-testid={`loss-product-${i}`}>
                    <span className="min-w-0 pr-2">
                      <span className="block truncate">{p.name}</span>
                      <span className="text-xs text-muted-foreground">
                        {Object.entries(p.reasons || {}).map(([r, q]) => `${r} ×${q}`).join(' · ')}
                      </span>
                    </span>
                    <span className="text-right whitespace-nowrap">
                      <span className="block font-semibold">{p.qty}</span>
                      <span className="text-xs text-muted-foreground">{money(p.value)}</span>
                    </span>
                  </div>
                )) : <p className="text-sm text-muted-foreground">Nothing was written off in this period.</p>}
              </div>
              <div>
                <p className="text-xs font-semibold uppercase text-muted-foreground mb-1">By reason</p>
                {reasons.length ? reasons.map((r, i) => (
                  <div key={r.reason} className="flex justify-between text-sm border-b border-border/60 py-1.5"
                       data-testid={`loss-reason-${i}`}>
                    <span className="min-w-0 pr-2 truncate">{r.label}</span>
                    <span className="text-right whitespace-nowrap">
                      <span className="block font-semibold">{r.qty}</span>
                      <span className="text-xs text-muted-foreground">{money(r.value)}</span>
                    </span>
                  </div>
                )) : <p className="text-sm text-muted-foreground">No reasons recorded yet.</p>}
              </div>
            </div>
            {!!report.donated_value && (
              <p className="text-xs text-muted-foreground" data-testid="loss-donated">
                Of that, {money(report.donated_value)} was donated — each donation has its own receipt.
              </p>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
};
