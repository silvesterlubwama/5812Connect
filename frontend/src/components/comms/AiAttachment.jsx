/**
 * A document the assistant pulled up, shown in the chat.
 *
 * The file sits behind an authenticated endpoint, so an <img src> would come
 * back empty — we fetch it as a blob with the session token and hand the
 * browser an object URL instead.
 */
import React, { useState } from 'react';
import { FileText, Image as ImageIcon, Download, Eye, CalendarClock } from 'lucide-react';
import { Button } from '../ui/button';
import api from '../../services/api';
import { toast } from 'sonner';

const TYPE_LABEL = {
  permit: 'Permit', certificate: 'Certificate', agreement: 'Agreement', contract: 'Contract',
  receipt: 'Receipt', policy: 'Policy', id: 'ID document', report: 'Report', other: 'Document',
};

/** The model writes **bold** and bullet lists; show them as such, not as asterisks. */
export const AiText = ({ text }) => {
  const lines = String(text || '').split('\n');
  const bold = (line) => line.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**')
      ? <strong key={i}>{part.slice(2, -2)}</strong>
      : <React.Fragment key={i}>{part}</React.Fragment>);
  return (
    <div className="text-sm space-y-1 break-words">
      {lines.map((line, i) => {
        const trimmed = line.trim();
        if (!trimmed) return <div key={i} className="h-1" />;
        const bullet = /^[*-]\s+/.test(trimmed);
        return bullet
          ? <div key={i} className="flex gap-1.5 pl-1"><span className="opacity-50">•</span><span>{bold(trimmed.replace(/^[*-]\s+/, ''))}</span></div>
          : <p key={i}>{bold(trimmed)}</p>;
      })}
    </div>
  );
};

export const AiAttachment = ({ att }) => {
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const isImage = (att.mime || '').startsWith('image/');

  const fetchBlob = async () => {
    const r = await api.get(`/org-documents/${att.document_id}/file`, { responseType: 'blob' });
    return URL.createObjectURL(r.data);
  };

  const open = async () => {
    setBusy(true);
    try {
      const url = await fetchBlob();
      if (isImage) setPreview(url);
      else window.open(url, '_blank', 'noopener');
    } catch (e) { toast.error(e?.response?.status === 404 ? 'That file is no longer stored' : 'Could not open the document'); }
    finally { setBusy(false); }
  };

  const download = async () => {
    setBusy(true);
    try {
      const url = await fetchBlob();
      const a = document.createElement('a');
      a.href = url;
      a.download = `${att.title || att.document_id}`.replace(/[^\w.\- ]+/g, '') + (isImage ? '' : '.pdf');
      a.click();
    } catch { toast.error('Download failed'); }
    finally { setBusy(false); }
  };

  return (
    <div className="mt-2 rounded-xl border bg-background/70 p-2.5" data-testid={`ai-attachment-${att.document_id}`}>
      <div className="flex items-start gap-2">
        <div className="p-1.5 rounded-lg bg-secondary shrink-0">
          {isImage ? <ImageIcon size={14} className="text-primary" /> : <FileText size={14} className="text-primary" />}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold truncate">{att.title}</p>
          <p className="text-[10px] text-muted-foreground">
            {TYPE_LABEL[att.doc_type] || 'Document'}
            {att.issuer ? ` · ${att.issuer}` : ''}
            {att.expires_on ? <span className="inline-flex items-center gap-0.5 ml-1"><CalendarClock size={9} /> expires {att.expires_on}</span> : ''}
          </p>
        </div>
      </div>
      {preview && <img src={preview} alt={att.title} className="mt-2 rounded-lg max-h-64 w-auto" data-testid={`ai-attachment-preview-${att.document_id}`} />}
      <div className="flex gap-1.5 mt-2">
        <Button size="sm" variant="outline" className="h-7 text-[11px] gap-1" onClick={open} disabled={busy} data-testid={`ai-attachment-open-${att.document_id}`}>
          <Eye size={11} /> {isImage ? 'Show it' : 'Open'}
        </Button>
        <Button size="sm" variant="ghost" className="h-7 text-[11px] gap-1" onClick={download} disabled={busy} data-testid={`ai-attachment-download-${att.document_id}`}>
          <Download size={11} /> Download
        </Button>
      </div>
    </div>
  );
};

export default AiAttachment;
