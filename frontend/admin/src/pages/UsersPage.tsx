import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import { Input } from '../components/ui/input';

interface User {
  id: string;
  username: string | null;
  netid: string | null;
  display_name: string | null;
  email: string | null;
  role: string;
  created_at: string;
  last_login: string | null;
}

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const navigate = useNavigate();

  async function load() {
    const data = await api.get<User[]>('/admin/users');
    setUsers(data);
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await api.post('/admin/users', {
        username,
        display_name: displayName,
        email: email || undefined,
        password,
      });
      setUsername('');
      setDisplayName('');
      setEmail('');
      setPassword('');
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create user');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="p-8 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-slate-100">Users</h2>
        <Button size="sm" onClick={() => setShowForm(!showForm)}>
          <Plus size={16} className="mr-1" /> New Local Account
        </Button>
      </div>

      {showForm && (
        <Card className="mb-6">
          <CardHeader>
            <h3 className="text-lg font-semibold text-slate-100">Create Local Account</h3>
            <p className="text-slate-400 text-sm mt-1">
              For course staff or students without campus SSO — e.g. TAs using a shared account.
            </p>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="grid grid-cols-2 gap-3">
              <Input placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} required />
              <Input placeholder="Display name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
              <Input placeholder="Email (optional)" value={email} onChange={(e) => setEmail(e.target.value)} />
              <Input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required />
              {error && <p className="text-red-400 text-sm col-span-2">{error}</p>}
              <div className="col-span-2 flex gap-3">
                <Button type="submit" disabled={saving}>{saving ? 'Creating…' : 'Create'}</Button>
                <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>Cancel</Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <div className="space-y-2">
        {users.map((u) => (
          <Card
            key={u.id}
            className="flex items-center justify-between px-6 py-3 cursor-pointer hover:border-indigo-500"
            onClick={() => navigate(`/users/${u.id}`)}
          >
            <div>
              <p className="font-medium text-slate-100">
                {u.display_name || u.username || u.netid}
              </p>
              <p className="text-slate-500 text-sm">
                {u.username ? `@${u.username}` : u.netid} · {u.role}
              </p>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
