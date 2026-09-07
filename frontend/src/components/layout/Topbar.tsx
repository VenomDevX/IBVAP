import { useState, useEffect } from 'react';
import { useTheme } from '../../context/ThemeContext';

interface TopbarProps {
  title: string;
  onMenuToggle: () => void;
}

export default function Topbar({ title, onMenuToggle }: TopbarProps) {
  const { isLight, toggleTheme } = useTheme();
  const [datetime, setDatetime] = useState('');

  useEffect(() => {
    const update = () => {
      setDatetime(
        new Date().toLocaleString('en-IN', {
          weekday: 'short', day: '2-digit', month: 'short',
          hour: '2-digit', minute: '2-digit', second: '2-digit',
          hour12: false,
        })
      );
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="menu-toggle" onClick={onMenuToggle}>
          <i className="fas fa-bars" />
        </button>
        <h1 className="page-title">{title}</h1>
      </div>
      <div className="topbar-right">
        <button onClick={toggleTheme} className="btn-icon" id="theme-toggle" title="Toggle Theme">
          <i className={isLight ? 'fas fa-sun' : 'fas fa-moon'} />
        </button>
        <div className="system-status" id="system-status">
          <span className="status-dot online" />
          <span>System Online</span>
        </div>
        <div className="datetime">{datetime}</div>
      </div>
    </header>
  );
}
