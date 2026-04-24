import React from 'react';
import { ScanLine, Smartphone, Fingerprint } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';

export function ScanDialog({ open, onOpenChange, scanMode, setScanMode, scanForm, setScanForm, members, guestRequests, saving, onScan }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Scan In/Out</DialogTitle></DialogHeader>
        <form onSubmit={onScan} className="space-y-4 mt-2">
          <div className="space-y-2">
            <Label>Scan Type</Label>
            <Select value={scanMode} onValueChange={v => { setScanMode(v); setScanForm({ member_id: '', action: scanForm.action, guest_request_id: '', guest_name: '' }); }}>
              <SelectTrigger data-testid="scan-type-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="member">Resident / Staff</SelectItem>
                <SelectItem value="guest">Approved Guest</SelectItem>
                <SelectItem value="nfc">NFC Tag</SelectItem>
                <SelectItem value="biometric">Biometric</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {scanMode === 'member' ? (
            <div className="space-y-2">
              <Label>Member</Label>
              <Select value={scanForm.member_id} onValueChange={v => setScanForm({ ...scanForm, member_id: v })}>
                <SelectTrigger data-testid="scan-member-select"><SelectValue placeholder="Select person" /></SelectTrigger>
                <SelectContent>{members.map(m => <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          ) : scanMode === 'guest' ? (
            <div className="space-y-2">
              <Label>Approved Guest Request</Label>
              <Select value={scanForm.guest_request_id} onValueChange={v => {
                const gr = guestRequests.find(g => g.id === v);
                setScanForm({ ...scanForm, guest_request_id: v, guest_name: gr?.guest_name || '' });
              }}>
                <SelectTrigger data-testid="scan-guest-select"><SelectValue placeholder="Select approved guest" /></SelectTrigger>
                <SelectContent>{guestRequests.filter(g => g.status === 'approved').map(g => <SelectItem key={g.id} value={g.id}>{g.guest_name} - {g.visit_date}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          ) : scanMode === 'nfc' ? (
            <div className="space-y-3">
              <div className="p-6 rounded-xl border-2 border-dashed border-primary/30 bg-primary/5 text-center">
                <Smartphone size={40} className="mx-auto mb-2 text-primary opacity-60" />
                <p className="text-sm font-medium">Place NFC tag on device</p>
                <p className="text-xs text-muted-foreground mt-1">Or enter serial number manually</p>
              </div>
              <div className="space-y-2">
                <Label>NFC Serial Number</Label>
                <Input placeholder="e.g. 04:A2:B3:C4:D5" value={scanForm.member_id} onChange={e => setScanForm({ ...scanForm, member_id: e.target.value })} data-testid="nfc-serial-input" />
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="p-6 rounded-xl border-2 border-dashed border-primary/30 bg-primary/5 text-center">
                <Fingerprint size={40} className="mx-auto mb-2 text-primary opacity-60" />
                <p className="text-sm font-medium">Touch the fingerprint sensor</p>
                <p className="text-xs text-muted-foreground mt-1">Or enter credential ID manually</p>
              </div>
              <div className="space-y-2">
                <Label>Credential ID</Label>
                <Input placeholder="Credential identifier" value={scanForm.member_id} onChange={e => setScanForm({ ...scanForm, member_id: e.target.value })} data-testid="biometric-credential-input" />
              </div>
            </div>
          )}
          <div className="space-y-2">
            <Label>Action</Label>
            <Select value={scanForm.action} onValueChange={v => setScanForm({ ...scanForm, action: v })}>
              <SelectTrigger data-testid="scan-action-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="in">Scan IN</SelectItem>
                <SelectItem value="out">Scan OUT</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex gap-3">
            <Button type="button" variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" className="flex-1" disabled={saving || (scanMode === 'member' ? !scanForm.member_id : scanMode === 'guest' ? !scanForm.guest_request_id : !scanForm.member_id)} data-testid="execute-scan-btn">
              {saving ? 'Processing...' : scanForm.action === 'in' ? 'Scan IN' : 'Scan OUT'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
