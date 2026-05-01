import React, { useState, useEffect, useRef, useCallback } from 'react';
import { MessageSquare, Plus, Send, Bot, Megaphone, Users, Search, Hash, Reply, Check, CheckCheck, X, Circle, Phone, Video, Smile, PhoneCall, ChevronRight, Trash2, Settings } from 'lucide-react';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Avatar, AvatarFallback } from '../components/ui/avatar';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Textarea } from '../components/ui/textarea';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { chatApi, membersApi, presenceApi, reactionsApi, conferencesApi } from '../services/api';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useWebSocket } from '../context/WebSocketContext';
import { useCall } from '../context/CallContext';
import { toast } from 'sonner';
import { ConferenceDialog } from '../components/comms/ConferenceDialog';
import { NewConversationDialog } from '../components/comms/NewConversationDialog';
import { AnnouncementDialog } from '../components/comms/AnnouncementDialog';

const initials = (name) => (name || '?').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
const QUICK_EMOJIS = ['👍', '❤️', '😂', '😮', '😢', '🎉', '🙏', '👏', '🔥', '💯', '✅'];

const AI_ROOM = { id: '__ai__', name: 'AI Assistant', type: 'ai_assistant', icon: 'bot' };
const ANNOUNCE_ROOM = { id: '__announcements__', name: 'Announcements', type: 'announcements', icon: 'megaphone', is_no_reply: true };
const ORG_ROLES = ['Adviser', 'Executive Director', 'Director', 'Manager', 'Leader', 'Coordinator', 'Staff', 'Volunteer'];

const PRESENCE_DOTS = {
  online: 'bg-green-500', idle: 'bg-yellow-500', pbx_only: 'bg-blue-500',
  offline: 'bg-red-500', dnd: 'bg-red-600', on_call: 'bg-blue-500 animate-pulse',
};
const PRESENCE_LABELS = {
  online: 'Available', idle: 'Away', pbx_only: 'Phone Only',
  offline: 'Offline', dnd: 'Do Not Disturb', on_call: 'On a Call',
};

