import React, { useEffect, useState } from 'react';
import api from '../../services/api';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { toast } from 'sonner';

export const MovePersonDialog = ({ org, organizations, onClose, onMoved }) => {
  const [people, setPeople] = useState([]);
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState(null);
  const [target, setTarget] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!org) return;
    api.get(`/organizations/${org.id}/people`, { params: query ? { q: query } : {} })
      .then(res => setPeople(res.data.people || []))
      .catch(err => toast.error(err.response?.data?.detail || 'Could not load people'));
  }, [org, query]);

  const move = async () => {
    setBusy(true);
    try {
      const res = await api.post('/organizations/transfer-person', {
        user_id: picked.id, from_org_id: org.id, to_org_id: target,
      });
      toast.success(res.data.message, { duration: 8000 });
      onMoved?.();
      onClose();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not move that person');
    } finally { setBusy(false); }
  };

  const destinations = organizations.filter(o => o.id !== org?.id && o.status !== 'suspended');

  return (
    <Dialog open={!!org} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-lg" data-testid="move-person-dialog">
        <DialogHeader><DialogTitle>Move someone out of {org?.name}</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Only their sign-in moves. Everything they created stays with {org?.name} — records belong
            to the organisation that owns them.
          </p>
          <div className="space-y-2">
            <Label htmlFor="move-search">Who</Label>
            <Input id="move-search" value={query} placeholder="Search by name or email"
              onChange={e => setQuery(e.target.value)} data-testid="move-person-search" />
            <div className="max-h-48 overflow-y-auto rounded-md border divide-y">
              {people.map(p => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setPicked(p)}
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-muted ${picked?.id === p.id ? 'bg-muted' : ''}`}
                  data-testid={`move-person-option-${p.id}`}
                >
                  <span className="font-medium">{p.name || p.email}</span>
                  <span className="text-xs text-muted-foreground block">{p.email} · {p.role}</span>
                </button>
              ))}
              {people.length === 0 && (
                <p className="px-3 py-2 text-sm text-muted-foreground">Nobody matches that.</p>
              )}
            </div>
          </div>
          <div className="space-y-2">
            <Label>Move them to</Label>
            <div className="flex flex-wrap gap-1.5">
              {destinations.map(o => (
                <Button key={o.id} size="sm" variant={target === o.id ? 'secondary' : 'outline'}
                  onClick={() => setTarget(o.id)} data-testid={`move-target-${o.slug}`}>
                  {o.name}
                </Button>
              ))}
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={move} disabled={!picked || !target || busy} data-testid="move-person-submit">
            {busy ? 'Moving…' : 'Move person'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
