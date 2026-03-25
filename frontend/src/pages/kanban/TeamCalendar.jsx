import React, { useState, useMemo } from 'react';
import { ChevronLeft, ChevronRight, Users, Clock, AlertTriangle } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Avatar, AvatarFallback } from '../../components/ui/avatar';
import { tasksApi } from '../../services/api';
import { toast } from 'sonner';

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const PRIORITY_COLORS = { low: '#10b981', medium: '#f59e0b', high: '#f97316', urgent: '#ef4444' };

function initials(name) {
  return (name || '?').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
}

function userColor(name) {
  return `hsl(${(name.charCodeAt(0) * 37) % 360}, 55%, 42%)`;
}

export function TeamCalendar({ boards, allTasks, staffUsers, onCardClick, onRefresh }) {
  const today = new Date();
  const [current, setCurrent] = useState({ month: today.getMonth(), year: today.getFullYear() });
  const [filterAssignee, setFilterAssignee] = useState('all');
  const [filterBoard, setFilterBoard] = useState('all');
  const [dragTask, setDragTask] = useState(null);
  const [dragOverDate, setDragOverDate] = useState(null);

  const handleDrop = async (dateStr) => {
    if (!dragTask || dragTask.due_date === dateStr) { setDragTask(null); setDragOverDate(null); return; }
    try {
      await tasksApi.update(dragTask.id, { due_date: dateStr });
      toast.success(`Rescheduled to ${dateStr}`);
      if (onRefresh) onRefresh();
    } catch { toast.error('Failed to reschedule'); }
    setDragTask(null);
    setDragOverDate(null);
  };

  const prev = () => setCurrent(c => c.month === 0 ? { month: 11, year: c.year - 1 } : { ...c, month: c.month - 1 });
  const next = () => setCurrent(c => c.month === 11 ? { month: 0, year: c.year + 1 } : { ...c, month: c.month + 1 });
  const goToday = () => setCurrent({ month: today.getMonth(), year: today.getFullYear() });

  const firstDay = new Date(current.year, current.month, 1).getDay();
  const daysInMonth = new Date(current.year, current.month + 1, 0).getDate();

  // Flatten all tasks into an array with due dates
  const tasks = useMemo(() => {
    let list = [];
    for (const t of allTasks) {
      if (t.is_archived) continue;
      if (filterBoard !== 'all' && t.board_id !== filterBoard) continue;
      const assignees = t.assignees || [];
      if (t.assignee && !assignees.includes(t.assignee)) assignees.push(t.assignee);
      if (filterAssignee !== 'all' && !assignees.includes(filterAssignee)) continue;
      list.push(t);
    }
    return list;
  }, [allTasks, filterAssignee, filterBoard]);

  // Group by date
  const tasksByDate = useMemo(() => {
    const map = {};
    for (const t of tasks) {
      if (!t.due_date) continue;
      const d = t.due_date.slice(0, 10);
      if (!map[d]) map[d] = [];
      map[d].push(t);
    }
    return map;
  }, [tasks]);

  // Workload stats per assignee
  const workloadStats = useMemo(() => {
    const stats = {};
    const monthStr = `${current.year}-${String(current.month + 1).padStart(2, '0')}`;
    for (const t of tasks) {
      if (!t.due_date || !t.due_date.startsWith(monthStr)) continue;
      const assignees = [...(t.assignees || [])];
      if (t.assignee && !assignees.includes(t.assignee)) assignees.push(t.assignee);
      for (const uid of assignees) {
        if (!stats[uid]) stats[uid] = { total: 0, overdue: 0, done: 0 };
        stats[uid].total++;
        if (t.status === 'done') stats[uid].done++;
        else if (new Date(t.due_date) < today) stats[uid].overdue++;
      }
    }
    return stats;
  }, [tasks, current, today]);

  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

  // Count tasks without due dates
  const noDueDateCount = tasks.filter(t => !t.due_date).length;

  return (
    <div className="flex flex-col h-full" style={{ minHeight: 'calc(100vh - 130px)' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 flex-shrink-0 border-b border-white/10" style={{ background: 'rgba(255,255,255,0.04)' }}>
        <div className="flex items-center gap-3">
          <Button size="sm" variant="ghost" className="text-slate-400 hover:text-white hover:bg-white/10 h-8 w-8 p-0" onClick={prev}>
            <ChevronLeft size={16} />
          </Button>
          <h2 className="text-base font-semibold text-white min-w-[180px] text-center" data-testid="team-calendar-title">
            {MONTHS[current.month]} {current.year}
          </h2>
          <Button size="sm" variant="ghost" className="text-slate-400 hover:text-white hover:bg-white/10 h-8 w-8 p-0" onClick={next}>
            <ChevronRight size={16} />
          </Button>
          <Button size="sm" variant="ghost" className="text-slate-400 hover:text-white hover:bg-white/10 h-8 text-xs" onClick={goToday}>
            Today
          </Button>
        </div>
        <div className="flex items-center gap-3">
          <Select value={filterBoard} onValueChange={setFilterBoard}>
            <SelectTrigger className="w-40 h-8 bg-[#0f172a] border-white/15 text-slate-200 text-xs">
              <SelectValue placeholder="All Boards" />
            </SelectTrigger>
            <SelectContent className="bg-[#1e293b] border-white/15">
              <SelectItem value="all" className="text-slate-200">All Boards</SelectItem>
              {boards.map(b => <SelectItem key={b.id} value={b.id} className="text-slate-200">{b.name}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={filterAssignee} onValueChange={setFilterAssignee}>
            <SelectTrigger className="w-44 h-8 bg-[#0f172a] border-white/15 text-slate-200 text-xs">
              <SelectValue placeholder="All Members" />
            </SelectTrigger>
            <SelectContent className="bg-[#1e293b] border-white/15">
              <SelectItem value="all" className="text-slate-200">All Members</SelectItem>
              {staffUsers.map(u => <SelectItem key={u.id} value={u.id} className="text-slate-200">{u.name}</SelectItem>)}
            </SelectContent>
          </Select>
          {noDueDateCount > 0 && (
            <Badge className="bg-amber-500/20 text-amber-400 text-[10px] border-0">{noDueDateCount} unscheduled</Badge>
          )}
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Calendar Grid */}
        <div className="flex-1 p-4 overflow-y-auto">
          {/* Day headers */}
          <div className="grid grid-cols-7 mb-1">
            {DAYS.map(d => (
              <div key={d} className="text-center text-[10px] font-semibold text-slate-500 uppercase tracking-wider py-1">{d}</div>
            ))}
          </div>

          {/* Calendar cells */}
          <div className="grid grid-cols-7 gap-px" style={{ background: 'rgba(255,255,255,0.05)' }}>
            {/* Empty cells before month starts */}
            {[...Array(firstDay)].map((_, i) => (
              <div key={`empty-${i}`} className="min-h-[100px] p-1" style={{ background: '#0d1321' }} />
            ))}
            {/* Day cells */}
            {[...Array(daysInMonth)].map((_, i) => {
              const day = i + 1;
              const dateStr = `${current.year}-${String(current.month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
              const dayTasks = tasksByDate[dateStr] || [];
              const isToday = dateStr === todayStr;
              const isPast = new Date(dateStr) < new Date(todayStr);

              return (
                <div key={day} className={`min-h-[100px] p-1.5 transition-colors ${isToday ? 'ring-1 ring-inset ring-blue-500' : ''} ${dragOverDate === dateStr ? 'ring-2 ring-inset ring-green-400 bg-green-500/10' : ''}`}
                  style={{ background: isToday && dragOverDate !== dateStr ? 'rgba(59,130,246,0.08)' : dragOverDate === dateStr ? undefined : '#0f172a' }}
                  data-testid={`calendar-day-${dateStr}`}
                  onDragOver={(e) => { e.preventDefault(); setDragOverDate(dateStr); }}
                  onDragLeave={() => setDragOverDate(null)}
                  onDrop={(e) => { e.preventDefault(); handleDrop(dateStr); }}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className={`text-xs font-semibold ${isToday ? 'text-blue-400' : isPast ? 'text-slate-600' : 'text-slate-400'}`}>
                      {day}
                    </span>
                    {dayTasks.length > 0 && (
                      <span className="text-[9px] text-slate-500">{dayTasks.length}</span>
                    )}
                  </div>
                  <div className="space-y-0.5">
                    {dayTasks.slice(0, 4).map(task => {
                      const isOverdue = isPast && task.status !== 'done';
                      const board = boards.find(b => b.id === task.board_id);
                      return (
                        <button key={task.id}
                          onClick={() => onCardClick(task)}
                          draggable
                          onDragStart={(e) => { e.dataTransfer.effectAllowed = 'move'; setDragTask(task); }}
                          onDragEnd={() => { setDragTask(null); setDragOverDate(null); }}
                          className={`w-full text-left rounded px-1.5 py-0.5 text-[10px] truncate transition-colors hover:brightness-125 ${
                            task.status === 'done' ? 'line-through opacity-50' : ''
                          }`}
                          style={{
                            background: isOverdue ? 'rgba(239,68,68,0.2)' : `${board?.background || '#3b82f6'}20`,
                            color: isOverdue ? '#fca5a5' : '#cbd5e1',
                            borderLeft: `2px solid ${PRIORITY_COLORS[task.priority] || board?.background || '#3b82f6'}`,
                          }}
                          data-testid={`calendar-task-${task.id}`}
                          title={`${task.title} (${task.status})`}
                        >
                          {task.title}
                        </button>
                      );
                    })}
                    {dayTasks.length > 4 && (
                      <span className="text-[9px] text-slate-500 pl-1.5">+{dayTasks.length - 4} more</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Workload Sidebar */}
        <div className="w-56 flex-shrink-0 bg-[#1e293b] border-l border-white/10 overflow-y-auto">
          <div className="p-3 border-b border-white/10">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest flex items-center gap-1.5">
              <Users size={12} /> Workload
            </p>
            <p className="text-[10px] text-slate-500 mt-0.5">{MONTHS[current.month]} {current.year}</p>
          </div>
          <div className="p-2 space-y-1">
            {Object.entries(workloadStats)
              .sort((a, b) => b[1].total - a[1].total)
              .map(([uid, stats]) => {
                const user = staffUsers.find(u => u.id === uid);
                if (!user) return null;
                const pct = stats.total > 0 ? Math.round((stats.done / stats.total) * 100) : 0;
                return (
                  <div key={uid} className="flex items-center gap-2 p-2 rounded-lg hover:bg-white/5 transition-colors cursor-pointer"
                    onClick={() => setFilterAssignee(filterAssignee === uid ? 'all' : uid)}
                    data-testid={`workload-user-${uid}`}
                  >
                    <Avatar className="h-7 w-7">
                      <AvatarFallback className="text-[10px] font-bold text-white" style={{ background: userColor(user.name) }}>
                        {initials(user.name)}
                      </AvatarFallback>
                    </Avatar>
                    <div className="flex-1 min-w-0">
                      <p className={`text-[11px] font-medium truncate ${filterAssignee === uid ? 'text-blue-400' : 'text-slate-300'}`}>{user.name}</p>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <div className="flex-1 h-1 bg-white/10 rounded-full overflow-hidden">
                          <div className="h-full rounded-full bg-emerald-500" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="text-[9px] text-slate-500">{stats.done}/{stats.total}</span>
                      </div>
                    </div>
                    {stats.overdue > 0 && (
                      <span className="flex items-center gap-0.5 text-[9px] text-red-400">
                        <AlertTriangle size={9} /> {stats.overdue}
                      </span>
                    )}
                  </div>
                );
              })}
            {Object.keys(workloadStats).length === 0 && (
              <p className="text-[11px] text-slate-500 text-center py-6">No assigned tasks with due dates this month</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
