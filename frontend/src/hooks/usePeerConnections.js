import { useCallback, useRef } from 'react';
import { toast } from 'sonner';

/**
 * Hook for managing WebRTC peer connections, ICE candidates, and media streams.
 */
export function usePeerConnections(iceServersRef, localStreamRef, remoteAudioRef, send, setRemoteStreams, setCallStatus, startDurationTimer, cleanupCall) {

  const peerConnectionsRef = useRef({});

  const getUserMedia = useCallback(async (withVideo = false) => {
    if (localStreamRef.current) localStreamRef.current.getTracks().forEach(t => t.stop());
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true, video: withVideo ? { width: 1280, height: 720, facingMode: 'user' } : false
    });
    localStreamRef.current = stream;
    return stream;
  }, [localStreamRef]);

  const createPeerConnection = useCallback((targetUserId, activeCallRef) => {
    if (peerConnectionsRef.current[targetUserId]) peerConnectionsRef.current[targetUserId].close();
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
        send({ type: 'ice_candidate', target_user_id: targetUserId, candidate: event.candidate, call_id: activeCallRef?.current?.call_id });
      }
    };

    pc.onconnectionstatechange = () => {
      if (pc.connectionState === 'connected') { setCallStatus('connected'); startDurationTimer(); }
      if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected') { toast.error('Connection lost'); cleanupCall(); }
    };

    return pc;
  }, [iceServersRef, localStreamRef, remoteAudioRef, send, setRemoteStreams, setCallStatus, startDurationTimer, cleanupCall]);

  const closeAllConnections = useCallback(() => {
    Object.values(peerConnectionsRef.current).forEach(pc => pc.close());
    peerConnectionsRef.current = {};
  }, []);

  return { peerConnectionsRef, getUserMedia, createPeerConnection, closeAllConnections };
}

/**
 * Utility: Format call duration seconds to h:mm:ss or m:ss string.
 */
export function formatCallDuration(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h > 0
    ? `${h}:${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`
    : `${m}:${sec.toString().padStart(2, '0')}`;
}
