import React, { useState, useEffect } from 'react';
import { Archive, RotateCcw } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Button } from '../../components/ui/button';
import { boardsApi, tasksExtApi } from '../../services/api';

export function ArchivePanel({ open, onClose, boardId, onRestoreCard, onRestoreList }) {
  const [archivedCards, setArchivedCards] = useState([]);
  const [archivedLists, setArchivedLists] = useState([]);
  const [tab, setTab] = useState('cards');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !boardId) return;
    setLoading(true);
    Promise.all([
      tasksExtApi.archived(boardId),
      boardsApi.archivedLists(boardId),
    ]).then(([cardsRes, listsRes]) => {
      setArchivedCards(cardsRes.data || []);
      setArchivedLists(listsRes.data || []);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [open, boardId]);

  const handleRestoreCard = async (card) => {
    try {
      const res = await tasksExtApi.restore(card.id);
      setArchivedCards(prev => prev.filter(c => c.id !== card.id));
      onRestoreCard?.(res.data);
    } catch (e) { console.error("Archive error:", e.message); }
  };

  const handleRestoreList = async (list) => {
    try {
      const res = await boardsApi.restoreList(boardId, list.id);
      setArchivedLists(prev => prev.filter(l => l.id !== list.id));
      onRestoreList?.(res.data);
    } catch (e) { console.error("Archive error:", e.message); }
  };

  return (
    <Dialog open={open} onOpenChange={o => { if (!o) onClose(); }}>
      <DialogContent className="max-w-lg bg-[#1e293b] border-white/10 text-slate-100 max-h-[80vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-slate-100"><Archive size={16} /> Archived Items</DialogTitle>
        </DialogHeader>
        <div className="flex gap-2 mt-2 flex-shrink-0">
          {[['cards', `Cards (${archivedCards.length})`], ['lists', `Lists (${archivedLists.length})`]].map(([v, l]) => (
            <Button key={v} size="sm" variant={tab === v ? 'default' : 'ghost'}
              className={tab === v ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'}
              onClick={() => setTab(v)}>{l}</Button>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto space-y-2 mt-3">
          {loading && <p className="text-xs text-slate-500 text-center py-4">Loading...</p>}
          {!loading && tab === 'cards' && (
            archivedCards.length === 0 ? <p className="text-sm text-slate-500 text-center py-8">No archived cards</p> :
            archivedCards.map(card => (
              <div key={card.id} className="flex items-center justify-between p-3 rounded-lg bg-[#0f172a] border border-white/10">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-slate-200 truncate">{card.title}</p>
                  <p className="text-xs text-slate-500">{card.list_name || 'No list'}</p>
                </div>
                <Button size="sm" variant="ghost" className="text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10 gap-1 ml-2 text-xs"
                  onClick={() => handleRestoreCard(card)}>
                  <RotateCcw size={11} /> Restore
                </Button>
              </div>
            ))
          )}
          {!loading && tab === 'lists' && (
            archivedLists.length === 0 ? <p className="text-sm text-slate-500 text-center py-8">No archived lists</p> :
            archivedLists.map(list => (
              <div key={list.id} className="flex items-center justify-between p-3 rounded-lg bg-[#0f172a] border border-white/10">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-slate-200 truncate">{list.name}</p>
                  <p className="text-xs text-slate-500">Archived</p>
                </div>
                <Button size="sm" variant="ghost" className="text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10 gap-1 ml-2 text-xs"
                  onClick={() => handleRestoreList(list)}>
                  <RotateCcw size={11} /> Restore
                </Button>
              </div>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
