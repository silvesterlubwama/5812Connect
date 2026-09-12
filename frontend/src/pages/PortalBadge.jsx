import React, { useEffect, useRef, useState } from 'react';
import { IdCard, Download, Printer, RefreshCw, Ticket, ZoomIn } from 'lucide-react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { UnifiedBadge, BadgeZoomDialog } from '../components/UnifiedBadge';
import api from '../services/api';
import { toast } from 'sonner';

// The member-facing badge. Uses the SAME <UnifiedBadge /> render as the wallet
// page so what you see here is what prints.
export default function PortalBadge() {
  const [badge, setBadge] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [zoomUrl, setZoomUrl] = useState(null);
  const [zooming, setZooming] = useState(false);
  const badgeRef = useRef(null);

  const load = async () => {
    setLoading(true);
    try {
      const issued = await api.post('/portal/my-wallet-badge');
      const token = issued.data?.token;
      if (!token) throw new Error('no token');
      const r = await api.get(`/wallet-badge/${token}`);
      setBadge({ ...r.data, token });
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not load your badge');
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const downloadPng = async () => {
    if (!badgeRef.current) return;
    setBusy(true);
    try {
      // iter345 — html-to-image (same path as <UnifiedBadge/>'s own export)
      // so the photo AND the SVG QR are baked into the PNG. html2canvas was
      // dropping both.
      const { toPng } = await import('html-to-image');
      const url = await toPng(badgeRef.current, {
        pixelRatio: 3, cacheBust: true, skipFonts: true, fetchRequestInit: { mode: 'cors' },
      });
      const a = document.createElement('a');
      const safe = (badge?.name || 'badge').replace(/[^a-z0-9-]+/gi, '_').toLowerCase();
      a.href = url; a.download = `5812-badge-${safe}.png`;
      document.body.appendChild(a); a.click(); a.remove();
    } catch {
      toast.error('Could not save the image — try Print instead');
    }
    setBusy(false);
  };

  const openZoom = async () => {
    if (!badgeRef.current) return;
    setZooming(true);
    try {
      const { toPng } = await import('html-to-image');
      setZoomUrl(await toPng(badgeRef.current, {
        pixelRatio: 3, cacheBust: true, skipFonts: true, fetchRequestInit: { mode: 'cors' },
      }));
    } catch {
      toast.error('Could not build the preview');
    }
    setZooming(false);
  };

  const person = badge && {
    id: badge.member_id || badge.id,
    member_id: badge.member_id,
    name: badge.name,
    role: badge.role,
    title: badge.title,
    department: badge.department,
    location_name: badge.location_name,
    country: badge.country,
    country_code: badge.country_code,
    photo_url: badge.photo_url,
    is_medical: badge.is_medical,
    is_resident: badge.is_resident,
    is_sponsored: badge.is_sponsored,
    qr_data: badge.qr_data,
  };

  const tickets = badge?.event_tickets || [];

  return (
    <div className="space-y-6" data-testid="portal-badge-page">
      <div className="flex items-center justify-between no-print">
        <div>
          <h1 className="text-2xl font-semibold font-heading flex items-center gap-2"><IdCard size={22} /> My Badge</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Your access pass. Event tickets you hold are attached to it automatically.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} data-testid="portal-badge-refresh"><RefreshCw size={14} /></Button>
      </div>

      {loading && <div className="h-64 bg-muted animate-pulse rounded-xl" />}

      {!loading && person && (
        <div className="flex flex-col items-center gap-5">
          <div ref={badgeRef} data-testid="portal-badge-card">
            <UnifiedBadge person={person} showActions={false} />
          </div>
          <div className="flex gap-2 no-print w-full max-w-sm">
            <Button variant="outline" className="flex-1 gap-2" onClick={openZoom} disabled={zooming} data-testid="portal-badge-zoom">
              <ZoomIn size={15} /> {zooming ? 'Building…' : '200%'}
            </Button>
            <Button className="flex-1 gap-2" onClick={downloadPng} disabled={busy} data-testid="portal-badge-download">
              <Download size={15} /> {busy ? 'Saving…' : 'Save image'}
            </Button>
            <Button variant="outline" className="flex-1 gap-2" onClick={() => window.print()} data-testid="portal-badge-print">
              <Printer size={15} /> Print
            </Button>
          </div>
          <BadgeZoomDialog url={zoomUrl} onClose={() => setZoomUrl(null)} onPrint={() => window.print()} />
        </div>
      )}

      {!loading && tickets.length > 0 && (
        <Card className="shadow-soft rounded-xl no-print" data-testid="badge-ticket-flags">
          <CardContent className="p-4 space-y-2">
            <p className="text-xs uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
              <Ticket size={12} /> Attached to this badge ({tickets.length})
            </p>
            {tickets.map(t => (
              <div key={t.ticket_id} className="flex items-center justify-between text-sm p-2 rounded-lg bg-accent/30">
                <div>
                  <p className="font-medium">{t.event_title}</p>
                  <p className="text-xs text-muted-foreground">{t.event_date}{t.event_time ? ` · ${t.event_time}` : ''}</p>
                </div>
                <Badge variant={t.used_at ? 'outline' : 'secondary'} className="text-[10px]">
                  {t.used_at ? 'Used' : 'Ticketed'}
                </Badge>
              </div>
            ))}
            <p className="text-[11px] text-muted-foreground pt-1">
              Staff scanning this badge at a gate or kiosk will see these passes — no separate ticket needed.
            </p>
          </CardContent>
        </Card>
      )}

      <style>{`@media print { .no-print { display: none !important; } body { background: #fff !important; } }`}</style>
    </div>
  );
}
