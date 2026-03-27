import React from 'react';
import { Phone, PhoneOff, Video } from 'lucide-react';
import { Button } from './ui/button';
import { useCall } from '../context/CallContext';
import { Dialog, DialogContent } from './ui/dialog';

export default function IncomingCallModal() {
  const { incomingCall, answerCall, rejectCall, hasIncomingCall } = useCall();
  
  if (!hasIncomingCall || !incomingCall) return null;
  
  const isVideoCall = incomingCall.call_type === 'video';
  const callerName = incomingCall.caller_name || 'Unknown Caller';
  const callerExt = incomingCall.caller_extension;
  
  return (
    <Dialog open={true} onOpenChange={() => {}}>
      <DialogContent 
        className="max-w-sm bg-slate-900 border-slate-700 text-white p-0 overflow-hidden"
        data-testid="incoming-call-modal"
      >
        <div className="relative">
          {/* Animated background */}
          <div className="absolute inset-0 bg-gradient-to-b from-primary/30 to-transparent animate-pulse" />
          
          <div className="relative p-8 flex flex-col items-center">
            {/* Caller Avatar */}
            <div className="relative mb-6">
              <div className="h-24 w-24 rounded-full bg-primary/20 flex items-center justify-center ring-4 ring-primary/30 animate-pulse">
                <span className="text-4xl font-bold text-primary">
                  {callerName.charAt(0).toUpperCase()}
                </span>
              </div>
              {isVideoCall && (
                <div className="absolute -bottom-1 -right-1 h-8 w-8 rounded-full bg-blue-500 flex items-center justify-center">
                  <Video size={16} className="text-white" />
                </div>
              )}
            </div>
            
            {/* Caller Info */}
            <h2 className="text-xl font-semibold text-white mb-1">{callerName}</h2>
            {callerExt && (
              <p className="text-slate-400 text-sm mb-2">Extension {callerExt}</p>
            )}
            <p className="text-primary text-sm animate-pulse mb-8">
              Incoming {isVideoCall ? 'video' : 'audio'} call...
            </p>
            
            {/* Action Buttons */}
            <div className="flex items-center gap-6">
              {/* Reject */}
              <div className="flex flex-col items-center gap-2">
                <Button
                  variant="destructive"
                  size="lg"
                  className="h-16 w-16 rounded-full shadow-lg shadow-red-500/30"
                  onClick={() => rejectCall()}
                  data-testid="reject-call-btn"
                >
                  <PhoneOff size={28} />
                </Button>
                <span className="text-xs text-slate-400">Decline</span>
              </div>
              
              {/* Answer Audio */}
              <div className="flex flex-col items-center gap-2">
                <Button
                  size="lg"
                  className="h-16 w-16 rounded-full bg-green-500 hover:bg-green-600 shadow-lg shadow-green-500/30"
                  onClick={() => answerCall(false)}
                  data-testid="answer-audio-btn"
                >
                  <Phone size={28} />
                </Button>
                <span className="text-xs text-slate-400">Audio</span>
              </div>
              
              {/* Answer Video (if video call) */}
              {isVideoCall && (
                <div className="flex flex-col items-center gap-2">
                  <Button
                    size="lg"
                    className="h-16 w-16 rounded-full bg-blue-500 hover:bg-blue-600 shadow-lg shadow-blue-500/30"
                    onClick={() => answerCall(true)}
                    data-testid="answer-video-btn"
                  >
                    <Video size={28} />
                  </Button>
                  <span className="text-xs text-slate-400">Video</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
