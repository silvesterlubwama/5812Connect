import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { AlertCircle, Mail, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import api from '../services/api';

/**
 * DirectorDigestWidget — live preview of today's overdue-task digest email
 * (the one server.py's `_fire_overdue_task_director_digest` sends at 08:00 UTC).
 *
 * Renders nothing when:
 *   • the caller isn't a director+ role (backend returns eligible=false)
 *   • there are zero overdue tasks in the caller's scope
 * Otherwise the widget shows a red-accented count, the top few late tasks,
 * and a link to Tasks. Directors can spot fires before their morning email
 * even arrives.
 */
export default function DirectorDigestWidget() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api.get('/tasks/director-digest-preview')
      .then(r => { if (!cancelled) setData(r.data); })
      .catch(() => { if (!cancelled) setErr(true); });
    return () => { cancelled = true; };
  }, []);

  if (err || !data || !data.eligible || data.task_count === 0) return null;

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
