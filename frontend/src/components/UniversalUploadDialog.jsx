import React, { useMemo, useState } from 'react';
import { Upload, FileText, Receipt, GraduationCap, Stethoscope, Table2, Check, X } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import api, { adminApi, childrenApi } from '../services/api';
import { toast } from 'sonner';

// Rule-based (NOT AI) file classification. Matches on filename keywords, then
// falls back to the extension. The user always confirms — and can override —
// before anything is filed.
const KINDS = {
  receipt: {
    label: 'Receipt / expense slip', icon: Receipt,
    blurb: 'Sent to Finance to be read and drafted as a journal entry for review.',
    words: ['receipt', 'rcpt', 'till', 'expense', 'invoice', 'inv-', 'bill'],
  },
  school_report: {
    label: 'School report card', icon: GraduationCap,
    blurb: 'Filed on the child\u2019s record as a school report.',
    words: ['report card', 'reportcard', 'report-card', 'school', 'term', 'grade', 'academic', 'exam result'],
    needsPerson: true, docType: 'school_report',
  },
  medical: {
    label: 'Medical / clinic document', icon: Stethoscope,
    blurb: 'Filed on the person\u2019s record as a medical document.',
    words: ['medical', 'clinic', 'health', 'immunis', 'immuniz', 'vaccin', 'lab', 'prescription'],
    needsPerson: true, docType: 'medical',
  },
  timesheet: {
    label: 'Timesheet workbook', icon: Table2,
    blurb: 'Uploaded to HR as submitted timesheets awaiting approval.',
    words: ['timesheet', 'time sheet', 'hours', 'attendance sheet'],
  },
  member_doc: {
    label: 'Person document', icon: FileText,
    blurb: 'Filed on the person\u2019s record.',
    words: [],
    needsPerson: true, docType: 'other',
  },
};

export function detectKind(file) {
  const name = (file?.name || '').toLowerCase();
  const ext = name.split('.').pop();
  for (const [kind, def] of Object.entries(KINDS)) {
    if (def.words.some(w => name.includes(w))) return kind;
  }
  if (['xlsx', 'xls'].includes(ext)) return 'timesheet';
  if (['jpg', 'jpeg', 'png', 'heic', 'webp'].includes(ext)) return 'receipt';
  return 'member_doc';
}

