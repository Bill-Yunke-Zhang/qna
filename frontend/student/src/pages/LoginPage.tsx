import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { useCourse } from '../lib/CourseContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardHeader } from '../components/ui/card';

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [netid, setNetid] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { refresh } = useCourse();

  async function handlePasswordLogin(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await api.post<{ access_token: string }>('/auth/login', { username, password });
      localStorage.setItem('token', data.access_token);
      await refresh();
      navigate('/questions');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleDevNetidLogin(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const temp = await api.post<{ temp_token: string }>('/auth/login', { netid });
      const res = await fetch('/api/auth/exchange-temp', {
        method: 'POST',
        headers: { Authorization: `Bearer ${temp.temp_token}` },
      });
      if (!res.ok) throw new Error('Failed to exchange temp token');
      const data = (await res.json()) as { access_token: string };
      localStorage.setItem('token', data.access_token);
      await refresh();
      navigate('/questions');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm space-y-4">
        <Card>
          <CardHeader>
            <h1 className="text-2xl font-bold text-slate-100">Student Login</h1>
            <p className="text-slate-400 text-sm mt-1">Course Q&amp;A</p>
          </CardHeader>
          <CardContent>
            <form onSubmit={handlePasswordLogin} className="space-y-4">
              <Input
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
              />
              <Input
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
              {error && <p className="text-red-400 text-sm">{error}</p>}
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? 'Signing in…' : 'Sign In'}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <p className="text-slate-400 text-xs mb-3">
              Development only — stands in for campus SSO until an OAuth2 proxy is deployed in
              front of this service.
            </p>
            <form onSubmit={handleDevNetidLogin} className="flex gap-2">
              <Input
                placeholder="netid"
                value={netid}
                onChange={(e) => setNetid(e.target.value)}
              />
              <Button type="submit" variant="outline" disabled={loading}>
                Dev Login
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
