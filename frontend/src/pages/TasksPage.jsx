import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Plus, MoreHorizontal, X, Edit2, Trash2, Check, Upload,
  Flag, Calendar, Tag, AlignLeft, CheckSquare, Paperclip,
  ChevronDown, RefreshCw, MapPin, Globe, Download
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { boardsApi, tasksApi, membersApi, locationsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

const PRIORITY_COLORS = { low: '#61bd4f', medium: '#f2d600', high: '#ff9f1a', urgent: '#eb5a46' };
const LABEL_COLORS = ['#61bd4f','#f2d600','#ff9f1a','#eb5a46','#c377e0','#0079bf','#00c2e0','#51e898','#ff78cb','#344563'];

export default function TasksPage() {
  const { user } = useAuth();
  const [boards, setBoards] = useState([]);
  const [activeBoardId, setActiveBoardId] = useState(null);
  const [board, setBoard] = useState(null); // {id, name, lists: [{id, name, position}]}
  const [tasks, setTasks] = useState({}); // {list_id: [task, ...]}
  const [loading, setLoading] = useState(true);
  const [locations, setLocations] = useState([]);
  const [members, setMembers] = useState([]);

  // UI state
  const [addingCard, setAddingCard] = useState(null); // list_id or null
  const [newCardTitle, setNewCardTitle] = useState('');
  const [addingList, setAddingList] = useState(false);
  const [newListName, setNewListName] = useState('');
  const [editingListId, setEditingListId] = useState(null);
  const [editingListName, setEditingListName] = useState('');
  const [dragging, setDragging] = useState(null); // {task, fromListId}
  const [dragOver, setDragOver] = useState(null); // {listId, index}

  // Card detail
  const [openCard, setOpenCard] = useState(null);
  const [cardEdit, setCardEdit] = useState({});
  const [savingCard, setSavingCard] = useState(false);
  const [newCheckItem, setNewCheckItem] = useState('');
  const cardFileRef = useRef(null);

  // Board management
  const [showNewBoard, setShowNewBoard] = useState(false);
  const [newBoardForm, setNewBoardForm] = useState({ name: '', location_id: '', background: '#0052cc' });
  const [showTrelloImport, setShowTrelloImport] = useState(false);
  const [trelloJson, setTrelloJson] = useState('');
  const [importLocationId, setImportLocationId] = useState('');
  const [importing, setImporting] = useState(false);
  const trelloFileRef = useRef(null);

  const isAdmin = ['admin', 'system_admin', 'executive director', 'director'].includes((user?.role || '').toLowerCase());
  const canEdit = isAdmin || ['manager', 'coordinator'].includes((user?.role || '').toLowerCase());

  const fetchBoards = useCallback(async () => {
    try {
      const [bRes, lRes, mRes] = await Promise.all([
        boardsApi.list(),
        locationsApi.list().catch(() => ({ data: [] })),
        membersApi.list({ limit: 200 }).catch(() => ({ data: { members: [] } })),
      ]);
      setBoards(bRes.data || []);
      setLocations(lRes.data || []);
      const ms = mRes.data?.members || mRes.data || [];
      setMembers(ms);
      if (bRes.data?.length && !activeBoardId) {
        setActiveBoardId(bRes.data[0].id);
      }
    } catch (err) { toast.error('Failed to load boards'); }
    finally { setLoading(false); }
  }, [activeBoardId]);

  useEffect(() => { fetchBoards(); }, []);

  const fetchBoardDetail = useCallback(async () => {
    if (!activeBoardId) return;
    try {
      const [bRes, tRes] = await Promise.all([
        boardsApi.get(activeBoardId),
        boardsApi.tasks(activeBoardId, null),
      ]);
      setBoard(bRes.data);
      // Group tasks by list_id
      const grouped = {};
      for (const list of bRes.data.lists || []) {
        grouped[list.id] = [];
      }
      for (const t of (tRes.data || [])) {
        const lid = t.list_id || '__none__';
        if (!grouped[lid]) grouped[lid] = [];
        grouped[lid].push(t);
      }
      // Sort by position within each list
      for (const lid of Object.keys(grouped)) {
        grouped[lid].sort((a, b) => (a.position || 0) - (b.position || 0));
      }
      setTasks(grouped);
    } catch { toast.error('Failed to load board'); }
  }, [activeBoardId]);

  useEffect(() => { fetchBoardDetail(); }, [fetchBoardDetail]);

  // ===== BOARD ACTIONS =====
  const createBoard = async () => {
    if (!newBoardForm.name.trim()) return;
    try {
      const loc = locations.find(l => l.id === newBoardForm.location_id);
      const res = await boardsApi.create({
        ...newBoardForm,
        location_name: loc?.name || '',
      });
      toast.success(`Board "${res.data.name}" created`);
      setShowNewBoard(false);
      setNewBoardForm({ name: '', location_id: '', background: '#0052cc' });
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

  const deleteList = async (listId) => {
    if (!window.confirm('Delete this list? Cards will be unassigned.')) return;
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
      const pos = (tasks[listId]?.length || 0);
      const res = await tasksApi.create({
        title: newCardTitle.trim(),
        board_id: activeBoardId,
        list_id: listId,
        list_name: list?.name || '',
        status: 'todo',
        position: pos,
        labels: [],
        checklist: [],
      });
      setTasks(prev => ({ ...prev, [listId]: [...(prev[listId] || []), res.data] }));
      setNewCardTitle('');
      setAddingCard(null);
    } catch { toast.error('Failed to add card'); }
  };

  const deleteCard = async (task, listId) => {
    try {
      await tasksApi.delete(task.id);
      setTasks(prev => ({ ...prev, [listId]: (prev[listId] || []).filter(t => t.id !== task.id) }));
      if (openCard?.id === task.id) setOpenCard(null);
      toast.success('Card deleted');
    } catch { toast.error('Failed to delete card'); }
  };

  const openCardDetail = (task) => {
    setOpenCard(task);
    setCardEdit({
      title: task.title || '',
      description: task.description || '',
      priority: task.priority || 'medium',
      due_date: task.due_date || '',
      assignee: task.assignee || '',
      labels: task.labels || [],
      checklist: task.checklist || [],
    });
  };

  const saveCardEdit = async () => {
    if (!openCard) return;
    setSavingCard(true);
    try {
      const res = await tasksApi.update(openCard.id, cardEdit);
      const updated = res.data;
      // Update in tasks state
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

  const toggleCheckItem = async (task, listId, idx) => {
    const checklist = [...(task.checklist || [])];
    checklist[idx] = { ...checklist[idx], completed: !checklist[idx].completed };
    try {
      await tasksApi.update(task.id, { checklist });
      setTasks(prev => ({ ...prev, [listId]: (prev[listId] || []).map(t => t.id === task.id ? { ...t, checklist } : t) }));
      if (openCard?.id === task.id) setOpenCard({ ...openCard, checklist });
    } catch { /* ignore */ }
  };

  const addCheckItem = async () => {
    if (!newCheckItem.trim() || !openCard) return;
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
      const loc = locations.find(l => l.id === importLocationId);
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

  // ===== ADD ATTACHMENT to card =====
  const attachFile = async (e) => {
    if (!openCard) return;
    const file = e.target.files?.[0];
    if (!file) return;
    toast.info(`Attachment "${file.name}" noted (document upload available in member profiles)`);
  };

  // ===== RENDER =====
  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" />
    </div>
  );

  const currentBoard = boards.find(b => b.id === activeBoardId);

  return (
    <div className="flex flex-col h-full" style={{ minHeight: 'calc(100vh - 64px)' }}>
      {/* ===== BOARD HEADER ===== */}
      <div
        className="flex items-center justify-between px-4 py-3 flex-shrink-0"
        style={{ background: currentBoard?.background || '#0052cc' }}
      >
        <div className="flex items-center gap-3 overflow-x-auto">
          {boards.map(b => (
            <button
              key={b.id}
              onClick={() => setActiveBoardId(b.id)}
              data-testid={`board-tab-${b.id}`}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition-all ${b.id === activeBoardId ? 'bg-white/30 text-white' : 'text-white/80 hover:bg-white/20'}`}
            >
              {b.location_name ? <MapPin size={12} /> : <Globe size={12} />}
              {b.name}
              <span className="text-xs opacity-70">({b.card_count || 0})</span>
            </button>
          ))}
          {canEdit && (
            <button
              onClick={() => setShowNewBoard(true)}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm text-white/80 hover:bg-white/20"
              data-testid="create-board-btn"
            >
              <Plus size={14} /> Board
            </button>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <Button
            size="sm"
            variant="ghost"
            className="text-white hover:bg-white/20 gap-1.5"
            onClick={() => setShowTrelloImport(true)}
          >
            <Download size={14} /> Import Trello
          </Button>
          <Button size="sm" variant="ghost" className="text-white hover:bg-white/20" onClick={fetchBoardDetail}>
            <RefreshCw size={14} />
          </Button>
        </div>
      </div>

      {/* ===== BOARD CONTENT ===== */}
      {!activeBoardId || !board ? (
        <div className="flex flex-col items-center justify-center flex-1 gap-4 text-muted-foreground">
          <p className="text-lg">No boards yet</p>
          <Button onClick={() => setShowNewBoard(true)} className="gap-2"><Plus size={16} /> Create Board</Button>
        </div>
      ) : (
        <div
          className="flex gap-4 p-4 overflow-x-auto flex-1 items-start"
          style={{ background: `${currentBoard?.background || '#0052cc'}22` }}
        >
          {/* ===== LISTS ===== */}
          {(board.lists || []).map(list => {
            const listTasks = tasks[list.id] || [];
            return (
              <div
                key={list.id}
                data-testid={`kanban-list-${list.id}`}
                className="flex-shrink-0 w-72 rounded-xl bg-[#ebecf0] flex flex-col max-h-[calc(100vh-160px)]"
                onDragOver={e => onDragOver(e, list.id, listTasks.length)}
                onDrop={e => onDrop(e, list.id)}
              >
                {/* List header */}
                <div className="flex items-center justify-between px-3 py-2.5 font-semibold text-sm text-[#172b4d]">
                  {editingListId === list.id ? (
                    <Input
                      autoFocus
                      className="h-7 text-sm font-semibold bg-white"
                      value={editingListName}
                      onChange={e => setEditingListName(e.target.value)}
                      onBlur={() => renameList(list.id)}
                      onKeyDown={e => { if (e.key === 'Enter') renameList(list.id); if (e.key === 'Escape') setEditingListId(null); }}
                    />
                  ) : (
                    <span
                      className="cursor-pointer hover:text-[#0052cc] flex-1 truncate"
                      onDoubleClick={() => { setEditingListId(list.id); setEditingListName(list.name); }}
                      data-testid={`list-name-${list.id}`}
                    >
                      {list.name}
                    </span>
                  )}
                  <span className="text-xs text-gray-400 ml-2 mr-1">{listTasks.length}</span>
                  {canEdit && (
                    <button
                      className="p-1 rounded hover:bg-gray-300 text-gray-500"
                      onClick={() => deleteList(list.id)}
                      title="Delete list"
                    >
                      <X size={13} />
                    </button>
                  )}
                </div>

                {/* Cards */}
                <div className="overflow-y-auto flex-1 px-2 space-y-1.5 pb-1">
                  {listTasks.map((task, idx) => (
                    <KanbanCard
                      key={task.id}
                      task={task}
                      listId={list.id}
                      members={members}
                      isDragging={dragging?.task?.id === task.id}
                      isDragOver={dragOver?.listId === list.id && dragOver?.idx === idx}
                      onDragStart={onDragStart}
                      onDragEnd={onDragEnd}
                      onClick={() => openCardDetail(task)}
                      onDelete={() => deleteCard(task, list.id)}
                      onToggleCheck={(i) => toggleCheckItem(task, list.id, i)}
                      canEdit={canEdit}
                    />
                  ))}
                </div>

                {/* Add card */}
                {addingCard === list.id ? (
                  <div className="px-2 pb-2 space-y-2">
                    <Textarea
                      autoFocus
                      rows={2}
                      placeholder="Enter a title..."
                      className="bg-white text-sm resize-none"
                      value={newCardTitle}
                      onChange={e => setNewCardTitle(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); addCard(list.id); } if (e.key === 'Escape') setAddingCard(null); }}
                      data-testid={`new-card-input-${list.id}`}
                    />
                    <div className="flex gap-2">
                      <Button size="sm" className="h-8" onClick={() => addCard(list.id)} data-testid={`add-card-confirm-${list.id}`}>Add</Button>
                      <Button size="sm" variant="ghost" className="h-8" onClick={() => setAddingCard(null)}><X size={14} /></Button>
                    </div>
                  </div>
                ) : (
                  canEdit && (
                    <button
                      data-testid={`add-card-btn-${list.id}`}
                      onClick={() => { setAddingCard(list.id); setNewCardTitle(''); }}
                      className="flex items-center gap-1.5 w-full px-3 py-2 text-sm text-[#5e6c84] hover:bg-gray-300/60 rounded-b-xl transition-colors"
                    >
                      <Plus size={14} /> Add a card
                    </button>
                  )
                )}
              </div>
            );
          })}

          {/* Add List */}
          {canEdit && (
            <div className="flex-shrink-0 w-72">
              {addingList ? (
                <div className="rounded-xl bg-[#ebecf0] p-2 space-y-2">
                  <Input
                    autoFocus
                    placeholder="Enter list name..."
                    className="bg-white text-sm h-8"
                    value={newListName}
                    onChange={e => setNewListName(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') addList(); if (e.key === 'Escape') setAddingList(false); }}
                    data-testid="new-list-input"
                  />
                  <div className="flex gap-2">
                    <Button size="sm" className="h-7" onClick={addList} data-testid="add-list-confirm-btn">Add List</Button>
                    <Button size="sm" variant="ghost" className="h-7" onClick={() => setAddingList(false)}><X size={13} /></Button>
                  </div>
                </div>
              ) : (
                <button
                  data-testid="add-list-btn"
                  onClick={() => setAddingList(true)}
                  className="flex items-center gap-2 w-full px-4 py-2.5 rounded-xl bg-white/30 hover:bg-white/50 text-sm font-medium text-white transition-colors"
                  style={{ color: currentBoard?.background ? 'white' : undefined }}
                >
                  <Plus size={16} /> Add another list
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* ===== CARD DETAIL DIALOG ===== */}
      <Dialog open={!!openCard} onOpenChange={o => { if (!o) { setOpenCard(null); setCardEdit({}); } }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          {openCard && (
            <>
              {openCard.cover_color && (
                <div className="h-12 rounded-t-lg -mx-6 -mt-6 mb-4" style={{ background: openCard.cover_color }} />
              )}
              <DialogHeader>
                <DialogTitle>
                  <Input
                    data-testid="card-title-input"
                    className="text-lg font-semibold border-0 shadow-none p-0 focus-visible:ring-0 bg-transparent"
                    value={cardEdit.title || ''}
                    onChange={e => setCardEdit({ ...cardEdit, title: e.target.value })}
                    onBlur={saveCardEdit}
                  />
                </DialogTitle>
              </DialogHeader>

              <div className="grid grid-cols-3 gap-6 mt-2">
                {/* Main column */}
                <div className="col-span-2 space-y-5">
                  {/* Labels */}
                  {(cardEdit.labels || []).length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {(cardEdit.labels || []).map((lbl, i) => (
                        <span key={i} className="px-2.5 py-0.5 rounded text-xs font-medium text-white"
                          style={{ background: lbl.color || '#61bd4f' }}>
                          {lbl.name || lbl}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Description */}
                  <div className="space-y-2">
                    <Label className="flex items-center gap-2 text-sm font-semibold"><AlignLeft size={14} /> Description</Label>
                    <Textarea
                      data-testid="card-description"
                      rows={3}
                      placeholder="Add a more detailed description..."
                      value={cardEdit.description || ''}
                      onChange={e => setCardEdit({ ...cardEdit, description: e.target.value })}
                      onBlur={saveCardEdit}
                    />
                  </div>

                  {/* Checklist */}
                  {(cardEdit.checklist || []).length > 0 && (
                    <div className="space-y-2">
                      <Label className="flex items-center gap-2 text-sm font-semibold">
                        <CheckSquare size={14} /> Checklist
                        <span className="text-xs text-muted-foreground ml-1">
                          {(cardEdit.checklist || []).filter(i => i.completed).length}/{(cardEdit.checklist || []).length}
                        </span>
                      </Label>
                      {/* Progress bar */}
                      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-green-500 transition-all"
                          style={{ width: `${((cardEdit.checklist || []).filter(i => i.completed).length / (cardEdit.checklist || []).length) * 100}%` }}
                        />
                      </div>
                      <div className="space-y-1.5">
                        {(cardEdit.checklist || []).map((item, i) => (
                          <div key={i} className="flex items-center gap-2 group">
                            <input
                              type="checkbox"
                              checked={item.completed}
                              className="h-4 w-4 rounded"
                              onChange={() => {
                                const cl = [...(cardEdit.checklist || [])];
                                cl[i] = { ...cl[i], completed: !cl[i].completed };
                                setCardEdit({ ...cardEdit, checklist: cl });
                              }}
                            />
                            <span className={`text-sm flex-1 ${item.completed ? 'line-through text-muted-foreground' : ''}`}>{item.text}</span>
                            <button
                              className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive"
                              onClick={() => {
                                const cl = [...(cardEdit.checklist || [])];
                                cl.splice(i, 1);
                                setCardEdit({ ...cardEdit, checklist: cl });
                              }}
                            >
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
                      className="h-8 text-sm"
                      value={newCheckItem}
                      onChange={e => setNewCheckItem(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') addCheckItem(); }}
                      data-testid="new-check-item"
                    />
                    <Button size="sm" className="h-8" variant="outline" onClick={addCheckItem}>Add</Button>
                  </div>
                </div>

                {/* Sidebar */}
                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Priority</Label>
                    <Select value={cardEdit.priority || 'medium'} onValueChange={v => setCardEdit({ ...cardEdit, priority: v })}>
                      <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="low">Low</SelectItem>
                        <SelectItem value="medium">Medium</SelectItem>
                        <SelectItem value="high">High</SelectItem>
                        <SelectItem value="urgent">Urgent</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Due Date</Label>
                    <Input type="date" className="h-8 text-xs" value={cardEdit.due_date || ''} onChange={e => setCardEdit({ ...cardEdit, due_date: e.target.value })} />
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Assignee</Label>
                    <Select value={cardEdit.assignee || '_unassigned'} onValueChange={v => setCardEdit({ ...cardEdit, assignee: v === '_unassigned' ? '' : v })}>
                      <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="Unassigned" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_unassigned">Unassigned</SelectItem>
                        {members.slice(0, 50).map(m => <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Labels */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Labels</Label>
                    <div className="flex flex-wrap gap-1">
                      {LABEL_COLORS.map(color => {
                        const existing = (cardEdit.labels || []).find(l => (l.color || l) === color);
                        return (
                          <button
                            key={color}
                            className={`h-5 w-8 rounded transition-transform hover:scale-110 ${existing ? 'ring-2 ring-offset-1 ring-gray-400' : ''}`}
                            style={{ background: color }}
                            onClick={() => {
                              const labels = [...(cardEdit.labels || [])];
                              const idx = labels.findIndex(l => (l.color || l) === color);
                              if (idx >= 0) { labels.splice(idx, 1); }
                              else { labels.push({ name: '', color }); }
                              setCardEdit({ ...cardEdit, labels });
                            }}
                          />
                        );
                      })}
                    </div>
                  </div>

                  <Button
                    size="sm"
                    className="w-full h-8 text-xs gap-1.5"
                    onClick={saveCardEdit}
                    disabled={savingCard}
                    data-testid="save-card-btn"
                  >
                    <Check size={12} /> {savingCard ? 'Saving...' : 'Save Card'}
                  </Button>

                  <Button
                    size="sm"
                    variant="ghost"
                    className="w-full h-8 text-xs text-destructive hover:text-destructive gap-1.5"
                    onClick={() => {
                      const listId = openCard.list_id;
                      deleteCard(openCard, listId);
                    }}
                  >
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
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Create Board</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Board Name *</Label>
              <Input data-testid="new-board-name" value={newBoardForm.name} onChange={e => setNewBoardForm({ ...newBoardForm, name: e.target.value })} placeholder="e.g. Kampala Office Tasks" />
            </div>
            <div className="space-y-2">
              <Label>Location (optional)</Label>
              <Select value={newBoardForm.location_id || '_global'} onValueChange={v => setNewBoardForm({ ...newBoardForm, location_id: v === '_global' ? '' : v })}>
                <SelectTrigger><SelectValue placeholder="Global (all users)" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_global">Global</SelectItem>
                  {locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Background Color</Label>
              <div className="flex gap-2">
                {['#0052cc','#5aac44','#e04646','#ff7800','#6554c0','#00b8d9','#172b4d','#344563'].map(c => (
                  <button key={c} className={`h-8 w-8 rounded-lg transition-transform hover:scale-110 ${newBoardForm.background === c ? 'ring-2 ring-offset-1 ring-gray-400 scale-110' : ''}`} style={{ background: c }} onClick={() => setNewBoardForm({ ...newBoardForm, background: c })} />
                ))}
              </div>
            </div>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => setShowNewBoard(false)}>Cancel</Button>
              <Button className="flex-1" onClick={createBoard} data-testid="confirm-create-board">Create</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* ===== TRELLO IMPORT DIALOG ===== */}
      <Dialog open={showTrelloImport} onOpenChange={setShowTrelloImport}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Import Trello Board</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <p className="text-sm text-muted-foreground">Export your Trello board as JSON (Board → Show menu → More → Print and export → Export as JSON) and paste or upload it here.</p>
            <div className="space-y-2">
              <Label>Assign to Location (optional)</Label>
              <Select value={importLocationId || '_global'} onValueChange={v => setImportLocationId(v === '_global' ? '' : v)}>
                <SelectTrigger><SelectValue placeholder="Global" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_global">Global (all users)</SelectItem>
                  {locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Label>Trello JSON</Label>
                <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" onClick={() => trelloFileRef.current?.click()}>
                  <Upload size={12} /> Upload file
                </Button>
                <input ref={trelloFileRef} type="file" className="hidden" accept=".json" onChange={handleTrelloFile} />
              </div>
              <Textarea
                rows={6}
                placeholder='Paste Trello board JSON here...'
                className="text-xs font-mono"
                value={trelloJson}
                onChange={e => setTrelloJson(e.target.value)}
                data-testid="trello-json-input"
              />
            </div>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => setShowTrelloImport(false)}>Cancel</Button>
              <Button className="flex-1" onClick={importTrello} disabled={importing || !trelloJson.trim()} data-testid="import-trello-btn">
                {importing ? 'Importing...' : 'Import Board'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}


// ===== KANBAN CARD COMPONENT =====
function KanbanCard({ task, listId, members, isDragging, isDragOver, onDragStart, onDragEnd, onClick, onDelete, onToggleCheck, canEdit }) {
  const assigneeMember = members.find(m => m.id === task.assignee);
  const checklist = task.checklist || [];
  const completed = checklist.filter(i => i.completed).length;
  const isOverdue = task.due_date && new Date(task.due_date) < new Date() && task.status !== 'done';

  return (
    <div
      draggable={canEdit}
      onDragStart={e => onDragStart(e, task, listId)}
      onDragEnd={onDragEnd}
      onClick={onClick}
      data-testid={`kanban-card-${task.id}`}
      className={`bg-white rounded-lg shadow-sm p-2.5 cursor-pointer hover:shadow-md transition-shadow border border-transparent hover:border-blue-200 group relative ${isDragging ? 'opacity-50 rotate-2' : ''} ${isDragOver ? 'border-t-2 border-t-blue-400' : ''}`}
    >
      {/* Cover color */}
      {task.cover_color && (
        <div className="h-2 rounded-t-sm -mx-2.5 -mt-2.5 mb-2" style={{ background: task.cover_color }} />
      )}

      {/* Labels */}
      {(task.labels || []).length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {task.labels.slice(0, 4).map((lbl, i) => (
            <span key={i} className="h-2 w-8 rounded-full" style={{ background: lbl.color || lbl || '#61bd4f' }} />
          ))}
        </div>
      )}

      {/* Title */}
      <p className="text-sm font-medium text-[#172b4d] leading-snug pr-4">{task.title}</p>

      {/* Footer indicators */}
      <div className="flex items-center gap-2 mt-2 flex-wrap">
        {isOverdue && (
          <span className="flex items-center gap-1 text-[10px] bg-red-100 text-red-600 rounded px-1.5 py-0.5">
            <Calendar size={9} /> {task.due_date}
          </span>
        )}
        {task.due_date && !isOverdue && (
          <span className="flex items-center gap-1 text-[10px] text-gray-400">
            <Calendar size={9} /> {task.due_date}
          </span>
        )}
        {checklist.length > 0 && (
          <span className={`flex items-center gap-1 text-[10px] rounded px-1.5 py-0.5 ${completed === checklist.length ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-500'}`}>
            <CheckSquare size={9} /> {completed}/{checklist.length}
          </span>
        )}
        {task.priority && task.priority !== 'medium' && (
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: PRIORITY_COLORS[task.priority] }} title={task.priority} />
        )}
        {assigneeMember && (
          <span className="ml-auto flex items-center justify-center h-5 w-5 rounded-full text-[9px] font-bold text-white bg-[#0052cc]" title={assigneeMember.name}>
            {assigneeMember.name.split(' ').map(n => n[0]).join('').slice(0,2).toUpperCase()}
          </span>
        )}
      </div>

      {/* Quick delete */}
      {canEdit && (
        <button
          className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 transition-opacity"
          onClick={e => { e.stopPropagation(); onDelete(); }}
          title="Delete"
        >
          <X size={12} />
        </button>
      )}
    </div>
  );
}
