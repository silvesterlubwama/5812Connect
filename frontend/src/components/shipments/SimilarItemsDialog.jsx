import React, { useState, useCallback, useEffect } from 'react';
import { Copy, Layers, Trash2, Undo2, RefreshCw, Boxes, AlertTriangle } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Card, CardContent } from '../ui/card';
import { Input } from '../ui/input';
import api from '../../services/api';
import { toast } from 'sonner';

const LEVELS = [
  { id: 'strict', label: 'Strict', hint: 'Almost the same wording' },
  { id: 'normal', label: 'Normal', hint: 'Same thing, different wording' },
  { id: 'loose', label: 'Loose', hint: 'Anything related — check carefully' },
];

// "Children's clothes size 14" + "…size 10" → "Children's clothes" so the
// combined customs line reads as one product rather than one of the sizes.
const commonName = (items) => {
  const words = items.map(i => (i.name || '').trim().split(/\s+/));
  const first = words[0] || [];
  const out = [];
  for (let n = 0; n < first.length; n++) {
    const w = first[n].toLowerCase();
    if (words.every(ws => (ws[n] || '').toLowerCase() === w)) out.push(first[n]);
    else break;
  }
  const prefix = out.join(' ').replace(/[\s,–-]+$/, '');
  return prefix.length >= 3 ? prefix : (items.sort((a, b) => b.name.length - a.name.length)[0]?.name || '');
};

