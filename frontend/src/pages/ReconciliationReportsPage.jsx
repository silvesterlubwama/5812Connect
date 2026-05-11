import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Badge } from '../components/ui/badge';
import api from '../services/api';
import { toast } from 'sonner';
import { TrendingDown, AlertTriangle, Calendar, RefreshCw } from 'lucide-react';

const fmt = (n) => (Number(n) || 0).toLocaleString();

/**
 * ReconciliationReportsPage — Daily Cash Reconciliation + Payroll Reconciliation.
 * For admin/director close-out and audit prep.
 */
export default function ReconciliationReportsPage() {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [cashData, setCashData] = useState(null);
  const [payrollData, setPayrollData] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadCash = async () => {
    setLoading(true);
    try {
      const r = await api.get('/cash-reconciliation/daily', { params: { date } });
      setCashData(r.data);
    } catch (e) { toast.error('Failed to load cash report'); }
    finally { setLoading(false); }
  };

  const loadPayroll = async () => {
    setLoading(true);
    try {
      const r = await api.get('/payroll-reconciliation', { params: { period } });
      setPayrollData(r.data);
    } catch (e) { toast.error('Failed to load payroll report'); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadCash(); }, []); // eslint-disable-line

  return (
    <div className="container mx-auto px-4 py-6 max-w-5xl space-y-5">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><TrendingDown size={22} /> Reconciliation Reports</h1>
        <p className="text-sm text-muted-foreground mt-1">Daily cash reconciliation + monthly payroll reconciliation — for end-of-period close-out & audit.</p>
      </div>

      <Tabs defaultValue="cash">
        <TabsList>
          <TabsTrigger value="cash" data-testid="tab-cash">Daily Cash</TabsTrigger>
          <TabsTrigger value="payroll" data-testid="tab-payroll">Payroll</TabsTrigger>
        </TabsList>

        <TabsContent value="cash" className="space-y-4 mt-4">
          <Card className="rounded-xl">
            <CardContent className="p-4 flex items-end gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Date</Label>
                <Input type="date" value={date} onChange={e => setDate(e.target.value)} className="h-9" data-testid="cash-date-input" />
              </div>
              <Button onClick={loadCash} disabled={loading} className="h-9 gap-1.5" data-testid="cash-load-btn">
                <RefreshCw size={14} /> Load
              </Button>
            </CardContent>
          </Card>

          {cashData && (
            <>
              <div className="grid sm:grid-cols-4 gap-3">
                <Card className="rounded-xl"><CardContent className="p-4 text-center"><p className="text-xs text-muted-foreground uppercase tracking-wider">Cash Sales</p><p className="text-xl font-bold text-green-700 mt-1">{fmt(cashData.totals?.cash_sales)}</p></CardContent></Card>
                <Card className="rounded-xl"><CardContent className="p-4 text-center"><p className="text-xs text-muted-foreground uppercase tracking-wider">Cash Drops</p><p className="text-xl font-bold text-blue-700 mt-1">{fmt(cashData.totals?.cash_drops)}</p></CardContent></Card>
                <Card className="rounded-xl"><CardContent className="p-4 text-center"><p className="text-xs text-muted-foreground uppercase tracking-wider">Expected</p><p className="text-xl font-bold mt-1">{fmt(cashData.totals?.expected)}</p></CardContent></Card>
                <Card className={`rounded-xl border-2 ${Math.abs(cashData.totals?.variance || 0) < 1 ? 'border-green-300' : 'border-amber-300'}`}><CardContent className="p-4 text-center"><p className="text-xs text-muted-foreground uppercase tracking-wider">Variance</p><p className={`text-xl font-bold mt-1 ${Math.abs(cashData.totals?.variance || 0) < 1 ? 'text-green-700' : 'text-amber-700'}`}>{cashData.totals?.variance > 0 ? '+' : ''}{fmt(cashData.totals?.variance)}</p></CardContent></Card>
              </div>

              {cashData.flagged_cashiers?.length > 0 && (
                <Card className="rounded-xl border-amber-300 bg-amber-50/30">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2"><AlertTriangle size={16} className="text-amber-600" /> Flagged Cashiers</CardTitle>
                    <CardDescription className="text-xs">3+ negative shifts in the last 30 days — review for training or fraud.</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-1">
                    {cashData.flagged_cashiers.map((c, i) => (
                      <div key={i} className="flex items-center justify-between text-sm" data-testid={`flagged-${c.cashier_id}`}>
                        <span className="font-medium">{c.cashier_name}</span>
                        <Badge className="bg-amber-100 text-amber-800">{c.neg_shifts_30d} neg shifts/30d</Badge>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}

              <Card className="rounded-xl">
                <CardHeader className="pb-2"><CardTitle className="text-sm">Per Cashier ({cashData.by_cashier?.length || 0})</CardTitle></CardHeader>
                <CardContent className="p-0 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-muted/40"><tr><th className="text-left p-2">Cashier</th><th className="text-right p-2">Shifts</th><th className="text-right p-2">Sales</th><th className="text-right p-2">Drops</th><th className="text-right p-2">Expected</th><th className="text-right p-2">Counted</th><th className="text-right p-2">Variance</th></tr></thead>
                    <tbody className="divide-y">
                      {(cashData.by_cashier || []).map((c, i) => (
                        <tr key={i} data-testid={`cashier-row-${c.cashier_id}`}>
                          <td className="p-2 font-medium">{c.cashier_name || 'Unknown'}</td>
                          <td className="text-right p-2">{c.shifts}</td>
                          <td className="text-right p-2 text-green-700">{fmt(c.cash_sales)}</td>
                          <td className="text-right p-2 text-blue-700">{fmt(c.cash_drops)}</td>
                          <td className="text-right p-2">{fmt(c.expected)}</td>
                          <td className="text-right p-2">{fmt(c.counted)}</td>
                          <td className={`text-right p-2 font-semibold ${Math.abs(c.variance) < 1 ? 'text-green-700' : c.variance > 0 ? 'text-amber-700' : 'text-red-700'}`}>{c.variance > 0 ? '+' : ''}{fmt(c.variance)}</td>
                        </tr>
                      ))}
                      {(cashData.by_cashier || []).length === 0 && (
                        <tr><td colSpan={7} className="p-6 text-center text-muted-foreground">No closed shifts on this date.</td></tr>
                      )}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            </>
          )}
        </TabsContent>

        <TabsContent value="payroll" className="space-y-4 mt-4">
          <Card className="rounded-xl">
            <CardContent className="p-4 flex items-end gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Period (YYYY-MM)</Label>
                <Input type="month" value={period} onChange={e => setPeriod(e.target.value)} className="h-9" data-testid="payroll-period-input" />
              </div>
              <Button onClick={loadPayroll} disabled={loading} className="h-9 gap-1.5" data-testid="payroll-load-btn">
                <RefreshCw size={14} /> Load
              </Button>
            </CardContent>
          </Card>

          {payrollData && (
            <Card className="rounded-xl">
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                  <Calendar size={14} /> Payroll Reconciliation — {payrollData.period}
                  {payrollData.is_balanced ? <Badge className="bg-green-100 text-green-700">Balanced</Badge> : <Badge className="bg-amber-100 text-amber-700">Variance!</Badge>}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">Paid payslips ({payrollData.paid_payslips_count})</span><span className="font-medium">{fmt(payrollData.paid_payslips_total)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Aggregated expense lines ({payrollData.aggregated_expense_count})</span><span className="font-medium">{fmt(payrollData.aggregated_expense_total)}</span></div>
                <div className={`flex justify-between border-t pt-2 font-bold text-base ${payrollData.is_balanced ? 'text-green-700' : 'text-amber-700'}`} data-testid="payroll-variance">
                  <span>Variance</span><span>{payrollData.variance > 0 ? '+' : ''}{fmt(payrollData.variance)}</span>
                </div>
                <p className="text-[11px] text-muted-foreground pt-2">
                  {payrollData.is_balanced
                    ? '✓ Aggregated expense matches sum of paid payslips.'
                    : 'Variance detected — investigate manually adjusted expenses or payslips with missing aggregation.'}
                </p>
                {payrollData.expense_dates?.length > 0 && (
                  <p className="text-[10px] text-muted-foreground">Expense dates: {payrollData.expense_dates.join(', ')}</p>
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
