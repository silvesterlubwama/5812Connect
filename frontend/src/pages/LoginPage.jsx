import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { secureStorage } from '../services/secureStorage';
import { Eye, EyeOff, Monitor, Users, Fingerprint } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { webAuthnApi } from '../services/api';
import { toast } from 'sonner';

export default function LoginPage() {
  const { login, setUser } = useAuth();
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [passkeyLoading, setPasskeyLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!identifier || !password) { toast.error('Please fill in all fields'); return; }
    setLoading(true);
    try {
      await login(identifier, password);
      navigate('/dashboard');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Invalid credentials');
    } finally {
      setLoading(false);
    }
  };

  const handlePasskeyLogin = async () => {
    if (!window.PublicKeyCredential) {
      toast.error('Passkeys not supported in this browser');
      return;
    }
    setPasskeyLoading(true);
    try {
      // 1. Get auth options from server
      const rpId = window.location.hostname;
      const optRes = await webAuthnApi.authenticateBegin(identifier.trim().toLowerCase() || '', rpId);
      const options = optRes.data;

      // 2. Convert base64url to ArrayBuffer
      const b64toAB = (b64) => {
        const bin = atob(b64.replace(/-/g,'+').replace(/_/g,'/'));
        return Uint8Array.from(bin, c => c.charCodeAt(0)).buffer;
      };
      const publicKey = {
        ...options,
        challenge: b64toAB(options.challenge),
        allowCredentials: (options.allowCredentials || []).map(c => ({ ...c, id: b64toAB(c.id) })),
      };

      // 3. Get assertion
      const assertion = await navigator.credentials.get({ publicKey });

      // 4. Convert to base64url
      const ABtoB64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=/g,'');
      const assertionJSON = {
        id: assertion.id,
        rawId: ABtoB64(assertion.rawId),
        type: assertion.type,
        response: {
          clientDataJSON: ABtoB64(assertion.response.clientDataJSON),
          authenticatorData: ABtoB64(assertion.response.authenticatorData),
          signature: ABtoB64(assertion.response.signature),
          userHandle: assertion.response.userHandle ? ABtoB64(assertion.response.userHandle) : null,
        },
      };

      // 5. Complete authentication
      assertionJSON.rpId = rpId;
      assertionJSON.expectedOrigin = window.location.origin;
      const verifyRes = await webAuthnApi.authenticateComplete(assertionJSON);
      const { token, user } = verifyRes.data;
      secureStorage.setToken(token);
      setUser(user);
      toast.success(`Welcome back, ${user.name}!`);
      navigate('/dashboard');
    } catch (err) {
      if (err.name === 'NotAllowedError') {
        toast.info('Passkey authentication cancelled');
      } else {
        toast.error(err.response?.data?.detail || err.message || 'Passkey authentication failed');
      }
    } finally { setPasskeyLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4 py-12">
      <div className="w-full max-w-md">
        <Card className="shadow-soft rounded-xl">
          <CardHeader className="text-center pb-4">
            <img
              src="https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=800&ssl=1"
              alt="58:12 Global"
              className="mx-auto h-16 w-auto object-contain mb-3"
            />
            <CardTitle className="text-2xl font-semibold font-heading">58:12 Global Connect</CardTitle>
            <CardDescription>Sign in to access the management system</CardDescription>
          </CardHeader>

          <CardContent className="space-y-4">
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="identifier">Email, Phone, or ID Number</Label>
                <Input id="identifier" type="text" placeholder="Email, phone, or national ID" value={identifier} onChange={e => setIdentifier(e.target.value)} required />
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Input id="password" type={showPassword ? 'text' : 'password'} placeholder="••••••••" value={password} onChange={e => setPassword(e.target.value)} required className="pr-10" />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              <div className="text-right">
                <Link to="/reset-password" className="text-sm text-primary hover:underline">Forgot password?</Link>
              </div>

              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? 'Signing in...' : 'Sign In'}
              </Button>
            </form>

            <div className="relative">
              <div className="absolute inset-0 flex items-center"><span className="w-full border-t" /></div>
              <div className="relative flex justify-center text-xs uppercase"><span className="bg-background px-2 text-muted-foreground">Or</span></div>
            </div>

            <Button
              variant="outline"
              className="w-full gap-2"
              onClick={handlePasskeyLogin}
              disabled={passkeyLoading}
              data-testid="passkey-login-btn"
            >
              <Fingerprint size={16} />
              {passkeyLoading ? 'Authenticating...' : 'Sign in with Passkey'}
            </Button>
            <div className="relative my-2">
              <div className="absolute inset-0 flex items-center"><span className="w-full border-t border-border" /></div>
              <div className="relative flex justify-center text-xs uppercase"><span className="bg-card px-2 text-muted-foreground">Or</span></div>
            </div>

            {/* REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH */}
            <Button variant="outline" className="w-full gap-2" type="button" data-testid="google-signin-btn" onClick={() => {
              const redirectUrl = window.location.origin + '/dashboard';
              window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
            }}>
              <svg className="w-4 h-4" viewBox="0 0 24 24">
                <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
              Sign in with Google
            </Button>

            <div className="relative my-2">
              <div className="absolute inset-0 flex items-center"><span className="w-full border-t border-border" /></div>
              <div className="relative flex justify-center text-xs uppercase"><span className="bg-card px-2 text-muted-foreground">Quick Access</span></div>
            </div>

            <Button variant="outline" className="w-full gap-2 border-primary/20 hover:bg-primary/5" type="button">
              <Users size={16} /> Parent Portal Login
            </Button>

            <p className="text-center text-sm text-muted-foreground mt-2">
              Need access?{' '}
              <Link to="/register" className="text-primary hover:underline font-medium">Request account</Link>
            </p>

            <div className="pt-4 border-t border-border space-y-2">
              <Link to="/kiosk">
                <Button variant="ghost" className="w-full gap-2 text-muted-foreground">
                  <Monitor size={16} /> Open Check-in Kiosk
                </Button>
              </Link>
              <Link to="/public-bookings">
                <Button variant="ghost" className="w-full gap-2 text-muted-foreground">
                  Book Events &amp; Community Spaces
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
        <p className="text-center text-xs text-muted-foreground mt-6">58:12 Global</p>
      </div>
    </div>
  );
}
