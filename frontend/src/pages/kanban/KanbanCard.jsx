import { Archive, Paperclip, CheckSquare, Calendar } from 'lucide-react';

const PRIORITY_COLORS = { low: '#10b981', medium: '#f59e0b', high: '#f97316', urgent: '#ef4444' };

export function KanbanCard({ task, listId, staffUsers, isDragging, isDragOver, onDragStart, onDragEnd, onClick, onArchive, canEdit }) {
  const assignedMembers = (task.assignees || [])
    .map(id => staffUsers.find(u => u.id === id))
    .filter(Boolean);
  const checklist = task.checklist || [];
  const completed = checklist.filter(i => i.completed).length;
  const isOverdue = task.due_date && new Date(task.due_date) < new Date() && task.status !== 'done';
  const attachCount = (task.attachments || []).length;

  return (
    <div
      draggable={canEdit}
      onDragStart={e => onDragStart(e, task, listId)}
      onDragEnd={onDragEnd}
      onClick={onClick}
      data-testid={`kanban-card-${task.id}`}
      className={`rounded-lg p-3 cursor-pointer transition-all group relative select-none
        ${isDragging ? 'opacity-40 rotate-1 scale-95' : ''}
        ${isDragOver ? 'border-t-2 border-t-blue-400' : ''}
      `}
      style={{
        background: '#0f172a',
        border: `1px solid rgba(255,255,255,${isDragging ? '0.05' : '0.1'})`,
        borderLeft: task.priority && task.priority !== 'medium' ? `3px solid ${PRIORITY_COLORS[task.priority]}` : '1px solid rgba(255,255,255,0.1)',
        boxShadow: isDragging ? 'none' : '0 1px 4px rgba(0,0,0,0.3)',
      }}
    >
      {/* Labels */}
      {(task.labels || []).length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {task.labels.slice(0, 5).map((lbl, i) => (
            <span key={i} className="h-1.5 w-6 rounded-full" style={{ background: lbl.color || lbl || '#3b82f6' }} />
          ))}
        </div>
      )}

      {/* Title */}
      <p className="text-xs font-medium text-slate-200 leading-snug pr-4">{task.title}</p>

      {/* Footer */}
      <div className="flex items-center gap-2 mt-2 flex-wrap">
        {task.due_date && (
          <span className={`flex items-center gap-1 text-[10px] rounded px-1.5 py-0.5 ${isOverdue ? 'bg-red-500/20 text-red-400' : 'text-slate-500'}`}>
            <Calendar size={9} /> {task.due_date}
          </span>
        )}
        {checklist.length > 0 && (
          <span className={`flex items-center gap-1 text-[10px] rounded px-1.5 py-0.5 ${completed === checklist.length ? 'bg-emerald-500/20 text-emerald-400' : 'bg-white/5 text-slate-500'}`}>
            <CheckSquare size={9} /> {completed}/{checklist.length}
          </span>
        )}
        {attachCount > 0 && (
          <span className="flex items-center gap-1 text-[10px] text-slate-500">
            <Paperclip size={9} /> {attachCount}
          </span>
        )}
        {assignedMembers.length > 0 && (
          <div className="ml-auto flex -space-x-1">
            {assignedMembers.slice(0, 3).map((m) => (
              <span key={m.id} className="h-5 w-5 rounded-full flex items-center justify-center text-[9px] font-bold text-white ring-1 ring-[#1e293b]"
                style={{ background: `hsl(${(m.name.charCodeAt(0) * 37) % 360}, 60%, 45%)` }}
                title={m.name}>
                {m.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
              </span>
            ))}
            {assignedMembers.length > 3 && (
              <span className="h-5 w-5 rounded-full flex items-center justify-center text-[9px] font-bold text-slate-300 bg-slate-600 ring-1 ring-[#1e293b]">
                +{assignedMembers.length - 3}
              </span>
            )}
          </div>
        )}
      </div>

      {canEdit && (
        <button
          className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 text-slate-500 hover:text-amber-400 transition-opacity"
          onClick={e => { e.stopPropagation(); onArchive(); }}
          title="Archive card"
        >
          <Archive size={11} />
        </button>
      )}
    </div>
  );
}
