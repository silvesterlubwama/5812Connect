/**
 * ExternalSponsorAutocomplete — typeahead picker over /api/social-work/sponsors/external.
 *
 * Used in the case-detail dialog's Manual Sponsor section. As the social
 * worker types, hits the roster endpoint with ?search= and surfaces matches
 * inline. Selecting a row fills the sponsor_manual block in one shot — no
 * re-typing of email/phone/notes for repeat donors.
 *
 * Returns the selected guest (or just the typed name) via `onPick`.
 */
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Input } from './ui/input';
import { Card, CardContent } from './ui/card';
import api from '../services/api';

export default function ExternalSponsorAutocomplete({ value, onChange, onPick, placeholder, testid }) {
  const [open, setOpen] = useState(false);
  const [hits, setHits] = useState([]);
  const [loading, setLoading] = useState(false);
  const blurTimer = useRef(null);

  // Debounced search — 250ms after the user stops typing
  const fetchHits = useCallback(async (q) => {
    const term = (q || '').trim();
    if (term.length < 2) { setHits([]); return; }
    setLoading(true);
    try {
      const r = await api.get(`/social-work/sponsors/external?search=${encodeURIComponent(term)}`);
      setHits((r.data || []).slice(0, 8));
    } catch { setHits([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => fetchHits(value), 250);
    return () => clearTimeout(t);
  }, [value, fetchHits]);

  const pick = (g) => {
    onPick && onPick(g);
    setOpen(false);
    setHits([]);
  };

  return (
    <div className="relative">
      <Input
        className="h-8 text-xs"
        value={value || ''}
        onChange={e => { onChange(e.target.value); setOpen(true); }}
        onFocus={() => { if (hits.length) setOpen(true); }}
        // Delay close so click handlers on the dropdown items still fire
        onBlur={() => { blurTimer.current = setTimeout(() => setOpen(false), 200); }}
        placeholder={placeholder || 'Type to search existing sponsors…'}
        data-testid={testid}
        autoComplete="off"
      />
      {open && (hits.length > 0 || loading) && (
        <Card className="absolute z-50 top-9 left-0 right-0 max-h-64 overflow-y-auto shadow-md">
          <CardContent className="p-1">
            {loading && <p className="text-[11px] text-muted-foreground px-2 py-1">Searching…</p>}
            {hits.map(g => (
              <button
                key={g.id}
                type="button"
                className="w-full text-left px-2 py-1.5 rounded hover:bg-accent text-xs"
                onMouseDown={() => pick(g)}     /* mousedown beats parent's onBlur */
                data-testid={`sponsor-hit-${g.id}`}
              >
                <p className="font-medium">{g.name}</p>
                <p className="text-[10px] text-muted-foreground">
                  {g.email || g.phone || '—'}
                  {g.active_cases > 0 && <span className="ml-2 text-emerald-700">· {g.active_cases} active case{g.active_cases === 1 ? '' : 's'}</span>}
                </p>
              </button>
            ))}
            {!loading && hits.length === 0 && (
              <p className="text-[11px] text-muted-foreground px-2 py-1">No existing sponsors match — keep typing to register a new one.</p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
