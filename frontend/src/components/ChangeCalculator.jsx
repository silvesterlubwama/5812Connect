import React, { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Input } from './ui/input';
import { breakChange, DENOMINATIONS, DENOM_LABEL } from '../utils/cashDenominations';

const fmt = (n, c) => `${c} ${(Number(n) || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

/**
 * ChangeCalculator — cashier enters the cash amount received from the customer.
 * Shows change due + a denomination-by-denomination breakdown for the country's currency.
 */
export default function ChangeCalculator({ open, onOpenChange, total, currency = 'UGX', onAccept }) {
  const [amountGiven, setAmountGiven] = useState('');
  const supportedDenoms = DENOMINATIONS[currency] || DENOMINATIONS.UGX;

  useEffect(() => {
    if (open) setAmountGiven('');
  }, [open]);

  const givenNum = Number(amountGiven) || 0;
  const change = givenNum - Number(total || 0);
  const insufficient = change < 0;
  const { breakdown, leftover } = !insufficient ? breakChange(change, currency) : { breakdown: [], leftover: 0 };

  // Quick-add common preset overpayments
  const presets = supportedDenoms.filter(d => d >= total).slice(0, 4);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="change-calculator">
        <DialogHeader>
          <DialogTitle>Cash & Change</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="text-center">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">Total to pay</p>
            <p className="text-3xl font-bold text-primary">{fmt(total, currency)}</p>
          </div>

          <div className="space-y-2">
            <Label className="text-xs">Amount given by customer</Label>
            <Input
              type="number"
              min={0}
              step={currency === 'USD' ? '0.01' : '1'}
              value={amountGiven}
              onChange={(e) => setAmountGiven(e.target.value)}
              autoFocus
              className="text-2xl h-14 text-center"
              data-testid="cash-given-input"
            />
            {/* Preset overpayment helpers */}
            <div className="flex flex-wrap gap-1.5 justify-center">
              {presets.map(p => (
                <Button key={p} type="button" size="sm" variant="outline" className="text-xs" onClick={() => setAmountGiven(String(p))}>
                  {DENOM_LABEL(currency, p)}
                </Button>
              ))}
              <Button type="button" size="sm" variant="outline" className="text-xs" onClick={() => setAmountGiven(String(total))}>
                Exact
              </Button>
            </div>
          </div>

          {/* Change breakdown */}
          <div className={`rounded-lg p-4 ${insufficient ? 'bg-red-50 border border-red-200' : 'bg-green-50 border border-green-200'}`}>
            <div className="flex items-baseline justify-between">
              <span className="text-xs uppercase tracking-wider text-muted-foreground">{insufficient ? 'Insufficient' : 'Change due'}</span>
              <span className={`text-2xl font-bold ${insufficient ? 'text-red-700' : 'text-green-700'}`} data-testid="change-amount">
                {fmt(Math.abs(change), currency)}
              </span>
            </div>
            {!insufficient && breakdown.length > 0 && (
              <div className="mt-3 space-y-0.5">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1.5">Give back:</p>
                {breakdown.map((b, i) => (
                  <div key={i} className="flex items-center justify-between text-xs">
                    <span>{b.count}× <span className="font-mono">{DENOM_LABEL(currency, b.value)}</span></span>
                    <span className="font-medium">{fmt(b.value * b.count, currency)}</span>
                  </div>
                ))}
                {leftover > 0 && (
                  <p className="text-[10px] text-amber-700 mt-1">Note: {fmt(leftover, currency)} cannot be made exactly with available denominations.</p>
                )}
              </div>
            )}
          </div>

          <div className="flex gap-2">
            <Button variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button
              className="flex-1"
              disabled={insufficient || givenNum === 0}
              onClick={() => { onAccept({ amount_given: givenNum, change_due: change, breakdown }); onOpenChange(false); }}
              data-testid="accept-cash-btn"
            >
              Complete &amp; Open Drawer
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
