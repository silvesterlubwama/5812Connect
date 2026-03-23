import React, { useState } from 'react';
import { Search, Plus, UserCheck } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Card, CardContent } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { MOCK_CHECKINS, MOCK_EVENTS } from '../mock';
import { toast } from 'sonner';

const methodBadge = { qr: 'bg-blue-100 text-blue-700', manual: 'bg-gray-100 text-gray-700', id: 'bg-purple-100 text-purple-700' };
const typeBadge = { member: 'border-green-500 text-green-600', staff: 'border-blue-500 text-blue-600', visitor: 'border-orange-500 text-orange-600' };

export default function CheckInsPage() {
  const [checkins, setCheckins] = useState(MOCK_CHECKINS);
  const [search, setSearch] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [newCheckin, setNewCheckin] = useState({ memberName: '', type: 'member', eventName: '', method: 'manual' });

  const filtered = checkins.filter(c =>
    !search || c.memberName.toLowerCase().includes(search.toLowerCase()) || c.eventName.toLowerCase().includes(search.toLowerCase())
  );

  const handleAdd = (e) => {
    e.preventDefault();
    const ci = {
      ...newCheckin,
      id: `ci_${Date.now()}`,
      memberId: null,
      checkInTime: new Date().toISOString(),
    };
    setCheckins(prev => [ci, ...prev]);
    setShowAdd(false);
    setNewCheckin({ memberName: '', type: 'member', eventName: '', method: 'manual' });
    toast.success(`${ci.memberName} checked in successfully!`);
  };

  const formatTime = (isoStr) => {
    return new Date(isoStr).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Check-Ins</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{checkins.length} total check-ins recorded</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <a href="/kiosk" target="_blank" className="gap-2">
              <UserCheck size={16} /> Open Kiosk
            </a>
          </Button>
          <Button onClick={() => setShowAdd(true)} className="gap-2">
            <Plus size={16} /> Manual Check-In
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <Card className="shadow-soft rounded-xl">
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-primary">{checkins.filter(c => c.type === 'member').length}</p>
            <p className="text-xs text-muted-foreground mt-0.5">Members</p>
          </CardContent>
        </Card>
        <Card className="shadow-soft rounded-xl">
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-blue-600">{checkins.filter(c => c.type === 'staff').length}</p>
            <p className="text-xs text-muted-foreground mt-0.5">Staff</p>
          </CardContent>
        </Card>
        <Card className="shadow-soft rounded-xl">
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-orange-500">{checkins.filter(c => c.type === 'visitor').length}</p>
            <p className="text-xs text-muted-foreground mt-0.5">Visitors</p>
          </CardContent>
        </Card>
      </div>

      {/* Search */}
      <div className="relative max-w-md">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input placeholder="Search check-ins..." className="pl-9" value={search} onChange={e => setSearch(e.target.value)} />
      </div>

      {/* Table */}
      <Card className="shadow-soft rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-secondary/50 border-b border-border">
              <tr>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Person</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Type</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Event</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Method</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filtered.map(ci => (
                <tr key={ci.id} className="hover:bg-accent/30 transition-colors">
                  <td className="px-4 py-3 font-medium">{ci.memberName}</td>
                  <td className="px-4 py-3">
                    <Badge variant="outline" className={`text-xs capitalize ${typeBadge[ci.type] || ''}`}>
                      {ci.type}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{ci.eventName}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium uppercase ${methodBadge[ci.method] || ''}`}>
                      {ci.method}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">{formatTime(ci.checkInTime)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <p className="text-center py-10 text-muted-foreground">No check-ins found</p>
          )}
        </div>
      </Card>

      {/* Manual Check-In Dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Manual Check-In</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleAdd} className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Person Name</Label>
              <Input placeholder="Full name" value={newCheckin.memberName} onChange={e => setNewCheckin({...newCheckin, memberName: e.target.value})} required />
            </div>
            <div className="space-y-2">
              <Label>Type</Label>
              <Select value={newCheckin.type} onValueChange={v => setNewCheckin({...newCheckin, type: v})}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="member">Member</SelectItem>
                  <SelectItem value="staff">Staff</SelectItem>
                  <SelectItem value="visitor">Visitor</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Event</Label>
              <Select value={newCheckin.eventName} onValueChange={v => setNewCheckin({...newCheckin, eventName: v})}>
                <SelectTrigger><SelectValue placeholder="Select event" /></SelectTrigger>
                <SelectContent>
                  {MOCK_EVENTS.map(e => <SelectItem key={e.id} value={e.title}>{e.title}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowAdd(false)}>Cancel</Button>
              <Button type="submit" className="flex-1">Check In</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
