import React, { useRef, useEffect, useState } from 'react';
import { 
  Phone, PhoneOff, Mic, MicOff, Video, VideoOff, 
  Monitor, MonitorOff, UserPlus, PhoneForwarded, 
  Circle, Pause, Play, MoreVertical, Maximize2, Minimize2,
  X, Volume2, VolumeX
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
    activeCall,
    callStatus,
    isMuted,
    isVideoEnabled,
    isScreenSharing,
    isRecording,
    formattedDuration,
    remoteStreams,
    participants,
    localStream,
    endCall,
    toggleMute,
    toggleVideo,
    toggleScreenShare,
    toggleHold,
    toggleRecording,
    transferCall,
    addParticipant,
    callableContacts,
    isInCall
  } = useCall();
  
  const localVideoRef = useRef(null);
  const remoteVideoRef = useRef(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showTransfer, setShowTransfer] = useState(false);
  const [showAddParticipant, setShowAddParticipant] = useState(false);
  const [showPip, setShowPip] = useState(true);
  
  // Attach local stream to video element
  useEffect(() => {
    if (localVideoRef.current && localStream) {
      localVideoRef.current.srcObject = localStream;
    }
  }, [localStream, isVideoEnabled]);
  
  // Attach remote stream to video element
  useEffect(() => {
    if (remoteVideoRef.current) {
      const streams = Object.values(remoteStreams);
      if (streams.length > 0) {
        remoteVideoRef.current.srcObject = streams[0];
      }
    }
  }, [remoteStreams]);
  
  // Toggle fullscreen
  const handleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };
  
  if (!isInCall) return null;
  
  const remoteParticipant = activeCall?.caller_name || activeCall?.target_user_id || 'Unknown';
  const isOnHold = callStatus === 'on_hold';
  const isConnecting = callStatus === 'connecting' || callStatus === 'ringing';
  
  return (
    <div 
      className="fixed inset-0 z-50 bg-slate-900 flex flex-col"
      data-testid="call-interface"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 bg-slate-900/80 backdrop-blur-sm border-b border-slate-700">
        <div className="flex items-center gap-4">
          <div className="h-10 w-10 rounded-full bg-primary/20 flex items-center justify-center">
            <Phone size={20} className="text-primary" />
          </div>
          <div>
            <h2 className="text-white font-semibold">{remoteParticipant}</h2>
            <div className="flex items-center gap-2">
              <Badge variant={callStatus === 'connected' ? 'default' : 'secondary'} className="text-xs">
                {isConnecting ? 'Connecting...' : isOnHold ? 'On Hold' : callStatus}
              </Badge>
              {callStatus === 'connected' && (
                <span className="text-sm text-slate-400">{formattedDuration}</span>
              )}
              {isRecording && (
                <Badge variant="destructive" className="text-xs animate-pulse">
                  <Circle size={8} className="mr-1 fill-current" /> REC
                </Badge>
              )}
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="text-slate-400 hover:text-white"
            onClick={handleFullscreen}
          >
            {isFullscreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
          </Button>
        </div>
      </div>
      
      {/* Video Area */}
      <div className="flex-1 relative bg-slate-800 flex items-center justify-center overflow-hidden">
        {/* Remote Video (Main) */}
        {Object.keys(remoteStreams).length > 0 ? (
          <video
            ref={remoteVideoRef}
            autoPlay
            playsInline
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="flex flex-col items-center justify-center">
            <div className="h-32 w-32 rounded-full bg-slate-700 flex items-center justify-center mb-4">
              <span className="text-5xl text-white font-bold">
                {remoteParticipant.charAt(0).toUpperCase()}
              </span>
            </div>
            <p className="text-white text-xl font-medium">{remoteParticipant}</p>
            {isConnecting && (
              <p className="text-slate-400 mt-2 animate-pulse">
                {callStatus === 'ringing' ? 'Ringing...' : 'Connecting...'}
              </p>
            )}
            {isOnHold && (
              <p className="text-amber-400 mt-2">Call on hold</p>
            )}
          </div>
        )}
        
        {/* Local Video (PiP) */}
        {isVideoEnabled && showPip && (
          <div className="absolute bottom-4 right-4 w-48 h-36 rounded-lg overflow-hidden border-2 border-slate-600 shadow-lg">
            <video
              ref={localVideoRef}
              autoPlay
              playsInline
              muted
              className="w-full h-full object-cover mirror"
            />
            <Button
              variant="ghost"
              size="sm"
              className="absolute top-1 right-1 h-6 w-6 p-0 bg-black/50 hover:bg-black/70 text-white"
              onClick={() => setShowPip(false)}
            >
              <X size={12} />
            </Button>
          </div>
        )}
        
        {/* Screen Share Indicator */}
        {isScreenSharing && (
          <div className="absolute top-4 left-4 bg-green-600 text-white px-3 py-1.5 rounded-lg text-sm flex items-center gap-2">
            <Monitor size={14} /> Sharing screen
          </div>
        )}
        
        {/* Participants count for conference */}
        {participants.length > 2 && (
          <div className="absolute top-4 right-4 bg-slate-800/90 text-white px-3 py-1.5 rounded-lg text-sm">
            {participants.length} participants
          </div>
        )}
      </div>
      
      {/* Controls */}
      <div className="px-6 py-6 bg-slate-900 border-t border-slate-700">
        <div className="flex items-center justify-center gap-3 max-w-2xl mx-auto">
          {/* Mute */}
          <Button
            variant={isMuted ? 'destructive' : 'secondary'}
            size="lg"
            className="h-14 w-14 rounded-full"
            onClick={toggleMute}
            data-testid="call-mute-btn"
          >
            {isMuted ? <MicOff size={24} /> : <Mic size={24} />}
          </Button>
          
          {/* Video */}
          <Button
            variant={isVideoEnabled ? 'secondary' : 'outline'}
            size="lg"
            className="h-14 w-14 rounded-full"
            onClick={toggleVideo}
            data-testid="call-video-btn"
          >
            {isVideoEnabled ? <Video size={24} /> : <VideoOff size={24} />}
          </Button>
          
          {/* Screen Share */}
          <Button
            variant={isScreenSharing ? 'default' : 'outline'}
            size="lg"
            className="h-14 w-14 rounded-full"
            onClick={toggleScreenShare}
            data-testid="call-screenshare-btn"
          >
            {isScreenSharing ? <MonitorOff size={24} /> : <Monitor size={24} />}
          </Button>
          
          {/* Hold */}
          <Button
            variant={isOnHold ? 'default' : 'outline'}
            size="lg"
            className="h-14 w-14 rounded-full"
            onClick={toggleHold}
            data-testid="call-hold-btn"
          >
            {isOnHold ? <Play size={24} /> : <Pause size={24} />}
          </Button>
          
          {/* Record */}
          <Button
            variant={isRecording ? 'destructive' : 'outline'}
            size="lg"
            className="h-14 w-14 rounded-full"
            onClick={toggleRecording}
            data-testid="call-record-btn"
          >
            <Circle size={24} className={isRecording ? 'fill-current' : ''} />
          </Button>
          
          {/* More Options */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="lg" className="h-14 w-14 rounded-full">
                <MoreVertical size={24} />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="center" className="w-48">
              <DropdownMenuItem onClick={() => setShowAddParticipant(true)}>
                <UserPlus size={16} className="mr-2" /> Add Participant
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setShowTransfer(true)}>
                <PhoneForwarded size={16} className="mr-2" /> Transfer Call
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setShowPip(!showPip)}>
                {showPip ? 'Hide' : 'Show'} Self View
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          
          {/* End Call */}
          <Button
            variant="destructive"
            size="lg"
            className="h-14 w-14 rounded-full ml-4"
            onClick={endCall}
            data-testid="call-end-btn"
          >
            <PhoneOff size={24} />
          </Button>
        </div>
      </div>
      
      {/* Transfer Dialog */}
      <Dialog open={showTransfer} onOpenChange={setShowTransfer}>
        <DialogContent className="max-w-sm">
          <h3 className="font-semibold mb-4">Transfer Call To</h3>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {callableContacts.filter(c => !participants.includes(c.user_id)).map(contact => (
              <button
                key={contact.user_id}
                className="w-full flex items-center gap-3 p-3 rounded-lg border border-border hover:bg-muted text-left"
                onClick={() => {
                  transferCall(contact.user_id);
                  setShowTransfer(false);
                }}
              >
                <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                  {contact.name?.charAt(0) || contact.extension}
                </div>
                <div>
                  <p className="font-medium text-sm">{contact.name || contact.display_name}</p>
                  <p className="text-xs text-muted-foreground">Ext. {contact.extension}</p>
                </div>
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
              <button
                key={contact.user_id}
                className="w-full flex items-center gap-3 p-3 rounded-lg border border-border hover:bg-muted text-left"
                onClick={() => {
                  addParticipant(contact.user_id);
                  setShowAddParticipant(false);
                }}
              >
                <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                  {contact.name?.charAt(0) || contact.extension}
                </div>
                <div>
                  <p className="font-medium text-sm">{contact.name || contact.display_name}</p>
                  <p className="text-xs text-muted-foreground">Ext. {contact.extension}</p>
                </div>
              </button>
            ))}
          </div>
        </DialogContent>
      </Dialog>
      
      <style jsx>{`
        .mirror {
          transform: scaleX(-1);
        }
      `}</style>
    </div>
  );
}
