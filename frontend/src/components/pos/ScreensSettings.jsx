import { useCallback, useEffect, useState } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Monitor, Copy, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { screensApi } from '../../services/api';

/**
 * Screens on the wall. A manager who works at this store pairs the device
 * once; the link it gets back is what the kitchen or the customer display
 * opens — nobody signs in on that screen ever again (iter420).
 */
export const ScreensSettings = ({ locationId, canManage = true }) => {
  const [screens, setScreens] = useState([]);
  const [kind, setKind] = useState('kitchen');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    if (!locationId) return;
    screensApi.list({ location_id: locationId })
      .then(r => setScreens(r.data || [])).catch(() => setScreens([]));
  }, [locationId]);

  useEffect(() => { load(); }, [load]);

  const linkFor = (s) => `${window.location.origin}/screen/${s.token}`;

  const pair = async () => {
    setBusy(true);
    try {
      const r = await screensApi.pair({ kind, location_id: locationId, name: name.trim() });
      toast.success(r.data?.message || 'Screen paired');
      setName('');
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not pair that screen');
    } finally { setBusy(false); }
  };

  const copy = async (s) => {
    try {
      await navigator.clipboard.writeText(linkFor(s));
      toast.success('Link copied — open it once on that screen');
    } catch {
      window.prompt('Copy this link onto the screen:', linkFor(s));
    }
  };

  const revoke = async (s) => {
    if (!window.confirm(`Unpair ${s.name}? That screen will stop showing anything.`)) return;
    try {
      await screensApi.revoke(s.id);
      toast.success('Screen unpaired');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not unpair it'); }
  };

  if (!locationId) return null;

  return (
    <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/40 dark:bg-slate-900/30 space-y-2"
         data-testid="screens-settings-block">
      <p className="text-xs font-semibold flex items-center gap-2"><Monitor size={13} /> Screens on the wall</p>
      <p className="text-[10px] text-muted-foreground">
        A kitchen board for the cooks, or a display the customer watches while you ring the sale up.
        Open the link once on that screen and leave it there — no sign-in, and it only ever shows this store.
      </p>

      {canManage && (
        <div className="flex flex-wrap gap-2 items-center">
          <Select value={kind} onValueChange={setKind}>
            <SelectTrigger className="h-8 text-xs w-40" data-testid="screen-kind-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="kitchen">Kitchen screen</SelectItem>
              <SelectItem value="sales">Customer display</SelectItem>
            </SelectContent>
          </Select>
          <Input value={name} onChange={e => setName(e.target.value)} placeholder="Name it (Grill screen)"
                 className="h-8 text-xs flex-1 min-w-[8rem]" data-testid="screen-name-input" />
          <Button size="sm" className="h-8 text-xs" onClick={pair} disabled={busy} data-testid="pair-screen-btn">
            {busy ? 'Pairing…' : 'Pair a screen'}
          </Button>
        </div>
      )}

      {!!screens.length && (
        <div className="rounded-lg border border-border divide-y divide-border">
          {screens.map(s => (
            <div key={s.id} className="flex items-center gap-2 px-2.5 py-1.5" data-testid={`screen-row-${s.id}`}>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium truncate">
                  {s.name} <span className="text-muted-foreground font-normal">
                    · {s.kind === 'kitchen' ? 'kitchen board' : 'customer display'}</span>
                </p>
                <p className="text-[10px] text-muted-foreground truncate">{linkFor(s)}</p>
              </div>
              <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => copy(s)}
                      title="Copy the link" data-testid={`screen-copy-${s.id}`}><Copy size={12} /></Button>
              {canManage && (
                <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive" onClick={() => revoke(s)}
                        title="Unpair this screen" data-testid={`screen-revoke-${s.id}`}><Trash2 size={12} /></Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
