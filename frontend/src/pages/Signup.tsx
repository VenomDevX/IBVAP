import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '../api/supabase';

export default function Signup() {
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSignup = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const emailToUse = identifier.includes('@') ? identifier : `${identifier}@ibvap.local`;
      const displayUsername = identifier.includes('@') ? identifier.split('@')[0] : identifier;

      const { error: authError } = await supabase.auth.signUp({
        email: emailToUse,
        password: password,
        options: {
          data: {
            username: displayUsername
          }
        }
      });

      if (authError) throw authError;

      alert('Signup successful! Check your email or login directly.');
      navigate('/login');
    } catch (err: any) {
      setError(err.message || 'Error signing up');
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
            <p>Register New Account</p>
          </div>

          <form onSubmit={handleSignup}>
            <div className="form-group">
              <label htmlFor="identifier"><i className="fas fa-user" /> Username or Email</label>
              <input type="text" id="identifier" value={identifier} onChange={e => setIdentifier(e.target.value)} required placeholder="e.g. admin or operator@ibvap.gov" autoComplete="username" />
            </div>

            <div className="form-group">
              <label htmlFor="password"><i className="fas fa-lock" /> Password</label>
              <input type="password" id="password" value={password} onChange={e => setPassword(e.target.value)} required placeholder="Choose a password" autoComplete="new-password" />
            </div>

            {error && <div className="form-error">{error}</div>}

            <button type="submit" className="btn btn-primary btn-full" disabled={loading}>
              {loading ? <><i className="fas fa-spinner fa-spin" /> Creating account...</> : <><i className="fas fa-user-plus" /> Sign Up</>}
            </button>
          </form>

          <div className="login-footer" style={{ marginTop: 15 }}>
            <p>Already have an account? <a href="/login">Sign In</a></p>
          </div>
        </div>
      </div>
    </div>
  );
}
