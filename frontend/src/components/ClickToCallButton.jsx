/**
 * Click-to-call button — drop next to any phone number in the UI. Uses the
 * browser JsSIP softphone (VoipContext) to place the call via the customer's
 * Grandstream UCM. The UCM applies its own outbound routes / trunk rules.
 */
import React from 'react';
import { Phone } from 'lucide-react';
import { Button } from './ui/button';
import { toast } from 'sonner';
import { useVoip } from '../context/VoipContext';

export default function ClickToCallButton({ number, label, size = 'sm', variant = 'outline', className = '' }) {
  const v = useVoip();
  if (!number) return null;

  const onClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (v.status !== 'registered') {
      toast.error(v.statusReason || 'Softphone is not registered. Ask admin to set your SIP extension in VoIP settings.');
      return;
    }
    v.dial(number);
    toast.success(`Dialling ${number}…`);
  };

  return (
    <Button
      size={size}
      variant={variant}
      onClick={onClick}
      className={`h-7 px-2 ${className}`}
      title={`Call ${number}${v.extension ? ` from ext ${v.extension}` : ''}`}
      data-testid={`click-to-call-${String(number).replace(/[^a-z0-9]/gi, '')}`}
    >
      <Phone size={11} className={label ? 'mr-1' : ''} />
      {label && <span className="text-[11px]">{label}</span>}
    </Button>
  );
}
