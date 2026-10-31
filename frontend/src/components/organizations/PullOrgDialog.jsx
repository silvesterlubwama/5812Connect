import React, { useEffect, useRef, useState } from 'react';
import api from '../../services/api';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../ui/dialog';
import { DownloadCloud, Loader2, CheckCircle2, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';

const fmtBytes = (b) => {
  if (!b) return '0 B';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.min(Math.floor(Math.log(b) / Math.log(1024)), u.length - 1);
  return `${(b / 1024 ** i).toFixed(i ? 1 : 0)} ${u[i]}`;
};

/** Pull an organisation from another deployment, with live progress. */
export function PullOrgDialog({ onClose, onDone }) {
  const [form, setForm] = useState({ source_url: '', transfer_key: '', name: '', slug: '' });
  const [target, setTarget] = useState('');       // '' = create a new organisation
  const [confirmed, setConfirmed] = useState(false);
  const [orgs, setOrgs] = useState([]);
  const [starting, setStarting] = useState(false);
  const [job, setJob] = useState(null);
  const timer = useRef(null);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  useEffect(() => {
    api.get('/organizations')
      .then((r) => setOrgs(r.data.organizations || []))
      .catch(() => setOrgs([]));
    return () => clearInterval(timer.current);
  }, []);

  const poll = (jobId) => {
    clearInterval(timer.current);
    timer.current = setInterval(async () => {
      try {
        const res = await api.get(`/organizations/pull/${jobId}`);
        setJob(res.data);
        if (res.data.status !== 'running') {
          clearInterval(timer.current);
          if (res.data.status === 'done') {
            toast.success(`${res.data.organization_name} arrived — ${res.data.rows_done?.toLocaleString()} records, ${res.data.files_done} files`);
            onDone?.();
          } else {
            toast.error(res.data.error || 'The transfer stopped before it finished');
          }
        }
      } catch {
        /* keep polling — a slow answer is not a failure */
      }
    }, 2000);
  };

  const start = async () => {
    if (!form.source_url.trim() || !form.transfer_key.trim()) {
      toast.error('The other server\'s address and its transfer key are both needed');
      return;
    }
    if (target && !confirmed) {
      toast.error('Tick the box to confirm everything in that organisation is replaced');
      return;
    }
    setStarting(true);
    try {
      const res = await api.post('/organizations/pull', {
        source_url: form.source_url.trim(),
        transfer_key: form.transfer_key.trim(),
        name: form.name.trim() || undefined,
        slug: target ? undefined : (form.slug.trim().toLowerCase() || undefined),
        target_org_id: target || undefined,
        overwrite: Boolean(target),
      });
      setJob({ ...res.data, status: 'running', rows_done: 0, files_done: 0, bytes_done: 0 });
      toast.success('Transfer started — you can leave this open or come back later');
      poll(res.data.job_id);
      onDone?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not start the transfer');
    } finally { setStarting(false); }
  };

  const rowPct = job?.rows_total ? Math.min(100, Math.round((job.rows_done / job.rows_total) * 100)) : 0;
  const filePct = job?.files_total ? Math.min(100, Math.round((job.files_done / job.files_total) * 100)) : 0;

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-lg" data-testid="pull-org-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <DownloadCloud className="w-5 h-5" /> Bring an organisation in from another deployment
          </DialogTitle>
        </DialogHeader>

        {!job ? (
          <div className="space-y-3 text-sm">
            <p className="text-muted-foreground text-xs">
              On the other server, open Organisations → the organisation → Move to another
              deployment, and create a transfer key. Paste it here with that server's address.
              The two servers then talk directly, so size is not a limit and nothing passes
              through this browser.
            </p>
            <div>
              <Label className="text-xs">Other server's address</Label>
              <Input placeholder="https://old-server.example.org" value={form.source_url}
                     onChange={set('source_url')} data-testid="pull-source-url" />
            </div>
            <div>
              <Label className="text-xs">Transfer key</Label>
              <Input placeholder="paste the key" value={form.transfer_key} className="font-mono text-xs"
                     onChange={set('transfer_key')} data-testid="pull-transfer-key" />
            </div>
            <div>
              <Label className="text-xs">Where it lands here</Label>
              <select
                className="w-full h-9 rounded-md border bg-background px-2 text-sm"
                value={target}
                onChange={(e) => { setTarget(e.target.value); setConfirmed(false); }}
                data-testid="pull-target-select"
              >
                <option value="">Create it as a new organisation</option>
                {orgs.map((o) => (
                  <option key={o.id} value={o.id}>Replace everything in “{o.name}”</option>
                ))}
              </select>
            </div>
            {target ? (
              <label className="flex items-start gap-2 text-xs cursor-pointer rounded-md border border-destructive/40 bg-destructive/5 p-2">
                <input type="checkbox" checked={confirmed} className="mt-0.5"
                       onChange={(e) => setConfirmed(e.target.checked)}
                       data-testid="pull-overwrite-confirm" />
                <span>
                  Everything currently in <strong>{orgs.find((o) => o.id === target)?.name}</strong> —
                  people, records and files — is deleted first and replaced by the copy coming
                  across. Its web addresses stay as they are. This cannot be undone.
                </span>
              </label>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-xs">Name here (optional)</Label>
                  <Input placeholder="same as before" value={form.name} onChange={set('name')} data-testid="pull-name" />
                </div>
                <div>
                  <Label className="text-xs">Web name / slug (optional)</Label>
                  <Input placeholder="same as before" value={form.slug} onChange={set('slug')} data-testid="pull-slug" />
                </div>
              </div>
            )}
            <p className="text-[11px] text-muted-foreground">
              {target
                ? 'Web addresses and the “main organisation” flag stay with this server — only the data inside is replaced.'
                : 'Web addresses and the “main organisation” flag stay behind — two servers must not claim the same address. Set them here afterwards.'}
            </p>
          </div>
        ) : (
          <div className="space-y-3 text-sm" data-testid="pull-progress">
            <p className="font-medium flex items-center gap-2">
              {job.status === 'running' && <Loader2 className="w-4 h-4 animate-spin" />}
              {job.status === 'done' && <CheckCircle2 className="w-4 h-4 text-green-600" />}
              {job.status === 'failed' && <AlertTriangle className="w-4 h-4 text-destructive" />}
              {job.organization_name}
              {job.current ? <span className="text-xs text-muted-foreground">· {job.current}</span> : null}
            </p>
            {job.cleared ? (
              <p className="text-xs text-muted-foreground" data-testid="pull-cleared">
                {job.cleared.toLocaleString()} existing record(s) cleared before the copy landed
              </p>
            ) : null}
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span>Records</span>
                <span data-testid="pull-rows">{(job.rows_done || 0).toLocaleString()} / {(job.rows_total || 0).toLocaleString()}</span>
              </div>
              <div className="h-2 rounded bg-muted overflow-hidden">
                <div className="h-full bg-primary transition-all" style={{ width: `${rowPct}%` }} />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span>Files</span>
                <span data-testid="pull-files">{job.files_done || 0} / {job.files_total || 0} · {fmtBytes(job.bytes_done)}</span>
              </div>
              <div className="h-2 rounded bg-muted overflow-hidden">
                <div className="h-full bg-primary transition-all" style={{ width: `${filePct}%` }} />
              </div>
            </div>
            {job.problem_count ? (
              <p className="text-xs text-amber-600" data-testid="pull-problems">
                {job.problem_count} item(s) reported a problem — first few: {(job.problems || []).slice(0, 3).join('; ')}
              </p>
            ) : null}
            {job.error ? <p className="text-xs text-destructive">{job.error}</p> : null}
            {job.status === 'running' ? (
              <p className="text-[11px] text-muted-foreground">
                Running on the server. Closing this window does not stop it.
              </p>
            ) : null}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="pull-close">Close</Button>
          {!job && (
            <Button onClick={start} disabled={starting} className="gap-2" data-testid="pull-start">
              <DownloadCloud className="w-4 h-4" /> {starting ? 'Checking…' : 'Start transfer'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
