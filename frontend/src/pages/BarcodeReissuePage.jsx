import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import api from '../services/api';
import { toast } from 'sonner';
import { Wrench, Barcode } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { Navigate } from 'react-router-dom';

/**
 * BarcodeReissuePage — admin tool to migrate legacy XX-* / var_* variant barcodes
 * to the new 5812-* format. Supports dry-run preview before committing.
 */
export default function BarcodeReissuePage() {
  const { user } = useAuth();
  const isAdmin = ['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director', 'Manager'].includes(user?.role);
  const [dryResult, setDryResult] = useState(null);
  const [applied, setApplied] = useState(null);
  const [running, setRunning] = useState(false);

  if (!isAdmin) return <Navigate to="/dashboard" replace />;

  const run = async (dry) => {
    setRunning(true);
    try {
      const res = await api.post('/admin/reissue-barcodes', { dry_run: !!dry });
      if (dry) {
        setDryResult(res.data);
        toast.info(`${res.data.candidates} variant(s) need migration`);
      } else {
        setApplied(res.data);
        setDryResult(null);
        toast.success(`Re-issued ${res.data.updated} barcode(s) to 5812-* format`);
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed');
    } finally { setRunning(false); }
  };

  const current = applied || dryResult;

  return (
    <div className="container mx-auto px-4 py-6 max-w-3xl space-y-5">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><Wrench size={22} /> Bulk Barcode Re-issue</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Migrate any legacy variant barcodes (<code className="bg-muted px-1 rounded text-[10px]">XX-...</code> or <code className="bg-muted px-1 rounded text-[10px]">var_...</code>) to the new <code className="bg-muted px-1 rounded text-[10px]">5812-{`{COUNTRY}{ABBR}-{DDMMYY}-V{NN}-{NNNN}`}</code> format.
        </p>
      </div>

      <Card className="rounded-xl">
        <CardHeader>
          <CardTitle className="text-base">How it works</CardTitle>
          <CardDescription className="text-xs">
            1. Click "Dry Run" to see which variants would be migrated. 2. Click "Apply" to commit. All changes are audit-logged in <code>db.barcode_migrations</code>.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => run(true)} disabled={running} data-testid="dry-run-btn">{running && !applied ? 'Scanning...' : 'Dry Run (preview)'}</Button>
            <Button onClick={() => { if (window.confirm('Re-issue all legacy barcodes to 5812-* format? This is reversible via the audit log.')) run(false); }} disabled={running} data-testid="apply-reissue-btn">
              <Barcode size={14} className="mr-1.5" /> {running && applied ? 'Applying...' : 'Apply Migration'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {current && (
        <Card className="rounded-xl">
          <CardHeader>
            <CardTitle className="text-base flex items-center justify-between">
              <span>{applied ? 'Migration Complete' : 'Dry Run Result'}</span>
              <Badge>{current.updated || current.candidates} variant(s)</Badge>
            </CardTitle>
            <CardDescription className="text-xs">
              {applied ? `Successfully migrated ${current.updated} barcodes.` : `${current.candidates} variants would be migrated. Click "Apply" above to commit.`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="border rounded-md overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-muted/40">
                  <tr><th className="text-left p-2">Product</th><th className="text-left p-2">Old</th><th className="text-left p-2">New</th></tr>
                </thead>
                <tbody className="divide-y">
                  {(current.mappings || []).map((m, i) => (
                    <tr key={i} data-testid={`mapping-${i}`}>
                      <td className="p-2 truncate">{m.product_name}</td>
                      <td className="p-2 font-mono text-muted-foreground">{m.old || '(empty)'}</td>
                      <td className="p-2 font-mono text-primary">{m.new}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {(current.mappings || []).length === 0 && (
                <p className="p-4 text-center text-muted-foreground text-sm">No legacy barcodes found — everything already on the new format ✓</p>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
