import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function Sidebar({ isOpen, onClose }: SidebarProps) {
  const { user, logout } = useAuth();

  return (
    <>
      <div
        className={`sidebar-overlay ${isOpen ? 'active' : ''}`}
        onClick={onClose}
      />
      <nav className={`sidebar ${isOpen ? 'open' : ''}`} id="sidebar">
        <div className="sidebar-header">
          <div className="logo">
            <i className="fas fa-shield-halved" />
            <span>IBVAP</span>
          </div>
          <small className="logo-subtitle">Border Surveillance AI</small>
        </div>

        <ul className="nav-links">
          <li>
            <NavLink to="/" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} end>
              <i className="fas fa-border-all" /><span>Dashboard</span>
            </NavLink>
          </li>
          <li>
            <NavLink to="/cameras" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <i className="fas fa-video" /><span>Cameras</span>
            </NavLink>
          </li>
          <li>
            <NavLink to="/alerts" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <i className="fas fa-bell" /><span>Alerts</span>
              <span className="badge" id="alert-badge" style={{ display: 'none' }}>0</span>
            </NavLink>
          </li>
          <li>
            <NavLink to="/events" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <i className="fas fa-list" /><span>Events</span>
            </NavLink>
          </li>
          <li>
            <NavLink to="/zones" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <i className="fas fa-draw-polygon" /><span>Zones</span>
            </NavLink>
          </li>
          <li>
            <NavLink to="/settings" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <i className="fas fa-gear" /><span>Settings</span>
            </NavLink>
          </li>
        </ul>

        <div className="sidebar-footer">
          <div className="user-info">
            <i className="fas fa-user-circle" />
            <span>{user?.email?.split('@')[0] || 'Operator'}</span>
          </div>
          <button onClick={logout} className="btn-logout" title="Log Out">
            <i className="fas fa-power-off" />
          </button>
        </div>
      </nav>
    </>
  );
}
