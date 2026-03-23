import React, { useState, useEffect } from 'react';
import { Megaphone, Plus, Pin, Trash2, RefreshCw } from 'lucide-react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Switch } from '../components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { announcementsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

const typeStyles = {
  general: 'bg-blue-100 text-blue-700',
  urgent: 'bg-red-100 text-red-700',
  prayer: 'bg-purple-100 text-purple-700',
  ministry: 'bg-green-100 text-green-700',
};

function timeAgo(iso) {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return new Date(iso).toLocaleDateString();
}

export default function CommsPage() {
  const { user } = useAuth();
  const [announcements, setAnnouncements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [filter, setFilter] = useState('all');
  const [form, setForm] = useState({ title: '', content: '', type: 'general', target_role: '', pinned: false });

  const isAdmin = ['admin', 'system_admin'].includes(user?.role);

  const fetchAnnouncements = async () => {
    setLoading(true);
    try {
      const res = await announcementsApi.list();
      setAnnouncements(res.data);
    } catch { toast.error('Failed to load announcements'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchAnnouncements(); }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await announcementsApi.create({ ...form, target_role: form.target_role || null });
      setAnnouncements(prev => [res.data, ...prev]);
      setShowCreate(false);
      setForm({ title: '', content: '', type: 'general', target_role: '', pinned: false });
      toast.success('Announcement posted!');
    } catch { toast.error('Failed to post announcement'); }
    finally { setSaving(false); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this announcement?')) return;
    await announcementsApi.delete(id);
    setAnnouncements(prev => prev.filter(a => a.id !== id));
    toast.success('Deleted');
  };

  const handlePin = async (id) => {
    await announcementsApi.togglePin(id);
    setAnnouncements(prev => prev.map(a => a.id === id ? { ...a, pinned: !a.pinned } : a));
  };

  const filtered = filter === 'all' ? announcements : announcements.filter(a => a.type === filter);
  const pinned = filtered.filter(a => a.pinned);
  const regular = filtered.filter(a => !a.pinned);

  return (
    <div className="p-6 space-y-5 max-w-3xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Communications</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{announcements.length} announcements</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchAnnouncements}><RefreshCw size={14} /></Button>
          {isAdmin && <Button className="gap-2" size="sm" onClick={() => setShowCreate(true)} data-testid="new-announcement-btn"><Plus size={14} /> New Announcement</Button>}
        </div>
      </div>

      <div className="flex gap-2 flex-wrap">
        {['all', 'general', 'urgent', 'prayer', 'ministry'].map(t => (
          <Button key={t} variant={filter === t ? 'default' : 'outline'} size="sm" className="capitalize text-xs" onClick={() => setFilter(t)}>{t}</Button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-28 bg-muted animate-pulse rounded-xl" />)}</div>
      ) : (
        <div className="space-y-3">
          {pinned.length > 0 && (
            <>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5"><Pin size={12} /> Pinned</p>
              {pinned.map(ann => <AnnouncementCard key={ann.id} ann={ann} isAdmin={isAdmin} onDelete={handleDelete} onPin={handlePin} />)}
              {regular.length > 0 && <div className="border-t border-border my-2" />}
            </>
          )}
          {regular.map(ann => <AnnouncementCard key={ann.id} ann={ann} isAdmin={isAdmin} onDelete={handleDelete} onPin={handlePin} />)}
          {filtered.length === 0 && (
            <div className="text-center py-16 text-sm text-muted-foreground">
              <Megaphone size={32} className="mx-auto mb-3 opacity-30" />
              No announcements yet.
            </div>
          )}
        </div>
      )}

      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New Announcement</DialogTitle></DialogHeader>
          <form onSubmit={handleCreate} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Title *</Label>
              <Input placeholder="Announcement title" value={form.title} onChange={e => setForm({...form, title: e.target.value})} required data-testid="announcement-title-input" />
            </div>
            <div className="space-y-2"><Label>Content *</Label>
              <Textarea placeholder="Write your announcement..." rows={4} value={form.content} onChange={e => setForm({...form, content: e.target.value})} required data-testid="announcement-content-input" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Type</Label>
                <Select value={form.type} onValueChange={v => setForm({...form, type: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="general">General</SelectItem>
                    <SelectItem value="urgent">Urgent</SelectItem>
                    <SelectItem value="prayer">Prayer</SelectItem>
                    <SelectItem value="ministry">Ministry</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Target</Label>
                <Select value={form.target_role} onValueChange={v => setForm({...form, target_role: v})}>
                  <SelectTrigger><SelectValue placeholder="Everyone" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">Everyone</SelectItem>
                    <SelectItem value="admin">Admins only</SelectItem>
                    <SelectItem value="staff">Staff only</SelectItem>
                    <SelectItem value="volunteer">Volunteers only</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 rounded-lg border border-border">
              <Switch checked={form.pinned} onCheckedChange={v => setForm({...form, pinned: v})} />
              <div>
                <p className="text-sm font-medium">Pin announcement</p>
                <p className="text-xs text-muted-foreground">Keep at top of feed</p>
              </div>
            </div>
            <div className="flex gap-3 pt-1">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowCreate(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving} data-testid="post-announcement-btn">{saving ? 'Posting...' : 'Post Announcement'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AnnouncementCard({ ann, isAdmin, onDelete, onPin }) {
  return (
    <Card className={`shadow-soft rounded-xl ${ann.pinned ? 'border-primary/30 bg-primary/5' : ''}`} data-testid="announcement-card">
      <CardContent className="p-5">
        <div className="flex items-start gap-3">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              {ann.pinned && <Pin size={12} className="text-primary" />}
              <p className="font-semibold text-sm">{ann.title}</p>
              <Badge variant="outline" className={`text-xs capitalize ${typeStyles[ann.type] || ''} border-0`}>{ann.type}</Badge>
              {ann.target_role && <Badge variant="outline" className="text-xs capitalize">{ann.target_role} only</Badge>}
            </div>
            <p className="text-sm text-muted-foreground leading-relaxed">{ann.content}</p>
            <div className="flex items-center gap-3 mt-2.5 text-xs text-muted-foreground">
              <span>{ann.author_name}</span>
              <span>·</span>
              <span>{timeAgo(ann.created_at)}</span>
            </div>
          </div>
          {isAdmin && (
            <div className="flex gap-1 shrink-0">
              <Button variant="ghost" size="icon" className={`h-7 w-7 ${ann.pinned ? 'text-primary' : 'text-muted-foreground'}`} onClick={() => onPin(ann.id)}>
                <Pin size={12} />
              </Button>
              <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={() => onDelete(ann.id)}>
                <Trash2 size={12} />
              </Button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
