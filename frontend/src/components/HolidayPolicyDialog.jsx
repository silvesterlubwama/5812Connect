import React, { useState } from 'react';
import { CalendarDays, Info } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { holidaysApi } from '../services/api';
import { toast } from 'sonner';

export const POLICY_LABELS = {
  paid: 'Paid holiday',
  optional_paid: 'Optional paid day off',
  unpaid: 'Unpaid day off',
  hidden: 'Not observed',
};

const OPTIONS = [
  { kind: 'paid', label: 'Paid holiday', help: 'Everyone is paid for the day. Hourly staff are credited their holiday hours — work it and the worked hours stack on top. Daily-wage staff get the day whether they work or not, and double when they do.' },
  { kind: 'optional_paid', label: 'Optional paid day off', help: 'Paid when they take the day off. If they choose to work it, they just get their normal pay.' },
  { kind: 'unpaid', label: 'Unpaid day off', help: 'Shown on the calendar for awareness. No effect on timesheets or payslips.' },
  { kind: 'hidden', label: 'Not observed — hide it', help: 'Removes this holiday from the calendar entirely. Nothing is paid.' },
];

/** Admin control for how a public holiday is treated by payroll.
 *  Saved per holiday NAME, so the choice sticks for every future year. */
export const HolidayPolicyDialog = ({ holiday, onClose, onSaved, canEdit }) => {
  const [saving, setSaving] = useState(null);
  if (!holiday) return null;
  const current = holiday.policy || 'unpaid';
  const save = async (kind) => {
    setSaving(kind);
    try {
      if (kind === 'unpaid') await holidaysApi.resetPolicy(holiday.policy_key);
      else await holidaysApi.setPolicy({ name: holiday.name, country: holiday.country, kind });
      toast.success(`${holiday.name} → ${POLICY_LABELS[kind]}`);
      onSaved?.();
      onClose();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not save holiday policy');
    } finally { setSaving(null); }
  };
  return (
    <Dialog open={!!holiday} onOpenChange={o => { if (!o) onClose(); }}>
      <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto" data-testid="holiday-policy-dialog">
        <DialogHeader><DialogTitle className="flex items-center gap-2"><CalendarDays size={16} />{holiday.name}</DialogTitle></DialogHeader>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>{new Date(holiday.date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}</span>
          <Badge variant="outline" className="text-[10px]">{holiday.country === 'US' ? 'US Federal' : 'Uganda Public'}</Badge>
          <Badge variant="secondary" className="text-[10px]" data-testid="holiday-current-policy">{POLICY_LABELS[current]}</Badge>
        </div>

        {!canEdit ? (
          <p className="text-sm text-muted-foreground pt-2">Only an admin can change how this holiday is paid.</p>
        ) : (
          <>
            <div className="space-y-2 pt-1">
              {OPTIONS.map(o => (
                <button
                  key={o.kind} type="button" disabled={!!saving}
                  data-testid={`holiday-policy-${o.kind}`}
                  onClick={() => save(o.kind)}
                  className={`w-full text-left rounded-lg border p-3 transition-colors hover:bg-secondary/60 disabled:opacity-60 ${current === o.kind ? 'border-primary bg-primary/5' : 'border-border'}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium">{o.label}</p>
                    {current === o.kind && <Badge className="text-[10px]">Current</Badge>}
                    {saving === o.kind && <span className="text-xs text-muted-foreground">Saving…</span>}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">{o.help}</p>
                </button>
              ))}
            </div>
            <p className="flex items-start gap-2 text-xs text-muted-foreground pt-1">
              <Info size={13} className="mt-0.5 shrink-0" />
              Applies to every {holiday.name} — this year and all future years — until an admin changes it. Holiday dates keep updating on their own.
            </p>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default HolidayPolicyDialog;
