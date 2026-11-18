/**
 * AccountAccessDialog — pin a staff member to the accounts they may use.
 *
 * Nobody is restricted until a director ticks accounts for them. From that
 * moment the person only sees those accounts (and their balances) and can only
 * post income or expenses against them. Unticking everything frees them again.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Badge } from '../ui/badge';
import { ScrollArea } from '../ui/scroll-area';
import { Checkbox } from '../ui/checkbox';
import { ShieldCheck, Search } from 'lucide-react';
import api from '../../services/api';
import { toast } from 'sonner';

export default function AccountAccessDialog({ open, onOpenChange, accounts = [] }) {
  const [staff, setStaff] = useState([]);
  const [picked, setPicked] = useState(null);      // the staff member being edited
  const [chosen, setChosen] = useState([]);        // their account ids
  const [q, setQ] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get('/finance/account-access/staff')
      .then(r => setStaff(r.data || []))
      .catch(e => toast.error(e?.response?.data?.detail || 'Could not load staff'));
    setPicked(null);
  }, [open]);

  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return staff;
    return staff.filter(u => `${u.name} ${u.email} ${u.role}`.toLowerCase().includes(t));
  }, [staff, q]);

  const choose = (u) => { setPicked(u); setChosen(u.account_ids || []); };

  const toggle = (id) => setChosen(c => (c.includes(id) ? c.filter(x => x !== id) : [...c, id]));

  const save = async () => {
    if (!picked) return;
    setSaving(true);
    try {
      const r = await api.put(`/finance/account-access/${picked.id}`, { account_ids: chosen });
      toast.success(r.data?.message || 'Saved');
      setStaff(s => s.map(u => (u.id === picked.id ? { ...u, account_ids: chosen } : u)));
      setPicked(null);
    } catch (e) { toast.error(e?.response?.data?.detail || 'Save failed'); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl" data-testid="account-access-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><ShieldCheck size={16} /> Who may use which account</DialogTitle>
          <DialogDescription className="text-xs">
            Tick the accounts a person is allowed to see and post against. Leave everything unticked to let them use the whole chart. Directors are never restricted.
          </DialogDescription>
        </DialogHeader>
        <div className="grid md:grid-cols-2 gap-4 mt-1">
          <div className="space-y-2">
            <div className="relative">
              <Search size={13} className="absolute left-2 top-2.5 text-muted-foreground" />
              <Input value={q} onChange={e => setQ(e.target.value)} placeholder="Find a staff member" className="h-8 pl-7 text-xs" data-testid="account-access-search" />
            </div>
            <ScrollArea className="h-[320px] rounded border">
              <div className="divide-y">
                {filtered.map(u => (
                  <button key={u.id} onClick={() => choose(u)}
                    className={`w-full text-left px-2.5 py-2 hover:bg-muted/60 transition-colors ${picked?.id === u.id ? 'bg-muted' : ''}`}
                    data-testid={`account-access-user-${u.id}`}>
                    <p className="text-xs font-medium">{u.name || u.email}</p>
                    <p className="text-[10px] text-muted-foreground flex items-center gap-1">
                      {u.role || 'staff'}
                      {(u.account_ids || []).length > 0
                        ? <Badge className="text-[9px] bg-amber-100 text-amber-700">{u.account_ids.length} account(s)</Badge>
                        : <span className="text-[9px]">unrestricted</span>}
                    </p>
                  </button>
                ))}
                {filtered.length === 0 && <p className="text-xs text-muted-foreground p-3">Nobody matches that.</p>}
              </div>
            </ScrollArea>
          </div>
          <div className="space-y-2">
            {!picked ? (
              <p className="text-xs text-muted-foreground p-3">Pick a staff member on the left to set their accounts.</p>
            ) : (
              <>
                <p className="text-xs font-semibold">{picked.name || picked.email} — {chosen.length || 'all'} account(s)</p>
                <ScrollArea className="h-[280px] rounded border">
                  <div className="divide-y">
                    {accounts.map(a => (
                      <label key={a.id} className="flex items-center gap-2 px-2.5 py-1.5 text-xs cursor-pointer hover:bg-muted/50">
                        <Checkbox checked={chosen.includes(a.id)} onCheckedChange={() => toggle(a.id)} data-testid={`account-access-acct-${a.code}`} />
                        <span className="font-mono text-[10px] text-muted-foreground w-12">{a.code}</span>
                        <span className="flex-1 truncate">{a.name}</span>
                        <Badge variant="outline" className="text-[9px]">{a.type}</Badge>
                      </label>
                    ))}
                  </div>
                </ScrollArea>
                <div className="flex gap-2">
                  <Button variant="ghost" size="sm" className="flex-1" onClick={() => setChosen([])} data-testid="account-access-clear">Unrestrict</Button>
                  <Button size="sm" className="flex-1" onClick={save} disabled={saving} data-testid="account-access-save">
                    {saving ? 'Saving…' : 'Save access'}
                  </Button>
                </div>
              </>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
