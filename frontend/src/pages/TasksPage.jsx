import React, { useState } from 'react';
import { Plus, GripVertical } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { MOCK_TASKS, MOCK_MEMBERS } from '../mock';
import { toast } from 'sonner';

const COLUMNS = [
  { id: 'todo', label: 'To Do', color: 'bg-slate-100 text-slate-700' },
  { id: 'in-progress', label: 'In Progress', color: 'bg-blue-100 text-blue-700' },
  { id: 'done', label: 'Done', color: 'bg-green-100 text-green-700' },
];

const priorityColors = {
  high: 'bg-red-100 text-red-700 border-red-200',
  medium: 'bg-amber-100 text-amber-700 border-amber-200',
  low: 'bg-gray-100 text-gray-600 border-gray-200',
};

export default function TasksPage() {
  const [tasks, setTasks] = useState(MOCK_TASKS);
  const [showAdd, setShowAdd] = useState(false);
  const [dragId, setDragId] = useState(null);
  const [newTask, setNewTask] = useState({ title: '', description: '', priority: 'medium', assignee: '', dueDate: '', status: 'todo' });

  const getTasksByStatus = (status) => tasks.filter(t => t.status === status);

  const handleDragStart = (e, id) => {
    setDragId(id);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDrop = (e, status) => {
    e.preventDefault();
    if (dragId) {
      setTasks(prev => prev.map(t => t.id === dragId ? { ...t, status } : t));
      setDragId(null);
    }
  };

  const handleAddTask = (e) => {
    e.preventDefault();
    const task = { ...newTask, id: `task_${Date.now()}`, tags: [] };
    setTasks(prev => [task, ...prev]);
    setShowAdd(false);
    setNewTask({ title: '', description: '', priority: 'medium', assignee: '', dueDate: '', status: 'todo' });
    toast.success('Task created!');
  };

  const moveTask = (taskId, newStatus) => {
    setTasks(prev => prev.map(t => t.id === taskId ? { ...t, status: newStatus } : t));
  };

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Tasks</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {tasks.filter(t => t.status === 'todo').length} to do · {tasks.filter(t => t.status === 'in-progress').length} in progress · {tasks.filter(t => t.status === 'done').length} done
          </p>
        </div>
        <Button onClick={() => setShowAdd(true)} className="gap-2">
          <Plus size={16} /> Add Task
        </Button>
      </div>

      {/* Kanban Board */}
      <div className="grid lg:grid-cols-3 gap-5 min-h-[500px]">
        {COLUMNS.map(col => {
          const colTasks = getTasksByStatus(col.id);
          return (
            <div
              key={col.id}
              className="flex flex-col bg-secondary/40 rounded-xl p-3 min-h-[400px]"
              onDragOver={e => e.preventDefault()}
              onDrop={e => handleDrop(e, col.id)}
            >
              <div className="flex items-center justify-between mb-3 px-1">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${col.color}`}>{col.label}</span>
                  <span className="text-xs text-muted-foreground">{colTasks.length}</span>
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
                    <CardContent className="p-3.5 space-y-2">
                      <div className="flex items-start gap-2">
                        <GripVertical size={13} className="mt-0.5 text-muted-foreground shrink-0" />
                        <p className="text-sm font-medium leading-snug flex-1">{task.title}</p>
                      </div>

                      {task.description && (
                        <p className="text-xs text-muted-foreground pl-5 leading-relaxed line-clamp-2">{task.description}</p>
                      )}

                      <div className="flex items-center justify-between pl-5 mt-2">
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium border capitalize ${priorityColors[task.priority]}`}>
                          {task.priority}
                        </span>
                        {task.dueDate && (
                          <span className="text-xs text-muted-foreground">{task.dueDate}</span>
                        )}
                      </div>

                      {task.assignee && (
                        <p className="text-xs text-muted-foreground pl-5">👤 {task.assignee}</p>
                      )}

                      {/* Quick move buttons */}
                      <div className="flex gap-1 pl-5 flex-wrap">
                        {COLUMNS.filter(c => c.id !== col.id).map(c => (
                          <Button
                            key={c.id}
                            variant="ghost"
                            className="h-6 text-xs px-2 text-muted-foreground hover:text-foreground"
                            onClick={() => moveTask(task.id, c.id)}
                          >
                            → {c.label}
                          </Button>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                ))}

                {colTasks.length === 0 && (
                  <div className="text-center py-8 text-xs text-muted-foreground border-2 border-dashed border-border rounded-lg">
                    Drop tasks here
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Add Task Dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Add New Task</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleAddTask} className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Title</Label>
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
                <Label>Status</Label>
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
                    {MOCK_MEMBERS.map(m => <SelectItem key={m.id} value={m.name}>{m.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Due Date</Label>
                <Input type="date" value={newTask.dueDate} onChange={e => setNewTask({...newTask, dueDate: e.target.value})} />
              </div>
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowAdd(false)}>Cancel</Button>
              <Button type="submit" className="flex-1">Add Task</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
