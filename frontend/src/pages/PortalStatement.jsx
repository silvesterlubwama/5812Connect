import React, { useCallback, useEffect, useState } from 'react';
import { FileSpreadsheet, Printer, ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { portalApi } from '../services/api';
import { useBranding } from '../context/BrandingContext';
import { toast } from 'sonner';

const monthLabel = (m) =>
  new Date(`${m}-01T00:00:00`).toLocaleDateString(undefined, { month: 'long', year: 'numeric' });

const shift = (m, delta) => {
  const [y, mo] = m.split('-').map(Number);
  const d = new Date(y, mo - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
};

export default function PortalStatement() {
  const { branding } = useBranding();
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (m) => {
    setLoading(true);
    try {
      const r = await portalApi.statement(m);
      setData(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not load your statement');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(month); }, [month, load]);

  const cur = data?.currency || 'UGX';
  const money = (v) => `${cur} ${Number(v || 0).toLocaleString()}`;
  const thisMonth = new Date().toISOString().slice(0, 7);

  return (
    <div className="space-y-6" data-testid="portal-statement-page">
      <div className="flex flex-wrap items-center justify-between gap-3 no-print">
        <div>
          <h1 className="text-2xl font-semibold font-heading flex items-center gap-2">
            <FileSpreadsheet size={22} /> My Statement
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Everything you bought and every ticket issued to you, one month at a time.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setMonth(shift(month, -1))} data-testid="statement-prev-month">
            <ChevronLeft size={14} />
          </Button>
          <span className="text-sm font-medium min-w-[9rem] text-center" data-testid="statement-month-label">
            {monthLabel(month)}
          </span>
          <Button variant="outline" size="sm" disabled={month >= thisMonth}
            onClick={() => setMonth(shift(month, 1))} data-testid="statement-next-month">
            <ChevronRight size={14} />
          </Button>
          <Button variant="outline" size="sm" onClick={() => load(month)} data-testid="statement-refresh"><RefreshCw size={14} /></Button>
          <Button size="sm" className="gap-1.5" onClick={() => window.print()} data-testid="statement-print">
            <Printer size={14} /> Print
          </Button>
        </div>
      </div>

      <Card className="shadow-soft rounded-xl print-area">
        <CardContent className="p-6 space-y-5">
          {/* Letterhead */}
          <div className="flex items-start justify-between gap-4 border-b border-border pb-4">
            <div className="flex items-center gap-3">
              {branding?.logo_url && <img src={branding.logo_url} alt="" className="h-10 w-10 object-contain" />}
              <div>
                <p className="font-semibold font-heading">{branding?.app_name || '58:12 Global'}</p>
                <p className="text-xs text-muted-foreground">Account statement · {monthLabel(month)}</p>
              </div>
            </div>
            <div className="text-right text-xs text-muted-foreground">
              <p className="font-medium text-foreground">{data?.holder?.name}</p>
              <p>{data?.holder?.email}</p>
            </div>
          </div>

          {loading && <div className="h-32 animate-pulse bg-muted rounded-lg" />}

          {!loading && (data?.lines || []).length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-10" data-testid="statement-empty">
              Nothing on your account for {monthLabel(month)}.
            </p>
          )}

          {!loading && (data?.lines || []).length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="statement-table">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground border-b border-border">
                    <th className="py-2 pr-3">Date</th>
                    <th className="py-2 pr-3">Reference</th>
                    <th className="py-2 pr-3">Description</th>
                    <th className="py-2 pr-3">Status</th>
                    <th className="py-2 text-right">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {data.lines.map((l, i) => (
                    <tr key={`${l.reference}-${i}`} className="border-b border-border/50" data-testid={`statement-row-${i}`}>
                      <td className="py-2 pr-3 whitespace-nowrap">{l.date}</td>
                      <td className="py-2 pr-3 font-mono text-[11px]">{l.reference}</td>
                      <td className="py-2 pr-3">{l.description}</td>
                      <td className="py-2 pr-3">
                        <Badge variant={l.status === 'Paid' || l.status === 'Valid' ? 'secondary' : 'outline'} className="text-[10px]">
                          {l.status}
                        </Badge>
                      </td>
                      <td className="py-2 text-right whitespace-nowrap">{money(l.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {!loading && data && (
            <div className="grid grid-cols-3 gap-3 pt-2">
              <div className="rounded-lg bg-accent/40 p-3">
                <p className="text-xs text-muted-foreground">Charged</p>
                <p className="text-base font-semibold" data-testid="statement-charged">{money(data.totals?.charged)}</p>
              </div>
              <div className="rounded-lg bg-accent/40 p-3">
                <p className="text-xs text-muted-foreground">Paid</p>
                <p className="text-base font-semibold" data-testid="statement-paid">{money(data.totals?.paid)}</p>
              </div>
              <div className="rounded-lg bg-accent/40 p-3">
                <p className="text-xs text-muted-foreground">Outstanding</p>
                <p className="text-base font-semibold" data-testid="statement-outstanding">{money(data.totals?.outstanding)}</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <style>{`
        @media print {
          .no-print { display: none !important; }
          body { background: #fff !important; }
        }
      `}</style>
    </div>
  );
}
