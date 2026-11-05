import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink, Lock, RefreshCw, Search, Shield, UserCog } from 'lucide-react';
import { Avatar, AvatarFallback, AvatarImage } from '../ui/avatar';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { Card, CardContent } from '../ui/card';
import { Input } from '../ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Switch } from '../ui/switch';
import { adminApi } from '../../services/api';
import EmptyState from '../EmptyState';
import { toast } from 'sonner';

// Job titles only — the admin TIER is the switch, not an entry in this list.
const JOB_ROLES = ['Executive Director', 'Adviser', 'Director', 'Manager', 'Coordinator', 'Staff', 'HR', 'Intern', 'Volunteer'];
const ADMIN_TIER = ['admin', 'system_admin'];
const initials = (name) => (name || '?').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
const jobRoleOf = (u) => (ADMIN_TIER.includes(u.role) ? (u.secondary_roles?.[0] || 'Staff') : (u.role || 'Staff'));

export default function StaffListTab({ canEdit }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [savingId, setSavingId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminApi.users();
      setUsers(Array.isArray(r.data) ? r.data : []);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not load the staff list');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return users
      .filter(u => roleFilter === 'all' || (roleFilter === 'admins' ? ADMIN_TIER.includes(u.role) : jobRoleOf(u) === roleFilter))
      .filter(u => !q || [u.name, u.email, u.role, u.phone].some(v => (v || '').toLowerCase().includes(q)))
      .sort((a, b) => (a.name || '').localeCompare(b.name || ''));
  }, [users, search, roleFilter]);

  // Every save goes to the sign-in account, so what you see here IS what the
  // person gets when they log in.
  const save = async (u, updates) => {
    setSavingId(u.id);
    try {
      await adminApi.updateUser(u.id, updates);
      setUsers(prev => prev.map(x => (x.id === u.id ? { ...x, ...updates } : x)));
      toast.success(`${u.name || 'Account'} updated`);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not update this account');
    } finally { setSavingId(null); }
  };

  const setAdmin = (u, on) => save(u, on
    ? { role: u.role === 'system_admin' ? 'system_admin' : 'admin', secondary_roles: [jobRoleOf(u)] }
    : { role: jobRoleOf(u) });

  const setJobRole = (u, role) => save(u, ADMIN_TIER.includes(u.role)
    ? { secondary_roles: [role] }
    : { role });

  if (loading) {
    return <div className="flex items-center gap-2 text-sm text-muted-foreground py-10 justify-center" data-testid="staff-loading"><RefreshCw size={14} className="animate-spin" /> Loading staff…</div>;
  }

  return (
    <div data-testid="staff-list-tab">
      <div className="flex flex-col sm:flex-row gap-2 mb-3">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input className="pl-9 h-8 text-sm" placeholder="Search staff by name, email or role..." value={search} onChange={e => setSearch(e.target.value)} data-testid="staff-search" />
        </div>
        <Select value={roleFilter} onValueChange={setRoleFilter}>
          <SelectTrigger className="w-full sm:w-44 h-8 text-sm" data-testid="staff-role-filter"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All roles</SelectItem>
            <SelectItem value="admins">Admins only</SelectItem>
            {JOB_ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" className="gap-2 h-8" onClick={load} data-testid="staff-refresh"><RefreshCw size={13} /> Refresh</Button>
      </div>

      {visible.length === 0 ? (
        <EmptyState
          icon={UserCog}
          title={search || roleFilter !== 'all' ? 'Nobody matches that search' : 'No staff accounts yet'}
          description="Staff are people with a sign-in account. Create them in the System Console, then set what they can reach from here."
          testid="staff-empty"
        />
      ) : (
        <div className="space-y-2" data-testid="staff-rows">
          {visible.map(u => {
            const isAdminTier = ADMIN_TIER.includes(u.role);
            const locked = (u.role || '').toLowerCase() === 'super_admin';
            const busy = savingId === u.id;
            return (
              <Card key={u.id} className="shadow-soft rounded-xl" data-testid={`staff-row-${u.id}`}>
                <CardContent className="p-3 flex flex-wrap items-center gap-3">
                  <Avatar className="h-9 w-9">
                    {u.photo_url && <AvatarImage src={u.photo_url} alt={u.name || ''} />}
                    <AvatarFallback className="bg-primary/10 text-primary text-xs font-semibold">{initials(u.name)}</AvatarFallback>
                  </Avatar>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-medium truncate" data-testid={`staff-name-${u.id}`}>{u.name || u.email}</p>
                      {isAdminTier && <Badge className="text-[10px] gap-1 bg-primary/10 text-primary border-primary/20" data-testid={`staff-admin-badge-${u.id}`}><Shield size={9} /> {u.role === 'system_admin' ? 'System admin' : 'Admin'}</Badge>}
                      {locked && <Badge variant="outline" className="text-[10px] gap-1"><Lock size={9} /> Owner</Badge>}
                      {u.status && u.status !== 'active' && <Badge variant="outline" className="text-[10px] border-amber-300 text-amber-700" data-testid={`staff-status-${u.id}`}>{u.status}</Badge>}
                    </div>
                    <p className="text-xs text-muted-foreground truncate">{u.email}{u.phone ? ` · ${u.phone}` : ''}</p>
                  </div>

                  {canEdit && !locked ? (
                    <div className="flex items-center gap-3 flex-wrap">
                      <Select value={jobRoleOf(u)} onValueChange={v => setJobRole(u, v)} disabled={busy}>
                        <SelectTrigger className="w-36 h-8 text-xs" data-testid={`staff-role-select-${u.id}`}><SelectValue /></SelectTrigger>
                        <SelectContent>{[...new Set([...JOB_ROLES, jobRoleOf(u)])].map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                      </Select>
                      <label className="flex items-center gap-2 text-xs text-muted-foreground">
                        Admin
                        <Switch checked={isAdminTier} disabled={busy} onCheckedChange={v => setAdmin(u, v)} data-testid={`staff-admin-toggle-${u.id}`} />
                      </label>
                      <label className="flex items-center gap-2 text-xs text-muted-foreground">
                        Active
                        <Switch checked={(u.status || 'active') === 'active'} disabled={busy} onCheckedChange={v => save(u, { status: v ? 'active' : 'suspended' })} data-testid={`staff-active-toggle-${u.id}`} />
                      </label>
                      <Button asChild variant="ghost" size="sm" className="h-8 w-8 p-0" title="Open in System Console">
                        <Link to="/admin" data-testid={`staff-open-console-${u.id}`}><ExternalLink size={13} /></Link>
                      </Button>
                    </div>
                  ) : (
                    <Badge variant="secondary" className="text-[10px]">{jobRoleOf(u)}</Badge>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
      <p className="text-[11px] text-muted-foreground mt-3">
        Changes here apply to the person's sign-in account straight away. Creating accounts, passwords and deletions stay in the{' '}
        <Link to="/admin" className="underline" data-testid="staff-console-link">System Console</Link>.
      </p>
    </div>
  );
}
