/**
 * ReviewsDueWidget — small stat card on the Social Work hub.
 *
 * Shows the count of children with an active social-work case whose last
 * welfare visit was > N days ago (default 90). Click opens a dialog listing
 * the overdue children so a social worker can plan the next batch of visits.
 *
 * Data: GET /api/social-work/reviews/compliance/due?days=N
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { CalendarClock, RefreshCw, ChevronRight } from 'lucide-react';
import api from '../services/api';
import EmptyState from './EmptyState';

export default function ReviewsDueWidget({ onOpenCase }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [days, setDays] = useState(90);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get(`/social-work/reviews/compliance/due?days=${days}`);
      setData(r.data);
    } catch (e) { console.warn(e?.message || e); }
    finally { setLoading(false); }
  }, [days]);

  useEffect(() => { refresh(); }, [refresh]);

  const dueCount = data?.due ?? 0;
  const tone = dueCount === 0
    ? 'text-emerald-600'
    : dueCount < 5 ? 'text-amber-600' : 'text-rose-600';

  return (
    <>
      <Card
        className="rounded-xl cursor-pointer hover:border-primary/40"
        onClick={() => setOpen(true)}
        data-testid="sw-reviews-due-card"
      >
        <CardContent className="p-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground uppercase">Reviews due</p>
            <CalendarClock size={12} className="text-muted-foreground" />
          </div>
          <p className={`text-2xl font-bold ${tone}`} data-testid="sw-reviews-due-count">{dueCount}</p>
          <p className="text-[10px] text-muted-foreground">
            children &gt; {days}d since last welfare visit
            {data?.never_visited ? ` · ${data.never_visited} never visited` : ''}
          </p>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl max-h-[88vh] overflow-y-auto" data-testid="sw-reviews-due-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><CalendarClock size={16} /> Reviews due</DialogTitle>
            <DialogDescription className="text-xs">
              Children with active cases whose last welfare visit is overdue. Click a row to open the case → Welfare Visits tab.
            </DialogDescription>
          </DialogHeader>

          <div className="flex items-center gap-2 mt-1 mb-3">
            <span className="text-xs text-muted-foreground">Overdue if last visit &gt;</span>
            <Select value={String(days)} onValueChange={v => setDays(parseInt(v))}>
              <SelectTrigger className="h-7 w-32 text-xs" data-testid="sw-reviews-due-threshold"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="30">30 days</SelectItem>
                <SelectItem value="60">60 days</SelectItem>
                <SelectItem value="90">90 days</SelectItem>
                <SelectItem value="180">180 days</SelectItem>
              </SelectContent>
            </Select>
            <Button size="sm" variant="ghost" onClick={refresh} disabled={loading} className="ml-auto">
              <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
            </Button>
          </div>

          {!data || data.list.length === 0 ? (
            <EmptyState
              icon={CalendarClock}
              title="Everyone is up to date 🎉"
              description={`No active cases have a last welfare visit older than ${days} days. Great work, team.`}
              testid="sw-reviews-due-empty"
            />
          ) : (
            <div className="space-y-1.5">
              {data.list.map(row => (
                <Card
                  key={row.child_id}
                  className="rounded-lg cursor-pointer hover:border-primary/40"
                  onClick={() => { if (onOpenCase) onOpenCase(row.child_id); setOpen(false); }}
                  data-testid={`sw-due-row-${row.child_id}`}
                >
                  <CardContent className="p-2.5 flex items-center gap-3">
                    <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center text-xs">{(row.name || '?').slice(0, 1)}</div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{row.name}</p>
                      <p className="text-[11px] text-muted-foreground">
                        {row.last_review_at
                          ? `Last visit ${row.last_review_at} (${row.days_since}d ago)`
                          : 'Never visited'}
                      </p>
                    </div>
                    <Badge className={row.last_review_at ? 'bg-amber-100 text-amber-700 text-[10px]' : 'bg-rose-100 text-rose-700 text-[10px]'}>
                      {row.last_review_at ? `${row.days_since}d overdue` : 'Never'}
                    </Badge>
                    <ChevronRight size={14} className="text-muted-foreground" />
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
