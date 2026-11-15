import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import PinNumpad from '../PinNumpad';
import { authApi } from '../../services/api';

/**
 * A waiter signs on at the till with their own PIN, so the table, the tab and
 * any tip belong to the person who actually served it (iter420). The PIN only
 * opens the till it was entered at — it is checked against the staff assigned
 * to this store.
 */
export const ServerSignInDialog = ({ open, onOpenChange, storeId, onSignedIn }) => {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (pin) => {
    setError(''); setBusy(true);
    try {
      const res = await authApi.pinLogin(pin, storeId);
      onSignedIn(res.data.user);
      onOpenChange(false);
    } catch (e) {
      setError(e.response?.data?.detail || 'That PIN is not on this till');
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) setError(''); onOpenChange(o); }}>
      <DialogContent className="max-w-sm" data-testid="server-signin-dialog">
        <DialogHeader><DialogTitle className="text-base">Who is serving?</DialogTitle></DialogHeader>
        <PinNumpad
          title="Waiter sign-in"
          subtitle="Enter your own 4-6 digit PIN"
          onSubmit={submit}
          error={error}
          loading={busy}
        />
        <p className="text-[11px] text-muted-foreground text-center">
          Every table and tip from now on is recorded against this name until someone else signs on.
        </p>
      </DialogContent>
    </Dialog>
  );
};
