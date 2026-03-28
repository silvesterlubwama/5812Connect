import React, { useRef, useEffect, useState } from 'react';
import { 
  Phone, PhoneOff, Mic, MicOff, Video, VideoOff, 
  Monitor, MonitorOff, UserPlus, PhoneForwarded, 
  Circle, Pause, Play, MoreVertical, Maximize2, Minimize2,
  X
} from 'lucide-react';
import { Button } from './ui/button';
import { useCall } from '../context/CallContext';
import { Dialog, DialogContent } from './ui/dialog';
import { 
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, 
  DropdownMenuTrigger, DropdownMenuSeparator 
} from './ui/dropdown-menu';
import { Badge } from './ui/badge';

export default function CallInterface() {
  const {
    activeCall, callStatus, isMuted, isVideoEnabled, isScreenSharing,
    isRecording, formattedDuration, remoteStreams, participants, localStream,
    endCall, toggleMute, toggleVideo, toggleScreenShare, toggleHold,
    toggleRecording, transferCall, addParticipant, callableContacts, isInCall, sipRegistered
  } = useCall();
  
  const localVideoRef = useRef(null);
  const remoteVideoRef = useRef(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showTransfer, setShowTransfer] = useState(false);
  const [showAddParticipant, setShowAddParticipant] = useState(false);
  const [showPip, setShowPip] = useState(true);
  
  useEffect(() => {
    if (localVideoRef.current && localStream) {
      localVideoRef.current.srcObject = localStream;
    }
  }, [localStream, isVideoEnabled]);
  
  useEffect(() => {
    if (remoteVideoRef.current) {
      const streams = Object.values(remoteStreams);
      if (streams.length > 0) {
        remoteVideoRef.current.srcObject = streams[0];
        remoteVideoRef.current.play().catch(() => {});
      }
    }
  }, [remoteStreams]);
  
  const handleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };
  
  if (!isInCall) return null;
  
  const remoteParticipant = activeCall?.caller_name || activeCall?.target_name || activeCall?.target_user_id || 'Unknown';
  const isOnHold = callStatus === 'on_hold';
  const isConnecting = callStatus === 'connecting' || callStatus === 'ringing';
  const isSipCall = activeCall?.call_type === 'sip';
  
  return (
    <div className="fixed inset-0 z-50 bg-[#0f1729] flex flex-col" data-testid="call-interface">
      {/* Header */}
      <div className="flex items-center justify-between px-4 sm:px-6 py-3 sm:py-4 bg-[#0f1729]/80 backdrop-blur-sm border-b border-white/10 shrink-0">
        <div className="flex items-center gap-3 sm:gap-4">
          <div className="h-10 w-10 rounded-full bg-white/10 flex items-center justify-center">
            <Phone size={20} className="text-green-400" />
          </div>
          <div>
            <h2 className="text-white font-semibold text-sm sm:text-base">{remoteParticipant}</h2>
            <div className="flex items-center gap-2">
              <Badge className={`text-[10px] ${callStatus === 'connected' ? 'bg-green-600' : 'bg-amber-600'}`}>
                {isConnecting ? 'Connecting...' : isOnHold ? 'On Hold' : callStatus}
              </Badge>
              {isSipCall && <Badge className="text-[10px] bg-blue-600">SIP</Badge>}
              {callStatus === 'connected' && <span className="text-xs text-white/60">{formattedDuration}</span>}
              {isRecording && <Badge className="text-[10px] bg-red-600 animate-pulse"><Circle size={6} className="mr-1 fill-current" /> REC</Badge>}
            </div>
          </div>
        </div>
        <Button variant="ghost" size="sm" className="text-white/60 hover:text-white hover:bg-white/10" onClick={handleFullscreen}>
          {isFullscreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
        </Button>
      </div>
      
      {/* Video/Avatar Area */}
      <div className="flex-1 relative bg-[#131b2e] flex items-center justify-center overflow-hidden">
        <video ref={remoteVideoRef} autoPlay playsInline className={`w-full h-full object-cover ${Object.keys(remoteStreams).length === 0 ? 'hidden' : ''}`} />
        {Object.keys(remoteStreams).length === 0 && (
          <div className="flex flex-col items-center justify-center">
            <div className="h-24 w-24 sm:h-32 sm:w-32 rounded-full bg-white/10 flex items-center justify-center mb-4">
              <span className="text-4xl sm:text-5xl text-white font-bold">{remoteParticipant.charAt(0).toUpperCase()}</span>
            </div>
            <p className="text-white text-lg sm:text-xl font-medium">{remoteParticipant}</p>
            {isConnecting && <p className="text-white/50 mt-2 animate-pulse">{callStatus === 'ringing' ? 'Ringing...' : 'Connecting...'}</p>}
            {isOnHold && <p className="text-amber-400 mt-2">Call on hold</p>}
          </div>
        )}
        
        {/* Local Video PiP */}
        {isVideoEnabled && showPip && (
          <div className="absolute bottom-4 right-4 w-32 h-24 sm:w-48 sm:h-36 rounded-lg overflow-hidden border-2 border-white/20 shadow-lg">
            <video ref={localVideoRef} autoPlay playsInline muted className="w-full h-full object-cover" style={{ transform: 'scaleX(-1)' }} />
            <Button variant="ghost" size="sm" className="absolute top-1 right-1 h-5 w-5 p-0 bg-black/50 hover:bg-black/70 text-white" onClick={() => setShowPip(false)}>
              <X size={10} />
            </Button>
          </div>
        )}
        
        {isScreenSharing && (
          <div className="absolute top-3 left-3 bg-green-600 text-white px-2 py-1 rounded-lg text-xs flex items-center gap-1.5"><Monitor size={12} /> Sharing</div>
        )}
        {participants.length > 2 && (
          <div className="absolute top-3 right-3 bg-white/10 text-white px-2 py-1 rounded-lg text-xs">{participants.length} participants</div>
        )}
      </div>
      
      {/* Controls - responsive, always visible */}
      <div className="px-4 py-4 sm:py-6 bg-[#0a0f1c] border-t border-white/10 shrink-0 safe-bottom">
        {/* Primary controls row - always visible */}
        <div className="flex items-center justify-center gap-2 sm:gap-3 max-w-lg mx-auto">
          {/* Mute - ALWAYS visible */}
          <button onClick={toggleMute} data-testid="call-mute-btn"
            className={`h-12 w-12 sm:h-14 sm:w-14 rounded-full flex items-center justify-center transition-colors ${isMuted ? 'bg-red-600 text-white' : 'bg-white/15 text-white hover:bg-white/25'}`}>
            {isMuted ? <MicOff size={20} /> : <Mic size={20} />}
          </button>
          
          {/* Video */}
          <button onClick={toggleVideo} data-testid="call-video-btn"
            className={`h-12 w-12 sm:h-14 sm:w-14 rounded-full flex items-center justify-center transition-colors ${isVideoEnabled ? 'bg-blue-600 text-white' : 'bg-white/15 text-white hover:bg-white/25'}`}>
            {isVideoEnabled ? <Video size={20} /> : <VideoOff size={20} />}
          </button>
          
          {/* Hold */}
          <button onClick={toggleHold} data-testid="call-hold-btn"
            className={`h-12 w-12 sm:h-14 sm:w-14 rounded-full flex items-center justify-center transition-colors ${isOnHold ? 'bg-amber-600 text-white' : 'bg-white/15 text-white hover:bg-white/25'}`}>
            {isOnHold ? <Play size={20} /> : <Pause size={20} />}
          </button>
          
          {/* Screen Share - hidden on mobile */}
          <button onClick={toggleScreenShare} data-testid="call-screenshare-btn"
            className={`hidden sm:flex h-12 w-12 sm:h-14 sm:w-14 rounded-full items-center justify-center transition-colors ${isScreenSharing ? 'bg-green-600 text-white' : 'bg-white/15 text-white hover:bg-white/25'}`}>
            {isScreenSharing ? <MonitorOff size={20} /> : <Monitor size={20} />}
          </button>
          
          {/* Record - hidden on mobile */}
          <button onClick={toggleRecording} data-testid="call-record-btn"
            className={`hidden sm:flex h-12 w-12 sm:h-14 sm:w-14 rounded-full items-center justify-center transition-colors ${isRecording ? 'bg-red-600 text-white' : 'bg-white/15 text-white hover:bg-white/25'}`}>
            <Circle size={20} className={isRecording ? 'fill-current' : ''} />
          </button>
          
          {/* More (Transfer/Add) */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="h-12 w-12 sm:h-14 sm:w-14 rounded-full flex items-center justify-center bg-white/15 text-white hover:bg-white/25 transition-colors">
                <MoreVertical size={20} />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="center" className="w-48">
              <DropdownMenuItem onClick={() => setShowAddParticipant(true)}><UserPlus size={16} className="mr-2" /> Add Participant</DropdownMenuItem>
              <DropdownMenuItem onClick={() => setShowTransfer(true)}><PhoneForwarded size={16} className="mr-2" /> Transfer Call</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="sm:hidden" onClick={toggleScreenShare}><Monitor size={16} className="mr-2" /> {isScreenSharing ? 'Stop Share' : 'Screen Share'}</DropdownMenuItem>
              <DropdownMenuItem className="sm:hidden" onClick={toggleRecording}><Circle size={16} className="mr-2" /> {isRecording ? 'Stop Record' : 'Record'}</DropdownMenuItem>
              <DropdownMenuItem onClick={() => setShowPip(!showPip)}>{showPip ? 'Hide' : 'Show'} Self View</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          
          {/* End Call - ALWAYS visible, prominent */}
          <button onClick={endCall} data-testid="call-end-btn"
            className="h-12 w-12 sm:h-14 sm:w-14 rounded-full flex items-center justify-center bg-red-600 hover:bg-red-700 text-white transition-colors ml-2 sm:ml-4 shadow-lg shadow-red-600/30">
            <PhoneOff size={22} />
          </button>
        </div>
      </div>
      
      {/* Transfer Dialog */}
      <Dialog open={showTransfer} onOpenChange={setShowTransfer}>
        <DialogContent className="max-w-sm">
          <h3 className="font-semibold mb-4">Transfer Call To</h3>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {callableContacts.filter(c => !participants.includes(c.user_id)).map(contact => (
              <button key={contact.user_id} className="w-full flex items-center gap-3 p-3 rounded-lg border border-border hover:bg-muted text-left"
                onClick={() => { transferCall(contact.user_id); setShowTransfer(false); }}>
                <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">{contact.name?.charAt(0) || '?'}</div>
                <div><p className="font-medium text-sm">{contact.name || contact.display_name}</p><p className="text-xs text-muted-foreground">{contact.extension ? `Ext. ${contact.extension}` : 'WebRTC'}</p></div>
              </button>
            ))}
          </div>
        </DialogContent>
      </Dialog>
      
      {/* Add Participant Dialog */}
      <Dialog open={showAddParticipant} onOpenChange={setShowAddParticipant}>
        <DialogContent className="max-w-sm">
          <h3 className="font-semibold mb-4">Add to Conference</h3>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {callableContacts.filter(c => !participants.includes(c.user_id)).map(contact => (
              <button key={contact.user_id} className="w-full flex items-center gap-3 p-3 rounded-lg border border-border hover:bg-muted text-left"
                onClick={() => { addParticipant(contact.user_id); setShowAddParticipant(false); }}>
                <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">{contact.name?.charAt(0) || '?'}</div>
                <div><p className="font-medium text-sm">{contact.name || contact.display_name}</p><p className="text-xs text-muted-foreground">{contact.extension ? `Ext. ${contact.extension}` : 'WebRTC'}</p></div>
              </button>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
