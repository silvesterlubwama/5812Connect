import React, { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import api from '../../services/api';

const SWATCHES = ['#6366f1', '#f59e0b', '#3b82f6', '#10b981', '#8b5cf6', '#ec4899',
  '#14b8a6', '#f97316', '#ef4444', '#64748b', '#84cc16', '#0ea5e9'];

// Add, rename, recolour or remove the event types the calendar offers.
export const EventTypesDialog = ({ open, onOpenChange, onChanged }) => {
  const [types, setTypes] = useState([]);
  const [draft, setDraft] = useState({ label: '', color: SWATCHES[0] });
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const r = await api.get('/event-types');
      setTypes(r.data || []);
    } catch { toast.error('Could not load event types'); }
  };
  useEffect(() => { if (open) load(); }, [open]);

  const add = async () => {
    if (!draft.label.trim()) { toast.error('Give the type a name'); return; }
    setBusy(true);
    try {
      await api.post('/event-types', { name: draft.label.trim(), label: draft.label.trim(), color: draft.color });
      setDraft({ label: '', color: SWATCHES[0] });
      await load();
      onChanged?.();
      toast.success('Event type added');
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not add the type'); }
    finally { setBusy(false); }
  };

  const save = async (t, patch) => {
    setTypes(prev => prev.map(x => x.id === t.id ? { ...x, ...patch } : x));
    try {
      await api.put(`/event-types/${t.id}`, patch);
      onChanged?.();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not save'); }
  };

  const remove = async (t) => {
    if (!window.confirm(`Remove "${t.label || t.name}"? Events already using it keep their type.`)) return;
    try {
      await api.delete(`/event-types/${t.id}`);
      await load();
      onChanged?.();
    } catch (e) { toast.error(e.response?.data?.detail || 'Only an admin can remove a type'); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="event-types-dialog">
        <DialogHeader><DialogTitle>Event types</DialogTitle></DialogHeader>
        <div className="space-y-2">
          {types.map(t => (
            <div key={t.id} className="flex items-center gap-2" data-testid={`event-type-row-${t.name}`}>
              <input type="color" value={t.color || '#6366f1'} className="h-8 w-9 rounded border bg-transparent"
                onChange={e => save(t, { color: e.target.value })} data-testid={`event-type-color-${t.name}`} />
              <Input className="h-8 text-xs flex-1" value={t.label || t.name}
                onChange={e => setTypes(prev => prev.map(x => x.id === t.id ? { ...x, label: e.target.value } : x))}
                onBlur={e => save(t, { label: e.target.value })}
                data-testid={`event-type-label-${t.name}`} />
              <button type="button" className="text-destructive" onClick={() => remove(t)}
                data-testid={`event-type-remove-${t.name}`}><Trash2 size={14} /></button>
            </div>
          ))}
          {types.length === 0 && <p className="text-xs text-muted-foreground">No types yet — add your first one below.</p>}
        </div>

        <div className="border-t pt-3 space-y-2">
          <Label className="text-xs">Add a type</Label>
          <div className="flex items-center gap-2">
            <input type="color" value={draft.color} className="h-8 w-9 rounded border bg-transparent"
              onChange={e => setDraft({ ...draft, color: e.target.value })} data-testid="event-type-new-color" />
            <Input className="h-8 text-xs flex-1" placeholder="e.g. Youth Camp" value={draft.label}
              onChange={e => setDraft({ ...draft, label: e.target.value })} data-testid="event-type-new-label" />
            <Button size="sm" className="h-8 gap-1" onClick={add} disabled={busy} data-testid="event-type-add-btn">
              <Plus size={13} /> Add
            </Button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {SWATCHES.map(c => (
              <button key={c} type="button" className="h-5 w-5 rounded-full border"
                style={{ backgroundColor: c }} onClick={() => setDraft({ ...draft, color: c })} />
            ))}
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default EventTypesDialog;
