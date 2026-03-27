import React, { useRef } from 'react';
import { Upload, Download } from 'lucide-react';
import { Button } from '../ui/button';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog';

export function UserImportDialog({ open, onOpenChange, importJson, setImportJson, importLoading, importResult, onImport, onImportFile }) {
  const importFileRef = useRef(null);
  return (
    <Dialog open={open} onOpenChange={o => { onOpenChange(o); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Import Users</DialogTitle>
          <DialogDescription>Upload a CSV or paste JSON array. Each row: name, email, role, phone, department, location_id</DialogDescription>
        </DialogHeader>
        {importResult ? (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="p-3 bg-green-50 rounded-lg border border-green-200"><p className="text-2xl font-bold text-green-700">{importResult.created}</p><p className="text-xs text-muted-foreground">Created</p></div>
              <div className="p-3 bg-amber-50 rounded-lg border border-amber-200"><p className="text-2xl font-bold text-amber-700">{importResult.skipped}</p><p className="text-xs text-muted-foreground">Skipped</p></div>
              <div className="p-3 bg-red-50 rounded-lg border border-red-200"><p className="text-2xl font-bold text-red-700">{importResult.errors?.length || 0}</p><p className="text-xs text-muted-foreground">Errors</p></div>
            </div>
            {importResult.errors?.length > 0 && <div className="text-xs text-red-600 bg-red-50 rounded-lg p-3 space-y-1">{importResult.errors.map((e, i) => <p key={i}>{e}</p>)}</div>}
            <Button className="w-full" onClick={() => onOpenChange(false)}>Done</Button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label className="text-xs">JSON / CSV Data</Label>
                <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" onClick={() => importFileRef.current?.click()}><Upload size={11} /> Upload CSV/JSON</Button>
                <input ref={importFileRef} type="file" className="hidden" accept=".csv,.json" onChange={onImportFile} />
              </div>
              <Textarea rows={6} placeholder={'[{"name":"Jane Doe","email":"jane@example.com","role":"Staff","phone":"+256..."},...]'}
                className="text-xs font-mono" value={importJson} onChange={e => setImportJson(e.target.value)} data-testid="import-json-input" />
            </div>
            <div className="text-xs text-muted-foreground bg-muted/50 rounded-lg p-3 space-y-1">
              <p className="font-medium">CSV column headers:</p>
              <p className="font-mono">name, email, role, phone, department, location_id</p>
              <p className="mt-1">All imported users are also added to the People directory.</p>
            </div>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>Cancel</Button>
              <Button className="flex-1 gap-2" onClick={onImport} disabled={importLoading || !importJson.trim()} data-testid="import-users-btn">
                <Download size={14} /> {importLoading ? 'Importing...' : 'Import Users'}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
