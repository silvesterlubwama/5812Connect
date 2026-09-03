import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Plus, Archive, RefreshCw, MapPin, Wifi, Trash2, Download, Upload, Globe, X, LayoutGrid, CalendarDays, CheckSquare, Settings, Users } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Switch } from '../components/ui/switch';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { boardsApi, tasksApi, locationsApi, adminApi } from '../services/api';
import { BulkActionBar, exportToCSV, SelectCheckbox } from '../components/BulkActions';
import { useAuth } from '../context/AuthContext';
import { useWebSocket } from '../context/WebSocketContext';
import { toast } from 'sonner';
import { dataEvents } from '../services/dataEvents';
import { KanbanList } from './kanban/KanbanList';
import { ArchivePanel } from './kanban/ArchivePanel';
import { CardDetailDialog } from './kanban/CardDetailDialog';
import { TeamCalendar } from './kanban/TeamCalendar';
import EmptyState from '../components/EmptyState';

export default function TasksPage() {
  const { user } = useAuth();
  const activeCampus = localStorage.getItem('5812_active_campus') || user?.location_id || '';
  const userLocs = user?.location_ids || (user?.location_id ? [user.location_id] : []);
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
  const [mobileBoardsOpen, setMobileBoardsOpen] = useState(false);
  const [newBoardForm, setNewBoardForm] = useState({ name: '', location_id: '', background: '#3b82f6', is_restricted: false, is_private: false });
  const [showBoardEdit, setShowBoardEdit] = useState(false);
  const [showTrelloImport, setShowTrelloImport] = useState(false);
  const [trelloJson, setTrelloJson] = useState('');
  const [importLocationId, setImportLocationId] = useState('');
  const [importing, setImporting] = useState(false);
  const [showArchive, setShowArchive] = useState(false);
  const [boardViewers, setBoardViewers] = useState([]);
  const trelloFileRef = useRef(null);
  const [viewMode, setViewMode] = useState('kanban'); // 'kanban' | 'calendar'
  const [allTasks, setAllTasks] = useState([]);
  const [selectedTaskIds, setSelectedTaskIds] = useState(new Set());

  const isAdmin = ['admin', 'system_admin', 'executive director', 'director'].includes((user?.role || '').toLowerCase());
  const canEdit = isAdmin || ['manager', 'coordinator', 'staff'].includes((user?.role || '').toLowerCase());

  // Staff filtered by board's location (if set), otherwise all staff
  const STAFF_ROLES = ['admin', 'system_admin', 'executive director', 'adviser', 'director',
                       'manager', 'leader', 'coordinator', 'staff', 'hr', 'volunteer'];
  const boardStaff = useMemo(() => {
    const staffOnly = staffUsers.filter(u => {
      const role = (u.role || '').toLowerCase();
      return STAFF_ROLES.includes(role);
    });
    if (!board || board.is_global || !board.location_id) return staffOnly;
    return staffOnly.filter(u => {
      if (u.location_id === board.location_id) return true;
      const userLocs = u.location_ids || [];
      return userLocs.includes(board.location_id);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [staffUsers, board]);

  // ===== LOAD DATA =====
  const fetchBoards = useCallback(async () => {
    try {
      const [bRes, lRes, uRes] = await Promise.all([
        boardsApi.list(),
        locationsApi.list().catch(() => ({ data: [] })),
        adminApi.userDirectory().catch(() => ({ data: [] })),
      ]);
      setBoards(bRes.data || []);
      setLocations(lRes.data || []);
      setStaffUsers(uRes.data || []);
      if (bRes.data?.length && !activeBoardId) setActiveBoardId(bRes.data[0].id);
    } catch { toast.error('Failed to load boards'); }
    finally { setLoading(false); }
  }, [activeBoardId]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchBoards(); }, []);

  // Refresh user directory when data changes
  useEffect(() => {
    const unsub = dataEvents.on('data-changed', (e) => {
      if (['users', 'members'].includes(e?.collection)) {
        adminApi.userDirectory().then(r => setStaffUsers(r.data || [])).catch(() => {});
      }
    });
    return unsub;
  }, []);

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
      // Optimistic update. Also refetch the board a beat later so we survive
      // any race where the WS broadcast lands before local state flushes and
      // the card never appears (iter 277 — user reported "new tasks aren't
      // saving"; server IS persisting them, the UI was hiding them).
      setTasks(prev => ({ ...prev, [listId]: [...(prev[listId] || []), res.data] }));
      setTimeout(() => { fetchBoardDetail(); }, 300);
      toast.success('Card added');
    } catch { toast.error('Failed to add card'); }
  }, [activeBoardId, board, tasks, fetchBoardDetail]);

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

  // ===== BULK OPERATIONS =====
  const [bulkMode, setBulkMode] = useState(false);
  const [selectedCards, setSelectedCards] = useState(new Set());

  const toggleBulkCard = (taskId) => {
    setSelectedCards(prev => {
      const next = new Set(prev);
      next.has(taskId) ? next.delete(taskId) : next.add(taskId);
      return next;
    });
  };
  const selectAllInList = (listId) => {
    const listTasks = tasks.filter(t => t.list_id === listId && !t.is_archived);
    setSelectedCards(prev => {
      const next = new Set(prev);
      listTasks.forEach(t => next.add(t.id));
      return next;
    });
  };
  const bulkArchive = async () => {
    if (selectedCards.size === 0) return;
    try {
      await tasksApi.bulkArchive([...selectedCards], true);
      toast.success(`${selectedCards.size} cards archived`);
      setSelectedCards(new Set()); setBulkMode(false); fetchBoards();
    } catch (e) { toast.error(e.message || 'Bulk archive failed'); }
  };
  const bulkMoveToList = async (targetListId, targetListName) => {
    if (selectedCards.size === 0) return;
    try {
      await tasksApi.bulkUpdate([...selectedCards], { list_id: targetListId });
      toast.success(`${selectedCards.size} cards moved`);
      setSelectedCards(new Set()); fetchBoards();
    } catch (e) { toast.error(e.message || 'Bulk move failed'); }
  };
  const bulkDelete = async () => {
    if (selectedCards.size === 0 || !window.confirm(`Delete ${selectedCards.size} cards permanently?`)) return;
    try {
      await tasksApi.bulkDelete([...selectedCards]);
      toast.success(`${selectedCards.size} cards deleted`);
      setSelectedCards(new Set()); setBulkMode(false); fetchBoards();
    } catch (e) { toast.error(e.message || 'Bulk delete failed'); }
  };
  const bulkExportCSV = async () => {
    try {
      const allTasksList = Object.values(tasks).flat();
      const selected = allTasksList.filter(t => selectedCards.has(t.id));
      exportToCSV(selected.length > 0 ? selected : allTasksList, 'tasks-export.csv');
      toast.success('Exported!');
    } catch (e) { toast.error(e.message || 'Export failed'); }
  };

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full" />
    </div>
  );

  const currentBoard = boards.find(b => b.id === activeBoardId);
  const accentColor = currentBoard?.background || '#3b82f6';

  return (
    <div className="flex h-full relative" style={{ minHeight: 'calc(100vh - 64px)', background: '#0f172a' }}>
      {/* Mobile backdrop when sidebar is open */}
      {mobileBoardsOpen && (
        <button
          aria-label="Close boards"
          className="fixed inset-0 z-30 bg-black/50 sm:hidden"
          onClick={() => setMobileBoardsOpen(false)}
        />
      )}
      {/* Sidebar — slide-in drawer on mobile, static column on ≥sm */}
      <div className={`w-56 flex-shrink-0 bg-[#1e293b] flex flex-col border-r border-white/10 fixed sm:static inset-y-0 left-0 z-40 transform transition-transform duration-200 sm:transform-none ${mobileBoardsOpen ? 'translate-x-0' : '-translate-x-full sm:translate-x-0'}`}>
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
          {boards.length === 0 && (
            <EmptyState
              compact
              icon={LayoutGrid}
              title="No boards yet"
              description="Boards group cards by team, project, or campus."
              action={{ label: 'New board', onClick: () => setShowNewBoard(true), testid: 'tasks-empty-create-board-btn' }}
              testid="tasks-boards-empty"
            />
          )}
          {boards.map(b => (
            <button key={b.id} onClick={() => { setActiveBoardId(b.id); setMobileBoardsOpen(false); }} data-testid={`board-tab-${b.id}`}
              className={`flex items-center gap-2 w-full px-2 py-2 rounded-md text-sm transition-all text-left group ${b.id === activeBoardId ? 'bg-white/15 text-white' : 'text-slate-400 hover:bg-white/8 hover:text-slate-200'}`}>
              <span className="w-3 h-3 rounded-sm flex-shrink-0" style={{ background: b.background || '#3b82f6' }} />
              <span className="flex-1 truncate text-xs">{b.name}</span>
              {/* Member avatars */}
              <div className="flex -space-x-1.5 shrink-0">
                {(b.tagged_members || []).slice(0, 3).map(uid => {
                  const s = staffUsers.find(u => u.id === uid);
                  const init = s ? (s.name || '?').charAt(0).toUpperCase() : '?';
                  return <div key={uid} className="w-5 h-5 rounded-full bg-primary/30 border border-slate-700 flex items-center justify-center text-[8px] font-bold text-white" title={s?.name || uid}>{init}</div>;
                })}
                {(b.tagged_members || []).length > 3 && <div className="w-5 h-5 rounded-full bg-slate-600 border border-slate-700 flex items-center justify-center text-[8px] text-white">+{b.tagged_members.length - 3}</div>}
              </div>
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
          <TeamCalendar boards={boards} allTasks={allTasks} staffUsers={staffUsers} onCardClick={setOpenCard} onRefresh={fetchBoards} />
        ) : (
        <>
        {currentBoard && (
          <div className="flex items-center justify-between px-3 sm:px-5 py-3 flex-shrink-0 border-b border-white/10" style={{ background: 'rgba(255,255,255,0.04)' }}>
            <div className="flex items-center gap-2 sm:gap-3 min-w-0">
              <button
                aria-label="Open boards"
                data-testid="mobile-boards-toggle"
                className="sm:hidden p-1.5 rounded text-slate-300 hover:bg-white/10"
                onClick={() => setMobileBoardsOpen(true)}
              >
                <LayoutGrid size={16} />
              </button>
              <span className="w-4 h-4 rounded flex-shrink-0" style={{ background: accentColor }} />
              <h2 className="text-base font-semibold text-white truncate">{currentBoard.name}</h2>
              {currentBoard.location_name && <span className="hidden sm:flex items-center gap-1 text-xs text-slate-400"><MapPin size={11} /> {currentBoard.location_name}</span>}
              {boardViewers.length > 1 && <span className="hidden sm:flex items-center gap-1 text-xs text-emerald-400"><Wifi size={11} /> {boardViewers.length} viewing</span>}
              {currentBoard.is_shared && <span className="hidden sm:inline text-xs text-blue-400 px-2 py-0.5 bg-blue-500/10 rounded">Shared</span>}
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="ghost" className="text-slate-400 hover:text-white hover:bg-white/10 gap-1.5 h-8 text-xs"
                data-testid="share-board-btn"
                onClick={async () => {
                  try {
                    const res = await boardsApi.update(currentBoard.id, { is_shared: !currentBoard.is_shared });
                    const updated = res.data;
                    if (updated.is_shared) {
                      const url = `${window.location.origin}/shared/${updated.share_token}`;
                      navigator.clipboard.writeText(url).catch(() => {});
                      toast.success('Share link copied! Anyone with the link can view this board.');
                    } else {
                      toast.success('Sharing disabled');
                    }
                    fetchBoards();
                  } catch { toast.error('Failed to update sharing'); }
                }}>
                <Globe size={13} /> {currentBoard.is_shared ? 'Unshare' : 'Share'}
              </Button>
              {/* Board Edit/Settings */}
              <Button size="sm" variant="ghost" className="text-slate-400 hover:text-white hover:bg-white/10 gap-1.5 h-8 text-xs" onClick={() => { setNewBoardForm({ name: currentBoard.name, location_id: currentBoard.location_id || '', background: currentBoard.background || '#3b82f6', is_restricted: currentBoard.is_restricted || false, is_private: currentBoard.is_private || false }); setShowBoardEdit(true); }} data-testid="board-settings-btn">
                <Settings size={13} /> Edit Board
              </Button>
              <Button size="sm" variant="ghost" className={`text-xs h-8 gap-1.5 ${bulkMode ? 'bg-blue-500/20 text-blue-400' : 'text-slate-400 hover:text-white hover:bg-white/10'}`}
                onClick={() => { setBulkMode(!bulkMode); setSelectedCards(new Set()); }} data-testid="bulk-mode-btn">
                <CheckSquare size={13} /> {bulkMode ? `${selectedCards.size} selected` : 'Multi-select'}
              </Button>
              {bulkMode && selectedCards.size > 0 && (
                <>
                  <Button size="sm" variant="ghost" className="text-amber-400 hover:bg-amber-500/10 h-8 text-xs gap-1.5" onClick={bulkArchive} data-testid="bulk-archive-btn">
                    <Archive size={13} /> Archive
                  </Button>
                  <Select onValueChange={(v) => {
                    const list = (board?.lists || []).find(l => l.id === v);
                    if (list) bulkMoveToList(list.id, list.name);
                  }}>
                    <SelectTrigger className="h-8 w-auto text-xs bg-transparent border-white/10 text-slate-300" data-testid="bulk-move-select"><SelectValue placeholder="Move to..." /></SelectTrigger>
                    <SelectContent>{(board?.lists || []).map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
                  </Select>
                  <Button size="sm" variant="ghost" className="text-red-400 hover:bg-red-500/10 h-8 text-xs" onClick={bulkDelete} data-testid="bulk-delete-btn">
                    <Trash2 size={13} />
                  </Button>
                </>
              )}
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
                onArchiveList={archiveList} onDeleteList={deleteList} onRenameList={renameList}
                bulkMode={bulkMode} selectedCards={selectedCards} toggleBulkCard={toggleBulkCard} selectAllInList={selectAllInList} />
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
                  {locations.filter(l => !activeCampus || l.id === activeCampus || l.parent_id === activeCampus).map(l => <SelectItem key={l.id} value={l.id} className="text-slate-200">{l.name}</SelectItem>)}
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
                  {locations.filter(l => !activeCampus || l.id === activeCampus || l.parent_id === activeCampus).map(l => <SelectItem key={l.id} value={l.id} className="text-slate-200">{l.name}</SelectItem>)}
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

      {/* Board Edit Dialog */}
      <Dialog open={showBoardEdit} onOpenChange={setShowBoardEdit}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Edit Board: {currentBoard?.name}</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Board Name</Label><Input value={newBoardForm.name} onChange={e => setNewBoardForm({...newBoardForm, name: e.target.value})} data-testid="edit-board-name" /></div>
            <div className="space-y-2"><Label>Campus / Location</Label>
              <Select value={newBoardForm.location_id || '__none__'} onValueChange={v => setNewBoardForm({...newBoardForm, location_id: v === '__none__' ? '' : v})}>
                <SelectTrigger><SelectValue placeholder="Global (all campuses)" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Global (all campuses)</SelectItem>
                  {locations.filter(l => !activeCampus || l.id === activeCampus || l.parent_id === activeCampus).map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2"><Label>Background Color</Label>
              <div className="flex gap-2">
                {['#3b82f6','#22c55e','#f59e0b','#ef4444','#8b5cf6','#ec4899','#14b8a6','#f97316','#0ea5e9'].map(c => (
                  <button key={c} className={`w-7 h-7 rounded-full border-2 ${newBoardForm.background === c ? 'border-white' : 'border-transparent'}`} style={{background: c}} onClick={() => setNewBoardForm({...newBoardForm, background: c})} />
                ))}
              </div>
            </div>
            <div className="space-y-3 p-3 border border-border rounded-lg">
              <div className="flex items-center justify-between"><Label className="text-sm">Restricted</Label>
                <Switch checked={newBoardForm.is_restricted || false} onCheckedChange={v => setNewBoardForm({...newBoardForm, is_restricted: v})} /></div>
              <div className="flex items-center justify-between"><Label className="text-sm">Private</Label>
                <Switch checked={newBoardForm.is_private || false} onCheckedChange={v => setNewBoardForm({...newBoardForm, is_private: v})} /></div>
              <p className="text-[10px] text-muted-foreground">Restricted/Private boards are only visible to tagged members</p>
            </div>
            {/* Board Members */}
            <div className="space-y-2"><Label>Assign Members</Label>
              <Select onValueChange={v => {
                if (v && !(currentBoard?.tagged_members || []).includes(v)) {
                  boardsApi.update(currentBoard.id, { tagged_members: [...(currentBoard?.tagged_members || []), v] }).then(() => { fetchBoards(); toast.success('Member added'); }).catch(() => toast.error('Failed'));
                }
              }}>
                <SelectTrigger><SelectValue placeholder="Add staff to board..." /></SelectTrigger>
                {/* iter 260 — scope the picker to the board's own location
                    when set. Same rule as the assignee dropdown so admins
                    don't accidentally tag a staffer from another campus.
                    Global boards fall through to the full staff list. */}
                <SelectContent>{staffUsers
                  .filter(s => {
                    const role = (s.role || '').toLowerCase();
                    if (!STAFF_ROLES.includes(role)) return false;
                    if (!currentBoard || currentBoard.is_global || !currentBoard.location_id) return true;
                    if (s.location_id === currentBoard.location_id) return true;
                    return (s.location_ids || []).includes(currentBoard.location_id);
                  })
                  .filter(s => !(currentBoard?.tagged_members || []).includes(s.id))
                  .map(s => (
                    <SelectItem key={s.id} value={s.id}>{s.name} ({s.role})</SelectItem>
                  ))}</SelectContent>
              </Select>
              <div className="flex flex-wrap gap-1 mt-1">
                {(currentBoard?.tagged_members || []).map(uid => {
                  const s = staffUsers.find(u => u.id === uid);
                  return s ? <Badge key={uid} variant="secondary" className="text-xs gap-1 cursor-pointer" onClick={() => {
                    boardsApi.update(currentBoard.id, { tagged_members: (currentBoard.tagged_members || []).filter(m => m !== uid) }).then(() => { fetchBoards(); toast.success('Removed'); }).catch(() => toast.error('Failed'));
                  }}>{s.name} &times;</Badge> : null;
                })}
              </div>
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowBoardEdit(false)}>Cancel</Button>
              <Button className="flex-1" onClick={async () => {
                try {
                  const loc = locations.find(l => l.id === newBoardForm.location_id);
                  await boardsApi.update(currentBoard.id, { name: newBoardForm.name, location_id: newBoardForm.location_id, location_name: loc?.name || '', background: newBoardForm.background, is_restricted: newBoardForm.is_restricted, is_private: newBoardForm.is_private, is_global: !newBoardForm.location_id });
                  toast.success('Board updated');
                  setShowBoardEdit(false); fetchBoards();
                } catch { toast.error('Failed'); }
              }} data-testid="save-board-edit">Save</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
