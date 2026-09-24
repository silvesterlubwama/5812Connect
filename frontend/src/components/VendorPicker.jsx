import React, { useState, useEffect, useRef } from 'react';
import { Input } from './ui/input';
import { Plus } from 'lucide-react';
import { vendorsApi } from '../services/api';
import { registerOpenPicker } from './SearchSelect';

// Vendor box that matches existing vendors as you type. Free text is still
// allowed — a new name is offered explicitly as "Add … as a new vendor" so
// nobody creates a duplicate vendor by accident.
export const VendorPicker = ({
  value, onChange, placeholder = 'Start typing a vendor name…',
  testId = 'vendor-picker', size = 'default', onPick,
}) => {
  const [matches, setMatches] = useState([]);
  const [open, setOpen] = useState(false);
  const [exact, setExact] = useState(false);
  const box = useRef(null);
  const timer = useRef(null);

  useEffect(() => {
    const away = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', away);
    return () => { document.removeEventListener('mousedown', away); clearTimeout(timer.current); };
  }, []);

  const typed = (value || '').trim();
  const showNew = open && typed.length >= 2 && !exact;

  // Only claim the Escape key while suggestions are actually on screen. The
  // dialog autofocuses this input, so registering on focus alone made Escape
  // stop closing the dialog before the user had typed anything.
  const listShowing = open && (matches.length > 0 || showNew);
  useEffect(() => registerOpenPicker(listShowing), [listShowing]);

  const search = (q) => {
    clearTimeout(timer.current);
    if (!q || q.trim().length < 1) { setMatches([]); setExact(false); return; }
    timer.current = setTimeout(async () => {
      try {
        const r = await vendorsApi.suggest(q.trim());
        const list = r.data || [];
        setMatches(list);
        setExact(list.some(v => (v.name || '').toLowerCase() === q.trim().toLowerCase()));
      } catch { setMatches([]); setExact(false); }
    }, 180);
  };

  return (
    <div ref={box} className="relative">
      <Input
        data-testid={testId}
        className={size === 'sm' ? 'h-8 text-xs' : ''}
        value={value || ''}
        placeholder={placeholder}
        autoComplete="off"
        onFocus={() => { setOpen(true); search(value); }}
        onKeyDown={e => {
          // Escape closes the suggestions, it must not close the dialog behind.
          if (e.key === 'Escape' && open) { e.preventDefault(); e.stopPropagation(); setOpen(false); }
        }}
        onChange={e => { onChange(e.target.value); setOpen(true); search(e.target.value); }}
      />
      {open && (matches.length > 0 || showNew) && (
        <div className="absolute z-50 left-0 right-0 top-full mt-1 rounded-md border bg-popover shadow-md max-h-48 overflow-y-auto"
          data-testid={`${testId}-options`}>
          {matches.map(v => (
            <button key={v.id} type="button"
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-accent"
              onClick={() => { onChange(v.name); onPick?.(v); setOpen(false); setMatches([]); }}
              data-testid={`${testId}-option-${v.id}`}>
              <span className="font-medium">{v.name}</span>
              {(v.email || v.phone || v.category) && (
                <span className="block text-[10px] text-muted-foreground">
                  {[v.category, v.phone, v.email].filter(Boolean).join(' · ')}
                </span>
              )}
            </button>
          ))}
          {showNew && (
            <button type="button"
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-accent border-t flex items-center gap-1.5 text-emerald-700"
              onClick={() => { setOpen(false); setMatches([]); }}
              data-testid={`${testId}-add-new`}>
              <Plus size={12} /> Add “{typed}” as a new vendor
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default VendorPicker;
