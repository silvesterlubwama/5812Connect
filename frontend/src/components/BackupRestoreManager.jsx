/**
 * BackupRestoreManager — admin card to export the full app to a single .tar.gz
 * and to restore one. Used for moving data between deployments (preview → prod,
 * cloud → self-hosted Tauri, etc).
 *
 * Safety:
 *   • Restore re-asks for the admin password (re-verified by the backend).
 *   • A pre-restore snapshot is auto-saved on the server; admins can download it
 *     back if a restore goes sideways.
 *   • Dry-run option parses + reports counts without writing anything.
 */
import React, { useEffect, useState } from 'react';
import { Download, Upload, Database, Clock, Eye, AlertTriangle, CheckCircle2 } from 'lucide-react';
import api from '../services/api';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { toast } from 'sonner';

const _fmtBytes = (n) => {
  if (!n) return '0 B';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
};

export default function BackupRestoreManager() {
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState(null);
  const [snapshots, setSnapshots] = useState([]);
  const [includeAudit, setIncludeAudit] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importFile, setImportFile] = useState(null);
  const [importMode, setImportMode] = useState('merge');
  const [importPassword, setImportPassword] = useState('');
  const [dryRun, setDryRun] = useState(true);
  const [report, setReport] = useState(null);

  const load = async () => {
    try {
      const [p, s] = await Promise.all([
        api.get('/admin/backup/preview'),
        api.get('/admin/backup/snapshots'),
      ]);
      setPreview(p.data);
      setSnapshots(s.data || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to load backup info');
    }
  };
  useEffect(() => { if (open) load(); }, [open]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const fd = new FormData();
      fd.append('include_audit', includeAudit ? 'true' : 'false');
      const r = await api.post('/admin/backup/export', fd, { responseType: 'blob' });
      const blob = r.data instanceof Blob ? r.data : new Blob([r.data], { type: 'application/gzip' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      a.href = url;
      a.download = `5812connect-backup-${stamp}.tar.gz`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success(`Backup downloaded (${_fmtBytes(blob.size)})`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Export failed');
    } finally { setExporting(false); }
  };

  const handleImport = async () => {
    if (!importFile) { toast.error('Select a .tar.gz file first'); return; }
    if (!importPassword) { toast.error('Re-enter your admin password'); return; }
    if (importMode === 'replace' && !dryRun && !window.confirm(
      'REPLACE mode will DROP each collection in the backup before re-inserting its rows. ' +
      'A pre-restore snapshot will be auto-saved so you can roll back. Continue?'
    )) return;
    setImporting(true); setReport(null);
    try {
      const fd = new FormData();
      fd.append('file', importFile);
      fd.append('mode', importMode);
      fd.append('admin_password', importPassword);
      fd.append('dry_run', dryRun ? 'true' : 'false');
      fd.append('include_audit', 'false');
      const r = await api.post('/admin/backup/import', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setReport(r.data);
      const totals = Object.values(r.data.collections || {}).reduce(
        (acc, v) => ({
          read: acc.read + (v.read || 0),
          inserted: acc.inserted + (v.inserted || 0),
          updated: acc.updated + (v.updated || 0),
          errors: acc.errors + (v.errors || 0),
        }),
        { read: 0, inserted: 0, updated: 0, errors: 0 },
      );
      toast.success(`${dryRun ? '[DRY-RUN] Would import' : 'Imported'} ${totals.read} docs · ${totals.inserted} new · ${totals.updated} updated · ${totals.errors} errors`, { duration: 8000 });
      setImportPassword('');
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Import failed');
    } finally { setImporting(false); }
  };

  const downloadSnapshot = async (filename) => {
    try {
      const r = await api.get(`/admin/backup/snapshots/${filename}/download`, { responseType: 'blob' });
      const blob = r.data instanceof Blob ? r.data : new Blob([r.data], { type: 'application/gzip' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Snapshot download failed');
    }
  };

  return (
    <>
      <Card className="rounded-xl mt-4 cursor-pointer hover:border-primary/40" onClick={() => setOpen(true)} data-testid="backup-restore-card">
        <CardContent className="p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Database size={18} className="text-primary" />
            <div>
              <p className="font-medium text-sm">Backup &amp; Restore</p>
              <p className="text-xs text-muted-foreground">
                Export the full app (every collection + uploads) as a single .tar.gz, or restore one. Used to move data between preview / production / self-hosted deployments.
              </p>
            </div>
          </div>
          <Button size="sm" variant="outline">Open</Button>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto" data-testid="backup-restore-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Database size={16} /> Backup &amp; Restore</DialogTitle>
            <DialogDescription className="text-xs">
              Cross-environment data migration. Exports include every Mongo collection (in JSONL) and every file under <code>/uploads</code>. Restores re-ask for the admin password and auto-save a pre-restore snapshot.
            </DialogDescription>
          </DialogHeader>

          {/* PREVIEW SUMMARY */}
          {preview && (
            <div className="grid grid-cols-3 gap-2 p-3 rounded-lg bg-muted/40 border text-center" data-testid="backup-preview-summary">
              <div><p className="text-2xl font-bold">{preview.total_collections}</p><p className="text-[10px] uppercase text-muted-foreground">Collections</p></div>
              <div><p className="text-2xl font-bold">{preview.total_docs?.toLocaleString()}</p><p className="text-[10px] uppercase text-muted-foreground">Documents</p></div>
              <div><p className="text-2xl font-bold">{_fmtBytes(preview.uploads_bytes)}</p><p className="text-[10px] uppercase text-muted-foreground">{preview.uploads_files} upload file{preview.uploads_files === 1 ? '' : 's'}</p></div>
            </div>
          )}

          {/* EXPORT */}
          <section className="space-y-3 mt-4 p-3 rounded-lg border" data-testid="backup-export-section">
            <h3 className="text-sm font-semibold flex items-center gap-2"><Download size={14} className="text-emerald-600" /> Export Backup</h3>
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input type="checkbox" checked={includeAudit} onChange={e => setIncludeAudit(e.target.checked)} data-testid="backup-include-audit" />
              <span>Include audit trail collections (recommended for compliance, increases file size)</span>
            </label>
            <Button onClick={handleExport} disabled={exporting} className="gap-2" data-testid="backup-export-btn">
              <Download size={14} /> {exporting ? 'Exporting…' : 'Download backup'}
            </Button>
          </section>

          {/* IMPORT */}
          <section className="space-y-3 mt-4 p-3 rounded-lg border border-amber-200 dark:border-amber-900/40 bg-amber-50/40 dark:bg-amber-950/20" data-testid="backup-import-section">
            <h3 className="text-sm font-semibold flex items-center gap-2"><Upload size={14} className="text-amber-700" /> Restore from Backup</h3>
            <div className="space-y-2">
              <Label className="text-xs">Backup file (.tar.gz from /export)</Label>
              <Input type="file" accept=".tar.gz,application/gzip,application/x-gzip" onChange={e => setImportFile(e.target.files?.[0] || null)} data-testid="backup-import-file" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Mode</Label>
                <select className="h-9 w-full rounded border bg-background px-2 text-sm" value={importMode} onChange={e => setImportMode(e.target.value)} data-testid="backup-import-mode">
                  <option value="merge">Merge — upsert per id (safest)</option>
                  <option value="replace">Replace — drop target collections first</option>
                </select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Admin password (re-verify)</Label>
                <Input type="password" value={importPassword} onChange={e => setImportPassword(e.target.value)} placeholder="Your current password" data-testid="backup-import-password" />
              </div>
            </div>
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input type="checkbox" checked={dryRun} onChange={e => setDryRun(e.target.checked)} data-testid="backup-import-dryrun" />
              <span><Eye size={11} className="inline mr-1" /> Dry-run (parse + report counts without writing)</span>
            </label>
            {importMode === 'replace' && !dryRun && (
              <div className="flex items-start gap-2 p-2 rounded bg-rose-100 dark:bg-rose-950/30 border border-rose-300 dark:border-rose-900/50 text-[11px] text-rose-900 dark:text-rose-200">
                <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                Replace mode drops each collection in the backup before re-inserting its docs. A pre-restore snapshot will be auto-saved.
              </div>
            )}
            <Button onClick={handleImport} disabled={importing || !importFile || !importPassword} className="gap-2" data-testid="backup-import-btn" variant={dryRun ? 'outline' : 'default'}>
              <Upload size={14} /> {importing ? 'Importing…' : (dryRun ? 'Dry-run import' : 'Import backup')}
            </Button>

            {report && (
              <div className="mt-3 text-[11px] rounded border bg-card p-3" data-testid="backup-import-report">
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircle2 size={13} className={report.errors.length === 0 ? 'text-emerald-600' : 'text-amber-600'} />
                  <p className="font-semibold">{report.dry_run ? 'DRY-RUN report' : 'Import complete'}</p>
                  <Badge variant="outline" className="text-[9px] ml-auto">{report.mode}</Badge>
                </div>
                <div className="grid grid-cols-4 gap-2 mb-2">
                  {Object.entries({
                    read: Object.values(report.collections || {}).reduce((a, v) => a + (v.read || 0), 0),
                    inserted: Object.values(report.collections || {}).reduce((a, v) => a + (v.inserted || 0), 0),
                    updated: Object.values(report.collections || {}).reduce((a, v) => a + (v.updated || 0), 0),
                    errors: Object.values(report.collections || {}).reduce((a, v) => a + (v.errors || 0), 0),
                  }).map(([k, v]) => (
                    <div key={k} className="text-center">
                      <p className="text-base font-bold">{v.toLocaleString()}</p>
                      <p className="text-[9px] uppercase text-muted-foreground">{k}</p>
                    </div>
                  ))}
                </div>
                {report.snapshot_path && (
                  <p className="text-[10px] text-muted-foreground italic">Rollback snapshot: <code className="bg-muted px-1 rounded">{report.snapshot_path.split('/').pop()}</code></p>
                )}
                {report.errors?.length > 0 && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-amber-700 dark:text-amber-300">{report.errors.length} error{report.errors.length === 1 ? '' : 's'} — show</summary>
                    <ul className="mt-1 ml-3 space-y-0.5 text-[10px] text-muted-foreground">
                      {report.errors.slice(0, 30).map((e, i) => <li key={i}>· {e.slice(0, 200)}</li>)}
                      {report.errors.length > 30 && <li>· …and {report.errors.length - 30} more</li>}
                    </ul>
                  </details>
                )}
              </div>
            )}
          </section>

          {/* SNAPSHOTS */}
          {snapshots.length > 0 && (
            <section className="space-y-2 mt-4 p-3 rounded-lg border">
              <h3 className="text-sm font-semibold flex items-center gap-2"><Clock size={14} className="text-blue-600" /> Pre-restore Snapshots</h3>
              <p className="text-[11px] text-muted-foreground">Auto-saved before each restore. Download to roll back if a restore goes sideways.</p>
              <div className="space-y-1.5">
                {snapshots.map(s => (
                  <div key={s.filename} className="flex items-center justify-between p-2 rounded border bg-card" data-testid={`backup-snapshot-${s.filename}`}>
                    <div>
                      <p className="text-xs font-mono">{s.filename}</p>
                      <p className="text-[10px] text-muted-foreground">{new Date(s.modified_at).toLocaleString()} · {_fmtBytes(s.size_bytes)}</p>
                    </div>
                    <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={() => downloadSnapshot(s.filename)}>
                      <Download size={11} className="mr-1" /> Download
                    </Button>
                  </div>
                ))}
              </div>
            </section>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
