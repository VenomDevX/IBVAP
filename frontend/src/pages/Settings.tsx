import { useState, useEffect } from 'react';
import { apiFetch } from '../api/client';
import { useAuth } from '../context/AuthContext';
import Card from '../components/ui/Card';
import type { User, DashboardSummary } from '../types';

export default function Settings() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const { user } = useAuth();
  const role: string = 'operator';
  const username = user?.email?.split('@')[0] || 'User';

  useEffect(() => {
    apiFetch('/api/statistics/summary').then(r => r.json()).then(setSummary).catch(() => {});
    if (role === 'admin') loadUsers();
  }, [role]);

  const loadUsers = async () => {
    try {
      const res = await apiFetch('/api/auth/users');
      setUsers(await res.json());
    } catch (err) {
      console.error('Failed to load users');
    }
  };

  const updateUser = async (uname: string, field: string, value: string | boolean) => {
    try {
      await apiFetch(`/api/auth/users/${uname}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [field]: value }),
      });
    } catch {
      alert('Failed to update user');
    }
  };

  return (
    <>
      <div className="settings-grid">
        <Card title="User Info" icon="fas fa-user-cog">
          <div className="context-info">
            <p><strong>Username:</strong> {username}</p>
            <p><strong>Role:</strong> {role}</p>
          </div>
        </Card>
        <Card title="System Info" icon="fas fa-server">
          <div className="context-info">
            {summary ? (
              <>
                <p><strong>Total Cameras:</strong> {summary.total_cameras || 0}</p>
                <p><strong>Online Cameras:</strong> {summary.online_cameras || 0}</p>
                <p><strong>Total Alerts:</strong> {summary.total_alerts || 0}</p>
                <p><strong>Active Tracks:</strong> {summary.active_tracks || 0}</p>
              </>
            ) : <p>Loading...</p>}
          </div>
        </Card>
      </div>

      {role === 'admin' && (
        <Card title="User Management (Admin)" icon="fas fa-users-cog" className="" >
          <table className="data-table">
            <thead>
              <tr><th>Username</th><th>Full Name</th><th>Role</th><th>Status</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.username}>
                  <td>{u.username}</td>
                  <td>{u.full_name}</td>
                  <td>
                    <select defaultValue={u.role} onChange={e => updateUser(u.username, 'role', e.target.value)}>
                      <option value="admin">Admin</option>
                      <option value="operator">Operator</option>
                    </select>
                  </td>
                  <td>
                    <select defaultValue={String(u.is_active)} onChange={e => updateUser(u.username, 'is_active', e.target.value === 'true')}>
                      <option value="true">Active</option>
                      <option value="false">Disabled</option>
                    </select>
                  </td>
                  <td><button className="btn btn-sm btn-primary" onClick={() => alert('Manage Areas not fully implemented')}>Manage Areas</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
