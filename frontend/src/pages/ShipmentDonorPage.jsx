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
import { Container, Heart, Sparkles, ChevronDown, ChevronUp, Truck, CheckCircle2, KeyRound, LogOut, Pencil, Trophy, Clock, Layers, Trash2, Ruler, Plus, X, ScanLine, FileText, Camera, Loader2 } from 'lucide-react';
import api from '../services/api';
import { toast } from 'sonner';
import EmptyState from '../components/EmptyState';
import { useBranding } from '../context/BrandingContext';
import ContainerVisualizer from '../components/ContainerVisualizer';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Textarea } from '../components/ui/textarea';

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
  // ─── Editor-PIN session ────────────────────────────────────────
  const [editToken, setEditToken] = useState(() => {
    try { return localStorage.getItem(`ship-edit-token:${token}`) || null; } catch { return null; }
  });
  const [showLogin, setShowLogin] = useState(false);
  const [pinInput, setPinInput] = useState('');
  const [showScanner, setShowScanner] = useState(false);
  const [scanBusy, setScanBusy] = useState(false);
  const [scanResult, setScanResult] = useState(null);  // result from /scan-item
  const [scanImages, setScanImages] = useState([]);    // File[] for upload
  const [loginBusy, setLoginBusy] = useState(false);
  // ─── PIN-scoped editing ────────────────────────────────────────
  const [editingItem, setEditingItem] = useState(null);   // existing or {} for new
  const [editingPallet, setEditingPallet] = useState(null);
  const [showContainerEdit, setShowContainerEdit] = useState(false);
  const [containerForm, setContainerForm] = useState({ length_cm: 1203, width_cm: 235, height_cm: 269, max_payload_kg: 26000 });
  // shorthand for authenticated request headers
  const authHeaders = () => editToken ? { 'X-Shipment-Edit-Token': editToken } : {};

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

  // ─── Editor login flow ───────────────────────────────────────────
  const submitLogin = async () => {
    setLoginBusy(true);
    try {
      const r = await api.post(`/public/shipments/${token}/login`, { pin: pinInput.trim() });
      try { localStorage.setItem(`ship-edit-token:${token}`, r.data.edit_token); } catch { /* ignore */ }
      setEditToken(r.data.edit_token);
      toast.success(`Editor session unlocked — ${r.data.ttl_hours}h`);
      setShowLogin(false); setPinInput('');
    } catch (e) { toast.error(e.response?.data?.detail || 'Incorrect PIN'); }
    finally { setLoginBusy(false); }
  };
  const logoutEditor = () => {
    try { localStorage.removeItem(`ship-edit-token:${token}`); } catch { /* ignore */ }
    setEditToken(null);
    toast.success('Editor session ended');
  };

  // ─── Editor-only mutations (all go through PIN-scoped endpoints) ─
  const saveItemEdit = async () => {
    if (!editingItem) return;
    const isNew = !editingItem.id;
    try {
      const url = isNew
        ? `/public/shipments/${token}/items`
        : `/public/shipments/${token}/items/${editingItem.id}`;
      const method = isNew ? api.post : api.put;
      await method(url, {
        name: editingItem.name,
        category: editingItem.category,
        priority: editingItem.priority,
        qty_needed: Number(editingItem.qty_needed) || 1,
        qty_acquired: Number(editingItem.qty_acquired) || 0,
        weight_kg: Number(editingItem.weight_kg) || 0,
        value_usd: Number(editingItem.value_usd) || 0,
        dims_cm: {
          length: Number(editingItem.dims_cm?.length) || 0,
          width: Number(editingItem.dims_cm?.width) || 0,
          height: Number(editingItem.dims_cm?.height) || 0,
        },
        pallet_id: editingItem.pallet_id || null,
        x_cm: Number(editingItem.x_cm) || 0,
        y_cm: Number(editingItem.y_cm) || 0,
        z_cm: Number(editingItem.z_cm) || 0,
        notes: editingItem.notes || '',
      }, { headers: authHeaders() });
      toast.success(isNew ? 'Item added' : 'Item updated');
      setEditingItem(null);
      await refresh();
    } catch (e) {
      if (e.response?.status === 401) { logoutEditor(); toast.error('Session expired — log in again'); }
      else toast.error(e.response?.data?.detail || 'Save failed');
    }
  };
  const deleteItem = async (itemId) => {
    if (!window.confirm('Delete this item?')) return;
    try {
      await api.delete(`/public/shipments/${token}/items/${itemId}`, { headers: authHeaders() });
      toast.success('Item deleted');
      await refresh();
    } catch (e) { toast.error(e.response?.data?.detail || 'Delete failed'); }
  };
  const savePallet = async () => {
    if (!editingPallet) return;
    const isNew = !editingPallet.id;
    const payload = {
      label: editingPallet.label,
      notes: editingPallet.notes || '',
      length_cm: Number(editingPallet.length_cm) || 120,
      width_cm: Number(editingPallet.width_cm) || 80,
      height_cm: Number(editingPallet.height_cm) || 150,
      x_cm: Number(editingPallet.x_cm) || 0,
      y_cm: Number(editingPallet.y_cm) || 0,
      color: editingPallet.color || '',
    };
    try {
      if (isNew) await api.post(`/public/shipments/${token}/pallets`, payload, { headers: authHeaders() });
      else await api.put(`/public/shipments/${token}/pallets/${editingPallet.id}`, payload, { headers: authHeaders() });
      toast.success(isNew ? 'Pallet added' : 'Pallet updated');
      setEditingPallet(null);
      await refresh();
    } catch (e) { toast.error(e.response?.data?.detail || 'Save failed'); }
  };
  const deletePallet = async (pid) => {
    if (!window.confirm('Delete this pallet? Items will be unassigned.')) return;
    try {
      await api.delete(`/public/shipments/${token}/pallets/${pid}`, { headers: authHeaders() });
      await refresh();
    } catch (e) { toast.error(e.response?.data?.detail || 'Delete failed'); }
  };
  const saveContainer = async () => {
    try {
      await api.put(`/public/shipments/${token}/container`, containerForm, { headers: authHeaders() });
      toast.success('Container dimensions saved');
      setShowContainerEdit(false);
      await refresh();
    } catch (e) { toast.error(e.response?.data?.detail || 'Save failed'); }
  };
  const movePallet = async (pid, x_cm, y_cm) => {
    try {
      await api.put(`/public/shipments/${token}/pallets/${pid}`, {
        x_cm: Math.round(x_cm), y_cm: Math.round(y_cm),
      }, { headers: authHeaders() });
      await refresh();
    } catch (e) { toast.error(e.response?.data?.detail || 'Move failed'); }
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
  const isEditor = !!editToken;
  // Countdown to target_ship_date
  const daysUntilShip = (() => {
    if (!data.target_ship_date) return null;
    const target = new Date(data.target_ship_date + 'T00:00:00Z');
    const now = new Date();
    const ms = target.getTime() - now.getTime();
    return Math.ceil(ms / (1000 * 60 * 60 * 24));
  })();

  return (
    <div className="min-h-screen bg-background" data-testid="shipment-donor-page">
      {/* Header bar */}
      <div className="border-b bg-card">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center gap-3 flex-wrap">
          {branding?.logo_url && <img src={branding.logo_url} alt={branding?.app_name || '58:12'} className="h-8 w-auto" />}
          <div className="flex-1 min-w-0">
            <p className="text-[11px] text-muted-foreground uppercase tracking-wide">{branding?.app_name || '58:12 Global'} · Container shipment</p>
            <h1 className="text-lg font-semibold truncate" data-testid="ship-donor-name">{data.name}</h1>
          </div>
          <Badge variant="outline" className="text-[10px] capitalize">{data.status}</Badge>
          {/* PIN-login button (only when the shipment has a PIN configured) */}
          {data.pin_required && !isEditor && (
            <Button size="sm" variant="outline" onClick={() => setShowLogin(true)} data-testid="ship-donor-login">
              <KeyRound size={12} className="mr-1" /> Editor login
            </Button>
          )}
          {isEditor && (
            <Button
              size="sm"
              variant="default"
              onClick={() => setShowScanner(true)}
              data-testid="ship-donor-open-scanner"
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              <ScanLine size={12} className="mr-1" /> Scan item
            </Button>
          )}
          {isEditor && (
            <Button size="sm" variant="outline"
              onClick={() => window.open(`${process.env.REACT_APP_BACKEND_URL}/api/public/shipments/${token}/waybill?edit_token=${encodeURIComponent(editToken || '')}`, '_blank')}
              data-testid="ship-donor-waybill"
              title="Open printable waybill in new tab"
            >
              <FileText size={12} className="mr-1" /> Waybill
            </Button>
          )}
          {isEditor && (
            <Badge className="bg-emerald-100 text-emerald-700 text-[10px]" data-testid="ship-donor-editor-badge">
              <Pencil size={9} className="mr-1" /> Edit mode
            </Badge>
          )}
          {isEditor && (
            <Button size="sm" variant="ghost" onClick={logoutEditor} title="End editor session" data-testid="ship-donor-logout">
              <LogOut size={12} />
            </Button>
          )}
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
            {/* At-a-glance stat row */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1" data-testid="ship-donor-stats">
              <div className="rounded-lg border bg-muted/30 p-2 text-center">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Pallets</p>
                <p className="text-sm font-semibold flex items-center justify-center gap-1"><Layers size={11} /> {t.pallet_count || 0}</p>
              </div>
              <div className="rounded-lg border bg-muted/30 p-2 text-center">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Donors</p>
                <p className="text-sm font-semibold flex items-center justify-center gap-1"><Heart size={11} className="text-rose-500" /> {t.donor_count || 0}</p>
              </div>
              <div className="rounded-lg border bg-muted/30 p-2 text-center">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Items in</p>
                <p className="text-sm font-semibold flex items-center justify-center gap-1"><CheckCircle2 size={11} className="text-emerald-600" /> {t.items_acquired || 0}</p>
              </div>
              <div className="rounded-lg border bg-muted/30 p-2 text-center" data-testid="ship-donor-countdown">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Ship in</p>
                <p className={`text-sm font-semibold flex items-center justify-center gap-1 ${daysUntilShip != null && daysUntilShip < 7 ? 'text-rose-700' : ''}`}>
                  <Clock size={11} /> {daysUntilShip == null ? '—' : daysUntilShip < 0 ? `${-daysUntilShip}d overdue` : `${daysUntilShip}d`}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Donor leaderboard */}
        {(t.leaderboard || []).length > 0 && (
          <Card className="rounded-xl" data-testid="ship-donor-leaderboard">
            <CardContent className="p-3 space-y-1.5">
              <p className="text-sm font-semibold flex items-center gap-1.5"><Trophy size={13} className="text-amber-500" /> Top contributors</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                {(t.leaderboard || []).map((row, idx) => (
                  <div key={row.donor_name} className="flex items-center gap-2 text-xs">
                    <span className="text-muted-foreground w-5 text-right">{idx + 1}.</span>
                    <span className="flex-1 truncate font-medium">{row.donor_name}</span>
                    <Badge variant="outline" className="text-[10px]">{row.total_qty} items</Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Editor toolbar — shows when logged in with PIN */}
        {isEditor && (
          <Card className="rounded-xl border-primary/30 bg-primary/5" data-testid="ship-donor-editor-bar">
            <CardContent className="p-3 flex items-center gap-2 flex-wrap">
              <p className="text-xs font-semibold flex items-center gap-1"><Pencil size={11} /> Editor tools</p>
              <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={() => setEditingItem({ name: '', category: '', priority: 'normal', qty_needed: 1, qty_acquired: 0, weight_kg: 0, value_usd: 0, dims_cm: { length: 0, width: 0, height: 0 }, x_cm: 0, y_cm: 0, z_cm: 0, notes: '' })} data-testid="ship-donor-add-item">
                <Plus size={10} className="mr-1" /> Item
              </Button>
              <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={() => setEditingPallet({ label: '', notes: '', length_cm: 120, width_cm: 80, height_cm: 150, x_cm: 0, y_cm: 0, color: '#10b981' })} data-testid="ship-donor-add-pallet">
                <Layers size={10} className="mr-1" /> Pallet
              </Button>
              <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={() => {
                const c = data.container_dims_cm || {};
                setContainerForm({
                  length_cm: c.length_cm || 1203, width_cm: c.width_cm || 235,
                  height_cm: c.height_cm || 269, max_payload_kg: c.max_payload_kg || data.max_payload_kg || 26000,
                });
                setShowContainerEdit(true);
              }} data-testid="ship-donor-edit-container">
                <Ruler size={10} className="mr-1" /> Container
              </Button>
              <p className="text-[10px] text-muted-foreground ml-auto">Click items below to edit · drag pallets on the 2D viz to reposition.</p>
            </CardContent>
          </Card>
        )}

        {/* Container visualization (3D by default — let donors see what's in the truck) */}
        {((data.already_acquired || []).length > 0 || (data.still_needed || []).length > 0) && (
          <ContainerVisualizer
            items={[...(data.already_acquired || []), ...(data.still_needed || [])]}
            pallets={data.pallets || []}
            container={data.container_dims_cm}
            defaultMode="3d"
            editable={isEditor}
            onPalletMove={isEditor ? movePallet : undefined}
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
                      <Heart size={11} className="mr-1" /> I&apos;ll donate
                    </Button>
                    {isEditor && (
                      <>
                        <Button size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={() => setEditingItem({ ...it })} data-testid={`ship-donor-edit-${it.id}`}><Pencil size={11} /></Button>
                        <Button size="sm" variant="ghost" className="h-8 w-8 p-0 text-rose-600" onClick={() => deleteItem(it.id)} data-testid={`ship-donor-del-${it.id}`}><Trash2 size={11} /></Button>
                      </>
                    )}
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

      {/* Editor login dialog */}
      <Dialog open={showLogin} onOpenChange={(o) => { if (!o) { setShowLogin(false); setPinInput(''); } }}>
        <DialogContent className="max-w-sm" data-testid="ship-donor-login-dialog">
          <DialogHeader>
            <DialogTitle>Editor sign-in</DialogTitle>
            <DialogDescription className="text-xs">
              Enter the PIN your admin shared with you. You&apos;ll be able to edit items, pallets, and container settings for this shipment for 12 hours.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 mt-2">
            <div className="space-y-1"><Label className="text-xs">Shipment PIN</Label>
              <Input type="password" value={pinInput} onChange={e => setPinInput(e.target.value)}
                placeholder="••••••••" autoFocus
                onKeyDown={e => e.key === 'Enter' && submitLogin()}
                data-testid="ship-donor-pin-input" />
            </div>
            <div className="flex gap-2 pt-1">
              <Button variant="ghost" className="flex-1" onClick={() => { setShowLogin(false); setPinInput(''); }}>Cancel</Button>
              <Button className="flex-1" onClick={submitLogin} disabled={loginBusy || !pinInput.trim()} data-testid="ship-donor-pin-submit">
                {loginBusy ? 'Signing in…' : 'Sign in'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* AI Scanner dialog (editor-only) */}
      <Dialog open={showScanner} onOpenChange={(o) => { if (!o) { setShowScanner(false); setScanResult(null); setScanImages([]); } }}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto" data-testid="ship-donor-scanner-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><ScanLine size={16} /> Scan an item</DialogTitle>
            <DialogDescription className="text-xs">Take 1–3 photos — book cover, barcode, label or general shot. AI identifies title, ISBN/UPC, category, dimensions, and estimated value.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            {!scanResult && (
              <>
                <label className="block">
                  <div className="border-2 border-dashed rounded-xl p-6 text-center hover:bg-muted/30 cursor-pointer" data-testid="ship-donor-scan-dropzone">
                    <Camera size={32} className="mx-auto text-muted-foreground mb-2" />
                    <p className="text-sm font-semibold">Tap to take a photo</p>
                    <p className="text-[10px] text-muted-foreground">or pick up to 3 images</p>
                  </div>
                  <input type="file" accept="image/*" capture="environment" multiple className="hidden"
                    onChange={e => setScanImages(Array.from(e.target.files || []).slice(0, 3))}
                    data-testid="ship-donor-scan-files" />
                </label>
                {scanImages.length > 0 && (
                  <div className="flex gap-1 flex-wrap" data-testid="ship-donor-scan-previews">
                    {scanImages.map((f, i) => (
                      <div key={i} className="w-20 h-20 border rounded overflow-hidden bg-muted">
                        <img src={URL.createObjectURL(f)} alt="" className="w-full h-full object-cover" />
                      </div>
                    ))}
                  </div>
                )}
                <Button
                  className="w-full bg-emerald-600 hover:bg-emerald-700"
                  disabled={scanBusy || scanImages.length === 0}
                  onClick={async () => {
                    setScanBusy(true);
                    try {
                      const fd = new FormData();
                      scanImages.forEach(f => fd.append('images', f));
                      const r = await api.post(`/public/shipments/${token}/scan-item`, fd, {
                        headers: { 'Content-Type': 'multipart/form-data', 'X-Shipment-Edit-Token': editToken || '' },
                      });
                      setScanResult(r.data);
                    } catch (e) {
                      toast.error(e.response?.data?.detail || 'Scan failed');
                    } finally {
                      setScanBusy(false);
                    }
                  }}
                  data-testid="ship-donor-scan-submit"
                >
                  {scanBusy ? <><Loader2 size={12} className="mr-1 animate-spin" /> Identifying…</> : <><Sparkles size={12} className="mr-1" /> Identify with AI</>}
                </Button>
              </>
            )}
            {scanResult && (
              <div className="space-y-2" data-testid="ship-donor-scan-result">
                <div className="rounded-lg border p-3 space-y-1 bg-muted/30">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Identified</p>
                  <p className="text-base font-semibold">{scanResult.name || 'Unknown'}</p>
                  {scanResult.author && <p className="text-xs">by {scanResult.author}</p>}
                  <div className="flex items-center gap-1 flex-wrap">
                    <Badge variant="outline" className="text-[10px]">{scanResult.category}</Badge>
                    {scanResult.isbn && <Badge variant="outline" className="text-[10px]">ISBN {scanResult.isbn}</Badge>}
                    {scanResult.upc && <Badge variant="outline" className="text-[10px]">UPC {scanResult.upc}</Badge>}
                    {scanResult.ai_identified && <Badge className="text-[10px] bg-amber-100 text-amber-800">AI · {scanResult.ai_confidence}</Badge>}
                    {scanResult.source && <Badge className="text-[10px] bg-blue-100 text-blue-800">{scanResult.source}</Badge>}
                  </div>
                  <p className="text-[11px] text-muted-foreground">~{scanResult.dims_cm?.length}×{scanResult.dims_cm?.width}×{scanResult.dims_cm?.height} cm · {scanResult.weight_kg} kg · ~${scanResult.value_usd}</p>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Place in</Label>
                  <Select value={scanResult.container_type || 'container'} onValueChange={v => setScanResult({ ...scanResult, container_type: v })}>
                    <SelectTrigger data-testid="ship-donor-scan-container-type"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="container">Directly in container (loose)</SelectItem>
                      <SelectItem value="pallet">On a pallet</SelectItem>
                      <SelectItem value="box">In a box</SelectItem>
                      <SelectItem value="tote">In a tote</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {(scanResult.container_type === 'pallet' || scanResult.container_type === 'box' || scanResult.container_type === 'tote') && (data.pallets || []).length > 0 && (
                  <div className="space-y-1">
                    <Label className="text-xs">Pallet/Box/Tote</Label>
                    <Select value={scanResult.pallet_id || ''} onValueChange={v => setScanResult({ ...scanResult, pallet_id: v })}>
                      <SelectTrigger data-testid="ship-donor-scan-pallet"><SelectValue placeholder="Pick…" /></SelectTrigger>
                      <SelectContent>
                        {(data.pallets || []).map(p => <SelectItem key={p.id} value={p.id}>{p.label || p.id.slice(0, 8)}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                )}
                {(data.items || []).length > 0 && scanResult.container_type !== 'container' && (
                  <div className="space-y-1">
                    <Label className="text-xs">Stack on top of (optional)</Label>
                    <Select value={scanResult.parent_id || '__none__'} onValueChange={v => setScanResult({ ...scanResult, parent_id: v === '__none__' ? null : v })}>
                      <SelectTrigger data-testid="ship-donor-scan-parent"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">— (place on floor of pallet)</SelectItem>
                        {(data.items || []).filter(it => it.pallet_id === scanResult.pallet_id).map(it => (
                          <SelectItem key={it.id} value={it.id}>{it.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
                <div className="flex gap-2 pt-2">
                  <Button variant="ghost" className="flex-1" onClick={() => { setScanResult(null); setScanImages([]); }} data-testid="ship-donor-scan-rescan">
                    Rescan
                  </Button>
                  <Button
                    className="flex-1 bg-emerald-600 hover:bg-emerald-700"
                    disabled={scanBusy || !scanResult.name}
                    onClick={async () => {
                      setScanBusy(true);
                      try {
                        await api.post(`/public/shipments/${token}/items`, {
                          ...scanResult,
                          qty_acquired: 1,
                          qty_needed: 1,
                        }, { headers: { 'X-Shipment-Edit-Token': editToken || '' } });
                        toast.success('Item added to shipment');
                        await refresh();
                        setScanResult(null);
                        setScanImages([]);
                        setShowScanner(false);
                      } catch (e) {
                        toast.error(e.response?.data?.detail || 'Save failed');
                      } finally {
                        setScanBusy(false);
                      }
                    }}
                    data-testid="ship-donor-scan-confirm"
                  >
                    {scanBusy ? <Loader2 size={12} className="animate-spin" /> : <>Add to shipment</>}
                  </Button>
                </div>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Item editor (editor-only) */}
      <Dialog open={!!editingItem} onOpenChange={(o) => { if (!o) setEditingItem(null); }}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="ship-donor-item-dialog">
          <DialogHeader>
            <DialogTitle>{editingItem?.id ? `Edit — ${editingItem?.name}` : 'New item'}</DialogTitle>
          </DialogHeader>
          {editingItem && (
            <div className="space-y-2 mt-2">
              <div className="space-y-1"><Label className="text-xs">Name *</Label>
                <Input value={editingItem.name || ''} onChange={e => setEditingItem({ ...editingItem, name: e.target.value })} data-testid="ship-donor-item-name" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">Category</Label>
                  <Input value={editingItem.category || ''} onChange={e => setEditingItem({ ...editingItem, category: e.target.value })} />
                </div>
                <div className="space-y-1"><Label className="text-xs">Priority</Label>
                  <Select value={editingItem.priority || 'normal'} onValueChange={v => setEditingItem({ ...editingItem, priority: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>{['urgent', 'high', 'normal', 'low'].map(p => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">Qty needed</Label>
                  <Input type="number" value={editingItem.qty_needed || 1} onChange={e => setEditingItem({ ...editingItem, qty_needed: parseInt(e.target.value) || 1 })} />
                </div>
                <div className="space-y-1"><Label className="text-xs">Qty acquired</Label>
                  <Input type="number" value={editingItem.qty_acquired || 0} onChange={e => setEditingItem({ ...editingItem, qty_acquired: parseInt(e.target.value) || 0 })} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">Weight (kg/unit)</Label>
                  <Input type="number" step="0.01" value={editingItem.weight_kg || 0} onChange={e => setEditingItem({ ...editingItem, weight_kg: parseFloat(e.target.value) || 0 })} />
                </div>
                <div className="space-y-1"><Label className="text-xs">Value ($/unit)</Label>
                  <Input type="number" step="0.01" value={editingItem.value_usd || 0} onChange={e => setEditingItem({ ...editingItem, value_usd: parseFloat(e.target.value) || 0 })} />
                </div>
              </div>
              <div className="space-y-1"><Label className="text-xs">Dims (cm) L × W × H</Label>
                <div className="grid grid-cols-3 gap-2">
                  <Input type="number" value={editingItem.dims_cm?.length || 0} onChange={e => setEditingItem({ ...editingItem, dims_cm: { ...editingItem.dims_cm, length: parseFloat(e.target.value) || 0 } })} />
                  <Input type="number" value={editingItem.dims_cm?.width || 0} onChange={e => setEditingItem({ ...editingItem, dims_cm: { ...editingItem.dims_cm, width: parseFloat(e.target.value) || 0 } })} />
                  <Input type="number" value={editingItem.dims_cm?.height || 0} onChange={e => setEditingItem({ ...editingItem, dims_cm: { ...editingItem.dims_cm, height: parseFloat(e.target.value) || 0 } })} />
                </div>
              </div>
              {(data.pallets || []).length > 0 && (
                <div className="space-y-1"><Label className="text-xs">Pallet</Label>
                  <Select value={editingItem.pallet_id || 'none'} onValueChange={v => setEditingItem({ ...editingItem, pallet_id: v === 'none' ? null : v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">— Unassigned (loose) —</SelectItem>
                      {(data.pallets || []).map(p => <SelectItem key={p.id} value={p.id}>{p.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              )}
              <div className="space-y-1"><Label className="text-xs">Notes</Label>
                <Textarea rows={2} value={editingItem.notes || ''} onChange={e => setEditingItem({ ...editingItem, notes: e.target.value })} />
              </div>
              <div className="flex gap-2 pt-2">
                <Button variant="ghost" className="flex-1" onClick={() => setEditingItem(null)}>Cancel</Button>
                <Button className="flex-1" onClick={saveItemEdit} data-testid="ship-donor-item-save">Save</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Pallet editor (editor-only) */}
      <Dialog open={!!editingPallet} onOpenChange={(o) => { if (!o) setEditingPallet(null); }}>
        <DialogContent className="max-w-md" data-testid="ship-donor-pallet-dialog">
          <DialogHeader>
            <DialogTitle>{editingPallet?.id ? 'Edit pallet' : 'New pallet'}</DialogTitle>
          </DialogHeader>
          {editingPallet && (
            <div className="space-y-2 mt-2">
              <div className="space-y-1"><Label className="text-xs">Label *</Label>
                <Input value={editingPallet.label || ''} onChange={e => setEditingPallet({ ...editingPallet, label: e.target.value })} data-testid="ship-donor-pallet-label" />
              </div>
              <div className="space-y-1"><Label className="text-xs">Footprint (cm) L × W × H</Label>
                <div className="grid grid-cols-3 gap-2">
                  <Input type="number" value={editingPallet.length_cm} onChange={e => setEditingPallet({ ...editingPallet, length_cm: parseFloat(e.target.value) || 0 })} />
                  <Input type="number" value={editingPallet.width_cm} onChange={e => setEditingPallet({ ...editingPallet, width_cm: parseFloat(e.target.value) || 0 })} />
                  <Input type="number" value={editingPallet.height_cm} onChange={e => setEditingPallet({ ...editingPallet, height_cm: parseFloat(e.target.value) || 0 })} />
                </div>
              </div>
              <div className="space-y-1"><Label className="text-xs">Position (X, Y cm from back-left)</Label>
                <div className="grid grid-cols-2 gap-2">
                  <Input type="number" value={editingPallet.x_cm} onChange={e => setEditingPallet({ ...editingPallet, x_cm: parseFloat(e.target.value) || 0 })} />
                  <Input type="number" value={editingPallet.y_cm} onChange={e => setEditingPallet({ ...editingPallet, y_cm: parseFloat(e.target.value) || 0 })} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">Color</Label>
                  <Input type="color" value={editingPallet.color || '#10b981'} onChange={e => setEditingPallet({ ...editingPallet, color: e.target.value })} className="h-9" />
                </div>
                <div className="space-y-1"><Label className="text-xs">Notes</Label>
                  <Input value={editingPallet.notes || ''} onChange={e => setEditingPallet({ ...editingPallet, notes: e.target.value })} />
                </div>
              </div>
              <div className="flex gap-2 pt-2">
                {editingPallet.id && <Button variant="ghost" className="text-rose-700" onClick={() => { setEditingPallet(null); deletePallet(editingPallet.id); }}><X size={11} className="mr-1" /> Delete</Button>}
                <Button variant="ghost" className="flex-1" onClick={() => setEditingPallet(null)}>Cancel</Button>
                <Button className="flex-1" onClick={savePallet} data-testid="ship-donor-pallet-save">Save</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Container dims editor (editor-only) */}
      <Dialog open={showContainerEdit} onOpenChange={setShowContainerEdit}>
        <DialogContent className="max-w-md" data-testid="ship-donor-container-dialog">
          <DialogHeader>
            <DialogTitle>Container dimensions</DialogTitle>
            <DialogDescription className="text-xs">Default = 40&apos; high-cube (1203 × 235 × 269 cm).</DialogDescription>
          </DialogHeader>
          <div className="space-y-2 mt-2">
            <div className="grid grid-cols-3 gap-2">
              <div className="space-y-1"><Label className="text-xs">L (cm)</Label>
                <Input type="number" value={containerForm.length_cm} onChange={e => setContainerForm({ ...containerForm, length_cm: parseFloat(e.target.value) || 0 })} />
              </div>
              <div className="space-y-1"><Label className="text-xs">W (cm)</Label>
                <Input type="number" value={containerForm.width_cm} onChange={e => setContainerForm({ ...containerForm, width_cm: parseFloat(e.target.value) || 0 })} />
              </div>
              <div className="space-y-1"><Label className="text-xs">H (cm)</Label>
                <Input type="number" value={containerForm.height_cm} onChange={e => setContainerForm({ ...containerForm, height_cm: parseFloat(e.target.value) || 0 })} />
              </div>
            </div>
            <div className="space-y-1"><Label className="text-xs">Max payload (kg)</Label>
              <Input type="number" value={containerForm.max_payload_kg} onChange={e => setContainerForm({ ...containerForm, max_payload_kg: parseFloat(e.target.value) || 0 })} />
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="ghost" className="flex-1" onClick={() => setShowContainerEdit(false)}>Cancel</Button>
              <Button className="flex-1" onClick={saveContainer} data-testid="ship-donor-container-save">Save</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
