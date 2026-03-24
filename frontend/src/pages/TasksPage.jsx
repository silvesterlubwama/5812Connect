import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Plus, Archive, RefreshCw, MapPin, Wifi, Trash2, Download, Upload, Globe, X, LayoutGrid, CalendarDays } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { boardsApi, tasksApi, locationsApi, adminApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useWebSocket } from '../context/WebSocketContext';
import { toast } from 'sonner';
import { KanbanList } from './kanban/KanbanList';
import { ArchivePanel } from './kanban/ArchivePanel';
import { CardDetailDialog } from './kanban/CardDetailDialog';
import { TeamCalendar } from './kanban/TeamCalendar';

export default function TasksPage() {
  const { user } = useAuth();
  const { addListener, joinBoard, leaveBoard } = useWebSocket();

  const [boards, setBoards] = useState([]);
  const [activeBoardId, setActiveBoardId] = useState(null);
  const [board, setBoard] = useState(null);
  const [tasks, setTasks] = useState({});
  const [loading, setLoading] = useState(true);
  const [locations, setLocations] = useState([]);
  const [staffUsers, setStaffUsers] = useState([]);
  const prevBoardRef = useRef(null);

  // Drag state
  const [dragging, setDragging] = useState(null);
  const [dragOver, setDragOver] = useState(null);

  // Dialogs
  const [openCard, setOpenCard] = useState(null);
  const [showNewBoard, setShowNewBoard] = useState(false);
  const [newBoardForm, setNewBoardForm] = useState({ name: '', location_id: '', background: '#3b82f6' });
  const [showTrelloImport, setShowTrelloImport] = useState(false);
  const [trelloJson, setTrelloJson] = useState('');
  const [importLocationId, setImportLocationId] = useState('');
  const [importing, setImporting] = useState(false);
  const [showArchive, setShowArchive] = useState(false);
  const [boardViewers, setBoardViewers] = useState([]);
  const trelloFileRef = useRef(null);
  const [viewMode, setViewMode] = useState('kanban'); // 'kanban' | 'calendar'
  const [allTasks, setAllTasks] = useState([]);

  const isAdmin = ['admin', 'system_admin', 'executive director', 'director'].includes((user?.role || '').toLowerCase());
  const canEdit = isAdmin || ['manager', 'coordinator'].includes((user?.role || '').toLowerCase());

  // Staff filtered by board's location (if set), otherwise all staff
  const boardStaff = useMemo(() => {
    if (!board || board.is_global || !board.location_id) return staffUsers;
    return staffUsers.filter(u => !u.location_id || u.location_id === board.location_id);
  }, [staffUsers, board]);

  // ===== LOAD DATA =====
  const fetchBoards = useCallback(async () => {
    try {
      const [bRes, lRes, uRes] = await Promise.all([
        boardsApi.list(),
        locationsApi.list().catch(() => ({ data: [] })),
        adminApi.users({ limit: 300 }).catch(() => ({ data: [] })),
      ]);
      setBoards(bRes.data || []);
      setLocations(lRes.data || []);
      setStaffUsers(uRes.data || []);
      if (bRes.data?.length && !activeBoardId) setActiveBoardId(bRes.data[0].id);
    } catch { toast.error('Failed to load boards'); }
    finally { setLoading(false); }
  }, [activeBoardId]);

  useEffect(() => { fetchBoards(); }, []);

  // Fetch all tasks for Team Calendar view
  useEffect(() => {
    if (viewMode !== 'calendar') return;
    tasksApi.list().then(res => setAllTasks(res.data || [])).catch(() => {});
  }, [viewMode]);

  const fetchBoardDetail = useCallback(async () => {
    if (!activeBoardId) return;
    try {
      const [bRes, tRes] = await Promise.all([
        boardsApi.get(activeBoardId),
        boardsApi.tasks(activeBoardId, null),
      ]);
      setBoard(bRes.data);
      const grouped = {};
      for (const list of bRes.data.lists || []) grouped[list.id] = [];
      for (const t of (tRes.data || [])) {
        const lid = t.list_id || '__none__';
        if (!grouped[lid]) grouped[lid] = [];
        grouped[lid].push(t);
      }
      for (const lid of Object.keys(grouped)) grouped[lid].sort((a, b) => (a.position || 0) - (b.position || 0));
      setTasks(grouped);
    } catch { toast.error('Failed to load board'); }
  }, [activeBoardId]);

  useEffect(() => { fetchBoardDetail(); }, [fetchBoardDetail]);

  // ===== WS BOARD ROOM =====
  useEffect(() => {
    if (!activeBoardId) return;
    if (prevBoardRef.current && prevBoardRef.current !== activeBoardId) leaveBoard(prevBoardRef.current);
    prevBoardRef.current = activeBoardId;
    const t = setTimeout(() => joinBoard(activeBoardId), 800);
    return () => { clearTimeout(t); leaveBoard(activeBoardId); };
  }, [activeBoardId, joinBoard, leaveBoard]);

  useEffect(() => {
    const unsubEvent = addListener('board_event', (data) => {
      if (data.board_id !== activeBoardId) return;
      const { action } = data;
      if (action === 'card_created') {
        setTasks(prev => {
          const next = { ...prev };
          const lid = data.list_id || '__none__';
          if (!next[lid]) next[lid] = [];
          if (!next[lid].find(t => t.id === data.task?.id)) next[lid] = [...next[lid], data.task];
          return next;
        });
      } else if (action === 'card_updated') {
        setTasks(prev => {
          const next = { ...prev };
          for (const lid of Object.keys(next)) next[lid] = next[lid].map(t => t.id === data.task_id ? { ...t, ...data.task } : t);
          return next;
        });
        if (openCard?.id === data.task_id) setOpenCard(prev => ({ ...prev, ...data.task }));
      } else if (action === 'card_moved') {
        setTasks(prev => {
          const next = { ...prev };
          if (data.from_list_id && next[data.from_list_id]) next[data.from_list_id] = next[data.from_list_id].filter(t => t.id !== data.task_id);
          if (data.to_list_id) {
            if (!next[data.to_list_id]) next[data.to_list_id] = [];
            if (!next[data.to_list_id].find(t => t.id === data.task_id) && data.task) next[data.to_list_id] = [...next[data.to_list_id], data.task];
          }
          return next;
        });
      } else if (action === 'card_deleted' || action === 'card_archived') {
        setTasks(prev => { const next = { ...prev }; for (const lid of Object.keys(next)) next[lid] = next[lid].filter(t => t.id !== data.task_id); return next; });
        if (openCard?.id === data.task_id) setOpenCard(null);
      } else if (action === 'card_restored') {
        setTasks(prev => {
          const next = { ...prev };
          const lid = data.list_id || '__none__';
          if (!next[lid]) next[lid] = [];
          if (!next[lid].find(t => t.id === data.task_id) && data.task) next[lid] = [...next[lid], data.task];
          return next;
        });
      } else if (action === 'list_created') {
        setBoard(prev => prev ? { ...prev, lists: [...(prev.lists || []), data.list] } : prev);
        setTasks(prev => ({ ...prev, [data.list?.id]: [] }));
      } else if (action === 'list_updated') {
        setBoard(prev => prev ? { ...prev, lists: (prev.lists || []).map(l => l.id === data.list_id ? { ...l, ...data.list } : l) } : prev);
      } else if (action === 'list_archived' || action === 'list_deleted') {
        setBoard(prev => prev ? { ...prev, lists: (prev.lists || []).filter(l => l.id !== data.list_id) } : prev);
        setTasks(prev => { const n = { ...prev }; delete n[data.list_id]; return n; });
      } else if (action === 'list_restored') {
        setBoard(prev => prev ? { ...prev, lists: [...(prev.lists || []), data.list] } : prev);
        setTasks(prev => ({ ...prev, [data.list?.id]: prev[data.list?.id] || [] }));
      }
    });
    const unsubPresence = addListener('board_presence', (data) => {
      if (data.board_id === activeBoardId) setBoardViewers(data.viewers || []);
    });
    return () => { unsubEvent(); unsubPresence(); };
  }, [activeBoardId, addListener, openCard]);

  // ===== BOARD ACTIONS =====
  const createBoard = async () => {
    if (!newBoardForm.name.trim()) return;
    try {
      const loc = locations.find(l => l.id === newBoardForm.location_id);
      const res = await boardsApi.create({ ...newBoardForm, location_name: loc?.name || '' });
      setBoards(prev => [res.data, ...prev]);
      setActiveBoardId(res.data.id);
      setShowNewBoard(false);
      setNewBoardForm({ name: '', location_id: '', background: '#3b82f6' });
      toast.success(`Board "${res.data.name}" created`);
    } catch { toast.error('Failed to create board'); }
  };

  const deleteBoard = async (boardId) => {
    if (!window.confirm('Delete this board and all its cards?')) return;
    try {
      await boardsApi.delete(boardId);
      setBoards(prev => prev.filter(b => b.id !== boardId));
      if (activeBoardId === boardId) setActiveBoardId(boards.filter(b => b.id !== boardId)[0]?.id || null);
      toast.success('Board deleted');
    } catch { toast.error('Failed to delete board'); }
  };

  // ===== LIST ACTIONS =====
  const addList = useCallback(async (name) => {
    if (!name.trim() || !activeBoardId) return;
    try {
      const res = await boardsApi.addList(activeBoardId, { name: name.trim() });
      setBoard(prev => ({ ...prev, lists: [...(prev?.lists || []), res.data] }));
      setTasks(prev => ({ ...prev, [res.data.id]: [] }));
    } catch { toast.error('Failed to add list'); }
  }, [activeBoardId]);

  const renameList = useCallback(async (listId, name) => {
    try {
      await boardsApi.updateList(activeBoardId, listId, { name });
      setBoard(prev => ({ ...prev, lists: prev.lists.map(l => l.id === listId ? { ...l, name } : l) }));
    } catch { toast.error('Failed to rename'); }
  }, [activeBoardId]);

  const archiveList = useCallback(async (listId) => {
    try {
      await boardsApi.archiveList(activeBoardId, listId);
      setBoard(prev => ({ ...prev, lists: prev.lists.filter(l => l.id !== listId) }));
      setTasks(prev => { const n = { ...prev }; delete n[listId]; return n; });
      toast.success('List archived');
    } catch { toast.error('Failed to archive list'); }
  }, [activeBoardId]);

  const deleteList = useCallback(async (listId) => {
    if (!window.confirm('Delete this list and its cards?')) return;
    try {
      await boardsApi.deleteList(activeBoardId, listId);
      setBoard(prev => ({ ...prev, lists: prev.lists.filter(l => l.id !== listId) }));
      setTasks(prev => { const n = { ...prev }; delete n[listId]; return n; });
      toast.success('List deleted');
    } catch { toast.error('Failed to delete list'); }
  }, [activeBoardId]);

  // ===== CARD ACTIONS =====
  const addCard = useCallback(async (listId, title) => {
    const list = board?.lists?.find(l => l.id === listId);
    const pos = tasks[listId]?.length || 0;
    try {
      const res = await tasksApi.create({ title, board_id: activeBoardId, list_id: listId, list_name: list?.name || '', status: 'todo', position: pos, assignees: [], labels: [], checklist: [], attachments: [] });
      setTasks(prev => ({ ...prev, [listId]: [...(prev[listId] || []), res.data] }));
    } catch { toast.error('Failed to add card'); }
  }, [activeBoardId, board, tasks]);

  const archiveCard = useCallback(async (task) => {
    const { tasksExtApi } = await import('../services/api');
    try {
      await tasksExtApi.archive(task.id);
      setTasks(prev => { const next = { ...prev }; next[task.list_id] = (next[task.list_id] || []).filter(t => t.id !== task.id); return next; });
      if (openCard?.id === task.id) setOpenCard(null);
      toast.success('Card archived');
    } catch { toast.error('Failed to archive card'); }
  }, [openCard]);

  const deleteCard = useCallback(async (task) => {
    if (!window.confirm('Delete this card permanently?')) return;
    try {
      await tasksApi.delete(task.id);
      setTasks(prev => { const next = { ...prev }; next[task.list_id] = (next[task.list_id] || []).filter(t => t.id !== task.id); return next; });
      if (openCard?.id === task.id) setOpenCard(null);
      toast.success('Card deleted');
    } catch { toast.error('Failed to delete card'); }
  }, [openCard]);

  const moveCard = useCallback(async (task, fromListId, toListId) => {
    if (fromListId === toListId) return;
    const list = board?.lists?.find(l => l.id === toListId);
    const pos = tasks[toListId]?.length || 0;
    const statusMap = { 'To Do': 'todo', 'In Progress': 'in-progress', 'Done': 'done' };
    const newStatus = statusMap[list?.name] || task.status;
    try {
      await boardsApi.moveTask(task.id, { list_id: toListId, position: pos, status: newStatus });
      setTasks(prev => {
        const next = { ...prev };
        next[fromListId] = (next[fromListId] || []).filter(t => t.id !== task.id);
        next[toListId] = [...(next[toListId] || []), { ...task, list_id: toListId, status: newStatus, position: pos }];
        return next;
      });
    } catch { toast.error('Move failed'); }
  }, [board, tasks]);

  const onCardSaved = useCallback((updated) => {
    setTasks(prev => {
      const next = { ...prev };
      for (const lid of Object.keys(next)) next[lid] = next[lid].map(t => t.id === updated.id ? { ...t, ...updated } : t);
      return next;
    });
    setOpenCard(prev => prev ? { ...prev, ...updated } : prev);
  }, []);

  // ===== DRAG =====
  const onDragStart = (e, task, fromListId) => { setDragging({ task, fromListId }); e.dataTransfer.effectAllowed = 'move'; };
  const onDragOver = (e, listId, idx) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; setDragOver({ listId, idx }); };
  const onDrop = (e, toListId) => { e.preventDefault(); if (!dragging) return; moveCard(dragging.task, dragging.fromListId, toListId); setDragging(null); setDragOver(null); };
  const onDragEnd = () => { setDragging(null); setDragOver(null); };

  // ===== TRELLO IMPORT =====
  const importTrello = async () => {
    if (!trelloJson.trim()) { toast.error('Paste or upload a Trello JSON export'); return; }
    setImporting(true);
    try {
      const parsed = JSON.parse(trelloJson);
      if (importLocationId) parsed.location_id = importLocationId;
      const res = await boardsApi.importTrello(parsed);
      toast.success(`Imported "${res.data.board_name}": ${res.data.lists} lists, ${res.data.imported} cards`);
      setShowTrelloImport(false); setTrelloJson('');
      await fetchBoards();
      setActiveBoardId(res.data.board_id);
    } catch (err) { toast.error(err.response?.data?.detail || 'Import failed — check JSON format'); }
    finally { setImporting(false); }
  };

  // ===== ADD LIST (inline state in canvas) =====
  const [addingList, setAddingList] = useState(false);
  const [newListName, setNewListName] = useState('');

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full" />
    </div>
  );

  const currentBoard = boards.find(b => b.id === activeBoardId);
  const accentColor = currentBoard?.background || '#3b82f6';

  return (
    <div className="flex h-full" style={{ minHeight: 'calc(100vh - 64px)', background: '#0f172a' }}>
      {/* Sidebar */}
      <div className="w-56 flex-shrink-0 bg-[#1e293b] flex flex-col border-r border-white/10">
        <div className="p-3 border-b border-white/10">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-2">Boards</p>
          {canEdit && (
            <button onClick={() => setShowNewBoard(true)} data-testid="create-board-btn"
              className="flex items-center gap-2 w-full px-2 py-1.5 rounded text-xs text-slate-400 hover:bg-white/10 hover:text-white transition-colors">
              <Plus size={13} /> New Board
            </button>
          )}
        </div>
        <div className="flex-1 overflow-y-auto py-2 space-y-0.5 px-2">
          {boards.length === 0 && <p className="text-xs text-slate-500 px-2 py-3 text-center">No boards yet</p>}
          {boards.map(b => (
            <button key={b.id} onClick={() => setActiveBoardId(b.id)} data-testid={`board-tab-${b.id}`}
              className={`flex items-center gap-2 w-full px-2 py-2 rounded-md text-sm transition-all text-left group ${b.id === activeBoardId ? 'bg-white/15 text-white' : 'text-slate-400 hover:bg-white/8 hover:text-slate-200'}`}>
              <span className="w-3 h-3 rounded-sm flex-shrink-0" style={{ background: b.background || '#3b82f6' }} />
              <span className="flex-1 truncate text-xs">{b.name}</span>
              <span className="text-[10px] opacity-50 flex-shrink-0">{b.card_count || 0}</span>
            </button>
          ))}
        </div>
        <div className="p-3 border-t border-white/10 space-y-1">
          <button onClick={() => setShowTrelloImport(true)}
            className="flex items-center gap-2 w-full px-2 py-1.5 rounded text-xs text-slate-400 hover:bg-white/10 hover:text-white transition-colors">
            <Download size={12} /> Import Trello
          </button>
          <div className="flex gap-1 mt-2">
            <button onClick={() => setViewMode('kanban')} data-testid="view-kanban-btn"
              className={`flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded text-xs transition-colors ${viewMode === 'kanban' ? 'bg-white/15 text-white' : 'text-slate-400 hover:bg-white/10 hover:text-white'}`}>
              <LayoutGrid size={12} /> Board
            </button>
            <button onClick={() => setViewMode('calendar')} data-testid="view-calendar-btn"
              className={`flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded text-xs transition-colors ${viewMode === 'calendar' ? 'bg-white/15 text-white' : 'text-slate-400 hover:bg-white/10 hover:text-white'}`}>
              <CalendarDays size={12} /> Calendar
            </button>
          </div>
        </div>
      </div>

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {viewMode === 'calendar' ? (
          <TeamCalendar boards={boards} allTasks={allTasks} staffUsers={staffUsers} onCardClick={setOpenCard} />
        ) : (
        <>
        {currentBoard && (
          <div className="flex items-center justify-between px-5 py-3 flex-shrink-0 border-b border-white/10" style={{ background: 'rgba(255,255,255,0.04)' }}>
            <div className="flex items-center gap-3">
              <span className="w-4 h-4 rounded" style={{ background: accentColor }} />
              <h2 className="text-base font-semibold text-white">{currentBoard.name}</h2>
              {currentBoard.location_name && <span className="flex items-center gap-1 text-xs text-slate-400"><MapPin size={11} /> {currentBoard.location_name}</span>}
              {boardViewers.length > 1 && <span className="flex items-center gap-1 text-xs text-emerald-400"><Wifi size={11} /> {boardViewers.length} viewing</span>}
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="ghost" className="text-slate-400 hover:text-white hover:bg-white/10 gap-1.5 h-8 text-xs" onClick={() => setShowArchive(true)}>
                <Archive size={13} /> Archive
              </Button>
              {isAdmin && (
                <Button size="sm" variant="ghost" className="text-slate-400 hover:text-red-400 hover:bg-red-500/10 h-8 text-xs" onClick={() => deleteBoard(activeBoardId)}>
                  <Trash2 size={13} />
                </Button>
              )}
              <Button size="sm" variant="ghost" className="text-slate-400 hover:text-white hover:bg-white/10 h-8" onClick={fetchBoardDetail}>
                <RefreshCw size={13} />
              </Button>
            </div>
          </div>
        )}

        {/* Canvas */}
        {!activeBoardId || !board ? (
          <div className="flex flex-col items-center justify-center flex-1 gap-4 text-slate-500">
            <p className="text-lg">No board selected</p>
            <Button onClick={() => setShowNewBoard(true)} className="gap-2 bg-blue-600 hover:bg-blue-700 text-white"><Plus size={16} /> Create Board</Button>
          </div>
        ) : (
          <div className="flex gap-4 p-5 overflow-x-auto flex-1 items-start">
            {(board.lists || []).map(list => (
              <KanbanList key={list.id} list={list} listTasks={tasks[list.id] || []}
                accentColor={accentColor} boardStaff={boardStaff} canEdit={canEdit}
                dragging={dragging} dragOver={dragOver}
                onDragStart={onDragStart} onDragEnd={onDragEnd} onDragOver={onDragOver} onDrop={onDrop}
                onCardClick={setOpenCard} onCardArchive={archiveCard} onAddCard={addCard}
                onArchiveList={archiveList} onDeleteList={deleteList} onRenameList={renameList} />
            ))}

            {canEdit && (
              <div className="flex-shrink-0 w-64">
                {addingList ? (
                  <div className="rounded-xl bg-[#1e293b] border border-white/10 p-3 space-y-2">
                    <Input autoFocus placeholder="List name..."
                      className="bg-[#0f172a] border-white/20 text-white placeholder:text-slate-500 text-sm h-8"
                      value={newListName} onChange={e => setNewListName(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') { addList(newListName); setNewListName(''); setAddingList(false); } if (e.key === 'Escape') setAddingList(false); }}
                      data-testid="new-list-input" />
                    <div className="flex gap-2">
                      <Button size="sm" className="h-7 bg-blue-600 hover:bg-blue-700 text-white text-xs"
                        onClick={() => { addList(newListName); setNewListName(''); setAddingList(false); }} data-testid="add-list-confirm-btn">Add List</Button>
                      <Button size="sm" variant="ghost" className="h-7 text-slate-400 hover:text-white" onClick={() => setAddingList(false)}><X size={13} /></Button>
                    </div>
                  </div>
                ) : (
                  <button data-testid="add-list-btn" onClick={() => setAddingList(true)}
                    className="flex items-center gap-2 w-full px-4 py-3 rounded-xl bg-white/8 hover:bg-white/12 text-sm font-medium text-slate-400 hover:text-white transition-all border border-white/10 border-dashed">
                    <Plus size={16} /> Add another list
                  </button>
                )}
              </div>
            )}
          </div>
        )}
        </>
        )}
      </div>

      {/* Card Detail Dialog */}
      <CardDetailDialog card={openCard} board={board} boardStaff={boardStaff}
        onClose={() => setOpenCard(null)}
        onSaved={onCardSaved}
        onArchive={archiveCard}
        onDelete={deleteCard}
        onMove={moveCard} />

      {/* Archive Panel */}
      <ArchivePanel open={showArchive} onClose={() => setShowArchive(false)} boardId={activeBoardId}
        onRestoreCard={(card) => {
          if (card?.list_id) setTasks(prev => {
            const next = { ...prev };
            if (!next[card.list_id]) next[card.list_id] = [];
            if (!next[card.list_id].find(t => t.id === card.id)) next[card.list_id] = [...next[card.list_id], card];
            return next;
          });
        }}
        onRestoreList={(list) => {
          if (list) {
            setBoard(prev => prev ? { ...prev, lists: [...(prev.lists || []), list] } : prev);
            setTasks(prev => ({ ...prev, [list.id]: prev[list.id] || [] }));
          }
        }} />

      {/* Create Board Dialog */}
      <Dialog open={showNewBoard} onOpenChange={setShowNewBoard}>
        <DialogContent className="max-w-sm bg-[#1e293b] border-white/10 text-slate-100">
          <DialogHeader><DialogTitle className="text-slate-100">Create Board</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label className="text-slate-300 text-xs">Board Name *</Label>
              <Input data-testid="new-board-name" value={newBoardForm.name} onChange={e => setNewBoardForm({ ...newBoardForm, name: e.target.value })}
                placeholder="e.g. Kampala Office Tasks"
                className="bg-[#0f172a] border-white/15 text-slate-200 placeholder:text-slate-500" />
            </div>
            <div className="space-y-2">
              <Label className="text-slate-300 text-xs">Location (optional)</Label>
              <Select value={newBoardForm.location_id || '_global'} onValueChange={v => setNewBoardForm({ ...newBoardForm, location_id: v === '_global' ? '' : v })}>
                <SelectTrigger className="bg-[#0f172a] border-white/15 text-slate-200"><SelectValue placeholder="Global" /></SelectTrigger>
                <SelectContent className="bg-[#1e293b] border-white/15">
                  <SelectItem value="_global" className="text-slate-200">Global (all users)</SelectItem>
                  {locations.map(l => <SelectItem key={l.id} value={l.id} className="text-slate-200">{l.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-slate-300 text-xs">Accent Color</Label>
              <div className="flex flex-wrap gap-2">
                {['#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#06b6d4','#f97316','#6366f1','#1d4ed8'].map(c => (
                  <button key={c} className={`h-8 w-8 rounded-lg transition-transform hover:scale-110 ${newBoardForm.background === c ? 'ring-2 ring-white ring-offset-1 ring-offset-[#1e293b] scale-110' : ''}`}
                    style={{ background: c }} onClick={() => setNewBoardForm({ ...newBoardForm, background: c })} />
                ))}
              </div>
            </div>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1 border-white/15 text-slate-300 hover:bg-white/10" onClick={() => setShowNewBoard(false)}>Cancel</Button>
              <Button className="flex-1 bg-blue-600 hover:bg-blue-700 text-white" onClick={createBoard} data-testid="confirm-create-board">Create</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Trello Import Dialog */}
      <Dialog open={showTrelloImport} onOpenChange={setShowTrelloImport}>
        <DialogContent className="max-w-lg bg-[#1e293b] border-white/10 text-slate-100">
          <DialogHeader><DialogTitle className="text-slate-100">Import Trello Board</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <p className="text-sm text-slate-400">Export your Trello board as JSON (Board menu → Print & Export → Export as JSON) and paste or upload it below.</p>
            <div className="space-y-2">
              <Label className="text-slate-300 text-xs">Location (optional)</Label>
              <Select value={importLocationId || '_global'} onValueChange={v => setImportLocationId(v === '_global' ? '' : v)}>
                <SelectTrigger className="bg-[#0f172a] border-white/15 text-slate-200"><SelectValue placeholder="Global" /></SelectTrigger>
                <SelectContent className="bg-[#1e293b] border-white/15">
                  <SelectItem value="_global" className="text-slate-200">Global</SelectItem>
                  {locations.map(l => <SelectItem key={l.id} value={l.id} className="text-slate-200">{l.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Label className="text-slate-300 text-xs">Trello JSON</Label>
                <Button size="sm" variant="outline" className="h-7 gap-1 text-xs border-white/15 text-slate-300 hover:bg-white/10"
                  onClick={() => trelloFileRef.current?.click()}>
                  <Upload size={12} /> Upload file
                </Button>
                <input ref={trelloFileRef} type="file" className="hidden" accept=".json"
                  onChange={e => { const f = e.target.files?.[0]; if (f) { const r = new FileReader(); r.onload = ev => setTrelloJson(ev.target.result); r.readAsText(f); } }} />
              </div>
              <Textarea rows={6} placeholder='Paste Trello board JSON here...'
                className="text-xs font-mono bg-[#0f172a] border-white/15 text-slate-200 placeholder:text-slate-500"
                value={trelloJson} onChange={e => setTrelloJson(e.target.value)} data-testid="trello-json-input" />
            </div>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1 border-white/15 text-slate-300 hover:bg-white/10" onClick={() => setShowTrelloImport(false)}>Cancel</Button>
              <Button className="flex-1 bg-blue-600 hover:bg-blue-700 text-white" onClick={importTrello} disabled={importing || !trelloJson.trim()} data-testid="import-trello-btn">
                {importing ? 'Importing...' : 'Import Board'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
