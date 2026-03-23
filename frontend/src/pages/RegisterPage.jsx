import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { toast } from 'sonner';

export default function RegisterPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: '', email: '', phone: '', nationalId: '', reason: '' });
  const [loading, setLoading] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      toast.success('Account request submitted! An admin will review your request.');
      navigate('/login');
    }, 1000);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4 py-12">
      <div className="w-full max-w-md">
        <Card className="shadow-soft rounded-xl">
          <CardHeader className="text-center">
            <img
              src="https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=800&ssl=1"
              alt="58:12 Global"
              className="mx-auto h-14 w-auto object-contain mb-3"
            />
            <CardTitle className="text-xl font-semibold">Request Account Access</CardTitle>
            <CardDescription>Submit a request to access the 58:12 Global Connect system</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label>Full Name</Label>
                <Input placeholder="Your full name" value={form.name} onChange={e => setForm({...form, name: e.target.value})} required />
              </div>
              <div className="space-y-2">
                <Label>Email Address</Label>
                <Input type="email" placeholder="your@email.com" value={form.email} onChange={e => setForm({...form, email: e.target.value})} required />
              </div>
              <div className="space-y-2">
                <Label>Phone Number</Label>
                <Input placeholder="+256 700 000000" value={form.phone} onChange={e => setForm({...form, phone: e.target.value})} />
              </div>
              <div className="space-y-2">
                <Label>National ID (optional)</Label>
                <Input placeholder="CM000000000XXXX" value={form.nationalId} onChange={e => setForm({...form, nationalId: e.target.value})} />
              </div>
              <div className="space-y-2">
                <Label>Reason for Access</Label>
                <Input placeholder="Staff, volunteer, parent..." value={form.reason} onChange={e => setForm({...form, reason: e.target.value})} />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? 'Submitting...' : 'Submit Request'}
              </Button>
              <div className="text-center text-sm text-muted-foreground">
                Already have an account?{' '}
                <Link to="/login" className="text-primary hover:underline">Sign in</Link>
              </div>
            </form>
          </CardContent>
        </Card>
        <p className="text-center text-xs text-muted-foreground mt-4">58:12 Global • Uganda CRM System</p>
      </div>
    </div>
  );
}
