import React, { useState } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';

/**
 * Confirmation dialog for dangerous bulk operations.
 * Requires user to type a confirmation word before proceeding.
 */
export function BulkDeleteConfirm({ open, onOpenChange, count, itemType = 'items', onConfirm }) {
  const [typed, setTyped] = useState('');
  const confirmWord = 'DELETE';
  const isConfirmed = typed.toUpperCase() === confirmWord;

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) setTyped(''); onOpenChange(o); }}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="text-destructive">Confirm Bulk Delete</DialogTitle>
          <DialogDescription>
            This will permanently delete <strong>{count} {itemType}</strong>. This action cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 mt-2">
          <p className="text-sm">Type <strong className="font-mono bg-destructive/10 px-1.5 py-0.5 rounded text-destructive">{confirmWord}</strong> to confirm:</p>
          <Input
            value={typed}
            onChange={e => setTyped(e.target.value)}
            placeholder={`Type ${confirmWord}`}
            className="font-mono"
            data-testid="bulk-delete-confirm-input"
            autoFocus
          />
          <div className="flex gap-3">
            <Button variant="outline" className="flex-1" onClick={() => { setTyped(''); onOpenChange(false); }}>Cancel</Button>
            <Button
              variant="destructive"
              className="flex-1"
              disabled={!isConfirmed}
              onClick={() => { setTyped(''); onOpenChange(false); onConfirm(); }}
              data-testid="bulk-delete-confirm-btn"
            >
              Delete {count} {itemType}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
