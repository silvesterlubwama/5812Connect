import React from 'react';
import { Baby, Phone, QrCode, UserCheck } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Badge } from '../ui/badge';
import { Checkbox } from '../ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog';

export function ParentCheckInDialog({
  open, onOpenChange,
  parentLookup, setParentLookup,
  parentEventId, setParentEventId,
  parentData, parentChildren,
  selectedChildIds, toggleChildSelection,
  lookingUp, checkingInChildren,
  events,
  onLookup, onCheckinChildren, onReset,
  showQrScanner, videoRef, onStartQrScan, onStopQrScan,
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) { onOpenChange(false); onStopQrScan(); } }}>
      <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Baby size={18} className="text-emerald-500" /> Parent Check-In</DialogTitle>
          <DialogDescription>Look up a parent by phone, email, ID, or QR code to check in their children</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 mt-2">
          <div className="space-y-2">
            <Label>Event (optional)</Label>
            <Select value={parentEventId || '_none'} onValueChange={v => setParentEventId(v === '_none' ? '' : v)}>
              <SelectTrigger data-testid="parent-event-select"><SelectValue placeholder="Select event" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="_none">No event</SelectItem>
                {events.map(e => <SelectItem key={e.id} value={e.id}>{e.title}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          {!parentData && (
            <>
              <div className="space-y-2">
                <Label>Parent Phone, Email, or ID *</Label>
                <div className="flex gap-2">
                  <Input
                    data-testid="parent-lookup-input"
                    placeholder="e.g. +256 700 123456"
                    value={parentLookup}
                    onChange={e => setParentLookup(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); onLookup(); } }}
                    className="flex-1"
                  />
                  <Button variant="outline" size="icon" onClick={onStartQrScan} title="Scan QR" data-testid="qr-scan-btn"><QrCode size={16} /></Button>
                </div>
              </div>

              {showQrScanner && (
                <div className="relative rounded-lg overflow-hidden border border-border bg-black">
                  <video ref={videoRef} className="w-full h-48 object-cover" muted playsInline />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <div className="w-40 h-40 border-2 border-white/60 rounded-lg" />
                  </div>
                  <Button size="sm" variant="secondary" className="absolute bottom-2 right-2" onClick={onStopQrScan}>Close</Button>
                </div>
              )}

              <Button className="w-full gap-2" onClick={onLookup} disabled={lookingUp || !parentLookup.trim()} data-testid="lookup-parent-btn">
                <Phone size={14} /> {lookingUp ? 'Looking up...' : 'Find Children'}
              </Button>
            </>
          )}

          {parentData && (
            <>
              <div className="p-3 rounded-lg bg-accent/30 border border-border">
                <p className="text-xs text-muted-foreground">Parent Found</p>
                <p className="font-medium">{parentData.name}</p>
                <div className="flex gap-3 text-xs text-muted-foreground mt-0.5">
                  {parentData.phone && <span>{parentData.phone}</span>}
                  {parentData.email && <span>{parentData.email}</span>}
                </div>
              </div>

              {parentChildren.length > 0 ? (
                <div className="space-y-2">
                  <Label>Select Children to Check In</Label>
                  {parentChildren.map(child => (
                    <div key={child.id} className="flex items-center gap-3 p-3 rounded-lg border border-border hover:bg-accent/20 transition-colors" data-testid={`parent-child-${child.id}`}>
                      <Checkbox
                        checked={selectedChildIds.includes(child.id)}
                        onCheckedChange={() => toggleChildSelection(child.id)}
                        data-testid={`select-child-${child.id}`}
                      />
                      <div className="flex-1">
                        <p className="text-sm font-medium">{child.name}</p>
                        <div className="flex gap-2 text-xs text-muted-foreground">
                          {child.class_group && <span>{child.class_group}</span>}
                          {child.gender && <span className="capitalize">{child.gender}</span>}
                        </div>
                        {child.allergies && <Badge variant="destructive" className="text-[10px] mt-1">{child.allergies}</Badge>}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-4">No children found for this parent</p>
              )}

              <div className="flex gap-3 pt-2">
                <Button variant="outline" className="flex-1" onClick={onReset} data-testid="parent-checkin-back">Back</Button>
                <Button
                  className="flex-1 gap-1.5"
                  onClick={onCheckinChildren}
                  disabled={checkingInChildren || selectedChildIds.length === 0}
                  data-testid="checkin-children-btn"
                >
                  <UserCheck size={14} />
                  {checkingInChildren ? 'Checking in...' : `Check In ${selectedChildIds.length} Child${selectedChildIds.length > 1 ? 'ren' : ''}`}
                </Button>
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
