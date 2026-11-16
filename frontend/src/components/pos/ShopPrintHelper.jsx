import { useCallback, useEffect, useState } from 'react';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Copy, Download, HardDriveDownload, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { screensApi } from '../../services/api';

/**
 * The shop's print helper (iter422).
 *
 * A receipt printer with its own IP lives on the shop's network. 58:12 runs in
 * the cloud and cannot see that network, so the receipt is handed to a small
 * helper running on any computer or Pi at the shop, which walks it over to the
 * printer. Pair it once here; the link it gets back is its only credential.
 */
const minutesSince = (iso) => {
  const t = Date.parse(iso || '');
  if (!t) return null;
  return Math.max(0, Math.round((Date.now() - t) / 60000));
};

export const ShopPrintHelper = ({ locationId }) => {
  const [helper, setHelper] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    if (!locationId) return;
    screensApi.list({ location_id: locationId })
      .then(r => setHelper((r.data || []).find(s => s.kind === 'bridge') || null))
      .catch(() => setHelper(null));
  }, [locationId]);

  useEffect(() => {
    load();
    const t = setInterval(load, 20000);      // so "running now" stays true
    return () => clearInterval(t);
  }, [load]);

  if (!locationId) return null;

  const base = `${window.location.origin}/api/screens/${helper?.token}`;
  const where = encodeURIComponent(window.location.origin);
  const mins = minutesSince(helper?.last_seen_at);
  const alive = mins !== null && mins < 3;

  const pair = async () => {
    setBusy(true);
    try {
      const r = await screensApi.pair({ kind: 'bridge', location_id: locationId, name: 'Shop print helper' });
      toast.success('Print helper set up — download it onto a computer at the shop');
      setHelper(r.data?.screen || null);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not set up the helper');
    } finally { setBusy(false); }
  };

  const unpair = async () => {
    if (!window.confirm('Stop this helper? Receipts will go back to the print window.')) return;
    try {
      await screensApi.revoke(helper.id);
      toast.success('Print helper stopped');
      setHelper(null);
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not stop it'); }
  };

  const copyCommand = async () => {
    const cmd = `powershell -ExecutionPolicy Bypass -File print-helper.ps1`;
    try { await navigator.clipboard.writeText(cmd); toast.success('Command copied'); }
    catch { window.prompt('Run this at the shop:', cmd); }
  };

  return (
    <div className="rounded-lg border border-border p-2.5 space-y-2" data-testid="shop-print-helper">
      <div className="flex items-center gap-2">
        <HardDriveDownload size={13} />
        <p className="text-xs font-semibold flex-1">Shop print helper</p>
        {helper && (alive
          ? <Badge className="bg-green-100 text-green-700 text-[10px]" data-testid="helper-online">Running now</Badge>
          : <Badge variant="outline" className="text-[10px]" data-testid="helper-offline">
              {mins === null ? 'Never started' : `Last seen ${mins} min ago`}
            </Badge>)}
      </div>

      {!helper ? (
        <>
          <p className="text-[11px] text-muted-foreground">
            A small program you leave running on any computer or Raspberry Pi at the shop. It
            collects receipts from 58:12 and sends them to the printer on the shop's own network —
            the till computer can be off, or be a phone.
          </p>
          <Button size="sm" className="h-8 text-xs" onClick={pair} disabled={busy} data-testid="pair-helper-btn">
            {busy ? 'Setting up…' : 'Set up the print helper'}
          </Button>
        </>
      ) : (
        <>
          <ol className="text-[11px] text-muted-foreground list-decimal pl-4 space-y-1">
            <li>
              On a computer at the shop, download the helper:{' '}
              <a href={`${base}/helper?format=ps1&base=${where}`} className="text-primary hover:underline" data-testid="helper-download-ps1">
                Windows
              </a>{' · '}
              <a href={`${base}/helper?format=py&base=${where}`} className="text-primary hover:underline" data-testid="helper-download-py">
                Mac, Linux or Pi
              </a>
            </li>
            <li>Right-click it → <strong>Run with PowerShell</strong>, and leave the window open.</li>
            <li>That's it — the badge above turns green within a few seconds.</li>
          </ol>
          <p className="text-[11px] text-muted-foreground">
            It already knows this shop's address, so there is nothing to type in. Anyone with the
            file can print to this shop's printers, so keep it on the shop's own machine.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" className="h-7 text-[11px] gap-1" asChild data-testid="helper-download-btn">
              <a href={`${base}/helper?format=ps1&base=${where}`} download><Download size={11} /> Download for Windows</a>
            </Button>
            <Button size="sm" variant="ghost" className="h-7 text-[11px] gap-1" onClick={copyCommand} data-testid="helper-copy-cmd">
              <Copy size={11} /> Copy the run command
            </Button>
            <Button size="sm" variant="ghost" className="h-7 text-[11px] gap-1 text-destructive" onClick={unpair} data-testid="helper-unpair-btn">
              <Trash2 size={11} /> Stop it
            </Button>
          </div>
          {!alive && mins !== null && (
            <p className="text-[11px] text-amber-700" data-testid="helper-stale-note">
              Nothing has collected a receipt for {mins} minutes. While it is not running, receipts
              fall back to this computer's print window so no sale is held up.
            </p>
          )}
        </>
      )}
    </div>
  );
};
