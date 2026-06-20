/**
 * ChildDocumentsPanel — typed file checklist.
 *
 * Renders the canonical 11-item child-file checklist (OVCMIS Form 008, LC1
 * Letter, Guardian ID, school reports, sponsor letters, etc.) as upload slots.
 * Each upload tags the file with `doc_type` so the profile-bundle ZIP can
 * group + label them and the checklist on the bundle's INDEX.md shows what's
 * still missing.
 *
 * Backend: GET/POST /api/children/{id}/file-doc-types + /file-docs.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Upload, FileText, RefreshCw, CheckCircle2, XCircle, Download, Trash2 } from 'lucide-react';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import api from '../services/api';
import { toast } from 'sonner';

export default function ChildDocumentsPanel({ child }) {
  const [types, setTypes] = useState([]);
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [bundling, setBundling] = useState(false);

  const refresh = useCallback(async () => {
    if (!child?.id) return;
    setLoading(true);
    try {
      const [t, d] = await Promise.all([
        api.get(`/children/${child.id}/file-doc-types`),
        api.get(`/children/${child.id}/file-docs`),
      ]);
      setTypes(t.data || []);
      setDocs(d.data || []);
    } catch (e) { console.warn(e?.message || e); }
    finally { setLoading(false); }
  }, [child?.id]);

  useEffect(() => { refresh(); }, [refresh]);

  const upload = async (docType, file) => {
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    fd.append('doc_type', docType);
    try {
      await api.post(`/children/${child.id}/file-docs`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success('Document uploaded');
      await refresh();
    } catch (e) { toast.error(e.response?.data?.detail || 'Upload failed'); }
  };

  const downloadBundle = async () => {
    setBundling(true);
    try {
      const r = await api.get(`/children/${child.id}/profile-bundle`, { responseType: 'blob' });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url;
      const safe = (child.name || 'child').replace(/\s+/g, '_');
      a.download = `${safe}-file-bundle.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
      toast.success('Bundle downloaded');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Bundle download failed');
    } finally { setBundling(false); }
  };

  return (
    <div className="space-y-3" data-testid="child-docs-panel">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="text-xs text-muted-foreground flex-1 min-w-0">
          Upload scans for the items that should live in this child&apos;s file. Each upload is tagged
          and shows up in the whole-profile bundle for offline / official handoff.
        </p>
        <Button size="sm" onClick={downloadBundle} disabled={bundling} data-testid="child-docs-bundle-btn">
          <Download size={12} className="mr-1" /> {bundling ? 'Bundling…' : 'Download profile bundle (ZIP)'}
        </Button>
        <Button size="sm" variant="ghost" onClick={refresh} disabled={loading} data-testid="child-docs-refresh">
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
        </Button>
      </div>

      {/* Checklist coverage */}
      <Card className="rounded-xl shadow-soft">
        <CardContent className="p-3 space-y-1.5">
          {types.map(t => (
            <div key={t.key} className="flex items-center gap-3" data-testid={`doctype-row-${t.key}`}>
              {t.count > 0 ? (
                <CheckCircle2 size={14} className="text-emerald-600 shrink-0" />
              ) : (
                <XCircle size={14} className="text-muted-foreground/40 shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium truncate">{t.label}</p>
                {t.count > 0 && <p className="text-[10px] text-muted-foreground">{t.count} document{t.count === 1 ? '' : 's'} on file</p>}
              </div>
              <label className="inline-flex shrink-0">
                <Button size="sm" variant="outline" className="h-7 text-[11px]" asChild>
                  <span><Upload size={11} className="mr-1" /> Upload</span>
                </Button>
                <Input
                  type="file"
                  accept="application/pdf,image/*"
                  className="hidden"
                  onChange={e => upload(t.key, e.target.files?.[0])}
                  data-testid={`doctype-upload-${t.key}`}
                />
              </label>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Uploaded list */}
      {docs.length > 0 && (
        <div className="space-y-1.5" data-testid="child-docs-list">
          <Label className="text-xs">Uploaded documents ({docs.length})</Label>
          {docs.map(d => (
            <Card key={d.id} className="rounded-lg" data-testid={`doc-row-${d.id}`}>
              <CardContent className="p-2 flex items-center gap-2 flex-wrap">
                <FileText size={14} className="text-muted-foreground shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium truncate">{d.doc_label || d.caption}</p>
                  <p className="text-[10px] text-muted-foreground truncate">
                    {d.file_name || '—'} · {((d.file_size || 0) / 1024).toFixed(0)} KB
                    {d.created_by_name && ` · uploaded by ${d.created_by_name}`}
                    {d.created_at && ` · ${(d.created_at || '').slice(0, 10)}`}
                  </p>
                </div>
                <Badge variant="outline" className="text-[10px]">{d.doc_type || 'other'}</Badge>
                {d.file_url && (
                  <a href={d.file_url} target="_blank" rel="noreferrer">
                    <Button size="sm" variant="ghost" className="h-7 text-[11px]">View</Button>
                  </a>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
