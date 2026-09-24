import React, { useState, useMemo, useRef, useEffect } from 'react';
import { Input } from './ui/input';
import { Check, ChevronDown, X } from 'lucide-react';

// Type-to-find replacement for a long <Select> of people that already exist
// (staff, board members, subjects). Nothing is ever created here — it only
// narrows a list you already loaded, so it stays usable at 200+ records.
//
//   options   [{ id, name, hint? }]
//   value     selected id
//   onChange  (id, option) => void
export const StaffPicker = ({
  options = [], value = '', onChange, placeholder = 'Type a name to find them…',
  testId = 'staff-picker', disabled = false, allowClear = true, emptyLabel = 'Nobody matches that name',
}) => {
  const [term, setTerm] = useState('');
  const [open, setOpen] = useState(false);
  const box = useRef(null);

  useEffect(() => {
    const away = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', away);
    return () => document.removeEventListener('mousedown', away);
  }, []);

  const selected = useMemo(() => options.find(o => o.id === value), [options, value]);
  const matches = useMemo(() => {
    const q = term.trim().toLowerCase();
    const pool = q
      ? options.filter(o => `${o.name || ''} ${o.hint || ''}`.toLowerCase().includes(q))
      : options;
    return pool.slice(0, 40);
  }, [options, term]);

  return (
    <div ref={box} className="relative">
      <div className="relative">
        <Input
          data-testid={testId}
          disabled={disabled}
          autoComplete="off"
          value={open ? term : (selected?.name || '')}
          placeholder={selected ? selected.name : placeholder}
          onFocus={() => { setOpen(true); setTerm(''); }}
          onChange={e => { setTerm(e.target.value); setOpen(true); }}
          onKeyDown={e => { if (e.key === 'Escape' && open) { e.preventDefault(); e.stopPropagation(); setOpen(false); } }}
        />
        <span className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1 text-muted-foreground">
          {allowClear && selected && !open && (
            <button type="button" onClick={() => onChange('', null)} data-testid={`${testId}-clear`}><X size={13} /></button>
          )}
          <ChevronDown size={14} />
        </span>
      </div>
      {open && (
        <div className="absolute z-50 left-0 right-0 top-full mt-1 rounded-md border bg-popover shadow-md max-h-56 overflow-y-auto"
          data-testid={`${testId}-options`}>
          {matches.length === 0 && (
            <p className="px-3 py-1.5 text-xs text-muted-foreground" data-testid={`${testId}-no-match`}>{emptyLabel}</p>
          )}
          {matches.map(o => (
            <button key={o.id} type="button"
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-accent flex items-center gap-2"
              onClick={() => { onChange(o.id, o); setOpen(false); setTerm(''); }}
              data-testid={`${testId}-option-${o.id}`}>
              {o.id === value ? <Check size={12} className="text-primary shrink-0" /> : <span className="w-3 shrink-0" />}
              <span className="min-w-0">
                <span className="font-medium block truncate">{o.name}</span>
                {o.hint && <span className="block text-[10px] text-muted-foreground truncate">{o.hint}</span>}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default StaffPicker;