const money = (n) => `$${Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

// One customs line per real product: find items that read the same, show what
// combining them would look like (quantity + value added up, boxes as "24 & 25")
// and let the admin combine across boxes, within one box, or delete a repeat.
export const SimilarItemsDialog = ({ open, onOpenChange, shipmentId, onChanged }) => {
  const [level, setLevel] = useState('strict');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState('');
  const [picks, setPicks] = useState({});      // groupId -> { keep, include: Set }
  const [skipped, setSkipped] = useState([]);

  const load = useCallback(async (sensitivity) => {
    if (!shipmentId) return;
    setLoading(true);
    try {
      const r = await api.get(`/shipments/${shipmentId}/similar-items`, { params: { sensitivity } });
      setData(r.data);
      const next = {};
      (r.data.groups || []).forEach(g => {
        next[g.id] = { keep: g.suggested_keep, include: new Set(g.items.map(i => i.id)), name: commonName([...g.items]) };
      });
      setPicks(next);
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not scan the packing list'); }
    finally { setLoading(false); }
  }, [shipmentId]);

  useEffect(() => { if (open) { setSkipped([]); load(level); } }, [open, level, load]);

  const setKeep = (gid, id) => setPicks(p => ({ ...p, [gid]: { ...p[gid], keep: id } }));
  const toggleInclude = (gid, id) => setPicks(p => {
    const cur = new Set(p[gid]?.include || []);
    if (cur.has(id)) cur.delete(id); else cur.add(id);
    return { ...p, [gid]: { ...p[gid], include: cur } };
  });

  const act = async (group, mode) => {
    const pick = picks[group.id] || {};
    const name = (pick.name ?? group.label ?? '').trim();
    if (mode !== 'delete_repeats' && !name) { toast.error('Give the combined line a name customs will understand'); return; }
    const keepId = pick.keep || group.suggested_keep;
    const mergeIds = group.items
      .map(i => i.id)
      .filter(id => id !== keepId && (pick.include ? pick.include.has(id) : true));
    if (!mergeIds.length) { toast.error('Tick at least one duplicate line'); return; }
    setBusy(group.id);
    try {
      const r = await api.post(`/shipments/${shipmentId}/items/consolidate`,
        { keep_id: keepId, merge_ids: mergeIds, mode, name });
      toast.success(mode === 'delete_repeats'
        ? `Removed ${r.data.removed} repeated line${r.data.removed > 1 ? 's' : ''}`
        : `One line now: ${r.data.qty_acquired} × ${money(r.data.line_value / (r.data.qty_acquired || 1))} — ${r.data.box_label}`);
      onChanged?.();
      await load(level);
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not combine those lines'); }
    finally { setBusy(''); }
  };

  const groups = (data?.groups || []).filter(g => !skipped.includes(g.label));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto" data-testid="ship-similar-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Copy size={16} /> Similar items &amp; repeated lines</DialogTitle>
          <DialogDescription>
            The same thing entered twice — or spread over two boxes — reads as two consignment lines at
            customs. Combine them into one line and the quantity, value and box numbers are added up for you.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-between gap-3 flex-wrap mt-1">
          <div className="flex gap-1.5">
            {LEVELS.map(l => (
              <Button key={l.id} size="sm" variant={level === l.id ? 'default' : 'outline'}
                className="h-7 text-[11px]" title={l.hint}
                onClick={() => setLevel(l.id)} data-testid={`ship-similar-level-${l.id}`}>{l.label}</Button>
            ))}
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            {data && (
              <span data-testid="ship-similar-summary">
                {groups.length} group{groups.length === 1 ? '' : 's'} · {data.duplicate_lines} extra line
                {data.duplicate_lines === 1 ? '' : 's'} · {data.across_boxes} across boxes · {data.items_scanned} items scanned
              </span>
            )}
            <Button size="sm" variant="ghost" className="h-7" onClick={() => load(level)} disabled={loading}
              data-testid="ship-similar-refresh"><RefreshCw size={13} /></Button>
          </div>
        </div>

        {loading && <div className="h-24 animate-pulse bg-muted rounded-xl mt-3" />}

        {!loading && groups.length === 0 && (
          <Card className="rounded-xl mt-3" data-testid="ship-similar-empty">
            <CardContent className="py-10 text-center">
              <Boxes size={34} className="mx-auto mb-3 opacity-20" />
              <p className="text-sm text-muted-foreground">No repeated lines at this sensitivity</p>
              <p className="text-xs text-muted-foreground mt-1">Try Normal or Loose to catch different wording for the same thing.</p>
            </CardContent>
          </Card>
        )}

        <div className="space-y-3 mt-3">
          {groups.map(g => {
            const pick = picks[g.id] || {};
            const keepId = pick.keep || g.suggested_keep;
            const included = g.items.filter(i => i.id === keepId || (pick.include ? pick.include.has(i.id) : true));
            const qty = included.reduce((s, i) => s + i.qty_acquired, 0);
            const value = included.reduce((s, i) => s + i.line_value, 0);
            return (
              <Card key={g.id} className="rounded-xl" data-testid={`ship-similar-group-${g.id}`}>
                <CardContent className="p-3 space-y-2.5">
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="min-w-0 flex-1">
                      <Input className="h-7 text-sm font-medium" value={pick.name ?? g.label}
                        onChange={e => setPicks(p => ({ ...p, [g.id]: { ...p[g.id], name: e.target.value } }))}
                        title="Name for the combined customs line"
                        data-testid={`ship-similar-name-${g.id}`} />
                      <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                        <Badge variant={g.same_box ? 'secondary' : 'outline'} className="text-[10px]">
                          {g.same_box ? 'Same box' : `${g.box_count} different boxes`}
                        </Badge>
                        <Badge variant="outline" className="text-[10px]">{g.box_label}</Badge>
                        {g.exact_repeat && (
                          <Badge variant="outline" className="text-[10px] border-amber-300 text-amber-700 gap-1">
                            <AlertTriangle size={9} /> Looks like the same line typed twice
                          </Badge>
                        )}
                      </div>
                    </div>
                    <div className="text-right text-xs shrink-0">
                      <p className="text-muted-foreground">Combined line</p>
                      <p className="font-semibold" data-testid={`ship-similar-preview-${g.id}`}>
                        {qty} pcs · {money(value)}
                      </p>
                      <p className="text-[10px] text-muted-foreground">{money(qty ? value / qty : 0)} each</p>
                    </div>
                  </div>

                  <div className="rounded-lg border divide-y">
                    {g.items.map(i => (
                      <label key={i.id} className="flex items-center gap-2 p-2 text-[11px] cursor-pointer hover:bg-accent/40"
                        data-testid={`ship-similar-item-${i.id}`}>
                        <input type="checkbox" className="accent-primary" disabled={i.id === keepId}
                          checked={i.id === keepId || (pick.include ? pick.include.has(i.id) : true)}
                          onChange={() => toggleInclude(g.id, i.id)} />
                        <input type="radio" className="accent-primary" name={`keep-${g.id}`}
                          checked={keepId === i.id} onChange={() => setKeep(g.id, i.id)}
                          title="Keep this line" data-testid={`ship-similar-keep-${i.id}`} />
                        <span className="flex-1 min-w-0">
                          <span className="font-medium block truncate">{i.name}</span>
                          <span className="text-muted-foreground">
                            {i.box_name || 'not boxed yet'}{i.category ? ` · ${i.category}` : ''}{i.hs_code ? ` · HS ${i.hs_code}` : ''}
                          </span>
                        </span>
                        <span className="shrink-0 text-right">
                          <span className="block">{i.qty_acquired} × {money(i.value_usd)}</span>
                          <span className="block text-muted-foreground">{money(i.line_value)}</span>
                        </span>
                        {keepId === i.id && <Badge className="text-[9px] shrink-0">keep</Badge>}
                      </label>
                    ))}
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" className="h-7 gap-1.5 text-[11px]" disabled={!!busy}
                      onClick={() => act(g, 'combine')} data-testid={`ship-similar-combine-${g.id}`}>
                      <Layers size={12} /> {busy === g.id ? 'Working…' : 'Combine into one line'}
                    </Button>
                    {!g.same_box && (
                      <Button size="sm" variant="outline" className="h-7 gap-1.5 text-[11px]" disabled={!!busy}
                        onClick={() => act(g, 'combine_same_box')} data-testid={`ship-similar-samebox-${g.id}`}>
                        <Boxes size={12} /> Combine only what shares the kept box
                      </Button>
                    )}
                    <Button size="sm" variant="outline" className="h-7 gap-1.5 text-[11px] text-destructive" disabled={!!busy}
                      onClick={() => act(g, 'delete_repeats')} data-testid={`ship-similar-delete-${g.id}`}>
                      <Trash2 size={12} /> Delete the ticked repeats
                    </Button>
                    <Button size="sm" variant="ghost" className="h-7 text-[11px]" disabled={!!busy}
                      onClick={() => setSkipped(s => [...s, g.label])} data-testid={`ship-similar-skip-${g.id}`}>
                      Keep separate
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        <p className="text-[11px] text-muted-foreground flex items-center gap-1.5 pt-2">
          <Undo2 size={11} /> Combined lines keep their original rows — use “Split back” on the item to undo.
        </p>
      </DialogContent>
    </Dialog>
  );
};

export default SimilarItemsDialog;
