/**
 * ShipmentDonorPage — public, token-gated.
 *
 * Visitors with the link see:
 *   • Shipment header (name, destination, target ship date)
 *   • Live container-fill progress bar
 *   • "Still needed" list (sorted urgent → low priority)
 *   • "Already on the truck" list (donors' hard work)
 *   • Per-item "I'll donate" button that pops a quantity + optional name picker
 *
 * No login required, no email captured. Donor name is optional and free-text.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Container, Heart, Sparkles, ChevronDown, ChevronUp, Truck, CheckCircle2 } from 'lucide-react';
import api from '../services/api';
import { toast } from 'sonner';
import EmptyState from '../components/EmptyState';
import { useBranding } from '../context/BrandingContext';
import ContainerVisualizer from '../components/ContainerVisualizer';

const PRIORITY_BADGE = {
  urgent: 'bg-rose-100 text-rose-700',
  high: 'bg-amber-100 text-amber-700',
  normal: 'bg-slate-100 text-slate-600',
  low: 'bg-slate-50 text-slate-500',
};

export default function ShipmentDonorPage() {
  const { token } = useParams();
  const { branding } = useBranding();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showAI, setShowAI] = useState(false);
  const [pickItem, setPickItem] = useState(null);
  const [donateForm, setDonateForm] = useState({ qty: 1, donor_name: '' });

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get(`/public/shipments/${token}`);
      setData(r.data);
      setError(null);
    } catch (e) {
      setError(e.response?.status === 404 ? 'This link is no longer valid.' : 'Could not load the shipment.');
      setData(null);
    } finally { setLoading(false); }
  }, [token]);

  useEffect(() => { refresh(); }, [refresh]);

  const submitDonation = async () => {
    if (!pickItem) return;
    const qty = parseInt(donateForm.qty) || 0;
    if (qty <= 0) { toast.error('Pick at least 1'); return; }
    try {
      const r = await api.post(`/public/shipments/${token}/items/${pickItem.id}/donate`, {
        qty,
        donor_name: (donateForm.donor_name || '').trim() || undefined,
      });
      toast.success(r.data?.message || 'Thank you!');
      setPickItem(null);
      setDonateForm({ qty: 1, donor_name: '' });
      await refresh();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not record donation'); }
  };

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center"><p className="text-sm text-muted-foreground">Loading shipment…</p></div>;
  }
  if (error || !data) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <Card className="max-w-md rounded-xl">
          <CardContent className="p-6 text-center">
            <Container size={36} className="mx-auto text-muted-foreground/40 mb-2" />
            <h1 className="text-lg font-semibold mb-1">Link unavailable</h1>
            <p className="text-sm text-muted-foreground">{error || 'Could not load this shipment.'}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const t = data.totals || {};

  return (
    <div className="min-h-screen bg-background" data-testid="shipment-donor-page">
      {/* Header bar */}
      <div className="border-b bg-card">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center gap-3">
          {branding?.logo_url && <img src={branding.logo_url} alt={branding?.app_name || '58:12'} className="h-8 w-auto" />}
          <div className="flex-1 min-w-0">
            <p className="text-[11px] text-muted-foreground uppercase tracking-wide">{branding?.app_name || '58:12 Global'} · Container shipment</p>
            <h1 className="text-lg font-semibold truncate" data-testid="ship-donor-name">{data.name}</h1>
          </div>
          <Badge variant="outline" className="text-[10px] capitalize">{data.status}</Badge>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 py-5 space-y-5">
        {/* Hero progress */}
        <Card className="rounded-xl">
          <CardContent className="p-4 space-y-3">
            <div className="flex items-center gap-3 flex-wrap">
              <Truck size={20} className="text-primary shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm">Bound for <strong>{data.dest_country}</strong>{data.target_ship_date && <span> · ship by <strong>{data.target_ship_date}</strong></span>}</p>
                {data.description && <p className="text-xs text-muted-foreground mt-1">{data.description}</p>}
              </div>
            </div>
            <div className="space-y-1.5" data-testid="ship-donor-progress">
              <div className="flex items-center justify-between text-xs">
                <span><strong>{t.weight_kg?.toLocaleString() || 0} kg</strong> in the truck · {t.weight_pct || 0}% full</span>
                <span className="text-muted-foreground">{t.items_acquired || 0} items covered · {t.items_needed || 0} still needed</span>
              </div>
              <div className="h-3 rounded-full bg-muted overflow-hidden">
                <div className={`h-full ${(t.weight_pct || 0) > 100 ? 'bg-rose-500' : (t.weight_pct || 0) > 80 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                  style={{ width: `${Math.min(100, t.weight_pct || 0)}%` }} />
              </div>
              {t.value_usd > 0 && <p className="text-[11px] text-muted-foreground">Estimated value contributed: <strong>${t.value_usd.toLocaleString()}</strong></p>}
            </div>
          </CardContent>
        </Card>

        {/* Container visualization (3D by default — let donors see what's in the truck) */}
        {((data.already_acquired || []).length > 0 || (data.still_needed || []).length > 0) && (
          <ContainerVisualizer
            items={[...(data.already_acquired || []), ...(data.still_needed || [])]}
            pallets={data.pallets || []}
            defaultMode="3d"
          />
        )}

        {/* Still needed */}
        <section>
          <h2 className="text-sm font-semibold mb-2 flex items-center gap-1.5"><Heart size={13} className="text-rose-500" /> Still needed ({(data.still_needed || []).length})</h2>
          {(data.still_needed || []).length === 0 ? (
            <EmptyState compact icon={CheckCircle2} title="Everything is covered 🎉" description="Thanks to the donor community, every item on this shipment's wishlist is on its way." testid="ship-donor-needed-empty" />
          ) : (
            <div className="space-y-2" data-testid="ship-donor-needed">
              {(data.still_needed || []).map(it => (
                <Card key={it.id} className="rounded-lg" data-testid={`ship-donor-needed-${it.id}`}>
                  <CardContent className="p-3 flex items-center gap-3 flex-wrap">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-medium truncate">{it.name}</p>
                        {it.category && <Badge variant="outline" className="text-[10px]">{it.category}</Badge>}
                        <Badge className={`text-[10px] capitalize ${PRIORITY_BADGE[it.priority] || ''}`}>{it.priority}</Badge>
                      </div>
                      <p className="text-[11px] text-muted-foreground">
                        <strong className="text-foreground">{it.qty_remaining}</strong> of {it.qty_needed} still needed
                        {it.weight_kg ? ` · ${it.weight_kg} kg each` : ''}
                        {it.value_usd ? ` · ~$${it.value_usd}/unit` : ''}
                      </p>
                      {it.notes && <p className="text-[10px] text-muted-foreground italic mt-0.5">{it.notes}</p>}
                    </div>
                    <Button size="sm" onClick={() => { setPickItem(it); setDonateForm({ qty: Math.min(1, it.qty_remaining), donor_name: '' }); }} data-testid={`ship-donor-pledge-${it.id}`}>
                      <Heart size={11} className="mr-1" /> I'll donate
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </section>

        {/* Already acquired */}
        {(data.already_acquired || []).length > 0 && (
          <section>
            <h2 className="text-sm font-semibold mb-2 flex items-center gap-1.5"><CheckCircle2 size={13} className="text-emerald-600" /> Already on the truck ({data.already_acquired.length})</h2>
            <div className="space-y-1.5" data-testid="ship-donor-acquired">
              {data.already_acquired.map(it => (
                <Card key={it.id} className="rounded-lg bg-emerald-50/30">
                  <CardContent className="p-2 flex items-center gap-2">
                    <CheckCircle2 size={12} className="text-emerald-600 shrink-0" />
                    <p className="text-xs truncate flex-1">
                      <span className="font-medium">{it.qty_acquired}× {it.name}</span>
                      {it.category && <span className="text-muted-foreground"> · {it.category}</span>}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </section>
        )}

        {/* AI packing — collapsible */}
        {data.ai_packing_text && (
          <section>
            <button onClick={() => setShowAI(s => !s)} className="w-full text-left flex items-center justify-between p-3 rounded-lg border hover:bg-muted/30" data-testid="ship-donor-ai-toggle">
              <span className="text-sm font-medium flex items-center gap-1.5"><Sparkles size={13} className="text-primary" /> Container packing plan (AI generated)</span>
              {showAI ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
            {showAI && (
              <Card className="rounded-lg mt-1" data-testid="ship-donor-ai-text">
                <CardContent className="p-3">
                  <pre className="text-[11px] whitespace-pre-wrap font-mono text-muted-foreground">{data.ai_packing_text}</pre>
                  {data.ai_packing_generated_at && (
                    <p className="text-[10px] text-muted-foreground mt-2">Last refreshed {new Date(data.ai_packing_generated_at).toLocaleDateString()}</p>
                  )}
                </CardContent>
              </Card>
            )}
          </section>
        )}

        <p className="text-center text-[11px] text-muted-foreground pt-4">
          Powered by {branding?.app_name || '58:12 Connect'}
        </p>
      </div>

      {/* Donate dialog */}
      <Dialog open={!!pickItem} onOpenChange={(o) => { if (!o) setPickItem(null); }}>
        <DialogContent className="max-w-sm" data-testid="ship-donor-dialog">
          <DialogHeader>
            <DialogTitle>Confirm donation</DialogTitle>
            <DialogDescription className="text-xs">No account needed — just tell us how many you can bring.</DialogDescription>
          </DialogHeader>
          {pickItem && (
            <div className="space-y-3 mt-1">
              <Card className="rounded-lg bg-muted/30"><CardContent className="p-2.5">
                <p className="text-sm font-medium">{pickItem.name}</p>
                <p className="text-[11px] text-muted-foreground">{pickItem.qty_remaining} of {pickItem.qty_needed} still needed</p>
              </CardContent></Card>
              <div className="space-y-1">
                <label className="text-xs font-medium">How many can you donate?</label>
                <Input type="number" min="1" max={pickItem.qty_remaining}
                  value={donateForm.qty} onChange={e => setDonateForm({ ...donateForm, qty: e.target.value })}
                  data-testid="ship-donor-qty" />
                <p className="text-[10px] text-muted-foreground">We'll cap at {pickItem.qty_remaining} (what's still needed).</p>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium">Your name <span className="opacity-60">(optional)</span></label>
                <Input value={donateForm.donor_name} onChange={e => setDonateForm({ ...donateForm, donor_name: e.target.value })}
                  placeholder="Anonymous" data-testid="ship-donor-name-input" />
                <p className="text-[10px] text-muted-foreground">Leave blank to donate anonymously.</p>
              </div>
              <div className="flex gap-2 pt-1">
                <Button variant="ghost" className="flex-1" onClick={() => setPickItem(null)}>Cancel</Button>
                <Button className="flex-1" onClick={submitDonation} data-testid="ship-donor-confirm">
                  <Heart size={12} className="mr-1" /> Confirm
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
