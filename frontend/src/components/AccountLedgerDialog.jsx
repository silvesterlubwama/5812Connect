import React, { useCallback, useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight, Printer, RefreshCw } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import api from '../services/api';
import { toast } from 'sonner';

const firstOfMonth = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`;
const lastOfMonth = (d) => {
  const e = new Date(d.getFullYear(), d.getMonth() + 1, 0);
  return `${e.getFullYear()}-${String(e.getMonth() + 1).padStart(2, '0')}-${String(e.getDate()).padStart(2, '0')}`;
};

// Per-account ledger so an account holder can audit themselves: every entry
// for or against the account in a month, with the opening balance carried in
// and a running balance out. Page back through previous months.
export function AccountLedgerDialog({ accountId, accountLabel, locationId, open, onOpenChange }) {
  const [anchor, setAnchor] = useState(() => new Date());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (d) => {
    if (!accountId) return;
    setLoading(true);
    try {
      const params = { date_from: firstOfMonth(d), date_to: lastOfMonth(d) };
      if (locationId && locationId !== 'all') params.location_id = locationId;
      const r = await api.get(`/finance/chart-of-accounts/${accountId}/ledger`, { params });
      setData(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not load the account ledger');
    } finally { setLoading(false); }
  }, [accountId, locationId]);

  useEffect(() => { if (open) load(anchor); }, [open, anchor, load]);

  const money = (v) => Number(v || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const monthLabel = anchor.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
  const thisMonth = firstOfMonth(anchor) >= firstOfMonth(new Date());

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto" data-testid="account-ledger-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {data?.account ? `${data.account.code} · ${data.account.name}` : accountLabel || 'Account ledger'}
            {data?.account && <Badge variant="outline" className="text-[10px] capitalize">{data.account.type}</Badge>}
          </DialogTitle>
          <DialogDescription>Every transaction for or against this account. Page back to audit earlier months.</DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setAnchor(new Date(anchor.getFullYear(), anchor.getMonth() - 1, 1))} data-testid="ledger-prev-month"><ChevronLeft size={14} /></Button>
            <span className="text-sm font-medium min-w-[9rem] text-center" data-testid="ledger-month-label">{monthLabel}</span>
            <Button variant="outline" size="sm" disabled={thisMonth} onClick={() => setAnchor(new Date(anchor.getFullYear(), anchor.getMonth() + 1, 1))} data-testid="ledger-next-month"><ChevronRight size={14} /></Button>
            <Button variant="ghost" size="sm" onClick={() => load(anchor)} data-testid="ledger-refresh"><RefreshCw size={14} /></Button>
          </div>
          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => window.print()} data-testid="ledger-print"><Printer size={14} /> Print</Button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
          <div className="rounded-lg bg-accent/40 p-2.5"><p className="text-xs text-muted-foreground">Opening</p><p className="font-semibold font-mono" data-testid="ledger-opening">{money(data?.opening_balance)}</p></div>
          <div className="rounded-lg bg-accent/40 p-2.5"><p className="text-xs text-muted-foreground">Debits</p><p className="font-semibold font-mono">{money(data?.total_debit)}</p></div>
          <div className="rounded-lg bg-accent/40 p-2.5"><p className="text-xs text-muted-foreground">Credits</p><p className="font-semibold font-mono">{money(data?.total_credit)}</p></div>
          <div className="rounded-lg bg-accent/40 p-2.5"><p className="text-xs text-muted-foreground">Closing</p><p className="font-semibold font-mono" data-testid="ledger-closing">{money(data?.closing_balance)}</p></div>
        </div>

        {loading && <div className="h-24 animate-pulse bg-muted rounded-lg" />}

        {!loading && (data?.rows || []).length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-8" data-testid="ledger-empty">Nothing posted to this account in {monthLabel}.</p>
        )}

        {!loading && (data?.rows || []).length > 0 && (
          <table className="w-full text-sm border-collapse" data-testid="ledger-table">
            <thead>
              <tr className="bg-muted/40 text-xs uppercase text-muted-foreground">
                <th className="text-left px-2 py-2 font-medium">Date</th>
                <th className="text-left px-2 py-2 font-medium">Description</th>
                <th className="text-left px-2 py-2 font-medium">Contra</th>
                <th className="text-right px-2 py-2 font-medium">Debit</th>
                <th className="text-right px-2 py-2 font-medium">Credit</th>
                <th className="text-right px-2 py-2 font-medium">Balance</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r, i) => (
                <tr key={`${r.je_id}-${i}`} className="border-t hover:bg-muted/20" data-testid={`ledger-row-${i}`}>
                  <td className="px-2 py-1.5 whitespace-nowrap">{r.date}</td>
                  <td className="px-2 py-1.5">{r.description}{r.reference ? <span className="text-xs text-muted-foreground"> · {r.reference}</span> : null}</td>
                  <td className="px-2 py-1.5 text-xs text-muted-foreground">{(r.counterparts || []).map(c => c.code).filter(Boolean).join(', ')}</td>
                  <td className="px-2 py-1.5 text-right font-mono">{r.debit ? money(r.debit) : ''}</td>
                  <td className="px-2 py-1.5 text-right font-mono">{r.credit ? money(r.credit) : ''}</td>
                  <td className="px-2 py-1.5 text-right font-mono font-medium">{money(r.balance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default AccountLedgerDialog;
