import React, { useState, useEffect, useRef, useCallback } from 'react';
import { MessageSquare, Plus, Send, Bot, Megaphone, Users, Search, Hash } from 'lucide-react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Avatar, AvatarFallback } from '../components/ui/avatar';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Textarea } from '../components/ui/textarea';
import { chatApi, membersApi } from '../services/api';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

const initials = (name) => (name || '?').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();

// Static pinned rooms
const AI_ROOM = { id: '__ai__', name: 'AI Assistant', type: 'ai_assistant', icon: 'bot' };
const ANNOUNCE_ROOM = { id: '__announcements__', name: 'Announcements', type: 'announcements', icon: 'megaphone', is_no_reply: true };

export default function CommsPage() {
  const { user } = useAuth();
  const [conversations, setConversations] = useState([]);
  const [selectedRoom, setSelectedRoom] = useState(null);
  const [messages, setMessages] = useState([]);
  const [newMsg, setNewMsg] = useState('');
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  // AI state
  const [aiMessages, setAiMessages] = useState([]);
  const [aiSessionId] = useState(() => `ai_${user?.id || 'anon'}_${Date.now()}`);

  // Announcements
  const [announcements, setAnnouncements] = useState([]);
  const [showNewAnnouncement, setShowNewAnnouncement] = useState(false);
  const [announcementForm, setAnnouncementForm] = useState({ title: '', content: '', type: 'general' });

  // New conversation
  const [showNewConv, setShowNewConv] = useState(false);
  const [allStaff, setAllStaff] = useState([]);
  const [convForm, setConvForm] = useState({ name: '', participants: [], type: 'direct' });

  const messagesEndRef = useRef(null);
  const scrollToBottom = () => setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);

  const fetchConversations = useCallback(async () => {
    try {
      const res = await chatApi.conversations();
      setConversations(res.data || []);
    } catch {}
  }, []);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await fetchConversations();
      try {
        const [annRes, staffRes] = await Promise.all([
          api.get('/announcements'),
          membersApi.list({ limit: 200 }),
        ]);
        setAnnouncements(annRes.data || []);
        setAllStaff(staffRes.data?.members || staffRes.data || []);
      } catch {}
      // Load AI history
      try {
        const aiRes = await chatApi.messages(`ai_${user?.id}`, { limit: 50 });
        setAiMessages((aiRes.data || []).map(m => ({ role: m.type === 'ai' ? 'assistant' : 'user', text: m.text })));
      } catch {}
      setLoading(false);
    };
    load();
  }, [fetchConversations, user?.id]);

  const selectRoom = async (room) => {
    setSelectedRoom(room);
    if (room.id === '__ai__') return; // AI messages managed in-memory
    if (room.id === '__announcements__') return; // announcements already loaded
    try {
      const res = await chatApi.messages(room.id);
      setMessages(res.data || []);
      scrollToBottom();
    } catch { toast.error('Failed to load messages'); }
  };

  const handleSend = async () => {
    if (!newMsg.trim() || !selectedRoom) return;

    // AI Assistant
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

    // Announcements
    if (selectedRoom.id === '__announcements__') {
      setShowNewAnnouncement(true);
      return;
    }

    // Normal chat
    setSending(true);
    try {
      const res = await chatApi.sendMessage(selectedRoom.id, newMsg);
      setMessages(prev => [...prev, res.data]);
      setNewMsg('');
      scrollToBottom();
      fetchConversations(); // update last_message in sidebar
    } catch { toast.error('Failed to send'); }
    finally { setSending(false); }
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
      const res = await chatApi.createConversation(convForm);
      setConversations(prev => [res.data, ...prev]);
      setShowNewConv(false);
      setConvForm({ name: '', participants: [], type: 'direct' });
      selectRoom(res.data);
      toast.success('Conversation created');
    } catch { toast.error('Failed to create conversation'); }
  };

  const isAdmin = ['admin', 'system_admin', 'Executive Director', 'Director'].includes(user?.role);
  const filteredConvs = conversations.filter(c => !searchQuery || c.name?.toLowerCase().includes(searchQuery.toLowerCase()));

  // Render the right pane content based on selected room
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

    // AI Room
    if (selectedRoom.id === '__ai__') {
      return (
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {aiMessages.length === 0 && (
            <div className="text-center py-12 text-sm text-muted-foreground">
              <Bot size={40} className="mx-auto mb-3 opacity-20" />
              <p className="font-medium">AI Assistant</p>
              <p className="text-xs mt-1 mb-4">Powered by Gemini — ask anything about your organization</p>
              <div className="flex flex-wrap gap-2 justify-center">
                {['How do I add a new member?', 'Help me plan an event', 'Summarize financial status'].map(q => (
                  <Button key={q} variant="outline" size="sm" className="text-xs h-7" onClick={() => setNewMsg(q)}>{q}</Button>
                ))}
              </div>
            </div>
          )}
          {aiMessages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
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

    // Announcements Room
    if (selectedRoom.id === '__announcements__') {
      return (
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {announcements.length === 0 ? (
            <div className="text-center py-16 text-sm text-muted-foreground">
              <Megaphone size={40} className="mx-auto mb-3 opacity-20" />
              <p>No announcements yet.</p>
            </div>
          ) : (
            announcements.map(a => (
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
            ))
          )}
          <div ref={messagesEndRef} />
        </div>
      );
    }

    // Normal Chat
    return (
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <div className="text-center py-16 text-sm text-muted-foreground">
            <MessageSquare size={32} className="mx-auto mb-2 opacity-20" />
            <p>No messages yet. Say hello!</p>
          </div>
        )}
        {messages.map(msg => (
          <div key={msg.id} className={`flex ${msg.sender_id === user?.id ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[70%] rounded-2xl px-4 py-2 ${msg.sender_id === user?.id ? 'bg-primary text-primary-foreground' : 'bg-secondary'}`}>
              {msg.sender_id !== user?.id && <p className="text-[10px] font-semibold opacity-70 mb-0.5">{msg.sender_name}</p>}
              <p className="text-sm">{msg.text}</p>
              <p className="text-[10px] opacity-50 mt-0.5">{msg.created_at?.slice(11, 16)}</p>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
    );
  };

  const getInputPlaceholder = () => {
    if (!selectedRoom) return '';
    if (selectedRoom.id === '__ai__') return 'Ask the AI assistant...';
    if (selectedRoom.id === '__announcements__') return 'Click to post an announcement...';
    return 'Type a message...';
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
          <p className="text-sm text-muted-foreground">Chat, AI assistant & announcements</p>
        </div>
      </div>

      <div className="flex h-[calc(100%-3.5rem)] gap-0 border border-border rounded-xl overflow-hidden bg-card">
        {/* Sidebar */}
        <div className="w-72 border-r border-border flex flex-col shrink-0">
          {/* Search + New */}
          <div className="p-3 border-b border-border space-y-2">
            <div className="relative">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input className="pl-8 h-8 text-xs" placeholder="Search chats..." value={searchQuery} onChange={e => setSearchQuery(e.target.value)} />
            </div>
            <Button className="w-full gap-2 h-8 text-xs" size="sm" onClick={() => setShowNewConv(true)} data-testid="new-conversation-btn">
              <Plus size={13} /> New Conversation
            </Button>
          </div>

          {/* Pinned rooms */}
          <div className="border-b border-border">
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest px-3 pt-2.5 pb-1">Pinned</p>
            <SidebarItem
              room={AI_ROOM} selected={selectedRoom?.id === '__ai__'}
              icon={<Bot size={14} className="text-primary" />}
              subtitle="Powered by Gemini"
              onClick={() => selectRoom(AI_ROOM)}
            />
            <SidebarItem
              room={ANNOUNCE_ROOM} selected={selectedRoom?.id === '__announcements__'}
              icon={<Megaphone size={14} className="text-amber-600" />}
              subtitle={`${announcements.length} announcements`}
              badge={announcements.length > 0 ? announcements.length : null}
              onClick={() => selectRoom(ANNOUNCE_ROOM)}
            />
          </div>

          {/* Conversations */}
          <div className="overflow-y-auto flex-1">
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest px-3 pt-2.5 pb-1">Conversations</p>
            {loading ? (
              <div className="p-3 space-y-2">{[1,2,3].map(i => <div key={i} className="h-12 bg-muted animate-pulse rounded" />)}</div>
            ) : filteredConvs.length === 0 ? (
              <p className="text-[11px] text-muted-foreground text-center py-6">No conversations yet</p>
            ) : (
              filteredConvs.map(conv => (
                <SidebarItem
                  key={conv.id}
                  room={conv} selected={selectedRoom?.id === conv.id}
                  icon={conv.type === 'group' ? <Users size={14} className="text-blue-500" /> : <Hash size={14} className="text-muted-foreground" />}
                  subtitle={conv.last_message || 'No messages'}
                  onClick={() => selectRoom(conv)}
                />
              ))
            )}
          </div>
        </div>

        {/* Main chat area */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Header */}
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
                  {selectedRoom.id === '__ai__' ? 'Gemini AI — ask anything' :
                   selectedRoom.id === '__announcements__' ? 'No-reply channel' :
                   `${selectedRoom.participants?.length || 0} participants`}
                </p>
              </div>
              {selectedRoom.id === '__announcements__' && isAdmin && (
                <Button size="sm" variant="outline" className="gap-1.5 text-xs h-7" onClick={() => setShowNewAnnouncement(true)} data-testid="post-announcement-btn">
                  <Plus size={12} /> Post
                </Button>
              )}
            </div>
          )}

          {/* Messages */}
          {renderMessages()}

          {/* Input */}
          {selectedRoom && !isInputDisabled() && !(selectedRoom.id === '__announcements__' && !isAdmin) && (
            <div className="p-3 border-t border-border flex gap-2 shrink-0">
              <Input className="flex-1" placeholder={getInputPlaceholder()} value={newMsg}
                onChange={e => setNewMsg(e.target.value)}
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
      </div>

      {/* New Conversation Dialog */}
      <Dialog open={showNewConv} onOpenChange={setShowNewConv}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New Conversation</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Name *</Label>
              <Input placeholder="e.g. Entebbe Team" value={convForm.name} onChange={e => setConvForm({...convForm, name: e.target.value})} data-testid="conv-name-input" />
            </div>
            <div className="space-y-2"><Label>Type</Label>
              <Select value={convForm.type} onValueChange={v => setConvForm({...convForm, type: v})}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="direct">Direct Message</SelectItem>
                  <SelectItem value="group">Group Chat</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2"><Label>Add Participants</Label>
              <Select onValueChange={v => {
                if (!convForm.participants.includes(v)) setConvForm({...convForm, participants: [...convForm.participants, v]});
              }}>
                <SelectTrigger><SelectValue placeholder="Select staff..." /></SelectTrigger>
                <SelectContent>
                  {allStaff.filter(s => s.id !== user?.id).map(s => (
                    <SelectItem key={s.id} value={s.id}>{s.name} ({s.role})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="flex flex-wrap gap-1 mt-1">
                {convForm.participants.map(pid => {
                  const staff = allStaff.find(s => s.id === pid);
                  return (
                    <Badge key={pid} variant="secondary" className="text-xs gap-1 cursor-pointer" onClick={() => setConvForm({...convForm, participants: convForm.participants.filter(p => p !== pid)})}>
                      {staff?.name || pid} &times;
                    </Badge>
                  );
                })}
              </div>
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowNewConv(false)}>Cancel</Button>
              <Button className="flex-1" disabled={!convForm.name} onClick={handleCreateConv} data-testid="create-conv-btn">Create</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Post Announcement Dialog */}
      <Dialog open={showNewAnnouncement} onOpenChange={setShowNewAnnouncement}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Post Announcement</DialogTitle></DialogHeader>
          <form onSubmit={handlePostAnnouncement} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Title *</Label>
              <Input placeholder="Announcement title" value={announcementForm.title} onChange={e => setAnnouncementForm({...announcementForm, title: e.target.value})} required data-testid="announcement-title-input" />
            </div>
            <div className="space-y-2"><Label>Content *</Label>
              <Textarea rows={4} placeholder="Write your announcement..." value={announcementForm.content} onChange={e => setAnnouncementForm({...announcementForm, content: e.target.value})} required data-testid="announcement-content-input" />
            </div>
            <div className="space-y-2"><Label>Type</Label>
              <Select value={announcementForm.type} onValueChange={v => setAnnouncementForm({...announcementForm, type: v})}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="general">General</SelectItem>
                  <SelectItem value="urgent">Urgent</SelectItem>
                  <SelectItem value="event">Event</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowNewAnnouncement(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" data-testid="post-announcement-submit">Post</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SidebarItem({ room, selected, icon, subtitle, badge, onClick }) {
  return (
    <div
      className={`px-3 py-2.5 cursor-pointer transition-colors flex items-center gap-2.5 hover:bg-accent/50 ${selected ? 'bg-accent' : ''}`}
      onClick={onClick} data-testid="sidebar-chat-item"
    >
      <div className="p-1.5 rounded-lg bg-secondary shrink-0">{icon}</div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{room.name}</p>
        <p className="text-[11px] text-muted-foreground truncate">{subtitle}</p>
      </div>
      {badge && <Badge variant="secondary" className="text-[10px] h-5 px-1.5 shrink-0">{badge}</Badge>}
    </div>
  );
}
