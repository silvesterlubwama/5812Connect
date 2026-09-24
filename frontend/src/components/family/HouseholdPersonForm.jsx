import React from 'react';
import { Label } from '../ui/label';
import { Input } from '../ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Switch } from '../ui/switch';

// One role list for every surface — People, child profiles and the member portal.
export const FAMILY_ROLES = ['Mother', 'Father', 'Guardian', 'Grandparent', 'Aunt', 'Uncle', 'Sibling', 'Step-Parent', 'Other'];
export const MAX_FAMILY_MEMBERS = 6;

const ROLE_ALIASES = {
  mother: 'Mother', mum: 'Mother', mom: 'Mother', mama: 'Mother',
  father: 'Father', dad: 'Father', papa: 'Father',
  guardian: 'Guardian', parent: 'Guardian', spouse: 'Guardian', husband: 'Guardian',
  wife: 'Guardian', partner: 'Guardian', caregiver: 'Guardian', 'foster parent': 'Guardian',
  'household member': 'Guardian', 'primary contact': 'Guardian',
  'step-parent': 'Step-Parent', 'step parent': 'Step-Parent', stepfather: 'Step-Parent', stepmother: 'Step-Parent',
  grandparent: 'Grandparent', grandmother: 'Grandparent', grandfather: 'Grandparent',
  granny: 'Grandparent', grandma: 'Grandparent', grandpa: 'Grandparent',
  aunt: 'Aunt', auntie: 'Aunt', 'aunt/uncle': 'Aunt', uncle: 'Uncle',
  sibling: 'Sibling', brother: 'Sibling', sister: 'Sibling',
};

export const normaliseRole = (raw) => {
  const r = (raw || '').trim().toLowerCase();
  if (!r) return 'Guardian';
  const exact = FAMILY_ROLES.find(x => x.toLowerCase() === r);
  return exact || ROLE_ALIASES[r] || 'Other';
};

// Pickup is on by default for the people who raise the children.
export const defaultCanPickup = (role) => ['mother', 'father', 'guardian'].includes((role || '').toLowerCase());

/** Shared name/phone/email/role/pickup block for family members. */
export const FamilyMemberFields = ({ form, setForm, testIdPrefix = 'member' }) => (
  <>
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <div className="space-y-1.5"><Label>Phone</Label>
        <Input value={form.phone || ''} onChange={e => setForm({ ...form, phone: e.target.value })} data-testid={`${testIdPrefix}-phone-input`} />
      </div>
      <div className="space-y-1.5"><Label>Email</Label>
        <Input type="email" value={form.email || ''} onChange={e => setForm({ ...form, email: e.target.value })} data-testid={`${testIdPrefix}-email-input`} />
      </div>
    </div>
    <div className="space-y-1.5"><Label>Role in the family</Label>
      <Select value={normaliseRole(form.role)}
        onValueChange={v => setForm({ ...form, role: v, can_pickup: defaultCanPickup(v) })}>
        <SelectTrigger data-testid={`${testIdPrefix}-role-select`}><SelectValue /></SelectTrigger>
        <SelectContent>{FAMILY_ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
      </Select>
    </div>
    <label className="flex items-start justify-between gap-3 rounded-lg border p-3 cursor-pointer"
      data-testid={`${testIdPrefix}-pickup-row`}>
      <span className="text-xs">
        <span className="block font-medium text-sm">Can pick up children</span>
        <span className="text-muted-foreground">Allowed to collect the children from a campus or event</span>
      </span>
      <Switch checked={form.can_pickup !== false}
        onCheckedChange={v => setForm({ ...form, can_pickup: v })}
        data-testid={`${testIdPrefix}-pickup-toggle`} />
    </label>
  </>
);
