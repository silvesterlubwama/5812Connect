import React, { useState, useEffect, useRef } from 'react';
import { Plus, GripVertical, Trash2, RefreshCw, Upload } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { tasksApi, membersApi } from '../services/api';
import { toast } from 'sonner';

const COLUMNS = [
  { id: 'todo', label: 'To Do', color: 'bg-slate-100 text-slate-700' },
  { id: 'in-progress', label: 'In Progress', color: 'bg-blue-100 text-blue-700' },
  { id: 'done', label: 'Done', color: 'bg-green-100 text-green-700' },
];
const priorityColors = {
  high: 'bg-red-100 text-red-700 border-red-200',
  medium: 'bg-amber-100 text-amber-700 border-amber-200',
  low: 'bg-slate-100 text-slate-600 border-slate-200',
};

export default function TasksPage() {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [members, setMembers] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
  const [dragId, setDragId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [newTask, setNewTask] = useState({ title: '', description: '', status: 'todo', priority: 'medium', assignee: '', due_date: '', tags: [] });
  const [showImport, setShowImport] = useState(false);
  const [importing, setImporting] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => {
    fetchTasks();
    membersApi.list({ limit: 50 }).then(res => setMembers(res.data.members)).catch(() => {});
  }, []);

  const fetchTasks = async () => {
    setLoading(true);
    try {
      const res = await tasksApi.list();
      setTasks(res.data);
    } catch { toast.error('Failed to load tasks'); }
    finally { setLoading(false); }
  };

  const getByStatus = (status) => tasks.filter(t => t.status === status);

  const handleDragStart = (e, id) => {
    setDragId(id);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDrop = async (e, newStatus) => {
    e.preventDefault();
    if (!dragId) return;
    const task = tasks.find(t => t.id === dragId);
    if (!task || task.status === newStatus) { setDragId(null); return; }
    setTasks(prev => prev.map(t => t.id === dragId ? { ...t, status: newStatus } : t));
    setDragId(null);
    try {
      await tasksApi.update(dragId, { status: newStatus });
    } catch { fetchTasks(); toast.error('Failed to update task'); }
  };

  const moveTask = async (taskId, newStatus) => {
    setTasks(prev => prev.map(t => t.id === taskId ? { ...t, status: newStatus } : t));
    try { await tasksApi.update(taskId, { status: newStatus }); }
    catch { fetchTasks(); }
  };

  const deleteTask = async (task) => {
    setTasks(prev => prev.filter(t => t.id !== task.id));
    try { await tasksApi.delete(task.id); toast.success('Task deleted'); }
    catch { fetchTasks(); toast.error('Failed to delete task'); }
  };

  const handleAdd = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await tasksApi.create(newTask);
      setTasks(prev => [res.data, ...prev]);
      setShowAdd(false);
      setNewTask({ title: '', description: '', status: 'todo', priority: 'medium', assignee: '', due_date: '', tags: [] });
      toast.success('Task created!');
    } catch { toast.error('Failed to create task'); }
    finally { setSaving(false); }
  };

  const handleTrelloImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const res = await tasksApi.importTrello(data);
      toast.success(`Imported ${res.data.imported} cards`);
      fetchTasks();
      setShowImport(false);
    } catch (err) {
      toast.error(err.message === 'Unexpected token' ? 'Invalid JSON file' : 'Import failed');
    } finally { setImporting(false); if (fileRef.current) fileRef.current.value = ''; }
  };

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Tasks</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {getByStatus('todo').length} to do · {getByStatus('in-progress').length} in progress · {getByStatus('done').length} done
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchTasks}><RefreshCw size={14} /></Button>
          <Button variant="outline" onClick={() => setShowImport(true)} className="gap-2"><Upload size={16} /> Import</Button>
          <Button onClick={() => setShowAdd(true)} className="gap-2"><Plus size={16} /> Add Task</Button>
        </div>
      </div>

      {loading ? (
        <div className="grid lg:grid-cols-3 gap-5">
          {COLUMNS.map(col => (
            <div key={col.id} className="bg-secondary/40 rounded-xl p-3 min-h-[300px] animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid lg:grid-cols-3 gap-5">
          {COLUMNS.map(col => {
            const colTasks = getByStatus(col.id);
            return (
              <div
                key={col.id}
                className="flex flex-col bg-secondary/40 rounded-xl p-3 min-h-[400px]"
                onDragOver={e => e.preventDefault()}
                onDrop={e => handleDrop(e, col.id)}
              >
                <div className="flex items-center justify-between mb-3 px-1">
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${col.color}`}>{col.label}</span>
                    <span className="text-xs text-muted-foreground font-medium">{colTasks.length}</span>
                  </div>
                  <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => { setNewTask(n => ({...n, status: col.id})); setShowAdd(true); }}>
                    <Plus size={14} />
                  </Button>
                </div>

                <div className="space-y-3 flex-1">
                  {colTasks.map(task => (
                    <Card
                      key={task.id}
                      draggable
                      onDragStart={e => handleDragStart(e, task.id)}
                      className="shadow-soft rounded-lg cursor-grab active:cursor-grabbing hover:shadow-soft-lg transition-shadow"
                    >
                      <CardContent className="p-3.5">
                        <div className="flex items-start gap-1.5 mb-2">
                          <GripVertical size={13} className="mt-0.5 text-muted-foreground shrink-0" />
                          <p className="text-sm font-medium leading-snug flex-1">{task.title}</p>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-5 w-5 shrink-0 text-muted-foreground hover:text-destructive"
                            onClick={() => deleteTask(task)}
                          >
                            <Trash2 size={11} />
                          </Button>
                        </div>

                        {task.description && (
                          <p className="text-xs text-muted-foreground pl-5 leading-relaxed line-clamp-2 mb-2">{task.description}</p>
                        )}

                        <div className="flex items-center gap-2 pl-5 flex-wrap mb-2">
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium border capitalize ${priorityColors[task.priority]}`}>
                            {task.priority}
                          </span>
                          {task.due_date && <span className="text-xs text-muted-foreground">{task.due_date}</span>}
                        </div>

                        {task.assignee && (
                          <p className="text-xs text-muted-foreground pl-5 mb-2">👤 {task.assignee}</p>
                        )}

                        {task.tags?.length > 0 && (
                          <div className="flex gap-1 pl-5 flex-wrap mb-2">
                            {task.tags.map(tag => (
                              <span key={tag} className="text-xs bg-primary/10 text-primary px-1.5 py-0.5 rounded">#{tag}</span>
                            ))}
                          </div>
                        )}

                        <div className="flex gap-1 pl-5 flex-wrap mt-1 pt-2 border-t border-border/50">
                          {COLUMNS.filter(c => c.id !== col.id).map(c => (
                            <Button key={c.id} variant="ghost" className="h-6 text-xs px-2 text-muted-foreground hover:text-foreground" onClick={() => moveTask(task.id, c.id)}>
                              → {c.label}
                            </Button>
                          ))}
                        </div>
                      </CardContent>
                    </Card>
                  ))}

                  {colTasks.length === 0 && (
                    <div className="text-center py-10 text-xs text-muted-foreground border-2 border-dashed border-border rounded-lg">
                      Drop tasks here
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Add New Task</DialogTitle></DialogHeader>
          <form onSubmit={handleAdd} className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Title *</Label>
              <Input placeholder="Task title" value={newTask.title} onChange={e => setNewTask({...newTask, title: e.target.value})} required />
            </div>
            <div className="space-y-2">
              <Label>Description</Label>
              <Input placeholder="Brief description" value={newTask.description} onChange={e => setNewTask({...newTask, description: e.target.value})} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Priority</Label>
                <Select value={newTask.priority} onValueChange={v => setNewTask({...newTask, priority: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="high">High</SelectItem>
                    <SelectItem value="medium">Medium</SelectItem>
                    <SelectItem value="low">Low</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Column</Label>
                <Select value={newTask.status} onValueChange={v => setNewTask({...newTask, status: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="todo">To Do</SelectItem>
                    <SelectItem value="in-progress">In Progress</SelectItem>
                    <SelectItem value="done">Done</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Assignee</Label>
                <Select value={newTask.assignee} onValueChange={v => setNewTask({...newTask, assignee: v})}>
                  <SelectTrigger><SelectValue placeholder="Select person" /></SelectTrigger>
                  <SelectContent>
                    {members.map(m => <SelectItem key={m.id} value={m.name}>{m.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Due Date</Label>
                <Input type="date" value={newTask.due_date} onChange={e => setNewTask({...newTask, due_date: e.target.value})} />
              </div>
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowAdd(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving}>{saving ? 'Adding...' : 'Add Task'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Import Dialog */}
      <Dialog open={showImport} onOpenChange={setShowImport}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Import Kanban Cards</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <p className="text-sm text-muted-foreground">Import cards from Trello or other kanban apps. Export your Trello board as JSON and upload it here.</p>
            <div className="border-2 border-dashed border-border rounded-lg p-8 text-center">
              <Upload size={32} className="mx-auto mb-3 text-muted-foreground" />
              <p className="text-sm font-medium mb-2">Drop JSON file or click to browse</p>
              <input ref={fileRef} type="file" accept=".json" onChange={handleTrelloImport} className="hidden" />
              <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={importing}>{importing ? 'Importing...' : 'Select File'}</Button>
            </div>
            <div className="text-xs text-muted-foreground space-y-1">
              <p className="font-medium">Supported formats:</p>
              <p>Trello JSON export (with cards, lists, checklists)</p>
              <p>Generic: {`{ "cards": [{ "name": "...", "desc": "...", "labels": [...] }] }`}</p>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
