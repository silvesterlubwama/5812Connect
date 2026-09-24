import React, { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { PersonPicker } from '../PersonPicker';

// Search-first name box for the "add somebody" forms. Typing looks the person
// up first; picking a match opens THAT profile instead of creating a second
// one. Creating anyway is allowed — the amber line below just makes the
// possible duplicate impossible to miss.
export const PersonNameField = ({
  value, onChange, kinds = '', onOpenExisting, testId = 'person-name',
  placeholder = 'Type their name to find them first…',
  addNewLabel = 'as a new person', size = 'default',
}) => {
  const [dupes, setDupes] = useState([]);
  const typed = (value || '').trim();
  const shown = typed.length >= 2 ? dupes : [];

  return (
    <div className="space-y-1">
      <PersonPicker
        value={value} onChange={onChange} kinds={kinds} size={size}
        testId={testId} placeholder={placeholder} addNewLabel={addNewLabel}
        onMatches={setDupes}
        onPick={p => onOpenExisting?.(p)}
        onAddNew={name => onChange(name)}
      />
      {shown.length > 0 && (
        <div className="flex items-start gap-1.5 rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-950/30 px-2 py-1.5 text-[11px] text-amber-800 dark:text-amber-300"
          data-testid={`${testId}-duplicate-warning`}>
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          <span className="min-w-0">
            Possible duplicate — <strong>{shown[0].name}</strong>
            {shown[0].role || shown[0].type ? ` (${shown[0].role || shown[0].type})` : ''} already exists
            {shown.length > 1 ? `, and ${shown.length - 1} other match${shown.length > 2 ? 'es' : ''}` : ''}.{' '}
            <button type="button" className="underline font-medium"
              onClick={() => onOpenExisting?.(shown[0])}
              data-testid={`${testId}-open-existing`}>Open them instead</button>
          </span>
        </div>
      )}
    </div>
  );
};

export default PersonNameField;
