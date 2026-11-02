import React, { useEffect, useState } from 'react';
import api from '../../services/api';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { toast } from 'sonner';

export const EditOrgDialog = ({ org, onClose, onSaved }) => {
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!org) return;
    setName(org.name || '');
    setSlug(org.slug || '');
  }, [org]);

  const cleanSlug = slug.trim().toLowerCase();
  const changedSlug = cleanSlug && cleanSlug !== org?.slug;

  const save = async () => {
    if (changedSlug && !window.confirm(
      `Anyone using ${window.location.origin}/${org.slug} will have to be given the new address `
      + `${window.location.origin}/${cleanSlug}. Change it?`)) return;
    setBusy(true);
    try {
      await api.put(`/organizations/${org.id}`, {
        name: name.trim(),
        slug: cleanSlug || undefined,
      });
      toast.success('Saved');
      onSaved?.();
      onClose();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not save');
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={!!org} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-lg" data-testid="edit-org-dialog">
        <DialogHeader><DialogTitle>{org?.name} settings</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="edit-org-name">Name</Label>
            <Input id="edit-org-name" value={name} onChange={e => setName(e.target.value)}
              data-testid="edit-org-name-input" />
            <p className="text-xs text-muted-foreground">
              What staff see on screen. Changing it breaks nothing.
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-org-slug">Web name</Label>
            <Input id="edit-org-slug" value={slug} onChange={e => setSlug(e.target.value)}
              placeholder="lub" data-testid="edit-org-slug-input" />
            <p className="text-xs text-muted-foreground">
              This organisation opens at{' '}
              <span className="font-mono break-all">
                {window.location.origin}/{cleanSlug || '…'}
              </span>{' '}
              — its own sign-in screen, logo and colours, with its pages underneath
              (<span className="font-mono">/{cleanSlug || '…'}/members</span>). Letters, numbers and
              dashes; keep it short. No DNS or certificate to set up.
            </p>
            {changedSlug ? (
              <p className="text-xs text-amber-600" data-testid="edit-org-slug-warning">
                Links to the old address stop working — everyone will need the new one.
              </p>
            ) : null}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={busy || !name.trim() || !cleanSlug} data-testid="edit-org-submit">
            {busy ? 'Saving…' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
