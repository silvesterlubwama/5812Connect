import React, { useState } from 'react';
import api from '../../services/api';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../ui/dialog';
import { Key, Copy, Check } from 'lucide-react';
import { toast } from 'sonner';

/** Issue the one-time key the other deployment uses to pull this organisation. */
export function TransferKeyDialog({ org, onClose }) {
  const [issued, setIssued] = useState(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const issue = async () => {
    setBusy(true);
    try {
      const res = await api.post(`/organizations/${org.id}/transfer-key`);
      setIssued(res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not create a transfer key');
    } finally { setBusy(false); }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(issued.transfer_key);
      setCopied(true);
      toast.success('Transfer key copied');
    } catch {
      toast.error('Could not copy — select the key and copy it manually');
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-lg" data-testid="transfer-key-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Key className="w-5 h-5" /> Move {org?.name} to another deployment
          </DialogTitle>
        </DialogHeader>
        {!issued ? (
          <div className="space-y-3 text-sm">
            <p className="text-muted-foreground">
              This creates a one-time key. On the <strong>other</strong> server, open Organisations →
              Bring one in, paste this server's address and the key, and it pulls the whole
              organisation across — records and files, however large.
            </p>
            <p className="text-xs text-muted-foreground">
              The key works for 48 hours, covers this organisation only, and stops working the
              moment the transfer finishes. Nothing is copied until the other server asks for it.
            </p>
            <Button onClick={issue} disabled={busy} className="gap-2" data-testid="transfer-key-create">
              <Key className="w-4 h-4" /> {busy ? 'Creating…' : 'Create transfer key'}
            </Button>
          </div>
        ) : (
          <div className="space-y-3 text-sm">
            <div>
              <Label className="text-xs">This server's address</Label>
              <Input readOnly value={window.location.origin} data-testid="transfer-source-url" />
            </div>
            <div>
              <Label className="text-xs">Transfer key — shown once</Label>
              <div className="flex gap-2">
                <Input readOnly value={issued.transfer_key} className="font-mono text-xs" data-testid="transfer-key-value" />
                <Button variant="outline" onClick={copy} className="shrink-0" data-testid="transfer-key-copy">
                  {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                </Button>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Expires {new Date(issued.expires_at).toLocaleString()}. Keep it out of email and chat —
              anyone holding it can read this organisation's data until it is used or expires.
            </p>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="transfer-key-close">Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
