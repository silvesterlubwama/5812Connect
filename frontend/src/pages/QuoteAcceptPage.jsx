import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../services/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { CheckCircle2, ShieldCheck } from 'lucide-react';

const fmt = (n, c = 'UGX') => `${c} ${(Number(n) || 0).toLocaleString()}`;
const LOGO_URL = 'https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1';

/**
 * QuoteAcceptPage — public page customers reach via /quote/:quoteNumber/accept
 * Shows quote details, then asks for verification (phone-last-4 or email),
 * then flips the quote to "accepted" + spawns a draft invoice for staff to finalise.
 */
export default function QuoteAcceptPage() {
  const { quoteNumber } = useParams();
  const [quote, setQuote] = useState(null);
  const [error, setError] = useState(null);
  const [verification, setVerification] = useState('');
  const [accepting, setAccepting] = useState(false);
  const [accepted, setAccepted] = useState(false);

  useEffect(() => {
    api.get(`/public/quotes/${encodeURIComponent(quoteNumber)}`)
      .then(r => {
        setQuote(r.data);
        if (r.data.status === 'accepted') setAccepted(true);
      })
      .catch((e) => setError(e.response?.data?.detail || 'Quote not found'));
  }, [quoteNumber]);

  const handleAccept = async () => {
    if (!verification.trim()) return;
    setAccepting(true);
    try {
      const res = await api.post(`/public/quotes/${encodeURIComponent(quoteNumber)}/accept`, { verification: verification.trim() });
      setAccepted(true);
      setQuote(q => ({ ...q, status: 'accepted', accepted_at: res.data.accepted_at }));
    } catch (e) {
      setError(e.response?.data?.detail || 'Could not accept quote');
    } finally { setAccepting(false); }
  };

  if (error) return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100 p-4">
      <Card className="max-w-md w-full">
        <CardContent className="p-8 text-center">
          <p className="text-lg font-bold text-red-600">Quote Not Available</p>
          <p className="text-sm text-slate-500 mt-2">{error}</p>
        </CardContent>
      </Card>
    </div>
  );

  if (!quote) return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100">
      <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  );

  const currency = quote.items?.[0]?.currency || 'UGX';

  return (
    <div className="min-h-screen bg-slate-100 p-4 flex items-center justify-center">
      <div className="w-full max-w-2xl space-y-4">
        <div className="text-center pt-4">
          <img src={LOGO_URL} alt="58:12 Global" className="h-10 mx-auto" />
        </div>
        <Card className="rounded-xl shadow-lg" data-testid="quote-accept-card">
          <CardHeader className="bg-gradient-to-br from-primary to-primary/80 text-primary-foreground rounded-t-xl">
            <CardTitle className="flex items-center justify-between">
              <span>QUOTE</span>
              <Badge className="bg-white/20 text-primary-foreground hover:bg-white/30 border-0">{quote.status}</Badge>
            </CardTitle>
            <p className="font-mono text-sm opacity-90 mt-1">{quote.invoice_number}</p>
            <p className="text-xs opacity-70">Issued by {quote.issued_by_name} · {quote.created_at?.slice(0, 10)}</p>
          </CardHeader>
          <CardContent className="space-y-4 pt-5">
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">For</p>
              <p className="font-semibold mt-0.5">{quote.customer_name}</p>
              {quote.customer_phone && <p className="text-xs">{quote.customer_phone}</p>}
            </div>

            <div className="border rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted/40">
                  <tr><th className="text-left p-2">Item</th><th className="text-right p-2">Qty</th><th className="text-right p-2">Unit</th><th className="text-right p-2">Total</th></tr>
                </thead>
                <tbody className="divide-y">
                  {(quote.items || []).map((it, i) => (
                    <tr key={i}>
                      <td className="p-2">{it.name}</td>
                      <td className="text-right p-2">{it.qty}</td>
                      <td className="text-right p-2">{(it.unit_price || 0).toLocaleString()}</td>
                      <td className="text-right p-2 font-medium">{((it.qty || 0) * (it.unit_price || 0)).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {quote.discount > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-center">
                <p className="text-xs uppercase tracking-wider text-amber-700">You save</p>
                <p className="text-lg font-bold text-amber-900">{fmt(quote.discount, currency)}</p>
              </div>
            )}

            <div className="bg-primary/5 rounded-lg p-3 flex justify-between items-center">
              <span className="text-sm font-semibold">TOTAL</span>
              <span className="text-2xl font-bold text-primary">{fmt(quote.total, currency)}</span>
            </div>

            {quote.notes && (
              <div className="bg-muted/30 rounded-lg p-3">
                <p className="text-xs uppercase tracking-wider text-muted-foreground">Notes</p>
                <p className="text-sm mt-1 whitespace-pre-wrap">{quote.notes}</p>
              </div>
            )}

            {accepted ? (
              <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-center" data-testid="quote-accepted-banner">
                <CheckCircle2 size={32} className="mx-auto text-green-600 mb-2" />
                <p className="font-bold text-green-700">Quote Accepted</p>
                <p className="text-xs text-green-600 mt-1">Our team will be in touch shortly to finalise the sale.</p>
                {quote.accepted_at && <p className="text-[10px] text-green-500 mt-1">Accepted: {new Date(quote.accepted_at).toLocaleString()}</p>}
              </div>
            ) : (
              <div className="space-y-2 pt-2 border-t">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <ShieldCheck size={14} /> Verify it's you to accept this quote
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Your phone number OR email on this quote</Label>
                  <Input
                    placeholder="+256... or you@example.com"
                    value={verification}
                    onChange={(e) => setVerification(e.target.value)}
                    data-testid="quote-verify-input"
                  />
                </div>
                <Button
                  className="w-full"
                  size="lg"
                  disabled={!verification.trim() || accepting}
                  onClick={handleAccept}
                  data-testid="quote-accept-btn"
                >
                  {accepting ? 'Confirming...' : 'Accept Quote'}
                </Button>
                <p className="text-[10px] text-muted-foreground text-center">By accepting, you authorise 58:12 Global to convert this quote into a sale at the prices shown.</p>
              </div>
            )}
          </CardContent>
        </Card>

        <p className="text-[10px] text-center text-muted-foreground">58:12 Global · Trusted partner in your community.</p>
      </div>
    </div>
  );
}
