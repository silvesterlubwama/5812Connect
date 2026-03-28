import React, { useState } from 'react';
import { Phone, Video, X, Search, Clock, User } from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { useCall } from '../context/CallContext';
import { Badge } from './ui/badge';

export default function Dialer({ open, onClose }) {
  const { initiateCall, callableContacts, myExtension, sipRegistered } = useCall();
  const [dialNumber, setDialNumber] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [calling, setCalling] = useState(false);

  const handleDial = async (callType = 'audio') => {
    if (!dialNumber.trim()) return;
    setCalling(true);
    try {
      // Check if it's an extension or a contact
      const contact = callableContacts.find(c => c.extension === dialNumber);
      if (contact) {
        await initiateCall(contact.user_id, callType);
      } else {
        // Treat as external number - would need PBX
        // For now, just show error
        // toast.error('External calls require PBX configuration');
      }
      onClose();
    } catch (err) {
      console.error('Call failed:', err);
    } finally {
      setCalling(false);
    }
  };

  const handleCallContact = async (contact, callType = 'audio') => {
    setCalling(true);
    try {
      await initiateCall(contact.user_id, callType);
      onClose();
    } catch (err) {
      console.error('Call failed:', err);
    } finally {
      setCalling(false);
    }
  };

  const handleKeypadPress = (digit) => {
    setDialNumber(prev => prev + digit);
  };

  const handleBackspace = () => {
    setDialNumber(prev => prev.slice(0, -1));
  };

  const filteredContacts = callableContacts.filter(c => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      (c.name || '').toLowerCase().includes(term) ||
      (c.display_name || '').toLowerCase().includes(term) ||
      c.extension.includes(term)
    );
  });

  const statusColors = {
    available: 'bg-green-500',
    busy: 'bg-amber-500',
    dnd: 'bg-red-500',
    offline: 'bg-slate-400',
    on_call: 'bg-blue-500',
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md p-0 overflow-hidden" data-testid="dialer-modal">
        <DialogHeader className="p-4 pb-0">
          <DialogTitle className="flex items-center gap-2">
            <Phone size={18} /> Make a Call
            <div className="ml-auto flex items-center gap-2">
              {sipRegistered && <Badge className="text-[10px] bg-green-100 text-green-700 gap-1"><span className="w-1.5 h-1.5 rounded-full bg-green-500" /> SIP</Badge>}
              {myExtension && <Badge variant="outline" className="text-xs">Ext: {myExtension.extension}</Badge>}
            </div>
          </DialogTitle>
        </DialogHeader>

        <Tabs defaultValue="contacts" className="p-4 pt-2">
          <TabsList className="w-full">
            <TabsTrigger value="contacts" className="flex-1">Contacts</TabsTrigger>
            <TabsTrigger value="keypad" className="flex-1">Keypad</TabsTrigger>
          </TabsList>

          {/* Contacts Tab */}
          <TabsContent value="contacts" className="mt-4">
            <div className="relative mb-3">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search contacts..."
                className="pl-9"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
              />
            </div>

            <div className="max-h-64 overflow-y-auto space-y-1">
              {filteredContacts.length === 0 ? (
                <div className="py-8 text-center text-muted-foreground text-sm">
                  <User size={32} className="mx-auto mb-2 opacity-30" />
                  No contacts with extensions
                </div>
              ) : (
                filteredContacts.map(contact => (
                  <div
                    key={contact.user_id}
                    className="flex items-center gap-3 p-2 rounded-lg hover:bg-muted transition-colors"
                    data-testid={`contact-${contact.extension}`}
                  >
                    <div className="relative">
                      <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center text-sm font-medium">
                        {(contact.name || contact.display_name || '?').charAt(0).toUpperCase()}
                      </div>
                      <div className={`absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-background ${statusColors[contact.status] || statusColors.offline}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{contact.name || contact.display_name}</p>
                      <p className="text-xs text-muted-foreground">Ext. {contact.extension}</p>
                    </div>
                    <div className="flex gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-8 w-8 p-0 rounded-full bg-green-100 hover:bg-green-200 text-green-600"
                        onClick={() => handleCallContact(contact, 'audio')}
                        disabled={calling || contact.status === 'dnd'}
                        data-testid={`call-audio-${contact.extension}`}
                      >
                        <Phone size={14} />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-8 w-8 p-0 rounded-full bg-blue-100 hover:bg-blue-200 text-blue-600"
                        onClick={() => handleCallContact(contact, 'video')}
                        disabled={calling || contact.status === 'dnd'}
                        data-testid={`call-video-${contact.extension}`}
                      >
                        <Video size={14} />
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </TabsContent>

          {/* Keypad Tab */}
          <TabsContent value="keypad" className="mt-4">
            {/* Display */}
            <div className="relative mb-4">
              <Input
                type="text"
                value={dialNumber}
                onChange={e => setDialNumber(e.target.value.replace(/[^\d*#]/g, ''))}
                placeholder="Enter extension or number"
                className="text-center text-2xl h-14 font-mono"
                data-testid="dial-input"
              />
              {dialNumber && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="absolute right-2 top-1/2 -translate-y-1/2 h-8 w-8 p-0"
                  onClick={handleBackspace}
                >
                  <X size={16} />
                </Button>
              )}
            </div>

            {/* Keypad Grid */}
            <div className="grid grid-cols-3 gap-2 mb-4">
              {['1', '2', '3', '4', '5', '6', '7', '8', '9', '*', '0', '#'].map(digit => (
                <Button
                  key={digit}
                  variant="outline"
                  className="h-14 text-xl font-medium"
                  onClick={() => handleKeypadPress(digit)}
                >
                  {digit}
                  {digit !== '*' && digit !== '#' && digit !== '0' && (
                    <span className="text-[10px] text-muted-foreground ml-1 uppercase">
                      {['', 'ABC', 'DEF', 'GHI', 'JKL', 'MNO', 'PQRS', 'TUV', 'WXYZ'][parseInt(digit)] || ''}
                    </span>
                  )}
                </Button>
              ))}
            </div>

            {/* Call Buttons */}
            <div className="flex gap-3">
              <Button
                className="flex-1 h-12 bg-green-500 hover:bg-green-600 text-white gap-2"
                onClick={() => handleDial('audio')}
                disabled={!dialNumber || calling}
                data-testid="dial-audio-btn"
              >
                <Phone size={18} /> Audio Call
              </Button>
              <Button
                className="flex-1 h-12 bg-blue-500 hover:bg-blue-600 text-white gap-2"
                onClick={() => handleDial('video')}
                disabled={!dialNumber || calling}
                data-testid="dial-video-btn"
              >
                <Video size={18} /> Video Call
              </Button>
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
