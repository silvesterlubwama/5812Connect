import React, { useState, useEffect, useRef } from 'react';
import { Input } from './ui/input';
import { Plus, UserPlus } from 'lucide-react';
import api from '../services/api';
import { registerOpenPicker } from './SearchSelect';

// Type a name, find the person who is already in the system, link to them.
// Only when nothing matches do we offer to create a new profile — that is what
// stops the same spouse or guardian being re-typed on every form.
//
//   value     the text in the box
//   onChange  (text) => void
//   onPick    (person) => void        an existing person was chosen
//   onAddNew  (typedName) => void     nothing matched, create a profile
//   portal    true = use the member-safe endpoint (name only, 3 chars min)
//   kinds     csv filter, e.g. 'member,user,guest'
//   onMatches (people[]) => void     every resolved search, so a caller can
//                                    warn about a possible duplicate
export const PersonPicker = ({
  value, onChange, onPick, onAddNew, onMatches, portal = false, kinds = '',
  placeholder = 'Start typing their name…', testId = 'person-picker',
  size = 'default', addNewLabel = 'as a new person', disabled = false,
}) => {
  const [matches, setMatches] = useState([]);
  const [open, setOpen] = useState(false);
  const [exact, setExact] = useState(false);
  const [searching, setSearching] = useState(false);
  const box = useRef(null);
  const timer = useRef(null);

  useEffect(() => {
    const away = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', away);
    return () => { document.removeEventListener('mousedown', away); clearTimeout(timer.current); };
  }, []);

  const typed = (value || '').trim();
  const minChars = portal ? 3 : 2;
  const showNew = open && !!onAddNew && typed.length >= 2 && !exact && !searching;
  const listShowing = open && (matches.length > 0 || showNew);
  useEffect(() => registerOpenPicker(listShowing), [listShowing]);

  const search = (q) => {
    clearTimeout(timer.current);
    const term = (q || '').trim();
    if (term.length < minChars) { setMatches([]); setExact(false); setSearching(false); onMatches?.([]); return; }
    setSearching(true);
    timer.current = setTimeout(async () => {
      try {
        const url = portal ? '/portal/people/suggest' : '/people/suggest';
        const r = await api.get(url, { params: { q: term, ...(kinds && !portal ? { kinds } : {}) } });
        const list = r.data?.people || [];
        setMatches(list);
        setExact(list.some(p => (p.name || '').toLowerCase() === term.toLowerCase()));
        onMatches?.(list);
      } catch { setMatches([]); setExact(false); onMatches?.([]); }
      setSearching(false);
    }, 200);
  };

  return (
    <div ref={box} className="relative">
      <Input
        data-testid={testId}
        className={size === 'sm' ? 'h-8 text-xs' : ''}
        value={value || ''}
        placeholder={placeholder}
        autoComplete="off"
        disabled={disabled}
        onFocus={() => { setOpen(true); search(value); }}
        onKeyDown={e => {
          if (e.key === 'Escape' && open) { e.preventDefault(); e.stopPropagation(); setOpen(false); }
        }}
        onChange={e => { onChange(e.target.value); setOpen(true); search(e.target.value); }}
      />
      {listShowing && (
        <div className="absolute z-50 left-0 right-0 top-full mt-1 rounded-md border bg-popover shadow-md max-h-56 overflow-y-auto"
          data-testid={`${testId}-options`}>
          {matches.map(p => (
            <button key={`${p.type}-${p.id}`} type="button"
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-accent flex items-center gap-2"
              onClick={() => { onChange(p.name); onPick?.(p); setOpen(false); setMatches([]); }}
              data-testid={`${testId}-option-${p.id}`}>
              {p.photo_url
                ? <img src={p.photo_url} alt="" className="h-6 w-6 rounded-full object-cover shrink-0" />
                : <span className="h-6 w-6 rounded-full bg-muted grid place-items-center text-[9px] shrink-0">
                    {(p.name || '?').slice(0, 2).toUpperCase()}
                  </span>}
              <span className="min-w-0">
                <span className="font-medium block truncate">{p.name}</span>
                <span className="block text-[10px] text-muted-foreground truncate">
                  {[p.hint || p.role || p.type, p.relationship, p.phone, p.email].filter(Boolean).join(' · ')}
                </span>
              </span>
            </button>
          ))}
          {matches.length === 0 && !searching && typed.length >= minChars && (
            <p className="px-3 py-1.5 text-xs text-muted-foreground" data-testid={`${testId}-no-match`}>
              Nobody found by that name
            </p>
          )}
          {showNew && (
            <button type="button"
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-accent border-t flex items-center gap-1.5 text-emerald-700"
              onClick={() => { setOpen(false); setMatches([]); onAddNew(typed); }}
              data-testid={`${testId}-add-new`}>
              {matches.length ? <Plus size={12} /> : <UserPlus size={12} />} Add “{typed}” {addNewLabel}
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default PersonPicker;
