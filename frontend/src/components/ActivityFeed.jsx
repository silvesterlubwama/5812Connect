/**
 * ActivityFeed — reusable component that fetches and renders the universal
 * activity log for a subject (member, child, staff, user, customer, guest).
 *
 * Props:
 *   subjectKind: 'member' | 'child' | 'staff' | 'user' | 'customer' | 'guest'
 *   subjectId:   string
 *   showAddNote: bool (default true)
 *   showDownload: bool (default true) — produces a JSON download for compliance
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Textarea } from './ui/textarea';
import { Activity, Plus, Download, Paperclip, ShoppingCart, Heart, DollarSign, FileText, Clock, AlertCircle, BookOpen, ScanLine } from 'lucide-react';
import api from '../services/api';
import { toast } from 'sonner';

const ICON_BY_CATEGORY = {
  sale: ShoppingCart,
  payment: DollarSign,
  donation: Heart,
  expense: DollarSign,
  bill: FileText,
  bill_payment: DollarSign,
  social_case: Heart,
  social_note: BookOpen,
  social_payment: Heart,
  checkin: ScanLine,
  access: ScanLine,
  event: Activity,
  payslip: DollarSign,
  salary: DollarSign,
  leave: Clock,
  reimbursement: DollarSign,
  attendance: Clock,
  document: FileText,
  photo: Paperclip,
  badge: FileText,
  report: FileText,
  note: BookOpen,
  system: Activity,
  other: Activity,
};

export default function ActivityFeed({ subjectKind, subjectId, showAddNote = true, showDownload = true }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [noteBody, setNoteBody] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const fileRef = useRef(null);

  const reload = useCallback(async () => {
    if (!subjectKind || !subjectId) return;
    setLoading(true);
    try {
      const r = await api.get(`/activity/${subjectKind}/${subjectId}`, { params: { limit: 300 } });
      setItems(r.data || []);
    } catch (e) {
      if (e.response?.status === 403) toast.error('You don\'t have access to view this activity');
    } finally { setLoading(false); }
  }, [subjectKind, subjectId]);
  useEffect(() => { reload(); }, [reload]);

  const submitNote = async () => {
    if (!noteBody.trim() && !fileRef.current?.files?.[0]) {
      toast.error('Add a note or attach a file');
      return;
    }
    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append('body', noteBody);
      fd.append('visibility', 'internal');
      const f = fileRef.current?.files?.[0];
      if (f) fd.append('file', f);
      await api.post(`/activity/${subjectKind}/${subjectId}/note`, fd);
      toast.success('Note added');
      setNoteBody('');
      if (fileRef.current) fileRef.current.value = '';
      reload();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to add note');
    } finally { setSubmitting(false); }
  };

  const downloadProfile = async () => {
    try {
      const r = await api.get(`/activity/${subjectKind}/${subjectId}/export`);
      const blob = new Blob([JSON.stringify(r.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `profile-${subjectKind}-${subjectId}.json`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success('Profile exported');
    } catch (e) { toast.error(e.response?.data?.detail || 'Export failed'); }
  };

  const filtered = categoryFilter === 'all' ? items : items.filter(i => i.category === categoryFilter);
  const categoryCounts = items.reduce((acc, i) => { acc[i.category] = (acc[i.category] || 0) + 1; return acc; }, {});
  const topCategories = Object.entries(categoryCounts).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([cat]) => cat);

  return (
    <div className="space-y-3" data-testid="activity-feed">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <Activity size={16} className="text-primary" />
          <h3 className="font-semibold text-sm">Activity Trail ({items.length})</h3>
          <Badge variant={categoryFilter === 'all' ? 'default' : 'outline'} className="cursor-pointer text-[10px]" onClick={() => setCategoryFilter('all')}>All</Badge>
          {topCategories.map(c => (
            <Badge key={c} variant={categoryFilter === c ? 'default' : 'outline'} className="cursor-pointer text-[10px] capitalize" onClick={() => setCategoryFilter(c)}>{c.replace('_', ' ')} ({categoryCounts[c]})</Badge>
          ))}
        </div>
        {showDownload && (
          <Button size="sm" variant="outline" onClick={downloadProfile} data-testid="activity-download-btn">
            <Download size={13} className="mr-1" />Download Profile
          </Button>
        )}
      </div>

      {showAddNote && (
        <Card className="rounded-lg border-dashed">
          <CardContent className="p-3 space-y-2">
            <Textarea
              rows={2}
              value={noteBody}
              onChange={e => setNoteBody(e.target.value)}
              placeholder={`Add a note about this ${subjectKind} (visit, observation, milestone)...`}
              data-testid="activity-note-input"
            />
            <div className="flex items-center justify-between gap-2">
              <input type="file" ref={fileRef} className="text-xs flex-1" data-testid="activity-file-input" />
              <Button size="sm" onClick={submitNote} disabled={submitting} data-testid="activity-note-submit">
                <Plus size={12} className="mr-1" />Add
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loading && <div className="space-y-2">{[1, 2, 3].map(i => <div key={i} className="h-14 bg-muted animate-pulse rounded" />)}</div>}
      {!loading && filtered.length === 0 && <p className="text-sm text-muted-foreground text-center py-12">No activity yet.</p>}
      {!loading && filtered.length > 0 && (
        <div className="space-y-2">
          {filtered.map(item => {
            const Icon = ICON_BY_CATEGORY[item.category] || Activity;
            return (
              <div key={item.id} className="flex items-start gap-3 p-2 rounded border" data-testid={`activity-row-${item.id}`}>
                <div className="rounded-full bg-muted p-1.5 mt-0.5"><Icon size={12} /></div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-medium">{item.title}</p>
                    <Badge variant="outline" className="text-[10px] capitalize">{item.category?.replace('_', ' ')}</Badge>
                    {item.derived && <Badge variant="secondary" className="text-[10px]" title="From a source record (sale, payment, etc) — not a manual note">auto</Badge>}
                    {item.visibility === 'public_to_subject' && <Badge className="text-[10px] bg-emerald-100 text-emerald-700">visible to subject</Badge>}
                  </div>
                  {item.body && <p className="text-xs text-muted-foreground mt-0.5 whitespace-pre-wrap">{item.body}</p>}
                  {item.attachments?.length > 0 && (
                    <div className="mt-1 text-[10px] flex flex-wrap gap-2">
                      {item.attachments.map((a, i) => (
                        <a key={i} href={a.url?.startsWith('http') ? a.url : `${process.env.REACT_APP_BACKEND_URL}${a.url}`} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline inline-flex items-center gap-1">
                          <Paperclip size={9} />{a.name}
                        </a>
                      ))}
                    </div>
                  )}
                  <p className="text-[10px] text-muted-foreground mt-1">
                    {item.created_at?.slice(0, 16).replace('T', ' ')}
                    {item.actor_name && ` · ${item.actor_name}`}
                    {item.amount != null && ` · ${item.currency || 'UGX'} ${Number(item.amount).toLocaleString()}`}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
