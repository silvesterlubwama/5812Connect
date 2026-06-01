/**
 * EmptyState — reusable, friendly "nothing here yet" panel.
 *
 * Use anywhere a list / table / tab is empty. Replaces the inconsistent
 * "No X found" text scattered across pages.
 *
 *   <EmptyState icon={Users} title="No staff yet" description="Add your first..."
 *               action={{ label: 'Add staff', onClick: () => setShowCreate(true) }} />
 */
import React from 'react';
import { Inbox } from 'lucide-react';
import { Button } from './ui/button';

export default function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,        // { label, onClick, testid?, variant? } — optional CTA
  secondaryAction, // optional second CTA, ghost-style
  className = '',
  compact = false,
  testid = 'empty-state',
}) {
  return (
    <div
      className={`flex flex-col items-center justify-center text-center ${compact ? 'py-8 px-4' : 'py-14 px-6'} ${className}`}
      data-testid={testid}
    >
      <div className={`relative mb-4 ${compact ? 'w-14 h-14' : 'w-20 h-20'} rounded-full bg-gradient-to-br from-muted to-muted/40 flex items-center justify-center`}>
        <Icon size={compact ? 22 : 32} className="text-muted-foreground/70" strokeWidth={1.5} />
        {/* Subtle floating dots so it doesn't feel like a placeholder */}
        <div className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-emerald-400/60" />
        <div className="absolute -bottom-1 -left-2 w-1.5 h-1.5 rounded-full bg-blue-400/50" />
      </div>
      <p className={`font-semibold ${compact ? 'text-sm' : 'text-base'}`}>{title}</p>
      {description && (
        <p className={`mt-1.5 text-muted-foreground ${compact ? 'text-xs max-w-xs' : 'text-sm max-w-md'}`}>
          {description}
        </p>
      )}
      {(action || secondaryAction) && (
        <div className="flex gap-2 mt-4 flex-wrap justify-center">
          {action && (
            <Button
              size={compact ? 'sm' : 'default'}
              onClick={action.onClick}
              variant={action.variant || 'default'}
              data-testid={action.testid || `${testid}-action`}
            >
              {action.label}
            </Button>
          )}
          {secondaryAction && (
            <Button
              size={compact ? 'sm' : 'default'}
              variant="ghost"
              onClick={secondaryAction.onClick}
              data-testid={secondaryAction.testid || `${testid}-secondary`}
            >
              {secondaryAction.label}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
