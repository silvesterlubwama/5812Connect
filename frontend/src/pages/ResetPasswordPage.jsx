import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { authApi } from '../services/api';
import { useBranding } from '../context/BrandingContext';
import { toast } from 'sonner';

export default function ResetPasswordPage() {
  const { branding } = useBranding();
  const [email, setEmail] = useState('');
  const [step, setStep] = useState('email'); // email | code | done
  const [resetCode, setResetCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSendCode = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await authApi.forgotPassword(email);
      toast.success('Reset code sent to your email');
      setStep('code');
    } catch { toast.error('Failed to send reset code'); }
    finally { setLoading(false); }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) { toast.error('Passwords do not match'); return; }
    if (newPassword.length < 6) { toast.error('Password must be at least 6 characters'); return; }
    setLoading(true);
    try {
      await authApi.resetPassword(resetCode, newPassword);
      toast.success('Password reset successfully!');
      setStep('done');
    } catch (err) { toast.error(err.response?.data?.detail || 'Reset failed'); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4 py-12">
      <div className="w-full max-w-md">
        <Card className="shadow-soft rounded-xl">
          <CardHeader className="text-center">
            <img
              src={branding?.logo_url || 'https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=800&ssl=1'}
              alt={branding?.app_name || '58:12 Global'}
              className="mx-auto h-14 w-auto object-contain mb-3"
              onError={(e) => { e.target.onerror = null; e.target.src = 'https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=800&ssl=1'; }}
            />
            <CardTitle className="text-xl font-semibold">Reset Password</CardTitle>
            <CardDescription>{step === 'email' ? 'Enter your email to receive a reset code' : step === 'code' ? 'Enter the code sent to your email' : 'Password reset complete'}</CardDescription>
          </CardHeader>
          <CardContent>
            {step === 'email' && (
              <form onSubmit={handleSendCode} className="space-y-4">
                <div className="space-y-2">
                  <Label>Email Address</Label>
                  <Input type="email" placeholder="your@email.com" value={email} onChange={e => setEmail(e.target.value)} required data-testid="reset-email-input" />
                </div>
                <Button type="submit" className="w-full" disabled={loading} data-testid="send-reset-code-btn">
                  {loading ? 'Sending...' : 'Send Reset Code'}
                </Button>
                <div className="text-center">
                  <Link to="/login" className="text-sm text-muted-foreground hover:text-primary">Back to login</Link>
                </div>
              </form>
            )}

            {step === 'code' && (
              <form onSubmit={handleResetPassword} className="space-y-4">
                <div className="space-y-2">
                  <Label>Reset Code</Label>
                  <Input placeholder="Enter 8-character code" value={resetCode} onChange={e => setResetCode(e.target.value)} required maxLength={8} className="text-center tracking-widest text-lg font-mono" data-testid="reset-code-input" />
                </div>
                <div className="space-y-2">
                  <Label>New Password</Label>
                  <Input type="password" placeholder="Min 6 characters" value={newPassword} onChange={e => setNewPassword(e.target.value)} required data-testid="new-password-input" />
                </div>
                <div className="space-y-2">
                  <Label>Confirm Password</Label>
                  <Input type="password" placeholder="Confirm new password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} required data-testid="confirm-password-input" />
                </div>
                <Button type="submit" className="w-full" disabled={loading} data-testid="reset-password-btn">
                  {loading ? 'Resetting...' : 'Reset Password'}
                </Button>
                <Button type="button" variant="ghost" className="w-full text-sm" onClick={() => setStep('email')}>
                  Use a different email
                </Button>
              </form>
            )}

            {step === 'done' && (
              <div className="text-center space-y-4">
                <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center mx-auto">
                  <svg className="w-8 h-8 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <p className="text-sm text-muted-foreground">Your password has been reset successfully.</p>
                <Button className="w-full" onClick={() => navigate('/login')} data-testid="back-to-login-btn">
                  Back to Login
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
