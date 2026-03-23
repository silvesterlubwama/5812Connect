import React, { useState, useEffect, useRef, useCallback } from 'react';
import { MessageSquare, Plus, Send, Bot, Megaphone, Users, Search } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Avatar, AvatarFallback } from '../components/ui/avatar';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Textarea } from '../components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { chatApi, membersApi, locationsApi } from '../services/api';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

const initials = (name) => (name || '?').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();

export default function CommsPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState('chat');
  const [conversations, setConversations] = useState([]);
  const [selectedConv, setSelectedConv] = useState(null);
  const [messages, setMessages] = useState([]);
  const [newMsg, setNewMsg] = useState('');
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);

  // AI Assistant state
  const [aiMessages, setAiMessages] = useState([]);
  const [aiInput, setAiInput] = useState('');
  const [aiSending, setAiSending] = useState(false);
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
  const aiEndRef = useRef(null);

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

  const selectConversation = async (conv) => {
    setSelectedConv(conv);
    try {
      const res = await chatApi.messages(conv.id);
      setMessages(res.data || []);
      setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    } catch { toast.error('Failed to load messages'); }
  };

  const handleSend = async () => {
    if (!newMsg.trim() || !selectedConv) return;
    setSending(true);
    try {
      const res = await chatApi.sendMessage(selectedConv.id, newMsg);
      setMessages(prev => [...prev, res.data]);
      setNewMsg('');
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    } catch { toast.error('Failed to send'); }
    finally { setSending(false); }
  };

  const handleAiSend = async () => {
    if (!aiInput.trim()) return;
    const userMsg = aiInput;
    setAiMessages(prev => [...prev, { role: 'user', text: userMsg }]);
    setAiInput('');
    setAiSending(true);
    try {
      const res = await chatApi.aiAssistant(userMsg, aiSessionId);
      setAiMessages(prev => [...prev, { role: 'assistant', text: res.data.response }]);
      setTimeout(() => aiEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    } catch {
      setAiMessages(prev => [...prev, { role: 'assistant', text: 'Sorry, I encountered an error. Please try again.' }]);
    }
    finally { setAiSending(false); }
  };

  const handleCreateConv = async () => {
    try {
      const res = await chatApi.createConversation(convForm);
      setConversations(prev => [res.data, ...prev]);
      setShowNewConv(false);
      setConvForm({ name: '', participants: [], type: 'direct' });
      setSelectedConv(res.data);
      setMessages([]);
      toast.success('Conversation created');
    } catch { toast.error('Failed to create conversation'); }
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

  const isAdmin = ['admin', 'system_admin'].includes(user?.role);

  return (
    <div className="p-6 h-[calc(100vh-4rem)]">
      <Tabs value={tab} onValueChange={setTab} className="h-full flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-semibold font-heading" data-testid="comms-title">Communications</h1>
            <p className="text-sm text-muted-foreground">Chat, AI assistant, and announcements</p>
          </div>
          <TabsList>
            <TabsTrigger value="chat" data-testid="tab-chat"><MessageSquare size={14} className="mr-1" />Chat</TabsTrigger>
            <TabsTrigger value="ai" data-testid="tab-ai"><Bot size={14} className="mr-1" />AI Assistant</TabsTrigger>
            <TabsTrigger value="announcements" data-testid="tab-announcements"><Megaphone size={14} className="mr-1" />Announcements</TabsTrigger>
          </TabsList>
        </div>

        {/* Chat Tab */}
        <TabsContent value="chat" className="flex-1 min-h-0">
          <div className="flex h-full gap-4 border border-border rounded-xl overflow-hidden bg-card">
            {/* Sidebar */}
            <div className="w-72 border-r border-border flex flex-col shrink-0">
              <div className="p-3 border-b border-border">
                <Button className="w-full gap-2" size="sm" onClick={() => setShowNewConv(true)} data-testid="new-conversation-btn">
                  <Plus size={14} /> New Conversation
                </Button>
              </div>
              <div className="overflow-y-auto flex-1">
                {loading ? (
                  <div className="p-3 space-y-2">{[1,2,3].map(i => <div key={i} className="h-14 bg-muted animate-pulse rounded" />)}</div>
                ) : conversations.length === 0 ? (
                  <p className="text-xs text-muted-foreground text-center py-8">No conversations yet</p>
                ) : (
                  conversations.map(conv => (
                    <div key={conv.id}
                      className={`p-3 border-b border-border cursor-pointer hover:bg-accent/50 transition-colors ${selectedConv?.id === conv.id ? 'bg-accent' : ''}`}
                      onClick={() => selectConversation(conv)} data-testid="conversation-item">
                      <div className="flex items-center gap-2">
                        <Avatar className="h-8 w-8">
                          <AvatarFallback className="text-xs bg-primary/10 text-primary">
                            {conv.type === 'group' ? <Users size={12} /> : initials(conv.name)}
                          </AvatarFallback>
                        </Avatar>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">{conv.name || 'Chat'}</p>
                          <p className="text-xs text-muted-foreground truncate">{conv.last_message || 'No messages'}</p>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Messages area */}
            <div className="flex-1 flex flex-col min-w-0">
              {selectedConv ? (
                <>
                  <div className="p-3 border-b border-border flex items-center gap-3">
                    <Avatar className="h-8 w-8"><AvatarFallback className="text-xs bg-primary/10 text-primary">{initials(selectedConv.name)}</AvatarFallback></Avatar>
                    <div>
                      <p className="text-sm font-semibold">{selectedConv.name || 'Chat'}</p>
                      <p className="text-xs text-muted-foreground">{selectedConv.participants?.length || 0} participants · {selectedConv.type}</p>
                    </div>
                  </div>
                  <div className="flex-1 overflow-y-auto p-4 space-y-3">
                    {messages.map(msg => (
                      <div key={msg.id} className={`flex ${msg.sender_id === user?.id ? 'justify-end' : 'justify-start'}`}>
                        <div className={`max-w-[70%] rounded-2xl px-4 py-2 ${msg.sender_id === user?.id ? 'bg-primary text-primary-foreground' : 'bg-secondary'}`}>
                          {msg.sender_id !== user?.id && <p className="text-xs font-semibold mb-0.5 opacity-75">{msg.sender_name}</p>}
                          <p className="text-sm">{msg.text}</p>
                          <p className="text-[10px] opacity-60 mt-0.5">{msg.created_at?.slice(11, 16)}</p>
                        </div>
                      </div>
                    ))}
                    <div ref={messagesEndRef} />
                  </div>
                  {!selectedConv.is_no_reply && (
                    <div className="p-3 border-t border-border flex gap-2">
                      <Input className="flex-1" placeholder="Type a message..." value={newMsg}
                        onChange={e => setNewMsg(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                        data-testid="chat-input" />
                      <Button onClick={handleSend} disabled={sending || !newMsg.trim()} data-testid="send-message-btn">
                        <Send size={16} />
                      </Button>
                    </div>
                  )}
                </>
              ) : (
                <div className="flex-1 flex items-center justify-center text-muted-foreground">
                  <div className="text-center">
                    <MessageSquare size={40} className="mx-auto mb-3 opacity-30" />
                    <p className="text-sm">Select a conversation to start chatting</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </TabsContent>

        {/* AI Assistant Tab */}
        <TabsContent value="ai" className="flex-1 min-h-0">
          <Card className="h-full flex flex-col shadow-soft rounded-xl overflow-hidden">
            <CardHeader className="py-3 px-5 border-b border-border">
              <div className="flex items-center gap-2">
                <div className="p-1.5 rounded-lg bg-primary/10"><Bot size={16} className="text-primary" /></div>
                <div>
                  <CardTitle className="text-sm">AI Assistant</CardTitle>
                  <p className="text-xs text-muted-foreground">Powered by Gemini - ask about processes, members, or tasks</p>
                </div>
              </div>
            </CardHeader>
            <CardContent className="flex-1 overflow-y-auto p-4 space-y-3">
              {aiMessages.length === 0 && (
                <div className="text-center py-12 text-sm text-muted-foreground">
                  <Bot size={40} className="mx-auto mb-3 opacity-30" />
                  <p>Ask me anything about your organization!</p>
                  <div className="flex flex-wrap gap-2 justify-center mt-4">
                    {['How do I add a new member?', 'Help me plan an event', 'Summarize our financial status'].map(q => (
                      <Button key={q} variant="outline" size="sm" className="text-xs" onClick={() => { setAiInput(q); }}>{q}</Button>
                    ))}
                  </div>
                </div>
              )}
              {aiMessages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 ${msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-secondary'}`}>
                    <p className="text-sm whitespace-pre-wrap">{msg.text}</p>
                  </div>
                </div>
              ))}
              {aiSending && (
                <div className="flex justify-start">
                  <div className="bg-secondary rounded-2xl px-4 py-2.5">
                    <div className="flex gap-1">
                      <span className="h-2 w-2 bg-muted-foreground/40 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="h-2 w-2 bg-muted-foreground/40 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="h-2 w-2 bg-muted-foreground/40 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                  </div>
                </div>
              )}
              <div ref={aiEndRef} />
            </CardContent>
            <div className="p-3 border-t border-border flex gap-2">
              <Input className="flex-1" placeholder="Ask the AI assistant..." value={aiInput}
                onChange={e => setAiInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAiSend(); } }}
                data-testid="ai-input" />
              <Button onClick={handleAiSend} disabled={aiSending || !aiInput.trim()} data-testid="ai-send-btn">
                <Send size={16} />
              </Button>
            </div>
          </Card>
        </TabsContent>

        {/* Announcements Tab */}
        <TabsContent value="announcements" className="flex-1 min-h-0 overflow-y-auto">
          <div className="space-y-4">
            {isAdmin && (
              <div className="flex justify-end">
                <Button className="gap-2" onClick={() => setShowNewAnnouncement(true)} data-testid="new-announcement-btn">
                  <Plus size={14} /> Post Announcement
                </Button>
              </div>
            )}
            {loading ? (
              <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-20 bg-muted animate-pulse rounded-xl" />)}</div>
            ) : announcements.length === 0 ? (
              <div className="text-center py-16 text-sm text-muted-foreground">
                <Megaphone size={40} className="mx-auto mb-3 opacity-30" />
                No announcements yet.
              </div>
            ) : (
              announcements.map(a => (
                <Card key={a.id} className="shadow-soft rounded-xl" data-testid="announcement-card">
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-semibold text-sm">{a.title}</h3>
                          <Badge variant="outline" className="text-xs capitalize">{a.type}</Badge>
                          {a.pinned && <Badge className="text-xs bg-amber-100 text-amber-700 border-amber-200">Pinned</Badge>}
                        </div>
                        <p className="text-sm text-muted-foreground">{a.content}</p>
                      </div>
                      <p className="text-xs text-muted-foreground shrink-0 ml-4">{a.created_at?.slice(0, 10)}</p>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </TabsContent>
      </Tabs>

      {/* New Conversation Dialog */}
      <Dialog open={showNewConv} onOpenChange={setShowNewConv}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New Conversation</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Conversation Name</Label>
              <Input placeholder="e.g. Team Discussion" value={convForm.name} onChange={e => setConvForm({...convForm, name: e.target.value})} data-testid="conv-name-input" />
            </div>
            <div className="space-y-2"><Label>Type</Label>
              <Select value={convForm.type} onValueChange={v => setConvForm({...convForm, type: v})}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="direct">Direct Message</SelectItem>
                  <SelectItem value="group">Group Chat</SelectItem>
                  <SelectItem value="announcements">Announcements (No Reply)</SelectItem>
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

      {/* New Announcement Dialog */}
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
              <Button type="submit" className="flex-1" data-testid="post-announcement-btn">Post</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