export default function UniversalUploadDialog({ open, onOpenChange }) {
  const [file, setFile] = useState(null);
  const [kind, setKind] = useState('receipt');
  const [people, setPeople] = useState([]);
  const [personId, setPersonId] = useState('');
  const [period, setPeriod] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const def = KINDS[kind] || KINDS.member_doc;
  const Icon = def.icon;

  const onPick = async (f) => {
    if (!f) return;
    setFile(f);
    const guess = detectKind(f);
    setKind(guess);
    if (KINDS[guess]?.needsPerson) loadPeople();
  };

  const loadPeople = async () => {
    if (people.length) return;
    try {
      const [dir, kids] = await Promise.all([
        adminApi.userDirectory({ limit: 300 }).catch(() => ({ data: [] })),
        childrenApi.list().catch(() => ({ data: [] })),
      ]);
      const users = (Array.isArray(dir.data) ? dir.data : dir.data?.users || []).map(u => ({ id: u.member_id || u.id, name: u.name, group: 'People' }));
      const children = (kids.data || []).map(c => ({ id: c.id, name: c.name, group: 'Children' }));
      setPeople([...children, ...users].filter(p => p.id && p.name));
    } catch { setPeople([]); }
  };

  const reset = () => { setFile(null); setPersonId(''); setPeriod(''); setBusy(false); setError(''); };

  const submit = async () => {
    setError('');
    if (!file) { setError('Choose a file first'); toast.error('Choose a file first'); return; }
    if (def.needsPerson && !personId) { setError('Pick who this document belongs to'); toast.error('Pick who this belongs to'); return; }
    if (kind === 'timesheet' && !period) { setError('Enter the pay period this sheet covers, e.g. 2026-09'); toast.error('Enter the pay period (e.g. 2026-09)'); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      if (kind === 'receipt') {
        const r = await api.post('/finance/receipts/scan', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
        toast.success(`Receipt sent to Finance${r.data?.vendor ? ' · ' + r.data.vendor : ''}`);
      } else if (kind === 'timesheet') {
        await api.post(`/hr/timesheets/upload?period=${encodeURIComponent(period)}`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
        toast.success('Timesheets uploaded — awaiting approval');
      } else {
        fd.append('doc_type', def.docType || 'other');
        fd.append('label', file.name);
        await api.post(`/members/${personId}/documents`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
        toast.success('Filed on the record');
      }
      reset();
      onOpenChange(false);
    } catch (e) {
      const msg = e?.response?.data?.detail || 'Upload failed';
      setError(typeof msg === 'string' ? msg : 'Upload failed');
      toast.error(typeof msg === 'string' ? msg : 'Upload failed');
      setBusy(false);
    }
  };

  const grouped = useMemo(() => people, [people]);

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) reset(); onOpenChange(o); }}>
      <DialogContent className="max-w-lg" data-testid="universal-upload-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Upload size={18} /> Upload anything</DialogTitle>
          <DialogDescription>Pick a file — we work out what it is, you confirm, and it goes to the right place.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <label className="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-border rounded-xl py-8 cursor-pointer hover:bg-accent/30 transition-colors">
            <Upload size={22} className="text-muted-foreground" />
            <span className="text-sm font-medium">{file ? file.name : 'Choose a photo, PDF or spreadsheet'}</span>
            <span className="text-xs text-muted-foreground">{file ? `${(file.size / 1024).toFixed(0)} KB` : 'Images · PDF · XLSX · CSV'}</span>
            <input type="file" className="hidden" accept="image/*,application/pdf,.xlsx,.xls,.csv"
              data-testid="universal-upload-input"
              onChange={e => onPick(e.target.files?.[0])} />
          </label>

          {file && (
            <>
              <div className="rounded-lg bg-accent/40 p-3 flex items-start gap-3" data-testid="universal-upload-detected">
                <Icon size={18} className="mt-0.5 text-primary" />
                <div className="min-w-0">
                  <div className="text-sm font-medium flex items-center gap-2">
                    <span>Looks like: {def.label}</span>
                    <Badge variant="secondary" className="text-[10px]">detected</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">{def.blurb}</p>
                </div>
              </div>

              <div className="space-y-1.5">
                <Label>If that&apos;s wrong, change it</Label>
                <Select value={kind} onValueChange={(v) => { setKind(v); if (KINDS[v]?.needsPerson) loadPeople(); }}>
                  <SelectTrigger data-testid="universal-upload-kind"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(KINDS).map(([k, d]) => <SelectItem key={k} value={k}>{d.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>

              {def.needsPerson && (
                <div className="space-y-1.5">
                  <Label>Who does it belong to?</Label>
                  <Select value={personId} onValueChange={setPersonId}>
                    <SelectTrigger data-testid="universal-upload-person"><SelectValue placeholder="Pick a person or child" /></SelectTrigger>
                    <SelectContent className="max-h-64">
                      {grouped.length === 0 && <div className="px-3 py-2 text-xs text-muted-foreground">Loading…</div>}
                      {grouped.map(p => <SelectItem key={p.id} value={p.id}>{p.name} · {p.group}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {kind === 'timesheet' && (
                <div className="space-y-1.5">
                  <Label>Pay period</Label>
                  <input className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                    placeholder="e.g. 2026-09" value={period} onChange={e => setPeriod(e.target.value)}
                    data-testid="universal-upload-period" />
                </div>
              )}

              {error && <p className="text-sm text-destructive" data-testid="universal-upload-error">{error}</p>}

              <div className="flex gap-2 pt-1">
                <Button variant="outline" className="flex-1 gap-1.5" onClick={() => { reset(); onOpenChange(false); }}><X size={14} /> Cancel</Button>
                <Button className="flex-1 gap-1.5" onClick={submit} disabled={busy} data-testid="universal-upload-confirm">
                  <Check size={14} /> {busy ? 'Uploading…' : 'Confirm & file it'}
                </Button>
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
