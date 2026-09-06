import React, { useEffect, useState } from 'react';
import { Building2, TrendingUp, Wallet, X } from 'lucide-react';
import { Card, CardContent } from './ui/card';
import { Progress } from './ui/progress';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { departmentsApi } from '../services/api';

/**
 * Department P&L tab — powered by GET /api/reports-department/pnl.
 *
 * Shows per-department revenue vs expense, budget-progress bars, and
 * run-rate cards. Sub-location and location rollups are computed
 * server-side (sum of child-department budgets + expenses) and rendered
 * as a compact strip above the department grid.
 *
 * iter-drilldown: Clicking a card opens a modal listing every
 * contributing expense + payroll allocation + tagged donation for the
 * selected window, so admins can audit exactly what rolled up.
 */
export function DepartmentPnlTab() {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const today = new Date().toISOString().slice(0, 10);
  const monthAgo = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10);
  const [dateFrom, setDateFrom] = useState(monthAgo);
  const [dateTo, setDateTo] = useState(today);
  const [drillDept, setDrillDept] = useState(null); // {id,name,color}
  const [drillData, setDrillData] = useState(null);
  const [drillBusy, setDrillBusy] = useState(false);

  const load = () => {
    setBusy(true);
    departmentsApi.pnl({ date_from: dateFrom, date_to: dateTo })
      .then(r => setData(r.data))
      .catch(() => setData({ departments: [], rollups: { by_sublocation: [], by_location: [] }, period: { from: dateFrom, to: dateTo, days: 30 } }))
      .finally(() => setBusy(false));
  };
  useEffect(load, [dateFrom, dateTo]);

  const openDrill = (d) => {
    setDrillDept(d);
    setDrillData(null);
    setDrillBusy(true);
    departmentsApi.entries(d.id, { date_from: dateFrom, date_to: dateTo })
      .then(r => setDrillData(r.data))
      .catch(() => setDrillData({ entries: [], totals: { revenue: 0, expense: 0, net: 0 } }))
      .finally(() => setDrillBusy(false));
  };

  const fmt = (n) => (Number(n) || 0).toLocaleString();

  return (
    <div className="space-y-4" data-testid="dept-pnl-tab">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="space-y-1">
          <Label className="text-xs">From</Label>
          <Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="h-8 text-xs" data-testid="dept-pnl-from" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">To</Label>
          <Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="h-8 text-xs" data-testid="dept-pnl-to" />
        </div>
        <p className="text-[11px] text-muted-foreground self-end mb-2">
          {data?.period ? `${data.period.days} day window · projections extrapolated to 30 days · click a card to audit contributing entries` : ''}
        </p>
      </div>

      {/* Rollups — sub-location + location totals derived from child departments */}
      {data?.rollups?.by_location?.length > 0 && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {data.rollups.by_location.map(r => {
            const pct = r.budget ? Math.min(100, (r.expense / r.budget) * 100) : 0;
            return (
              <Card key={r.location_id} className="border-primary/20">
                <CardContent className="p-3 space-y-1.5">
                  <div className="flex items-center gap-2 text-xs">
                    <Building2 size={12} className="text-primary" />
                    <span className="font-medium">{r.name || r.location_id}</span>
                    <Badge variant="secondary" className="ml-auto text-[9px]">Campus rollup</Badge>
                  </div>
                  <Progress value={pct} className="h-1.5" />
                  <p className="text-[11px] text-muted-foreground">
                    <strong>{fmt(r.expense)}</strong> of <strong>{fmt(r.budget)}</strong>
                    {r.budget ? <> · {pct.toFixed(1)}%</> : ' · no budget set'}
                  </p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Per-department grid */}
      {busy ? (
        <p className="text-center py-8 text-sm text-muted-foreground">Loading…</p>
      ) : !data?.departments?.length ? (
        <div className="text-center py-8 border border-dashed rounded-lg text-sm text-muted-foreground">
          No departments to report on yet. Add some in <strong>Admin → System Console → Departments</strong>, then tag expenses / salaries with them.
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {data.departments.map(d => {
            const pct = d.budget_used_pct;
            const over = pct != null && pct > 100;
            return (
              <Card
                key={d.id}
                className="cursor-pointer transition-colors hover:border-primary/40"
                onClick={() => openDrill(d)}
                data-testid={`dept-pnl-card-${d.id}`}
              >
                <CardContent className="p-3 space-y-2">
                  <div className="flex items-center gap-2">
                    {d.color && <span className="w-3 h-3 rounded-full" style={{ background: d.color }} />}
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm truncate">{d.name}</p>
                      <p className="text-[10px] text-muted-foreground truncate">
                        {d.location_name}{d.sublocation_name ? ` · ${d.sublocation_name}` : ''}
                      </p>
                    </div>
                    <Badge variant="outline" className="text-[9px]">Audit</Badge>
                  </div>
                  {d.budget > 0 && (
                    <>
                      <Progress value={Math.min(100, pct || 0)} className={`h-1.5 ${over ? '[&>*]:bg-red-500' : ''}`} />
                      <p className={`text-[11px] ${over ? 'text-red-600 font-medium' : 'text-muted-foreground'}`}>
                        {fmt(d.expense)} of {fmt(d.budget)}
                        {pct != null && <> · {pct.toFixed(1)}%</>}
                        {over && ' · OVER'}
                      </p>
                    </>
                  )}
                  <div className="grid grid-cols-3 gap-1 pt-1 border-t">
                    <div>
                      <p className="text-[9px] text-muted-foreground uppercase">Rev</p>
                      <p className="text-xs font-mono text-emerald-600">{fmt(d.revenue)}</p>
                    </div>
                    <div>
                      <p className="text-[9px] text-muted-foreground uppercase">Exp</p>
                      <p className="text-xs font-mono text-red-600">{fmt(d.expense)}</p>
                    </div>
                    <div>
                      <p className="text-[9px] text-muted-foreground uppercase">Net</p>
                      <p className={`text-xs font-mono ${d.net >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>{fmt(d.net)}</p>
                    </div>
                  </div>
                  <div className="pt-1.5 border-t text-[11px] text-muted-foreground flex items-center gap-1.5">
                    <TrendingUp size={11} /> Run-rate: <strong className="text-foreground">{fmt(d.run_rate_monthly)}/mo</strong>
                    <Wallet size={11} className="ml-1" />
                    <strong className={d.budget - d.expense >= 0 ? 'text-emerald-700' : 'text-red-700'}>{fmt(d.budget - d.expense)}</strong>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Drill-down modal */}
      <Dialog open={!!drillDept} onOpenChange={(o) => { if (!o) { setDrillDept(null); setDrillData(null); } }}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-hidden flex flex-col" data-testid="dept-drill-modal">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {drillDept?.color && <span className="w-3 h-3 rounded-full" style={{ background: drillDept.color }} />}
              <span>{drillDept?.name}</span>
              <Badge variant="secondary" className="text-[10px]">{dateFrom} → {dateTo}</Badge>
            </DialogTitle>
          </DialogHeader>
          {drillBusy && <p className="py-8 text-center text-sm text-muted-foreground">Loading contributing entries…</p>}
          {!drillBusy && drillData && (
            <>
              <div className="grid grid-cols-3 gap-2 text-center border-b pb-3">
                <div>
                  <p className="text-[10px] text-muted-foreground uppercase">Revenue</p>
                  <p className="text-sm font-mono text-emerald-700" data-testid="drill-total-revenue">{fmt(drillData.totals?.revenue)}</p>
                </div>
                <div>
                  <p className="text-[10px] text-muted-foreground uppercase">Expense</p>
                  <p className="text-sm font-mono text-red-700" data-testid="drill-total-expense">{fmt(drillData.totals?.expense)}</p>
                </div>
                <div>
                  <p className="text-[10px] text-muted-foreground uppercase">Net</p>
                  <p className={`text-sm font-mono ${drillData.totals?.net >= 0 ? 'text-emerald-800' : 'text-red-800'}`} data-testid="drill-total-net">{fmt(drillData.totals?.net)}</p>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto -mx-6 px-6">
                {drillData.entries?.length ? (
                  <table className="w-full text-xs">
                    <thead className="text-left text-muted-foreground sticky top-0 bg-background">
                      <tr className="border-b">
                        <th className="py-2">Date</th>
                        <th>Kind</th>
                        <th>Title</th>
                        <th>Note</th>
                        <th className="text-right">Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {drillData.entries.map((e, i) => (
                        <tr key={`${e.kind}-${e.id}-${i}`} className="border-b last:border-0" data-testid={`drill-entry-${e.kind}-${i}`}>
                          <td className="py-1.5">{e.date}</td>
                          <td>
                            <Badge variant={e.kind === 'donation' ? 'default' : e.kind === 'payroll' ? 'secondary' : 'outline'} className="text-[9px] capitalize">
                              {e.kind}
                            </Badge>
                          </td>
                          <td className="font-medium truncate max-w-[180px]">{e.title}</td>
                          <td className="text-muted-foreground truncate max-w-[140px]">{e.note}</td>
                          <td className={`text-right font-mono ${e.kind === 'donation' ? 'text-emerald-700' : 'text-red-700'}`}>
                            {e.kind === 'donation' ? '+' : '-'}{fmt(e.amount)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="py-12 text-center text-sm text-muted-foreground">No entries touched this department in the selected window.</p>
                )}
              </div>
              <div className="pt-3 border-t flex justify-end">
                <Button size="sm" variant="outline" onClick={() => setDrillDept(null)} data-testid="drill-close-btn">
                  <X size={14} className="mr-1" /> Close
                </Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default DepartmentPnlTab;
