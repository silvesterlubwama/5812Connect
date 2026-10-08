import React, { useState } from 'react';
import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Button } from '../ui/button';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Layers, Share2, Trash2, Palette, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import api from '../../services/api';

const TASK_SCOPES = [
  { value: 'mine', label: 'My tasks only' },
  { value: 'campus', label: 'All tasks in my campus' },
  { value: 'off', label: 'Hide tasks' },
];

const Row = ({ checked, onChange, label, note, testId, children }) => (
  <label className="flex items-start gap-2 py-1 cursor-pointer text-xs">
    <input type="checkbox" className="mt-0.5" checked={checked} onChange={e => onChange(e.target.checked)}
      data-testid={testId} />
    <span className="flex-1">
      {label}
      {note && <span className="block text-[10px] text-muted-foreground">{note}</span>}
    </span>
    {children}
  </label>
);

/** The familiar "my calendars" list: everything is on until you untick it.
 *  Campuses and sub-locations, each imported calendar, holidays and tasks. */
export const CalendarsPanel = ({
  locations = [], calendars = [], prefs, onPrefsChange, onCalendarsChanged,
  users = [], onManageTypes,
}) => {
  const [shareCal, setShareCal] = useState(null);
  const [shareUsers, setShareUsers] = useState([]);
  const [shareLocs, setShareLocs] = useState([]);
  const [saving, setSaving] = useState(false);

  const hiddenLocs = prefs.hidden_location_ids || [];
  const hiddenCals = prefs.hidden_calendar_ids || [];

  const toggleIn = (list, id, on) => (on ? list.filter(x => x !== id) : [...list, id]);

  const openShare = (c) => {
    setShareCal(c);
    setShareUsers(c.visible_to_users || []);
    setShareLocs(c.visible_to_locations || []);
  };

  const saveShare = async () => {
    setSaving(true);
    try {
      await api.put(`/events/imported-calendars/${shareCal.id}/share`,
        { user_ids: shareUsers, location_ids: shareLocs });
      toast.success(shareUsers.length + shareLocs.length === 0
        ? 'Calendar is private again'
        : 'Calendar shared');
      setShareCal(null);
      onCalendarsChanged?.();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not share the calendar'); }
    finally { setSaving(false); }
  };

  const refreshCal = async (c) => {
    try {
      const r = await api.post(`/events/imported-calendars/${c.id}/refresh`);
      toast.success(r.data?.message || 'Calendar refreshed');
      onCalendarsChanged?.();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not refresh it'); }
  };

  const removeCal = async (c) => {    if (!window.confirm(`Remove "${c.name}" and its ${c.event_count || 0} events from the calendar?`)) return;
    try {
      const r = await api.delete(`/events/imported-calendars/${c.id}`);
      toast.success(r.data?.message || 'Imported calendar removed');
      onCalendarsChanged?.();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not remove it'); }
  };

  return (
    <>
      <Popover>
        <PopoverTrigger asChild>
          <Button size="sm" variant="outline" className="h-8 text-xs gap-1.5" data-testid="calendars-panel-btn">
            <Layers size={14} /> Calendars
            {(hiddenLocs.length + hiddenCals.length) > 0 && (
              <span className="ml-0.5 rounded-full bg-primary/10 px-1.5 text-[10px]">
                {hiddenLocs.length + hiddenCals.length} off
              </span>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-80 max-h-[70vh] overflow-y-auto p-3 space-y-3" align="end"
          data-testid="calendars-panel">
          <div>
            <Label className="text-[11px] uppercase tracking-wide text-muted-foreground">Campuses & locations</Label>
            {locations.length === 0 && <p className="text-xs text-muted-foreground">No locations yet.</p>}
            {locations.map(l => (
              <Row key={l.id} testId={`cal-loc-${l.id}`}
                checked={!hiddenLocs.includes(l.id)}
                label={l.name}
                note={l.parent_id ? 'sub-location' : 'campus'}
                onChange={on => onPrefsChange({ hidden_location_ids: toggleIn(hiddenLocs, l.id, on) })} />
            ))}
          </div>

          <div className="border-t pt-2">
            <Label className="text-[11px] uppercase tracking-wide text-muted-foreground">Imported calendars</Label>
            {calendars.length === 0 && (
              <p className="text-xs text-muted-foreground">None yet — use More → Import .ics.</p>
            )}
            {calendars.map(c => (
              <Row key={c.id} testId={`cal-imported-${c.id}`}
                checked={!hiddenCals.includes(c.id)}
                label={c.name}
                note={`${c.event_count || 0} events · ${c.is_owner ? 'yours' : `shared by ${c.owner_name || 'a colleague'}`}`}
                onChange={on => onPrefsChange({ hidden_calendar_ids: toggleIn(hiddenCals, c.id, on) })}>
                {c.is_owner && (
                  <span className="flex items-center gap-1">
                    {c.source_url && (
                      <button type="button" title="Refresh from the link"
                        onClick={(e) => { e.preventDefault(); refreshCal(c); }}
                        data-testid={`cal-refresh-${c.id}`}><RefreshCw size={13} /></button>
                    )}
                    <button type="button" title="Share this calendar" onClick={(e) => { e.preventDefault(); openShare(c); }}
                      data-testid={`cal-share-${c.id}`}><Share2 size={13} /></button>
                    <button type="button" title="Remove this calendar" className="text-destructive"
                      onClick={(e) => { e.preventDefault(); removeCal(c); }}
                      data-testid={`cal-remove-${c.id}`}><Trash2 size={13} /></button>
                  </span>
                )}
              </Row>
            ))}
          </div>

          <div className="border-t pt-2 space-y-2">
            <Row testId="cal-holidays-check" checked={prefs.show_holidays !== false}
              label="Public holidays" note="US federal + Uganda public"
              onChange={on => onPrefsChange({ show_holidays: on })} />
            <div>
              <Label className="text-[11px] uppercase tracking-wide text-muted-foreground">Tasks</Label>
              <Select value={prefs.task_scope || 'campus'} onValueChange={v => onPrefsChange({ task_scope: v })}>
                <SelectTrigger className="h-8 text-xs mt-1" data-testid="cal-task-scope"><SelectValue /></SelectTrigger>
                <SelectContent>{TASK_SCOPES.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <Button size="sm" variant="ghost" className="w-full justify-start gap-2 h-8 text-xs"
              onClick={onManageTypes} data-testid="cal-manage-types-btn">
              <Palette size={13} /> Manage event types
            </Button>
          </div>
        </PopoverContent>
      </Popover>

      <Dialog open={!!shareCal} onOpenChange={o => !o && setShareCal(null)}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto" data-testid="cal-share-dialog">
          <DialogHeader><DialogTitle>Share "{shareCal?.name}"</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-xs">People</Label>
              <div className="max-h-40 overflow-y-auto rounded border p-2 mt-1">
                {users.map(u => (
                  <label key={u.id} className="flex items-center gap-2 text-xs py-0.5 cursor-pointer">
                    <input type="checkbox" checked={shareUsers.includes(u.id)}
                      onChange={e => setShareUsers(prev => e.target.checked ? [...prev, u.id] : prev.filter(x => x !== u.id))}
                      data-testid={`share-user-${u.id}`} />
                    {u.name} <span className="text-muted-foreground">{u.email}</span>
                  </label>
                ))}
                {users.length === 0 && <p className="text-xs text-muted-foreground">No other users found.</p>}
              </div>
            </div>
            <div>
              <Label className="text-xs">Campuses & locations</Label>
              <div className="max-h-40 overflow-y-auto rounded border p-2 mt-1">
                {locations.map(l => (
                  <label key={l.id} className="flex items-center gap-2 text-xs py-0.5 cursor-pointer">
                    <input type="checkbox" checked={shareLocs.includes(l.id)}
                      onChange={e => setShareLocs(prev => e.target.checked ? [...prev, l.id] : prev.filter(x => x !== l.id))}
                      data-testid={`share-loc-${l.id}`} />
                    {l.name}
                  </label>
                ))}
              </div>
            </div>
            <p className="text-[10px] text-muted-foreground">
              Anyone you pick sees these events on their own calendar and can switch them off there.
            </p>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShareCal(null)}>Cancel</Button>
            <Button onClick={saveShare} disabled={saving} data-testid="cal-share-save">
              {saving ? 'Saving…' : 'Save sharing'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default CalendarsPanel;
