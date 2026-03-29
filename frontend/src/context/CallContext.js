import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from './AuthContext';
import { useWebSocket } from './WebSocketContext';
import { callingApi } from '../services/api';
import { toast } from 'sonner';

// Lazy-load SIP service only when needed
let sipService = null;
const getSipService = () => {
  if (!sipService) { try { sipService = require('../services/sipService').default; } catch {} }
  return sipService;
};

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
  const [sipRegistered, setSipRegistered] = useState(false);
  const [sipError, setSipError] = useState(null);

  const localStreamRef = useRef(null);
  const screenStreamRef = useRef(null);
  const peerConnectionsRef = useRef({});
  const iceServersRef = useRef([{ urls: 'stun:stun.l.google.com:19302' }]);
  const durationIntervalRef = useRef(null);
  const remoteAudioRef = useRef(null);

  // Hidden audio element for remote streams
  useEffect(() => {
    if (!remoteAudioRef.current) {
      const el = document.createElement('audio');
      el.autoplay = true; el.id = 'remote-audio'; el.style.display = 'none';
      document.body.appendChild(el);
      remoteAudioRef.current = el;
    }
    return () => { remoteAudioRef.current?.remove(); remoteAudioRef.current = null; };
  }, []);

  // Load contacts + ICE servers
  useEffect(() => {
    if (!user?.id) return;
    callingApi.getCallableContacts(user.id).then(r => setCallableContacts(r.data || [])).catch(() => {});
    callingApi.getIceServers().then(r => { if (r.data?.ice_servers) iceServersRef.current = r.data.ice_servers; }).catch(() => {});
    // Check if PBX is configured for SIP (dormant - only register when user explicitly tests)
    callingApi.getSipCredentials().then(r => {
      if (r.data?.sip_username && r.data?.websocket_url) {
        setSipError(null); // PBX is configured, SIP available but not auto-registered
      }
    }).catch(() => {});
  }, [user?.id]);

  // WebSocket call signaling
  useEffect(() => {
    const types = ['incoming_call', 'call_answered', 'ice_candidate', 'call_rejected', 'call_ended', 'call_hold_changed', 'call_mute_changed'];
    const unsubs = types.map(type => addListener(type, (data) => {
      switch (type) {
        case 'incoming_call': handleIncomingCall(data); break;
        case 'call_answered': handleCallAnswered(data); break;
        case 'ice_candidate': handleIceCandidate(data); break;
        case 'call_rejected': handleCallRejected(data); break;
        case 'call_ended': handleCallEnded(data); break;
        case 'call_hold_changed': setCallStatus(data.is_held ? 'on_hold' : 'connected'); break;
        default: break;
      }
    }));
    return () => unsubs.forEach(u => u());
  }, [addListener]);

  // Get user media
  const getUserMedia = useCallback(async (withVideo = false) => {
    if (localStreamRef.current) {
      localStreamRef.current.getTracks().forEach(t => t.stop());
    }
    const constraints = { audio: true, video: withVideo ? { width: 1280, height: 720, facingMode: 'user' } : false };
    const stream = await navigator.mediaDevices.getUserMedia(constraints);
    localStreamRef.current = stream;
    setIsVideoEnabled(withVideo);
    return stream;
  }, []);

  // Create WebRTC peer connection
  const createPeerConnection = useCallback((targetUserId) => {
    if (peerConnectionsRef.current[targetUserId]) {
      peerConnectionsRef.current[targetUserId].close();
    }
    const pc = new RTCPeerConnection({ iceServers: iceServersRef.current });
    peerConnectionsRef.current[targetUserId] = pc;

    if (localStreamRef.current) {
      localStreamRef.current.getTracks().forEach(track => pc.addTrack(track, localStreamRef.current));
    }
    pc.ontrack = (event) => {
      const [stream] = event.streams;
      setRemoteStreams(prev => ({ ...prev, [targetUserId]: stream }));
      if (remoteAudioRef.current) { remoteAudioRef.current.srcObject = stream; remoteAudioRef.current.play().catch(() => {}); }
    };
    pc.onicecandidate = (event) => {
      if (event.candidate) {
        send({ type: 'ice_candidate', target_user_id: targetUserId, candidate: event.candidate, call_id: activeCall?.call_id });
      }
    };
    pc.onconnectionstatechange = () => {
      if (pc.connectionState === 'connected') { setCallStatus('connected'); startDurationTimer(); }
      if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected') { toast.error('Call connection lost'); endCall(); }
    };
    return pc;
  }, [send, activeCall]);

  // Initiate call — pure WebRTC
  const initiateCall = useCallback(async (targetUserId, callType = 'audio') => {
    if (!user?.id) { toast.error('Not connected'); return; }
    try {
      await getUserMedia(callType === 'video');
      const res = await callingApi.initiateCall({ to_user_id: targetUserId, call_type: callType, use_pbx: false }, user.id);
      const { call_id, ice_servers, call } = res.data;
      if (ice_servers) iceServersRef.current = ice_servers;
      const target = callableContacts.find(c => c.user_id === targetUserId);
      setActiveCall({ ...call, call_id, target_name: target?.name || targetUserId, call_type: callType });
      setCallStatus('ringing');
      setParticipants([user.id, targetUserId]);
      const pc = createPeerConnection(targetUserId);
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      send({ type: 'call_offer', call_id, target_user_id: targetUserId, sdp: offer, call_type: callType, caller_name: user.name });
      return call_id;
    } catch (err) {
      console.error('Call failed:', err);
      endCall();
      toast.error('Failed to start call');
    }
  }, [user, callableContacts, createPeerConnection, getUserMedia, send]);

  // Handle incoming call
  const handleIncomingCall = useCallback((data) => {
    setIncomingCall(data);
    setCallStatus('ringing');
    try { const audio = new Audio('/ringtone.mp3'); audio.loop = true; audio.play().catch(() => {}); data.ringtone = audio; } catch {}
  }, []);

  // Answer call
  const answerCall = useCallback(async (withVideo = false) => {
    if (!incomingCall) return;
    try {
      if (incomingCall.ringtone) { incomingCall.ringtone.pause(); incomingCall.ringtone.currentTime = 0; }
      const isVideoCall = withVideo || incomingCall.call_type === 'video';
      await getUserMedia(isVideoCall);
      const pc = createPeerConnection(incomingCall.caller_id);
      await pc.setRemoteDescription(new RTCSessionDescription(incomingCall.sdp));
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      send({ type: 'call_answer', call_id: incomingCall.call_id, caller_id: incomingCall.caller_id, sdp: answer });
      setActiveCall({ call_id: incomingCall.call_id, caller_id: incomingCall.caller_id, caller_name: incomingCall.caller_name, call_type: incomingCall.call_type });
      setCallStatus('connected');
      setParticipants([user.id, incomingCall.caller_id]);
      setIncomingCall(null);
      startDurationTimer();
      callingApi.callAction(incomingCall.call_id, { action: 'answer' }, user.id).catch(() => {});
    } catch (err) { console.error('Answer failed:', err); rejectCall(); }
  }, [incomingCall, user, createPeerConnection, getUserMedia, send]);

  const handleCallAnswered = useCallback((data) => {
    const pc = peerConnectionsRef.current[data.answerer_id || data.caller_id];
    if (pc && data.sdp) { pc.setRemoteDescription(new RTCSessionDescription(data.sdp)).catch(() => {}); }
    setCallStatus('connected');
    startDurationTimer();
  }, []);

  const handleIceCandidate = useCallback((data) => {
    const pc = peerConnectionsRef.current[data.from_user_id || data.sender_id];
    if (pc && data.candidate) { pc.addIceCandidate(new RTCIceCandidate(data.candidate)).catch(() => {}); }
  }, []);

  const handleCallRejected = useCallback(() => {
    toast.info('Call was declined');
    endCall();
  }, []);

  const handleCallEnded = useCallback(() => { endCall(); }, []);

  // Reject incoming call
  const rejectCall = useCallback(() => {
    if (incomingCall?.ringtone) { incomingCall.ringtone.pause(); }
    if (incomingCall?.call_id) { send({ type: 'call_reject', call_id: incomingCall.call_id }); }
    setIncomingCall(null);
    setCallStatus('idle');
  }, [incomingCall, send]);

  // End call
  const endCall = useCallback(() => {
    if (localStreamRef.current) { localStreamRef.current.getTracks().forEach(t => t.stop()); localStreamRef.current = null; }
    if (screenStreamRef.current) { screenStreamRef.current.getTracks().forEach(t => t.stop()); screenStreamRef.current = null; }
    Object.values(peerConnectionsRef.current).forEach(pc => pc.close());
    peerConnectionsRef.current = {};
    if (durationIntervalRef.current) { clearInterval(durationIntervalRef.current); durationIntervalRef.current = null; }
    if (activeCall?.call_id) {
      send({ type: 'call_hangup', call_id: activeCall.call_id });
      callingApi.callAction(activeCall.call_id, { action: 'hangup' }, user?.id).catch(() => {});
    }
    setActiveCall(null); setCallStatus('idle'); setIsMuted(false); setIsVideoEnabled(false);
    setIsScreenSharing(false); setIsRecording(false); setCallDuration(0);
    setRemoteStreams({}); setParticipants([]);
  }, [activeCall, send, user]);

  // Toggle mute
  const toggleMute = useCallback(() => {
    if (localStreamRef.current) {
      const track = localStreamRef.current.getAudioTracks()[0];
      if (track) { track.enabled = !track.enabled; setIsMuted(!track.enabled); }
    }
  }, []);

  // Toggle video
  const toggleVideo = useCallback(async () => {
    if (isVideoEnabled) {
      localStreamRef.current?.getVideoTracks().forEach(t => { t.stop(); localStreamRef.current.removeTrack(t); });
      setIsVideoEnabled(false);
    } else {
      try {
        const videoStream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 } });
        const videoTrack = videoStream.getVideoTracks()[0];
        localStreamRef.current?.addTrack(videoTrack);
        Object.values(peerConnectionsRef.current).forEach(pc => {
          const sender = pc.getSenders().find(s => s.track?.kind === 'video');
          if (sender) sender.replaceTrack(videoTrack); else pc.addTrack(videoTrack, localStreamRef.current);
        });
        setIsVideoEnabled(true);
      } catch { toast.error('Camera not available'); }
    }
  }, [isVideoEnabled]);

  // Screen share
  const toggleScreenShare = useCallback(async () => {
    if (isScreenSharing) {
      screenStreamRef.current?.getTracks().forEach(t => t.stop());
      screenStreamRef.current = null;
      // Restore camera track
      const camTrack = localStreamRef.current?.getVideoTracks()[0];
      Object.values(peerConnectionsRef.current).forEach(pc => {
        const sender = pc.getSenders().find(s => s.track?.kind === 'video');
        if (sender && camTrack) sender.replaceTrack(camTrack);
      });
      setIsScreenSharing(false);
    } else {
      try {
        const screen = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true });
        screenStreamRef.current = screen;
        const screenTrack = screen.getVideoTracks()[0];
        Object.values(peerConnectionsRef.current).forEach(pc => {
          const sender = pc.getSenders().find(s => s.track?.kind === 'video');
          if (sender) sender.replaceTrack(screenTrack); else pc.addTrack(screenTrack, screen);
        });
        screenTrack.onended = () => { setIsScreenSharing(false); };
        setIsScreenSharing(true);
      } catch { toast.error('Screen sharing cancelled'); }
    }
  }, [isScreenSharing]);

  // Hold
  const toggleHold = useCallback(() => {
    const held = callStatus === 'on_hold';
    setCallStatus(held ? 'connected' : 'on_hold');
    send({ type: 'call_hold', call_id: activeCall?.call_id, is_held: !held });
  }, [callStatus, activeCall, send]);

  // Record
  const toggleRecording = useCallback(async () => {
    if (isRecording) { setIsRecording(false); toast.success('Recording stopped'); }
    else { setIsRecording(true); toast.success('Recording started'); }
  }, [isRecording]);

  // Transfer
  const transferCall = useCallback((targetUserId) => {
    send({ type: 'call_transfer', call_id: activeCall?.call_id, transfer_to_user_id: targetUserId });
    toast.info('Transferring...');
  }, [activeCall, send]);

  // Add participant (group call)
  const addParticipant = useCallback(async (targetUserId) => {
    try {
      const pc = createPeerConnection(targetUserId);
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      send({ type: 'call_offer', call_id: activeCall?.call_id, target_user_id: targetUserId, sdp: offer, call_type: activeCall?.call_type || 'audio', caller_name: user?.name });
      setParticipants(prev => [...prev, targetUserId]);
      toast.success('Participant added');
    } catch { toast.error('Failed to add participant'); }
  }, [activeCall, user, createPeerConnection, send]);

  // Duration timer
  const startDurationTimer = useCallback(() => {
    if (durationIntervalRef.current) clearInterval(durationIntervalRef.current);
    setCallDuration(0);
    durationIntervalRef.current = setInterval(() => setCallDuration(p => p + 1), 1000);
  }, []);

  const formatDuration = (s) => {
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return h > 0 ? `${h}:${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}` : `${m}:${sec.toString().padStart(2, '0')}`;
  };

  return (
    <CallContext.Provider value={{
      activeCall, incomingCall, callStatus, isMuted, isVideoEnabled, isScreenSharing,
      isRecording, callDuration, formattedDuration: formatDuration(callDuration),
      remoteStreams, participants, callableContacts, localStream: localStreamRef.current,
      sipRegistered, sipError,
      initiateCall, answerCall, rejectCall, endCall, toggleMute, toggleVideo,
      toggleScreenShare, toggleHold, toggleRecording, transferCall, addParticipant,
      isInCall: !!activeCall, hasIncomingCall: !!incomingCall,
    }}>
      {children}
    </CallContext.Provider>
  );
};
