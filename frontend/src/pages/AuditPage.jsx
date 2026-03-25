import React, { useState, useEffect } from 'react';
import { Shield, RefreshCw, ChevronLeft, ChevronRight, RotateCcw, Trash2, Archive } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { auditApi, adminApi } from '../services/api';
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

  // Recycle bin state
  const [deletedItems, setDeletedItems] = useState([]);
  const [deletedLoading, setDeletedLoading] = useState(false);
  const [collectionFilter, setCollectionFilter] = useState('all');
  const [restoringId, setRestoringId] = useState(null);

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

  const fetchDeletedItems = async () => {
    setDeletedLoading(true);
    try {
      const res = await adminApi.deletedItems(collectionFilter !== 'all' ? collectionFilter : undefined);
      setDeletedItems(res.data || []);
    } catch { toast.error('Failed to load deleted items'); }
    finally { setDeletedLoading(false); }
  };

  const handleRestore = async (itemId) => {
    setRestoringId(itemId);
    try {
      await adminApi.restoreItem(itemId);
      toast.success('Item restored!');
      setDeletedItems(prev => prev.filter(i => i.id !== itemId));
    } catch (err) { toast.error(err.response?.data?.detail || 'Restore failed'); }
    finally { setRestoringId(null); }
  };

  const handlePermanentDelete = async (itemId) => {
    if (!window.confirm('Permanently delete? This cannot be undone.')) return;
    try {
      await adminApi.permanentDelete(itemId);
      toast.success('Permanently deleted');
      setDeletedItems(prev => prev.filter(i => i.id !== itemId));
    } catch { toast.error('Delete failed'); }
  };

  useEffect(() => { fetchLogs(); }, [page]);
  useEffect(() => { fetchDeletedItems(); }, [collectionFilter]);

  const collectionLabel = (col) => ({ members: 'Member', families: 'Family', children: 'Child', guests: 'Guest', users: 'User' }[col] || col);
  const daysRemaining = (deletedAt) => {
    if (!deletedAt) return 0;
    const deleted = new Date(deletedAt);
    const expiresAt = new Date(deleted.getTime() + 30 * 24 * 60 * 60 * 1000);
    return Math.max(0, Math.ceil((expiresAt - Date.now()) / (24 * 60 * 60 * 1000)));
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10">
            <Shield size={18} className="text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold font-heading" data-testid="audit-page-title">Audit Trail</h1>
            <p className="text-sm text-muted-foreground mt-0.5">{total.toLocaleString()} events logged &middot; {deletedItems.length} items in recycle bin</p>
          </div>
        </div>
      </div>

      <Tabs defaultValue="audit">
        <TabsList>
          <TabsTrigger value="audit" data-testid="tab-audit"><Shield size={13} className="mr-1.5" /> Audit Log</TabsTrigger>
          <TabsTrigger value="recycle" data-testid="tab-recycle"><Archive size={13} className="mr-1.5" /> Recycle Bin</TabsTrigger>
        </TabsList>

        <TabsContent value="audit" className="mt-4">
          <Card className="shadow-soft rounded-xl">
            <CardContent className="p-5">
              <div className="flex justify-end mb-3">
                <Button variant="outline" size="sm" onClick={fetchLogs} data-testid="audit-refresh"><RefreshCw size={14} /></Button>
              </div>
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
        </TabsContent>

        <TabsContent value="recycle" className="mt-4">
          <Card className="shadow-soft rounded-xl">
            <CardContent className="p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <Select value={collectionFilter} onValueChange={setCollectionFilter}>
                    <SelectTrigger className="w-[180px]" data-testid="recycle-filter"><SelectValue placeholder="All types" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Types</SelectItem>
                      <SelectItem value="members">Members</SelectItem>
                      <SelectItem value="families">Families</SelectItem>
                      <SelectItem value="children">Children</SelectItem>
                      <SelectItem value="guests">Guests</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">{deletedItems.length} deleted items (30-day retention)</p>
                </div>
                <Button variant="outline" size="sm" onClick={fetchDeletedItems} data-testid="recycle-refresh"><RefreshCw size={14} /></Button>
              </div>
              {deletedLoading ? (
                <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-14 bg-muted animate-pulse rounded" />)}</div>
              ) : deletedItems.length > 0 ? (
                <div className="space-y-2">
                  {deletedItems.map(item => (
                    <div key={item.id} className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-accent/20 transition-colors" data-testid={`deleted-item-${item.id}`}>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium">{item.name || item.family_name || item.title || item.id}</p>
                          <Badge variant="outline" className="text-[10px]">{collectionLabel(item._deleted_from)}</Badge>
                          <Badge variant="secondary" className="text-[10px]">{daysRemaining(item.deleted_at)}d left</Badge>
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {item.email && `${item.email} · `}
                          Deleted: {item.deleted_at ? new Date(item.deleted_at).toLocaleString() : 'Unknown'}
                        </p>
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" className="gap-1 text-green-600 border-green-200 hover:bg-green-50" data-testid={`restore-${item.id}`} onClick={() => handleRestore(item.id)} disabled={restoringId === item.id}>
                          <RotateCcw size={13} /> {restoringId === item.id ? 'Restoring...' : 'Restore'}
                        </Button>
                        <Button size="sm" variant="ghost" className="text-destructive h-8 w-8 p-0" data-testid={`perm-delete-${item.id}`} onClick={() => handlePermanentDelete(item.id)} title="Permanent delete">
                          <Trash2 size={13} />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-16">
                  <Archive size={40} className="mx-auto mb-3 opacity-20" />
                  <p className="text-muted-foreground">Recycle bin is empty</p>
                  <p className="text-xs text-muted-foreground mt-1">Deleted items appear here for 30 days before permanent removal</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
