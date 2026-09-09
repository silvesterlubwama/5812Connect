import React, { useState, useEffect, useCallback } from 'react';
import { Download } from 'lucide-react';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import api, { checkinsApi } from '../services/api';
import { toast } from 'sonner';

const WaitlistPanel = ({ eventId, ticketTiers, onPromoted }) => {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    setLoading(true);
    try { const res = await api.get(`/events/${eventId}/waitlist`); setEntries(res.data || []); }
    catch { /* ignore */ }
    finally { setLoading(false); }
  }, [eventId]);
  useEffect(() => { reload(); }, [reload]);
  const tierName = (id) => (ticketTiers || []).find(t => t.id === id)?.name || '—';
  if (loading) return <div className="space-y-2">{[1, 2].map(i => <div key={i} className="h-12 bg-muted animate-pulse rounded" />)}</div>;
  if (entries.length === 0) return <p className="text-sm text-muted-foreground text-center py-6" data-testid="waitlist-empty">No one on the waitlist.</p>;
  return (
    <div className="space-y-2" data-testid="waitlist-panel">
      {entries.map(e => (
        <div key={e.id} className="flex items-center justify-between gap-2 p-2 rounded border border-border text-sm" data-testid={`waitlist-${e.id}`}>
          <div className="min-w-0">
            <p className="font-medium truncate">{e.name} <span className="text-xs text-muted-foreground font-normal">· {e.num_tickets} ticket(s) · {tierName(e.tier_id)}</span></p>
            <p className="text-xs text-muted-foreground truncate">{e.email}{e.phone ? ` · ${e.phone}` : ''} · joined {e.created_at?.slice(0, 10)}</p>
          </div>
          <div className="flex gap-1 shrink-0">
            {e.status === 'waiting' ? (
              <>
                <Button size="sm" variant="outline" className="h-7 text-xs" data-testid={`waitlist-promote-${e.id}`} onClick={async () => {
                  try { await api.post(`/events/${eventId}/waitlist/${e.id}/promote`); toast.success('Promoted to booking'); reload(); onPromoted?.(); }
                  catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
                }}>Promote</Button>
                <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive" data-testid={`waitlist-cancel-${e.id}`} onClick={async () => {
                  if (!window.confirm('Cancel this waitlist entry?')) return;
                  try { await api.delete(`/events/${eventId}/waitlist/${e.id}`); toast.success('Cancelled'); reload(); }
                  catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
                }}>Cancel</Button>
              </>
            ) : <Badge variant="outline" className="text-[10px] capitalize">{e.status}</Badge>}
          </div>
        </div>
      ))}
    </div>
  );
};

/** Registrations / check-ins / tiers / waitlist for one event.
 *  `event` is the full detail payload from GET /api/events/{id}. */
