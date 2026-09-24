import React, { useState, useCallback, useEffect } from 'react';
import { Users2, Merge, ChevronDown, ChevronRight, RefreshCw, ShieldCheck } from 'lucide-react';
import { Card, CardContent } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import api from '../../services/api';
import { toast } from 'sonner';

const SIGNAL_LABEL = { email: 'same email', phone: 'same phone', national_id: 'same ID number' };

export const DuplicatePeoplePanel = ({ onMerged }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState('');
  const [keepers, setKeepers] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get('/people/duplicates');
      setData(r.data);
    } catch (e) { console.warn(e.message || e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const mergeGroup = async (group) => {
    const keepId = keepers[group.name] || group.suggested_keep;
    const dropIds = group.identities.map(i => i.id).filter(id => id !== keepId);
    if (!dropIds.length) return;
    setBusy(group.name);
    try {
      const r = await api.post('/people/duplicates/merge', { keep_id: keepId, drop_ids: dropIds });
      toast.success(`Merged ${r.data.merged} duplicate${r.data.merged > 1 ? 's' : ''} into one profile`);
      await load();
      onMerged?.();
    } catch (e) { toast.error(e.response?.data?.detail || 'Merge failed'); }
    finally { setBusy(''); }
  };

  const autoMerge = async () => {
    setBusy('auto');
    try {
      const r = await api.post('/people/duplicates/auto-merge');
      toast.success(`Auto-merged ${r.data.groups_merged} people (${r.data.records_merged} stray records)`);
      await load();
      onMerged?.();
    } catch (e) { toast.error(e.response?.data?.detail || 'Auto-merge failed'); }
    finally { setBusy(''); }
  };

  const total = data?.total || 0;
  if (!loading && !total) return null;

  return (
    <Card className="rounded-xl border-amber-200 bg-amber-50/40 dark:bg-amber-950/20" data-testid="duplicate-people-panel">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <button className="flex items-center gap-2 text-left" onClick={() => setOpen(o => !o)} data-testid="toggle-duplicates">
            {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
            <Users2 size={16} className="text-amber-600" />
            <span className="text-sm font-medium">
              {loading ? 'Checking for duplicate people…' : `${total} possible duplicate ${total === 1 ? 'person' : 'people'}`}
            </span>
            {data?.exact_total > 0 && (
              <Badge variant="outline" className="text-[10px] border-amber-300 text-amber-700">{data.exact_total} confident</Badge>
            )}
          </button>
          <div className="flex gap-2">
            {data?.exact_total > 0 && (
              <Button size="sm" variant="outline" className="gap-1.5 h-8" onClick={autoMerge} disabled={!!busy} data-testid="auto-merge-duplicates">
                <ShieldCheck size={13} /> {busy === 'auto' ? 'Merging…' : `Auto-merge ${data.exact_total} confident`}
              </Button>
            )}
            <Button size="sm" variant="ghost" className="h-8" onClick={load} disabled={loading}><RefreshCw size={13} /></Button>
          </div>
        </div>
        {!open && (
          <p className="text-xs text-muted-foreground">
            The same person saved more than once makes edits look like they didn&apos;t save. Open to review and merge.
          </p>
        )}
        {open && (
          <div className="space-y-3">
            {(data?.groups || []).map(group => {
              const keepId = keepers[group.name] || group.suggested_keep;
              return (
                <div key={group.name} className="rounded-lg border bg-background p-3 space-y-2" data-testid={`dup-group-${group.name.replace(/\s+/g, '-').toLowerCase()}`}>
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium">{group.name}</p>
                      {group.signals.map(s => (
                        <Badge key={s} variant="outline" className="text-[10px]">{SIGNAL_LABEL[s] || s}</Badge>
                      ))}
                      {!group.signals.length && <Badge variant="outline" className="text-[10px]">name only — check carefully</Badge>}
                    </div>
                    <Button size="sm" className="h-7 gap-1.5 text-[11px]" onClick={() => mergeGroup(group)} disabled={!!busy}
                      data-testid={`merge-group-${group.name.replace(/\s+/g, '-').toLowerCase()}`}>
                      <Merge size={12} /> {busy === group.name ? 'Merging…' : 'Merge into selected'}
                    </Button>
                  </div>
                  <div className="space-y-1.5">
                    {group.identities.map(ident => (
                      <label key={ident.id} className="flex items-start gap-2 text-xs p-2 rounded-md hover:bg-accent/40 cursor-pointer"
                        data-testid={`dup-identity-${ident.id}`}>
                        <input type="radio" className="mt-0.5 accent-primary" name={`keep-${group.name}`}
                          checked={keepId === ident.id}
                          onChange={() => setKeepers(k => ({ ...k, [group.name]: ident.id }))} />
                        <span className="flex-1">
                          <span className="font-medium">{ident.name}</span>
                          {ident.has_login && <Badge variant="secondary" className="ml-2 text-[10px]">has login</Badge>}
                          {keepId === ident.id && <Badge className="ml-2 text-[10px]">keep this one</Badge>}
                          <span className="block text-muted-foreground mt-0.5">
                            {[ident.role, ident.email, ident.phone].filter(Boolean).join(' · ') || 'no contact details'}
                          </span>
                          <span className="block text-muted-foreground">
                            {ident.records.map(r => `${r.collection}${r.department ? ` (${r.department})` : ''}`).join(', ')}
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
};
