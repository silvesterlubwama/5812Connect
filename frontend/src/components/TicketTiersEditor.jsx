import React from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';

/** Ticket tier rows (Early Bird / Regular / VIP …). Each tier carries its own
 *  price + capacity and overrides the event's base price. */
export const TicketTiersEditor = ({ tiers = [], onChange, idPrefix = 'tier' }) => {
  const set = (idx, patch) => onChange(tiers.map((t, i) => (i === idx ? { ...t, ...patch } : t)));
  return (
    <div className="rounded-lg border border-border p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium">Ticket Tiers <span className="text-xs text-muted-foreground font-normal">(optional — overrides base price)</span></p>
          <p className="text-xs text-muted-foreground">e.g. Early Bird, Regular, VIP</p>
        </div>
        <Button
          type="button" size="sm" variant="outline" data-testid={`${idPrefix}-add-btn`}
          onClick={() => onChange([...tiers, { id: `tier_${Date.now().toString(36)}`, name: '', price: 0, capacity: 0, sold: 0, description: '' }])}
        >+ Add Tier</Button>
      </div>
      {tiers.map((t, idx) => (
        <div key={t.id || idx} className="grid grid-cols-12 gap-1.5 items-end" data-testid={`${idPrefix}-row-${idx}`}>
          <div className="col-span-4">
            {idx === 0 && <p className="text-[10px] text-muted-foreground mb-0.5">Name</p>}
            <Input className="h-8 text-xs" placeholder="Early Bird" value={t.name || ''} onChange={e => set(idx, { name: e.target.value })} data-testid={`${idPrefix}-name-${idx}`} />
          </div>
          <div className="col-span-3">
            {idx === 0 && <p className="text-[10px] text-muted-foreground mb-0.5">Price</p>}
            <Input className="h-8 text-xs" type="number" min="0" value={t.price ?? 0} onChange={e => set(idx, { price: parseFloat(e.target.value) || 0 })} data-testid={`${idPrefix}-price-${idx}`} />
          </div>
          <div className="col-span-3">
            {idx === 0 && <p className="text-[10px] text-muted-foreground mb-0.5">Capacity</p>}
            <Input className="h-8 text-xs" type="number" min="0" value={t.capacity ?? 0} onChange={e => set(idx, { capacity: parseInt(e.target.value) || 0 })} data-testid={`${idPrefix}-capacity-${idx}`} />
          </div>
          <div className="col-span-2">
            <Button type="button" size="sm" variant="ghost" className="h-8 w-full text-destructive" data-testid={`${idPrefix}-delete-${idx}`}
              onClick={() => onChange(tiers.filter((_, j) => j !== idx))}>Remove</Button>
          </div>
        </div>
      ))}
      {tiers.length === 0 && <p className="text-xs text-muted-foreground">No tiers — the base price applies to everyone.</p>}
    </div>
  );
};

export default TicketTiersEditor;
