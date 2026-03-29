import React, { useState } from 'react';
import { Phone, Video, X, Search, Users, PhoneCall } from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Badge } from './ui/badge';
import { useCall } from '../context/CallContext';
import { toast } from 'sonner';

export default function Dialer({ open, onClose }) {
  const { initiateCall, callableContacts, isInCall } = useCall();
  const [searchTerm, setSearchTerm] = useState('');
  const [calling, setCalling] = useState(false);

  const filteredContacts = callableContacts.filter(c => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (c.name || '').toLowerCase().includes(term) ||
      (c.display_name || '').toLowerCase().includes(term) ||
      (c.email || '').toLowerCase().includes(term) ||
      (c.role || '').toLowerCase().includes(term);
  });

  const handleCall = async (userId, callType) => {
    if (isInCall) { toast.error('Already on a call'); return; }
    setCalling(true);
    try {
      await initiateCall(userId, callType);
      onClose();
    } catch (err) { toast.error('Call failed'); }
    finally { setCalling(false); }
  };

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="max-w-md max-h-[80vh] p-0 gap-0 overflow-hidden">
        <DialogHeader className="p-4 pb-0">
          <DialogTitle className="flex items-center gap-2">
            <PhoneCall size={18} /> Call a Contact
            <Badge variant="outline" className="ml-auto text-xs">{callableContacts.length} contacts</Badge>
          </DialogTitle>
        </DialogHeader>

        {/* Search */}
        <div className="px-4 py-3">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input className="pl-9 h-9" placeholder="Search contacts..." value={searchTerm} onChange={e => setSearchTerm(e.target.value)} data-testid="dialer-search" />
          </div>
        </div>

        {/* Contacts */}
        <div className="overflow-y-auto max-h-96 px-2 pb-4">
          {filteredContacts.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Users size={28} className="mx-auto mb-2 opacity-30" />
              <p className="text-sm">{searchTerm ? 'No contacts found' : 'No staff contacts available'}</p>
            </div>
          ) : (
            <div className="space-y-1">
              {filteredContacts.map(contact => (
                <div key={contact.user_id} className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-secondary/60 transition-colors group" data-testid={`contact-${contact.user_id}`}>
                  <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center text-sm font-semibold text-primary shrink-0">
                    {(contact.name || contact.display_name || '?').charAt(0).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{contact.name || contact.display_name}</p>
                    <p className="text-xs text-muted-foreground truncate">{contact.role || 'Staff'} {contact.email ? `- ${contact.email}` : ''}</p>
                  </div>
                  {/* Call buttons - visible on hover */}
                  <div className="flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                    <Button size="icon" variant="ghost" disabled={calling}
                      className="h-8 w-8 text-green-600 hover:bg-green-100 dark:hover:bg-green-950"
                      onClick={() => handleCall(contact.user_id, 'audio')}
                      data-testid={`call-audio-${contact.user_id}`}>
                      <Phone size={15} />
                    </Button>
                    <Button size="icon" variant="ghost" disabled={calling}
                      className="h-8 w-8 text-blue-600 hover:bg-blue-100 dark:hover:bg-blue-950"
                      onClick={() => handleCall(contact.user_id, 'video')}
                      data-testid={`call-video-${contact.user_id}`}>
                      <Video size={15} />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="p-3 border-t border-border text-center">
          <p className="text-[10px] text-muted-foreground">WebRTC calls - unlimited audio & video, screen sharing, group calls</p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
