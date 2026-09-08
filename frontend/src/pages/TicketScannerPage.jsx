import React, { useEffect, useRef, useState } from 'react';
import { Html5Qrcode } from 'html5-qrcode';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Ticket, CheckCircle2, XCircle, Camera, CameraOff, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import api from '../services/api';

/**
 * Door-staff ticket scanner. Accepts either a scanned QR (containing the
 * `tkt_*` id) or a manually-typed id. Redeems via /api/tickets/{id}/redeem.
 * Prev outcome is shown as a persistent card so staff can double-check the
 * last scan before waving the next family in.
 */
export default function TicketScannerPage() {
  const [manual, setManual] = useState('');
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState(null); // { kind: 'ok'|'used'|'invalid'|'void', title, sub, ticket }
  const [scanning, setScanning] = useState(false);
  const scannerRef = useRef(null);
  const readerId = 'ticket-scanner-video';

  const redeem = async (id) => {
    const tid = String(id || '').trim();
    if (!tid) return;
    setBusy(true);
    try {
      // First look up so the "already used" case surfaces clearly.
      const lk = await api.get(`/tickets/${tid}`);
      const t = lk.data.ticket;
      const ev = lk.data.event;
      if (t.status === 'used') {
        setLast({ kind: 'used', title: 'Already used', sub: `at ${t.used_at || 'earlier'} · by ${t.used_by_name || 'staff'}`, ticket: t, event: ev });
        toast.warning('Ticket already used');
        return;
      }
      if (t.status === 'void') {
        setLast({ kind: 'void', title: 'Void ticket', sub: 'Refunded or cancelled', ticket: t, event: ev });
        toast.error('Void ticket');
        return;
      }
      const r = await api.post(`/tickets/${tid}/redeem`);
      setLast({ kind: 'ok', title: 'Admit one', sub: `${ev?.title || 'Event'} · ${t.holder_name || 'Guest'}`, event: ev, ticket: { ...t, ...r.data, status: 'used' } });
      toast.success(`Admit — ${t.holder_name || 'guest'}`);
    } catch (e) {
      const s = e?.response?.status;
      const detail = e?.response?.data?.detail || 'Scan failed';
      if (s === 404) setLast({ kind: 'invalid', title: 'Not a valid ticket', sub: tid });
      else if (s === 409) setLast({ kind: 'used', title: 'Already used', sub: detail });
      else setLast({ kind: 'invalid', title: 'Scan failed', sub: detail });
      toast.error(detail);
    } finally { setBusy(false); setManual(''); }
  };

  const startCamera = async () => {
    if (scanning) return;
    setScanning(true);
    try {
      const scanner = new Html5Qrcode(readerId);
      scannerRef.current = scanner;
      await scanner.start(
        { facingMode: 'environment' },
        { fps: 8, qrbox: { width: 260, height: 260 } },
        async (decoded) => {
          // debounce — pause between scans
          if (busy) return;
          const match = String(decoded).match(/tkt_[a-zA-Z0-9]+/);
          const id = match ? match[0] : decoded;
          await redeem(id);
        },
        () => {} // ignore per-frame decode failures
      );
    } catch (e) {
      toast.error('Camera unavailable — use manual entry');
      setScanning(false);
    }
  };

  const stopCamera = async () => {
    try { await scannerRef.current?.stop(); await scannerRef.current?.clear(); } catch { /* ignore */ }
    setScanning(false);
  };

  useEffect(() => () => { stopCamera(); }, []);

  const kindStyle = {
    ok: 'border-emerald-400 bg-emerald-50 text-emerald-900',
    used: 'border-amber-400 bg-amber-50 text-amber-900',
    void: 'border-red-400 bg-red-50 text-red-900',
    invalid: 'border-red-400 bg-red-50 text-red-900',
  };
  const kindIcon = {
    ok: <CheckCircle2 size={40} className="text-emerald-600" />,
    used: <XCircle size={40} className="text-amber-600" />,
    void: <XCircle size={40} className="text-red-600" />,
    invalid: <XCircle size={40} className="text-red-600" />,
  };

  return (
    <div className="max-w-2xl mx-auto space-y-4 p-4">
      <div className="flex items-center gap-2">
        <Ticket size={20} className="text-primary" />
        <h1 className="text-xl font-bold">Ticket Scanner</h1>
      </div>
      <Card>
        <CardHeader className="py-3"><CardTitle className="text-base flex items-center gap-2">
          <Camera size={16} /> Camera scan
        </CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div id={readerId} className="w-full rounded overflow-hidden bg-black/5 min-h-[240px] flex items-center justify-center text-xs text-muted-foreground">
            {!scanning && 'Tap Start to activate the camera'}
          </div>
          <div className="flex gap-2">
            {!scanning ? (
              <Button size="sm" onClick={startCamera} data-testid="ticket-scan-start"><Camera size={14} className="mr-1" />Start camera</Button>
            ) : (
              <Button size="sm" variant="outline" onClick={stopCamera} data-testid="ticket-scan-stop"><CameraOff size={14} className="mr-1" />Stop</Button>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="py-3"><CardTitle className="text-base">Manual entry</CardTitle></CardHeader>
        <CardContent className="flex gap-2">
          <Input
            placeholder="tkt_..."
            value={manual}
            onChange={e => setManual(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && redeem(manual)}
            data-testid="ticket-scan-manual-input"
          />
          <Button onClick={() => redeem(manual)} disabled={!manual.trim() || busy} data-testid="ticket-scan-manual-btn">
            {busy ? <RefreshCw size={14} className="animate-spin mr-1" /> : null}Redeem
          </Button>
        </CardContent>
      </Card>

      {last && (
        <Card className={`border-2 ${kindStyle[last.kind]}`} data-testid={`ticket-scan-result-${last.kind}`}>
          <CardContent className="p-6 flex items-center gap-4">
            {kindIcon[last.kind]}
            <div className="flex-1 min-w-0">
              <p className="text-xl font-bold">{last.title}</p>
              <p className="text-sm mt-0.5 truncate">{last.sub}</p>
              {/* iter-scanner-deeplink: surface the event date and venue so
                  door staff at multi-day fairs immediately spot wrong-day scans. */}
              {last.event && (
                <div className="text-[11px] mt-1.5 opacity-80 space-y-0.5">
                  {last.event.event_date && (
                    <p data-testid="ticket-scan-event-date">
                      📅 {new Date(last.event.event_date).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
                    </p>
                  )}
                  {(last.event.location_name || last.event.venue || last.event.location_id) && (
                    <p data-testid="ticket-scan-event-venue">
                      📍 {last.event.location_name || last.event.venue || last.event.location_id}
                    </p>
                  )}
                </div>
              )}
              {last.ticket?.id && (
                <p className="text-[10px] font-mono mt-1 opacity-60">{last.ticket.id}</p>
              )}
            </div>
            <Badge variant={last.kind === 'ok' ? 'default' : 'destructive'} className="uppercase text-[10px]">
              {last.kind}
            </Badge>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
