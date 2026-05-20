import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Check, Trash2, Archive, AlignLeft, CheckSquare, Paperclip, Flag, Calendar, Users, Tag, ChevronRight, Upload, Eye, X, Download, Link2, ExternalLink, Clock, Play, Square } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { Label } from '../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { tasksApi, tasksExtApi, adminApi } from '../../services/api';
import api from '../../services/api';
import { toast } from 'sonner';

const LABEL_COLORS = ['#10b981','#f59e0b','#f97316','#ef4444','#8b5cf6','#3b82f6','#06b6d4','#84cc16','#ec4899','#6366f1'];

export function CardDetailDialog({ card, board, boardStaff, onClose, onSaved, onArchive, onDelete, onMove }) {
  const [title, setTitle] = useState(card?.title || '');
  const [description, setDescription] = useState(card?.description || '');
  const [priority, setPriority] = useState(card?.priority || 'medium');
  const [dueDate, setDueDate] = useState(card?.due_date || '');
  const [assignees, setAssignees] = useState(card?.assignees || []);
  const [labels, setLabels] = useState(card?.labels || []);
  const [checklist, setChecklist] = useState(card?.checklist || []);
  const [attachments, setAttachments] = useState(card?.attachments || []);
  const [newCheckItem, setNewCheckItem] = useState('');
  const [saving, setSaving] = useState(false);
  const [uploadingAttachment, setUploadingAttachment] = useState(false);
  const [showAddLink, setShowAddLink] = useState(false);
  const [linkForm, setLinkForm] = useState({ url: '', name: '' });
  const [isRecurring, setIsRecurring] = useState(card?.is_recurring || false);
  const [recurrencePattern, setRecurrencePattern] = useState(card?.recurrence_pattern || 'weekly');
  const [recurrenceInterval, setRecurrenceInterval] = useState(card?.recurrence_interval || 1);
  const fileRef = useRef(null);

  useEffect(() => {
    if (card) {
      setTitle(card.title || '');
      setDescription(card.description || '');
      setPriority(card.priority || 'medium');
      setDueDate(card.due_date || '');
      setAssignees(card.assignees || []);
      setLabels(card.labels || []);
      setChecklist(card.checklist || []);
      setAttachments(card.attachments || []);
    }
  }, [card?.id]);

  const save = async () => {
    if (!card) return;
    setSaving(true);
    try {
      const res = await tasksApi.update(card.id, { title, description, priority, due_date: dueDate, assignees, labels, checklist, attachments, is_recurring: isRecurring, recurrence_pattern: isRecurring ? recurrencePattern : null, recurrence_interval: isRecurring ? recurrenceInterval : null });
      onSaved?.(res.data);
      toast.success('Saved');
    } catch { toast.error('Save failed'); }
    finally { setSaving(false); }
  };

  const toggleCheck = (idx) => {
    const cl = [...checklist];
    cl[idx] = { ...cl[idx], completed: !cl[idx].completed };
    setChecklist(cl);
  };

  const addCheck = () => {
    if (!newCheckItem.trim()) return;
    setChecklist([...checklist, { text: newCheckItem.trim(), completed: false }]);
    setNewCheckItem('');
  };

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !card) return;
    setUploadingAttachment(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await tasksExtApi.uploadAttachment(card.id, formData);
      setAttachments(prev => [...prev, res.data]);
      toast.success(`Attached: ${file.name}`);
    } catch { toast.error('Upload failed'); }
    finally { setUploadingAttachment(false); }
  };

  const removeAttachment = async (attId) => {
    try {
      await tasksExtApi.deleteAttachment(card.id, attId);
      setAttachments(prev => prev.filter(a => a.id !== attId));
    } catch { toast.error('Failed to remove attachment'); }
  };

  const addLinkAttachment = () => {
    if (!linkForm.url.trim()) return;
    const url = linkForm.url.trim().startsWith('http') ? linkForm.url.trim() : `https://${linkForm.url.trim()}`;
    const name = linkForm.name.trim() || new URL(url).hostname;
    const att = { id: `link_${Date.now()}`, name, url, type: 'link', source: 'manual' };
    setAttachments(prev => [...prev, att]);
    setLinkForm({ url: '', name: '' });
    setShowAddLink(false);
    toast.success(`Link added: ${name}`);
  };

  const toggleLabel = (color) => {
    const idx = labels.findIndex(l => (l.color || l) === color);
    if (idx >= 0) setLabels(labels.filter((_, i) => i !== idx));
    else setLabels([...labels, { name: '', color }]);
  };

  const toggleAssignee = (uid) => {
    setAssignees(prev => prev.includes(uid) ? prev.filter(id => id !== uid) : [...prev, uid]);
  };

  if (!card) return null;

  const completedCount = checklist.filter(i => i.completed).length;

  return (
    <Dialog open={!!card} onOpenChange={o => { if (!o) onClose(); }}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto bg-[#1e293b] border-white/10 text-slate-100">
        {card.cover_color && <div className="h-10 rounded-t-lg -mx-6 -mt-6 mb-3" style={{ background: card.cover_color }} />}
        <DialogHeader>
          <DialogTitle className="text-slate-100">
            <Input data-testid="card-title-input"
              className="text-base font-semibold border-0 shadow-none p-0 focus-visible:ring-0 bg-transparent text-white placeholder:text-slate-400"
              value={title} onChange={e => setTitle(e.target.value)} onBlur={save} />
          </DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-3 gap-5 mt-2">
          {/* Main */}
          <div className="col-span-2 space-y-5">
            {labels.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {labels.map((lbl, i) => <span key={lbl.name || lbl.color || i} className="px-2.5 py-0.5 rounded text-xs font-medium text-white" style={{ background: lbl.color || '#3b82f6' }}>{lbl.name || lbl}</span>)}
              </div>
            )}

            <div className="space-y-2">
              <Label className="flex items-center gap-2 text-sm font-semibold text-slate-300"><AlignLeft size={14} /> Description</Label>
              <Textarea rows={3} placeholder="Add a description..."
                className="bg-[#0f172a] border-white/15 text-slate-200 placeholder:text-slate-500 text-sm resize-none"
                value={description} onChange={e => setDescription(e.target.value)} onBlur={save} data-testid="card-description" />
            </div>

            <TaskTimeTracker taskId={card.id} />

            {checklist.length > 0 && (
              <div className="space-y-2">
                <Label className="flex items-center gap-2 text-sm font-semibold text-slate-300">
                  <CheckSquare size={14} /> Checklist <span className="text-xs text-slate-500">{completedCount}/{checklist.length}</span>
                </Label>
                <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                  <div className="h-full bg-emerald-500 transition-all" style={{ width: `${checklist.length ? (completedCount / checklist.length) * 100 : 0}%` }} />
                </div>
                <div className="space-y-1.5">
                  {checklist.map((item, i) => (
                    <div key={item?.text || item?.label || i} className="flex items-center gap-2 group">
                      <input type="checkbox" checked={item.completed} className="h-4 w-4 rounded accent-emerald-500" onChange={() => toggleCheck(i)} />
                      <span className={`text-sm flex-1 ${item.completed ? 'line-through text-slate-500' : 'text-slate-200'}`}>{item.text}</span>
                      <button className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400"
                        onClick={() => setChecklist(checklist.filter((_, ci) => ci !== i))}><X size={12} /></button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex gap-2">
              <Input placeholder="Add checklist item..." className="h-8 text-sm bg-[#0f172a] border-white/15 text-slate-200 placeholder:text-slate-500"
                value={newCheckItem} onChange={e => setNewCheckItem(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') addCheck(); }} data-testid="new-check-item" />
              <Button size="sm" className="h-8 bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs" onClick={addCheck}>Add</Button>
            </div>

            {/* Attachments */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label className="flex items-center gap-2 text-sm font-semibold text-slate-300">
                  <Paperclip size={14} /> Attachments {attachments.length > 0 && <span className="text-xs text-slate-500">({attachments.length})</span>}
                </Label>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" className="h-7 text-xs text-slate-400 hover:text-white gap-1.5"
                    onClick={() => setShowAddLink(!showAddLink)} data-testid="add-link-btn">
                    <Link2 size={11} /> Link
                  </Button>
                  <Button size="sm" variant="ghost" className="h-7 text-xs text-slate-400 hover:text-white gap-1.5"
                    onClick={() => fileRef.current?.click()} disabled={uploadingAttachment} data-testid="attach-file-btn">
                    <Upload size={11} /> {uploadingAttachment ? 'Uploading...' : 'File'}
                  </Button>
                  <input ref={fileRef} type="file" className="hidden" onChange={handleFile} />
                </div>
              </div>
              {/* Add Link Form */}
              {showAddLink && (
                <div className="rounded-lg bg-[#0f172a] border border-white/10 p-3 space-y-2">
                  <Input className="h-8 text-xs bg-[#1e293b] border-white/10 text-white" placeholder="https://..." value={linkForm.url} onChange={e => setLinkForm({ ...linkForm, url: e.target.value })} onKeyDown={e => { if (e.key === 'Enter') addLinkAttachment(); }} data-testid="link-url-input" autoFocus />
                  <Input className="h-8 text-xs bg-[#1e293b] border-white/10 text-white" placeholder="Display name (optional)" value={linkForm.name} onChange={e => setLinkForm({ ...linkForm, name: e.target.value })} />
                  <div className="flex gap-2">
                    <Button size="sm" variant="ghost" className="h-7 text-xs text-slate-400" onClick={() => { setShowAddLink(false); setLinkForm({ url: '', name: '' }); }}>Cancel</Button>
                    <Button size="sm" className="h-7 text-xs" disabled={!linkForm.url.trim()} onClick={addLinkAttachment} data-testid="save-link-btn">Add Link</Button>
                  </div>
                </div>
              )}
              {attachments.map((att, i) => {
                const isLink = att.type === 'link' || (!att.name?.match(/\.\w+$/) && att.url?.startsWith('http'));
                const isImage = !isLink && att.name?.match(/\.(jpg|jpeg|png|gif|webp|svg)$/i);
                const isPdf = !isLink && att.name?.match(/\.pdf$/i);
                const fullUrl = att.url?.startsWith('http') ? att.url : (att.url ? `${process.env.REACT_APP_BACKEND_URL}${att.url.startsWith('/') ? '' : '/'}${att.url}` : '');
                return (
                <div key={att.id || att.name || i} className="rounded-lg bg-[#0f172a] border border-white/10 group overflow-hidden">
                  {isLink && fullUrl && (
                    <a href={fullUrl} target="_blank" rel="noopener noreferrer" className="flex items-center gap-3 p-3 hover:bg-white/5 transition-colors">
                      <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center shrink-0"><ExternalLink size={16} className="text-blue-400" /></div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-blue-300 truncate">{att.name}</p>
                        <p className="text-[10px] text-slate-500 truncate">{fullUrl}</p>
                      </div>
                    </a>
                  )}
                  {isImage && fullUrl && (
                    <a href={fullUrl} target="_blank" rel="noopener noreferrer">
                      <img src={fullUrl} alt={att.name} className="w-full h-32 object-cover rounded-t-lg hover:opacity-80 transition-opacity" onError={e => { e.target.style.display = 'none'; }} />
                    </a>
                  )}
                  {isPdf && fullUrl && (
                    <div className="w-full h-32 bg-slate-800 flex items-center justify-center rounded-t-lg cursor-pointer hover:bg-slate-700" onClick={() => window.open(fullUrl, '_blank')}>
                      <div className="text-center"><Paperclip size={24} className="text-red-400 mx-auto mb-1" /><p className="text-[10px] text-slate-400">PDF — Click to view</p></div>
                    </div>
                  )}
                  {!isLink && (
                  <div className="flex items-center gap-2 p-2">
                    <Paperclip size={12} className="text-slate-400 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-slate-200 truncate">{att.name}</p>
                      {att.source === 'trello' && <p className="text-[10px] text-slate-500">From Trello</p>}
                    </div>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      {fullUrl && <a href={fullUrl} target="_blank" rel="noopener noreferrer" className="text-slate-400 hover:text-blue-400 p-1" title="View"><Eye size={11} /></a>}
                      {fullUrl && <a href={fullUrl} download className="text-slate-400 hover:text-green-400 p-1" title="Download"><Download size={11} /></a>}
                      <button onClick={() => removeAttachment(att.id)} className="text-slate-400 hover:text-red-400 p-1" title="Delete"><X size={11} /></button>
                    </div>
                  </div>
                  )}
                  {isLink && (
                    <div className="flex items-center justify-end gap-1 px-2 pb-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={() => removeAttachment(att.id)} className="text-slate-400 hover:text-red-400 p-1" title="Remove"><X size={11} /></button>
                    </div>
                  )}
                </div>
                );
              })}
            </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs text-slate-400 flex items-center gap-1.5"><Flag size={11} /> Priority</Label>
              <Select value={priority} onValueChange={setPriority}>
                <SelectTrigger className="h-8 text-xs bg-[#0f172a] border-white/15 text-slate-200"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-[#1e293b] border-white/15">
                  {[['low','Low','#10b981'],['medium','Medium','#f59e0b'],['high','High','#f97316'],['urgent','Urgent','#ef4444']].map(([v,l,c]) => (
                    <SelectItem key={v} value={v} className="text-slate-200 focus:bg-white/10">
                      <span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: c }} />{l}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs text-slate-400 flex items-center gap-1.5"><Calendar size={11} /> Due Date</Label>
              <Input type="date" className="h-8 text-xs bg-[#0f172a] border-white/15 text-slate-200"
                value={dueDate} onChange={e => setDueDate(e.target.value)} />
            </div>

            {/* Recurring */}
            <div className="space-y-1.5">
              <label className="flex items-center gap-2 cursor-pointer text-xs text-slate-400">
                <input type="checkbox" className="h-3 w-3 accent-blue-500" checked={isRecurring}
                  onChange={e => setIsRecurring(e.target.checked)} data-testid="recurring-toggle" />
                Recurring Task
              </label>
              {isRecurring && (
                <div className="flex gap-2">
                  <Select value={recurrencePattern} onValueChange={setRecurrencePattern}>
                    <SelectTrigger className="h-7 text-[11px] bg-[#0f172a] border-white/15 text-slate-200 flex-1"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="daily">Daily</SelectItem>
                      <SelectItem value="weekly">Weekly</SelectItem>
                      <SelectItem value="biweekly">Bi-weekly</SelectItem>
                      <SelectItem value="monthly">Monthly</SelectItem>
                    </SelectContent>
                  </Select>
                  <Input type="number" min={1} max={12} className="h-7 w-16 text-[11px] bg-[#0f172a] border-white/15 text-slate-200"
                    value={recurrenceInterval} onChange={e => setRecurrenceInterval(parseInt(e.target.value) || 1)} placeholder="N" />
                </div>
              )}
            </div>

            {/* Location-filtered members */}
            <div className="space-y-1.5">
              <Label className="text-xs text-slate-400 flex items-center gap-1.5">
                <Users size={11} /> Members
                {board?.location_id && !board?.is_global && (
                  <span className="text-[10px] text-slate-600 ml-auto">(location)</span>
                )}
              </Label>
              <div className="max-h-36 overflow-y-auto space-y-1 rounded-lg bg-[#0f172a] border border-white/10 p-1.5">
                {boardStaff.slice(0, 60).map(u => (
                  <label key={u.id} className="flex items-center gap-2 cursor-pointer px-1 py-0.5 rounded hover:bg-white/5">
                    <input type="checkbox" className="h-3 w-3 accent-blue-500" checked={assignees.includes(u.id)}
                      onChange={() => toggleAssignee(u.id)} />
                    <span className="h-5 w-5 rounded-full bg-slate-600 flex items-center justify-center text-[9px] font-bold text-white flex-shrink-0">
                      {u.name?.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
                    </span>
                    <span className="text-xs text-slate-300 truncate">{u.name}</span>
                    {u.location_id && board?.location_id === u.location_id && (
                      <span className="text-[9px] text-blue-400 ml-auto">same loc</span>
                    )}
                  </label>
                ))}
                {boardStaff.length === 0 && <p className="text-xs text-slate-500 text-center py-1">No staff found</p>}
              </div>
              {/* External user search */}
              <div className="mt-2">
                <Input className="h-7 text-xs bg-[#0f172a] border-white/10 text-white placeholder:text-slate-500" placeholder="Search other campuses..." 
                  onChange={async (e) => {
                    const q = e.target.value.trim();
                    if (q.length < 2) return;
                    try {
                      const res = await adminApi.users({ search: q, limit: 10 });
                      const ext = (res.data || []).filter(u => !boardStaff.find(s => s.id === u.id));
                      const container = e.target.parentElement.querySelector('.ext-results');
                      if (container) container.innerHTML = ext.map(u => `<div class="ext-user" data-id="${u.id}" data-name="${u.name}">${u.name} (${u.role || '?'})</div>`).join('') || '<div class="text-slate-500 text-center py-1">No matches</div>';
                    } catch {}
                  }}
                  onClick={(e) => {
                    const handler = (ev) => {
                      if (ev.target.classList.contains('ext-user')) {
                        toggleAssignee(ev.target.dataset.id);
                        ev.target.style.opacity = '0.5';
                      }
                    };
                    const container = e.target.parentElement.querySelector('.ext-results');
                    if (container) container.addEventListener('click', handler);
                  }}
                />
                <div className="ext-results max-h-24 overflow-y-auto mt-1 space-y-0.5 text-xs text-slate-300 [&_.ext-user]:px-2 [&_.ext-user]:py-1 [&_.ext-user]:rounded [&_.ext-user]:cursor-pointer [&_.ext-user:hover]:bg-white/10"></div>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs text-slate-400 flex items-center gap-1.5"><Tag size={11} /> Labels</Label>
              <div className="flex flex-wrap gap-1.5">
                {LABEL_COLORS.map(color => (
                  <button key={color}
                    className={`h-5 w-8 rounded transition-transform hover:scale-110 ${labels.find(l => (l.color || l) === color) ? 'ring-2 ring-white ring-offset-1 ring-offset-[#1e293b]' : ''}`}
                    style={{ background: color }} onClick={() => toggleLabel(color)} />
                ))}
              </div>
            </div>

            {board?.lists?.length > 1 && (
              <div className="space-y-1.5">
                <Label className="text-xs text-slate-400 flex items-center gap-1.5"><ChevronRight size={11} /> Move to</Label>
                <Select value={card.list_id || ''} onValueChange={toListId => { if (toListId && toListId !== card.list_id) onMove?.(card, card.list_id, toListId); }}>
                  <SelectTrigger className="h-8 text-xs bg-[#0f172a] border-white/15 text-slate-200"><SelectValue placeholder="Select list" /></SelectTrigger>
                  <SelectContent className="bg-[#1e293b] border-white/15">
                    {board.lists.map(l => <SelectItem key={l.id} value={l.id} className="text-slate-200 focus:bg-white/10 text-xs">{l.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            )}

            <Button size="sm" className="w-full h-8 text-xs bg-blue-600 hover:bg-blue-700 text-white gap-1.5"
              onClick={save} disabled={saving} data-testid="save-card-btn">
              <Check size={12} /> {saving ? 'Saving...' : 'Save Card'}
            </Button>
            <Button size="sm" variant="ghost" className="w-full h-8 text-xs text-amber-400 hover:text-amber-300 hover:bg-amber-500/10 gap-1.5"
              onClick={() => { save(); onArchive?.(card); }}>
              <Archive size={12} /> Archive Card
            </Button>
            <Button size="sm" variant="ghost" className="w-full h-8 text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 gap-1.5"
              onClick={() => onDelete?.(card)}>
              <Trash2 size={12} /> Delete Card
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}


// ========= Task Time Tracker Widget =========
function TaskTimeTracker({ taskId }) {
  const [entries, setEntries] = useState([]);
  const [active, setActive] = useState(null);
  const [totalHours, setTotalHours] = useState(0);
  const [tick, setTick] = useState(0);
  const [logForm, setLogForm] = useState({ minutes: '', date: new Date().toISOString().slice(0, 10), notes: '' });
  const [showLog, setShowLog] = useState(false);

  const reload = useCallback(async () => {
    try {
      const [list, activeRes] = await Promise.all([
        api.get(`/tasks/${taskId}/time`),
        api.get('/time/me/active').catch(() => ({ data: null })),
      ]);
      setEntries(list.data.entries || []);
      setTotalHours(list.data.total_hours || 0);
      const a = activeRes.data;
      setActive(a && a.task_id === taskId ? a : null);
    } catch { /* ignore */ }
  }, [taskId]);
  useEffect(() => { reload(); }, [reload]);
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setTick(x => x + 1), 1000);
    return () => clearInterval(t);
  }, [active]);

  const elapsed = active ? (() => {
    const start = new Date(active.started_at);
    const s = Math.max(0, Math.floor((Date.now() - start.getTime()) / 1000));
    return `${String(Math.floor(s/3600)).padStart(2,'0')}:${String(Math.floor((s%3600)/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`;
  })() : null;

  const start = async () => {
    try { await api.post(`/tasks/${taskId}/time/start`); reload(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };
  const stop = async () => {
    try { await api.post(`/tasks/${taskId}/time/stop`); toast.success('Time logged'); reload(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };
  const logManual = async () => {
    try {
      const payload = { minutes: parseInt(logForm.minutes), date: logForm.date, notes: logForm.notes };
      await api.post(`/tasks/${taskId}/time/log`, payload);
      toast.success('Time logged');
      setShowLog(false);
      setLogForm({ minutes: '', date: new Date().toISOString().slice(0, 10), notes: '' });
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };
  const deleteEntry = async (id) => {
    if (!window.confirm('Delete this time entry?')) return;
    try { await api.delete(`/tasks/${taskId}/time/${id}`); reload(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  return (
    <div className="space-y-2" data-testid="task-time-tracker">
      <div className="flex items-center justify-between">
        <Label className="flex items-center gap-2 text-sm font-semibold text-slate-300">
          <Clock size={14} /> Time Tracking
          {totalHours > 0 && <span className="text-xs text-slate-500 font-normal">{totalHours}h logged</span>}
        </Label>
        <div className="flex gap-1">
          {active ? (
            <Button size="sm" variant="destructive" className="h-7 text-xs" onClick={stop} data-testid="task-time-stop"><Square size={11} className="mr-1" />Stop {elapsed}</Button>
          ) : (
            <Button size="sm" variant="outline" className="h-7 text-xs bg-[#0f172a] border-white/15 text-slate-200" onClick={start} data-testid="task-time-start"><Play size={11} className="mr-1" />Start</Button>
          )}
          <Button size="sm" variant="ghost" className="h-7 text-xs text-slate-300" onClick={() => setShowLog(s => !s)} data-testid="task-time-log-btn">Log manually</Button>
        </div>
      </div>
      {showLog && (
        <div className="grid grid-cols-12 gap-2 p-2 rounded bg-[#0f172a] border border-white/10">
          <Input className="col-span-3 h-7 text-xs" type="number" placeholder="minutes" value={logForm.minutes} onChange={e => setLogForm({...logForm, minutes: e.target.value})} data-testid="task-time-log-mins" />
          <Input className="col-span-3 h-7 text-xs" type="date" value={logForm.date} onChange={e => setLogForm({...logForm, date: e.target.value})} />
          <Input className="col-span-4 h-7 text-xs" placeholder="notes" value={logForm.notes} onChange={e => setLogForm({...logForm, notes: e.target.value})} />
          <Button size="sm" className="col-span-2 h-7 text-xs" disabled={!logForm.minutes} onClick={logManual} data-testid="task-time-log-submit">Log</Button>
        </div>
      )}
      {entries.length > 0 && (
        <div className="space-y-1 text-xs">
          {entries.slice(0, 8).map(e => (
            <div key={e.id} className="flex items-center justify-between p-1.5 rounded bg-[#0f172a]/50">
              <span className="text-slate-300">{e.user_name} · {(e.started_at || '').slice(0, 10)}</span>
              <div className="flex items-center gap-2">
                <span className="text-slate-200 font-medium">{e.ended_at ? `${Math.floor((e.duration_minutes||0)/60)}h ${(e.duration_minutes||0)%60}m` : 'running'}</span>
                <button onClick={() => deleteEntry(e.id)} className="text-slate-500 hover:text-red-400">×</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

