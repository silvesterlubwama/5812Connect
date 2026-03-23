import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { authApi } from '../services/api';
import { toast } from 'sonner';

export default function RegisterPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: '', email: '', phone: '', password: '', confirmPassword: '' });
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (form.password !== form.confirmPassword) { toast.error('Passwords do not match'); return; }
    if (form.password.length < 6) { toast.error('Password must be at least 6 characters'); return; }
    setLoading(true);
    try {
      await authApi.register({ name: form.name, email: form.email, phone: form.phone || undefined, password: form.password });
      toast.success('Account request submitted! An admin will review your request.');
      navigate('/login');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Registration failed');
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4 py-12">
      <div className="w-full max-w-md">
        <Card className="shadow-soft rounded-xl">
          <CardHeader className="text-center">
            <img src="https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=800&ssl=1" alt="58:12 Global" className="mx-auto h-14 w-auto object-contain mb-3" />
            <CardTitle className="text-xl font-semibold">Create an account</CardTitle>
            <CardDescription>Create an account to join 58:12 Global Connect</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label>Full Name *</Label>
                <Input placeholder="John Doe" value={form.name} onChange={e => setForm({...form, name: e.target.value})} required />
              </div>
              <div className="space-y-2">
                <Label>Email *</Label>
                <Input type="email" placeholder="you@example.com" value={form.email} onChange={e => setForm({...form, email: e.target.value})} required />
              </div>
              <div className="space-y-2">
                <Label>Phone (Optional)</Label>
                <Input placeholder="+256 700 000 000" value={form.phone} onChange={e => setForm({...form, phone: e.target.value})} />
              </div>
              <div className="space-y-2">
                <Label>Password *</Label>
                <div className="relative">
                  <Input type={showPass ? 'text' : 'password'} placeholder="Create a password" value={form.password} onChange={e => setForm({...form, password: e.target.value})} required className="pr-10" />
                  <button type="button" className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground" onClick={() => setShowPass(!showPass)}>
                    {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>
              <div className="space-y-2">
                <Label>Confirm Password *</Label>
                <Input type="password" placeholder="Confirm your password" value={form.confirmPassword} onChange={e => setForm({...form, confirmPassword: e.target.value})} required />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Submitting...' : 'Request Access'}</Button>
              <Button variant="outline" type="button" className="w-full gap-2">
                <svg className="w-4 h-4" viewBox="0 0 24 24">
                  <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                  <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
                Sign up with Google
              </Button>
              <p className="text-xs text-muted-foreground text-center">
                New accounts start as Volunteers. A coordinator will assign your role.
              </p>
              <div className="text-center text-sm text-muted-foreground">
                Already have an account?{' '}<Link to="/login" className="text-primary hover:underline">Back to Login</Link>
              </div>
              <div className="text-center">
                <Link to="/public-bookings" className="text-xs text-muted-foreground hover:text-primary">Book Events &amp; Community Spaces</Link>
              </div>
            </form>
          </CardContent>
        </Card>
        <p className="text-center text-xs text-muted-foreground mt-4">58:12 Global • Uganda CRM System</p>
      </div>
    </div>
  );
}
