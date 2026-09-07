import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '../api/supabase';

export default function Login() {
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      // If the user enters a username without an '@', append a default domain
      const emailToUse = identifier.includes('@') ? identifier : `${identifier}@ibvap.local`;

      const { error: authError } = await supabase.auth.signInWithPassword({
        email: emailToUse,
        password: password,
      });

      if (authError) throw authError;

      navigate('/');
    } catch (err: any) {
      setError(err.message || 'Invalid email or password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-body">
      <div className="login-container">
        <div className="login-card">
          <div className="login-header">
            <div className="login-logo">
              <i className="fas fa-shield-halved" />
            </div>
            <h1>IBVAP</h1>
            <p>Intelligent Border Video Analytics Platform</p>
          </div>

          <form onSubmit={handleLogin}>
            <div className="form-group">
              <label htmlFor="identifier"><i className="fas fa-user" /> Username or Email</label>
              <input type="text" id="identifier" value={identifier} onChange={e => setIdentifier(e.target.value)} required placeholder="e.g. admin or operator@ibvap.gov" autoComplete="username" />
            </div>

            <div className="form-group">
              <label htmlFor="password"><i className="fas fa-lock" /> Password</label>
              <input type="password" id="password" value={password} onChange={e => setPassword(e.target.value)} required placeholder="Enter password" autoComplete="current-password" />
            </div>

            {error && <div className="form-error">{error}</div>}

            <button type="submit" className="btn btn-primary btn-full" disabled={loading}>
              {loading ? <><i className="fas fa-spinner fa-spin" /> Signing in...</> : <><i className="fas fa-sign-in-alt" /> Sign In</>}
            </button>
          </form>

          <div className="login-footer">
            <p>Authorized personnel only</p>
            <p style={{ marginTop: 10 }}><a href="/signup">Create an Account</a></p>
          </div>
        </div>
      </div>
    </div>
  );
}
