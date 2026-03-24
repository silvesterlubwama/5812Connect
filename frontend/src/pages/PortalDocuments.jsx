import React, { useState, useEffect } from 'react';
import { FileText, Download } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { portalApi } from '../services/api';
import { toast } from 'sonner';

export default function PortalDocuments() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    portalApi.documents()
      .then(res => setDocuments(res.data))
      .catch(() => toast.error('Failed to load documents'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" /></div>;

  return (
    <div className="space-y-6 max-w-4xl" data-testid="portal-documents">
      <div>
        <h1 className="text-2xl font-bold font-heading">My Documents</h1>
        <p className="text-sm text-muted-foreground mt-1">{documents.length} documents on file</p>
      </div>

      {documents.length === 0 ? (
        <Card className="shadow-soft rounded-xl">
          <CardContent className="py-12 text-center text-muted-foreground">
            <FileText size={40} className="mx-auto mb-3 opacity-30" />
            <p>No documents on file yet</p>
            <p className="text-xs mt-1">Documents uploaded by admin will appear here</p>
          </CardContent>
        </Card>
      ) : (
        <Card className="shadow-soft rounded-xl">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Document List</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="divide-y">
              {documents.map(doc => (
                <div key={doc.id} className="flex items-center justify-between py-3" data-testid={`doc-${doc.id}`}>
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-primary/10">
                      <FileText size={16} className="text-primary" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">{doc.original_name || doc.filename}</p>
                      <p className="text-xs text-muted-foreground">{doc.doc_type || 'Document'} — {new Date(doc.uploaded_at).toLocaleDateString()}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-xs">{doc.doc_type || 'file'}</Badge>
                    {doc.url && (
                      <a href={doc.url} target="_blank" rel="noopener noreferrer" className="p-1.5 rounded-lg hover:bg-accent">
                        <Download size={14} />
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