export default function CommsPage() {
  const { user } = useAuth();
  const { onlineUsers, typingUsers, sendTyping, sendChatMessage, sendReadReceipt, addListener } = useWebSocket();
  const { initiateCall, isInCall } = useCall();
  const [conversations, setConversations] = useState([]);
  const [selectedRoom, setSelectedRoom] = useState(null);
  const [messages, setMessages] = useState([]);
  const [newMsg, setNewMsg] = useState('');
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [replyTo, setReplyTo] = useState(null);
  const [showEditGroup, setShowEditGroup] = useState(false);
  const [groupAddSearch, setGroupAddSearch] = useState('');

  const [aiMessages, setAiMessages] = useState([]);
  const [aiSessionId] = useState(() => `ai_${user?.id || 'anon'}_${Date.now()}`);

  const [announcements, setAnnouncements] = useState([]);
  const [showNewAnnouncement, setShowNewAnnouncement] = useState(false);
  const [announcementForm, setAnnouncementForm] = useState({ title: '', content: '', type: 'general' });

  const [showNewConv, setShowNewConv] = useState(false);
  const [allStaff, setAllStaff] = useState([]);
  const [convForm, setConvForm] = useState({ name: '', participants: [], type: 'direct' });

  // Presence
  const [presenceMap, setPresenceMap] = useState({});
  const [myStatus, setMyStatus] = useState('online');

  // Reactions
  const [showEmojiFor, setShowEmojiFor] = useState(null);

  // Thread panel
  const [activeThread, setActiveThread] = useState(null);
  const [threadMessages, setThreadMessages] = useState([]);
  const [threadMsg, setThreadMsg] = useState('');

  // Conference
  const [showConference, setShowConference] = useState(false);
  const [showOrgChart, setShowOrgChart] = useState(false);
  const [confForm, setConfForm] = useState({ title: '', description: '', scheduled_at: '', duration_minutes: 60, user_ids: [], external_emails: '', is_video_enabled: true, password: '', create_calendar_event: true, send_email_invites: true });

  const messagesEndRef = useRef(null);
  const typingTimeout = useRef(null);
  const scrollToBottom = () => setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);

  const fetchConversations = useCallback(async () => {
    try {
      const res = await chatApi.conversations();
      setConversations(res.data || []);
    } catch (e) { console.warn(e.message || e); }
  }, []);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await fetchConversations();
      try {
        const [annRes, staffRes] = await Promise.all([
          api.get('/announcements'),
          chatApi.users(),
        ]);
        setAnnouncements(annRes.data || []);
        let staff = staffRes.data || [];
        // For directors+, also load directors from other campuses for cross-campus messaging
        if (['admin', 'system_admin', 'executive director', 'adviser', 'director'].includes((user?.role || '').toLowerCase())) {
          try {
            const [dirRes, edRes] = await Promise.all([
              api.get('/admin/users', { params: { role: 'Director', limit: 50 } }),
              api.get('/admin/users', { params: { role: 'Executive Director', limit: 20 } }),
            ]);
            const allDirs = [...(dirRes.data || []), ...(edRes.data || [])];
            const existingIds = new Set(staff.map(s => s.id));
            for (const d of allDirs) {
              if (!existingIds.has(d.id) && d.id !== user?.id && d.status !== 'deleted') {
                staff.push({ ...d, is_cross_campus: true });
              }
            }
          } catch (e) { console.warn(e.message || e); }
        }
        setAllStaff(staff);
      } catch (e) { console.warn(e.message || e); }
      try {
        const aiRes = await chatApi.messages(`ai_${user?.id}`, { limit: 50 });
        setAiMessages((aiRes.data || []).map(m => ({ role: m.type === 'ai' ? 'assistant' : 'user', text: m.text })));
      } catch (e) { console.warn(e.message || e); }
      setLoading(false);
    };
    load();
  }, [fetchConversations, user?.id]);

  // Fetch presence for online users
  useEffect(() => {
    if (!user?.id) return;
    const fetchPresence = async () => {
      try {
        await presenceApi.heartbeat(user.id);
        const res = await presenceApi.getOnlineUsers();
        const map = {};
        (res.data || []).forEach(u => { map[u.user_id] = u.status; });
        setPresenceMap(map);
      } catch (e) { console.warn(e.message || e); }
    };
    fetchPresence();
    const interval = setInterval(fetchPresence, 30000);
    return () => clearInterval(interval);
  }, [user?.id]);

  // Listen for WebSocket messages
  useEffect(() => {
    const unsub = addListener('chat_message', (data) => {
      if (data.conversation_id === selectedRoom?.id) {
        setMessages(prev => {
          if (prev.find(m => m.id === data.message.id)) return prev;
          return [...prev, data.message];
        });
        scrollToBottom();
        if (data.message.sender_id !== user?.id) {
          sendReadReceipt(data.conversation_id, data.message.id);
        }
      }
      setConversations(prev => prev.map(c => c.id === data.conversation_id ? { ...c, last_message: data.message.text?.slice(0, 100), updated_at: data.message.created_at } : c));
    });
    return unsub;
  }, [addListener, selectedRoom?.id, user?.id, sendReadReceipt]);

  // Listen for read receipts
  useEffect(() => {
    const unsub = addListener('read_receipt', (data) => {
      if (data.conversation_id === selectedRoom?.id) {
        setMessages(prev => prev.map(m => m.id === data.message_id ? { ...m, read_by: [...(m.read_by || []), data.user_id] } : m));
      }
    });
    return unsub;
  }, [addListener, selectedRoom?.id]);

  // Listen for message deletions
  useEffect(() => {
    const unsub = addListener('message_deleted', (data) => {
      if (data.conversation_id === selectedRoom?.id) {
        setMessages(prev => prev.filter(m => m.id !== data.message_id));
      }
    });
    return unsub;
  }, [addListener, selectedRoom?.id]);


  const selectRoom = async (room) => {
    setSelectedRoom(room);
    setReplyTo(null);
    if (room.id === '__ai__' || room.id === '__announcements__') return;
    try {
      const res = await chatApi.messages(room.id);
      setMessages(res.data || []);
      scrollToBottom();
      const unread = (res.data || []).filter(m => m.sender_id !== user?.id && !(m.read_by || []).includes(user?.id));
      if (unread.length > 0) sendReadReceipt(room.id, unread[unread.length - 1].id);
    } catch { toast.error('Failed to load messages'); }
  };

  const handleTyping = () => {
    if (!selectedRoom || selectedRoom.id.startsWith('__')) return;
    clearTimeout(typingTimeout.current);
    sendTyping(selectedRoom.id, selectedRoom.participants || []);
    typingTimeout.current = setTimeout(() => {}, 3000);
  };

  const handleSend = async () => {
    if (!newMsg.trim() || !selectedRoom) return;

    if (selectedRoom.id === '__ai__') {
      const userText = newMsg;
      setAiMessages(prev => [...prev, { role: 'user', text: userText }]);
      setNewMsg('');
      setSending(true);
      scrollToBottom();
      try {
        const res = await chatApi.aiAssistant(userText, aiSessionId);
        setAiMessages(prev => [...prev, { role: 'assistant', text: res.data.response }]);
        scrollToBottom();
      } catch {
        setAiMessages(prev => [...prev, { role: 'assistant', text: 'Sorry, I encountered an error. Please try again.' }]);
      }
      setSending(false);
      return;
    }

    if (selectedRoom.id === '__announcements__') {
      setShowNewAnnouncement(true);
      return;
    }

    sendChatMessage(selectedRoom.id, newMsg, user?.name, replyTo ? { id: replyTo.id, text: replyTo.text, sender_name: replyTo.sender_name } : null);
    setNewMsg('');
    setReplyTo(null);
    scrollToBottom();
  };

  const handlePostAnnouncement = async (e) => {
    e.preventDefault();
    try {
      const res = await api.post('/announcements', announcementForm);
      setAnnouncements(prev => [res.data, ...prev]);
      setShowNewAnnouncement(false);
      setAnnouncementForm({ title: '', content: '', type: 'general' });
      toast.success('Announcement posted!');
    } catch { toast.error('Failed to post announcement'); }
  };

  const handleCreateConv = async () => {
    try {
      const payload = { ...convForm };
      // Auto-name direct messages with the other person's name
      if (payload.type === 'direct' && payload.participants.length === 1 && !payload.name) {
        const other = allStaff.find(s => s.id === payload.participants[0]);
        payload.name = other?.name || 'Direct Message';
      }
      if (!payload.name && payload.type === 'group') { payload.name = 'Group Chat'; }
      const res = await chatApi.createConversation(payload);
      setConversations(prev => [res.data, ...prev]);
      setShowNewConv(false);
      setConvForm({ name: '', participants: [], type: 'direct' });
      selectRoom(res.data);
      toast.success('Conversation created');
    } catch { toast.error('Failed to create conversation'); }
  };

  const handleReaction = async (msgId, emoji) => {
    try {
      await reactionsApi.addReaction(msgId, emoji, user?.id);
      setMessages(prev => prev.map(m => {
        if (m.id !== msgId) return m;
        const reactions = [...(m.reactions || [])];
        const existing = reactions.findIndex(r => r.emoji === emoji && r.user_id === user?.id);
        if (existing >= 0) reactions.splice(existing, 1);
        else reactions.push({ emoji, user_id: user?.id, user_name: user?.name });
        return { ...m, reactions };
      }));
      setShowEmojiFor(null);
    } catch { toast.error('Failed to add reaction'); }
  };

  const handleSetMyStatus = async (status) => {
    try {
      await presenceApi.setStatus(user?.id, status);
      setMyStatus(status);
      toast.success(`Status set to ${PRESENCE_LABELS[status] || status}`);
    } catch { toast.error('Failed to update status'); }
  };

  const getUserPresence = (userId) => presenceMap[userId] || (onlineUsers.includes(userId) ? 'online' : 'offline');

  const handleDeleteConversation = async (convId) => {
    if (!window.confirm('Hide this conversation? It will be removed from your list only.')) return;
    try {
      await chatApi.deleteConversation(convId);
      setConversations(prev => prev.filter(c => c.id !== convId));
      if (selectedRoom?.id === convId) { setSelectedRoom(null); setMessages([]); }
      toast.success('Conversation hidden');
    } catch { toast.error('Failed'); }
  };

  const handleDeleteMessage = async (msgId) => {
    try {
      await chatApi.deleteMessage(msgId);
      setMessages(prev => prev.filter(m => m.id !== msgId));
      toast.success('Message deleted');
    } catch (err) { toast.error(err.response?.data?.detail || 'Cannot delete — already read'); }
  };

  const handleAddGroupMembers = async (userIds) => {
    if (!selectedRoom || selectedRoom.type !== 'group') return;
    try {
      const res = await chatApi.updateGroupMembers(selectedRoom.id, { add: userIds });
      setSelectedRoom(res.data);
      setConversations(prev => prev.map(c => c.id === selectedRoom.id ? res.data : c));
      setShowEditGroup(false);
      setGroupAddSearch('');
      toast.success('Members added');
    } catch { toast.error('Failed'); }
  };

  const handleRemoveGroupMember = async (userId) => {
    if (!selectedRoom || selectedRoom.type !== 'group') return;
    if (!window.confirm('Remove this member from the group?')) return;
    try {
      const res = await chatApi.updateGroupMembers(selectedRoom.id, { remove: [userId] });
      setSelectedRoom(res.data);
      setConversations(prev => prev.map(c => c.id === selectedRoom.id ? res.data : c));
      toast.success('Member removed');
    } catch { toast.error('Failed'); }
  };



  // Thread support
  const openThread = async (msg) => {
    setActiveThread(msg);
    try {
      const res = await chatApi.messages(msg.conversation_id, { thread_id: msg.id });
      setThreadMessages(res.data || []);
    } catch { setThreadMessages([]); }
  };

  const sendThreadMessage = async () => {
    if (!threadMsg.trim() || !activeThread) return;
    try {
      const res = await chatApi.sendMessage(activeThread.conversation_id, threadMsg, activeThread.id);
      setThreadMessages(prev => [...prev, res.data]);
      setThreadMsg('');
      // Update thread count in main messages
      setMessages(prev => prev.map(m => m.id === activeThread.id ? { ...m, thread_count: (m.thread_count || 0) + 1 } : m));
    } catch { toast.error('Failed to send'); }
  };

  // Conference scheduling
  const handleCreateConference = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        ...confForm,
        external_emails: confForm.external_emails ? confForm.external_emails.split(',').map(e => e.trim()).filter(Boolean) : [],
        scheduled_at: confForm.scheduled_at ? new Date(confForm.scheduled_at).toISOString() : null,
      };
      const res = await conferencesApi.create(payload, user?.id);
      toast.success(`Conference "${res.data.title}" created! Code: ${res.data.meeting_code}`);
      setShowConference(false);
      setConfForm({ title: '', description: '', scheduled_at: '', duration_minutes: 60, user_ids: [], external_emails: '', is_video_enabled: true, password: '', create_calendar_event: true, send_email_invites: true });
    } catch { toast.error('Failed to create conference'); }
  };

  const isAdmin = ['admin', 'system_admin', 'Executive Director', 'Director'].includes(user?.role);
  const isStaff = isAdmin || ['Manager', 'Coordinator', 'Staff'].includes(user?.role);
  const filteredConvs = conversations.filter(c => !searchQuery || c.name?.toLowerCase().includes(searchQuery.toLowerCase()));
  const currentTyping = selectedRoom ? typingUsers[selectedRoom.id] : null;
  const typingUserName = currentTyping ? allStaff.find(s => s.id === currentTyping.user_id)?.name?.split(' ')[0] || 'Someone' : null;

  const getReadStatus = (msg) => {
    if (msg.sender_id !== user?.id) return null;
    const readBy = (msg.read_by || []).filter(id => id !== user?.id);
    if (readBy.length > 0) return 'read';
    return 'sent';
  };

  const renderReactions = (msg) => {
    const reactions = msg.reactions || [];
    if (reactions.length === 0) return null;
    const grouped = {};
    reactions.forEach(r => {
      if (!grouped[r.emoji]) grouped[r.emoji] = { emoji: r.emoji, count: 0, mine: false };
      grouped[r.emoji].count++;
      if (r.user_id === user?.id) grouped[r.emoji].mine = true;
    });
    return (
      <div className="flex gap-1 mt-1 flex-wrap">
        {Object.values(grouped).map(r => (
          <button key={r.emoji} onClick={() => handleReaction(msg.id, r.emoji)}
            className={`text-xs px-1.5 py-0.5 rounded-full border transition-colors ${r.mine ? 'bg-primary/10 border-primary/30' : 'bg-muted/50 border-transparent hover:border-border'}`}>
            {r.emoji} {r.count > 1 && <span className="text-muted-foreground">{r.count}</span>}
          </button>
        ))}
      </div>
    );
  };

  const renderMessages = () => {
    if (!selectedRoom) {
      return (
        <div className="flex-1 flex items-center justify-center text-muted-foreground">
          <div className="text-center">
            <MessageSquare size={48} className="mx-auto mb-4 opacity-20" />
            <p className="text-sm font-medium">Select a conversation</p>
            <p className="text-xs mt-1">Choose a chat room or start a new conversation</p>
          </div>
        </div>
      );
    }

    if (selectedRoom.id === '__ai__') {
      return (
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {aiMessages.length === 0 && (
            <div className="text-center py-12 text-sm text-muted-foreground">
              <Bot size={40} className="mx-auto mb-3 opacity-20" />
              <p className="font-medium">AI Assistant</p>
              <p className="text-xs mt-1 mb-4">Powered by Gemini</p>
              <div className="flex flex-wrap gap-2 justify-center">
                {['How do I add a new member?', 'Help me plan an event', 'Summarize financial status'].map(q => (
                  <Button key={q} variant="outline" size="sm" className="text-xs h-7" onClick={() => setNewMsg(q)}>{q}</Button>
                ))}
              </div>
            </div>
          )}
          {aiMessages.map((msg, i) => (
            <div key={`ai-${i}-${msg.role}`} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 ${msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-secondary'}`}>
                {msg.role === 'assistant' && <p className="text-[10px] font-semibold opacity-60 mb-0.5">AI Assistant</p>}
                <p className="text-sm whitespace-pre-wrap">{msg.text}</p>
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="bg-secondary rounded-2xl px-4 py-3">
                <div className="flex gap-1.5">
                  <span className="h-2 w-2 bg-muted-foreground/40 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="h-2 w-2 bg-muted-foreground/40 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="h-2 w-2 bg-muted-foreground/40 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      );
    }

    if (selectedRoom.id === '__announcements__') {
      return (
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {announcements.length === 0 ? (
            <div className="text-center py-16 text-sm text-muted-foreground">
              <Megaphone size={40} className="mx-auto mb-3 opacity-20" />
              <p>No announcements yet.</p>
            </div>
          ) : announcements.map(a => (
            <div key={a.id} className="flex justify-start" data-testid="announcement-msg">
              <div className="max-w-[85%] bg-secondary rounded-2xl px-4 py-3">
                <div className="flex items-center gap-2 mb-1">
                  <p className="text-xs font-bold text-primary">{a.title}</p>
                  <Badge variant="outline" className="text-[10px] capitalize h-4">{a.type}</Badge>
                </div>
                <p className="text-sm">{a.content}</p>
                <p className="text-[10px] text-muted-foreground mt-1">{a.created_at?.slice(0, 10)}</p>
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      );
    }

    // Normal Chat with reply-to, read receipts, reactions
    return (
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <div className="text-center py-16 text-sm text-muted-foreground">
            <MessageSquare size={32} className="mx-auto mb-2 opacity-20" />
            <p>No messages yet. Say hello!</p>
          </div>
        )}
        {messages.map(msg => {
          const isMine = msg.sender_id === user?.id;
          const readStatus = getReadStatus(msg);
          const replyRef = msg.reply_to;
          return (
            <div key={msg.id} className={`flex ${isMine ? 'justify-end' : 'justify-start'} group`} data-testid={`chat-msg-${msg.id}`}>
              <div className={`max-w-[70%] rounded-2xl px-4 py-2 relative ${isMine ? 'bg-primary text-primary-foreground' : 'bg-secondary'}`}>
                {replyRef && (
                  <div className={`text-[10px] mb-1.5 px-2 py-1 rounded-lg border-l-2 ${isMine ? 'border-primary-foreground/40 bg-primary-foreground/10' : 'border-primary/40 bg-primary/5'}`}>
                    <p className="font-semibold opacity-70">{replyRef.sender_name}</p>
                    <p className="truncate opacity-60">{replyRef.text}</p>
                  </div>
                )}
                {!isMine && (
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <p className="text-[10px] font-semibold opacity-70">{msg.sender_name}</p>
                    <span className={`w-1.5 h-1.5 rounded-full ${PRESENCE_DOTS[getUserPresence(msg.sender_id)] || 'bg-gray-400'}`} />
                  </div>
                )}
                <p className="text-sm whitespace-pre-wrap">{msg.text}</p>
                <div className="flex items-center justify-end gap-1 mt-0.5">
                  <p className="text-[10px] opacity-50">{msg.created_at?.slice(11, 16)}</p>
                  {isMine && readStatus === 'read' && <CheckCheck size={12} className="opacity-70 text-blue-300" />}
                  {isMine && readStatus === 'sent' && <Check size={12} className="opacity-50" />}
                </div>
                {renderReactions(msg)}
                {/* Thread indicator */}
                {msg.thread_count > 0 && (
                  <button onClick={() => openThread(msg)} className="flex items-center gap-1.5 mt-1 text-[11px] text-primary hover:underline" data-testid={`thread-${msg.id}`}>
                    <MessageSquare size={11} /> {msg.thread_count} {msg.thread_count === 1 ? 'reply' : 'replies'}
                  </button>
                )}
                {/* Reply + Reaction + Thread buttons */}
                <div className="absolute -left-24 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
                  <button className="h-6 w-6 flex items-center justify-center rounded-full bg-secondary hover:bg-accent text-muted-foreground" onClick={() => setReplyTo(msg)} data-testid={`reply-btn-${msg.id}`}>
                    <Reply size={12} />
                  </button>
                  <button className="h-6 w-6 flex items-center justify-center rounded-full bg-secondary hover:bg-accent text-muted-foreground" onClick={() => openThread(msg)} title="Thread">
                    <MessageSquare size={12} />
                  </button>
                  {isMine && <button className="h-6 w-6 flex items-center justify-center rounded-full bg-secondary hover:bg-destructive/20 text-muted-foreground hover:text-destructive" onClick={() => handleDeleteMessage(msg.id)} title="Delete (before read)" data-testid={`delete-msg-${msg.id}`}>
                    <Trash2 size={11} />
                  </button>}
                  <Popover open={showEmojiFor === msg.id} onOpenChange={(open) => setShowEmojiFor(open ? msg.id : null)}>
                    <PopoverTrigger asChild>
                      <button className="h-6 w-6 flex items-center justify-center rounded-full bg-secondary hover:bg-accent text-muted-foreground" data-testid={`react-btn-${msg.id}`}>
                        <Smile size={12} />
                      </button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-2" side="top" align="start">
                      <div className="flex flex-wrap gap-1 max-w-[200px]">
                        {QUICK_EMOJIS.map(emoji => (
                          <button key={emoji} onClick={() => handleReaction(msg.id, emoji)} className="text-lg hover:scale-125 transition-transform p-0.5">{emoji}</button>
                        ))}
                      </div>
                    </PopoverContent>
                  </Popover>
                </div>
              </div>
            </div>
          );
        })}
        {typingUserName && (
          <div className="flex justify-start">
            <div className="bg-secondary rounded-2xl px-4 py-2">
              <p className="text-[11px] text-muted-foreground italic">{typingUserName} is typing...</p>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
    );
  };

  const getInputPlaceholder = () => {
    if (!selectedRoom) return '';
    if (selectedRoom.id === '__ai__') return 'Ask the AI assistant...';
    if (selectedRoom.id === '__announcements__') return 'Click to post an announcement...';
    return replyTo ? `Reply to ${replyTo.sender_name}...` : 'Type a message...';
  };

  const isInputDisabled = () => {
    if (!selectedRoom) return true;
    if (selectedRoom.id === '__announcements__' && !isAdmin) return true;
    return false;
  };

  return (
    <div className="p-6 h-[calc(100vh-4rem)]">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-semibold font-heading" data-testid="comms-title">Communications</h1>
          <p className="text-sm text-muted-foreground">Chat, AI assistant, announcements & calling</p>
        </div>
        {/* My status selector */}
        <div className="flex items-center gap-2">
          {isStaff && <Button size="sm" variant="outline" className="gap-1.5 text-xs h-8" onClick={() => setShowConference(true)} data-testid="schedule-conference-btn"><Video size={13} /> Conference</Button>}
          <Select value={myStatus} onValueChange={handleSetMyStatus}>
            <SelectTrigger className="w-[160px] h-8 text-xs" data-testid="my-status-select">
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${PRESENCE_DOTS[myStatus]}`} />
                <SelectValue />
              </div>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="online"><div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-green-500" /> Available</div></SelectItem>
              <SelectItem value="away"><div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-yellow-500" /> Away</div></SelectItem>
              <SelectItem value="dnd"><div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-red-600" /> Do Not Disturb</div></SelectItem>
              <SelectItem value="offline"><div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-red-500" /> Offline</div></SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex h-[calc(100%-3.5rem)] gap-0 border border-border rounded-xl overflow-hidden bg-card">
        {/* Sidebar */}
        <div className="w-72 border-r border-border flex flex-col shrink-0">
          <div className="p-3 border-b border-border space-y-2">
            <div className="relative">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input className="pl-8 h-8 text-xs" placeholder="Search chats..." value={searchQuery} onChange={e => setSearchQuery(e.target.value)} />
            </div>
            <Button className="w-full gap-2 h-8 text-xs" size="sm" onClick={() => setShowNewConv(true)} data-testid="new-conversation-btn">
              <Plus size={13} /> New Conversation
            </Button>
          </div>

          <div className="border-b border-border">
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest px-3 pt-2.5 pb-1">Pinned</p>
            <SidebarItem room={AI_ROOM} selected={selectedRoom?.id === '__ai__'} icon={<Bot size={14} className="text-primary" />} subtitle="Powered by Gemini" onClick={() => selectRoom(AI_ROOM)} />
            <SidebarItem room={ANNOUNCE_ROOM} selected={selectedRoom?.id === '__announcements__'} icon={<Megaphone size={14} className="text-amber-600" />} subtitle={`${announcements.length} announcements`} badge={announcements.length > 0 ? announcements.length : null} onClick={() => selectRoom(ANNOUNCE_ROOM)} />
          </div>

          {/* Org Chart - Staff by Role */}
          <div className="border-b border-border">
            <button onClick={() => setShowOrgChart(!showOrgChart)} className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest px-3 pt-2.5 pb-1 flex items-center gap-1 w-full hover:text-foreground">
              <ChevronRight size={10} className={`transition-transform ${showOrgChart ? 'rotate-90' : ''}`} /> Organization
            </button>
            {showOrgChart && (
              <div className="px-2 pb-2 space-y-0.5 max-h-48 overflow-y-auto">
                {ORG_ROLES.map(role => {
                  const roleStaff = allStaff.filter(s => s.role === role);
                  if (roleStaff.length === 0) return null;
                  return (
                    <div key={role}>
                      <p className="text-[9px] text-muted-foreground/60 uppercase px-2 pt-1">{role}s</p>
                      {roleStaff.map(s => (
                        <div key={s.id} className="flex items-center gap-2 px-2 py-1 rounded hover:bg-accent/30 cursor-pointer text-xs" onClick={async () => {
                          const existing = conversations.find(c => c.type === 'direct' && c.participants?.includes(s.id));
                          if (existing) { selectRoom(existing); return; }
                          try {
                            const res = await chatApi.createConversation({ name: s.name, participants: [s.id, user?.id], type: 'direct' });
                            setConversations(prev => [res.data, ...prev]);
                            selectRoom(res.data);
                          } catch { toast.error('Failed to start conversation'); }
                        }}>
                          <span className={`w-1.5 h-1.5 rounded-full ${PRESENCE_DOTS[getUserPresence(s.id)] || 'bg-gray-400'}`} />
                          <span className="truncate">{s.name}</span>
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="overflow-y-auto flex-1">
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest px-3 pt-2.5 pb-1">Conversations</p>
            {loading ? (
              <div className="p-3 space-y-2">{[1,2,3].map(i => <div key={i} className="h-12 bg-muted animate-pulse rounded" />)}</div>
            ) : filteredConvs.length === 0 ? (
              <p className="text-[11px] text-muted-foreground text-center py-6">No conversations yet</p>
            ) : filteredConvs.map(conv => {
              // Get presence for participants (direct messages)
              const otherParticipant = conv.type === 'direct' ? conv.participants?.find(p => p !== user?.id) : null;
              const otherPresence = otherParticipant ? getUserPresence(otherParticipant) : null;
              return (
                <SidebarItem
                  key={conv.id} room={conv} selected={selectedRoom?.id === conv.id}
                  icon={<div className="relative">
                    {conv.type === 'group' ? <Users size={14} className="text-blue-500" /> : <Hash size={14} className="text-muted-foreground" />}
                    {otherPresence && (
                      <span className={`absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full border border-card ${PRESENCE_DOTS[otherPresence] || 'bg-gray-400'}`} />
                    )}
                  </div>}
                  subtitle={typingUsers[conv.id] ? <span className="italic text-primary">typing...</span> : (conv.last_message || 'No messages')}
                  onClick={() => selectRoom(conv)}
                  onDelete={() => handleDeleteConversation(conv.id)}
                />
              );
            })}
          </div>

          {/* Online count */}
          <div className="p-3 border-t border-border">
            <p className="text-[10px] text-muted-foreground flex items-center gap-1.5">
              <Circle size={6} className="fill-green-500 text-green-500" /> {Object.keys(presenceMap).length || onlineUsers.length} online
            </p>
          </div>
        </div>

        {/* Main chat area */}
        <div className="flex-1 flex flex-col min-w-0">
          {selectedRoom && (
            <div className="p-3 border-b border-border flex items-center gap-3 shrink-0">
              <div className="p-1.5 rounded-lg bg-secondary">
                {selectedRoom.id === '__ai__' ? <Bot size={16} className="text-primary" /> :
                 selectedRoom.id === '__announcements__' ? <Megaphone size={16} className="text-amber-600" /> :
                 selectedRoom.type === 'group' ? <Users size={16} className="text-blue-500" /> :
                 <MessageSquare size={16} className="text-muted-foreground" />}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold truncate">{selectedRoom.name || 'Chat'}</p>
                <p className="text-xs text-muted-foreground">
                  {selectedRoom.id === '__ai__' ? 'Gemini AI' :
                   selectedRoom.id === '__announcements__' ? 'No-reply channel' :
                   currentTyping ? <span className="text-primary italic">{typingUserName} is typing...</span> :
                   `${selectedRoom.participants?.length || 0} participants`}
                </p>
              </div>
              {/* Call buttons for staff conversations */}
              {isStaff && selectedRoom.id !== '__ai__' && selectedRoom.id !== '__announcements__' && (
                <div className="flex items-center gap-1">
                  <Button size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground hover:text-green-600" data-testid="voice-call-btn"
                    onClick={() => {
                      const otherUser = selectedRoom.participants?.find(p => p !== user?.id);
                      if (otherUser) { initiateCall(otherUser, 'audio'); }
                      else { toast.error('No user to call'); }
                    }}>
                    <Phone size={15} />
                  </Button>
                  <Button size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground hover:text-blue-600" data-testid="video-call-btn"
                    onClick={() => {
                      const otherUser = selectedRoom.participants?.find(p => p !== user?.id);
                      if (otherUser) { initiateCall(otherUser, 'video'); }
                      else { toast.error('No user to call'); }
                    }}>
                    <Video size={15} />
                  </Button>
                </div>
              )}
              {selectedRoom.id === '__announcements__' && isAdmin && (
                <Button size="sm" variant="outline" className="gap-1.5 text-xs h-7" onClick={() => setShowNewAnnouncement(true)} data-testid="post-announcement-btn">
                  <Plus size={12} /> Post
                </Button>
              )}
              {selectedRoom.type === 'group' && !selectedRoom.id.startsWith('__') && (
                <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setShowEditGroup(true)} title="Edit Group" data-testid="edit-group-btn"><Settings size={14} /></Button>
              )}
            </div>
          )}

          {renderMessages()}

          {/* Reply Preview */}
          {replyTo && (
            <div className="px-3 pt-2 flex items-center gap-2 border-t border-border bg-secondary/30">
              <Reply size={14} className="text-primary shrink-0" />
              <div className="flex-1 min-w-0 text-xs">
                <p className="font-semibold text-primary">{replyTo.sender_name}</p>
                <p className="truncate text-muted-foreground">{replyTo.text}</p>
              </div>
              <button onClick={() => setReplyTo(null)} className="shrink-0 text-muted-foreground hover:text-foreground"><X size={14} /></button>
            </div>
          )}

          {/* Input */}
          {selectedRoom && !isInputDisabled() && !(selectedRoom.id === '__announcements__' && !isAdmin) && (
            <div className="p-3 border-t border-border flex gap-2 shrink-0">
              <Input className="flex-1" placeholder={getInputPlaceholder()} value={newMsg}
                onChange={e => { setNewMsg(e.target.value); handleTyping(); }}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                onClick={() => { if (selectedRoom.id === '__announcements__') setShowNewAnnouncement(true); }}
                readOnly={selectedRoom.id === '__announcements__'}
                data-testid="chat-input" />
              <Button onClick={handleSend} disabled={sending || (!newMsg.trim() && selectedRoom.id !== '__announcements__')} size="icon" data-testid="send-message-btn">
                <Send size={16} />
              </Button>
            </div>
          )}
          {selectedRoom?.id === '__announcements__' && !isAdmin && (
            <div className="p-3 border-t border-border text-center">
              <p className="text-xs text-muted-foreground">This is a no-reply announcements channel</p>
            </div>
          )}
        </div>

        {/* Thread Panel (slide-out) */}
        {activeThread && (
          <div className="w-80 border-l border-border flex flex-col shrink-0 bg-card" data-testid="thread-panel">
            <div className="p-3 border-b border-border flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold">Thread</p>
                <p className="text-[11px] text-muted-foreground truncate">{activeThread.sender_name}: {activeThread.text?.slice(0, 40)}...</p>
              </div>
              <button onClick={() => setActiveThread(null)} className="text-muted-foreground hover:text-foreground"><X size={16} /></button>
            </div>
            {/* Original message */}
            <div className="p-3 border-b border-border bg-secondary/30">
              <p className="text-[10px] font-semibold text-muted-foreground">{activeThread.sender_name}</p>
              <p className="text-sm">{activeThread.text}</p>
              <p className="text-[10px] text-muted-foreground mt-1">{activeThread.created_at?.slice(0, 16).replace('T', ' ')}</p>
            </div>
            {/* Thread replies */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {threadMessages.length === 0 && <p className="text-xs text-muted-foreground text-center py-4">No replies yet</p>}
              {threadMessages.map(tm => (
                <div key={tm.id} className={`flex ${tm.sender_id === user?.id ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] rounded-xl px-3 py-1.5 ${tm.sender_id === user?.id ? 'bg-primary text-primary-foreground' : 'bg-secondary'}`}>
                    {tm.sender_id !== user?.id && <p className="text-[10px] font-semibold opacity-70">{tm.sender_name}</p>}
                    <p className="text-xs">{tm.text}</p>
                    <p className="text-[9px] opacity-50 mt-0.5 text-right">{tm.created_at?.slice(11, 16)}</p>
                  </div>
                </div>
              ))}
            </div>
            {/* Thread input */}
            <div className="p-2 border-t border-border flex gap-2">
              <Input className="flex-1 text-xs h-8" placeholder="Reply in thread..." value={threadMsg} onChange={e => setThreadMsg(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); sendThreadMessage(); } }} data-testid="thread-input" />
              <Button size="icon" className="h-8 w-8" onClick={sendThreadMessage} disabled={!threadMsg.trim()} data-testid="thread-send-btn"><Send size={14} /></Button>
            </div>
          </div>
        )}
      </div>

      {/* Schedule Conference Dialog */}
      <ConferenceDialog
        open={showConference}
        onOpenChange={setShowConference}
        confForm={confForm}
        setConfForm={setConfForm}
        allStaff={allStaff}
        userId={user?.id}
        onSubmit={handleCreateConference}
      />

      {/* New Conversation Dialog */}
      <NewConversationDialog
        open={showNewConv}
        onOpenChange={setShowNewConv}
        convForm={convForm}
        setConvForm={setConvForm}
        allStaff={allStaff}
        userId={user?.id}
        getUserPresence={getUserPresence}
        PRESENCE_DOTS={PRESENCE_DOTS}
        onCreateConv={handleCreateConv}
      />

      {/* Post Announcement Dialog */}
      <AnnouncementDialog
        open={showNewAnnouncement}
        onOpenChange={setShowNewAnnouncement}
        form={announcementForm}
        setForm={setAnnouncementForm}
        onSubmit={handlePostAnnouncement}
      />

      {/* Edit Group Dialog */}
      <Dialog open={showEditGroup} onOpenChange={setShowEditGroup}>
        <DialogContent className="max-w-md max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Edit Group: {selectedRoom?.name}</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <p className="text-xs font-semibold text-muted-foreground uppercase">Members ({selectedRoom?.participants?.length || 0})</p>
            <div className="space-y-1 max-h-40 overflow-auto">
              {(selectedRoom?.participants || []).map(pid => {
                const s = allStaff.find(x => x.id === pid);
                return (
                  <div key={pid} className="flex items-center justify-between p-2 rounded-lg hover:bg-accent/30 text-sm">
                    <span>{s?.name || pid} {pid === user?.id && <span className="text-xs text-muted-foreground">(you)</span>}</span>
                    {pid !== user?.id && <button className="text-xs text-destructive hover:underline" onClick={() => handleRemoveGroupMember(pid)}>Remove</button>}
                  </div>
                );
              })}
            </div>
            <div className="border-t pt-3 space-y-2">
              <p className="text-xs font-semibold text-muted-foreground">Add Members</p>
              <Input placeholder="Search staff..." value={groupAddSearch} onChange={e => setGroupAddSearch(e.target.value)} className="h-8 text-sm" data-testid="group-add-search" />
              {groupAddSearch.trim().length >= 2 && (
                <div className="max-h-32 overflow-auto border rounded-lg p-1 space-y-0.5">
                  {allStaff.filter(s => s.id !== user?.id && !(selectedRoom?.participants || []).includes(s.id) && s.name?.toLowerCase().includes(groupAddSearch.toLowerCase())).slice(0, 10).map(s => (
                    <button key={s.id} className="w-full text-left p-2 rounded hover:bg-accent/50 text-sm" onClick={() => handleAddGroupMembers([s.id])}>{s.name} ({s.role})</button>
                  ))}
                </div>
              )}
            </div>
            <Button variant="outline" className="w-full" onClick={() => setShowEditGroup(false)}>Close</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SidebarItem({ room, selected, icon, subtitle, badge, onClick, onDelete }) {
  return (
    <div
      className={`px-3 py-2.5 cursor-pointer transition-colors flex items-center gap-2.5 hover:bg-accent/50 group ${selected ? 'bg-accent' : ''}`}
      onClick={onClick} data-testid="sidebar-chat-item"
    >
      <div className="p-1.5 rounded-lg bg-secondary shrink-0">{icon}</div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{room.name}</p>
        <p className="text-[11px] text-muted-foreground truncate">{subtitle}</p>
      </div>
      {badge && <Badge variant="secondary" className="text-[10px] h-5 px-1.5 shrink-0">{badge}</Badge>}
      {onDelete && <button className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive p-0.5 shrink-0" onClick={e => { e.stopPropagation(); onDelete(); }} data-testid="delete-conv-btn"><X size={12} /></button>}
    </div>
  );
}
