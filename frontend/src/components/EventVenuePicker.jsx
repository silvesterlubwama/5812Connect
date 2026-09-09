import React, { useState } from 'react';
import { Building2, MapPin, Plus } from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from './ui/select';
import { venuesApi } from '../services/api';
import { toast } from 'sonner';

const NEW = '__new__';
const CUSTOM = '__custom__';

const isExternal = (v) => !v.location_id || v.is_offsite || v.is_external;

/** Venue chooser for events. Order of preference, per house rules:
 *  1. venues at a campus the user can actually access (restricted ones stay out —
 *     the API filters them), 2. external venues we've used before,
 *  3. add a brand-new venue right here, 4. a one-off typed address.
 *
 *  `value` = { venue_id, location, location_id }. Emits patches via onChange.
 */
export const EventVenuePicker = ({ value, onChange, venues = [], locations = [], onVenueCreated, idPrefix = 'venue' }) => {
  const [mode, setMode] = useState(() => (value?.venue_id ? value.venue_id : (value?.location ? CUSTOM : '')));
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState({ name: '', address: '', country: '', capacity: '', external: true, location_id: '' });
  // Venues created in this dialog — kept locally so the freshly-saved option
  // exists in the list the instant we select it (Radix needs the item mounted).
  const [justAdded, setJustAdded] = useState([]);

  const all = [...venues, ...justAdded.filter(j => !venues.some(v => v.id === j.id))];
  const campusVenues = all.filter(v => !isExternal(v));
  const externalVenues = all.filter(isExternal);
  const locName = (id) => locations.find(l => l.id === id)?.name || 'Campus';

  const pick = (val) => {
    setMode(val);
    if (val === NEW || val === CUSTOM) {
      onChange({ venue_id: '', location: val === CUSTOM ? (value?.location || '') : '' });
      return;
    }
    const v = all.find(x => x.id === val);
    if (!v) return;
    onChange({
      venue_id: v.id,
      location: v.name + (v.address ? ` — ${v.address}` : ''),
      ...(v.location_id ? { location_id: v.location_id } : {}),
    });
  };

  const createVenue = async () => {
    if (!draft.name.trim()) return toast.error('Give the venue a name');
    setSaving(true);
    try {
      const res = await venuesApi.create({
        name: draft.name.trim(),
        address: draft.address.trim() || undefined,
        country: draft.country.trim() || undefined,
        capacity: draft.capacity ? parseInt(draft.capacity) : undefined,
        is_offsite: draft.external,
        is_external: draft.external,
        location_id: draft.external ? undefined : (draft.location_id || undefined),
        is_bookable: true,
      });
      const v = res.data;
      toast.success(`${v.name} saved — it'll be in the list next time too`);
      setJustAdded(prev => [...prev, v]);
      onVenueCreated?.();
      setDraft({ name: '', address: '', country: '', capacity: '', external: true, location_id: '' });
      setMode(v.id);
      onChange({ venue_id: v.id, location: v.name + (v.address ? ` — ${v.address}` : ''), ...(v.location_id ? { location_id: v.location_id } : {}) });
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not save venue');
    } finally { setSaving(false); }
  };

  return (
    <div className="space-y-2">
      <Label>Venue</Label>
      <Select value={mode} onValueChange={pick}>
        <SelectTrigger data-testid={`${idPrefix}-select`}><SelectValue placeholder="Pick a venue" /></SelectTrigger>
        <SelectContent className="max-h-72">
          {campusVenues.length > 0 && (
            <SelectGroup>
              <SelectLabel className="flex items-center gap-1.5 text-xs"><Building2 size={12} />Our venues</SelectLabel>
              {campusVenues.map(v => (
                <SelectItem key={v.id} value={v.id}>{v.name} · {locName(v.location_id)}{v.capacity ? ` · ${v.capacity} seats` : ''}</SelectItem>
              ))}
            </SelectGroup>
          )}
          {externalVenues.length > 0 && (
            <SelectGroup>
              <SelectLabel className="flex items-center gap-1.5 text-xs"><MapPin size={12} />External venues used before</SelectLabel>
              {externalVenues.map(v => (
                <SelectItem key={v.id} value={v.id}>{v.name}{v.address ? ` · ${v.address}` : ''}</SelectItem>
              ))}
            </SelectGroup>
          )}
          <SelectGroup>
            <SelectItem value={NEW} data-testid={`${idPrefix}-add-new`}>+ Add a new venue…</SelectItem>
            <SelectItem value={CUSTOM} data-testid={`${idPrefix}-custom`}>One-off — just type the place</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>

      {mode === CUSTOM && (
        <Input placeholder="e.g. Kampala Serena Hotel, Kintu Road" value={value?.location || ''}
          onChange={e => onChange({ location: e.target.value, venue_id: '' })} data-testid={`${idPrefix}-custom-input`} />
      )}

      {mode === NEW && (
        <div className="rounded-lg border border-border p-3 space-y-2" data-testid={`${idPrefix}-new-form`}>
          <div className="grid grid-cols-2 gap-2">
            <div className="col-span-2"><Label className="text-xs">Venue name</Label>
              <Input className="h-8" value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} placeholder="Serena Victoria Hall" data-testid={`${idPrefix}-new-name`} />
            </div>
            <div className="col-span-2"><Label className="text-xs">Address</Label>
              <Input className="h-8" value={draft.address} onChange={e => setDraft({ ...draft, address: e.target.value })} placeholder="Kintu Road, Kampala" data-testid={`${idPrefix}-new-address`} />
            </div>
            <div><Label className="text-xs">Country</Label>
              <Input className="h-8" value={draft.country} onChange={e => setDraft({ ...draft, country: e.target.value })} placeholder="Uganda" data-testid={`${idPrefix}-new-country`} />
            </div>
            <div><Label className="text-xs">Capacity</Label>
              <Input className="h-8" type="number" min="0" value={draft.capacity} onChange={e => setDraft({ ...draft, capacity: e.target.value })} data-testid={`${idPrefix}-new-capacity`} />
            </div>
          </div>
          <label className="flex items-center gap-2 text-xs">
            <input type="checkbox" checked={draft.external} onChange={e => setDraft({ ...draft, external: e.target.checked })} data-testid={`${idPrefix}-new-external`} />
            External / off-site venue (not one of our campuses)
          </label>
          {!draft.external && (
            <Select value={draft.location_id} onValueChange={v => setDraft({ ...draft, location_id: v })}>
              <SelectTrigger className="h-8" data-testid={`${idPrefix}-new-campus`}><SelectValue placeholder="Which campus?" /></SelectTrigger>
              <SelectContent>{locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
            </Select>
          )}
          <Button type="button" size="sm" className="w-full h-8" disabled={saving} onClick={createVenue} data-testid={`${idPrefix}-new-save`}>
            <Plus size={13} className="mr-1" />{saving ? 'Saving…' : 'Save venue & use it'}
          </Button>
        </div>
      )}
    </div>
  );
};

export default EventVenuePicker;
