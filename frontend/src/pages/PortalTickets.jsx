import React, { useEffect, useState } from 'react';
import { Ticket, Calendar, MapPin, CheckCircle2, XCircle, Clock, RefreshCw } from 'lucide-react';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { QRCode } from 'react-qrcode-logo';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

// Ticket wallet — every event ticket the current account owns. Renders a
// scannable QR each door-staff can redeem via /api/tickets/{id}/redeem.
// Works even for `pending` guests so anyone who buys can walk in.
export default function PortalTickets() {
  const { user } = useAuth();
  const [passes, setPasses] = useState([]);
  const [loading, setLoading] = useState(true);
  const load = () => {
    setLoading(true);
    api.get('/portal/tickets').then(r => setPasses(r.data || [])).catch(() => setPasses([])).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const now = new Date();
  const isPast = (t) => t.event_date && new Date(t.event_date) < new Date(now.toDateString());
  const upcoming = passes.filter(t => !isPast(t) && t.status !== 'used' && t.status !== 'void');
  const usedOrPast = passes.filter(t => isPast(t) || t.status === 'used' || t.status === 'void');

  const badgeFor = (t) => {
    if (t.status === 'used') return <Badge className="bg-slate-100 text-slate-600">Used {t.used_at ? '· ' + new Date(t.used_at).toLocaleString() : ''}</Badge>;
    if (t.status === 'void') return <Badge variant="destructive">Void</Badge>;
    if (isPast(t)) return <Badge variant="outline">Past event</Badge>;
    return <Badge className="bg-green-100 text-green-700">Valid</Badge>;
  };

  const Pass = ({ t }) => (
    <Card key={t.ticket_id} className="shadow-soft rounded-xl overflow-hidden" data-testid={`ticket-pass-${t.ticket_id}`}>
      <CardContent className="p-0 grid grid-cols-1 sm:grid-cols-[1fr_auto]">
        <div className="p-4 space-y-2 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Ticket</p>
              <p className="text-base font-semibold font-heading truncate">{t.event_title}</p>
            </div>
            {badgeFor(t)}
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs text-muted-foreground">
            {t.event_date && <p className="flex items-center gap-1.5"><Calendar size={12} />{t.event_date}{t.event_time ? ` · ${t.event_time}` : ''}</p>}
            {t.event_location && <p className="flex items-center gap-1.5"><MapPin size={12} />{t.event_location}</p>}
          </div>
          <div className="flex items-center gap-3 text-xs pt-1 border-t border-dashed border-border">
            <div>
              <p className="text-muted-foreground">Holder</p>
              <p className="font-medium">{t.holder_name || user?.name}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Type</p>
              <p className="font-medium">{t.tier_name || (t.is_free ? 'Free entry' : 'General')}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Ticket #</p>
              <p className="font-mono text-[11px]">{t.ticket_id}</p>
            </div>
          </div>
        </div>
        <div className="border-t sm:border-t-0 sm:border-l border-dashed border-border p-4 flex flex-col items-center justify-center bg-muted/30" data-testid={`ticket-qr-${t.ticket_id}`}>
          <QRCode
            value={t.ticket_id}
            size={128}
            qrStyle="dots"
            eyeRadius={4}
            fgColor={t.status === 'used' || isPast(t) ? '#94a3b8' : '#0f172a'}
            ecLevel="M"
          />
          <p className="text-[10px] text-muted-foreground mt-2">Show this at the door</p>
        </div>
      </CardContent>
    </Card>
  );

  return (
    <div className="space-y-6" data-testid="portal-tickets-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading flex items-center gap-2"><Ticket size={22} /> My Tickets</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Every event pass tied to your account. Screenshot or show live at the door.</p>
        </div>
        <Button variant="outline" size="sm" onClick={load} data-testid="tickets-refresh"><RefreshCw size={14} /></Button>
      </div>
      {loading && <div className="animate-pulse h-40 bg-muted rounded-xl" />}
      {!loading && passes.length === 0 && (
        <Card><CardContent className="p-8 text-center text-sm text-muted-foreground">
          <Ticket className="mx-auto mb-3" size={32} />
          No tickets yet. Buy or RSVP for an event and the pass will land here automatically.
        </CardContent></Card>
      )}
      {upcoming.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs uppercase tracking-wide text-muted-foreground flex items-center gap-1.5"><CheckCircle2 size={12} className="text-green-500" /> Ready to use ({upcoming.length})</p>
          {upcoming.map(t => <Pass key={t.ticket_id} t={t} />)}
        </div>
      )}
      {usedOrPast.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs uppercase tracking-wide text-muted-foreground flex items-center gap-1.5"><Clock size={12} /> Past / used ({usedOrPast.length})</p>
          {usedOrPast.map(t => <Pass key={t.ticket_id} t={t} />)}
        </div>
      )}
    </div>
  );
}
