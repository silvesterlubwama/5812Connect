/**
 * Managers drop the organisation's paperwork straight into the AI chat.
 *
 * The file is read once on the way in — the assistant names it, pulls out the
 * expiry date and writes a summary — so later anyone allowed to see it can just
 * ask "when does our NGO permit expire?".
 */
import React, { useRef, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Paperclip, FileUp } from 'lucide-react';
import api from '../../services/api';
import { toast } from 'sonner';

const LEVELS = [
  { value: '5', label: 'Every staff member' },
  { value: '6', label: 'Coordinators and above' },
  { value: '7', label: 'Managers and above' },
  { value: '8', label: 'Directors and above' },
  { value: '10', label: 'Admins only' },
];
const TYPES = ['permit', 'certificate', 'agreement', 'contract', 'receipt', 'policy', 'id', 'report', 'other'];

export const AiDocumentUpload = ({ onFiled }) => {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState(null);
  const [form, setForm] = useState({ title: '', doc_type: '', min_level: '5', expires_on: '' });
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);

  const pick = (f) => {
    if (!f) return;
    setFile(f);
    setForm(s => ({ ...s, title: s.title || f.name.replace(/\.[^.]+$/, '') }));
    setOpen(true);
  };

  const submit = async () => {
    if (!file) return;
    setBusy(true);
    const fd = new FormData();
    fd.append('file', file);
    if (form.title) fd.append('title', form.title);
    if (form.doc_type) fd.append('doc_type', form.doc_type);
    if (form.expires_on) fd.append('expires_on', form.expires_on);
    fd.append('min_level', form.min_level);
    try {
      const r = await api.post('/org-documents', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success(`Filed: ${r.data.title}`);
      setOpen(false);
      setFile(null);
      setForm({ title: '', doc_type: '', min_level: '5', expires_on: '' });
      onFiled?.(r.data);
    } catch (e) { toast.error(e?.response?.data?.detail || 'Could not file that document'); }
    finally { setBusy(false); }
  };

  return (
    <>
      <input ref={inputRef} type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png,.webp,.txt,.csv"
        onChange={e => pick(e.target.files?.[0])} data-testid="ai-doc-file-input" />
      <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => inputRef.current?.click()} data-testid="ai-doc-upload-btn">
        <Paperclip size={12} /> Add document
      </Button>

      <Dialog open={open} onOpenChange={(o) => { if (!o) { setOpen(false); setFile(null); } }}>
        <DialogContent className="max-w-md" data-testid="ai-doc-upload-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><FileUp size={16} /> File this with the organisation</DialogTitle>
            <DialogDescription className="text-xs">
              The assistant reads it once and remembers it. Choose who may see it — anyone below that level won't know it exists.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-1">
            <p className="text-xs text-muted-foreground truncate">{file?.name} · {Math.round((file?.size || 0) / 1024)} KB</p>
            <div className="space-y-1">
              <Label className="text-xs">Title</Label>
              <Input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} className="h-8 text-xs"
                placeholder="NGO operating permit 2026" data-testid="ai-doc-title" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-xs">What is it?</Label>
                <Select value={form.doc_type} onValueChange={v => setForm({ ...form, doc_type: v })}>
                  <SelectTrigger className="h-8 text-xs" data-testid="ai-doc-type"><SelectValue placeholder="Let the AI decide" /></SelectTrigger>
                  <SelectContent>
                    {TYPES.map(t => <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Expires on</Label>
                <Input type="date" value={form.expires_on} onChange={e => setForm({ ...form, expires_on: e.target.value })}
                  className="h-8 text-xs" data-testid="ai-doc-expiry" />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Who may see it</Label>
              <Select value={form.min_level} onValueChange={v => setForm({ ...form, min_level: v })}>
                <SelectTrigger className="h-8 text-xs" data-testid="ai-doc-level"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {LEVELS.map(l => <SelectItem key={l.value} value={l.value}>{l.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-2 pt-1">
              <Button variant="ghost" className="flex-1" onClick={() => { setOpen(false); setFile(null); }}>Cancel</Button>
              <Button className="flex-1" onClick={submit} disabled={busy} data-testid="ai-doc-submit">
                {busy ? 'Reading it…' : 'File it'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default AiDocumentUpload;
