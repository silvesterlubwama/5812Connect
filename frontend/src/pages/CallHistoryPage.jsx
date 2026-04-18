import React, { useState, useEffect } from 'react';
import { 
  Phone, PhoneIncoming, PhoneOutgoing, PhoneMissed, Video, 
  Clock, Trash2, Play, Download, Search, RefreshCw, Filter,
  Voicemail, Calendar
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { callingApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useCall } from '../context/CallContext';
import { toast } from 'sonner';
import { BulkActionBar, exportToCSV, SelectCheckbox } from '../components/BulkActions';

export default function CallHistoryPage() {
  const { user } = useAuth();
  const { initiateCall } = useCall();
  const [calls, setCalls] = useState([]);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [voicemails, setVoicemails] = useState([]);
  const [recordings, setRecordings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [callTypeFilter, setCallTypeFilter] = useState('all');
  const [tab, setTab] = useState('history');

  useEffect(() => {
    if (user?.id) {
      fetchData();
    }
  }, [user?.id]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [historyRes, voicemailRes, recordingsRes] = await Promise.all([
        callingApi.getHistory(user.id, { limit: 100 }),
        callingApi.getVoicemails(user.id),
        callingApi.getRecordings(user.id),
      ]);
      setCalls(historyRes.data?.calls || []);
      setVoicemails(voicemailRes.data || []);
      setRecordings(recordingsRes.data || []);
    } catch (err) {
      toast.error('Failed to load call history');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (callId) => {
    if (!window.confirm('Delete this call record?')) return;
    try {
      await callingApi.deleteCallRecord(callId);
      setCalls(prev => prev.filter(c => c.id !== callId));
      toast.success('Call record deleted');
    } catch {
      toast.error('Failed to delete');
    }
  };

  const handleDeleteVoicemail = async (id) => {
    if (!window.confirm('Delete this voicemail?')) return;
    try {
      await callingApi.deleteVoicemail(id);
      setVoicemails(prev => prev.filter(v => v.id !== id));
      toast.success('Voicemail deleted');
    } catch {
      toast.error('Failed to delete');
    }
  };

  const handleMarkVoicemailRead = async (id) => {
    try {
      await callingApi.markVoicemailRead(id);
      setVoicemails(prev => prev.map(v => v.id === id ? { ...v, is_read: true } : v));
    } catch {
      toast.error('Failed to mark as read');
    }
  };

  const handleCallback = (call) => {
    const targetId = call.caller_id === user.id ? call.target_user_id : call.caller_id;
    if (targetId) {
      initiateCall(targetId, call.call_type || 'audio');
    }
  };

  const formatDuration = (seconds) => {
    if (!seconds) return '--';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '--';
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now - date;
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    
    if (days === 0) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else if (days === 1) {
      return 'Yesterday';
    } else if (days < 7) {
      return date.toLocaleDateString([], { weekday: 'short' });
    } else {
      return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
    }
  };

  const getCallIcon = (call) => {
    const isMissed = ['missed', 'rejected', 'no_answer'].includes(call.status);
    const isOutgoing = call.caller_id === user.id;
    
    if (isMissed) return <PhoneMissed size={16} className="text-red-500" />;
    if (isOutgoing) return <PhoneOutgoing size={16} className="text-green-500" />;
    return <PhoneIncoming size={16} className="text-blue-500" />;
  };

  const getCallLabel = (call) => {
    const isMissed = ['missed', 'rejected', 'no_answer'].includes(call.status);
    const isOutgoing = call.caller_id === user.id;
    
    if (isMissed) return 'Missed';
    if (isOutgoing) return 'Outgoing';
    return 'Incoming';
  };

  const filteredCalls = calls.filter(call => {
    if (searchTerm) {
      const searchLower = searchTerm.toLowerCase();
      const matchesName = (call.caller_name || '').toLowerCase().includes(searchLower);
      const matchesExt = (call.caller_extension || '').includes(searchTerm);
      if (!matchesName && !matchesExt) return false;
    }
    
    if (callTypeFilter !== 'all') {
      if (callTypeFilter === 'missed' && !['missed', 'rejected', 'no_answer'].includes(call.status)) return false;
      if (callTypeFilter === 'video' && call.call_type !== 'video') return false;
      if (callTypeFilter === 'audio' && call.call_type !== 'audio') return false;
    }
    
    return true;
  });

  return (
    <div className="p-6 space-y-6" data-testid="call-history-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Call History</h1>
          <p className="text-sm text-muted-foreground mt-0.5">View call logs, voicemails, and recordings</p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchData}>
          <RefreshCw size={14} className="mr-2" /> Refresh
        </Button>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="history" data-testid="tab-call-history">
            <Phone size={14} className="mr-2" /> Call History
          </TabsTrigger>
          <TabsTrigger value="voicemail" data-testid="tab-voicemail">
            <Voicemail size={14} className="mr-2" /> Voicemail
            {voicemails.filter(v => !v.is_read).length > 0 && (
              <Badge variant="destructive" className="ml-2 h-5 w-5 p-0 text-xs">
                {voicemails.filter(v => !v.is_read).length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="recordings" data-testid="tab-recordings">
            <Play size={14} className="mr-2" /> Recordings
          </TabsTrigger>
        </TabsList>

        {/* Call History Tab */}
        <TabsContent value="history" className="mt-4">
          <Card className="shadow-soft rounded-xl">
            <CardHeader className="pb-3">
              <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                <div className="relative flex-1 max-w-sm">
                  <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Search calls..."
                    className="pl-9"
                    value={searchTerm}
                    onChange={e => setSearchTerm(e.target.value)}
                    data-testid="call-search-input"
                  />
                </div>
                <Select value={callTypeFilter} onValueChange={setCallTypeFilter}>
                  <SelectTrigger className="w-32">
                    <Filter size={14} className="mr-2" />
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Calls</SelectItem>
                    <SelectItem value="missed">Missed</SelectItem>
                    <SelectItem value="audio">Audio</SelectItem>
                    <SelectItem value="video">Video</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map(i => (
                    <div key={i} className="h-16 bg-muted animate-pulse rounded-lg" />
                  ))}
                </div>
              ) : filteredCalls.length === 0 ? (
                <div className="py-12 text-center">
                  <Phone size={48} className="mx-auto mb-3 opacity-30 text-muted-foreground" />
                  <p className="text-muted-foreground">No call history</p>
                </div>
              ) : (
                <div className="space-y-1">
                  {filteredCalls.map(call => {
                    const isOutgoing = call.caller_id === user.id;
                    const otherParty = isOutgoing 
                      ? (call.target_user_id || call.target_extension || call.target_number || 'Unknown')
                      : (call.caller_name || call.caller_extension || 'Unknown');
                    
                    return (
                      <div
                        key={call.id}
                        className="flex items-center gap-4 p-3 rounded-lg hover:bg-muted/50 transition-colors"
                        data-testid={`call-record-${call.id}`}
                      >
                        <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center">
                          {getCallIcon(call)}
                        </div>
                        
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="font-medium text-sm truncate">{otherParty}</p>
                            {call.call_type === 'video' && (
                              <Video size={12} className="text-blue-500" />
                            )}
                            {call.is_conference && (
                              <Badge variant="outline" className="text-xs">Conference</Badge>
                            )}
                          </div>
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <span>{getCallLabel(call)}</span>
                            <span>•</span>
                            <span>{formatDate(call.started_at)}</span>
                            {call.duration > 0 && (
                              <>
                                <span>•</span>
                                <span>{formatDuration(call.duration)}</span>
                              </>
                            )}
                          </div>
                        </div>
                        
                        <div className="flex items-center gap-1">
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-8 w-8 p-0"
                            onClick={() => handleCallback(call)}
                            data-testid={`callback-${call.id}`}
                          >
                            <Phone size={14} />
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-8 w-8 p-0 text-destructive hover:text-destructive"
                            onClick={() => handleDelete(call.id)}
                          >
                            <Trash2 size={14} />
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Voicemail Tab */}
        <TabsContent value="voicemail" className="mt-4">
          <Card className="shadow-soft rounded-xl">
            <CardContent className="p-4">
              {voicemails.length === 0 ? (
                <div className="py-12 text-center">
                  <Voicemail size={48} className="mx-auto mb-3 opacity-30 text-muted-foreground" />
                  <p className="text-muted-foreground">No voicemails</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {voicemails.map(vm => (
                    <div
                      key={vm.id}
                      className={`flex items-center gap-4 p-3 rounded-lg border ${vm.is_read ? 'border-border' : 'border-primary bg-primary/5'}`}
                      data-testid={`voicemail-${vm.id}`}
                    >
                      <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center">
                        <Voicemail size={18} className={vm.is_read ? 'text-muted-foreground' : 'text-primary'} />
                      </div>
                      
                      <div className="flex-1 min-w-0">
                        <p className={`text-sm ${vm.is_read ? '' : 'font-medium'}`}>
                          {vm.from_user_id || vm.from_number || 'Unknown Caller'}
                        </p>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Clock size={10} />
                          <span>{formatDuration(vm.duration)}</span>
                          <span>•</span>
                          <span>{formatDate(vm.created_at)}</span>
                        </div>
                        {vm.transcript && (
                          <p className="text-xs text-muted-foreground mt-1 truncate">{vm.transcript}</p>
                        )}
                      </div>
                      
                      <div className="flex items-center gap-1">
                        {vm.audio_url && (
                          <Button size="sm" variant="ghost" className="h-8 w-8 p-0" asChild>
                            <a href={vm.audio_url} target="_blank" rel="noopener noreferrer">
                              <Play size={14} />
                            </a>
                          </Button>
                        )}
                        {!vm.is_read && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-xs"
                            onClick={() => handleMarkVoicemailRead(vm.id)}
                          >
                            Mark Read
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-8 w-8 p-0 text-destructive hover:text-destructive"
                          onClick={() => handleDeleteVoicemail(vm.id)}
                        >
                          <Trash2 size={14} />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Recordings Tab */}
        <TabsContent value="recordings" className="mt-4">
          <Card className="shadow-soft rounded-xl">
            <CardContent className="p-4">
              {recordings.length === 0 ? (
                <div className="py-12 text-center">
                  <Play size={48} className="mx-auto mb-3 opacity-30 text-muted-foreground" />
                  <p className="text-muted-foreground">No recordings</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {recordings.map(rec => (
                    <div
                      key={rec.id}
                      className="flex items-center gap-4 p-3 rounded-lg border border-border"
                      data-testid={`recording-${rec.id}`}
                    >
                      <div className="h-10 w-10 rounded-full bg-red-100 dark:bg-red-950 flex items-center justify-center">
                        <Play size={18} className="text-red-500" />
                      </div>
                      
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-sm">
                          {rec.caller_name || rec.caller_id} → {rec.target_user_id || rec.target_extension}
                        </p>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Calendar size={10} />
                          <span>{formatDate(rec.started_at)}</span>
                          <span>•</span>
                          <Clock size={10} />
                          <span>{formatDuration(rec.duration)}</span>
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-1">
                        {rec.recording_url && (
                          <>
                            <Button size="sm" variant="outline" className="gap-1" asChild>
                              <a href={rec.recording_url} target="_blank" rel="noopener noreferrer">
                                <Play size={12} /> Play
                              </a>
                            </Button>
                            <Button size="sm" variant="ghost" className="h-8 w-8 p-0" asChild>
                              <a href={rec.recording_url} download>
                                <Download size={14} />
                              </a>
                            </Button>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
