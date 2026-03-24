import React, { useRef, useEffect, useState } from 'react';
import { Plus, MoreHorizontal, Edit2, Archive, Trash2, X } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { KanbanCard } from './KanbanCard';

export function KanbanList({
  list, listTasks, accentColor, boardStaff, canEdit,
  dragging, dragOver, onDragStart, onDragEnd, onDragOver, onDrop,
  onCardClick, onCardArchive, onAddCard,
  onArchiveList, onDeleteList, onRenameList,
}) {
  const [openMenu, setOpenMenu] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [nameVal, setNameVal] = useState(list.name);
  const [addingCard, setAddingCard] = useState(false);
  const [newCardTitle, setNewCardTitle] = useState('');
  const menuRef = useRef(null);

  useEffect(() => {
    const handler = (e) => { if (menuRef.current && !menuRef.current.contains(e.target)) setOpenMenu(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const confirmRename = () => {
    if (nameVal.trim() && nameVal !== list.name) onRenameList(list.id, nameVal.trim());
    setEditingName(false);
  };

  const handleAddCard = () => {
    if (!newCardTitle.trim()) { setAddingCard(false); return; }
    onAddCard(list.id, newCardTitle.trim());
    setNewCardTitle('');
    setAddingCard(false);
  };

  return (
    <div
      data-testid={`kanban-list-${list.id}`}
      className="flex-shrink-0 w-64 rounded-xl flex flex-col"
      style={{ maxHeight: 'calc(100vh - 180px)', background: '#1e293b', border: '1px solid rgba(255,255,255,0.08)' }}
      onDragOver={e => onDragOver(e, list.id, listTasks.length)}
      onDrop={e => onDrop(e, list.id)}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 flex-shrink-0"
        style={{ borderBottom: `2px solid ${accentColor}40`, borderRadius: '12px 12px 0 0', background: 'rgba(255,255,255,0.04)' }}>
        {editingName ? (
          <Input autoFocus className="h-7 text-sm font-semibold bg-[#0f172a] border-white/15 text-white"
            value={nameVal} onChange={e => setNameVal(e.target.value)}
            onBlur={confirmRename}
            onKeyDown={e => { if (e.key === 'Enter') confirmRename(); if (e.key === 'Escape') setEditingName(false); }} />
        ) : (
          <span className="cursor-pointer hover:text-white flex-1 truncate text-sm font-semibold text-slate-200"
            onDoubleClick={() => { setEditingName(true); setNameVal(list.name); }}
            data-testid={`list-name-${list.id}`}>
            {list.name}
          </span>
        )}
        <div className="flex items-center gap-1 ml-2 flex-shrink-0">
          <span className="text-xs text-slate-500">{listTasks.length}</span>
          {canEdit && (
            <div className="relative" ref={menuRef}>
              <button className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-white"
                onClick={() => setOpenMenu(o => !o)}>
                <MoreHorizontal size={14} />
              </button>
              {openMenu && (
                <div className="absolute right-0 top-7 z-50 w-44 rounded-xl bg-[#0f172a] border border-white/10 shadow-2xl py-1">
                  <button className="flex items-center gap-2 w-full px-3 py-2 text-xs text-slate-300 hover:bg-white/10"
                    onClick={() => { setOpenMenu(false); setEditingName(true); setNameVal(list.name); }}>
                    <Edit2 size={11} /> Rename List
                  </button>
                  <button className="flex items-center gap-2 w-full px-3 py-2 text-xs text-amber-400 hover:bg-amber-500/10"
                    onClick={() => { setOpenMenu(false); onArchiveList(list.id); }}>
                    <Archive size={11} /> Archive List
                  </button>
                  <div className="border-t border-white/10 my-1" />
                  <button className="flex items-center gap-2 w-full px-3 py-2 text-xs text-red-400 hover:bg-red-500/10"
                    onClick={() => { setOpenMenu(false); onDeleteList(list.id); }}>
                    <Trash2 size={11} /> Delete List
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Cards */}
      <div className="overflow-y-auto flex-1 px-2 py-2 space-y-2">
        {listTasks.map((task, idx) => (
          <KanbanCard
            key={task.id}
            task={task}
            listId={list.id}
            staffUsers={boardStaff}
            isDragging={dragging?.task?.id === task.id}
            isDragOver={dragOver?.listId === list.id && dragOver?.idx === idx}
            onDragStart={onDragStart}
            onDragEnd={onDragEnd}
            onClick={() => onCardClick(task)}
            onArchive={() => onCardArchive(task)}
            canEdit={canEdit}
          />
        ))}
        {listTasks.length === 0 && (
          <div className="h-8 rounded-lg border border-dashed border-white/10 flex items-center justify-center">
            <span className="text-[11px] text-slate-600">Drop cards here</span>
          </div>
        )}
      </div>

      {/* Add card */}
      {addingCard ? (
        <div className="px-2 pb-2 space-y-2 flex-shrink-0">
          <Textarea autoFocus rows={2} placeholder="Enter a title..."
            className="bg-[#0f172a] border-white/15 text-slate-200 placeholder:text-slate-500 text-sm resize-none"
            value={newCardTitle} onChange={e => setNewCardTitle(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAddCard(); } if (e.key === 'Escape') setAddingCard(false); }}
            data-testid={`new-card-input-${list.id}`} />
          <div className="flex gap-2">
            <Button size="sm" className="h-7 bg-blue-600 hover:bg-blue-700 text-white text-xs" onClick={handleAddCard} data-testid={`add-card-confirm-${list.id}`}>Add</Button>
            <Button size="sm" variant="ghost" className="h-7 text-slate-400 hover:text-white" onClick={() => setAddingCard(false)}><X size={14} /></Button>
          </div>
        </div>
      ) : canEdit && (
        <button data-testid={`add-card-btn-${list.id}`}
          onClick={() => { setAddingCard(true); setNewCardTitle(''); }}
          className="flex items-center gap-1.5 w-full px-3 py-2.5 text-xs text-slate-500 hover:text-slate-300 hover:bg-white/5 rounded-b-xl transition-colors flex-shrink-0">
          <Plus size={13} /> Add a card
        </button>
      )}
    </div>
  );
}
