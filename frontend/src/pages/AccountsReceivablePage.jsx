import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import api from '../services/api';
import { toast } from 'sonner';
import { MessageSquare, Phone, Mail, ExternalLink, Search, AlertCircle, RefreshCw, Calendar, X } from 'lucide-react';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { useAuth } from '../context/AuthContext';

const fmt = (n, c = 'UGX') => `${c} ${(Number(n) || 0).toLocaleString()}`;
const daysAgo = (dt) => Math.floor((Date.now() - new Date(dt).getTime()) / (1000 * 60 * 60 * 24));

const TIER_META = {
  1: { label: 'Reminder 1', cls: 'bg-amber-100 text-amber-800 border-amber-300' },
  2: { label: 'Reminder 2', cls: 'bg-orange-100 text-orange-800 border-orange-300' },
  3: { label: 'FINAL', cls: 'bg-red-100 text-red-800 border-red-300' },
};

/**
 * AccountsReceivablePage — list pending non-cash sales aggregated by customer.
 * 1-click WhatsApp / SMS reminder; click into customer to see all their open sales.
 */
export default function AccountsReceivablePage() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [promiseFor, setPromiseFor] = useState(null);
  const [promiseForm, setPromiseForm] = useState({ promised_date: '', promised_amount: '', note: '' });

  const fetchData = () => {
    setLoading(true);
    api.get('/accounts-receivable')
      .then(r => setData(r.data))
      .catch(() => toast.error('Failed to load AR'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(); }, []);

  if (!user) return null;

  const filtered = (data?.by_customer || []).filter(c => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (c.customer_name || '').toLowerCase().includes(s) || (c.customer_phone || '').includes(s);
  });

  const sendWhatsApp = (c) => {
    if (!c.customer_phone) { toast.error('No phone number on file'); return; }
    const lines = [
      `Hi ${c.customer_name}, this is a friendly reminder about ${c.sales_count} outstanding payment${c.sales_count === 1 ? '' : 's'} totalling ${fmt(c.total)}:`,
      ...c.sales.slice(0, 5).map(s => `· ${s.receipt_number} (${s.created_at?.slice(0, 10)}): ${fmt(s.total)}`),
      '',
      'Could you confirm settlement at your convenience? Thanks!',
      '— 58:12 Global',
    ];
    const msg = encodeURIComponent(lines.join('\n'));
    window.open(`https://wa.me/${c.customer_phone.replace(/\D/g, '')}?text=${msg}`, '_blank');
  };

  return (
    <div className="container mx-auto px-4 py-6 space-y-5 max-w-5xl">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <AlertCircle size={22} className="text-amber-600" /> Accounts Receivable
          </h1>
          <p className="text-sm text-muted-foreground mt-1">Pending non-cash sales aggregated by customer — send a 1-click reminder.</p>
        </div>
        <Button variant="outline" size="sm" className="gap-1.5" onClick={fetchData} data-testid="ar-refresh"><RefreshCw size={14} /> Refresh</Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Card className="rounded-xl"><CardContent className="p-4 text-center">
          <p className="text-xs text-muted-foreground uppercase tracking-wider">Total Outstanding</p>
          <p className="text-3xl font-bold text-amber-700 mt-1" data-testid="ar-total">{fmt(data?.total_outstanding || 0)}</p>
        </CardContent></Card>
        <Card className="rounded-xl"><CardContent className="p-4 text-center">
          <p className="text-xs text-muted-foreground uppercase tracking-wider">Customers</p>
          <p className="text-3xl font-bold mt-1">{data?.customer_count || 0}</p>
        </CardContent></Card>
        <Card className="rounded-xl"><CardContent className="p-4 text-center">
          <p className="text-xs text-muted-foreground uppercase tracking-wider">Sales Outstanding</p>
          <p className="text-3xl font-bold mt-1">{(data?.by_customer || []).reduce((s, c) => s + c.sales_count, 0)}</p>
        </CardContent></Card>
      </div>

      <div className="relative max-w-md">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input className="pl-9" placeholder="Search by name or phone..." value={search} onChange={e => setSearch(e.target.value)} data-testid="ar-search" />
      </div>

      {loading ? (
        <div className="space-y-2">{[1, 2, 3].map(i => <div key={i} className="h-24 bg-muted animate-pulse rounded-xl" />)}</div>
      ) : filtered.length === 0 ? (
        <Card className="rounded-xl border-dashed"><CardContent className="p-10 text-center text-sm text-muted-foreground">
          🎉 No outstanding non-cash sales. All settled.
        </CardContent></Card>
      ) : (
        <div className="space-y-3">
          {filtered.map((c, i) => {
            const aged = daysAgo(c.oldest_date);
            const isOverdue = aged > 14;
            const tier = c.last_reminder?.tier;
            const tierMeta = tier ? TIER_META[tier] : null;
            const promise = c.payment_promise;
            const promiseActive = promise && new Date(promise.promised_date) >= new Date();
            return (
              <Card key={i} className={`rounded-xl ${promiseActive ? 'border-emerald-300 bg-emerald-50/30' : isOverdue ? 'border-amber-300 bg-amber-50/30' : ''}`} data-testid={`ar-customer-${i}`}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between flex-wrap gap-2">
                    <div>
                      <CardTitle className="text-base">{c.customer_name}</CardTitle>
                      <CardDescription className="text-xs mt-0.5">
                        {c.customer_phone && <span className="mr-2">📞 {c.customer_phone}</span>}
                        <span>{c.sales_count} pending · oldest {aged} day{aged === 1 ? '' : 's'} ago</span>
                        {isOverdue && !promiseActive && <Badge className="ml-2 bg-amber-100 text-amber-700 hover:bg-amber-200">overdue</Badge>}
                        {tierMeta && <Badge className={`ml-2 ${tierMeta.cls}`} variant="outline" data-testid={`ar-tier-${i}`}>{tierMeta.label}</Badge>}
                        {promiseActive && (
                          <Badge className="ml-2 bg-emerald-100 text-emerald-800 border-emerald-300" variant="outline" data-testid={`ar-promise-${i}`}>
                            Promised {promise.promised_date.slice(0, 10)}
                            {promise.promised_amount ? ` · ${fmt(promise.promised_amount)}` : ''}
                          </Badge>
                        )}
                      </CardDescription>
                    </div>
                    <div className="text-right">
                      <p className="text-2xl font-bold text-amber-700">{fmt(c.total)}</p>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="pt-0 space-y-2">
                  <div className="space-y-1">
                    {c.sales.slice(0, 3).map((s, j) => (
                      <div key={j} className="flex items-center justify-between text-xs">
                        <span className="font-mono">{s.receipt_number}</span>
                        <span className="text-muted-foreground">{s.created_at?.slice(0, 10)} · <span className="capitalize">{s.payment_method}</span></span>
                        <span className="font-medium">{fmt(s.total)}</span>
                      </div>
                    ))}
                    {c.sales.length > 3 && <p className="text-[10px] text-muted-foreground">+ {c.sales.length - 3} more...</p>}
                  </div>
                  <div className="flex gap-2 pt-2 border-t flex-wrap">
                    {c.customer_phone && (
                      <Button size="sm" variant="outline" className="gap-1.5 h-8 text-xs flex-1 min-w-[120px]" onClick={() => sendWhatsApp(c)} data-testid={`ar-whatsapp-${i}`}>
                        <MessageSquare size={12} /> WhatsApp
                      </Button>
                    )}
                    <Button size="sm" variant="outline" className="gap-1.5 h-8 text-xs flex-1 min-w-[120px]" onClick={async () => {
                      try {
                        const cust_key = c.customer_id || c.customer_name;
                        const res = await api.post('/payment-reminders/send', { customer_id_or_name: cust_key });
                        toast.success(`Reminder sent to ${res.data.sent_to}`);
                        fetchData();
                      } catch (e) {
                        if ((e.response?.data?.detail || '').includes('last 7 days')) {
                          if (!window.confirm('A reminder was sent in the last 7 days. Send anyway?')) return;
                          try {
                            const cust_key = c.customer_id || c.customer_name;
                            const res = await api.post('/payment-reminders/send', { customer_id_or_name: cust_key, force: true });
                            toast.success(`Reminder sent to ${res.data.sent_to}`);
                            fetchData();
                          } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
                        } else { toast.error(e.response?.data?.detail || 'No email on file'); }
                      }
                    }} data-testid={`ar-email-${i}`}>
                      <Mail size={12} /> Email Reminder
                    </Button>
                    {promiseActive ? (
                      <Button size="sm" variant="outline" className="gap-1.5 h-8 text-xs" data-testid={`ar-promise-clear-${i}`} onClick={async () => {
                        const cust_key = c.customer_id || c.customer_name;
                        try {
                          await api.delete(`/accounts-receivable/promise/${encodeURIComponent(cust_key)}`);
                          toast.success('Promise cleared');
                          fetchData();
                        } catch { toast.error('Failed'); }
                      }}>
                        <X size={12} /> Clear Promise
                      </Button>
                    ) : (
                      <Button size="sm" variant="outline" className="gap-1.5 h-8 text-xs" data-testid={`ar-promise-${i}`} onClick={() => {
                        setPromiseFor(c);
                        setPromiseForm({ promised_date: '', promised_amount: '', note: '' });
                      }}>
                        <Calendar size={12} /> Mark Promised
                      </Button>
                    )}
                    {c.customer_phone && (
                      <a href={`tel:${c.customer_phone}`} className="inline-flex">
                        <Button size="sm" variant="outline" className="gap-1.5 h-8 text-xs">
                          <Phone size={12} /> Call
                        </Button>
                      </a>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Payment Promise Dialog */}
      <Dialog open={!!promiseFor} onOpenChange={(o) => { if (!o) setPromiseFor(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Mark Payment Promised — {promiseFor?.customer_name}</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <p className="text-xs text-muted-foreground">Pauses reminder emails until the promised date. Outstanding total: <strong>{fmt(promiseFor?.total)}</strong>.</p>
            <div className="space-y-1">
              <Label className="text-xs">Promised Date *</Label>
              <Input type="date" value={promiseForm.promised_date} onChange={e => setPromiseForm({...promiseForm, promised_date: e.target.value})} data-testid="promise-date-input" min={new Date().toISOString().slice(0, 10)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Promised Amount (optional)</Label>
              <Input type="number" placeholder="Full balance if blank" value={promiseForm.promised_amount} onChange={e => setPromiseForm({...promiseForm, promised_amount: e.target.value})} data-testid="promise-amount-input" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Note (optional)</Label>
              <Input placeholder="e.g. spoke to John, paying via bank" value={promiseForm.note} onChange={e => setPromiseForm({...promiseForm, note: e.target.value})} data-testid="promise-note-input" />
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setPromiseFor(null)}>Cancel</Button>
              <Button className="flex-1" data-testid="promise-save-btn" disabled={!promiseForm.promised_date} onClick={async () => {
                try {
                  const cust_key = promiseFor.customer_id || promiseFor.customer_name;
                  await api.post('/accounts-receivable/promise', {
                    customer_key: cust_key,
                    promised_date: promiseForm.promised_date,
                    promised_amount: promiseForm.promised_amount ? parseFloat(promiseForm.promised_amount) : undefined,
                    note: promiseForm.note,
                  });
                  toast.success('Promise recorded — reminders paused');
                  setPromiseFor(null);
                  fetchData();
                } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
              }}>Save Promise</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
