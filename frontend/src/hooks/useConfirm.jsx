/**
 * useConfirm — drop-in replacement for `window.confirm()` that uses a custom
 * in-app dialog. Critical for kiosk/fullscreen contexts because browsers
 * exit fullscreen mode when `window.confirm()` is shown.
 *
 * Usage:
 *   const { confirm, ConfirmDialog } = useConfirm();
 *   if (await confirm({ title: 'Delete?', message: 'This cannot be undone.' })) {
 *     // user pressed OK
 *   }
 *   return <>... <ConfirmDialog /></>
 */
import React, { useState, useRef, useCallback } from 'react';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '../components/ui/alert-dialog';

export default function useConfirm() {
  const [state, setState] = useState({
    open: false,
    title: 'Are you sure?',
    message: '',
    confirmLabel: 'Confirm',
    cancelLabel: 'Cancel',
    destructive: false,
  });
  const resolverRef = useRef(null);

  const confirm = useCallback((opts = {}) => {
    return new Promise((resolve) => {
      setState({
        open: true,
        title: opts.title || 'Are you sure?',
        message: opts.message || '',
        confirmLabel: opts.confirmLabel || 'Confirm',
        cancelLabel: opts.cancelLabel || 'Cancel',
        destructive: !!opts.destructive,
      });
      resolverRef.current = resolve;
    });
  }, []);

  const handleAction = useCallback((result) => {
    setState((s) => ({ ...s, open: false }));
    if (resolverRef.current) {
      resolverRef.current(result);
      resolverRef.current = null;
    }
  }, []);

  const ConfirmDialog = useCallback(() => (
    <AlertDialog open={state.open} onOpenChange={(o) => { if (!o) handleAction(false); }}>
      <AlertDialogContent data-testid="confirm-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>{state.title}</AlertDialogTitle>
          {state.message && <AlertDialogDescription>{state.message}</AlertDialogDescription>}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={() => handleAction(false)} data-testid="confirm-cancel">{state.cancelLabel}</AlertDialogCancel>
          <AlertDialogAction
            onClick={() => handleAction(true)}
            data-testid="confirm-ok"
            className={state.destructive ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90' : ''}
          >
            {state.confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  ), [state, handleAction]);

  return { confirm, ConfirmDialog };
}
