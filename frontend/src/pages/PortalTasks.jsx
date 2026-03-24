import React, { useState, useEffect } from 'react';
import { portalApi } from '../services/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { toast } from 'sonner';

const COLUMNS = [
  { id: 'todo', label: 'To Do', color: 'bg-slate-500' },
  { id: 'in-progress', label: 'In Progress', color: 'bg-blue-500' },
  { id: 'done', label: 'Done', color: 'bg-green-500' },
];
const priorityColors = {
  high: 'bg-red-100 text-red-700 border-red-200',
  medium: 'bg-amber-100 text-amber-700 border-amber-200',
  low: 'bg-slate-100 text-slate-600 border-slate-200',
};

export default function PortalTasks() {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchTasks = async () => {
    setLoading(true);
    try {
      const res = await portalApi.tasks();
      setTasks(res.data);
    } catch { toast.error('Failed to load tasks'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchTasks(); }, []);

  const getByStatus = (status) => tasks.filter(t => t.status === status);

  const moveTask = async (taskId, newStatus) => {
    try {
      await portalApi.updateTaskStatus(taskId, newStatus);
      setTasks(prev => prev.map(t => t.id === taskId ? { ...t, status: newStatus } : t));
      toast.success('Task updated');
    } catch { toast.error('Failed to update task'); }
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" /></div>;

  return (
    <div className="space-y-6" data-testid="portal-tasks">
      <div>
        <h1 className="text-2xl font-bold font-heading">My Tasks</h1>
        <p className="text-sm text-muted-foreground mt-1">{tasks.length} tasks assigned to you</p>
      </div>

      {tasks.length === 0 ? (
        <Card className="shadow-soft rounded-xl">
          <CardContent className="py-12 text-center text-muted-foreground">
            No tasks assigned to you yet.
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {COLUMNS.map(col => (
            <div key={col.id}>
              <div className="flex items-center gap-2 mb-3">
                <div className={`w-2.5 h-2.5 rounded-full ${col.color}`} />
                <h3 className="text-sm font-semibold">{col.label}</h3>
                <Badge variant="secondary" className="text-xs ml-auto">{getByStatus(col.id).length}</Badge>
              </div>
              <div className="space-y-2">
                {getByStatus(col.id).map(task => (
                  <Card key={task.id} className="shadow-soft rounded-xl" data-testid={`portal-task-${task.id}`}>
                    <CardContent className="p-3.5">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-medium leading-tight">{task.title}</p>
                        <Badge className={`text-[10px] shrink-0 ${priorityColors[task.priority] || priorityColors.medium}`}>
                          {task.priority}
                        </Badge>
                      </div>
                      {task.description && <p className="text-xs text-muted-foreground mt-1.5 line-clamp-2">{task.description}</p>}
                      {task.due_date && <p className="text-xs text-muted-foreground mt-1">Due: {task.due_date}</p>}
                      <div className="flex gap-1.5 mt-2.5">
                        {col.id !== 'todo' && (
                          <Button size="sm" variant="outline" className="text-xs h-7 px-2" onClick={() => moveTask(task.id, col.id === 'done' ? 'in-progress' : 'todo')}>
                            {col.id === 'done' ? 'Back to Progress' : 'Back to Todo'}
                          </Button>
                        )}
                        {col.id !== 'done' && (
                          <Button size="sm" className="text-xs h-7 px-2" onClick={() => moveTask(task.id, col.id === 'todo' ? 'in-progress' : 'done')}>
                            {col.id === 'todo' ? 'Start' : 'Complete'}
                          </Button>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))}
                {getByStatus(col.id).length === 0 && (
                  <div className="py-8 text-center text-xs text-muted-foreground border border-dashed rounded-xl">Empty</div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