export const EventDetailTabs = ({ event, onRefresh }) => {
  const attendees = event.attendees || [];
  const checkins = event.checkins || [];
  const tiers = event.ticket_tiers || [];
  const exportAttendees = async () => {
    try {
      const res = await api.get(`/events/${event.id}/attendees/export`, { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url; a.download = `${(event.title || 'event').replace(/\s+/g, '-')}-attendees.csv`;
      a.click(); URL.revokeObjectURL(url);
    } catch { toast.error('Export failed'); }
  };
  return (
    <Tabs defaultValue="attendees" className="mt-1" data-testid="event-detail-tabs">
      <TabsList className="w-full grid grid-cols-4 h-auto">
        <TabsTrigger value="attendees" className="text-xs" data-testid="tab-attendees">Registered ({attendees.length})</TabsTrigger>
        <TabsTrigger value="checkins" className="text-xs" data-testid="tab-checkins">Check-Ins ({checkins.length})</TabsTrigger>
        <TabsTrigger value="tiers" className="text-xs" data-testid="tab-tiers">Tiers ({tiers.length})</TabsTrigger>
        <TabsTrigger value="waitlist" className="text-xs" data-testid="tab-waitlist">Waitlist</TabsTrigger>
      </TabsList>

      <TabsContent value="attendees" className="mt-3">
        {attendees.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-6" data-testid="event-attendees-empty">No registrations yet — public sign-ups appear here.</p>
        ) : (
          <div className="space-y-2" data-testid="event-attendees-list">
            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={exportAttendees} data-testid="export-attendees-btn"><Download size={12} className="mr-1" />Export CSV</Button>
            {attendees.map((a, i) => (
              <div key={a.id || a.email || `att-${i}`} className="flex items-center justify-between gap-2 p-2 rounded border border-border text-sm flex-wrap" data-testid={`attendee-row-${a.id || i}`}>
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{a.name}</p>
                  <p className="text-xs text-muted-foreground truncate">{a.email || '—'}{a.phone ? ` · ${a.phone}` : ''}</p>
                  {(a.num_tickets > 1 || a.tier_name) && (
                    <p className="text-[10px] text-muted-foreground mt-0.5">
                      {a.num_tickets || 1} ticket{(a.num_tickets || 1) === 1 ? '' : 's'}{a.tier_name ? ` · ${a.tier_name}` : ''}
                      {a.total ? ` · ${event.currency || 'UGX'} ${Number(a.total).toLocaleString()}` : ''}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-1.5">
                  {a.payment_status && !['paid', 'free'].includes(a.payment_status) && (
                    <>
                      <Badge variant="outline" className="text-[10px] capitalize">{a.payment_status}</Badge>
                      <Button size="sm" variant="outline" className="h-6 text-[10px]" data-testid={`mark-paid-${a.id || i}`} onClick={async () => {
                        try { await api.put(`/public/bookings/${a.id}/mark-paid`); toast.success('Marked paid'); onRefresh?.(); }
                        catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
                      }}>Mark paid</Button>
                    </>
                  )}
                  <Badge className="bg-green-600 text-white border-0 text-xs capitalize">{a.status}</Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </TabsContent>

      <TabsContent value="checkins" className="mt-3">
        {checkins.length === 0 ? <p className="text-sm text-muted-foreground text-center py-6">No check-ins</p> : (
          <div className="space-y-2">{checkins.map((ci, i) => (
            <div key={ci.id || `ci-${i}`} className="flex items-center justify-between gap-2 p-2 rounded border border-border text-sm">
              <div className="min-w-0"><p className="font-medium truncate">{ci.member_name}</p><p className="text-xs text-muted-foreground">{ci.check_in_time ? new Date(ci.check_in_time).toLocaleString() : ''}</p></div>
              <div className="flex gap-1.5 items-center shrink-0">
                <Badge variant="outline" className="text-xs capitalize">{ci.type}</Badge>
                {!ci.check_out_time ? (
                  <Button size="sm" variant="outline" className="h-6 text-xs" data-testid={`checkout-${ci.id}`} onClick={async () => {
                    try { await checkinsApi.checkout(ci.id); toast.success('Checked out'); onRefresh?.(); } catch { toast.error('Checkout failed'); }
                  }}>Check Out</Button>
                ) : <Badge className="bg-green-100 text-green-700 text-xs">Out</Badge>}
              </div>
            </div>
          ))}</div>
        )}
      </TabsContent>

      <TabsContent value="tiers" className="mt-3">
        {tiers.length === 0 ? <p className="text-sm text-muted-foreground text-center py-6">No ticket tiers — hit Edit to add them.</p> : (
          <div className="space-y-2" data-testid="tiers-summary">
            {tiers.map((t, i) => {
              const pct = t.capacity ? Math.min(100, ((t.sold || 0) / t.capacity) * 100) : 0;
              return (
                <div key={t.id || i} className="p-3 rounded-lg border border-border">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-medium text-sm truncate">{t.name}</p>
                      {t.description && <p className="text-xs text-muted-foreground truncate">{t.description}</p>}
                    </div>
                    <div className="text-right shrink-0">
                      <p className="font-bold text-sm">{(t.price || 0).toLocaleString()}</p>
                      <p className="text-xs text-muted-foreground">{t.sold || 0} / {t.capacity} sold</p>
                    </div>
                  </div>
                  <div className="mt-2 bg-muted rounded-full h-1.5"><div className="bg-primary h-1.5 rounded-full" style={{ width: `${pct}%` }} /></div>
                </div>
              );
            })}
          </div>
        )}
      </TabsContent>

      <TabsContent value="waitlist" className="mt-3">
        <WaitlistPanel eventId={event.id} ticketTiers={tiers} onPromoted={onRefresh} />
      </TabsContent>
    </Tabs>
  );
};

export default EventDetailTabs;
