import React, { useEffect, useState } from 'react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../components/ui/dialog';
import { Building2, Plus, LogIn, PauseCircle, PlayCircle, Download, Upload, Trash2, Settings2, UserRoundCog } from 'lucide-react';
import { toast } from 'sonner';
import { OrgActivityLog } from '../components/organizations/OrgActivityLog';
import { MovePersonDialog } from '../components/organizations/MovePersonDialog';
import { EditOrgDialog } from '../components/organizations/EditOrgDialog';

const blankOrg = {
  name: '', slug: '', hostnames: '', owner_name: '', owner_email: '', owner_password: '',
};

export default function OrganizationsPage() {
  const { user, enterOrganization } = useAuth();
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(blankOrg);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deleteSlug, setDeleteSlug] = useState('');
  const [editing, setEditing] = useState(null);
  const [busyOrg, setBusyOrg] = useState(null);
  const [moving, setMoving] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get('/organizations');
      setOrgs(res.data.organizations || []);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not load organisations');
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.name.trim() || !form.slug.trim()) { toast.error('Name and slug are required'); return; }
    setSaving(true);
    try {
      await api.post('/organizations', {
        name: form.name.trim(),
        slug: form.slug.trim().toLowerCase(),
        hostnames: form.hostnames.split(',').map(h => h.trim()).filter(Boolean),
        owner_name: form.owner_name.trim() || undefined,
        owner_email: form.owner_email.trim() || undefined,
        owner_password: form.owner_password || undefined,
      });
      toast.success(`${form.name} created`);
      setShowCreate(false);
      setForm(blankOrg);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not create organisation');
    } finally { setSaving(false); }
  };

  const setStatus = async (org, status) => {
    try {
      await api.post(`/organizations/${org.id}/status`, { status });
      toast.success(`${org.name} ${status === 'suspended' ? 'suspended' : 'reactivated'}`);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not change status');
    }
  };

  const exportOrg = async (org) => {
    if (busyOrg) return;
    setBusyOrg(org.id);
    const preparing = toast.loading(`Preparing ${org.name} — this can take a minute for a large organisation…`);
    try {
      // Ask for the raw text: a big export is tens of MB and re-serialising the
      // parsed object (JSON.stringify with indentation) doubled the memory for
      // no benefit.
      const res = await api.get(`/organizations/${org.id}/export`, { responseType: 'text' });
      const text = typeof res.data === 'string' ? res.data : JSON.stringify(res.data);
      let summary = {};
      try { summary = JSON.parse(text); } catch { summary = {}; }

      const blob = new Blob([text], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${org.slug}-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.style.display = 'none';
      // The anchor has to be in the document, and the object URL has to outlive
      // the click — revoking it immediately cancelled the download, which is why
      // nothing ever arrived for anything but the smallest organisation.
      document.body.appendChild(a);
      a.click();
      window.setTimeout(() => {
        URL.revokeObjectURL(url);
        a.remove();
      }, 60000);

      toast.dismiss(preparing);
      const files = summary.file_count || 0;
      const size = blob.size >= 1024 * 1024
        ? `${(blob.size / 1024 / 1024).toFixed(1)} MB`
        : `${Math.max(1, Math.round(blob.size / 1024))} KB`;
      toast.success(
        `${org.name}: ${summary.document_count ?? '?'} records and ${files} file${files === 1 ? '' : 's'} (${size})`,
        { duration: 8000 },
      );
      if (summary.files_missing?.length) {
        toast.warning(`${summary.files_missing.length} file(s) could not be read and are listed in the export`, { duration: 10000 });
      }
    } catch (err) {
      toast.dismiss(preparing);
      toast.error(err.response?.data?.detail || 'Export failed');
    } finally {
      setBusyOrg(null);
    }
  };

  const importOrg = async (file) => {
    try {
      const payload = JSON.parse(await file.text());
      const res = await api.post('/organizations/import', payload);
      toast.success(`Restored ${res.data.restored_documents} records as ${res.data.organization.name}`);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Import failed — is this a 58:12 export file?');
    }
  };

  const remove = async () => {
    try {
      const res = await api.delete(`/organizations/${confirmDelete.id}`, {
        params: { confirm: deleteSlug },
      });
      toast.success(res.data.message);
      setConfirmDelete(null);
      setDeleteSlug('');
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Delete failed');
    }
  };

  const enter = async (org) => {
    try {
      await enterOrganization(org.id);
      window.location.href = '/dashboard';
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not open that organisation');
    }
  };

  const activeId = user?.active_organization_id;

  return (
    <div className="space-y-8" data-testid="organizations-page">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold font-heading flex items-center gap-2">
            <Building2 className="text-primary" size={28} /> Organisations
          </h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Each organisation is a sealed world: its own people, money, campuses and admins.
            Nothing is shared, and you work inside one at a time.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="inline-flex">
            <input
              type="file"
              accept="application/json"
              className="hidden"
              data-testid="import-org-input"
              onChange={(e) => { if (e.target.files?.[0]) importOrg(e.target.files[0]); e.target.value = ''; }}
            />
            <Button variant="outline" asChild data-testid="import-org-btn">
              <span className="cursor-pointer gap-2 inline-flex items-center"><Upload size={15} /> Import</span>
            </Button>
          </label>
          <Button onClick={() => setShowCreate(true)} className="gap-2" data-testid="new-org-btn">
            <Plus size={16} /> New organisation
          </Button>
        </div>
      </div>

      {loading ? (
        <p className="text-muted-foreground" data-testid="orgs-loading">Loading…</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {orgs.map(org => (
            <Card
              key={org.id}
              data-testid={`org-card-${org.slug}`}
              className={`transition-colors ${org.id === activeId ? 'border-primary' : ''}`}
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="text-lg">{org.name}</CardTitle>
                  {org.status === 'suspended'
                    ? <Badge variant="destructive" data-testid={`org-status-${org.slug}`}>Suspended</Badge>
                    : <Badge variant="secondary" data-testid={`org-status-${org.slug}`}>Active</Badge>}
                </div>
                <p className="text-xs text-muted-foreground font-mono">{org.slug}</p>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex gap-4 text-sm">
                  <span><strong>{org.stats?.users ?? 0}</strong> <span className="text-muted-foreground">{org.stats?.users === 1 ? 'user' : 'users'}</span></span>
                  <span><strong>{org.stats?.members ?? 0}</strong> <span className="text-muted-foreground">{org.stats?.members === 1 ? 'person' : 'people'}</span></span>
                  <span><strong>{org.stats?.campuses ?? 0}</strong> <span className="text-muted-foreground">{org.stats?.campuses === 1 ? 'campus' : 'campuses'}</span></span>
                </div>
                {(org.hostnames || []).length > 0 && (
                  <p className="text-xs text-muted-foreground break-all">{org.hostnames.join(', ')}</p>
                )}
                {org.suspend_reason && (
                  <p className="text-xs text-destructive">Reason: {org.suspend_reason}</p>
                )}
                <div className="flex flex-wrap gap-2 pt-1">
                  <Button
                    size="sm" variant="default" className="gap-1.5"
                    disabled={org.status === 'suspended' || org.id === activeId}
                    onClick={() => enter(org)}
                    data-testid={`enter-org-${org.slug}`}
                  >
                    <LogIn size={14} /> {org.id === activeId ? 'Current' : 'Open'}
                  </Button>
                  <Button size="sm" variant="outline" className="gap-1.5"
                    onClick={() => exportOrg(org)} disabled={busyOrg === org.id}
                    data-testid={`export-org-${org.slug}`}>
                    <Download size={14} /> {busyOrg === org.id ? 'Preparing…' : 'Export'}
                  </Button>
                  {org.status === 'suspended' ? (
                    <Button size="sm" variant="outline" className="gap-1.5"
                      onClick={() => setStatus(org, 'active')} data-testid={`resume-org-${org.slug}`}>
                      <PlayCircle size={14} /> Resume
                    </Button>
                  ) : (
                    <Button size="sm" variant="outline" className="gap-1.5"
                      onClick={() => setStatus(org, 'suspended')} data-testid={`suspend-org-${org.slug}`}>
                      <PauseCircle size={14} /> Suspend
                    </Button>
                  )}
                  <Button size="sm" variant="outline" className="gap-1.5"
                    onClick={() => setEditing(org)} data-testid={`edit-org-${org.slug}`}>
                    <Settings2 size={14} /> Address
                  </Button>
                  <Button size="sm" variant="outline" className="gap-1.5"
                    onClick={() => setMoving(org)} data-testid={`move-person-${org.slug}`}>
                    <UserRoundCog size={14} /> Move someone
                  </Button>
                  {org.status === 'suspended' && !org.is_default && (
                    <Button size="sm" variant="ghost" className="gap-1.5 text-destructive"
                      onClick={() => setConfirmDelete(org)} data-testid={`delete-org-${org.slug}`}>
                      <Trash2 size={14} /> Delete
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {!loading && <OrgActivityLog organizations={orgs.map(o => ({ id: o.id, name: o.name }))} />}

      {editing && (
        <EditOrgDialog org={editing} onClose={() => setEditing(null)} onSaved={load} />
      )}
      {moving && (
        <MovePersonDialog org={moving} organizations={orgs} onClose={() => setMoving(null)} onMoved={load} />
      )}

      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-lg" data-testid="create-org-dialog">
          <DialogHeader><DialogTitle>New organisation</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="org-name">Name</Label>
              <Input id="org-name" value={form.name} data-testid="org-name-input"
                onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Lubwamas" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="org-slug">Short code</Label>
              <Input id="org-slug" value={form.slug} data-testid="org-slug-input"
                onChange={e => setForm({ ...form, slug: e.target.value.toLowerCase() })}
                placeholder="lubwamas" />
              <p className="text-xs text-muted-foreground">Lowercase letters, numbers and hyphens.</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="org-hosts">Web addresses</Label>
              <Input id="org-hosts" value={form.hostnames} data-testid="org-hostnames-input"
                onChange={e => setForm({ ...form, hostnames: e.target.value })}
                placeholder="new.lubwamas.org, personal.5812uganda.org" />
              <p className="text-xs text-muted-foreground">
                Comma separated. Point each one at this server and it opens straight into this organisation.
              </p>
            </div>
            <div className="pt-2 border-t border-border space-y-4">
              <p className="text-sm font-medium">First administrator (optional)</p>
              <div className="grid gap-3 sm:grid-cols-2">
                <Input placeholder="Full name" value={form.owner_name} data-testid="org-owner-name-input"
                  onChange={e => setForm({ ...form, owner_name: e.target.value })} />
                <Input placeholder="Email" type="email" value={form.owner_email} data-testid="org-owner-email-input"
                  onChange={e => setForm({ ...form, owner_email: e.target.value })} />
              </div>
              <Input placeholder="Temporary password" type="text" value={form.owner_password}
                data-testid="org-owner-password-input"
                onChange={e => setForm({ ...form, owner_password: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={create} disabled={saving} data-testid="create-org-submit">
              {saving ? 'Creating…' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!confirmDelete} onOpenChange={(o) => { if (!o) { setConfirmDelete(null); setDeleteSlug(''); } }}>
        <DialogContent data-testid="delete-org-dialog">
          <DialogHeader><DialogTitle>Delete {confirmDelete?.name}?</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              This erases every record belonging to {confirmDelete?.name} — people, money, history.
              It cannot be undone. Export first if you may ever need it back.
            </p>
            <div className="space-y-2">
              <Label htmlFor="confirm-slug">Type <span className="font-mono">{confirmDelete?.slug}</span> to confirm</Label>
              <Input id="confirm-slug" value={deleteSlug} data-testid="delete-confirm-input"
                onChange={e => setDeleteSlug(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setConfirmDelete(null); setDeleteSlug(''); }}>Cancel</Button>
            <Button variant="destructive" onClick={remove}
              disabled={deleteSlug !== confirmDelete?.slug} data-testid="delete-org-submit">
              Delete permanently
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
