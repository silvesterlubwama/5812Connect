import React from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';

export function AnnouncementDialog({ open, onOpenChange, form, setForm, onSubmit }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Post Announcement</DialogTitle></DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4 mt-2">
          <div className="space-y-2"><Label>Title *</Label>
            <Input placeholder="Announcement title" value={form.title} onChange={e => setForm({...form, title: e.target.value})} required data-testid="announcement-title-input" />
          </div>
          <div className="space-y-2"><Label>Content *</Label>
            <Textarea rows={4} placeholder="Write your announcement..." value={form.content} onChange={e => setForm({...form, content: e.target.value})} required data-testid="announcement-content-input" />
          </div>
          <div className="space-y-2"><Label>Type</Label>
            <Select value={form.type} onValueChange={v => setForm({...form, type: v})}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="general">General</SelectItem>
                <SelectItem value="urgent">Urgent</SelectItem>
                <SelectItem value="event">Event</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex gap-3 pt-2">
            <Button type="button" variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" className="flex-1" data-testid="post-announcement-submit">Post</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
