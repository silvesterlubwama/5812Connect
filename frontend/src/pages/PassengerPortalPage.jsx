/**
 * PassengerPortalPage — public, token-authenticated self-service for
 * passengers to see their tickets, upload boarding passes, run AI-OCR,
 * and mark themselves checked in.
 *
 * Route: /p/passenger/:token
 */
import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { toast, Toaster } from 'sonner';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { CheckCircle2, Plane, Sparkles, Loader2, Ticket, Luggage, ExternalLink } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function PassengerPortalPage() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [checkInFor, setCheckInFor] = useState(null); // ticket
  const [scanning, setScanning] = useState(false);
  const [ocr, setOcr] = useState(null);
  const [seat, setSeat] = useState('');
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/api/passenger-portal/${token}`);
      setData(r.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Portal link invalid');
    } finally { setLoading(false); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchData(); }, [token]);

  const openCheckIn = (t) => {
    setCheckInFor(t);
    setSeat(t.seat || '');
    setFile(null);
    setOcr(null);
  };

  const runOcr = async () => {
    if (!file) return;
    setScanning(true); setOcr(null);
    try {
      const fd = new FormData();
      fd.append('boarding_pass', file);
      const r = await axios.post(`${API}/api/passenger-portal/${token}/tickets/${checkInFor.id}/scan-boarding-pass`, fd);
      setOcr(r.data);
      if (r.data?.seat) setSeat(r.data.seat);
      if (r.data?.error) toast.warning(r.data.error);
      else toast.success('Fields extracted');
    } catch (e) { toast.error(e.response?.data?.detail || 'OCR failed'); }
    finally { setScanning(false); }
  };

  const submitCheckIn = async () => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('checked_in', 'true');
      fd.append('seat', seat);
      if (file) fd.append('boarding_pass', file);
      await axios.post(`${API}/api/passenger-portal/${token}/tickets/${checkInFor.id}/check-in`, fd);
      toast.success('Checked in ✓');
      setCheckInFor(null);
      await fetchData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };

  if (loading) return <div className="min-h-screen flex items-center justify-center bg-slate-50"><Loader2 className="animate-spin" size={24} /></div>;
  if (!data) return <div className="min-h-screen flex items-center justify-center bg-slate-50 text-slate-600">Portal link invalid or expired.</div>;

  const flightById = (id) => (data.flights || []).find(f => f.id === id);

  return (
    <div className="min-h-screen bg-gradient-to-br from-sky-50 via-slate-50 to-indigo-50">
      <Toaster />
      <div className="max-w-2xl mx-auto p-4 md:p-6 space-y-4">
        {/* Header */}
        <div className="rounded-xl bg-white shadow-sm border border-border p-4 space-y-1">
          <p className="text-[11px] uppercase tracking-wider text-indigo-600 font-semibold flex items-center gap-1"><Plane size={12} /> Passenger portal</p>
          <h1 className="text-xl md:text-2xl font-bold tracking-tight" data-testid="portal-passenger-name">{data.passenger.name}</h1>
          <p className="text-sm text-muted-foreground">{data.shipment.name} · <span className="capitalize">{data.shipment.status}</span></p>
          {data.passenger.passport_no && (
            <p className="text-[11px] text-slate-500">Passport <span className="font-mono">{data.passenger.passport_no}</span></p>
          )}
        </div>

        {/* Flights */}
        {(data.flights || []).length > 0 && (
          <section className="rounded-xl bg-white shadow-sm border border-border p-4 space-y-2" data-testid="portal-flights">
            <h2 className="text-sm font-semibold flex items-center gap-1"><Plane size={13} /> Your flights ({data.flights.length})</h2>
            {data.flights.map(f => (
              <div key={f.id} className="rounded-md border border-border p-2 flex items-center gap-2 flex-wrap text-[12px]" data-testid={`portal-flight-${f.id}`}>
                <Badge style={{ backgroundColor: statusColor(f.status), color: 'white' }}>{f.status || 'scheduled'}</Badge>
                <span className="font-semibold">{f.airline}</span>
                <span className="font-mono">{f.flight_no}</span>
                <span className="text-muted-foreground">{f.origin || '?'} → {f.destination || '?'}</span>
                {f.departure_at && <span className="text-[11px] text-muted-foreground">{f.departure_at.slice(0, 16).replace('T', ' ')}</span>}
                {f.booking_url && <a href={f.booking_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline text-[11px] flex items-center gap-0.5"><ExternalLink size={9} /> Booking</a>}
                {f.ai_summary && <p className="basis-full text-[11px] italic text-purple-700 mt-0.5">🤖 {f.ai_summary}</p>}
              </div>
            ))}
          </section>
        )}

        {/* Tickets */}
        <section className="rounded-xl bg-white shadow-sm border border-border p-4 space-y-2" data-testid="portal-tickets">
          <h2 className="text-sm font-semibold flex items-center gap-1"><Ticket size={13} /> Your tickets ({(data.passenger.tickets || []).length})</h2>
          {(data.passenger.tickets || []).length === 0 && (
            <p className="text-[11px] italic text-muted-foreground">No tickets yet. The organiser will add them.</p>
          )}
          {(data.passenger.tickets || []).map(t => {
            const f = flightById(t.flight_id);
            return (
              <div key={t.id} className={`rounded-md border p-3 space-y-1 ${t.checked_in ? 'border-emerald-300 bg-emerald-50/40' : 'border-border'}`} data-testid={`portal-ticket-${t.id}`}>
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="outline" className={`text-[10px] font-mono ${t.checked_in ? 'bg-emerald-100 border-emerald-300 text-emerald-800' : ''}`}>
                    {t.checked_in && <CheckCircle2 size={10} className="mr-0.5 inline" />}
                    {t.ticket_no}
                  </Badge>
                  {f && <span className="text-[12px]">{f.airline} {f.flight_no} · {f.origin || '?'}→{f.destination || '?'}</span>}
                  {t.seat && <span className="font-mono text-[11px]">🪑 {t.seat}</span>}
                  {t.pnr && <span className="font-mono text-[11px] text-slate-500">PNR {t.pnr}</span>}
                </div>
                <div className="flex items-center gap-2 flex-wrap pt-1">
                  {t.boarding_pass_url && (
                    <a href={t.boarding_pass_url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-blue-700 hover:underline flex items-center gap-1">
                      <ExternalLink size={11} /> View boarding pass
                    </a>
                  )}
                  <Button size="sm" onClick={() => openCheckIn(t)} className={`ml-auto h-7 text-[11px] ${t.checked_in ? 'bg-slate-100 text-slate-700 hover:bg-slate-200' : 'bg-emerald-600 hover:bg-emerald-700 text-white'}`} data-testid={`portal-checkin-${t.id}`}>
                    {t.checked_in ? 'Update boarding pass' : 'Check in ✓'}
                  </Button>
                </div>
                {t.checked_in && t.checked_in_at && (
                  <p className="text-[10px] text-emerald-700 italic">Checked in {new Date(t.checked_in_at).toLocaleString()}</p>
                )}
              </div>
            );
          })}
        </section>

        {/* Suitcases (view-only) */}
        {(data.suitcases || []).length > 0 && (
          <section className="rounded-xl bg-white shadow-sm border border-border p-4 space-y-1" data-testid="portal-suitcases">
            <h2 className="text-sm font-semibold flex items-center gap-1"><Luggage size={13} /> Your suitcases ({data.suitcases.length})</h2>
            {data.suitcases.map(sc => {
              const over = sc.weight_kg > sc.weight_limit_kg && sc.weight_limit_kg > 0;
              return (
                <div key={sc.id} className="text-[12px] flex items-center gap-2">
                  <Badge variant="outline" className="text-[10px] capitalize">{sc.type}</Badge>
                  <span className="font-medium">{sc.name}</span>
                  <span className={`font-mono ${over ? 'text-rose-700' : 'text-muted-foreground'}`}>{sc.weight_kg}/{sc.weight_limit_kg}kg</span>
                  {sc.tracking_no && <span className="font-mono text-[10px] text-teal-700">🏷 {sc.tracking_no}</span>}
                </div>
              );
            })}
          </section>
        )}

        <p className="text-center text-[10px] text-slate-400 pt-2">
          Powered by 58:12 Connect · this link is unique to you — do not share
        </p>
      </div>

      {/* Check-in dialog */}
      {checkInFor && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={() => !busy && setCheckInFor(null)}>
          <div className="bg-white rounded-xl max-w-md w-full p-5 space-y-3" onClick={e => e.stopPropagation()} data-testid="portal-checkin-dialog">
            <h3 className="text-base font-semibold flex items-center gap-2"><CheckCircle2 size={16} className="text-emerald-600" /> Check in — {data.passenger.name}</h3>
            <p className="text-[11px] text-muted-foreground">Ticket <span className="font-mono">{checkInFor.ticket_no}</span>. Snap a photo of your boarding pass and (optionally) let AI auto-fill the fields.</p>

            <div>
              <Label className="text-xs">Seat</Label>
              <Input value={seat} onChange={e => setSeat(e.target.value)} placeholder="14A" className="font-mono" data-testid="portal-seat" />
            </div>

            <div>
              <Label className="text-xs">Boarding pass photo/PDF</Label>
              <div className="flex gap-2">
                <Input type="file" accept="image/*,application/pdf" onChange={e => { setFile(e.target.files?.[0] || null); setOcr(null); }} className="flex-1" data-testid="portal-file" />
                <Button size="sm" variant="outline" onClick={runOcr} disabled={!file || scanning} className="text-purple-700 border-purple-300 hover:bg-purple-50" data-testid="portal-ocr">
                  {scanning ? <><Loader2 size={11} className="mr-1 animate-spin" />Scanning…</> : <><Sparkles size={11} className="mr-1" />AI scan</>}
                </Button>
              </div>
              {file && <p className="text-[10px] text-muted-foreground mt-1">{file.name} · {(file.size / 1024).toFixed(0)} KB</p>}
            </div>

            {ocr && !ocr.error && (
              <div className="rounded-md border border-purple-200 bg-purple-50 p-2 text-[11px] space-y-1">
                <p className="font-semibold text-purple-900 flex items-center gap-1"><Sparkles size={11} /> AI extracted <span className="text-[10px] text-purple-600">(confidence {Math.round((ocr.confidence || 0) * 100)}%)</span></p>
                <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10.5px]">
                  {ocr.airline && <span><b>Airline:</b> {ocr.airline}</span>}
                  {ocr.flight_no && <span><b>Flight:</b> {ocr.flight_no}</span>}
                  {ocr.pnr && <span><b>PNR:</b> {ocr.pnr}</span>}
                  {ocr.seat && <span><b>Seat:</b> {ocr.seat}</span>}
                  {ocr.gate && <span><b>Gate:</b> {ocr.gate}</span>}
                  {ocr.boarding_time && <span><b>Boarding:</b> {ocr.boarding_time}</span>}
                </div>
              </div>
            )}

            <div className="flex gap-2 justify-end pt-1">
              <Button variant="outline" onClick={() => setCheckInFor(null)} disabled={busy}>Cancel</Button>
              <Button onClick={submitCheckIn} disabled={busy} className="bg-emerald-600 hover:bg-emerald-700" data-testid="portal-submit">
                {busy ? 'Saving…' : 'Check in ✓'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function statusColor(status) {
  return {
    scheduled: '#64748b', boarding: '#f59e0b', departed: '#0ea5e9', in_air: '#0284c7',
    landed: '#10b981', delayed: '#f97316', cancelled: '#ef4444',
  }[(status || 'scheduled').toLowerCase()] || '#64748b';
}
