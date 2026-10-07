import React, { useState, useCallback, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Download, FileText, RefreshCw, Banknote } from 'lucide-react';
import { toast } from 'sonner';
import api from '../../services/api';
import { dataEvents } from '../../services/dataEvents';

const money = (v) => (Number(v) || 0).toLocaleString(undefined, { minimumFractionDigits: 2 });

const download = async (path, params, filename) => {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/payroll/${path}?${qs}`, {
    headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
  });
  if (!r.ok) { toast.error('Export failed'); return; }
  const link = document.createElement('a');
  link.href = URL.createObjectURL(await r.blob());
  link.download = filename;
  link.click();
};

// What has to be paid over to URA / NSSF / the insurer, who it came from, and
// recording the payment so the liability clears itself.
export const RemittanceDialog = ({ open, onOpenChange, locationId, periods = [] }) => {
  const thisMonth = new Date().toISOString().slice(0, 7);
  const [from, setFrom] = useState(thisMonth);
  const [to, setTo] = useState(thisMonth);
  const [status, setStatus] = useState('paid');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState([]);          // line names to remit
  const [accounts, setAccounts] = useState([]);
  const [payments, setPayments] = useState([]);
  const [payOpen, setPayOpen] = useState(false);
  const [paying, setPaying] = useState(false);
  const [payForm, setPayForm] = useState({
    paid_from_account_id: '', date: new Date().toISOString().slice(0, 10),
    payee: '', reference: '', notes: '',
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rep, hist] = await Promise.all([
        api.get('/hr/payroll/remittance', {
          params: { period_from: from, period_to: to, location_id: locationId || undefined, status },
        }),
        api.get('/hr/payroll/remittance/payments', { params: { location_id: locationId || undefined } }),
      ]);
      setData(rep.data);
      setPayments(hist.data?.payments || []);
      setSelected((rep.data?.lines || []).filter(l => (l.outstanding || 0) > 0).map(l => l.name));
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not load the remittance report'); }
    finally { setLoading(false); }
  }, [from, to, status, locationId]);

  useEffect(() => { if (open) load(); }, [open, load]);

  useEffect(() => {
    if (!open) return;
    api.get('/finance/chart-of-accounts')
      .then(r => {
        const rows = Array.isArray(r.data) ? r.data : (r.data?.accounts || []);
        // Only real money accounts — paying URA out of Accounts Receivable or
        // Inventory would be nonsense.
        setAccounts(rows.filter(a => a.type === 'asset' && (a.is_cash || a.bank_subtype || /^10/.test(a.code || ''))));
      })
      .catch(() => setAccounts([]));
  }, [open]);

  const params = { period_from: from, period_to: to, location_id: locationId, status };
  const selectedTotal = (data?.lines || [])
    .filter(l => selected.includes(l.name))
    .reduce((s, l) => s + (l.outstanding || 0), 0);

  const toggle = (name) => setSelected(prev => prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name]);

  const recordPayment = async () => {
    if (!payForm.paid_from_account_id) { toast.error('Choose the account the money comes from'); return; }
    setPaying(true);
    try {
      const r = await api.post('/hr/payroll/remittance/pay', {
        ...payForm, period_from: from, period_to: to, status,
        location_id: locationId || undefined, lines: selected,
      });
      toast.success(r.data?.message || 'Remittance recorded');
      dataEvents.emit('finance-changed', { source: 'payroll_remittance' });
      setPayOpen(false);
      setPayForm(f => ({ ...f, reference: '', notes: '' }));
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not record the payment'); }
    finally { setPaying(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto" data-testid="remittance-dialog">
        <DialogHeader><DialogTitle>Statutory remittance — what we owe</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 items-end">
            <div><Label className="text-xs">From period</Label>
              <Input className="h-8 text-xs" value={from} onChange={e => setFrom(e.target.value)}
                placeholder="2026-01" data-testid="remittance-from" list="remittance-periods" />
            </div>
            <div><Label className="text-xs">To period</Label>
              <Input className="h-8 text-xs" value={to} onChange={e => setTo(e.target.value)}
                placeholder="2026-06" data-testid="remittance-to" list="remittance-periods" />
            </div>
            <datalist id="remittance-periods">{periods.map(p => <option key={p} value={p} />)}</datalist>
            <div><Label className="text-xs">Payslips</Label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger className="h-8 text-xs" data-testid="remittance-status"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="paid">Paid only</SelectItem>
                  <SelectItem value="approved">Approved</SelectItem>
                  <SelectItem value="all">All</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button size="sm" variant="secondary" className="h-8 gap-1" onClick={load} disabled={loading} data-testid="remittance-refresh">
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
            </Button>
          </div>

          {!data ? (
            <p className="text-sm text-muted-foreground text-center py-8">Loading…</p>
          ) : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
                <div className="rounded-lg border p-2"><p className="text-[10px] text-muted-foreground">Withheld from staff</p>
                  <p className="text-sm font-bold" data-testid="remittance-total-employee">{data.currency} {money(data.total_employee)}</p></div>
                <div className="rounded-lg border p-2"><p className="text-[10px] text-muted-foreground">Employer contributions</p>
                  <p className="text-sm font-bold" data-testid="remittance-total-employer">{data.currency} {money(data.total_employer)}</p></div>
                <div className="rounded-lg border p-2"><p className="text-[10px] text-muted-foreground">Already remitted</p>
                  <p className="text-sm font-bold" data-testid="remittance-total-remitted">{data.currency} {money(data.total_remitted)}</p></div>
                <div className="rounded-lg border p-2 bg-muted/40"><p className="text-[10px] text-muted-foreground">Still outstanding</p>
                  <p className="text-sm font-bold" data-testid="remittance-total">{data.currency} {money(data.total_outstanding)}</p></div>
              </div>

              <div className="rounded-md border overflow-hidden">
                <table className="w-full text-xs">
                  <thead className="bg-muted/50">
                    <tr>
                      <th className="w-7 px-2 py-1.5"></th>
                      <th className="text-left px-2 py-1.5">Statutory line</th>
                      <th className="text-left px-2 py-1.5 hidden sm:table-cell">Payable a/c</th>
                      <th className="text-right px-2 py-1.5">Withheld</th>
                      <th className="text-right px-2 py-1.5">Employer</th>
                      <th className="text-right px-2 py-1.5 hidden sm:table-cell">Remitted</th>
                      <th className="text-right px-2 py-1.5">Outstanding</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.lines || []).length === 0 && (
                      <tr><td colSpan={7} className="text-center text-muted-foreground py-5">Nothing withheld for this period yet.</td></tr>
                    )}
                    {(data.lines || []).map(l => (
                      <React.Fragment key={l.name}>
                        <tr className="border-t font-medium" data-testid={`remittance-line-${l.name}`}>
                          <td className="px-2 py-1.5">
                            <input type="checkbox" checked={selected.includes(l.name)}
                              disabled={(l.outstanding || 0) <= 0}
                              onChange={() => toggle(l.name)} data-testid={`remittance-select-${l.name}`} />
                          </td>
                          <td className="px-2 py-1.5">{l.name}
                            <span className="text-[10px] text-muted-foreground ml-1">· {l.staff_count} staff</span>
                          </td>
                          <td className="px-2 py-1.5 text-muted-foreground hidden sm:table-cell">{l.liability_account_code}</td>
                          <td className="px-2 py-1.5 text-right">{money(l.employee_withheld)}</td>
                          <td className="px-2 py-1.5 text-right">{money(l.employer_contribution)}</td>
                          <td className="px-2 py-1.5 text-right text-muted-foreground hidden sm:table-cell">{money(l.remitted)}</td>
                          <td className="px-2 py-1.5 text-right font-bold">{money(l.outstanding)}</td>
                        </tr>
                        {(l.staff || []).map(s => (
                          <tr key={`${l.name}-${s.staff_name}`} className="text-[11px] text-muted-foreground">
                            <td></td>
                            <td className="px-2 py-1 pl-4" colSpan={3}>{s.staff_name}</td>
                            <td className="px-2 py-1 text-right">{money(s.employer_contribution)}</td>
                            <td className="hidden sm:table-cell"></td>
                            <td className="px-2 py-1 text-right">{money(s.total)}</td>
                          </tr>
                        ))}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex flex-wrap gap-2 items-center">
                <Button size="sm" className="gap-1.5" disabled={selectedTotal <= 0}
                  onClick={() => setPayOpen(v => !v)} data-testid="remittance-pay-btn">
                  <Banknote size={13} /> Record payment ({data.currency} {money(selectedTotal)})
                </Button>
                <Button size="sm" variant="outline" className="gap-1.5" data-testid="remittance-csv"
                  onClick={() => download('remittance.csv', params, `statutory-remittance-${from}.csv`)}>
                  <Download size={13} /> CSV
                </Button>
                <Button size="sm" variant="outline" className="gap-1.5" data-testid="remittance-pdf"
                  onClick={() => download('remittance.pdf', params, `statutory-remittance-${from}.pdf`)}>
                  <FileText size={13} /> PDF
                </Button>
              </div>

              {payOpen && (
                <div className="rounded-lg border p-3 space-y-3 bg-muted/20" data-testid="remittance-pay-form">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <div><Label className="text-xs">Paid from *</Label>
                      <Select value={payForm.paid_from_account_id}
                        onValueChange={v => setPayForm({ ...payForm, paid_from_account_id: v })}>
                        <SelectTrigger className="h-8 text-xs" data-testid="remittance-pay-account">
                          <SelectValue placeholder="Bank or cash account" />
                        </SelectTrigger>
                        <SelectContent>
                          {accounts.map(a => <SelectItem key={a.id} value={a.id}>{a.code} · {a.name}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>
                    <div><Label className="text-xs">Payment date</Label>
                      <Input className="h-8 text-xs" type="date" value={payForm.date}
                        onChange={e => setPayForm({ ...payForm, date: e.target.value })} data-testid="remittance-pay-date" />
                    </div>
                    <div><Label className="text-xs">Paid to</Label>
                      <Input className="h-8 text-xs" placeholder="URA / NSSF / insurer" value={payForm.payee}
                        onChange={e => setPayForm({ ...payForm, payee: e.target.value })} data-testid="remittance-pay-payee" />
                    </div>
                    <div><Label className="text-xs">Receipt / filing reference</Label>
                      <Input className="h-8 text-xs" placeholder="e.g. URA PRN 123456" value={payForm.reference}
                        onChange={e => setPayForm({ ...payForm, reference: e.target.value })} data-testid="remittance-pay-reference" />
                    </div>
                  </div>
                  <div><Label className="text-xs">Notes</Label>
                    <Textarea rows={2} className="text-xs" value={payForm.notes}
                      onChange={e => setPayForm({ ...payForm, notes: e.target.value })} />
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="ghost" onClick={() => setPayOpen(false)}>Cancel</Button>
                    <Button size="sm" onClick={recordPayment} disabled={paying} data-testid="remittance-pay-submit">
                      {paying ? 'Recording…' : `Pay ${data.currency} ${money(selectedTotal)}`}
                    </Button>
                  </div>
                  <p className="text-[10px] text-muted-foreground">
                    Posts the payment against the liability account(s) and credits the account you picked, so the books show the filing as settled.
                  </p>
                </div>
              )}

              {payments.length > 0 && (
                <div className="space-y-1.5">
                  <Label className="text-xs">Filing history</Label>
                  <div className="rounded-md border divide-y" data-testid="remittance-history">
                    {payments.slice(0, 8).map(p => (
                      <div key={p.id} className="p-2 text-[11px] flex items-center justify-between gap-2">
                        <div>
                          <p className="font-medium">{p.date} · {p.payee || 'Statutory remittance'}</p>
                          <p className="text-muted-foreground">
                            {(p.lines || []).map(l => l.name).join(', ')} · from {p.paid_from_account_name}
                            {p.reference ? ` · ref ${p.reference}` : ''}
                          </p>
                        </div>
                        <span className="font-bold whitespace-nowrap">{p.currency} {money(p.total)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default RemittanceDialog;
