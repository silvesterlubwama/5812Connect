/**
 * PBX Call Analytics — admin dashboard panel.
 *
 * Reads from /api/pbx/cdr/analytics. Shows:
 *   • KPI tiles  (total, missed ratio, avg duration, incoming vs outgoing)
 *   • Daily sparkline (last N days)
 *   • Hour-of-day heatmap (0–23)
 *   • Top numbers / top contacts / top staff tables
 *
 * Kept dependency-free — no charting library, just CSS bars.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { ArrowDownLeft, ArrowUpRight, PhoneMissed, RefreshCw, BarChart3, Clock, Users, Hash } from 'lucide-react';
import api from '../services/api';
import { toast } from 'sonner';

const fmtDuration = (s) => {
  if (!s) return '0s';
  const m = Math.floor(s / 60);
  const sec = s % 60;
  if (m === 0) return `${sec}s`;
  if (m < 60) return `${m}m ${sec}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
};

const fmtPct = (n) => `${Math.round((n || 0) * 100)}%`;

export default function PBXAnalytics() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = (d = days) => {
    setLoading(true);
    api.get('/pbx/cdr/analytics', { params: { days: d } })
      .then(r => setData(r.data))
      .catch(e => toast.error(e.response?.data?.detail || 'Failed to load analytics'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(days); }, [days]);

  const maxDaily = useMemo(() => Math.max(1, ...(data?.daily || []).map(d => d.total)), [data]);
  const maxHour = useMemo(() => Math.max(1, ...(data?.busiest_hour || []).map(h => h.count)), [data]);
  const peakHour = useMemo(() => {
    const list = data?.busiest_hour || [];
    const top = list.reduce((acc, h) => h.count > (acc?.count || 0) ? h : acc, null);
    return top && top.count > 0 ? top : null;
  }, [data]);

  if (!data && !loading) return <div className="p-6 text-sm text-muted-foreground">No data.</div>;

  const s = data?.summary || {};

  return (
    <div className="space-y-4" data-testid="pbx-analytics">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2"><BarChart3 size={16} /> Call analytics</h2>
          <p className="text-xs text-muted-foreground">Aggregated from browser softphone CDRs. Trailing {days} days.</p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={String(days)} onValueChange={v => setDays(parseInt(v))}>
            <SelectTrigger className="w-28 h-8 text-xs" data-testid="analytics-range"><SelectValue /></SelectTrigger>
            <SelectContent>
              {[7, 14, 30, 60, 90, 180].map(d => <SelectItem key={d} value={String(d)}>{d} days</SelectItem>)}
            </SelectContent>
          </Select>
          <Button size="sm" variant="outline" onClick={() => load()} disabled={loading} data-testid="analytics-refresh">
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          </Button>
        </div>
      </div>

      {/* KPI tiles */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Card><CardContent className="p-3">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Total calls</p>
          <p className="text-xl font-bold" data-testid="kpi-total">{s.total || 0}</p>
        </CardContent></Card>
        <Card><CardContent className="p-3">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide flex items-center gap-1"><ArrowDownLeft size={10} /> Incoming</p>
          <p className="text-xl font-bold text-emerald-600" data-testid="kpi-incoming">{s.incoming || 0}</p>
        </CardContent></Card>
        <Card><CardContent className="p-3">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide flex items-center gap-1"><ArrowUpRight size={10} /> Outgoing</p>
          <p className="text-xl font-bold text-blue-600" data-testid="kpi-outgoing">{s.outgoing || 0}</p>
        </CardContent></Card>
        <Card><CardContent className="p-3">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide flex items-center gap-1"><PhoneMissed size={10} /> Missed</p>
          <p className="text-xl font-bold text-rose-600" data-testid="kpi-missed">{s.missed || 0}</p>
          <p className="text-[10px] text-muted-foreground">{fmtPct(s.missed_ratio)} ratio</p>
        </CardContent></Card>
        <Card><CardContent className="p-3">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide flex items-center gap-1"><Clock size={10} /> Avg duration</p>
          <p className="text-xl font-bold" data-testid="kpi-avg-duration">{fmtDuration(s.avg_duration_sec)}</p>
          <p className="text-[10px] text-muted-foreground">across answered</p>
        </CardContent></Card>
      </div>

      {/* Daily sparkline */}
      <Card><CardContent className="p-3">
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-semibold">Calls per day</p>
          <p className="text-[10px] text-muted-foreground">{(data?.daily || []).length} active day(s)</p>
        </div>
        {(data?.daily || []).length === 0 ? (
          <p className="text-[11px] text-muted-foreground py-4 text-center">No calls in this window yet.</p>
        ) : (
          <div className="flex items-end gap-0.5 h-24" data-testid="analytics-daily">
            {(data?.daily || []).map(d => {
              const h = Math.max(2, Math.round((d.total / maxDaily) * 90));
              return (
                <div key={d.date} className="flex-1 flex flex-col items-center gap-0.5 group" title={`${d.date} · ${d.total} calls (${d.incoming} in / ${d.outgoing} out / ${d.missed} missed)`}>
                  <div className="w-full bg-primary/70 hover:bg-primary rounded-t transition-all" style={{ height: `${h}%` }} />
                </div>
              );
            })}
          </div>
        )}
        <div className="flex justify-between text-[9px] text-muted-foreground mt-1">
          <span>{(data?.daily || [])[0]?.date || ''}</span>
          <span>{(data?.daily || []).slice(-1)[0]?.date || ''}</span>
        </div>
      </CardContent></Card>

      {/* Hour heatmap */}
      <Card><CardContent className="p-3">
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-semibold">Busiest hour of day</p>
          {peakHour && (
            <p className="text-[10px] text-muted-foreground">Peak: {String(peakHour.hour).padStart(2, '0')}:00 ({peakHour.count} calls)</p>
          )}
        </div>
        <div className="grid grid-cols-24 gap-0.5" style={{ gridTemplateColumns: 'repeat(24, minmax(0, 1fr))' }} data-testid="analytics-hour-heatmap">
          {(data?.busiest_hour || []).map(h => {
            const intensity = h.count === 0 ? 0 : Math.max(0.15, h.count / maxHour);
            return (
              <div key={h.hour}
                   className="aspect-square rounded-sm transition-all hover:ring-2 hover:ring-primary"
                   style={{ background: `rgba(59, 130, 246, ${intensity})` }}
                   title={`${String(h.hour).padStart(2, '0')}:00 — ${h.count} call(s)`}
              />
            );
          })}
        </div>
        <div className="flex justify-between text-[9px] text-muted-foreground mt-1">
          <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>23:00</span>
        </div>
      </CardContent></Card>

      {/* Tables */}
      <div className="grid md:grid-cols-2 gap-3">
        {/* Top numbers */}
        <Card><CardContent className="p-3">
          <p className="text-xs font-semibold flex items-center gap-1 mb-2"><Hash size={11} /> Top numbers</p>
          {(data?.top_numbers || []).length === 0 ? (
            <p className="text-[11px] text-muted-foreground">—</p>
          ) : (
            <div className="space-y-1" data-testid="analytics-top-numbers">
              {(data?.top_numbers || []).map(n => (
                <div key={n.digits} className="flex items-center gap-2 text-[11px]">
                  <span className="font-mono w-32 truncate">{n.digits}</span>
                  <span className="flex-1 text-muted-foreground truncate">{n.name || '—'}</span>
                  <span className="font-semibold">{n.count}</span>
                  <span className="text-muted-foreground w-14 text-right">{fmtDuration(n.total_duration_sec)}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent></Card>

        {/* Top contacts */}
        <Card><CardContent className="p-3">
          <p className="text-xs font-semibold flex items-center gap-1 mb-2"><Users size={11} /> Top matched contacts</p>
          {(data?.top_contacts || []).length === 0 ? (
            <p className="text-[11px] text-muted-foreground">—</p>
          ) : (
            <div className="space-y-1" data-testid="analytics-top-contacts">
              {(data?.top_contacts || []).map(c => (
                <div key={`${c.kind}-${c.id}`} className="flex items-center gap-2 text-[11px]">
                  <span className="capitalize w-16 text-muted-foreground">{c.kind || '—'}</span>
                  <span className="flex-1 truncate font-medium">{c.name || '—'}</span>
                  <span className="font-semibold">{c.count}</span>
                  <span className="text-muted-foreground w-14 text-right">{fmtDuration(c.total_duration_sec)}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent></Card>
      </div>

      {/* Top staff */}
      <Card><CardContent className="p-3">
        <p className="text-xs font-semibold flex items-center gap-1 mb-2"><Users size={11} /> Busiest staff</p>
        {(data?.top_staff || []).length === 0 ? (
          <p className="text-[11px] text-muted-foreground">—</p>
        ) : (
          <div className="space-y-1" data-testid="analytics-top-staff">
            {(data?.top_staff || []).map(u => (
              <div key={u.user_id} className="flex items-center gap-2 text-[11px]">
                <span className="flex-1 truncate font-medium">{u.name}</span>
                <span className="text-muted-foreground w-32 truncate">{u.role}</span>
                <span className="font-semibold">{u.count}</span>
                <span className="text-muted-foreground w-14 text-right">{fmtDuration(u.total_duration_sec)}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent></Card>
    </div>
  );
}
