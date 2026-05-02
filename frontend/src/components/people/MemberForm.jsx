import React from 'react';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Switch } from '../ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { MOCK_GROUPS, MOCK_ROLES } from '../../mock';

// Shared form for members/staff — extracted from UnifiedPeoplePage.jsx
export default function MemberForm({ data, onChange, locations, showDepartment }) {
  const departmentOptions = (() => {
    if (!data.location_id) return [];
    const loc = locations.find(l => l.id === data.location_id);
    if (!loc) return [];
    const deps = loc.departments || [];
    if (deps.length === 0 && loc.name) return [loc.name];
    return deps;
  })();

  const isNonDeptRole = ['Parent', 'Customer', 'Guest', 'Child'].includes(data.role);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5"><Label className="text-xs">Name *</Label><Input value={data.name} onChange={e => onChange({ ...data, name: e.target.value })} required data-testid="member-name-input" /></div>
        <div className="space-y-1.5"><Label className="text-xs">Email</Label><Input type="email" value={data.email} onChange={e => onChange({ ...data, email: e.target.value })} data-testid="member-email-input" /></div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5"><Label className="text-xs">Phone</Label><Input value={data.phone} onChange={e => onChange({ ...data, phone: e.target.value })} data-testid="member-phone-input" /></div>
        <div className="space-y-1.5"><Label className="text-xs">ID Number</Label><Input value={data.national_id} onChange={e => onChange({ ...data, national_id: e.target.value })} /></div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5"><Label className="text-xs">Gender *</Label>
          <Select value={data.gender} onValueChange={v => onChange({ ...data, gender: v })}>
            <SelectTrigger data-testid="member-gender-select"><SelectValue placeholder="Select" /></SelectTrigger>
            <SelectContent><SelectItem value="male">Male</SelectItem><SelectItem value="female">Female</SelectItem></SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5"><Label className="text-xs">Role</Label>
          <Select value={data.role} onValueChange={v => onChange({ ...data, role: v })}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>{MOCK_ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
          </Select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5"><Label className="text-xs">Group</Label>
          <Select value={data.group} onValueChange={v => onChange({ ...data, group: v })}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>{MOCK_GROUPS.map(g => <SelectItem key={g} value={g}>{g}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5"><Label className="text-xs">Location</Label>
          <Select value={data.location_id || ''} onValueChange={v => onChange({ ...data, location_id: v, department: '' })}>
            <SelectTrigger><SelectValue placeholder="Select location" /></SelectTrigger>
            <SelectContent>{locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
          </Select>
        </div>
      </div>
      {/* System Admin toggle */}
      {!['Parent', 'Customer', 'Guest', 'Child'].includes(data.role) && (
        <div className="flex items-center justify-between p-2.5 rounded-lg border border-amber-200 bg-amber-50/50">
          <div><Label className="text-xs font-medium">System Admin</Label><p className="text-[10px] text-muted-foreground">Full cross-campus access</p></div>
          <Switch checked={data.is_admin || false} onCheckedChange={v => onChange({ ...data, is_admin: v })} data-testid="member-admin-toggle" />
        </div>
      )}
      {showDepartment && !isNonDeptRole && departmentOptions.length > 0 && (
        <div className="space-y-1.5"><Label className="text-xs">Department</Label>
          <Select value={data.department || ''} onValueChange={v => onChange({ ...data, department: v })}>
            <SelectTrigger><SelectValue placeholder="Select department" /></SelectTrigger>
            <SelectContent>{departmentOptions.map(d => <SelectItem key={d} value={d}>{d}</SelectItem>)}</SelectContent>
          </Select>
        </div>
      )}
      {isNonDeptRole && (
        <div className="space-y-1.5"><Label className="text-xs">Programme</Label>
          <Input placeholder="e.g. Children's Church" value={data.program || ''} onChange={e => onChange({ ...data, program: e.target.value })} />
        </div>
      )}
      <div className="space-y-1.5"><Label className="text-xs">Date of Birth</Label><Input type="date" value={data.date_of_birth || ''} onChange={e => onChange({ ...data, date_of_birth: e.target.value })} /></div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5"><Label className="text-xs">PIN Code</Label><Input placeholder="4-digit PIN" maxLength={10} value={data.pin || ''} onChange={e => onChange({ ...data, pin: e.target.value })} /></div>
        <div className="space-y-1.5 flex flex-col justify-end gap-2">
          <div className="flex items-center gap-2"><Switch checked={data.is_parent || false} onCheckedChange={v => onChange({ ...data, is_parent: v })} /><Label className="text-xs">Parent</Label></div>
          <div className="flex items-center gap-2"><Switch checked={data.is_donor || false} onCheckedChange={v => onChange({ ...data, is_donor: v })} /><Label className="text-xs">Donor</Label></div>
        </div>
      </div>
      <div className="space-y-1.5"><Label className="text-xs">Notes</Label><Textarea rows={2} value={data.notes || ''} onChange={e => onChange({ ...data, notes: e.target.value })} /></div>
    </div>
  );
}
