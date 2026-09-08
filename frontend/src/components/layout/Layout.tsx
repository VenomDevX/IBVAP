import { useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import ToastContainer from '../toast/ToastContainer';

const PAGE_TITLES: Record<string, string> = {
  '/': 'Command Dashboard',
  '/cameras': 'Camera Management',
  '/multiview': 'Multi-Camera View',
  '/map': 'Global Map View',
  '/alerts': 'Alert Center',
  '/events': 'Event History',
  '/zones': 'Virtual Zone Configuration',
  '/settings': 'System Settings',
  '/audit': 'Audit Logs',
};

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();

  const title = PAGE_TITLES[location.pathname] || 'IBVAP';

  return (
    <>
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <main className="main-content">
        <Topbar title={title} onMenuToggle={() => setSidebarOpen(prev => !prev)} />
        <div className="content">
          <Outlet />
        </div>
      </main>
      <ToastContainer />
    </>
  );
}
