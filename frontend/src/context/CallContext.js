import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from './AuthContext';
import { useWebSocket } from './WebSocketContext';
import { callingApi } from '../services/api';
import { toast } from 'sonner';

const CallContext = createContext(null);

export const useCall = () => {
  const ctx = useContext(CallContext);
  if (!ctx) throw new Error('useCall must be used within CallProvider');
  return ctx;
};

export const CallProvider = ({ children }) => {
  const { user } = useAuth();
  const { sendMessage, lastMessage, isConnected } = useWebSocket();
  
  // Call state
  const [activeCall, setActiveCall] = useState(null);
  const [incomingCall, setIncomingCall] = useState(null);
  const [callStatus, setCallStatus] = useState('idle'); // idle, ringing, connecting, connected, on_hold, ended
  const [isMuted, setIsMuted] = useState(false);
  const [isVideoEnabled, setIsVideoEnabled] = useState(false);
  const [isScreenSharing, setIsScreenSharing] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [callDuration, setCallDuration] = useState(0);
  const [remoteStreams, setRemoteStreams] = useState({});
  const [participants, setParticipants] = useState([]);
  
  // WebRTC refs
  const localStreamRef = useRef(null);
  const screenStreamRef = useRef(null);
  const peerConnectionsRef = useRef({});
  const durationIntervalRef = useRef(null);
  const iceServersRef = useRef([{ urls: 'stun:stun.l.google.com:19302' }]);
  
  // Extension info
  const [myExtension, setMyExtension] = useState(null);
  const [callableContacts, setCallableContacts] = useState([]);
  
  // Load user's extension and contacts
  useEffect(() => {
    if (user?.id) {
      callingApi.getUserExtension(user.id).then(res => {
        setMyExtension(res.data);
      }).catch(() => {});
      
      callingApi.getCallableContacts(user.id).then(res => {
        setCallableContacts(res.data || []);
      }).catch(() => {});
      
      callingApi.getIceServers().then(res => {
        if (res.data?.ice_servers) {
          iceServersRef.current = res.data.ice_servers;
        }
      }).catch(() => {});
    }
  }, [user?.id]);
  
  // Handle incoming WebSocket messages for calls
  useEffect(() => {
    if (!lastMessage) return;
    
    const { type, ...data } = lastMessage;
    
    switch (type) {
      case 'incoming_call':
        handleIncomingCall(data);
        break;
      case 'call_answered':
        handleCallAnswered(data);
        break;
      case 'ice_candidate':
        handleIceCandidate(data);
        break;
      case 'call_rejected':
        handleCallRejected(data);
        break;
      case 'call_ended':
        handleCallEnded(data);
        break;
      case 'call_hold_changed':
        if (data.is_held) {
          setCallStatus('on_hold');
        } else {
          setCallStatus('connected');
        }
        break;
      case 'call_mute_changed':
        // Update remote participant mute state
        break;
      case 'conference_invite':
        handleConferenceInvite(data);
        break;
      case 'conference_participant_added':
        setParticipants(prev => [...prev, data.new_participant_id]);
        break;
      case 'incoming_transfer':
        handleIncomingTransfer(data);
        break;
      case 'screen_share_started':
        toast.info('Remote user started screen sharing');
        break;
      case 'screen_share_stopped':
        toast.info('Remote user stopped screen sharing');
        break;
      default:
        break;
    }
  }, [lastMessage]);
  
  // Create peer connection
  const createPeerConnection = useCallback((targetUserId) => {
    const pc = new RTCPeerConnection({
      iceServers: iceServersRef.current
    });
    
    pc.onicecandidate = (event) => {
      if (event.candidate) {
        sendMessage({
          type: 'ice_candidate',
          call_id: activeCall?.call_id,
          candidate: event.candidate,
          target_user_id: targetUserId
        });
      }
    };
    
    pc.ontrack = (event) => {
      setRemoteStreams(prev => ({
        ...prev,
        [targetUserId]: event.streams[0]
      }));
    };
    
    pc.oniceconnectionstatechange = () => {
      if (pc.iceConnectionState === 'disconnected' || pc.iceConnectionState === 'failed') {
        // Handle disconnection
      }
    };
    
    // Add local tracks
    if (localStreamRef.current) {
      localStreamRef.current.getTracks().forEach(track => {
        pc.addTrack(track, localStreamRef.current);
      });
    }
    
    peerConnectionsRef.current[targetUserId] = pc;
    return pc;
  }, [activeCall, sendMessage]);
  
  // Get user media
  const getUserMedia = useCallback(async (video = false) => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: video ? { width: 1280, height: 720 } : false
      });
      localStreamRef.current = stream;
      setIsVideoEnabled(video);
      return stream;
    } catch (err) {
      toast.error('Could not access microphone/camera');
      throw err;
    }
  }, []);
  
  // Initiate a call
  const initiateCall = useCallback(async (targetUserId, callType = 'audio') => {
    if (!user?.id || !isConnected) {
      toast.error('Not connected');
      return;
    }
    
    try {
      // Get media
      const stream = await getUserMedia(callType === 'video');
      
      // Create call via API
      const res = await callingApi.initiateCall({
        to_user_id: targetUserId,
        call_type: callType,
        use_pbx: false
      }, user.id);
      
      const { call_id, ice_servers, call } = res.data;
      
      if (ice_servers) {
        iceServersRef.current = ice_servers;
      }
      
      setActiveCall({ ...call, call_id });
      setCallStatus('ringing');
      setParticipants([user.id, targetUserId]);
      
      // Create peer connection and offer
      const pc = createPeerConnection(targetUserId);
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      
      // Send offer via WebSocket
      sendMessage({
        type: 'call_offer',
        call_id,
        target_user_id: targetUserId,
        sdp: offer,
        call_type: callType,
        caller_name: user.name,
        caller_extension: myExtension?.extension
      });
      
      return call_id;
    } catch (err) {
      console.error('Failed to initiate call:', err);
      endCall();
      throw err;
    }
  }, [user, isConnected, createPeerConnection, getUserMedia, sendMessage, myExtension]);
  
  // Handle incoming call
  const handleIncomingCall = useCallback((data) => {
    if (activeCall) {
      // Already in a call, reject
      sendMessage({
        type: 'call_reject',
        call_id: data.call_id,
        caller_id: data.caller_id,
        reason: 'busy'
      });
      return;
    }
    
    setIncomingCall(data);
    // Play ringtone
    const ringtone = new Audio('/ringtone.mp3');
    ringtone.loop = true;
    ringtone.play().catch(() => {});
    
    // Store ringtone ref to stop it later
    setIncomingCall(prev => ({ ...data, ringtone }));
  }, [activeCall, sendMessage]);
  
  // Answer incoming call
  const answerCall = useCallback(async (withVideo = false) => {
    if (!incomingCall) return;
    
    try {
      // Stop ringtone
      if (incomingCall.ringtone) {
        incomingCall.ringtone.pause();
        incomingCall.ringtone.currentTime = 0;
      }
      
      // Get media
      const stream = await getUserMedia(withVideo);
      
      // Create peer connection
      const pc = createPeerConnection(incomingCall.caller_id);
      
      // Set remote description (offer)
      await pc.setRemoteDescription(new RTCSessionDescription(incomingCall.sdp));
      
      // Create answer
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      
      // Send answer
      sendMessage({
        type: 'call_answer',
        call_id: incomingCall.call_id,
        caller_id: incomingCall.caller_id,
        sdp: answer
      });
      
      setActiveCall({
        call_id: incomingCall.call_id,
        caller_id: incomingCall.caller_id,
        caller_name: incomingCall.caller_name,
        call_type: incomingCall.call_type
      });
      setCallStatus('connected');
      setParticipants([user.id, incomingCall.caller_id]);
      setIncomingCall(null);
      
      // Start duration timer
      startDurationTimer();
      
      // Update status in API
      callingApi.callAction(incomingCall.call_id, { action: 'answer' }, user.id).catch(() => {});
      
    } catch (err) {
      console.error('Failed to answer call:', err);
      rejectCall();
    }
  }, [incomingCall, user, createPeerConnection, getUserMedia, sendMessage]);
  
  // Reject incoming call
  const rejectCall = useCallback((reason = 'rejected') => {
    if (!incomingCall) return;
    
    // Stop ringtone
    if (incomingCall.ringtone) {
      incomingCall.ringtone.pause();
      incomingCall.ringtone.currentTime = 0;
    }
    
    sendMessage({
      type: 'call_reject',
      call_id: incomingCall.call_id,
      caller_id: incomingCall.caller_id,
      reason
    });
    
    callingApi.callAction(incomingCall.call_id, { action: 'reject' }, user?.id).catch(() => {});
    
    setIncomingCall(null);
  }, [incomingCall, sendMessage, user]);
  
  // Handle call answered (we initiated the call)
  const handleCallAnswered = useCallback(async (data) => {
    const pc = peerConnectionsRef.current[data.answerer_id];
    if (pc) {
      await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));
      setCallStatus('connected');
      startDurationTimer();
    }
  }, []);
  
  // Handle ICE candidate
  const handleIceCandidate = useCallback(async (data) => {
    const pc = peerConnectionsRef.current[data.from_user_id];
    if (pc && data.candidate) {
      try {
        await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
      } catch (err) {
        console.error('Failed to add ICE candidate:', err);
      }
    }
  }, []);
  
  // Handle call rejected
  const handleCallRejected = useCallback((data) => {
    toast.error(`Call ${data.reason === 'busy' ? 'rejected - user is busy' : 'rejected'}`);
    endCall();
  }, []);
  
  // Handle call ended
  const handleCallEnded = useCallback((data) => {
    toast.info('Call ended');
    endCall();
  }, []);
  
  // Handle conference invite
  const handleConferenceInvite = useCallback((data) => {
    // Similar to incoming call but for conference
    handleIncomingCall({
      ...data,
      is_conference: true
    });
  }, [handleIncomingCall]);
  
  // Handle transfer
  const handleIncomingTransfer = useCallback((data) => {
    handleIncomingCall({
      ...data,
      is_transfer: true
    });
  }, [handleIncomingCall]);
  
  // End call
  const endCall = useCallback(() => {
    // Stop all streams
    if (localStreamRef.current) {
      localStreamRef.current.getTracks().forEach(track => track.stop());
      localStreamRef.current = null;
    }
    if (screenStreamRef.current) {
      screenStreamRef.current.getTracks().forEach(track => track.stop());
      screenStreamRef.current = null;
    }
    
    // Close all peer connections
    Object.values(peerConnectionsRef.current).forEach(pc => pc.close());
    peerConnectionsRef.current = {};
    
    // Stop duration timer
    if (durationIntervalRef.current) {
      clearInterval(durationIntervalRef.current);
      durationIntervalRef.current = null;
    }
    
    // Send hangup message
    if (activeCall?.call_id) {
      sendMessage({
        type: 'call_hangup',
        call_id: activeCall.call_id
      });
      callingApi.callAction(activeCall.call_id, { action: 'hangup' }, user?.id).catch(() => {});
    }
    
    // Reset state
    setActiveCall(null);
    setCallStatus('idle');
    setIsMuted(false);
    setIsVideoEnabled(false);
    setIsScreenSharing(false);
    setIsRecording(false);
    setCallDuration(0);
    setRemoteStreams({});
    setParticipants([]);
  }, [activeCall, sendMessage, user]);
  
  // Toggle mute
  const toggleMute = useCallback(() => {
    if (localStreamRef.current) {
      const audioTrack = localStreamRef.current.getAudioTracks()[0];
      if (audioTrack) {
        audioTrack.enabled = !audioTrack.enabled;
        setIsMuted(!audioTrack.enabled);
        
        sendMessage({
          type: 'call_mute',
          call_id: activeCall?.call_id,
          is_muted: !audioTrack.enabled,
          media_type: 'audio'
        });
      }
    }
  }, [activeCall, sendMessage]);
  
  // Toggle video
  const toggleVideo = useCallback(async () => {
    if (!localStreamRef.current) return;
    
    const videoTrack = localStreamRef.current.getVideoTracks()[0];
    
    if (videoTrack) {
      // Disable video
      videoTrack.stop();
      localStreamRef.current.removeTrack(videoTrack);
      setIsVideoEnabled(false);
      
      sendMessage({
        type: 'call_mute',
        call_id: activeCall?.call_id,
        is_muted: true,
        media_type: 'video'
      });
    } else {
      // Enable video
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 } });
        const newVideoTrack = stream.getVideoTracks()[0];
        localStreamRef.current.addTrack(newVideoTrack);
        
        // Add to all peer connections
        Object.values(peerConnectionsRef.current).forEach(pc => {
          pc.addTrack(newVideoTrack, localStreamRef.current);
        });
        
        setIsVideoEnabled(true);
        
        sendMessage({
          type: 'call_mute',
          call_id: activeCall?.call_id,
          is_muted: false,
          media_type: 'video'
        });
      } catch (err) {
        toast.error('Could not enable camera');
      }
    }
  }, [activeCall, sendMessage]);
  
  // Toggle screen share
  const toggleScreenShare = useCallback(async () => {
    if (isScreenSharing) {
      // Stop screen share
      if (screenStreamRef.current) {
        screenStreamRef.current.getTracks().forEach(track => track.stop());
        screenStreamRef.current = null;
      }
      setIsScreenSharing(false);
      
      sendMessage({
        type: 'screen_share_stop',
        call_id: activeCall?.call_id
      });
    } else {
      // Start screen share
      try {
        const stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
        screenStreamRef.current = stream;
        
        // Replace video track in peer connections
        const screenTrack = stream.getVideoTracks()[0];
        Object.values(peerConnectionsRef.current).forEach(pc => {
          const sender = pc.getSenders().find(s => s.track?.kind === 'video');
          if (sender) {
            sender.replaceTrack(screenTrack);
          }
        });
        
        screenTrack.onended = () => {
          toggleScreenShare();
        };
        
        setIsScreenSharing(true);
        
        sendMessage({
          type: 'screen_share_start',
          call_id: activeCall?.call_id
        });
      } catch (err) {
        toast.error('Could not share screen');
      }
    }
  }, [isScreenSharing, activeCall, sendMessage]);
  
  // Toggle hold
  const toggleHold = useCallback(() => {
    const isOnHold = callStatus === 'on_hold';
    setCallStatus(isOnHold ? 'connected' : 'on_hold');
    
    sendMessage({
      type: 'call_hold',
      call_id: activeCall?.call_id,
      is_held: !isOnHold
    });
    
    callingApi.callAction(activeCall?.call_id, { action: isOnHold ? 'unhold' : 'hold' }, user?.id).catch(() => {});
  }, [callStatus, activeCall, sendMessage, user]);
  
  // Toggle recording
  const toggleRecording = useCallback(async () => {
    if (isRecording) {
      await callingApi.stopRecording(activeCall?.call_id);
      setIsRecording(false);
      toast.success('Recording stopped');
    } else {
      await callingApi.startRecording(activeCall?.call_id);
      setIsRecording(true);
      toast.success('Recording started');
    }
  }, [isRecording, activeCall]);
  
  // Transfer call
  const transferCall = useCallback((targetUserId) => {
    sendMessage({
      type: 'call_transfer',
      call_id: activeCall?.call_id,
      transfer_to_user_id: targetUserId
    });
    
    callingApi.callAction(activeCall?.call_id, { 
      action: 'transfer', 
      target_user_id: targetUserId 
    }, user?.id).catch(() => {});
    
    toast.info('Transferring call...');
  }, [activeCall, sendMessage, user]);
  
  // Add participant to conference
  const addParticipant = useCallback((targetUserId) => {
    sendMessage({
      type: 'conference_add',
      call_id: activeCall?.call_id,
      participant_id: targetUserId
    });
    
    callingApi.callAction(activeCall?.call_id, { 
      action: 'add_participant', 
      target_user_id: targetUserId 
    }, user?.id).catch(() => {});
  }, [activeCall, sendMessage, user]);
  
  // Start duration timer
  const startDurationTimer = useCallback(() => {
    if (durationIntervalRef.current) {
      clearInterval(durationIntervalRef.current);
    }
    setCallDuration(0);
    durationIntervalRef.current = setInterval(() => {
      setCallDuration(prev => prev + 1);
    }, 1000);
  }, []);
  
  // Format duration
  const formatDuration = (seconds) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    if (hrs > 0) {
      return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };
  
  return (
    <CallContext.Provider value={{
      // State
      activeCall,
      incomingCall,
      callStatus,
      isMuted,
      isVideoEnabled,
      isScreenSharing,
      isRecording,
      callDuration,
      formattedDuration: formatDuration(callDuration),
      remoteStreams,
      participants,
      myExtension,
      callableContacts,
      localStream: localStreamRef.current,
      
      // Actions
      initiateCall,
      answerCall,
      rejectCall,
      endCall,
      toggleMute,
      toggleVideo,
      toggleScreenShare,
      toggleHold,
      toggleRecording,
      transferCall,
      addParticipant,
      
      // Helpers
      isInCall: !!activeCall,
      hasIncomingCall: !!incomingCall,
    }}>
      {children}
    </CallContext.Provider>
  );
};
