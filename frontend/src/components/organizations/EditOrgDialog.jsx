import React, { useEffect, useState } from 'react';
import api from '../../services/api';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { toast } from 'sonner';

export const EditOrgDialog = ({ org, onClose, onSaved }) => {
  const [name, setName] = useState('');
  const [hostnames, setHostnames] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!org) return;
    setName(org.name || '');
    setHostnames((org.hostnames || []).join(', '));
  }, [org]);

  const save = async () => {
    setBusy(true);
    try {
      await api.put(`/organizations/${org.id}`, {
        name: name.trim(),
        hostnames: hostnames.split(',').map(h => h.trim()).filter(Boolean),
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
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-org-hosts">Web addresses</Label>
            <Input id="edit-org-hosts" value={hostnames} onChange={e => setHostnames(e.target.value)}
              placeholder="new.lubwamas.org, personal.5812uganda.org"
              data-testid="edit-org-hostnames-input" />
            <p className="text-xs text-muted-foreground">
              Comma separated. Point the address at this server (an A record or CNAME to the same
              host as the main site) and it opens straight into {org?.name} with its own logo,
              colours and sign-in screen. Each address can only belong to one organisation.
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={busy || !name.trim()} data-testid="edit-org-submit">
            {busy ? 'Saving…' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
