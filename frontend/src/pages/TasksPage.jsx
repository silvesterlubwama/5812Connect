import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Plus, MoreHorizontal, X, Edit2, Trash2, Check, Upload,
  Flag, Calendar, Tag, AlignLeft, CheckSquare, Paperclip,
  RefreshCw, MapPin, Globe, Download, Archive, RotateCcw,
  Users, Link, Eye, ChevronRight, Search, Wifi, Bluetooth
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { boardsApi, tasksApi, membersApi, locationsApi, adminApi } from '../services/api';
import { tasksExtApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useWebSocket } from '../context/WebSocketContext';
import { toast } from 'sonner';

const PRIORITY_COLORS = { low: '#10b981', medium: '#f59e0b', high: '#f97316', urgent: '#ef4444' };
const LABEL_COLORS = ['#10b981','#f59e0b','#f97316','#ef4444','#8b5cf6','#3b82f6','#06b6d4','#84cc16','#ec4899','#6366f1'];

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

  // UI state
  const [addingCard, setAddingCard] = useState(null);
  const [newCardTitle, setNewCardTitle] = useState('');
  const [addingList, setAddingList] = useState(false);
  const [newListName, setNewListName] = useState('');
  const [editingListId, setEditingListId] = useState(null);
  const [editingListName, setEditingListName] = useState('');
  const [openListMenu, setOpenListMenu] = useState(null);
  const [dragging, setDragging] = useState(null);
  const [dragOver, setDragOver] = useState(null);

  // Card detail
  const [openCard, setOpenCard] = useState(null);
  const [cardEdit, setCardEdit] = useState({});
  const [savingCard, setSavingCard] = useState(false);
  const [newCheckItem, setNewCheckItem] = useState('');
  const cardFileRef = useRef(null);
  const [uploadingAttachment, setUploadingAttachment] = useState(false);

  // Board management
  const [showNewBoard, setShowNewBoard] = useState(false);
  const [newBoardForm, setNewBoardForm] = useState({ name: '', location_id: '', background: '#3b82f6' });
  const [showTrelloImport, setShowTrelloImport] = useState(false);
  const [trelloJson, setTrelloJson] = useState('');
  const [importLocationId, setImportLocationId] = useState('');
  const [importing, setImporting] = useState(false);
  const trelloFileRef = useRef(null);

  // Archive panel
  const [showArchive, setShowArchive] = useState(false);
  const [archivedCards, setArchivedCards] = useState([]);
  const [archivedLists, setArchivedLists] = useState([]);
  const [archiveTab, setArchiveTab] = useState('cards');

  // WS presence
  const [boardViewers, setBoardViewers] = useState([]);

  const isAdmin = ['admin', 'system_admin', 'executive director', 'director'].includes((user?.role || '').toLowerCase());
  const canEdit = isAdmin || ['manager', 'coordinator'].includes((user?.role || '').toLowerCase());

  // ===== FETCH INITIAL DATA =====
  const fetchBoards = useCallback(async () => {
    try {
      const [bRes, lRes, uRes] = await Promise.all([
        boardsApi.list(),
        locationsApi.list().catch(() => ({ data: [] })),
        adminApi.users({ limit: 200 }).catch(() => ({ data: [] })),
      ]);
      setBoards(bRes.data || []);
      setLocations(lRes.data || []);
      setStaffUsers(uRes.data || []);
      if (bRes.data?.length && !activeBoardId) {
        setActiveBoardId(bRes.data[0].id);
      }
    } catch { toast.error('Failed to load boards'); }
    finally { setLoading(false); }
  }, [activeBoardId]);

  useEffect(() => { fetchBoards(); }, []);

  // ===== FETCH BOARD DETAIL =====
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
      for (const lid of Object.keys(grouped)) {
        grouped[lid].sort((a, b) => (a.position || 0) - (b.position || 0));
      }
      setTasks(grouped);
    } catch { toast.error('Failed to load board'); }
  }, [activeBoardId]);

  useEffect(() => { fetchBoardDetail(); }, [fetchBoardDetail]);

  // ===== WEBSOCKET BOARD ROOM =====
  useEffect(() => {
    if (!activeBoardId) return;
    if (prevBoardRef.current && prevBoardRef.current !== activeBoardId) {
      leaveBoard(prevBoardRef.current);
    }
    prevBoardRef.current = activeBoardId;
    // Delay slightly to ensure WS is connected
    const t = setTimeout(() => joinBoard(activeBoardId), 800);
    return () => {
      clearTimeout(t);
      leaveBoard(activeBoardId);
    };
  }, [activeBoardId, joinBoard, leaveBoard]);

  // Listen for board events
  useEffect(() => {
    const unsubBoardEvent = addListener('board_event', (data) => {
      if (data.board_id !== activeBoardId) return;
      const action = data.action;
      if (action === 'card_created') {
        setTasks(prev => {
          const next = { ...prev };
          const lid = data.list_id || '__none__';
          if (!next[lid]) next[lid] = [];
          if (!next[lid].find(t => t.id === data.task?.id)) {
            next[lid] = [...next[lid], data.task];
          }
          return next;
        });
      } else if (action === 'card_updated') {
        setTasks(prev => {
          const next = { ...prev };
          for (const lid of Object.keys(next)) {
            next[lid] = next[lid].map(t => t.id === data.task_id ? { ...t, ...data.task } : t);
          }
          return next;
        });
        if (openCard?.id === data.task_id) {
          setOpenCard(prev => ({ ...prev, ...data.task }));
        }
      } else if (action === 'card_moved') {
        setTasks(prev => {
          const next = { ...prev };
          const from = data.from_list_id;
          const to = data.to_list_id;
          if (from && next[from]) next[from] = next[from].filter(t => t.id !== data.task_id);
          if (to) {
            if (!next[to]) next[to] = [];
            if (!next[to].find(t => t.id === data.task_id) && data.task) {
              next[to] = [...next[to], data.task];
            }
          }
          return next;
        });
      } else if (action === 'card_deleted' || action === 'card_archived') {
        setTasks(prev => {
          const next = { ...prev };
          for (const lid of Object.keys(next)) {
            next[lid] = next[lid].filter(t => t.id !== data.task_id);
          }
          return next;
        });
        if (openCard?.id === data.task_id) setOpenCard(null);
      } else if (action === 'card_restored') {
        setTasks(prev => {
          const next = { ...prev };
          const lid = data.list_id || '__none__';
          if (!next[lid]) next[lid] = [];
          if (!next[lid].find(t => t.id === data.task_id) && data.task) {
            next[lid] = [...next[lid], data.task];
          }
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
    return () => { unsubBoardEvent(); unsubPresence(); };
  }, [activeBoardId, addListener, openCard]);

  // ===== BOARD ACTIONS =====
  const createBoard = async () => {
    if (!newBoardForm.name.trim()) return;
    try {
      const loc = locations.find(l => l.id === newBoardForm.location_id);
      const res = await boardsApi.create({ ...newBoardForm, location_name: loc?.name || '' });
      toast.success(`Board "${res.data.name}" created`);
      setShowNewBoard(false);
      setNewBoardForm({ name: '', location_id: '', background: '#3b82f6' });
      setBoards(prev => [res.data, ...prev]);
      setActiveBoardId(res.data.id);
    } catch { toast.error('Failed to create board'); }
  };

  const deleteBoard = async (boardId) => {
    if (!window.confirm('Delete this board and all its cards?')) return;
    try {
      await boardsApi.delete(boardId);
      setBoards(prev => prev.filter(b => b.id !== boardId));
      if (activeBoardId === boardId) {
        const remaining = boards.filter(b => b.id !== boardId);
        setActiveBoardId(remaining[0]?.id || null);
      }
      toast.success('Board deleted');
    } catch { toast.error('Failed to delete board'); }
  };

  // ===== LIST ACTIONS =====
  const addList = async () => {
    if (!newListName.trim() || !activeBoardId) return;
    try {
      const res = await boardsApi.addList(activeBoardId, { name: newListName.trim() });
      setBoard(prev => ({ ...prev, lists: [...(prev?.lists || []), res.data] }));
      setTasks(prev => ({ ...prev, [res.data.id]: [] }));
      setAddingList(false);
      setNewListName('');
    } catch { toast.error('Failed to add list'); }
  };

  const renameList = async (listId) => {
    if (!editingListName.trim()) { setEditingListId(null); return; }
    try {
      await boardsApi.updateList(activeBoardId, listId, { name: editingListName.trim() });
      setBoard(prev => ({ ...prev, lists: prev.lists.map(l => l.id === listId ? { ...l, name: editingListName.trim() } : l) }));
    } catch { toast.error('Failed to rename'); }
    setEditingListId(null);
  };

  const archiveList = async (listId) => {
    setOpenListMenu(null);
    try {
      await boardsApi.archiveList(activeBoardId, listId);
      setBoard(prev => ({ ...prev, lists: prev.lists.filter(l => l.id !== listId) }));
      setTasks(prev => { const n = { ...prev }; delete n[listId]; return n; });
      toast.success('List archived');
    } catch { toast.error('Failed to archive list'); }
  };

  const deleteList = async (listId) => {
    setOpenListMenu(null);
    if (!window.confirm('Delete this list and its cards?')) return;
    try {
      await boardsApi.deleteList(activeBoardId, listId);
      setBoard(prev => ({ ...prev, lists: prev.lists.filter(l => l.id !== listId) }));
      setTasks(prev => { const n = { ...prev }; delete n[listId]; return n; });
      toast.success('List deleted');
    } catch { toast.error('Failed to delete list'); }
  };

  // ===== CARD ACTIONS =====
  const addCard = async (listId) => {
    if (!newCardTitle.trim()) { setAddingCard(null); return; }
    try {
      const list = board?.lists?.find(l => l.id === listId);
      const pos = tasks[listId]?.length || 0;
      const res = await tasksApi.create({
        title: newCardTitle.trim(),
        board_id: activeBoardId,
        list_id: listId,
        list_name: list?.name || '',
        status: 'todo',
        position: pos,
        assignees: [],
        labels: [],
        checklist: [],
        attachments: [],
      });
      setTasks(prev => ({ ...prev, [listId]: [...(prev[listId] || []), res.data] }));
      setNewCardTitle('');
      setAddingCard(null);
    } catch { toast.error('Failed to add card'); }
  };

  const deleteCard = async (task) => {
    if (!window.confirm('Delete this card permanently?')) return;
    const listId = task.list_id;
    try {
      await tasksApi.delete(task.id);
      setTasks(prev => ({ ...prev, [listId]: (prev[listId] || []).filter(t => t.id !== task.id) }));
      if (openCard?.id === task.id) setOpenCard(null);
      toast.success('Card deleted');
    } catch { toast.error('Failed to delete card'); }
  };

  const archiveCard = async (task) => {
    const listId = task.list_id;
    try {
      await tasksExtApi.archive(task.id);
      setTasks(prev => ({ ...prev, [listId]: (prev[listId] || []).filter(t => t.id !== task.id) }));
      if (openCard?.id === task.id) setOpenCard(null);
      toast.success('Card archived');
    } catch { toast.error('Failed to archive card'); }
  };

  const openCardDetail = (task) => {
    setOpenCard(task);
    setCardEdit({
      title: task.title || '',
      description: task.description || '',
      priority: task.priority || 'medium',
      due_date: task.due_date || '',
      assignee: task.assignee || '',
      assignees: task.assignees || [],
      labels: task.labels || [],
      checklist: task.checklist || [],
      attachments: task.attachments || [],
    });
  };

  const saveCardEdit = async () => {
    if (!openCard) return;
    setSavingCard(true);
    try {
      const res = await tasksApi.update(openCard.id, cardEdit);
      const updated = res.data;
      setTasks(prev => {
        const newState = { ...prev };
        for (const lid of Object.keys(newState)) {
          newState[lid] = newState[lid].map(t => t.id === openCard.id ? { ...t, ...updated } : t);
        }
        return newState;
      });
      setOpenCard({ ...openCard, ...updated });
      toast.success('Saved');
    } catch { toast.error('Save failed'); }
    finally { setSavingCard(false); }
  };

  const toggleCheckItem = async (idx) => {
    const checklist = [...(cardEdit.checklist || [])];
    checklist[idx] = { ...checklist[idx], completed: !checklist[idx].completed };
    setCardEdit({ ...cardEdit, checklist });
  };

  const addCheckItem = () => {
    if (!newCheckItem.trim()) return;
    const checklist = [...(cardEdit.checklist || []), { text: newCheckItem.trim(), completed: false }];
    setCardEdit({ ...cardEdit, checklist });
    setNewCheckItem('');
  };

  const moveCardToList = async (task, fromListId, toListId) => {
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
  };

  // ===== ATTACHMENT UPLOAD =====
  const handleAttachFile = async (e) => {
    if (!openCard) return;
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingAttachment(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await tasksExtApi.uploadAttachment(openCard.id, formData);
      const newAtt = res.data;
      const updatedAttachments = [...(cardEdit.attachments || []), newAtt];
      setCardEdit({ ...cardEdit, attachments: updatedAttachments });
      setOpenCard({ ...openCard, attachments: updatedAttachments });
      toast.success(`Attached: ${file.name}`);
    } catch { toast.error('Upload failed'); }
    finally { setUploadingAttachment(false); }
  };

  const removeAttachment = async (attId) => {
    if (!openCard) return;
    try {
      await tasksExtApi.deleteAttachment(openCard.id, attId);
      const updated = (cardEdit.attachments || []).filter(a => a.id !== attId);
      setCardEdit({ ...cardEdit, attachments: updated });
      setOpenCard({ ...openCard, attachments: updated });
    } catch { toast.error('Failed to remove attachment'); }
  };

  // ===== DRAG & DROP =====
  const onDragStart = (e, task, fromListId) => {
    setDragging({ task, fromListId });
    e.dataTransfer.effectAllowed = 'move';
  };
  const onDragOver = (e, listId, idx) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOver({ listId, idx });
  };
  const onDrop = (e, toListId) => {
    e.preventDefault();
    if (!dragging) return;
    moveCardToList(dragging.task, dragging.fromListId, toListId);
    setDragging(null);
    setDragOver(null);
  };
  const onDragEnd = () => { setDragging(null); setDragOver(null); };

  // ===== TRELLO IMPORT =====
  const handleTrelloFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => setTrelloJson(ev.target.result);
    reader.readAsText(file);
  };

  const importTrello = async () => {
    if (!trelloJson.trim()) { toast.error('Paste or upload a Trello JSON export'); return; }
    setImporting(true);
    try {
      const parsed = JSON.parse(trelloJson);
      if (importLocationId) parsed.location_id = importLocationId;
      const res = await boardsApi.importTrello(parsed);
      toast.success(`Imported "${res.data.board_name}": ${res.data.lists} lists, ${res.data.imported} cards`);
      setShowTrelloImport(false);
      setTrelloJson('');
      await fetchBoards();
      setActiveBoardId(res.data.board_id);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Import failed — check JSON format');
    } finally { setImporting(false); }
  };

  // ===== ARCHIVE PANEL =====
  const openArchivePanel = async () => {
    try {
      const [cardsRes, listsRes] = await Promise.all([
        tasksExtApi.archived(activeBoardId),
        boardsApi.archivedLists(activeBoardId),
      ]);
      setArchivedCards(cardsRes.data || []);
      setArchivedLists(listsRes.data || []);
      setShowArchive(true);
    } catch { toast.error('Failed to load archived items'); }
  };

  const restoreCard = async (task) => {
    try {
      const res = await tasksExtApi.restore(task.id);
      setArchivedCards(prev => prev.filter(c => c.id !== task.id));
      const restored = res.data;
      if (restored && restored.list_id) {
        setTasks(prev => {
          const next = { ...prev };
          if (!next[restored.list_id]) next[restored.list_id] = [];
          if (!next[restored.list_id].find(t => t.id === restored.id)) {
            next[restored.list_id] = [...next[restored.list_id], restored];
          }
          return next;
        });
      }
      toast.success('Card restored');
    } catch { toast.error('Failed to restore card'); }
  };

  const restoreList = async (list) => {
    try {
      const res = await boardsApi.restoreList(activeBoardId, list.id);
      setArchivedLists(prev => prev.filter(l => l.id !== list.id));
      setBoard(prev => prev ? { ...prev, lists: [...(prev.lists || []), res.data] } : prev);
      setTasks(prev => ({ ...prev, [list.id]: prev[list.id] || [] }));
      toast.success('List restored');
    } catch { toast.error('Failed to restore list'); }
  };

  // ===== RENDER =====
  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full" />
    </div>
  );

  const currentBoard = boards.find(b => b.id === activeBoardId);
  const accentColor = currentBoard?.background || '#3b82f6';

  return (
    <div className="flex h-full" style={{ minHeight: 'calc(100vh - 64px)', background: '#0f172a' }}>
      {/* ===== LEFT SIDEBAR ===== */}
      <div className="w-56 flex-shrink-0 bg-[#1e293b] flex flex-col border-r border-white/10">
        <div className="p-3 border-b border-white/10">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-2">Boards</p>
          {canEdit && (
            <button
              onClick={() => setShowNewBoard(true)}
              data-testid="create-board-btn"
              className="flex items-center gap-2 w-full px-2 py-1.5 rounded text-xs text-slate-400 hover:bg-white/10 hover:text-white transition-colors"
            >
              <Plus size={13} /> New Board
            </button>
          )}
        </div>
        <div className="flex-1 overflow-y-auto py-2 space-y-0.5 px-2">
          {boards.length === 0 && (
            <p className="text-xs text-slate-500 px-2 py-3 text-center">No boards yet</p>
          )}
          {boards.map(b => (
            <button
              key={b.id}
              onClick={() => setActiveBoardId(b.id)}
              data-testid={`board-tab-${b.id}`}
              className={`flex items-center gap-2 w-full px-2 py-2 rounded-md text-sm transition-all text-left group ${b.id === activeBoardId ? 'bg-white/15 text-white' : 'text-slate-400 hover:bg-white/8 hover:text-slate-200'}`}
            >
              <span className="w-3 h-3 rounded-sm flex-shrink-0" style={{ background: b.background || '#3b82f6' }} />
              <span className="flex-1 truncate text-xs">{b.name}</span>
              <span className="text-[10px] opacity-50 flex-shrink-0">{b.card_count || 0}</span>
            </button>
          ))}
        </div>
        <div className="p-3 border-t border-white/10 space-y-1">
          <button
            onClick={() => setShowTrelloImport(true)}
            className="flex items-center gap-2 w-full px-2 py-1.5 rounded text-xs text-slate-400 hover:bg-white/10 hover:text-white transition-colors"
          >
            <Download size={12} /> Import Trello
          </button>
        </div>
      </div>

      {/* ===== MAIN BOARD AREA ===== */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Board header */}
        {currentBoard && (
          <div className="flex items-center justify-between px-5 py-3 flex-shrink-0 border-b border-white/10"
            style={{ background: 'rgba(255,255,255,0.04)' }}>
            <div className="flex items-center gap-3">
              <span className="w-4 h-4 rounded" style={{ background: accentColor }} />
              <h2 className="text-base font-semibold text-white">{currentBoard.name}</h2>
              {currentBoard.location_name && (
                <span className="flex items-center gap-1 text-xs text-slate-400">
                  <MapPin size={11} /> {currentBoard.location_name}
                </span>
              )}
              {boardViewers.length > 1 && (
                <span className="flex items-center gap-1 text-xs text-emerald-400">
                  <Wifi size={11} /> {boardViewers.length} viewing
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="ghost" className="text-slate-400 hover:text-white hover:bg-white/10 gap-1.5 h-8 text-xs"
                onClick={openArchivePanel}>
                <Archive size={13} /> Archive
              </Button>
              {isAdmin && (
                <Button size="sm" variant="ghost" className="text-slate-400 hover:text-red-400 hover:bg-red-500/10 h-8 text-xs"
                  onClick={() => deleteBoard(activeBoardId)}>
                  <Trash2 size={13} />
                </Button>
              )}
              <Button size="sm" variant="ghost" className="text-slate-400 hover:text-white hover:bg-white/10 h-8"
                onClick={fetchBoardDetail}>
                <RefreshCw size={13} />
              </Button>
            </div>
          </div>
        )}

        {/* Board canvas */}
        {!activeBoardId || !board ? (
          <div className="flex flex-col items-center justify-center flex-1 gap-4 text-slate-500">
            <p className="text-lg">No board selected</p>
            <Button onClick={() => setShowNewBoard(true)} className="gap-2 bg-blue-600 hover:bg-blue-700 text-white">
              <Plus size={16} /> Create Board
            </Button>
          </div>
        ) : (
          <div className="flex gap-4 p-5 overflow-x-auto flex-1 items-start">
            {(board.lists || []).map(list => {
              const listTasks = tasks[list.id] || [];
              return (
                <KanbanList
                  key={list.id}
                  list={list}
                  listTasks={listTasks}
                  accentColor={accentColor}
                  editingListId={editingListId}
                  editingListName={editingListName}
                  setEditingListId={setEditingListId}
                  setEditingListName={setEditingListName}
                  renameList={renameList}
                  openListMenu={openListMenu}
                  setOpenListMenu={setOpenListMenu}
                  archiveList={archiveList}
                  deleteList={deleteList}
                  addingCard={addingCard}
                  setAddingCard={setAddingCard}
                  newCardTitle={newCardTitle}
                  setNewCardTitle={setNewCardTitle}
                  addCard={addCard}
                  staffUsers={staffUsers}
                  dragging={dragging}
                  dragOver={dragOver}
                  onDragStart={onDragStart}
                  onDragEnd={onDragEnd}
                  onDragOver={onDragOver}
                  onDrop={onDrop}
                  openCardDetail={openCardDetail}
                  archiveCard={archiveCard}
                  canEdit={canEdit}
                />
              );
            })}

            {/* Add List */}
            {canEdit && (
              <div className="flex-shrink-0 w-64">
                {addingList ? (
                  <div className="rounded-xl bg-[#1e293b] border border-white/10 p-3 space-y-2">
                    <Input
                      autoFocus
                      placeholder="List name..."
                      className="bg-[#0f172a] border-white/20 text-white placeholder:text-slate-500 text-sm h-8"
                      value={newListName}
                      onChange={e => setNewListName(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') addList(); if (e.key === 'Escape') setAddingList(false); }}
                      data-testid="new-list-input"
                    />
                    <div className="flex gap-2">
                      <Button size="sm" className="h-7 bg-blue-600 hover:bg-blue-700 text-white text-xs" onClick={addList} data-testid="add-list-confirm-btn">Add List</Button>
                      <Button size="sm" variant="ghost" className="h-7 text-slate-400 hover:text-white" onClick={() => setAddingList(false)}><X size={13} /></Button>
                    </div>
                  </div>
                ) : (
                  <button
                    data-testid="add-list-btn"
                    onClick={() => setAddingList(true)}
                    className="flex items-center gap-2 w-full px-4 py-3 rounded-xl bg-white/8 hover:bg-white/12 text-sm font-medium text-slate-400 hover:text-white transition-all border border-white/10 border-dashed"
                  >
                    <Plus size={16} /> Add another list
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ===== CARD DETAIL DIALOG ===== */}
      <Dialog open={!!openCard} onOpenChange={o => { if (!o) { setOpenCard(null); setCardEdit({}); } }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto bg-[#1e293b] border-white/10 text-slate-100">
          {openCard && (
            <>
              {openCard.cover_color && (
                <div className="h-10 rounded-t-lg -mx-6 -mt-6 mb-3" style={{ background: openCard.cover_color }} />
              )}
              <DialogHeader>
                <DialogTitle className="text-slate-100">
                  <Input
                    data-testid="card-title-input"
                    className="text-base font-semibold border-0 shadow-none p-0 focus-visible:ring-0 bg-transparent text-white placeholder:text-slate-400"
                    value={cardEdit.title || ''}
                    onChange={e => setCardEdit({ ...cardEdit, title: e.target.value })}
                    onBlur={saveCardEdit}
                  />
                </DialogTitle>
              </DialogHeader>

              <div className="grid grid-cols-3 gap-5 mt-2">
                {/* Main column */}
                <div className="col-span-2 space-y-5">
                  {/* Labels */}
                  {(cardEdit.labels || []).length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {(cardEdit.labels || []).map((lbl, i) => (
                        <span key={i} className="px-2.5 py-0.5 rounded text-xs font-medium text-white"
                          style={{ background: lbl.color || '#3b82f6' }}>
                          {lbl.name || lbl}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Description */}
                  <div className="space-y-2">
                    <Label className="flex items-center gap-2 text-sm font-semibold text-slate-300">
                      <AlignLeft size={14} /> Description
                    </Label>
                    <Textarea
                      data-testid="card-description"
                      rows={3}
                      placeholder="Add a description..."
                      className="bg-[#0f172a] border-white/15 text-slate-200 placeholder:text-slate-500 text-sm resize-none"
                      value={cardEdit.description || ''}
                      onChange={e => setCardEdit({ ...cardEdit, description: e.target.value })}
                      onBlur={saveCardEdit}
                    />
                  </div>

                  {/* Checklist */}
                  {(cardEdit.checklist || []).length > 0 && (
                    <div className="space-y-2">
                      <Label className="flex items-center gap-2 text-sm font-semibold text-slate-300">
                        <CheckSquare size={14} /> Checklist
                        <span className="text-xs text-slate-500 ml-1">
                          {(cardEdit.checklist || []).filter(i => i.completed).length}/{(cardEdit.checklist || []).length}
                        </span>
                      </Label>
                      <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-emerald-500 transition-all"
                          style={{ width: `${((cardEdit.checklist || []).filter(i => i.completed).length / (cardEdit.checklist || []).length) * 100}%` }}
                        />
                      </div>
                      <div className="space-y-1.5">
                        {(cardEdit.checklist || []).map((item, i) => (
                          <div key={i} className="flex items-center gap-2 group">
                            <input type="checkbox" checked={item.completed} className="h-4 w-4 rounded accent-emerald-500"
                              onChange={() => toggleCheckItem(i)} />
                            <span className={`text-sm flex-1 ${item.completed ? 'line-through text-slate-500' : 'text-slate-200'}`}>{item.text}</span>
                            <button className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400"
                              onClick={() => { const cl = [...(cardEdit.checklist || [])]; cl.splice(i, 1); setCardEdit({ ...cardEdit, checklist: cl }); }}>
                              <X size={12} />
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Add checklist item */}
                  <div className="flex gap-2">
                    <Input
                      placeholder="Add checklist item..."
                      className="h-8 text-sm bg-[#0f172a] border-white/15 text-slate-200 placeholder:text-slate-500"
                      value={newCheckItem}
                      onChange={e => setNewCheckItem(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') addCheckItem(); }}
                      data-testid="new-check-item"
                    />
                    <Button size="sm" className="h-8 bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs" onClick={addCheckItem}>Add</Button>
                  </div>

                  {/* Attachments */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label className="flex items-center gap-2 text-sm font-semibold text-slate-300">
                        <Paperclip size={14} /> Attachments
                        {(cardEdit.attachments || []).length > 0 && (
                          <span className="text-xs text-slate-500">({(cardEdit.attachments || []).length})</span>
                        )}
                      </Label>
                      <div>
                        <Button size="sm" variant="ghost"
                          className="h-7 text-xs text-slate-400 hover:text-white gap-1.5"
                          onClick={() => cardFileRef.current?.click()}
                          disabled={uploadingAttachment}
                          data-testid="attach-file-btn">
                          <Upload size={11} /> {uploadingAttachment ? 'Uploading...' : 'Attach'}
                        </Button>
                        <input ref={cardFileRef} type="file" className="hidden" onChange={handleAttachFile} />
                      </div>
                    </div>
                    {(cardEdit.attachments || []).length > 0 && (
                      <div className="space-y-1.5">
                        {(cardEdit.attachments || []).map((att, i) => (
                          <div key={att.id || i} className="flex items-center gap-2 p-2 rounded-lg bg-[#0f172a] border border-white/10 group">
                            <Paperclip size={12} className="text-slate-400 flex-shrink-0" />
                            <div className="flex-1 min-w-0">
                              <p className="text-xs text-slate-200 truncate">{att.name}</p>
                              {att.source === 'trello' && <p className="text-[10px] text-slate-500">From Trello</p>}
                              {att.mime_type && <p className="text-[10px] text-slate-500">{att.mime_type}</p>}
                            </div>
                            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100">
                              {att.url && (
                                <a href={att.url} target="_blank" rel="noopener noreferrer"
                                  className="text-slate-400 hover:text-blue-400 p-1">
                                  <Eye size={11} />
                                </a>
                              )}
                              <button onClick={() => removeAttachment(att.id)}
                                className="text-slate-400 hover:text-red-400 p-1">
                                <X size={11} />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Sidebar */}
                <div className="space-y-4">
                  {/* Priority */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-slate-400 flex items-center gap-1.5"><Flag size={11} /> Priority</Label>
                    <Select value={cardEdit.priority || 'medium'} onValueChange={v => setCardEdit({ ...cardEdit, priority: v })}>
                      <SelectTrigger className="h-8 text-xs bg-[#0f172a] border-white/15 text-slate-200">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-[#1e293b] border-white/15">
                        {[['low','Low','#10b981'],['medium','Medium','#f59e0b'],['high','High','#f97316'],['urgent','Urgent','#ef4444']].map(([v,l,c]) => (
                          <SelectItem key={v} value={v} className="text-slate-200 focus:bg-white/10">
                            <span className="flex items-center gap-2">
                              <span className="h-2 w-2 rounded-full" style={{ background: c }} />{l}
                            </span>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Due Date */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-slate-400 flex items-center gap-1.5"><Calendar size={11} /> Due Date</Label>
                    <Input type="date" className="h-8 text-xs bg-[#0f172a] border-white/15 text-slate-200"
                      value={cardEdit.due_date || ''} onChange={e => setCardEdit({ ...cardEdit, due_date: e.target.value })} />
                  </div>

                  {/* Member assignments */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-slate-400 flex items-center gap-1.5"><Users size={11} /> Members</Label>
                    <div className="max-h-36 overflow-y-auto space-y-1 rounded-lg bg-[#0f172a] border border-white/10 p-1.5">
                      {staffUsers.slice(0, 60).map(u => {
                        const assigned = (cardEdit.assignees || []).includes(u.id);
                        return (
                          <label key={u.id} className="flex items-center gap-2 cursor-pointer px-1 py-0.5 rounded hover:bg-white/5">
                            <input type="checkbox" className="h-3 w-3 accent-blue-500" checked={assigned}
                              onChange={() => {
                                const current = cardEdit.assignees || [];
                                const updated = assigned ? current.filter(id => id !== u.id) : [...current, u.id];
                                setCardEdit({ ...cardEdit, assignees: updated });
                              }} />
                            <span className="h-5 w-5 rounded-full bg-slate-600 flex items-center justify-center text-[9px] font-bold text-white flex-shrink-0">
                              {u.name?.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
                            </span>
                            <span className="text-xs text-slate-300 truncate">{u.name}</span>
                          </label>
                        );
                      })}
                      {staffUsers.length === 0 && <p className="text-xs text-slate-500 text-center py-1">No staff found</p>}
                    </div>
                  </div>

                  {/* Labels */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-slate-400 flex items-center gap-1.5"><Tag size={11} /> Labels</Label>
                    <div className="flex flex-wrap gap-1.5">
                      {LABEL_COLORS.map(color => {
                        const existing = (cardEdit.labels || []).find(l => (l.color || l) === color);
                        return (
                          <button
                            key={color}
                            className={`h-5 w-8 rounded transition-transform hover:scale-110 ${existing ? 'ring-2 ring-white ring-offset-1 ring-offset-[#1e293b]' : ''}`}
                            style={{ background: color }}
                            onClick={() => {
                              const labels = [...(cardEdit.labels || [])];
                              const idx = labels.findIndex(l => (l.color || l) === color);
                              if (idx >= 0) labels.splice(idx, 1);
                              else labels.push({ name: '', color });
                              setCardEdit({ ...cardEdit, labels });
                            }}
                          />
                        );
                      })}
                    </div>
                  </div>

                  {/* Move to list */}
                  {board?.lists && board.lists.length > 1 && (
                    <div className="space-y-1.5">
                      <Label className="text-xs text-slate-400 flex items-center gap-1.5"><ChevronRight size={11} /> Move to</Label>
                      <Select value={openCard?.list_id || ''} onValueChange={async (toListId) => {
                        if (toListId && toListId !== openCard?.list_id) {
                          await moveCardToList(openCard, openCard.list_id, toListId);
                          setOpenCard({ ...openCard, list_id: toListId });
                        }
                      }}>
                        <SelectTrigger className="h-8 text-xs bg-[#0f172a] border-white/15 text-slate-200">
                          <SelectValue placeholder="Select list" />
                        </SelectTrigger>
                        <SelectContent className="bg-[#1e293b] border-white/15">
                          {board.lists.map(l => (
                            <SelectItem key={l.id} value={l.id} className="text-slate-200 focus:bg-white/10 text-xs">{l.name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  )}

                  <Button size="sm" className="w-full h-8 text-xs bg-blue-600 hover:bg-blue-700 text-white gap-1.5"
                    onClick={saveCardEdit} disabled={savingCard} data-testid="save-card-btn">
                    <Check size={12} /> {savingCard ? 'Saving...' : 'Save Card'}
                  </Button>

                  <Button size="sm" variant="ghost"
                    className="w-full h-8 text-xs text-amber-400 hover:text-amber-300 hover:bg-amber-500/10 gap-1.5"
                    onClick={() => archiveCard(openCard)}>
                    <Archive size={12} /> Archive Card
                  </Button>

                  <Button size="sm" variant="ghost"
                    className="w-full h-8 text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 gap-1.5"
                    onClick={() => deleteCard(openCard)}>
                    <Trash2 size={12} /> Delete Card
                  </Button>
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* ===== CREATE BOARD DIALOG ===== */}
      <Dialog open={showNewBoard} onOpenChange={setShowNewBoard}>
        <DialogContent className="max-w-sm bg-[#1e293b] border-white/10 text-slate-100">
          <DialogHeader><DialogTitle className="text-slate-100">Create Board</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label className="text-slate-300 text-xs">Board Name *</Label>
              <Input data-testid="new-board-name" value={newBoardForm.name}
                onChange={e => setNewBoardForm({ ...newBoardForm, name: e.target.value })}
                placeholder="e.g. Kampala Office Tasks"
                className="bg-[#0f172a] border-white/15 text-slate-200 placeholder:text-slate-500" />
            </div>
            <div className="space-y-2">
              <Label className="text-slate-300 text-xs">Location (optional)</Label>
              <Select value={newBoardForm.location_id || '_global'}
                onValueChange={v => setNewBoardForm({ ...newBoardForm, location_id: v === '_global' ? '' : v })}>
                <SelectTrigger className="bg-[#0f172a] border-white/15 text-slate-200">
                  <SelectValue placeholder="Global (all users)" />
                </SelectTrigger>
                <SelectContent className="bg-[#1e293b] border-white/15">
                  <SelectItem value="_global" className="text-slate-200">Global</SelectItem>
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

      {/* ===== TRELLO IMPORT DIALOG ===== */}
      <Dialog open={showTrelloImport} onOpenChange={setShowTrelloImport}>
        <DialogContent className="max-w-lg bg-[#1e293b] border-white/10 text-slate-100">
          <DialogHeader><DialogTitle className="text-slate-100">Import Trello Board</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <p className="text-sm text-slate-400">Export your Trello board as JSON (Board menu → Print & Export → Export as JSON) and paste or upload it below.</p>
            <div className="space-y-2">
              <Label className="text-slate-300 text-xs">Location (optional)</Label>
              <Select value={importLocationId || '_global'} onValueChange={v => setImportLocationId(v === '_global' ? '' : v)}>
                <SelectTrigger className="bg-[#0f172a] border-white/15 text-slate-200">
                  <SelectValue placeholder="Global" />
                </SelectTrigger>
                <SelectContent className="bg-[#1e293b] border-white/15">
                  <SelectItem value="_global" className="text-slate-200">Global (all users)</SelectItem>
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
                <input ref={trelloFileRef} type="file" className="hidden" accept=".json" onChange={handleTrelloFile} />
              </div>
              <Textarea rows={6} placeholder='Paste Trello board JSON here...'
                className="text-xs font-mono bg-[#0f172a] border-white/15 text-slate-200 placeholder:text-slate-500"
                value={trelloJson} onChange={e => setTrelloJson(e.target.value)}
                data-testid="trello-json-input" />
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

      {/* ===== ARCHIVE PANEL ===== */}
      <Dialog open={showArchive} onOpenChange={setShowArchive}>
        <DialogContent className="max-w-lg bg-[#1e293b] border-white/10 text-slate-100 max-h-[80vh] overflow-hidden flex flex-col">
          <DialogHeader><DialogTitle className="text-slate-100 flex items-center gap-2"><Archive size={16} /> Archived Items</DialogTitle></DialogHeader>
          <div className="flex gap-2 mt-2 flex-shrink-0">
            <Button size="sm" variant={archiveTab === 'cards' ? 'default' : 'ghost'}
              className={archiveTab === 'cards' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'}
              onClick={() => setArchiveTab('cards')}>
              Cards ({archivedCards.length})
            </Button>
            <Button size="sm" variant={archiveTab === 'lists' ? 'default' : 'ghost'}
              className={archiveTab === 'lists' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'}
              onClick={() => setArchiveTab('lists')}>
              Lists ({archivedLists.length})
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto space-y-2 mt-3">
            {archiveTab === 'cards' && (
              archivedCards.length === 0 ? (
                <p className="text-sm text-slate-500 text-center py-8">No archived cards</p>
              ) : archivedCards.map(card => (
                <div key={card.id} className="flex items-center justify-between p-3 rounded-lg bg-[#0f172a] border border-white/10">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-200 truncate">{card.title}</p>
                    <p className="text-xs text-slate-500">{card.list_name || 'No list'}</p>
                  </div>
                  <Button size="sm" variant="ghost" className="text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10 gap-1 ml-2 text-xs"
                    onClick={() => restoreCard(card)}>
                    <RotateCcw size={11} /> Restore
                  </Button>
                </div>
              ))
            )}
            {archiveTab === 'lists' && (
              archivedLists.length === 0 ? (
                <p className="text-sm text-slate-500 text-center py-8">No archived lists</p>
              ) : archivedLists.map(list => (
                <div key={list.id} className="flex items-center justify-between p-3 rounded-lg bg-[#0f172a] border border-white/10">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-200 truncate">{list.name}</p>
                    <p className="text-xs text-slate-500">Archived</p>
                  </div>
                  <Button size="sm" variant="ghost" className="text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10 gap-1 ml-2 text-xs"
                    onClick={() => restoreList(list)}>
                    <RotateCcw size={11} /> Restore
                  </Button>
                </div>
              ))
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}


// ===== KANBAN LIST COMPONENT =====
function KanbanList({
  list, listTasks, accentColor,
  editingListId, editingListName, setEditingListId, setEditingListName, renameList,
  openListMenu, setOpenListMenu, archiveList, deleteList,
  addingCard, setAddingCard, newCardTitle, setNewCardTitle, addCard,
  staffUsers, dragging, dragOver,
  onDragStart, onDragEnd, onDragOver, onDrop,
  openCardDetail, archiveCard, canEdit
}) {
  const menuRef = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setOpenListMenu(null);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [setOpenListMenu]);

  return (
    <div
      data-testid={`kanban-list-${list.id}`}
      className="flex-shrink-0 w-64 rounded-xl flex flex-col"
      style={{ maxHeight: 'calc(100vh - 180px)', background: '#1e293b', border: '1px solid rgba(255,255,255,0.08)' }}
      onDragOver={e => onDragOver(e, list.id, listTasks.length)}
      onDrop={e => onDrop(e, list.id)}
    >
      {/* List header */}
      <div className="flex items-center justify-between px-3 py-2.5 flex-shrink-0"
        style={{ borderBottom: `2px solid ${accentColor}40`, borderRadius: '12px 12px 0 0', background: 'rgba(255,255,255,0.04)' }}>
        {editingListId === list.id ? (
          <Input
            autoFocus
            className="h-7 text-sm font-semibold bg-[#0f172a] border-white/15 text-white"
            value={editingListName}
            onChange={e => setEditingListName(e.target.value)}
            onBlur={() => renameList(list.id)}
            onKeyDown={e => { if (e.key === 'Enter') renameList(list.id); if (e.key === 'Escape') setEditingListId(null); }}
          />
        ) : (
          <span
            className="cursor-pointer hover:text-white flex-1 truncate text-sm font-semibold text-slate-200"
            onDoubleClick={() => { setEditingListId(list.id); setEditingListName(list.name); }}
            data-testid={`list-name-${list.id}`}
          >
            {list.name}
          </span>
        )}
        <div className="flex items-center gap-1 ml-2 flex-shrink-0">
          <span className="text-xs text-slate-500">{listTasks.length}</span>
          {canEdit && (
            <div className="relative" ref={openListMenu === list.id ? menuRef : null}>
              <button
                className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-white"
                onClick={e => { e.stopPropagation(); setOpenListMenu(openListMenu === list.id ? null : list.id); }}
                title="List options"
              >
                <MoreHorizontal size={14} />
              </button>
              {openListMenu === list.id && (
                <div className="absolute right-0 top-7 z-50 w-44 rounded-xl bg-[#0f172a] border border-white/10 shadow-2xl py-1">
                  <button className="flex items-center gap-2 w-full px-3 py-2 text-xs text-slate-300 hover:bg-white/10 hover:text-white"
                    onClick={() => { setOpenListMenu(null); setEditingListId(list.id); setEditingListName(list.name); }}>
                    <Edit2 size={11} /> Rename List
                  </button>
                  <button className="flex items-center gap-2 w-full px-3 py-2 text-xs text-amber-400 hover:bg-amber-500/10 hover:text-amber-300"
                    onClick={() => archiveList(list.id)}>
                    <Archive size={11} /> Archive List
                  </button>
                  <div className="border-t border-white/10 my-1" />
                  <button className="flex items-center gap-2 w-full px-3 py-2 text-xs text-red-400 hover:bg-red-500/10 hover:text-red-300"
                    onClick={() => deleteList(list.id)}>
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
            staffUsers={staffUsers}
            isDragging={dragging?.task?.id === task.id}
            isDragOver={dragOver?.listId === list.id && dragOver?.idx === idx}
            onDragStart={onDragStart}
            onDragEnd={onDragEnd}
            onClick={() => openCardDetail(task)}
            onArchive={() => archiveCard(task)}
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
      {addingCard === list.id ? (
        <div className="px-2 pb-2 space-y-2 flex-shrink-0">
          <Textarea
            autoFocus
            rows={2}
            placeholder="Enter a title..."
            className="bg-[#0f172a] border-white/15 text-slate-200 placeholder:text-slate-500 text-sm resize-none"
            value={newCardTitle}
            onChange={e => setNewCardTitle(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); addCard(list.id); } if (e.key === 'Escape') setAddingCard(null); }}
            data-testid={`new-card-input-${list.id}`}
          />
          <div className="flex gap-2">
            <Button size="sm" className="h-7 bg-blue-600 hover:bg-blue-700 text-white text-xs" onClick={() => addCard(list.id)} data-testid={`add-card-confirm-${list.id}`}>Add</Button>
            <Button size="sm" variant="ghost" className="h-7 text-slate-400 hover:text-white" onClick={() => setAddingCard(null)}><X size={14} /></Button>
          </div>
        </div>
      ) : (
        canEdit && (
          <button
            data-testid={`add-card-btn-${list.id}`}
            onClick={() => { setAddingCard(list.id); setNewCardTitle(''); }}
            className="flex items-center gap-1.5 w-full px-3 py-2.5 text-xs text-slate-500 hover:text-slate-300 hover:bg-white/5 rounded-b-xl transition-colors flex-shrink-0"
          >
            <Plus size={13} /> Add a card
          </button>
        )
      )}
    </div>
  );
}


// ===== KANBAN CARD COMPONENT =====
function KanbanCard({ task, listId, staffUsers, isDragging, isDragOver, onDragStart, onDragEnd, onClick, onArchive, canEdit }) {
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
        {/* Assignee avatars */}
        {assignedMembers.length > 0 && (
          <div className="ml-auto flex -space-x-1">
            {assignedMembers.slice(0, 3).map((m, i) => (
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

      {/* Quick archive on hover */}
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
