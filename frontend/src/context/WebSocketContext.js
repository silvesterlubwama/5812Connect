import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from './AuthContext';

const WebSocketContext = createContext(null);

export const WebSocketProvider = ({ children }) => {
  const { user } = useAuth();
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const [onlineUsers, setOnlineUsers] = useState([]);
  const [typingUsers, setTypingUsers] = useState({});
  const listenersRef = useRef(new Map());
  const isConnecting = useRef(false);

  const addListener = useCallback((type, callback) => {
    if (!listenersRef.current.has(type)) listenersRef.current.set(type, new Set());
    listenersRef.current.get(type).add(callback);
    return () => listenersRef.current.get(type)?.delete(callback);
  }, []);

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const sendTyping = useCallback((conversationId, participants) => {
    send({ type: 'typing', conversation_id: conversationId, participants });
  }, [send]);

  const sendChatMessage = useCallback((conversationId, text, senderName, replyTo) => {
    send({ type: 'chat_message', conversation_id: conversationId, text, sender_name: senderName, reply_to: replyTo || null });
  }, [send]);

  const sendReadReceipt = useCallback((conversationId, messageId) => {
    send({ type: 'read_receipt', conversation_id: conversationId, message_id: messageId });
  }, [send]);

  const connect = useCallback(() => {
    if (!user?.id || isConnecting.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    isConnecting.current = true;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const backendUrl = process.env.REACT_APP_BACKEND_URL || '';
    const host = backendUrl.replace(/^https?:\/\//, '');
    const wsUrl = `${protocol}//${host}/ws/${user.id}`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        isConnecting.current = false;
        clearTimeout(reconnectTimer.current);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'online_users') setOnlineUsers(data.users || []);
          else if (data.type === 'user_online') setOnlineUsers(prev => prev.includes(data.user_id) ? prev : [...prev, data.user_id]);
          else if (data.type === 'user_offline') setOnlineUsers(prev => prev.filter(id => id !== data.user_id));
          else if (data.type === 'typing') {
            const key = data.conversation_id;
            setTypingUsers(prev => ({ ...prev, [key]: { user_id: data.user_id, ts: Date.now() } }));
            setTimeout(() => setTypingUsers(prev => {
              const entry = prev[key];
              if (entry && Date.now() - entry.ts > 3000) { const next = { ...prev }; delete next[key]; return next; }
              return prev;
            }), 3500);
          }
          const handlers = listenersRef.current.get(data.type);
          if (handlers) handlers.forEach(cb => cb(data));
        } catch {}
      };

      ws.onclose = () => {
        isConnecting.current = false;
        reconnectTimer.current = setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        isConnecting.current = false;
        ws.close();
      };
    } catch {
      isConnecting.current = false;
    }
  }, [user?.id]);

  useEffect(() => {
    if (user?.id) connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
      isConnecting.current = false;
    };
  }, [user?.id, connect]);

  // Ping keepalive
  useEffect(() => {
    const interval = setInterval(() => send({ type: 'ping' }), 25000);
    return () => clearInterval(interval);
  }, [send]);

  return (
    <WebSocketContext.Provider value={{ onlineUsers, typingUsers, send, sendTyping, sendChatMessage, sendReadReceipt, addListener }}>
      {children}
    </WebSocketContext.Provider>
  );
};

export const useWebSocket = () => {
  const ctx = useContext(WebSocketContext);
  if (!ctx) return { onlineUsers: [], typingUsers: {}, send: () => {}, sendTyping: () => {}, sendChatMessage: () => {}, sendReadReceipt: () => {}, addListener: () => () => {} };
  return ctx;
};
