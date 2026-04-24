import React from 'react';
import { Wifi } from 'lucide-react';
import { Button } from '../ui/button';
import { Label } from '../ui/label';
import { Badge } from '../ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog';

export function NfcCheckInDialog({ open, onOpenChange, nfcStatus, setNfcStatus, nfcMember, setNfcMember, nfcEventId, setNfcEventId, events, onStartScan, onConfirmCheckin }) {
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) { onOpenChange(false); setNfcStatus('idle'); setNfcMember(null); } }}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>NFC Check-In</DialogTitle>
          <DialogDescription>Tap an NFC tag to check in a member</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 mt-2">
          {nfcStatus === 'idle' && (
            <div className="space-y-3">
              <div className="space-y-2">
                <Label>Event (optional)</Label>
                <Select value={nfcEventId || '_none'} onValueChange={v => setNfcEventId(v === '_none' ? '' : v)}>
                  <SelectTrigger><SelectValue placeholder="Select event" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_none">No event</SelectItem>
                    {events.map(e => <SelectItem key={e.id} value={e.id}>{e.title}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <Button className="w-full gap-2" onClick={onStartScan} data-testid="start-nfc-scan">
                <Wifi size={16} /> Start NFC Scan
              </Button>
            </div>
          )}
          {nfcStatus === 'scanning' && (
            <div className="flex flex-col items-center gap-4 py-6">
              <div className="relative">
                <div className="h-20 w-20 rounded-full border-4 border-primary/30 flex items-center justify-center">
                  <Wifi size={32} className="text-primary animate-pulse" />
                </div>
                <div className="absolute inset-0 rounded-full border-4 border-primary border-t-transparent animate-spin" />
              </div>
              <p className="text-sm font-medium">Waiting for NFC tag...</p>
              <p className="text-xs text-muted-foreground text-center">Hold the NFC card or phone near the reader</p>
              <Button variant="outline" size="sm" onClick={() => setNfcStatus('idle')}>Cancel</Button>
            </div>
          )}
          {nfcStatus === 'success' && nfcMember && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-green-50 border border-green-200 text-center">
                <p className="text-xs text-green-600 mb-1">NFC Tag Detected</p>
                <p className="font-semibold text-green-900">{nfcMember.name}</p>
                <p className="text-xs text-green-700">{nfcMember.role} {nfcMember.group ? `· ${nfcMember.group}` : ''}</p>
              </div>
              <div className="flex gap-3">
                <Button variant="outline" className="flex-1" onClick={() => { setNfcStatus('idle'); setNfcMember(null); }}>Cancel</Button>
                <Button className="flex-1" onClick={onConfirmCheckin} data-testid="confirm-nfc-checkin">Confirm Check-In</Button>
              </div>
            </div>
          )}
          {nfcStatus === 'unsupported' && (
            <div className="space-y-3">
              <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-sm text-amber-800">
                <p className="font-medium mb-1">NFC Not Supported</p>
                <p className="text-xs">Web NFC (NDEFReader) requires Chrome on Android. Desktop browsers and Safari are not supported.</p>
                <p className="text-xs mt-2">Please use PIN check-in or manual entry instead.</p>
              </div>
              <Button variant="outline" className="w-full" onClick={() => onOpenChange(false)}>Close</Button>
            </div>
          )}
          {nfcStatus === 'error' && (
            <div className="space-y-3">
              <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-sm text-red-800">NFC scan failed. Please try again.</div>
              <div className="flex gap-3">
                <Button variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>Close</Button>
                <Button className="flex-1" onClick={() => { setNfcStatus('idle'); onStartScan(); }}>Retry</Button>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
