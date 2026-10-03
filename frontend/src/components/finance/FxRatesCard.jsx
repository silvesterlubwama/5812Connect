import React, { useEffect, useState } from 'react';
import { Repeat, Save } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import api from '../../services/api';
import { toast } from 'sonner';

const COMMON = ['USD', 'EUR', 'GBP', 'KES', 'TZS', 'RWF', 'UGX'];

// Rates set once here are used by every report, so nobody has to retype a rate
// on each export (iter375). A report can still override for a single export.
export const FxRatesCard = ({ canEdit }) => {
  const [base, setBase] = useState('UGX');
  const [rates, setRates] = useState({});
  const [meta, setMeta] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get('/finance/fx/rates')
      .then(r => {
        setBase(r.data.base || 'UGX');
        setRates(r.data.rates || {});
        setMeta({ updated_at: r.data.updated_at, updated_by: r.data.updated_by });
      })
      .catch(() => { /* non-admins simply see blanks */ });
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const res = await api.put('/finance/fx/rates', { base, rates });
      setRates(res.data.rates || {});
      setMeta({ updated_at: res.data.updated_at, updated_by: res.data.updated_by });
      toast.success('Exchange rates saved — every report can use them now');
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not save rates'); }
    finally { setSaving(false); }
  };

  const [newCode, setNewCode] = useState('');
  const [extra, setExtra] = useState([]);
  const codes = Array.from(new Set([...COMMON, ...Object.keys(rates), ...extra])).filter(c => c !== base);

  const addCurrency = () => {
    const code = newCode.trim().toUpperCase();
    if (!/^[A-Z]{3,4}$/.test(code)) { toast.error('Use a 3-letter currency code, e.g. CAD'); return; }
    if (code === base) { toast.error(`${code} is already the base currency`); return; }
    setExtra(e => [...e, code]);
    setNewCode('');
  };

  return (
    <Card data-testid="fx-rates-card">
      <CardHeader><CardTitle className="text-base flex items-center gap-2"><Repeat size={16} /> Exchange rates</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2 max-w-[180px]">
          <Label>Base currency</Label>
          <Input data-testid="fx-base" value={base} disabled={!canEdit}
            onChange={e => setBase(e.target.value.trim().toUpperCase().slice(0, 4))} />
          <p className="text-xs text-muted-foreground">The currency your books are kept in.</p>
        </div>

        <div>
          <Label className="text-xs uppercase tracking-wide text-muted-foreground">
            1 {base || 'base'} equals…
          </Label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-2">
            {codes.map(code => (
              <div key={code} className="space-y-1">
                <Label className="text-xs">{code}</Label>
                <Input type="number" step="0.000001" placeholder="not set" disabled={!canEdit}
                  data-testid={`fx-rate-${code}`}
                  value={rates[code] ?? ''}
                  onChange={e => {
                    const v = e.target.value;
                    setRates(r => {
                      const next = { ...r };
                      if (v === '') delete next[code]; else next[code] = v;
                      return next;
                    });
                  }} />
              </div>
            ))}
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            Leave a currency blank to hide it from reports. Example: 1 UGX = 0.00027 USD.
          </p>
        </div>

        <div className="flex items-end gap-2">
          <div className="space-y-1">
            <Label className="text-xs">Add another currency</Label>
            <Input className="w-32" placeholder="e.g. CAD" value={newCode} disabled={!canEdit}
              data-testid="fx-new-code"
              onChange={e => setNewCode(e.target.value.toUpperCase().slice(0, 4))}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addCurrency(); } }} />
          </div>
          <Button variant="outline" onClick={addCurrency} disabled={!canEdit} data-testid="fx-add-currency">Add</Button>
        </div>

        {meta.updated_at && (
          <p className="text-xs text-muted-foreground" data-testid="fx-updated">
            Last changed {new Date(meta.updated_at).toLocaleString()}{meta.updated_by ? ` by ${meta.updated_by}` : ''}
          </p>
        )}
        {canEdit && (
          <Button onClick={save} disabled={saving} data-testid="fx-save-btn">
            <Save size={14} className="mr-1.5" />{saving ? 'Saving…' : 'Save rates'}
          </Button>
        )}
      </CardContent>
    </Card>
  );
};

export default FxRatesCard;
