import React from 'react';
import { Input } from '../ui/input';
import { Switch } from '../ui/switch';

const key = (name) => (name || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');

const LABEL = {
  deduction: 'deducted from pay',
  allowance: 'added to pay',
  employer_contribution: 'employer contribution',
};

// Per-employee view of the campus statutory lines: switch one off for this
// person, or give them their own rate (e.g. a different PAYE rate).
export const StatutoryOverrides = ({ lines = [], value = {}, onChange, currency = 'UGX' }) => {
  if (!lines.length) {
    return (
      <p className="text-[11px] text-muted-foreground" data-testid="statutory-overrides-empty">
        No statutory lines set for this campus yet — add them in HR → Settings → Compliance and they will apply to everyone here.
      </p>
    );
  }
  const set = (k, patch) => onChange({ ...value, [k]: { ...(value[k] || {}), ...patch } });

  return (
    <div className="space-y-2" data-testid="statutory-overrides">
      {lines.map((l, i) => {
        const k = l.key || key(l.name);
        const ov = value[k] || {};
        const enabled = ov.enabled !== false;
        const pct = ov.is_percentage !== undefined ? ov.is_percentage : !!l.is_percentage;
        const amount = ov.amount !== undefined && ov.amount !== null ? ov.amount : (l.amount ?? 0);
        const usesBands = !!(l.bands || []).length && ov.amount === undefined;
        return (
          <div key={k || i} className={`rounded-lg border p-2.5 text-xs space-y-1.5 ${enabled ? '' : 'opacity-60'}`}
            data-testid={`statutory-override-${k}`}>
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="font-medium">{l.name}</p>
                <p className="text-[10px] text-muted-foreground">{LABEL[l.type] || l.type}{l.mode === 'add_to_pay' ? ' · paid with salary' : ''}</p>
              </div>
              <Switch checked={enabled} onCheckedChange={v => set(k, { enabled: v })}
                data-testid={`statutory-toggle-${k}`} />
            </div>
            {enabled && (
              <div className="flex items-center gap-2">
                {usesBands ? (
                  <span className="text-[11px] text-muted-foreground flex-1">
                    Progressive bands from HR Settings. Type a rate to use a flat one for this person.
                  </span>
                ) : (
                  <span className="text-[11px] text-muted-foreground flex-1">
                    {pct ? 'Rate applied to gross' : `Fixed amount in ${currency}`}
                  </span>
                )}
                <Input className="h-7 w-24 text-xs" type="number" step="0.01"
                  placeholder={usesBands ? 'bands' : String(l.amount ?? 0)}
                  value={ov.amount ?? ''}
                  onChange={e => set(k, { amount: e.target.value === '' ? undefined : parseFloat(e.target.value), is_percentage: pct })}
                  data-testid={`statutory-amount-${k}`} />
                <label className="flex items-center gap-1 text-[10px] cursor-pointer">
                  <input type="checkbox" checked={pct} onChange={e => set(k, { is_percentage: e.target.checked })}
                    data-testid={`statutory-pct-${k}`} /> %
                </label>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default StatutoryOverrides;
