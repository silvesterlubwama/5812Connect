import React, { useState } from 'react';
import { Button } from './ui/button';
import { Delete, LogIn } from 'lucide-react';

/**
 * PinNumpad — large-touch-target numeric keypad for cashier / kiosk PIN entry.
 * Calls onSubmit(pin) when user presses the green check.
 */
export default function PinNumpad({ onSubmit, title = 'Enter PIN', subtitle = '', maxLen = 6, minLen = 4, error = '', loading = false }) {
  const [pin, setPin] = useState('');

  const handleKey = (k) => {
    if (k === 'del') return setPin(p => p.slice(0, -1));
    if (k === 'submit') {
      if (pin.length >= minLen) onSubmit(pin);
      return;
    }
    setPin(p => (p.length < maxLen ? p + k : p));
  };

  const dots = Array.from({ length: maxLen }, (_, i) => i < pin.length);

  return (
    <div className="flex flex-col items-center gap-4 select-none" data-testid="pin-numpad">
      <div className="text-center">
        <h2 className="text-xl font-bold">{title}</h2>
        {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
      </div>
      <div className="flex gap-2">
        {dots.map((filled, i) => (
          <span key={i} className={`w-3.5 h-3.5 rounded-full transition-all ${filled ? 'bg-primary scale-110' : 'bg-muted'}`} />
        ))}
      </div>
      {error && <p className="text-sm text-destructive font-medium" data-testid="pin-error">{error}</p>}
      <div className="grid grid-cols-3 gap-3 w-full max-w-[280px]">
        {[1, 2, 3, 4, 5, 6, 7, 8, 9].map(n => (
          <Button key={n} variant="outline" className="h-16 text-2xl font-light" onClick={() => handleKey(String(n))} data-testid={`pin-key-${n}`}>{n}</Button>
        ))}
        <Button variant="ghost" className="h-16 text-base" onClick={() => handleKey('del')} data-testid="pin-key-del"><Delete size={20} /></Button>
        <Button variant="outline" className="h-16 text-2xl font-light" onClick={() => handleKey('0')} data-testid="pin-key-0">0</Button>
        <Button className="h-16 gap-1.5 bg-green-600 hover:bg-green-700" disabled={pin.length < minLen || loading} onClick={() => handleKey('submit')} data-testid="pin-submit">
          <LogIn size={18} />
        </Button>
      </div>
    </div>
  );
}
