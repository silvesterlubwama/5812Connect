import React from 'react';
import { Video, X } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Badge } from '../ui/badge';
import { Textarea } from '../ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';

export function ConferenceDialog({ open, onOpenChange, confForm, setConfForm, allStaff, userId, onSubmit }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Schedule Conference</DialogTitle></DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4 mt-2">
          <div className="space-y-2"><Label>Title *</Label><Input placeholder="Team Standup" value={confForm.title} onChange={e => setConfForm({...confForm, title: e.target.value})} required data-testid="conf-title" /></div>
          <div className="space-y-2"><Label>Description</Label><Textarea rows={2} placeholder="Meeting agenda..." value={confForm.description} onChange={e => setConfForm({...confForm, description: e.target.value})} /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2"><Label>Date & Time</Label><Input type="datetime-local" value={confForm.scheduled_at} onChange={e => setConfForm({...confForm, scheduled_at: e.target.value})} data-testid="conf-datetime" /></div>
            <div className="space-y-2"><Label>Duration (min)</Label><Input type="number" min={15} max={480} value={confForm.duration_minutes} onChange={e => setConfForm({...confForm, duration_minutes: parseInt(e.target.value) || 60})} /></div>
          </div>
          <div className="space-y-2">
            <Label>Invite Staff</Label>
            <Select onValueChange={v => { if (v && !confForm.user_ids.includes(v)) setConfForm({...confForm, user_ids: [...confForm.user_ids, v]}); }}>
              <SelectTrigger><SelectValue placeholder="Add participants..." /></SelectTrigger>
              <SelectContent>{allStaff.filter(s => s.id !== userId && !confForm.user_ids.includes(s.id)).map(s => (
                <SelectItem key={s.id} value={s.id}>{s.name} ({s.role})</SelectItem>
              ))}</SelectContent>
            </Select>
            <div className="flex flex-wrap gap-1">{confForm.user_ids.map(uid => {
              const s = allStaff.find(x => x.id === uid);
              return <Badge key={uid} variant="secondary" className="text-xs gap-1 cursor-pointer" onClick={() => setConfForm({...confForm, user_ids: confForm.user_ids.filter(i => i !== uid)})}>{s?.name || uid} <X size={10} /></Badge>;
            })}</div>
          </div>
          <div className="space-y-2">
            <Label>External Email Invites</Label>
            <Input placeholder="email1@example.com, email2@example.com" value={confForm.external_emails} onChange={e => setConfForm({...confForm, external_emails: e.target.value})} data-testid="conf-ext-emails" />
            <p className="text-[10px] text-muted-foreground">Comma-separated emails for non-users</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2"><Label>Password (optional)</Label><Input placeholder="Meeting password" value={confForm.password} onChange={e => setConfForm({...confForm, password: e.target.value})} /></div>
            <div className="flex items-center gap-2 pt-6"><input type="checkbox" id="conf-video" checked={confForm.is_video_enabled} onChange={e => setConfForm({...confForm, is_video_enabled: e.target.checked})} /><Label htmlFor="conf-video" className="cursor-pointer text-xs">Video enabled</Label></div>
          </div>
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-xs cursor-pointer"><input type="checkbox" checked={confForm.create_calendar_event} onChange={e => setConfForm({...confForm, create_calendar_event: e.target.checked})} />Add to Calendar</label>
            <label className="flex items-center gap-2 text-xs cursor-pointer"><input type="checkbox" checked={confForm.send_email_invites} onChange={e => setConfForm({...confForm, send_email_invites: e.target.checked})} />Send Email Invites</label>
          </div>
          <div className="flex gap-3 pt-2">
            <Button type="button" variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" className="flex-1" data-testid="create-conf-btn">Schedule</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
