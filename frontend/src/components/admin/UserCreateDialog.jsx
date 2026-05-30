import React from 'react';
import { Users, Plus } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Switch } from '../ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog';
import { toast } from 'sonner';

const ROLES = ['Executive Director', 'Adviser', 'Director', 'Manager', 'Coordinator', 'Staff', 'HR', 'Volunteer', 'Security Contractor', 'Member', 'Parent', 'Customer', 'Guest'];

export function UserCreateDialog({ open, onOpenChange, form, setForm, locations, createdUser, onCreateUser }) {
  return (
    <Dialog open={open} onOpenChange={o => { onOpenChange(o); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{createdUser ? 'User Created!' : 'Create New User'}</DialogTitle>
          <DialogDescription>{createdUser ? 'Share these credentials with the new user.' : 'Add a staff member or user account.'}</DialogDescription>
        </DialogHeader>
        {createdUser ? (
          <div className="space-y-4">
            <div className="flex items-center gap-3 p-4 bg-green-50 rounded-xl border border-green-200">
              <div className="h-10 w-10 rounded-full bg-green-100 flex items-center justify-center font-bold text-green-700">{createdUser.name?.[0]}</div>
              <div>
                <p className="font-semibold">{createdUser.name}</p>
                <p className="text-sm text-muted-foreground">{createdUser.email} · {createdUser.role}</p>
              </div>
            </div>
            {createdUser.temp_password && (
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground">Temporary Password (share securely)</p>
                <div className="flex items-center gap-2 p-3 bg-muted rounded-lg font-mono text-sm">
                  <span className="flex-1">{createdUser.temp_password}</span>
                  <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={() => { navigator.clipboard.writeText(createdUser.temp_password); toast.success('Copied!'); }}>Copy</Button>
                </div>
              </div>
            )}
            {createdUser.has_member_profile && <p className="text-xs text-indigo-600 flex items-center gap-1.5"><Users size={12} /> Also added to People directory</p>}
            <Button className="w-full" onClick={() => onOpenChange(false)}>Done</Button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2 space-y-1.5"><Label className="text-xs">Full Name *</Label><Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} data-testid="create-user-name" /></div>
              <div className="col-span-2 space-y-1.5"><Label className="text-xs">Email *</Label><Input type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} data-testid="create-user-email" /></div>
              <div className="space-y-1.5"><Label className="text-xs">Phone</Label><Input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} /></div>
              <div className="space-y-1.5">
                <Label className="text-xs">Role</Label>
                <Select value={form.role} onValueChange={v => setForm({ ...form, role: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label className="text-xs">Department</Label><Input value={form.department} onChange={e => setForm({ ...form, department: e.target.value })} /></div>
              <div className="space-y-1.5">
                <Label className="text-xs">Location</Label>
                <Select value={form.location_id || '_none'} onValueChange={v => setForm({ ...form, location_id: v === '_none' ? '' : v })}>
                  <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_none">None</SelectItem>
                    {locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg border border-amber-200 bg-amber-50/50">
              <div><Label className="text-xs font-medium">System Admin Access</Label><p className="text-[10px] text-muted-foreground">Full cross-campus visibility</p></div>
              <Switch data-testid="create-admin-toggle" checked={form.is_admin || false} onCheckedChange={v => setForm({ ...form, is_admin: v })} />
            </div>
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <input type="checkbox" className="accent-primary" checked={form.also_create_member} onChange={e => setForm({ ...form, also_create_member: e.target.checked })} />
              Also add to People directory (recommended)
            </label>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>Cancel</Button>
              <Button className="flex-1 gap-2" onClick={onCreateUser} data-testid="confirm-create-user"><Plus size={14} /> Create User</Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
