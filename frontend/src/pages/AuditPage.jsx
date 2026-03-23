import React, { useState, useEffect } from 'react';
import { Shield, RefreshCw, ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { auditApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

const actionColors = {
  create: 'bg-green-100 text-green-700',
  update: 'bg-blue-100 text-blue-700',
  delete: 'bg-red-100 text-red-700',
  login: 'bg-purple-100 text-purple-700',
};

function timeAgo(isoStr) {
  if (!isoStr) return '';
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return new Date(isoStr).toLocaleString();
}

export default function AuditPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const limit = 25;

  useEffect(() => {
    if (user && !['admin', 'system_admin'].includes(user.role)) {
      navigate('/dashboard');
      toast.error('Admin access required');
    }
  }, [user, navigate]);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const res = await auditApi.list({ skip: page * limit, limit });
      setLogs(res.data.logs || []);
      setTotal(res.data.total || 0);
    } catch { toast.error('Failed to load audit trail'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchLogs(); }, [page]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10">
            <Shield size={18} className="text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold font-heading">Audit Trail</h1>
            <p className="text-sm text-muted-foreground mt-0.5">{total.toLocaleString()} total events logged</p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={fetchLogs} data-testid="audit-refresh"><RefreshCw size={14} /></Button>
      </div>

      <Card className="shadow-soft rounded-xl">
        <CardContent className="p-5">
          {loading ? (
            <div className="space-y-3">{[1,2,3,4,5].map(i => <div key={i} className="h-12 bg-muted animate-pulse rounded" />)}</div>
          ) : logs.length > 0 ? (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left border-b border-border">
                    <th className="pb-2 pr-4 font-medium text-muted-foreground">Time</th>
                    <th className="pb-2 pr-4 font-medium text-muted-foreground">Action</th>
                    <th className="pb-2 pr-4 font-medium text-muted-foreground">Resource</th>
                    <th className="pb-2 pr-4 font-medium text-muted-foreground">Resource ID</th>
                    <th className="pb-2 font-medium text-muted-foreground">User</th>
                  </tr></thead>
                  <tbody className="divide-y divide-border">
                    {logs.map(log => (
                      <tr key={log.id} className="hover:bg-accent/30 transition-colors" data-testid="audit-row">
                        <td className="py-2.5 pr-4 text-muted-foreground text-xs">{timeAgo(log.timestamp)}</td>
                        <td className="py-2.5 pr-4">
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${actionColors[log.action] || 'bg-slate-100 text-slate-700'}`}>
                            {log.action}
                          </span>
                        </td>
                        <td className="py-2.5 pr-4 font-medium capitalize">{log.resource}</td>
                        <td className="py-2.5 pr-4 text-muted-foreground font-mono text-xs">{log.resource_id || '—'}</td>
                        <td className="py-2.5 text-muted-foreground text-xs font-mono">{log.user_id?.slice(0, 8) || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-between mt-4 pt-3 border-t border-border">
                <p className="text-xs text-muted-foreground">
                  Page {page + 1} of {Math.ceil(total / limit)} · {total} events
                </p>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)} data-testid="audit-prev">
                    <ChevronLeft size={14} />
                  </Button>
                  <Button variant="outline" size="sm" disabled={(page + 1) * limit >= total} onClick={() => setPage(p => p + 1)} data-testid="audit-next">
                    <ChevronRight size={14} />
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-16">No audit events recorded yet.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
