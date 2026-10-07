import React from 'react';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Button } from '../ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Plus, Trash2, Layers } from 'lucide-react';

// Campus-wide statutory lines. These apply to EVERY payslip in the campus;
// an employee can override the rate or opt out on their own pay settings.
export const ComplianceLinesEditor = ({ lines = [], onChange }) => {
  const patch = (i, next) => onChange(lines.map((l, j) => (j === i ? { ...l, ...next } : l)));
  const remove = (i) => onChange(lines.filter((_, j) => j !== i));

  const addBand = (i) => patch(i, { bands: [...(lines[i].bands || []), { up_to: null, rate: 0 }] });
  const patchBand = (i, bi, next) => patch(i, {
    bands: (lines[i].bands || []).map((b, j) => (j === bi ? { ...b, ...next } : b)),
  });
  const removeBand = (i, bi) => {
    const bands = (lines[i].bands || []).filter((_, j) => j !== bi);
    patch(i, { bands: bands.length ? bands : null });
  };

  if (!lines.length) {
    return <p className="text-[11px] text-muted-foreground">No statutory lines yet — pick your country's common ones below. They then apply to every payslip in this campus automatically.</p>;
  }

  return (
    <div className="space-y-2" data-testid="compliance-lines-editor">
      {lines.map((cl, i) => {
        const isEmployer = cl.type === 'employer_contribution';
        return (
          <div key={i} className="rounded-lg border p-2.5 space-y-2 bg-muted/20" data-testid={`compliance-line-${i}`}>
            <div className="flex items-start gap-2">
              <Input className="h-8 text-xs flex-1" value={cl.name || ''} placeholder="e.g. NSSF Employee"
                onChange={e => patch(i, { name: e.target.value })} data-testid={`compliance-name-${i}`} />
              <Select value={cl.type || 'deduction'} onValueChange={v => patch(i, { type: v, mode: v === 'employer_contribution' ? (cl.mode || 'employer_cost') : undefined })}>
                <SelectTrigger className="h-8 text-xs w-[150px]" data-testid={`compliance-type-${i}`}><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="deduction">Deduct from staff</SelectItem>
                  <SelectItem value="allowance">Add to pay</SelectItem>
                  <SelectItem value="employer_contribution">Employer contribution</SelectItem>
                </SelectContent>
              </Select>
              <button type="button" className="text-destructive mt-1.5" onClick={() => remove(i)} data-testid={`compliance-remove-${i}`}>
                <Trash2 size={13} />
              </button>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 items-end">
              <div>
                <Label className="text-[10px]">{cl.is_percentage ? 'Rate %' : 'Fixed amount'}</Label>
                <Input className="h-8 text-xs" type="number" step="0.01" value={cl.amount ?? 0}
                  disabled={!!(cl.bands || []).length}
                  onChange={e => patch(i, { amount: parseFloat(e.target.value) || 0 })}
                  data-testid={`compliance-amount-${i}`} />
              </div>
              <label className="flex items-center gap-1 text-[11px] cursor-pointer pb-2">
                <input type="checkbox" checked={!!cl.is_percentage}
                  onChange={e => patch(i, { is_percentage: e.target.checked })}
                  data-testid={`compliance-pct-${i}`} /> percentage of gross
              </label>
              {isEmployer && (
                <div>
                  <Label className="text-[10px]">How it is paid</Label>
                  <Select value={cl.mode || 'employer_cost'} onValueChange={v => patch(i, { mode: v })}>
                    <SelectTrigger className="h-8 text-xs" data-testid={`compliance-mode-${i}`}><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="employer_cost">Employer cost (not paid to staff)</SelectItem>
                      <SelectItem value="add_to_pay">Added to the paycheck</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}
              {isEmployer && (
                <div>
                  <Label className="text-[10px]">Expense a/c</Label>
                  <Input className="h-8 text-xs" value={cl.account_code || ''} placeholder="5002"
                    onChange={e => patch(i, { account_code: e.target.value })}
                    data-testid={`compliance-expense-acct-${i}`} />
                </div>
              )}
              <div>
                <Label className="text-[10px]">Payable to a/c</Label>
                <Input className="h-8 text-xs" value={cl.liability_account_code || ''} placeholder="2200"
                  onChange={e => patch(i, { liability_account_code: e.target.value })}
                  data-testid={`compliance-liability-acct-${i}`} />
              </div>
            </div>

            <div className="space-y-1.5">
              {(cl.bands || []).length === 0 ? (
                <Button type="button" size="sm" variant="ghost" className="h-7 text-[11px] gap-1"
                  onClick={() => addBand(i)} data-testid={`compliance-add-bands-${i}`}>
                  <Layers size={12} /> Use progressive bands (PAYE)
                </Button>
              ) : (
                <div className="rounded-md border border-dashed p-2 space-y-1.5">
                  <p className="text-[10px] text-muted-foreground">Each slice of pay is taxed at its own rate. Leave the top band's limit blank for "and above".</p>
                  {(cl.bands || []).map((b, bi) => (
                    <div key={bi} className="flex items-center gap-2 text-[11px]">
                      <span className="text-muted-foreground w-10">up to</span>
                      <Input className="h-7 text-xs w-28" type="number" value={b.up_to ?? ''} placeholder="and above"
                        onChange={e => patchBand(i, bi, { up_to: e.target.value === '' ? null : parseFloat(e.target.value) })}
                        data-testid={`compliance-band-upto-${i}-${bi}`} />
                      <Input className="h-7 text-xs w-20" type="number" step="0.1" value={b.rate ?? 0}
                        onChange={e => patchBand(i, bi, { rate: parseFloat(e.target.value) || 0 })}
                        data-testid={`compliance-band-rate-${i}-${bi}`} />
                      <span className="text-muted-foreground">%</span>
                      <button type="button" className="text-destructive" onClick={() => removeBand(i, bi)}>×</button>
                    </div>
                  ))}
                  <Button type="button" size="sm" variant="ghost" className="h-7 text-[11px] gap-1" onClick={() => addBand(i)}>
                    <Plus size={12} /> Add band
                  </Button>
                </div>
              )}
            </div>
            {cl.notes && <p className="text-[10px] text-muted-foreground">{cl.notes}</p>}
          </div>
        );
      })}
    </div>
  );
};

export default ComplianceLinesEditor;
