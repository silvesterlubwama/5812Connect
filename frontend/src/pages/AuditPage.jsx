import React, { useState, useEffect, useCallback } from 'react';
import { Shield, RefreshCw, ChevronLeft, ChevronRight, RotateCcw, Trash2, Archive, CheckSquare, Square, CheckCheck } from 'lucide-react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { auditApi, adminApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

const actionColors = {
  create: 'bg-green-100 text-green-700', update: 'bg-blue-100 text-blue-700',
  delete: 'bg-red-100 text-red-700', login: 'bg-purple-100 text-purple-700',
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
  const [deletedItems, setDeletedItems] = useState([]);
  const [deletedLoading, setDeletedLoading] = useState(false);
  const [collectionFilter, setCollectionFilter] = useState('all');
  const [restoringId, setRestoringId] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());

  useEffect(() => {
    if (user && !['admin', 'system_admin'].includes(user.role)) {
      navigate('/dashboard'); toast.error('Admin access required');
    }
  }, [user, navigate]);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await auditApi.list({ skip: page * limit, limit });
      setLogs(res.data.logs || []); setTotal(res.data.total || 0);
    } catch { toast.error('Failed to load audit trail'); }
    finally { setLoading(false); }
  }, [page]);

  const fetchDeletedItems = useCallback(async () => {
    setDeletedLoading(true);
    try {
      const res = await adminApi.deletedItems(collectionFilter !== 'all' ? collectionFilter : undefined);
      setDeletedItems(res.data || []); setSelectedIds(new Set());
    } catch { toast.error('Failed to load deleted items'); }
    finally { setDeletedLoading(false); }
  }, [collectionFilter]);

  const handleRestore = async (itemId) => {
    setRestoringId(itemId);
    try {
      await adminApi.restoreItem(itemId); toast.success('Item restored!');
      setDeletedItems(prev => prev.filter(i => i.id !== itemId));
      setSelectedIds(prev => { const n = new Set(prev); n.delete(itemId); return n; });
    } catch (err) { toast.error(err.response?.data?.detail || 'Restore failed'); }
    finally { setRestoringId(null); }
  };

  const handlePermanentDelete = async (itemId) => {
    if (!window.confirm('Permanently delete? This cannot be undone.')) return;
    try {
      await adminApi.permanentDelete(itemId); toast.success('Permanently deleted');
      setDeletedItems(prev => prev.filter(i => i.id !== itemId));
      setSelectedIds(prev => { const n = new Set(prev); n.delete(itemId); return n; });
    } catch { toast.error('Delete failed'); }
  };

  const handleBulkDelete = async () => {
    if (!selectedIds.size) return;
    if (!window.confirm(`Permanently delete ${selectedIds.size} items? This cannot be undone.`)) return;
    try {
      await adminApi.bulkDeleteItems([...selectedIds]);
      toast.success(`Deleted ${selectedIds.size} items`);
      setDeletedItems(prev => prev.filter(i => !selectedIds.has(i.id)));
      setSelectedIds(new Set());
    } catch { toast.error('Bulk delete failed'); }
  };

  const handleBulkRestore = async () => {
    if (!selectedIds.size) return;
    try {
      await adminApi.bulkRestoreItems([...selectedIds]);
      toast.success(`Restored ${selectedIds.size} items`);
      setDeletedItems(prev => prev.filter(i => !selectedIds.has(i.id)));
      setSelectedIds(new Set());
    } catch { toast.error('Bulk restore failed'); }
  };

  const toggleSelect = (id) => setSelectedIds(prev => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n;
  });
  const toggleAll = () => {
    if (selectedIds.size === deletedItems.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(deletedItems.map(i => i.id)));
  };

  useEffect(() => { fetchLogs(); }, [fetchLogs]);
  useEffect(() => { fetchDeletedItems(); }, [fetchDeletedItems]);

  const collectionLabel = (col) => ({ members: 'Member', families: 'Family', children: 'Child', guests: 'Guest', users: 'User' }[col] || col);
  const daysRemaining = (deletedAt) => {
    if (!deletedAt) return 0;
    const expiresAt = new Date(new Date(deletedAt).getTime() + 30 * 24 * 60 * 60 * 1000);
    return Math.max(0, Math.ceil((expiresAt - Date.now()) / (24 * 60 * 60 * 1000)));
  };

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10"><Shield size={18} className="text-primary" /></div>
          <div>
            <h1 className="text-xl sm:text-2xl font-semibold font-heading" data-testid="audit-page-title">Audit Trail</h1>
            <p className="text-sm text-muted-foreground mt-0.5">{total.toLocaleString()} events &middot; {deletedItems.length} in recycle bin</p>
          </div>
        </div>
      </div>

      <Tabs defaultValue="audit">
        <TabsList>
          <TabsTrigger value="audit" data-testid="tab-audit"><Shield size={13} className="mr-1.5" /> Audit Log</TabsTrigger>
          <TabsTrigger value="recycle" data-testid="tab-recycle"><Archive size={13} className="mr-1.5" /> Recycle Bin ({deletedItems.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="audit" className="mt-4">
          <Card>
            <CardContent className="p-4 sm:p-5">
              <div className="flex justify-end mb-3">
                <Button variant="outline" size="sm" onClick={fetchLogs} data-testid="audit-refresh"><RefreshCw size={14} /></Button>
              </div>
              {loading ? <div className="space-y-3">{[1,2,3,4,5].map(i => <div key={i} className="h-12 bg-muted animate-pulse rounded" />)}</div>
              : logs.length > 0 ? (
                <>
                  <div className="overflow-x-auto table-scroll">
                    <table className="w-full text-sm">
                      <thead><tr className="text-left border-b">
                        <th className="pb-2 pr-4 font-medium text-muted-foreground">Time</th>
                        <th className="pb-2 pr-4 font-medium text-muted-foreground">Action</th>
                        <th className="pb-2 pr-4 font-medium text-muted-foreground">Resource</th>
                        <th className="pb-2 pr-4 font-medium text-muted-foreground">ID</th>
                        <th className="pb-2 font-medium text-muted-foreground">User</th>
                      </tr></thead>
                      <tbody className="divide-y">
                        {logs.map(log => (
                          <tr key={log.id} className="hover:bg-accent/30" data-testid="audit-row">
                            <td className="py-2.5 pr-4 text-muted-foreground text-xs">{timeAgo(log.timestamp)}</td>
                            <td className="py-2.5 pr-4"><span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${actionColors[log.action] || 'bg-slate-100 text-slate-700'}`}>{log.action}</span></td>
                            <td className="py-2.5 pr-4 font-medium capitalize">{log.resource}</td>
                            <td className="py-2.5 pr-4 text-muted-foreground font-mono text-xs">{log.resource_id?.slice(0, 8) || '—'}</td>
                            <td className="py-2.5 text-muted-foreground text-xs font-mono">{log.user_id?.slice(0, 8) || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="flex items-center justify-between mt-4 pt-3 border-t">
                    <p className="text-xs text-muted-foreground">Page {page + 1} of {Math.ceil(total / limit)}</p>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}><ChevronLeft size={14} /></Button>
                      <Button variant="outline" size="sm" disabled={(page + 1) * limit >= total} onClick={() => setPage(p => p + 1)}><ChevronRight size={14} /></Button>
                    </div>
                  </div>
                </>
              ) : <p className="text-sm text-muted-foreground text-center py-16">No audit events recorded yet.</p>}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="recycle" className="mt-4">
          <Card>
            <CardContent className="p-4 sm:p-5">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
                <div className="flex items-center gap-3 flex-wrap">
                  <Select value={collectionFilter} onValueChange={setCollectionFilter}>
                    <SelectTrigger className="w-[160px]" data-testid="recycle-filter"><SelectValue placeholder="All types" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Types</SelectItem>
                      <SelectItem value="members">Members</SelectItem>
                      <SelectItem value="families">Families</SelectItem>
                      <SelectItem value="children">Children</SelectItem>
                      <SelectItem value="guests">Guests</SelectItem>
                      <SelectItem value="users">Users</SelectItem>
                    </SelectContent>
                  </Select>
                  {selectedIds.size > 0 && (
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary">{selectedIds.size} selected</Badge>
                      <Button size="sm" variant="outline" className="gap-1 text-green-600 h-7 text-xs" onClick={handleBulkRestore} data-testid="bulk-restore-btn">
                        <RotateCcw size={12} /> Restore
                      </Button>
                      <Button size="sm" variant="destructive" className="gap-1 h-7 text-xs" onClick={handleBulkDelete} data-testid="bulk-delete-btn">
                        <Trash2 size={12} /> Delete
                      </Button>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="ghost" size="sm" onClick={toggleAll} className="text-xs gap-1" data-testid="select-all-btn">
                    {selectedIds.size === deletedItems.length && deletedItems.length > 0 ? <CheckCheck size={13} /> : <Square size={13} />}
                    {selectedIds.size === deletedItems.length && deletedItems.length > 0 ? 'Deselect All' : 'Select All'}
                  </Button>
                  <Button variant="outline" size="sm" onClick={fetchDeletedItems} data-testid="recycle-refresh"><RefreshCw size={14} /></Button>
                </div>
              </div>

              {deletedLoading ? <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-14 bg-muted animate-pulse rounded" />)}</div>
              : deletedItems.length > 0 ? (
                <div className="space-y-2">
                  {deletedItems.map(item => (
                    <div key={item.id} className={`flex items-center gap-3 p-3 rounded-lg border hover:bg-accent/20 transition-colors ${selectedIds.has(item.id) ? 'bg-primary/5 border-primary/30' : 'border-border'}`} data-testid={`deleted-item-${item.id}`}>
                      <button className="shrink-0" onClick={() => toggleSelect(item.id)} data-testid={`select-${item.id}`}>
                        {selectedIds.has(item.id) ? <CheckSquare size={16} className="text-primary" /> : <Square size={16} className="text-muted-foreground" />}
                      </button>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="text-sm font-medium truncate">{item.name || item.family_name || item.title || item.id}</p>
                          <Badge variant="outline" className="text-[10px]">{collectionLabel(item._deleted_from)}</Badge>
                          <Badge variant="secondary" className="text-[10px]">{daysRemaining(item.deleted_at)}d left</Badge>
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5 truncate">
                          {item.email && `${item.email} · `}Deleted: {item.deleted_at ? new Date(item.deleted_at).toLocaleString() : 'Unknown'}
                        </p>
                      </div>
                      <div className="flex gap-1.5 shrink-0">
                        <Button size="sm" variant="outline" className="gap-1 text-green-600 border-green-200 hover:bg-green-50 h-8 text-xs" data-testid={`restore-${item.id}`} onClick={() => handleRestore(item.id)} disabled={restoringId === item.id}>
                          <RotateCcw size={12} /> Restore
                        </Button>
                        <Button size="sm" variant="ghost" className="text-destructive h-8 w-8 p-0" data-testid={`perm-delete-${item.id}`} onClick={() => handlePermanentDelete(item.id)}>
                          <Trash2 size={12} />
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
