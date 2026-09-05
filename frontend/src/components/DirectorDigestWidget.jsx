import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { AlertCircle, Mail, ArrowRight, MoonStar } from 'lucide-react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import api from '../services/api';

/**
 * DirectorDigestWidget — live preview of today's overdue-task digest email
 * (the one server.py's `_fire_overdue_task_director_digest` sends at 08:00 UTC).
 *
 * Renders nothing when:
 *   • the caller isn't a director+ role (backend returns eligible=false)
 *   • there are zero overdue tasks in the caller's scope
 * Otherwise the widget shows a red-accented count, the top few late tasks,
 * a "Snooze 1 day" button per row (so it drops out of tomorrow's digest),
 * and a link to Tasks.
 */
export default function DirectorDigestWidget() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [snoozingId, setSnoozingId] = useState(null);

  const load = () => {
    api.get('/tasks/director-digest-preview')
      .then(r => setData(r.data))
      .catch(() => setErr(true));
  };
  useEffect(() => { load(); }, []);

  if (err || !data || !data.eligible || data.task_count === 0) return null;

  const snooze1Day = async (id) => {
    setSnoozingId(id);
    try {
      await api.post(`/tasks/${id}/snooze`, { days: 1 });
      toast.success('Snoozed 1 day — drops out of tomorrow’s digest');
      // Optimistically remove from the visible list; reload for authoritative count
      setData(d => d && ({
        ...d,
        task_count: d.task_count - 1,
        tasks: (d.tasks || []).filter(t => t.id !== id),
      }));
      // Background refetch in case the count differs (multiple assignees etc.)
      setTimeout(load, 400);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Snooze failed');
    }
    setSnoozingId(null);
  };

  const shown = (data.tasks || []).slice(0, 5);
  return (
    <Card className="shadow-soft rounded-xl border-rose-200" data-testid="director-digest-widget">
      <CardHeader className="pb-2 pt-4 px-5">
        <CardTitle className="text-base font-semibold flex items-center gap-2 text-rose-700">
          <AlertCircle size={16} /> Today's overdue-task digest
          <Badge className="bg-rose-600 hover:bg-rose-600 ml-1" data-testid="director-digest-count">
            {data.task_count}
          </Badge>
        </CardTitle>
        <p className="text-[11px] text-muted-foreground mt-1 flex items-center gap-1">
          <Mail size={11} />
          {data.already_sent_today
            ? 'Emailed to you at 08:00 UTC today'
            : 'This is what your 08:00 UTC email will contain'}
          {data.scope === 'campus' && <> · scope: your campuses</>}
        </p>
      </CardHeader>
      <CardContent className="px-5 pb-4">
        <ul className="space-y-1.5">
          {shown.map(t => (
            <li key={t.id} data-testid={`digest-row-${t.id}`} className="flex items-start gap-2 text-xs">
              <span className="font-mono w-10 shrink-0 text-rose-700 font-semibold">{t.days_late}d</span>
              <span className="flex-1 line-clamp-2">
                {t.title}
                {t.assignee_names.length > 0 && (
                  <span className="text-muted-foreground"> · {t.assignee_names.slice(0, 3).join(', ')}</span>
                )}
              </span>
              <button
                onClick={() => snooze1Day(t.id)}
                disabled={snoozingId === t.id}
                data-testid={`digest-snooze-${t.id}`}
                title="Snooze 1 day — drops out of tomorrow’s digest"
                className="shrink-0 text-muted-foreground hover:text-rose-700 disabled:opacity-40"
              >
                <MoonStar size={13} />
              </button>
            </li>
          ))}
        </ul>
        {data.task_count > shown.length && (
          <p className="text-[11px] text-muted-foreground mt-2">+ {data.task_count - shown.length} more in your digest</p>
        )}
        <Button size="sm" variant="outline" className="mt-3 gap-1.5 text-xs h-8" asChild data-testid="digest-view-all-btn">
          <Link to="/tasks">Go to Tasks <ArrowRight size={12} /></Link>
        </Button>
      </CardContent>
    </Card>
  );
}
