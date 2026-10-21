import React, { useCallback, useEffect, useState } from 'react';
import api from '../../services/api';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { History, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

const PAGE = 50;

const describe = (row) => {
  const what = [row.action, row.resource].filter(Boolean).join(' ').replace(/_/g, ' ');
  const d = row.details || {};
  const extra = d.name || d.fields?.join(', ') || d.count || d.email || '';
  return extra ? `${what} — ${extra}` : what;
};

export const OrgActivityLog = ({ organizations = [] }) => {
  const [rows, setRows] = useState([]);
  const [orgFilter, setOrgFilter] = useState('');
  const [skip, setSkip] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/organizations/activity', {
        params: { limit: PAGE, skip, ...(orgFilter ? { org_id: orgFilter } : {}) },
      });
      setRows(res.data.activity || []);
      setTotal(res.data.total || 0);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not load the activity log');
    } finally { setLoading(false); }
  }, [orgFilter, skip]);

  useEffect(() => { load(); }, [load]);

  return (
    <Card data-testid="org-activity-log">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="text-lg flex items-center gap-2">
            <History size={18} className="text-primary" /> Activity
          </CardTitle>
          <Button size="sm" variant="ghost" onClick={load} disabled={loading} data-testid="activity-refresh">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Which organisation you opened and when, plus the changes admins made inside each one.
        </p>
        <div className="flex flex-wrap gap-1.5 pt-2">
          <Button
            size="sm" variant={orgFilter ? 'ghost' : 'secondary'}
            onClick={() => { setOrgFilter(''); setSkip(0); }}
            data-testid="activity-filter-all"
          >
            Everything
          </Button>
          {organizations.map(o => (
            <Button
              key={o.id} size="sm" variant={orgFilter === o.id ? 'secondary' : 'ghost'}
              onClick={() => { setOrgFilter(o.id); setSkip(0); }}
              data-testid={`activity-filter-${o.id}`}
            >
              {o.name}
            </Button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {rows.length === 0 && !loading && (
          <p className="text-sm text-muted-foreground" data-testid="activity-empty">Nothing recorded yet.</p>
        )}
        {rows.map(row => (
          <div
            key={`${row.id}-${row.timestamp}`}
            className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border/60 pb-2 last:border-0"
            data-testid="activity-row"
          >
            <div className="min-w-0">
              <p className="text-sm">
                <span className="font-medium">{row.user_name || 'Someone'}</span>{' '}
                <span className="text-muted-foreground">{describe(row)}</span>
              </p>
              <p className="text-xs text-muted-foreground">
                {row.timestamp ? new Date(row.timestamp).toLocaleString() : ''}
                {row.organization_name ? ` · ${row.organization_name}` : ''}
              </p>
            </div>
            <Badge variant={row.scope === 'platform' ? 'default' : 'outline'} className="shrink-0">
              {row.scope === 'platform' ? 'Platform' : 'Organisation'}
            </Badge>
          </div>
        ))}
        {total > PAGE && (
          <div className="flex items-center justify-between pt-2">
            <Button size="sm" variant="outline" disabled={skip === 0 || loading}
              onClick={() => setSkip(Math.max(0, skip - PAGE))} data-testid="activity-prev">
              Newer
            </Button>
            <span className="text-xs text-muted-foreground">{skip + 1}–{Math.min(skip + PAGE, total)} of {total}</span>
            <Button size="sm" variant="outline" disabled={skip + PAGE >= total || loading}
              onClick={() => setSkip(skip + PAGE)} data-testid="activity-next">
              Older
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
