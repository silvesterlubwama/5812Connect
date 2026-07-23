/**
 * Compatibility shim that lets existing components that used the old
 * `useCall()` hook (from the deleted CallContext) keep compiling. It maps
 * the two properties we still need — `initiateCall` (WebRTC user→user) and
 * `isInCall` — onto the new VoipContext.
 *
 * Cross-staff WebRTC video calls (initiate video from CommsPage) now route
 * through the same softphone as normal audio: we resolve the target user's
 * SIP extension and dial that. Video is deferred until we wire an admin-side
 * "enable video on extension" toggle — until then the button places an audio
 * call.
 */
import { useCallback } from 'react';
import { toast } from 'sonner';
import { useVoip } from '../context/VoipContext';
import api from '../services/api';

export const useCall = () => {
  const v = useVoip();
  const initiateCall = useCallback(async (targetUserId, _type = 'audio') => {
    if (v.status !== 'registered') {
      toast.error(v.statusReason || 'Softphone not registered');
      return;
    }
    try {
      const r = await api.get('/voip/me/directory');
      const target = (r.data || []).find(u => u.user_id === targetUserId);
      if (!target?.extension) {
        toast.error('That colleague has no SIP extension assigned yet.');
        return;
      }
      v.dial(target.extension);
    } catch (e) {
      toast.error('Could not resolve extension');
    }
  }, [v]);
  return {
    initiateCall,
    isInCall: ['outgoing', 'in-call', 'held'].includes(v.callState),
    hasIncomingCall: v.callState === 'incoming',
    // Legacy fields kept as safe defaults so old consumers (Dialer.jsx) that
    // destructure `callableContacts` etc. keep rendering without a full rewrite.
    callableContacts: [],
    sipRegistered: v.status === 'registered',
  };
};

export default useCall;
