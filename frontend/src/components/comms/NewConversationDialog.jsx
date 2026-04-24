import React from 'react';
import { X } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Badge } from '../ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';

export function NewConversationDialog({ open, onOpenChange, convForm, setConvForm, allStaff, userId, getUserPresence, PRESENCE_DOTS, onCreateConv }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
        <DialogHeader><DialogTitle>New Conversation</DialogTitle></DialogHeader>
        <div className="space-y-4 mt-2">
          <div className="space-y-2"><Label>{convForm.participants.length > 1 ? 'Group Name *' : 'Conversation Name'}</Label>
            <Input placeholder={convForm.participants.length > 1 ? 'e.g. Entebbe Team' : 'Optional name'} value={convForm.name} onChange={e => setConvForm({...convForm, name: e.target.value})} data-testid="conv-name-input" />
          </div>
          {convForm.participants.length > 1 && (
            <p className="text-xs text-muted-foreground bg-blue-50 dark:bg-blue-950 px-3 py-1.5 rounded-lg">Group chat (2+ participants selected)</p>
          )}
          <div className="space-y-2"><Label>Add Participants</Label>
            <Select onValueChange={v => {
              if (!convForm.participants.includes(v)) {
                const newP = [...convForm.participants, v];
                setConvForm({...convForm, participants: newP, type: newP.length > 1 ? 'group' : 'direct'});
              }
            }}>
              <SelectTrigger><SelectValue placeholder="Select staff..." /></SelectTrigger>
              <SelectContent>
                {allStaff.filter(s => s.id !== userId).map(s => (
                  <SelectItem key={s.id} value={s.id}>
                    <span className="flex items-center gap-2">
                      {s.name} ({s.role})
                      <span className={`w-2 h-2 rounded-full ${PRESENCE_DOTS[getUserPresence(s.id)] || 'bg-gray-400'}`} />
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="flex flex-wrap gap-1 mt-1">
              {convForm.participants.map(pid => {
                const staff = allStaff.find(s => s.id === pid);
                return (
                  <Badge key={pid} variant="secondary" className="text-xs gap-1 cursor-pointer" onClick={() => {
                    const newP = convForm.participants.filter(p => p !== pid);
                    setConvForm({...convForm, participants: newP, type: newP.length > 1 ? 'group' : 'direct'});
                  }}>
                    {staff?.name || pid} &times;
                  </Badge>
                );
              })}
            </div>
          </div>
          <div className="flex gap-3 pt-2">
            <Button variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button className="flex-1" disabled={convForm.participants.length === 0} onClick={onCreateConv} data-testid="create-conv-btn">
              {convForm.participants.length > 1 ? 'Create Group' : 'Start Chat'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
