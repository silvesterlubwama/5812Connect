import { useCallback, useRef } from 'react';
import { toast } from 'sonner';

/**
 * Hook for managing WebRTC media controls: mute, video, screen share, recording.
 * Operates on the provided localStreamRef and peerConnectionsRef.
 */
export function useMediaControls(localStreamRef, screenStreamRef, peerConnectionsRef) {
  const toggleMute = useCallback((isMuted, setIsMuted) => {
    if (localStreamRef.current) {
      const track = localStreamRef.current.getAudioTracks()[0];
      if (track) { track.enabled = !track.enabled; setIsMuted(!track.enabled); }
    }
  }, [localStreamRef]);

  const toggleVideo = useCallback(async (isVideoEnabled, setIsVideoEnabled) => {
    if (isVideoEnabled) {
      localStreamRef.current?.getVideoTracks().forEach(t => { t.stop(); localStreamRef.current.removeTrack(t); });
      setIsVideoEnabled(false);
    } else {
      try {
        const vs = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 } });
        const vt = vs.getVideoTracks()[0];
        localStreamRef.current?.addTrack(vt);
        Object.values(peerConnectionsRef.current).forEach(pc => {
          const sender = pc.getSenders().find(s => s.track?.kind === 'video');
          if (sender) sender.replaceTrack(vt); else pc.addTrack(vt, localStreamRef.current);
        });
        setIsVideoEnabled(true);
      } catch { toast.error('Camera not available'); }
    }
  }, [localStreamRef, peerConnectionsRef]);

  const toggleScreenShare = useCallback(async (isScreenSharing, setIsScreenSharing) => {
    if (isScreenSharing) {
      screenStreamRef.current?.getTracks().forEach(t => t.stop()); screenStreamRef.current = null;
      setIsScreenSharing(false);
    } else {
      try {
        const screen = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true });
        screenStreamRef.current = screen;
        const st = screen.getVideoTracks()[0];
        Object.values(peerConnectionsRef.current).forEach(pc => {
          const sender = pc.getSenders().find(s => s.track?.kind === 'video');
          if (sender) sender.replaceTrack(st); else pc.addTrack(st, screen);
        });
        st.onended = () => setIsScreenSharing(false);
        setIsScreenSharing(true);
      } catch { toast.error('Screen sharing cancelled'); }
    }
  }, [screenStreamRef, peerConnectionsRef]);

  const toggleRecording = useCallback((setIsRecording) => {
    setIsRecording(prev => { if (prev) toast.success('Recording stopped'); else toast.success('Recording started'); return !prev; });
  }, []);

  return { toggleMute, toggleVideo, toggleScreenShare, toggleRecording };
}
