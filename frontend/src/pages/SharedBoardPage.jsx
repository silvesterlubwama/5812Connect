import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Badge } from '../components/ui/badge';
import { Calendar, Clock, Users } from 'lucide-react';
import api from '../services/api';

const priorityColors = { high: 'bg-red-500', medium: 'bg-amber-500', low: 'bg-green-500' };

export default function SharedBoardPage() {
  const { shareToken } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get(`/public/boards/${shareToken}`)
      .then(res => setData(res.data))
      .catch(() => setError('Board not found or sharing is disabled'))
      .finally(() => setLoading(false));
  }, [shareToken]);

  if (loading) return (
    <div className="min-h-screen bg-[#0b1121] flex items-center justify-center">
      <div className="text-white/40 animate-pulse">Loading board...</div>
    </div>
  );

  if (error) return (
    <div className="min-h-screen bg-[#0b1121] flex items-center justify-center">
      <div className="text-center">
        <p className="text-white/60 text-lg">{error}</p>
        <p className="text-white/30 text-sm mt-2">This board may have been unshared or doesn't exist.</p>
      </div>
    </div>
  );

  const { board, lists, tasks } = data;
  const tasksByList = {};
  (tasks || []).forEach(t => {
    const lid = t.list_id || 'none';
    if (!tasksByList[lid]) tasksByList[lid] = [];
    tasksByList[lid].push(t);
  });

  return (
    <div className="min-h-screen bg-[#0b1121] text-white" data-testid="shared-board-page">
      <div className="px-6 py-4 border-b border-white/10" style={{ background: 'rgba(255,255,255,0.03)' }}>
        <div className="flex items-center gap-3">
          <span className="w-4 h-4 rounded" style={{ background: board.background || '#3b82f6' }} />
          <h1 className="text-lg font-semibold">{board.name}</h1>
          <Badge variant="secondary" className="text-[10px]">Read-only</Badge>
        </div>
        {board.description && <p className="text-xs text-white/40 mt-1">{board.description}</p>}
      </div>

      <div className="flex gap-4 p-4 overflow-x-auto" style={{ minHeight: 'calc(100vh - 64px)' }}>
        {(lists || []).map(list => (
          <div key={list.id} className="flex-shrink-0 w-72 bg-white/5 rounded-lg border border-white/10 flex flex-col max-h-[80vh]">
            <div className="px-3 py-2.5 border-b border-white/10 flex items-center justify-between">
              <h3 className="text-sm font-medium text-white/80">{list.name}</h3>
              <span className="text-xs text-white/30">{(tasksByList[list.id] || []).length}</span>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-2">
              {(tasksByList[list.id] || []).map(task => (
                <div key={task.id} className="rounded-lg p-3 bg-[#0f172a] border border-white/10">
                  {(task.labels || []).length > 0 && (
                    <div className="flex gap-1 mb-1.5 flex-wrap">
                      {task.labels.map((l, i) => <span key={l.color || i} className="w-8 h-1.5 rounded-full" style={{ background: l.color }} />)}
                    </div>
                  )}
                  <p className="text-xs font-medium text-white/90">{task.title}</p>
                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    {task.priority && <span className={`w-2 h-2 rounded-full ${priorityColors[task.priority] || 'bg-slate-500'}`} />}
                    {task.due_date && <span className="text-[10px] text-white/40 flex items-center gap-1"><Calendar size={9} />{task.due_date}</span>}
                    {(task.assignees || []).length > 0 && <span className="text-[10px] text-white/40 flex items-center gap-1"><Users size={9} />{task.assignees.length}</span>}
                    {task.is_recurring && <span className="text-[10px] text-violet-400">repeat</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
