import React, { useEffect, useMemo, useState } from 'react';
import { MapPin, ArrowRightLeft } from 'lucide-react';
import { Button } from './ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Label } from './ui/label';
import { eventsApi, productsApi, boardsApi, tasksApi, locationsApi } from '../services/api';
import { toast } from 'sonner';

/**
 * Reusable "Move this record to another campus" dialog.
 *
 * Props:
 *   open, onOpenChange   — controlled dialog visibility
 *   kind                  — 'event' | 'board' | 'product' | 'task'
 *   record                — the record object being moved. Must include:
 *                             { id, location_id?, location_name?, title?/name?, board_id? (task) }
 *   currentBoardName      — task only, shown in the header
 *   onMoved(updated)      — callback after successful relocation
 *
 * Backing endpoints:
 *   event / board / product  → PUT /<collection>/{id} with { location_id, location_name }
 *   task                     → PUT /tasks/{id} with { board_id, list_id, list_name }
 *                              (task inherits campus from board, so we move the
 *                              board pointer rather than duplicating a location_id)
 */
export function CrossCampusMoveDialog({ open, onOpenChange, kind, record, currentBoardName, onMoved }) {
  const [locations, setLocations] = useState([]);
  const [boards, setBoards] = useState([]);
  const [busy, setBusy] = useState(false);
  const [targetLocationId, setTargetLocationId] = useState('');
  const [targetBoardId, setTargetBoardId] = useState('');
  const [targetListId, setTargetListId] = useState('');

  const isTask = kind === 'task';
  const label = {
    event: 'event',
    board: 'board',
    product: 'product',
    task: 'card',
  }[kind] || 'record';

  // Load campuses + (task only) boards on open.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      try {
        const [locsRes, boardsRes] = await Promise.all([
          locationsApi.list().catch(() => ({ data: [] })),
          isTask ? boardsApi.list().catch(() => ({ data: [] })) : Promise.resolve({ data: [] }),
        ]);
        if (cancelled) return;
        setLocations(locsRes.data || []);
        setBoards(boardsRes.data || []);
        setTargetLocationId(record?.location_id || '');
        setTargetBoardId(isTask ? (record?.board_id || '') : '');
        setTargetListId('');
      } catch {
        if (!cancelled) toast.error('Could not load destinations');
      }
    })();
    return () => { cancelled = true; };
  }, [open, isTask, record?.location_id, record?.board_id]);

  // For task moves: once a target board is chosen, pull its lists so we know
  // where the card should land.
  const [targetLists, setTargetLists] = useState([]);
  useEffect(() => {
    if (!isTask || !targetBoardId) { setTargetLists([]); return; }
    let cancelled = false;
    boardsApi.get(targetBoardId)
      .then(r => {
        if (cancelled) return;
        const lists = (r.data?.lists || []).filter(l => !l.is_archived);
        setTargetLists(lists);
        // Default to the first list in the target board
        setTargetListId(lists[0]?.id || '');
      })
      .catch(() => setTargetLists([]));
    return () => { cancelled = true; };
  }, [isTask, targetBoardId]);

  // Group boards by campus for the task-move picker so admins can eyeball
  // where each destination lives without opening another tab.
  const boardsByCampus = useMemo(() => {
    if (!isTask) return [];
    const byCampus = new Map();
    for (const b of boards) {
      if (b.id === record?.board_id) continue; // can't move to same board
      const key = b.location_id || '__global__';
      if (!byCampus.has(key)) byCampus.set(key, []);
      byCampus.get(key).push(b);
    }
    const groups = [];
    for (const [locId, list] of byCampus.entries()) {
      const locName = locId === '__global__'
        ? 'Global (no campus)'
        : (locations.find(l => l.id === locId)?.name || locId);
      groups.push({ locId, locName, boards: list.sort((a, b) => (a.name || '').localeCompare(b.name || '')) });
    }
    return groups.sort((a, b) => a.locName.localeCompare(b.locName));
  }, [isTask, boards, locations, record?.board_id]);

  const currentLocationName = record?.location_name
    || locations.find(l => l.id === record?.location_id)?.name
    || (record?.location_id ? record.location_id : 'Global');

  const canApply = isTask
    ? !!(targetBoardId && targetBoardId !== record?.board_id && targetListId)
    : !!(targetLocationId && targetLocationId !== record?.location_id);

  const apply = async () => {
    if (!record?.id || !canApply) return;
    setBusy(true);
    try {
      let updated;
      if (kind === 'event') {
        const loc = locations.find(l => l.id === targetLocationId);
        const res = await eventsApi.update(record.id, {
          location_id: targetLocationId,
          location: loc?.name || record.location || '',
          country: loc?.country || record.country || '',
        });
        updated = res.data;
      } else if (kind === 'board') {
        const loc = locations.find(l => l.id === targetLocationId);
        const res = await boardsApi.update(record.id, {
          location_id: targetLocationId,
          location_name: loc?.name || '',
          is_global: false,
        });
        updated = res.data;
      } else if (kind === 'product') {
        const res = await productsApi.update(record.id, { location_id: targetLocationId });
        updated = res.data;
      } else if (kind === 'task') {
        const targetBoard = boards.find(b => b.id === targetBoardId);
        const targetList = targetLists.find(l => l.id === targetListId);
        const res = await tasksApi.update(record.id, {
          board_id: targetBoardId,
          list_id: targetListId,
          list_name: targetList?.name || '',
        });
        updated = { ...res.data, _movedTo: targetBoard };
      }
      const newLocName = kind === 'task'
        ? (boards.find(b => b.id === targetBoardId)?.name || 'target board')
        : (locations.find(l => l.id === targetLocationId)?.name || 'target campus');
      toast.success(`Moved to ${newLocName}`);
      onMoved?.(updated);
      onOpenChange(false);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Move failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm" data-testid="cross-campus-move-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ArrowRightLeft size={16} /> Move {label}
          </DialogTitle>
          <DialogDescription>
            {isTask ? (
              <>Move this card to another board — including boards in other campuses. Currently on <strong>{currentBoardName || 'this board'}</strong>.</>
            ) : (
              <>Relocate this {label} to a different campus. Currently on <strong>{currentLocationName}</strong>.</>
            )}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          {isTask ? (
            <>
              <div className="space-y-1.5">
                <Label className="text-xs">Destination board</Label>
                <Select value={targetBoardId} onValueChange={setTargetBoardId}>
                  <SelectTrigger data-testid="move-target-board-select">
                    <SelectValue placeholder="Pick a board…" />
                  </SelectTrigger>
                  <SelectContent>
                    {boardsByCampus.length === 0 && (
                      <SelectItem value="__none__" disabled>No other boards available</SelectItem>
                    )}
                    {boardsByCampus.map(group => (
                      <React.Fragment key={group.locId}>
                        <div className="px-2 py-1 text-[10px] font-semibold uppercase text-muted-foreground bg-muted/40 border-b border-border/40 flex items-center gap-1">
                          <MapPin size={10} /> {group.locName}
                        </div>
                        {group.boards.map(b => (
                          <SelectItem key={b.id} value={b.id} data-testid={`move-target-board-opt-${b.id}`}>
                            <span className="inline-flex items-center gap-1.5">
                              <span className="w-2 h-2 rounded-sm" style={{ background: b.background || '#3b82f6' }} />
                              {b.name}
                            </span>
                          </SelectItem>
                        ))}
                      </React.Fragment>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {targetBoardId && targetLists.length > 0 && (
                <div className="space-y-1.5">
                  <Label className="text-xs">Destination list</Label>
                  <Select value={targetListId} onValueChange={setTargetListId}>
                    <SelectTrigger data-testid="move-target-list-select">
                      <SelectValue placeholder="Pick a list…" />
                    </SelectTrigger>
                    <SelectContent>
                      {targetLists.map(l => (
                        <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </>
          ) : (
            <div className="space-y-1.5">
              <Label className="text-xs">Destination campus</Label>
              <Select value={targetLocationId} onValueChange={setTargetLocationId}>
                <SelectTrigger data-testid="move-target-campus-select">
                  <SelectValue placeholder="Pick a campus…" />
                </SelectTrigger>
                <SelectContent>
                  {locations.length === 0 && (
                    <SelectItem value="__none__" disabled>No campuses available</SelectItem>
                  )}
                  {locations
                    .filter(l => l.id !== record?.location_id)
                    .sort((a, b) => (a.name || '').localeCompare(b.name || ''))
                    .map(l => (
                      <SelectItem key={l.id} value={l.id} data-testid={`move-target-campus-opt-${l.id}`}>
                        <span className="inline-flex items-center gap-1.5">
                          <MapPin size={10} /> {l.name}
                          {l.country && <span className="text-[10px] text-muted-foreground">· {l.country}</span>}
                        </span>
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>
        <div className="flex gap-2 justify-end">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button onClick={apply} disabled={!canApply || busy} data-testid="move-apply-btn">
            {busy ? 'Moving…' : 'Move'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default CrossCampusMoveDialog;
