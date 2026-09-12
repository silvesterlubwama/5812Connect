import React, { useEffect, useState, useMemo } from 'react';
import { Building2, Plus, Trash2, Edit2, Save, X, Wand2 } from 'lucide-react';
import { Card, CardContent } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Badge } from '../ui/badge';
import { Switch } from '../ui/switch';
import { departmentsApi, locationsApi } from '../../services/api';
import api from '../../services/api';
import { toast } from 'sonner';

const DEFAULT_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16', '#6366f1', '#f97316'];

/**
 * Admin System Console → Departments tab.
 *
 * Departments are a cost-centre dimension (Option B from the design chat):
 * they live inside a campus (required) and optionally inside a sub-location,
 * but they aren't physical places themselves. Used for budgeting,
 * multi-department staffing, and split-funded salaries.
 */
export function DepartmentsManager() {
  const [departments, setDepartments] = useState([]);
  const [locations, setLocations] = useState([]);
  const [subLocations, setSubLocations] = useState([]);
  const [showInactive, setShowInactive] = useState(false);
  const [busy, setBusy] = useState(false);

  const [showAdd, setShowAdd] = useState(false);
  const empty = { name: '', description: '', location_id: '', sublocation_id: '', color: DEFAULT_COLORS[0], budget: '', active: true };
  const [form, setForm] = useState(empty);
  const [editingId, setEditingId] = useState(null);

  // Legacy free-text department migration
  const [legacy, setLegacy] = useState(null);      // { groups, total_records }
  const [showLegacy, setShowLegacy] = useState(false);
  const [migrating, setMigrating] = useState(false);
  const [migrateResult, setMigrateResult] = useState(null);

  const openLegacy = async () => {
    setShowLegacy(true);
    setMigrateResult(null);
    try {
      const res = await departmentsApi.legacyScan();
      setLegacy(res.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not scan for legacy departments');
      setLegacy({ groups: [], total_records: 0 });
    }
  };

  const runMigration = async () => {
    setMigrating(true);
    try {
      const res = await departmentsApi.migrateLegacy({ dry_run: false });
      setMigrateResult(res.data);
      toast.success(`Migrated ${res.data.records_total} record(s) into ${res.data.departments_created.length} department(s)`);
      await fetchAll();
      const rescan = await departmentsApi.legacyScan();
      setLegacy(rescan.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Migration failed');
    } finally { setMigrating(false); }
  };

  const fetchAll = async () => {
    try {
      const [dRes, lRes, sRes] = await Promise.all([
        departmentsApi.list({ include_inactive: showInactive }),
        locationsApi.list().catch(() => ({ data: [] })),
        // Sub-locations live inside the financial router today; fetch what
        // exists and gracefully fall back to an empty list.
        api.get('/financial/sublocations').catch(() => ({ data: [] })),
      ]);
      setDepartments(dRes.data || []);
      setLocations(lRes.data || []);
      setSubLocations(sRes.data || []);
    } catch {
      toast.error('Failed to load departments');
    }
  };

  useEffect(() => { fetchAll(); /* eslint-disable-next-line */ }, [showInactive]);

  const subLocsForCampus = useMemo(
    () => subLocations.filter(s => s.location_id === form.location_id),
    [subLocations, form.location_id],
  );

  const startEdit = (d) => {
    setEditingId(d.id);
    setForm({
      name: d.name || '',
      description: d.description || '',
      location_id: d.location_id || '',
      sublocation_id: d.sublocation_id || '',
      color: d.color || DEFAULT_COLORS[0],
      budget: d.budget ?? '',
      active: d.active !== false,
    });
    setShowAdd(true);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setForm(empty);
    setShowAdd(false);
  };

  const save = async () => {
    if (!form.name.trim()) { toast.error('Name is required'); return; }
    if (!form.location_id) { toast.error('Pick a campus'); return; }
    setBusy(true);
    try {
      const payload = {
        name: form.name.trim(),
        description: form.description || null,
        location_id: form.location_id,
        sublocation_id: form.sublocation_id || null,
        color: form.color || null,
        budget: form.budget === '' ? null : Number(form.budget),
        active: !!form.active,
      };
      if (editingId) {
        await departmentsApi.update(editingId, payload);
        toast.success('Department updated');
      } else {
        await departmentsApi.create(payload);
        toast.success('Department created');
      }
      cancelEdit();
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Save failed');
    } finally { setBusy(false); }
  };

  const remove = async (d, hard = false) => {
    // iter-dept-guard: peek at usage first so the confirm modal is honest.
    let usage = null;
    try {
      const uRes = await departmentsApi.usage(d.id);
      usage = uRes.data;
    } catch { /* fall through to blind confirm */ }
    let msg;
    if (usage && (usage.users_tagged || usage.active_salaries || usage.unpaid_expenses)) {
      msg = `"${d.name}" is in use — ${usage.users_tagged} user(s), ${usage.active_salaries} active salary record(s), ${usage.unpaid_expenses} unpaid expense(s). \n\n` +
        (hard ? 'Hard delete is refused while any user is tagged. Cancel and use Reassign first.' : 'Deactivate anyway? Existing tagged records keep their reference and can be reassigned later.');
    } else {
      msg = hard
        ? `Permanently delete "${d.name}"? Only allowed when no user is tagged with it.`
        : `Deactivate "${d.name}"? Existing tagged staff and expenses keep their reference.`;
    }
    if (!window.confirm(msg)) return;
    try {
      if (!hard && usage && (usage.users_tagged || usage.active_salaries || usage.unpaid_expenses)) {
        // Force-deactivate via PUT to bypass the 409 guard now that the
        // admin has seen and accepted the impact.
        await departmentsApi.update(d.id, { active: false, force: true });
        toast.success('Department deactivated (force)');
      } else {
        await departmentsApi.delete(d.id, { hard });
        toast.success(hard ? 'Department deleted' : 'Department deactivated');
      }
      fetchAll();
    } catch (e) {
      // 409 with structured detail → give the admin a chance to reassign.
      const detail = e.response?.data?.detail;
      if (e.response?.status === 409 && typeof detail === 'object') {
        const target = window.prompt(
          `Cannot deactivate — ${detail.users_tagged} user(s), ${detail.active_salaries} salary(ies), ${detail.unpaid_expenses} unpaid expense(s) still reference this department.\n\n` +
          `To reassign to another department, enter its id (see the list below), or Cancel:\n\n` +
          departments.filter(x => x.id !== d.id && x.active !== false).map(x => `${x.id} — ${x.name}`).join('\n')
        );
        if (target) {
          try {
            await departmentsApi.reassign(d.id, target.trim());
            toast.success('References reassigned. Retrying deactivation…');
            await departmentsApi.update(d.id, { active: false });
            toast.success('Department deactivated');
            fetchAll();
          } catch (e2) {
            toast.error(e2.response?.data?.detail || 'Reassign failed');
          }
        }
      } else {
        toast.error(detail || 'Delete failed');
      }
    }
  };

  const locName = (id) => locations.find(l => l.id === id)?.name || id;
  const subName = (id) => subLocations.find(s => s.id === id)?.name || id;

  return (
    <Card data-testid="departments-manager">
      <CardContent className="p-4 space-y-4">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <Building2 size={18} className="text-primary" />
            <div>
              <h3 className="font-semibold text-sm">Departments</h3>
              <p className="text-xs text-muted-foreground">Cost-centres that live inside a campus. Used for staff tagging, split-funded salaries, and department P&L.</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
              <Switch checked={showInactive} onCheckedChange={setShowInactive} data-testid="dept-show-inactive" />
              Show inactive
            </label>
            <Button size="sm" variant="outline" onClick={openLegacy} data-testid="migrate-legacy-depts-btn">
              <Wand2 size={13} className="mr-1" /> Migrate legacy
            </Button>
            <Button size="sm" onClick={() => { setEditingId(null); setForm(empty); setShowAdd(true); }} data-testid="add-department-btn">
              <Plus size={13} className="mr-1" /> Add
            </Button>
          </div>
        </div>

        <Dialog open={showLegacy} onOpenChange={setShowLegacy}>
          <DialogContent className="max-w-[620px]" data-testid="legacy-depts-dialog">
            <DialogHeader>
              <DialogTitle className="text-base">Migrate legacy departments</DialogTitle>
            </DialogHeader>
            <p className="text-xs text-muted-foreground">
              Before departments were real records, they were typed in by hand on staff, members and expenses.
              Those rows never show up in department P&amp;L or staffing reports. This folds each typed name into a
              proper department inside the same campus (matching existing ones, ignoring case and stray spaces).
            </p>
            {!legacy ? (
              <p className="text-sm py-6 text-center text-muted-foreground">Scanning…</p>
            ) : legacy.groups.length === 0 ? (
              <p className="text-sm py-6 text-center text-muted-foreground" data-testid="legacy-depts-empty">
                Nothing to migrate — every record already points at a real department.
              </p>
            ) : (
              <div className="space-y-2 max-h-[45vh] overflow-y-auto">
                {legacy.groups.map(g => (
                  <div key={g.legacy_name} className="rounded-lg border p-2.5 text-sm" data-testid={`legacy-group-${g.legacy_name.trim().replace(/\s+/g, '-').toLowerCase()}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">"{g.legacy_name}"</span>
                      <Badge variant="outline" className="text-[10px]">{g.count} record{g.count === 1 ? '' : 's'}</Badge>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-1">
                      {Object.entries(g.collections).map(([c, n]) => `${n} ${c}`).join(' · ')}
                      {g.matches_existing ? ` → links to existing "${g.matches_existing.name}"` : ' → a new department will be created'}
                    </p>
                    {g.samples?.length > 0 && (
                      <p className="text-[11px] text-muted-foreground">e.g. {g.samples.join(', ')}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
            {migrateResult && (
              <div className="rounded-lg border border-emerald-300 bg-emerald-50 p-2.5 text-xs" data-testid="legacy-migrate-result">
                Created {migrateResult.departments_created.length} department(s) and updated {migrateResult.records_total} record(s).
                {migrateResult.skipped_no_campus > 0 && ` ${migrateResult.skipped_no_campus} skipped (no campus on the record).`}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="outline" onClick={() => setShowLegacy(false)} data-testid="legacy-depts-close">Close</Button>
              <Button size="sm" disabled={migrating || !legacy?.groups?.length} onClick={runMigration} data-testid="legacy-depts-run-btn">
                {migrating ? 'Migrating…' : `Migrate ${legacy?.total_records || 0} record(s)`}
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        {showAdd && (
          <div className="rounded-lg border p-3 space-y-3 bg-muted/30">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1"><Label className="text-xs">Name *</Label>
                <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Social Work" data-testid="dept-name-input" />
              </div>
              <div className="space-y-1"><Label className="text-xs">Campus *</Label>
                <Select value={form.location_id} onValueChange={v => setForm({ ...form, location_id: v, sublocation_id: '' })}>
                  <SelectTrigger data-testid="dept-campus-select"><SelectValue placeholder="Pick campus…" /></SelectTrigger>
                  <SelectContent>
                    {locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {subLocsForCampus.length > 0 && (
              <div className="space-y-1"><Label className="text-xs">Sub-location (optional)</Label>
                <Select value={form.sublocation_id || '__none__'} onValueChange={v => setForm({ ...form, sublocation_id: v === '__none__' ? '' : v })}>
                  <SelectTrigger data-testid="dept-subloc-select"><SelectValue placeholder="No sub-location" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">— none —</SelectItem>
                    {subLocsForCampus.map(s => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1"><Label className="text-xs">Colour</Label>
                <div className="flex gap-1 flex-wrap">
                  {DEFAULT_COLORS.map(c => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => setForm({ ...form, color: c })}
                      className={`w-6 h-6 rounded-full transition-transform ${form.color === c ? 'ring-2 ring-primary ring-offset-2 scale-110' : ''}`}
                      style={{ background: c }}
                      aria-label={`Pick colour ${c}`}
                    />
                  ))}
                </div>
              </div>
              <div className="space-y-1"><Label className="text-xs">Budget (optional)</Label>
                <Input type="number" min={0} value={form.budget} onChange={e => setForm({ ...form, budget: e.target.value })} placeholder="e.g. 5000000" data-testid="dept-budget-input" />
              </div>
            </div>
            <div className="space-y-1"><Label className="text-xs">Description</Label>
              <Input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="What does this department do?" />
            </div>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                <Switch checked={form.active} onCheckedChange={v => setForm({ ...form, active: v })} />
                Active
              </label>
              <div className="ml-auto flex gap-2">
                <Button size="sm" variant="outline" onClick={cancelEdit} disabled={busy}><X size={12} className="mr-1" /> Cancel</Button>
                <Button size="sm" onClick={save} disabled={busy} data-testid="dept-save-btn"><Save size={12} className="mr-1" /> {editingId ? 'Update' : 'Create'}</Button>
              </div>
            </div>
          </div>
        )}

        {departments.length === 0 ? (
          <div className="text-center py-6 text-sm text-muted-foreground border border-dashed rounded-lg">
            No departments yet. Add one to start tagging staff and expenses.
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 gap-2">
            {departments.map(d => (
              <div key={d.id} className={`rounded-lg border p-3 flex items-center gap-3 ${d.active === false ? 'opacity-50 bg-muted/30' : ''}`} data-testid={`dept-row-${d.id}`}>
                <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: d.color || '#3b82f6' }} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-medium text-sm truncate">{d.name}</p>
                    {d.active === false && <Badge variant="secondary" className="text-[9px]">Inactive</Badge>}
                  </div>
                  <p className="text-[11px] text-muted-foreground truncate">
                    {locName(d.location_id)}{d.sublocation_id ? ` · ${subName(d.sublocation_id)}` : ''}
                    {d.budget != null && d.budget !== '' ? ` · Budget ${Number(d.budget).toLocaleString()}` : ''}
                  </p>
                </div>
                <div className="flex gap-1">
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => startEdit(d)} data-testid={`dept-edit-${d.id}`}><Edit2 size={12} /></Button>
                  <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => remove(d, false)} data-testid={`dept-deactivate-${d.id}`}><Trash2 size={12} /></Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default DepartmentsManager;
