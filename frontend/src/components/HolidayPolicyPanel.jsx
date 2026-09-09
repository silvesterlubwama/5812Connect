import React, { useState, useEffect, useCallback } from 'react';
import { CalendarDays, RefreshCw, Info } from 'lucide-react';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { holidaysApi } from '../services/api';
import { POLICY_LABELS } from './HolidayPolicyDialog';
import { toast } from 'sonner';

const KINDS = ['paid', 'optional_paid', 'unpaid', 'hidden'];

const KIND_STYLE = {
  paid: 'bg-green-100 text-green-800 border-green-200',
  optional_paid: 'bg-amber-100 text-amber-800 border-amber-200',
  unpaid: 'bg-slate-100 text-slate-700 border-slate-200',
  hidden: 'bg-red-50 text-red-700 border-red-200',
};

const KIND_EFFECT = {
  paid: 'Hourly credited their holiday hours (stacks if they work it) · daily-wage paid the day, double if worked',
  optional_paid: 'Paid only when they take the day off · normal pay if they work it',
  unpaid: 'On the calendar for awareness · no payroll effect',
  hidden: 'Hidden from the calendar · no payroll effect',
};

/** One screen for every public holiday and how payroll treats it.
 *  Choices are stored per holiday NAME, so they hold for all future years. */
export const HolidayPolicyPanel = ({ canEdit }) => {
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(String(thisYear));
  const [country, setCountry] = useState('all');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await holidaysApi.list({ year: parseInt(year), country, include_hidden: true });
      setRows(res.data || []);
    } catch { toast.error('Could not load holidays'); }
    finally { setLoading(false); }
  }, [year, country]);
  useEffect(() => { load(); }, [load]);

  const setKind = async (row, kind) => {
    if (kind === (row.policy || 'unpaid')) return;
    setSavingKey(row.policy_key + row.date);
    try {
      if (kind === 'unpaid') await holidaysApi.resetPolicy(row.policy_key);
      else await holidaysApi.setPolicy({ name: row.name, country: row.country, kind });
      // Every occurrence of this holiday shares the policy — patch them all.
      setRows(prev => prev.map(r => (r.policy_key === row.policy_key ? { ...r, policy: kind } : r)));
      toast.success(`${row.name} → ${POLICY_LABELS[kind]} (every year)`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not save');
      load();
    } finally { setSavingKey(null); }
  };

  const counts = KINDS.reduce((acc, k) => ({ ...acc, [k]: rows.filter(r => (r.policy || 'unpaid') === k).length }), {});
  const years = [thisYear - 1, thisYear, thisYear + 1, thisYear + 2].map(String);

  return (
    <div className="space-y-4" data-testid="holiday-policy-panel">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <h2 className="text-base md:text-lg font-semibold flex items-center gap-2"><CalendarDays size={16} />Public Holidays & Pay</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Set once, applies every year. Dates keep updating themselves.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={year} onValueChange={setYear}>
            <SelectTrigger className="w-28 h-9" data-testid="holiday-year-select"><SelectValue /></SelectTrigger>
            <SelectContent>{years.map(y => <SelectItem key={y} value={y}>{y}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={country} onValueChange={setCountry}>
            <SelectTrigger className="w-36 h-9" data-testid="holiday-country-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All countries</SelectItem>
              <SelectItem value="US">US federal</SelectItem>
              <SelectItem value="UG">Uganda public</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" className="h-9" onClick={load} data-testid="holiday-refresh"><RefreshCw size={14} /></Button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
        {KINDS.map(k => (
          <Card key={k} className="shadow-none">
            <CardContent className="p-3">
              <p className="text-2xl font-semibold" data-testid={`holiday-count-${k}`}>{counts[k] ?? 0}</p>
              <p className="text-xs font-medium mt-0.5">{POLICY_LABELS[k]}</p>
              <p className="text-[10px] text-muted-foreground mt-1 leading-snug">{KIND_EFFECT[k]}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {!canEdit && (
        <p className="flex items-start gap-2 text-xs text-muted-foreground">
          <Info size={13} className="mt-0.5 shrink-0" />Only an admin can change how a holiday is paid.
        </p>
      )}

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-4 space-y-2">{[1, 2, 3, 4, 5].map(i => <div key={i} className="h-10 bg-muted animate-pulse rounded" />)}</div>
          ) : rows.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-10">No holidays for this selection.</p>
          ) : (
            <div className="divide-y divide-border">
              {rows.map(r => {
                const kind = r.policy || 'unpaid';
                const d = new Date(r.date + 'T00:00:00');
                const busy = savingKey === r.policy_key + r.date;
                return (
                  <div key={`${r.country}-${r.date}-${r.name}`} className="flex flex-col sm:flex-row sm:items-center gap-2 p-3" data-testid={`holiday-row-${r.policy_key}`}>
                    <div className="sm:w-32 shrink-0">
                      <p className="text-sm font-medium">{d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</p>
                      <p className="text-[11px] text-muted-foreground">{d.toLocaleDateString('en-US', { weekday: 'long' })}</p>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{r.name}</p>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <Badge variant="outline" className="text-[10px]">{r.country === 'US' ? 'US federal' : 'Uganda public'}</Badge>
                        <Badge variant="outline" className={`text-[10px] ${KIND_STYLE[kind]}`}>{POLICY_LABELS[kind]}</Badge>
                      </div>
                    </div>
                    <div className="sm:w-52 shrink-0">
                      <Select value={kind} onValueChange={v => setKind(r, v)} disabled={!canEdit || busy}>
                        <SelectTrigger className="h-9" data-testid={`holiday-kind-${r.policy_key}`}><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {KINDS.map(k => <SelectItem key={k} value={k}>{POLICY_LABELS[k]}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default HolidayPolicyPanel;
