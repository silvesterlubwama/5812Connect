import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from './AuthContext';
import { useWebSocket } from './WebSocketContext';
import { callingApi } from '../services/api';
import { toast } from 'sonner';
import { useMediaControls } from '../hooks/useMediaControls';
import { usePeerConnections, formatCallDuration } from '../hooks/usePeerConnections';

const CallContext = createContext(null);

export const useCall = () => {
  const ctx = useContext(CallContext);
  if (!ctx) return {
    activeCall: null, incomingCall: null, callStatus: 'idle', isMuted: false,
    isVideoEnabled: false, isScreenSharing: false, isRecording: false, callDuration: 0,
    formattedDuration: '0:00', remoteStreams: {}, participants: [], callableContacts: [],
    localStream: null, sipRegistered: false, sipError: null, isInCall: false, hasIncomingCall: false,
    initiateCall: () => {}, answerCall: () => {}, rejectCall: () => {}, endCall: () => {},
    toggleMute: () => {}, toggleVideo: () => {}, toggleScreenShare: () => {},
    toggleHold: () => {}, toggleRecording: () => {}, transferCall: () => {}, addParticipant: () => {},
  };
  return ctx;
};

export const CallProvider = ({ children }) => {
  const { user } = useAuth();
  const { send, addListener } = useWebSocket();

  // Call state
  const [activeCall, setActiveCall] = useState(null);
  const [incomingCall, setIncomingCall] = useState(null);
  const [callStatus, setCallStatus] = useState('idle');
  const [isMuted, setIsMuted] = useState(false);
  const [isVideoEnabled, setIsVideoEnabled] = useState(false);
  const [isScreenSharing, setIsScreenSharing] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [callDuration, setCallDuration] = useState(0);
  const [remoteStreams, setRemoteStreams] = useState({});
  const [participants, setParticipants] = useState([]);
  const [callableContacts, setCallableContacts] = useState([]);

  // Refs
  const localStreamRef = useRef(null);
  const screenStreamRef = useRef(null);
  const iceServersRef = useRef([{ urls: 'stun:stun.l.google.com:19302' }]);
  const durationIntervalRef = useRef(null);
  const remoteAudioRef = useRef(null);
  const activeCallRef = useRef(null);
  activeCallRef.current = activeCall;

  // Hidden audio element
  useEffect(() => {
    if (!remoteAudioRef.current) {
      const el = document.createElement('audio');
      el.autoplay = true; el.id = 'remote-audio'; el.style.display = 'none';
      document.body.appendChild(el);
      remoteAudioRef.current = el;
    }
    return () => { if (remoteAudioRef.current) { remoteAudioRef.current.remove(); remoteAudioRef.current = null; } };
  }, []);

  // Load contacts
  useEffect(() => {
    if (!user?.id) return;
    callingApi.getCallableContacts(user.id).then(r => setCallableContacts(r.data || [])).catch(() => {});
    callingApi.getIceServers().then(r => { if (r.data?.ice_servers) iceServersRef.current = r.data.ice_servers; }).catch(() => {});
  }, [user?.id]);

  // Duration timer
  const startDurationTimer = useCallback(() => {
    if (durationIntervalRef.current) clearInterval(durationIntervalRef.current);
    setCallDuration(0);
    durationIntervalRef.current = setInterval(() => setCallDuration(p => p + 1), 1000);
  }, []);

  const stopDurationTimer = useCallback(() => {
    if (durationIntervalRef.current) { clearInterval(durationIntervalRef.current); durationIntervalRef.current = null; }
  }, []);

  // Cleanup
  const cleanupCall = useCallback(() => {
    if (localStreamRef.current) { localStreamRef.current.getTracks().forEach(t => t.stop()); localStreamRef.current = null; }
    if (screenStreamRef.current) { screenStreamRef.current.getTracks().forEach(t => t.stop()); screenStreamRef.current = null; }
    stopDurationTimer();
    setActiveCall(null); setCallStatus('idle'); setIsMuted(false); setIsVideoEnabled(false);
    setIsScreenSharing(false); setIsRecording(false); setCallDuration(0);
    setRemoteStreams({}); setParticipants([]);
  }, [stopDurationTimer]);

  // Extracted hooks
  const { peerConnectionsRef, getUserMedia, createPeerConnection, closeAllConnections } =
    usePeerConnections(iceServersRef, localStreamRef, remoteAudioRef, send, setRemoteStreams, setCallStatus, startDurationTimer, cleanupCall);

  const mediaControls = useMediaControls(localStreamRef, screenStreamRef, peerConnectionsRef);

  // Override cleanupCall to also close peer connections
  const fullCleanup = useCallback(() => {
    closeAllConnections();
    cleanupCall();
  }, [closeAllConnections, cleanupCall]);

  // Initiate call
  const initiateCall = useCallback(async (targetUserId, callType = 'audio') => {
    if (!user?.id) { toast.error('Not connected'); return; }
    try {
      const stream = await getUserMedia(callType === 'video');
      setIsVideoEnabled(callType === 'video');
      const res = await callingApi.initiateCall({ to_user_id: targetUserId, call_type: callType, use_pbx: false }, user.id);
      const { call_id, ice_servers, call } = res.data;
      if (ice_servers) iceServersRef.current = ice_servers;
      const target = callableContacts.find(c => c.user_id === targetUserId);
      setActiveCall({ ...call, call_id, target_name: target?.name || targetUserId, call_type: callType });
      setCallStatus('ringing'); setParticipants([user.id, targetUserId]);
      const pc = createPeerConnection(targetUserId, activeCallRef);
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      send({ type: 'call_offer', call_id, target_user_id: targetUserId, sdp: offer, call_type: callType, caller_name: user.name });
      return call_id;
    } catch (err) { console.error('Call failed:', err); fullCleanup(); toast.error('Failed to start call'); }
  }, [user, callableContacts, createPeerConnection, getUserMedia, send, fullCleanup]);

  // Answer call
  const answerCall = useCallback(async (withVideo = false) => {
    if (!incomingCall) return;
    try {
      if (incomingCall.ringtone) { incomingCall.ringtone.pause(); incomingCall.ringtone.currentTime = 0; }
      const isVideoCall = withVideo || incomingCall.call_type === 'video';
      await getUserMedia(isVideoCall);
      setIsVideoEnabled(isVideoCall);
      const pc = createPeerConnection(incomingCall.caller_id, activeCallRef);
      await pc.setRemoteDescription(new RTCSessionDescription(incomingCall.sdp));
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      send({ type: 'call_answer', call_id: incomingCall.call_id, caller_id: incomingCall.caller_id, sdp: answer });
      setActiveCall({ call_id: incomingCall.call_id, caller_id: incomingCall.caller_id, caller_name: incomingCall.caller_name, call_type: incomingCall.call_type });
      setCallStatus('connected'); setParticipants([user.id, incomingCall.caller_id]); setIncomingCall(null);
      startDurationTimer();
      callingApi.callAction(incomingCall.call_id, { action: 'answer' }, user.id).catch(() => {});
    } catch (err) { console.error('Answer failed:', err); rejectCall(); }
  }, [incomingCall, user, createPeerConnection, getUserMedia, send, startDurationTimer]);

  // Reject call
  const rejectCall = useCallback(() => {
    if (incomingCall?.ringtone) incomingCall.ringtone.pause();
    if (incomingCall?.call_id) send({ type: 'call_reject', call_id: incomingCall.call_id });
    setIncomingCall(null); setCallStatus('idle');
  }, [incomingCall, send]);

  // End call
  const endCall = useCallback(() => {
    if (activeCall?.call_id) {
      send({ type: 'call_hangup', call_id: activeCall.call_id });
      callingApi.callAction(activeCall.call_id, { action: 'hangup' }, user?.id).catch(() => {});
    }
    fullCleanup();
  }, [activeCall, send, user, fullCleanup]);

  // WebSocket signaling
  useEffect(() => {
    const unsubs = [
      addListener('incoming_call', (data) => { setIncomingCall(data); setCallStatus('ringing'); }),
      addListener('call_answered', (data) => {
        const pc = peerConnectionsRef.current[data.answerer_id || data.caller_id];
        if (pc && data.sdp) pc.setRemoteDescription(new RTCSessionDescription(data.sdp)).catch(() => {});
        setCallStatus('connected'); startDurationTimer();
      }),
      addListener('ice_candidate', (data) => {
        const pc = peerConnectionsRef.current[data.from_user_id || data.sender_id];
        if (pc && data.candidate) pc.addIceCandidate(new RTCIceCandidate(data.candidate)).catch(() => {});
      }),
      addListener('call_rejected', () => { toast.info('Call declined'); fullCleanup(); }),
      addListener('call_ended', () => fullCleanup()),
      addListener('call_hold_changed', (data) => setCallStatus(data.is_held ? 'on_hold' : 'connected')),
    ];
    return () => unsubs.forEach(u => u());
  }, [addListener, startDurationTimer, fullCleanup, peerConnectionsRef]);

  // Wrapped toggle functions (bind current state)
  const handleToggleMute = useCallback(() => mediaControls.toggleMute(isMuted, setIsMuted), [mediaControls, isMuted]);
  const handleToggleVideo = useCallback(() => mediaControls.toggleVideo(isVideoEnabled, setIsVideoEnabled), [mediaControls, isVideoEnabled]);
  const handleToggleScreenShare = useCallback(() => mediaControls.toggleScreenShare(isScreenSharing, setIsScreenSharing), [mediaControls, isScreenSharing]);
  const handleToggleRecording = useCallback(() => mediaControls.toggleRecording(setIsRecording), [mediaControls]);

  const toggleHold = useCallback(() => {
    const held = callStatus === 'on_hold';
    setCallStatus(held ? 'connected' : 'on_hold');
    send({ type: 'call_hold', call_id: activeCall?.call_id, is_held: !held });
  }, [callStatus, activeCall, send]);

  const transferCall = useCallback((targetUserId) => {
    send({ type: 'call_transfer', call_id: activeCall?.call_id, transfer_to_user_id: targetUserId });
    toast.info('Transferring...');
  }, [activeCall, send]);

  const addParticipant = useCallback(async (targetUserId) => {
    try {
      const pc = createPeerConnection(targetUserId, activeCallRef);
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      send({ type: 'call_offer', call_id: activeCall?.call_id, target_user_id: targetUserId, sdp: offer, call_type: activeCall?.call_type || 'audio', caller_name: user?.name });
      setParticipants(prev => [...prev, targetUserId]);
      toast.success('Participant added');
    } catch { toast.error('Failed to add participant'); }
  }, [activeCall, user, createPeerConnection, send]);

  return (
    <CallContext.Provider value={{
      activeCall, incomingCall, callStatus, isMuted, isVideoEnabled, isScreenSharing,
      isRecording, callDuration, formattedDuration: formatCallDuration(callDuration),
      remoteStreams, participants, callableContacts, localStream: localStreamRef.current,
      sipRegistered: false, sipError: null,
      initiateCall, answerCall, rejectCall, endCall,
      toggleMute: handleToggleMute, toggleVideo: handleToggleVideo,
      toggleScreenShare: handleToggleScreenShare, toggleHold, toggleRecording: handleToggleRecording,
      transferCall, addParticipant,
      isInCall: !!activeCall, hasIncomingCall: !!incomingCall,
    }}>
      {children}
    </CallContext.Provider>
  );
};
