import React, { useState, useEffect, useRef } from 'react';
import { FileText, Download, Upload, AlertCircle, CheckCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Label } from '../components/ui/label';
import { documentsApi, portalApi } from '../services/api';
import { toast } from 'sonner';

const ID_TYPE_LABELS = {
  national_id: 'National ID',
  state_id: 'State ID',
  drivers_license: "Driver's Licence",
  passport: 'Passport',
  birth_certificate: 'Birth Certificate',
  refugee_id: 'Refugee ID',
  alien_id: 'Alien ID',
  voter_card: 'Voter Card',
  student_id: 'Student ID',
  employee_id: 'Employee ID',
  other: 'Other',
};

export default function PortalDocuments() {
  const [documents, setDocuments] = useState([]);
  const [requests, setRequests] = useState([]);
  const [memberId, setMemberId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadDocType, setUploadDocType] = useState('other');
  const fileInputRef = useRef(null);

  useEffect(() => {
    portalApi.documents()
      .then(res => {
        const data = res.data;
        if (data && typeof data === 'object' && 'documents' in data) {
          setDocuments(data.documents || []);
          setRequests(data.requests || []);
          setMemberId(data.member_id);
        } else {
          // Legacy response (flat array)
          setDocuments(Array.isArray(data) ? data : []);
        }
      })
      .catch(() => toast.error('Failed to load documents'))
      .finally(() => setLoading(false));
  }, []);

  const handleUpload = async (e, requestId = null, requestDocType = null) => {
    const file = e.target.files?.[0];
    if (!file || !memberId) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('doc_type', requestDocType || uploadDocType);
      if (requestId) fd.append('request_id', requestId);
      const res = await documentsApi.upload(memberId, fd);
      setDocuments(prev => [res.data, ...prev]);
      if (requestId) {
        setRequests(prev => prev.map(r => r.id === requestId ? { ...r, status: 'fulfilled' } : r));
      }
      toast.success('Document uploaded successfully');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const pendingRequests = requests.filter(r => r.status === 'pending');
  const fulfilledRequests = requests.filter(r => r.status === 'fulfilled');

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" />
    </div>
  );

  return (
    <div className="space-y-6 max-w-4xl" data-testid="portal-documents">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold font-heading">My Documents</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {documents.length} document{documents.length !== 1 ? 's' : ''} on file
          </p>
        </div>
        {memberId && (
          <div className="flex items-center gap-2">
            <Select value={uploadDocType} onValueChange={setUploadDocType}>
              <SelectTrigger className="h-9 text-sm w-44"><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(ID_TYPE_LABELS).map(([k, v]) => (
                  <SelectItem key={k} value={k}>{v}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              className="gap-2 h-9"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              data-testid="upload-document-btn"
            >
              <Upload size={14} />
              {uploading ? 'Uploading...' : 'Upload Document'}
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              accept=".jpg,.jpeg,.png,.pdf,.doc,.docx"
              onChange={handleUpload}
            />
          </div>
        )}
      </div>

      {/* Pending requests */}
      {pendingRequests.length > 0 && (
        <Card className="shadow-soft rounded-xl border-yellow-200 bg-yellow-50/50">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm flex items-center gap-2 text-yellow-800">
              <AlertCircle size={15} /> Documents Requested ({pendingRequests.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-2">
            {pendingRequests.map(req => (
              <FulfillRow
                key={req.id}
                req={req}
                memberId={memberId}
                onFulfilled={(doc) => {
                  setDocuments(prev => [doc, ...prev]);
                  setRequests(prev => prev.map(r => r.id === req.id ? { ...r, status: 'fulfilled' } : r));
                }}
              />
            ))}
          </CardContent>
        </Card>
      )}

      {/* Documents list */}
      <Card className="shadow-soft rounded-xl">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Documents on File</CardTitle>
        </CardHeader>
        <CardContent>
          {documents.length === 0 ? (
            <div className="py-10 text-center text-muted-foreground">
              <FileText size={40} className="mx-auto mb-3 opacity-30" />
              <p>No documents uploaded yet</p>
              {memberId
                ? <p className="text-xs mt-1">Use "Upload Document" above to add your first document</p>
                : <p className="text-xs mt-1">Documents uploaded by admin will appear here</p>
              }
            </div>
          ) : (
            <div className="divide-y divide-border">
              {documents.map(doc => (
                <div key={doc.id} className="flex items-center justify-between py-3" data-testid={`doc-${doc.id}`}>
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-primary/10">
                      <FileText size={16} className="text-primary" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">{ID_TYPE_LABELS[doc.doc_type] || doc.label || 'Document'}</p>
                      <p className="text-xs text-muted-foreground">
                        {doc.original_filename} · {new Date(doc.created_at || doc.uploaded_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-xs capitalize">
                      {ID_TYPE_LABELS[doc.doc_type] || doc.doc_type}
                    </Badge>
                    <a
                      href={documentsApi.fileUrl(doc.id)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-1.5 rounded-lg hover:bg-accent"
                      title="View / Download"
                    >
                      <Download size={14} />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Fulfilled requests */}
      {fulfilledRequests.length > 0 && (
        <Card className="shadow-soft rounded-xl">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center gap-2 text-green-700">
              <CheckCircle size={14} /> Completed Requests
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="divide-y divide-border">
              {fulfilledRequests.map(req => (
                <div key={req.id} className="flex items-center justify-between py-2.5 text-sm">
                  <span className="text-muted-foreground">{ID_TYPE_LABELS[req.doc_type] || req.doc_type}</span>
                  <Badge variant="outline" className="text-xs bg-green-50 text-green-700 border-green-200">Fulfilled</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function FulfillRow({ req, memberId, onFulfilled }) {
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);

  const handle = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('doc_type', req.doc_type);
      fd.append('request_id', req.id);
      const res = await documentsApi.upload(memberId, fd);
      onFulfilled(res.data);
      toast.success('Document uploaded and request fulfilled');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  return (
    <div className="flex items-center justify-between p-3 rounded-lg border border-yellow-200 bg-white">
      <div>
        <p className="text-sm font-medium text-yellow-900">
          {ID_TYPE_LABELS[req.doc_type] || req.doc_type} requested
        </p>
        {req.message && <p className="text-xs text-yellow-700 mt-0.5">"{req.message}"</p>}
        <p className="text-xs text-yellow-600 mt-0.5">
          By {req.requested_by_name} · {new Date(req.requested_at).toLocaleDateString()}
        </p>
      </div>
      <Button
        size="sm"
        className="gap-1.5 h-8"
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
        data-testid={`fulfill-request-${req.id}`}
      >
        <Upload size={12} /> {uploading ? 'Uploading...' : 'Upload'}
      </Button>
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        accept=".jpg,.jpeg,.png,.pdf,.doc,.docx"
        onChange={handle}
      />
    </div>
  );
}
