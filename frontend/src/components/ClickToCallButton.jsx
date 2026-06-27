/**
 * Click-to-call button — drop next to any phone number in the UI.
 *
 * Behaviour:
 *   • If the current user has a WebRTC softphone → fires a `softphone-dial`
 *     custom event so BrowserSoftphone picks it up locally (no AMI roundtrip).
 *   • Else if the user has a hardphone extension → POSTs to /api/pbx/originate
 *     which uses Asterisk AMI Originate to ring their desk phone first, then
 *     bridge to the target on answer.
 *   • Else → toast "no extension assigned to your account".
 *
 * Props: `number` (string, required), `label` (string, optional badge text),
 *        `size` ('sm'|'md', default 'sm'), `variant` (passes to Button).
 */
import React, { useEffect, useState } from 'react';
import { Phone } from 'lucide-react';
import { Button } from './ui/button';
import api from '../services/api';
import { toast } from 'sonner';

let _cachedConfig = undefined;   // module-level cache so 100 buttons share one fetch
let _cachePromise = null;

async function getConfig() {
  if (_cachedConfig !== undefined) return _cachedConfig;
  if (_cachePromise) return _cachePromise;
  _cachePromise = api.get('/pbx/me/click-to-call-config').then(r => {
    _cachedConfig = (r.status === 204 || !r.data) ? null : r.data;
    return _cachedConfig;
  }).catch(() => { _cachedConfig = null; return null; });
  return _cachePromise;
}

export default function ClickToCallButton({ number, label, size = 'sm', variant = 'outline', className = '' }) {
  const [config, setConfig] = useState(_cachedConfig);
  useEffect(() => { if (_cachedConfig === undefined) getConfig().then(setConfig); }, []);
  if (!number) return null;

  const onClick = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    const cfg = config || await getConfig();
    if (!cfg) { toast.error('No phone extension is assigned to your account. Ask an admin to set one up in PBX Admin.'); return; }
    if (cfg.is_softphone) {
      // Use the browser softphone for instant calling
      window.dispatchEvent(new CustomEvent('softphone-dial', { detail: { number } }));
      toast.success(`Dialling ${number}…`);
    } else {
      // Use AMI Originate to ring the user's desk phone
      try {
        await api.post('/pbx/originate', { from_extension: cfg.extension, to_number: number });
        toast.success(`Ringing extension ${cfg.extension}. Pick up — then we'll dial ${number}.`);
      } catch (err) {
        toast.error(err.response?.data?.detail || 'Could not place call — is the PBX appliance online?');
      }
    }
  };

  return (
    <Button
      size={size}
      variant={variant}
      onClick={onClick}
      className={`h-7 px-2 ${className}`}
      title={`Call ${number}${config?.extension ? ` from ext ${config.extension}` : ''}`}
      data-testid={`click-to-call-${number.replace(/[^a-z0-9]/gi, '')}`}
    >
      <Phone size={11} className={label ? 'mr-1' : ''} />
      {label && <span className="text-[11px]">{label}</span>}
    </Button>
  );
}
