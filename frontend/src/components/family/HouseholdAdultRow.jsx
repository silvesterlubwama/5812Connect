import React from 'react';
import { Phone, Mail, Edit, Trash2, Lock, Clock } from 'lucide-react';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { normaliseRole } from './HouseholdPersonForm';

/** One family member row — same shape everywhere (People, child profile, portal). */
export const HouseholdAdultRow = ({ person, pending, readOnly, onEdit, onRemove, testId }) => (
  <div className="flex items-center justify-between gap-3 p-3 rounded-lg bg-accent/30" data-testid={testId}>
    <div className="min-w-0">
      <p className="text-sm font-medium truncate">{person.name}</p>
      <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5 flex-wrap">
        {person.phone && <span className="flex items-center gap-1"><Phone size={10} />{person.phone}</span>}
        {person.email && <span className="flex items-center gap-1"><Mail size={10} />{person.email}</span>}
        {readOnly && <span className="flex items-center gap-1"><Lock size={10} /> managed by staff</span>}
      </div>
      {pending?.length > 0 && (
        <p className="text-[11px] text-amber-700 mt-1 flex items-center gap-1" data-testid={`${testId}-pending`}>
          <Clock size={10} /> Change awaiting review: {Object.values(pending[0].fields || {}).join(', ')}
        </p>
      )}
    </div>
    <div className="flex items-center gap-2 shrink-0">
      {person.approval_status === 'pending' && (
        <Badge variant="outline" className="text-[10px] border-amber-300 text-amber-700">Pending review</Badge>
      )}
      <Badge variant="outline" className="text-[10px]">{normaliseRole(person.role || person.relationship)}</Badge>
      {person.can_pickup === false
        ? <Badge variant="outline" className="text-[10px] border-rose-200 text-rose-600">No pickup</Badge>
        : <Badge variant="outline" className="text-[10px] border-emerald-200 text-emerald-700">Can pick up</Badge>}
      {!readOnly && onEdit && (
        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={onEdit} data-testid={`${testId}-edit`}><Edit size={13} /></Button>
      )}
      {!readOnly && onRemove && (
        <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" onClick={onRemove} data-testid={`${testId}-remove`}><Trash2 size={13} /></Button>
      )}
    </div>
  </div>
);
