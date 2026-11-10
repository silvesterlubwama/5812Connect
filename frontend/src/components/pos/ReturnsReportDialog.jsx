import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { PackageX } from 'lucide-react';

/** What keeps coming back — by product, and by reason. */
export const ReturnsReportDialog = ({ report, range, setRange, loading, open, onOpenChange, onRefresh, currency = 'UGX' }) => {
  const money = (n) => `${currency} ${Number(n || 0).toLocaleString()}`;
  const products = report?.by_product || [];
  const reasons = report?.by_reason || [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid="returns-report-dialog">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2">
            <PackageX size={16} className="text-amber-600" />
            What keeps coming back{report?.store_name ? ` — ${report.store_name}` : ''}
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-wrap items-end gap-2">
          <div>
            <Label className="text-xs">From</Label>
            <Input type="date" value={range.start} className="h-8 w-auto"
              onChange={(e) => setRange(r => ({ ...r, start: e.target.value }))} data-testid="returns-start-input" />
          </div>
          <div>
            <Label className="text-xs">To</Label>
            <Input type="date" value={range.end} className="h-8 w-auto"
              onChange={(e) => setRange(r => ({ ...r, end: e.target.value }))} data-testid="returns-end-input" />
          </div>
          <Button size="sm" variant="outline" onClick={() => onRefresh(range)} disabled={loading}
            data-testid="returns-refresh-btn">{loading ? 'Working…' : 'Show'}</Button>
        </div>

        {report && (
          <>
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-lg border border-border py-2">
                <p className="text-lg font-bold" data-testid="returns-count">{report.refunds_count}</p>
                <p className="text-xs text-muted-foreground">returns</p>
              </div>
              <div className="rounded-lg border border-border py-2">
                <p className="text-lg font-bold" data-testid="returns-items">{report.items_returned}</p>
                <p className="text-xs text-muted-foreground">items back</p>
              </div>
              <div className="rounded-lg border border-border py-2">
                <p className="text-lg font-bold text-amber-600" data-testid="returns-total">{money(report.refunds_total)}</p>
                <p className="text-xs text-muted-foreground">given back</p>
              </div>
            </div>

            {report.worst && (
              <p className="text-sm bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 rounded-lg px-3 py-2"
                 data-testid="returns-worst">
                Worst offender: <span className="font-semibold">{report.worst.name}</span> — {report.worst.qty} back,
                {' '}{money(report.worst.amount)} refunded.
              </p>
            )}

            <div className="grid md:grid-cols-2 gap-4 max-h-80 overflow-y-auto">
              <div>
                <p className="text-xs font-semibold uppercase text-muted-foreground mb-1">By product</p>
                {products.length ? products.map((p, i) => (
                  <div key={p.product_id || p.name} className="flex justify-between text-sm border-b border-border/60 py-1.5"
                       data-testid={`returns-product-${i}`}>
                    <span className="min-w-0 pr-2">
                      <span className="block truncate">{p.name}</span>
                      <span className="text-xs text-muted-foreground">
                        {Object.entries(p.reasons || {}).map(([r, q]) => `${r} ×${q}`).join(' · ')}
                      </span>
                    </span>
                    <span className="text-right whitespace-nowrap">
                      <span className="block font-semibold">{p.qty}</span>
                      <span className="text-xs text-muted-foreground">{money(p.amount)}</span>
                    </span>
                  </div>
                )) : <p className="text-sm text-muted-foreground">Nothing came back in this period.</p>}
              </div>
              <div>
                <p className="text-xs font-semibold uppercase text-muted-foreground mb-1">By reason</p>
                {reasons.length ? reasons.map((r, i) => (
                  <div key={r.reason} className="flex justify-between text-sm border-b border-border/60 py-1.5"
                       data-testid={`returns-reason-${i}`}>
                    <span className="min-w-0 pr-2 truncate">{r.reason}</span>
                    <span className="text-right whitespace-nowrap">
                      <span className="block font-semibold">{r.count}</span>
                      <span className="text-xs text-muted-foreground">{money(r.amount)}</span>
                    </span>
                  </div>
                )) : <p className="text-sm text-muted-foreground">No reasons recorded yet.</p>}
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
};
