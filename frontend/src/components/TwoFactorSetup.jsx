import React, { useState } from 'react';
import { Shield, Smartphone, Key, CheckCircle, X, Copy } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { twoFactorApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

export default function TwoFactorSetup() {
  const { user, refreshUser } = useAuth();
  const [showSetup, setShowSetup] = useState(false);
  const [setupData, setSetupData] = useState(null);
  const [verifyCode, setVerifyCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [disabling, setDisabling] = useState(false);

  const is2FAEnabled = user?.two_factor_enabled;

  const handleStartSetup = async () => {
    setLoading(true);
    try {
      const res = await twoFactorApi.setup();
      setSetupData(res.data);
      setShowSetup(true);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to start 2FA setup');
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async () => {
    if (!verifyCode || verifyCode.length !== 6) {
      toast.error('Please enter a 6-digit code');
      return;
    }
    setVerifying(true);
    try {
      await twoFactorApi.verify(verifyCode);
      toast.success('Two-factor authentication enabled!');
      setShowSetup(false);
      setSetupData(null);
      setVerifyCode('');
      if (refreshUser) refreshUser();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Invalid verification code');
    } finally {
      setVerifying(false);
    }
  };

  const handleDisable = async () => {
    if (!window.confirm('Are you sure you want to disable two-factor authentication? This will make your account less secure.')) return;
    setDisabling(true);
    try {
      await twoFactorApi.disable();
      toast.success('Two-factor authentication disabled');
      if (refreshUser) refreshUser();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to disable 2FA');
    } finally {
      setDisabling(false);
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    toast.success('Copied to clipboard');
  };

  return (
    <>
      <Card className="shadow-soft rounded-xl">
        <CardHeader className="pb-4">
          <CardTitle className="text-base flex items-center gap-2">
            <Smartphone size={16} /> Two-Factor Authentication (2FA)
          </CardTitle>
          <CardDescription>
            Add an extra layer of security to your account using an authenticator app
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between p-4 rounded-lg border border-border">
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg ${is2FAEnabled ? 'bg-green-100 dark:bg-green-950' : 'bg-muted'}`}>
                {is2FAEnabled ? (
                  <CheckCircle size={20} className="text-green-600" />
                ) : (
                  <Shield size={20} className="text-muted-foreground" />
                )}
              </div>
              <div>
                <p className="font-medium text-sm">Authenticator App</p>
                <p className="text-xs text-muted-foreground">
                  {is2FAEnabled 
                    ? 'Your account is protected with 2FA' 
                    : 'Use Google Authenticator, Authy, or similar'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={is2FAEnabled ? 'default' : 'secondary'} className="text-xs">
                {is2FAEnabled ? 'Enabled' : 'Not Enabled'}
              </Badge>
              {is2FAEnabled ? (
                <Button 
                  variant="destructive" 
                  size="sm" 
                  onClick={handleDisable} 
                  disabled={disabling}
                  data-testid="disable-2fa-btn"
                >
                  {disabling ? 'Disabling...' : 'Disable'}
                </Button>
              ) : (
                <Button 
                  size="sm" 
                  onClick={handleStartSetup} 
                  disabled={loading}
                  data-testid="enable-2fa-btn"
                >
                  {loading ? 'Loading...' : 'Enable'}
                </Button>
              )}
            </div>
          </div>

          {!is2FAEnabled && (
            <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-950/30 text-xs text-amber-700 dark:text-amber-400">
              <strong>Recommended:</strong> Enable 2FA to protect your account from unauthorized access, even if your password is compromised.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Setup Dialog */}
      <Dialog open={showSetup} onOpenChange={(open) => { if (!open) { setShowSetup(false); setSetupData(null); setVerifyCode(''); } }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Key size={18} /> Set Up Two-Factor Authentication
            </DialogTitle>
          </DialogHeader>
          {setupData && (
            <div className="space-y-4 mt-2">
              <div className="text-center">
                <p className="text-sm text-muted-foreground mb-4">
                  Scan this QR code with your authenticator app
                </p>
                {setupData.qr_code_base64 ? (
                  <img 
                    src={`data:image/png;base64,${setupData.qr_code_base64}`} 
                    alt="2FA QR Code" 
                    className="mx-auto w-48 h-48 rounded-lg border border-border"
                    data-testid="2fa-qr-code"
                  />
                ) : (
                  <div className="mx-auto w-48 h-48 rounded-lg border border-border bg-muted flex items-center justify-center">
                    <p className="text-xs text-muted-foreground">QR Code</p>
                  </div>
                )}
              </div>

              <div className="p-3 rounded-lg bg-muted space-y-2">
                <p className="text-xs text-muted-foreground">Can't scan? Enter this code manually:</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 text-xs font-mono bg-background p-2 rounded border border-border break-all">
                    {setupData.secret || 'XXXXXXXXXXXXXXXX'}
                  </code>
                  <Button 
                    size="sm" 
                    variant="ghost" 
                    onClick={() => copyToClipboard(setupData.secret)}
                    data-testid="copy-secret-btn"
                  >
                    <Copy size={14} />
                  </Button>
                </div>
              </div>

              <div className="space-y-2">
                <Label>Enter verification code from your app</Label>
                <Input
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  placeholder="000000"
                  value={verifyCode}
                  onChange={e => setVerifyCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  className="text-center text-lg tracking-widest font-mono"
                  data-testid="2fa-verify-code-input"
                />
              </div>

              <div className="flex gap-3 pt-2">
                <Button 
                  variant="outline" 
                  className="flex-1" 
                  onClick={() => { setShowSetup(false); setSetupData(null); setVerifyCode(''); }}
                >
                  Cancel
                </Button>
                <Button 
                  className="flex-1" 
                  onClick={handleVerify} 
                  disabled={verifying || verifyCode.length !== 6}
                  data-testid="verify-2fa-btn"
                >
                  {verifying ? 'Verifying...' : 'Verify & Enable'}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
