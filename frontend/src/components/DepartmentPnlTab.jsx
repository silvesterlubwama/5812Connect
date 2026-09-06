import React, { useEffect, useState } from 'react';
import { Building2, TrendingUp, Wallet } from 'lucide-react';
import { Card, CardContent } from './ui/card';
import { Progress } from './ui/progress';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { departmentsApi } from '../services/api';

/**
 * Department P&L tab — powered by GET /api/reports-department/pnl.
 *
 * Shows per-department revenue vs expense, budget-progress bars, and
 * run-rate cards. Sub-location and location rollups are computed
 * server-side (sum of child-department budgets + expenses) and rendered
 * as a compact strip above the department grid.
 */
export function DepartmentPnlTab() {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const today = new Date().toISOString().slice(0, 10);
  const monthAgo = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10);
  const [dateFrom, setDateFrom] = useState(monthAgo);
  const [dateTo, setDateTo] = useState(today);
  const [selected, setSelected] = useState(null);

  const load = () => {
    setBusy(true);
    departmentsApi.pnl({ date_from: dateFrom, date_to: dateTo })
      .then(r => setData(r.data))
      .catch(() => setData({ departments: [], rollups: { by_sublocation: [], by_location: [] }, period: { from: dateFrom, to: dateTo, days: 30 } }))
      .finally(() => setBusy(false));
  };
  useEffect(load, [dateFrom, dateTo]);

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
          {data?.period ? `${data.period.days} day window · projections extrapolated to 30 days` : ''}
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
                className={`cursor-pointer transition-colors hover:border-primary/40 ${selected === d.id ? 'ring-2 ring-primary/40' : ''}`}
                onClick={() => setSelected(selected === d.id ? null : d.id)}
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
                  {selected === d.id && (
                    <div className="pt-2 border-t space-y-1 text-[11px]">
                      <div className="flex items-center gap-1.5 text-muted-foreground">
                        <TrendingUp size={11} /> Monthly run-rate: <strong className="text-foreground">{fmt(d.run_rate_monthly)}</strong>
                      </div>
                      <div className="flex items-center gap-1.5 text-muted-foreground">
                        <Wallet size={11} /> Budget headroom: <strong className={d.budget - d.expense >= 0 ? 'text-emerald-700' : 'text-red-700'}>{fmt(d.budget - d.expense)}</strong>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default DepartmentPnlTab;
