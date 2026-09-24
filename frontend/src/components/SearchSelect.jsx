import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Input } from './ui/input';
import { ChevronDown, X } from 'lucide-react';

// Radix dialogs listen for Escape on the document in the CAPTURE phase, so a
// React handler can never stop them: pressing Escape to dismiss a suggestion
// list would close the whole entry form and lose everything typed. Dialogs that
// host a picker pass `onEscapeKeyDown={guardPickerEscape}` instead.
const openPickers = new Set();
export const isPickerOpen = () => openPickers.size > 0;
export const guardPickerEscape = (e) => { if (isPickerOpen()) e.preventDefault(); };
// Lets other pickers (e.g. VendorPicker) join the same Escape guard.
export const registerOpenPicker = (open) => {
  const token = {};
  if (open) openPickers.add(token);
  return () => openPickers.delete(token);
};

// Type-to-filter picker for finance entry. Options: [{ value, label, hint, keywords }].
// Behaves like a normal click-and-pick dropdown if you never type.
export const SearchSelect = ({
  value, onChange, options = [], placeholder = 'Search or pick…',
  testId, className = '', size = 'default', allowClear = false, emptyLabel = 'No match',
}) => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [cursor, setCursor] = useState(0);
  const box = useRef(null);
  const listRef = useRef(null);

  const selected = options.find(o => o.value === value);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter(o =>
      `${o.label} ${o.hint || ''} ${o.keywords || ''}`.toLowerCase().includes(q));
  }, [options, query]);

  useEffect(() => {
    const away = (e) => { if (box.current && !box.current.contains(e.target)) { setOpen(false); setQuery(''); } };
    document.addEventListener('mousedown', away);
    return () => document.removeEventListener('mousedown', away);
  }, []);

  useEffect(() => { setCursor(0); }, [query, open]);
  useEffect(() => {
    const token = {};
    if (open) openPickers.add(token);
    return () => openPickers.delete(token);
  }, [open]);
  useEffect(() => {
    if (!open || !listRef.current) return;
    listRef.current.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' });
  }, [cursor, open]);

  const pick = (opt) => { onChange(opt.value); setOpen(false); setQuery(''); };

  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setCursor(c => Math.min(c + 1, matches.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setCursor(c => Math.max(c - 1, 0)); }
    else if (e.key === 'Enter') { if (open && matches[cursor]) { e.preventDefault(); e.stopPropagation(); pick(matches[cursor]); } }
    else if (e.key === 'Escape') {
      if (open) {
        // Don't let Escape reach the dialog — closing the suggestion list must
        // not throw away the half-filled entry form behind it.
        e.preventDefault();
        e.stopPropagation();
        setOpen(false);
        setQuery('');
      }
    }
  };

  const h = size === 'sm' ? 'h-8 text-xs' : '';

  return (
    <div ref={box} className={`relative ${className}`}>
      <div className="relative">
        <Input
          data-testid={testId}
          className={`${h} pr-14`}
          autoComplete="off"
          value={open ? query : (selected?.label || '')}
          placeholder={selected ? selected.label : placeholder}
          onFocus={() => setOpen(true)}
          onClick={() => setOpen(true)}
          onChange={e => { setQuery(e.target.value); setOpen(true); }}
          onKeyDown={onKeyDown}
        />
        <div className="absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center gap-0.5">
          {allowClear && selected && !open && (
            <button type="button" className="p-1 text-muted-foreground hover:text-foreground"
              onClick={() => onChange('')} data-testid={testId ? `${testId}-clear` : undefined} aria-label="Clear">
              <X size={13} />
            </button>
          )}
          <ChevronDown size={14} className="text-muted-foreground pointer-events-none" />
        </div>
      </div>
      {open && (
        <div ref={listRef}
          className="absolute z-50 left-0 right-0 top-full mt-1 rounded-md border bg-popover shadow-md max-h-56 overflow-y-auto"
          data-testid={testId ? `${testId}-options` : undefined}>
          {matches.length === 0 && <p className="px-3 py-2 text-xs text-muted-foreground">{emptyLabel}</p>}
          {matches.map((o, i) => (
            <button key={o.value} type="button" data-active={i === cursor}
              className={`w-full text-left px-3 py-1.5 text-sm ${i === cursor ? 'bg-accent' : ''} ${o.value === value ? 'font-semibold' : ''}`}
              onMouseEnter={() => setCursor(i)}
              onClick={() => pick(o)}
              data-testid={testId ? `${testId}-option-${o.value}` : undefined}>
              {o.label}
              {o.hint && <span className="block text-[10px] text-muted-foreground">{o.hint}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default SearchSelect;
