'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { apiFetch } from '@/src/api/client';
import { useAuth } from '@/src/context/AuthContext';
import { useTheme } from '@/src/context/ThemeContext';
import { cn } from '@/src/lib/cn';
import Card from '@/src/components/ui/Card';
import Badge from '@/src/components/ui/Badge';
import StatusDot from '@/src/components/ui/StatusDot';
import { Button } from '@/src/components/ui/Button';
import Icon from '@/src/components/ui/Icon';
import type { DashboardSummary } from '@/src/types';
import { useSystemHealth } from '@/src/hooks/useSystemHealth';

function Row({ label, children, description }: { label: string; children: ReactNode; description?: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-default py-4 text-[0.85rem] last:border-0">
      <div>
        <div className="text-fg font-medium">{label}</div>
        {description && <div className="text-fg-subtle text-xs mt-0.5">{description}</div>}
      </div>
      <div className="flex items-center gap-2 text-right text-fg-muted font-medium">{children}</div>
    </div>
  );
}

const ROLE_TONE = { admin: 'accent', operator: 'info', auditor: 'warning' } as const;

export default function SettingsPage() {
  const { user, role, allowedAreas, profileError, logout } = useAuth();
  const { isLight, setTheme } = useTheme();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const { health, reachable } = useSystemHealth();
  
  const [activeTab, setActiveTab] = useState('profile');

  const username = user?.email?.split('@')[0] || 'User';

  useEffect(() => {
    apiFetch('/api/statistics/summary').then(r => r.json()).then(setSummary).catch(() => setSummary(null));
  }, []);

  const online = summary?.online_cameras ?? 0;
  const total = summary?.total_cameras ?? 0;
  const camPct = total ? Math.round((online / total) * 100) : 0;

  return (
    <div className="flex h-[calc(100vh-4rem)] w-full text-fg bg-bg">
      {/* Settings Sub-Sidebar */}
      <div className="w-64 border-r border-default flex flex-col h-full bg-base">
        <div className="p-4">
          <div className="relative">
            <input 
              type="text" 
              placeholder="Search settings..." 
              className="w-full bg-surface border border-default rounded py-2 pl-9 pr-4 text-sm focus:outline-none focus:border-accent"
            />
            <Icon name="magnifying-glass" className="absolute left-3 top-2.5 text-fg-muted" />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto py-2">
          <div className="px-3 mb-6">
            <h3 className="text-xs font-semibold text-fg-muted mb-2 px-3 uppercase tracking-wider">General</h3>
            <button 
              onClick={() => setActiveTab('profile')}
              className={cn(
                "w-full text-left px-3 py-2 text-sm rounded flex items-center gap-3",
                activeTab === 'profile' ? "bg-surface text-fg font-medium" : "text-fg-subtle hover:text-fg"
              )}
            >
              <Icon name="user" className="w-4" /> Profile
            </button>
            <button 
              onClick={() => setActiveTab('appearance')}
              className={cn(
                "w-full text-left px-3 py-2 text-sm rounded flex items-center gap-3",
                activeTab === 'appearance' ? "bg-surface text-fg font-medium" : "text-fg-subtle hover:text-fg"
              )}
            >
              <Icon name="palette" className="w-4" /> Appearance
            </button>
          </div>

          <div className="px-3 mb-6">
            <h3 className="text-xs font-semibold text-fg-muted mb-2 px-3 uppercase tracking-wider">System</h3>
            <button 
              onClick={() => setActiveTab('health')}
              className={cn(
                "w-full text-left px-3 py-2 text-sm rounded flex items-center gap-3",
                activeTab === 'health' ? "bg-surface text-fg font-medium" : "text-fg-subtle hover:text-fg"
              )}
            >
              <Icon name="heart-pulse" className="w-4" /> System Health
            </button>
          </div>
        </div>
      </div>

      {/* Main Settings Content */}
      <div className="flex-1 overflow-y-auto p-10 bg-bg">
        <div className="max-w-4xl">
          
          {activeTab === 'profile' && (
            <>
              <h1 className="text-2xl font-semibold mb-1">Profile & Session</h1>
              <p className="text-fg-muted text-sm mb-8">Manage your account details and current session.</p>

              <div className="grid gap-6">
                {/* Premium Card 1 */}
                <div className="border border-default rounded bg-surface p-6 shadow-sm">
                  <div className="flex items-center gap-3 mb-2">
                    <div className="w-10 h-10 rounded-full bg-accent/10 flex items-center justify-center text-accent">
                      <Icon name="id-badge" className="text-lg" />
                    </div>
                    <h2 className="text-lg font-medium">User Information</h2>
                  </div>
                  <div className="mt-4">
                    <Row label="Name" description="Your display name">{username}</Row>
                    <Row label="Email" description="Primary contact email">{user?.email || '—'}</Row>
                    <Row label="Role" description="Your system access level">
                      <Badge tone={ROLE_TONE[(role ?? 'operator') as keyof typeof ROLE_TONE] ?? 'neutral'}>{role ?? 'unknown'}</Badge>
                    </Row>
                    <Row label="Assigned areas" description="Zones you can monitor">
                      {profileError ? 'Authorization unavailable' : allowedAreas?.length ? allowedAreas.join(', ') : 'All areas'}
                    </Row>
                  </div>
                </div>

                {/* Premium Card 2 */}
                <div className="border border-default rounded bg-surface p-6 shadow-sm">
                  <div className="flex items-center gap-3 mb-2">
                    <div className="w-10 h-10 rounded-full bg-danger/10 flex items-center justify-center text-danger">
                      <Icon name="right-from-bracket" className="text-lg" />
                    </div>
                    <h2 className="text-lg font-medium">Session Management</h2>
                  </div>
                  <div className="mt-4">
                    <Row label="Signed in as">{user?.email || username}</Row>
                    <div className="flex items-center justify-between py-4">
                      <p className="text-[0.8rem] leading-relaxed text-fg-subtle max-w-sm">
                        Sessions expire automatically after inactivity. Make sure to sign out on shared machines to protect your account.
                      </p>
                      <Button variant="danger" onClick={logout}>
                        <Icon name="power-off" className="mr-2" /> Sign out
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}

          {activeTab === 'health' && (
            <>
              <h1 className="text-2xl font-semibold mb-1">System Health</h1>
              <p className="text-fg-muted text-sm mb-8">Real-time diagnostics and performance metrics.</p>

              <div className="border border-default rounded bg-surface p-6 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="w-10 h-10 rounded-full bg-success/10 flex items-center justify-center text-success">
                    <Icon name="heart-pulse" className="text-lg" />
                  </div>
                  <h2 className="text-lg font-medium">Diagnostics</h2>
                </div>
                
                <div className="mt-4">
                  <Row label="Backend API" description="Main server connectivity">
                    <StatusDot status={health?.ready ? 'online' : 'offline'} />
                    <span className={cn(health?.ready ? 'text-success' : reachable === false ? 'text-danger' : 'text-warning')}>
                      {reachable == null ? 'Checking…' : reachable === false ? 'Unreachable' : health?.ready ? 'Operational' : 'Degraded'}
                    </span>
                  </Row>
                  <Row label="AI Pipeline" description="Inference engine status">{health?.pipeline ?? 'Unknown'}</Row>
                  
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 py-4 border-b border-default">
                    <div className="border border-default rounded-lg p-3 bg-bg">
                      <div className="text-xs text-fg-muted mb-1">Object Detector</div>
                      <div className="font-medium text-sm flex items-center gap-2">
                        <StatusDot status={health?.models?.detector ? 'online' : 'offline'} />
                        {health?.models?.detector ? 'Loaded' : 'Unavailable'}
                      </div>
                    </div>
                    <div className="border border-default rounded-lg p-3 bg-bg">
                      <div className="text-xs text-fg-muted mb-1">Fine Classifier</div>
                      <div className="font-medium text-sm flex items-center gap-2">
                        <StatusDot status={health?.models?.fine_classifier ? 'online' : 'offline'} />
                        {health?.models?.fine_classifier ? 'Loaded' : 'Unavailable'}
                      </div>
                    </div>
                    <div className="border border-default rounded-lg p-3 bg-bg">
                      <div className="text-xs text-fg-muted mb-1">Face Recognition</div>
                      <div className="font-medium text-sm flex items-center gap-2">
                        <StatusDot status={health?.models?.face_recognition ? 'online' : 'offline'} />
                        {health?.models?.face_recognition ? 'Loaded' : 'Disabled'}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between gap-4 border-b border-default py-5 text-[0.85rem]">
                    <div>
                      <div className="text-fg font-medium">Cameras Online</div>
                      <div className="text-fg-subtle text-xs mt-0.5">Active feeds in the network</div>
                    </div>
                    <span className="flex items-center gap-3">
                      <span className="inline-block h-2 w-32 overflow-hidden rounded-full bg-default">
                        <span className="block h-full bg-success rounded-full" style={{ width: `${camPct}%` }} />
                      </span>
                      <span className="tabular-nums text-fg font-medium">{online} / {total}</span>
                    </span>
                  </div>
                  
                  <Row label="Active Alerts" description="Unreviewed incidents">{summary?.unreviewed_alerts ?? 0}</Row>
                  <Row label="Active Tracks" description="Entities currently tracked">{summary?.active_tracks ?? 0}</Row>
                  <Row label="Evidence Capture" description="Automated snapshot recording">
                    <span className={cn(
                      "px-2 py-1 rounded text-xs font-medium",
                      health?.storage?.capture_enabled ? "bg-success/10 text-success" : "bg-warning/10 text-warning"
                    )}>
                      {health?.storage?.capture_enabled ? 'Enabled' : 'Paused'}
                    </span>
                  </Row>
                  <Row label="Evidence Storage" description="Storage consumption">
                    {health?.storage?.snapshot_storage_mb == null ? 'Not measured' : `${health.storage.snapshot_storage_mb} / ${health.storage.snapshot_storage_limit_mb} MB`}
                  </Row>
                </div>
              </div>
            </>
          )}

          {activeTab === 'appearance' && (
            <>
              <h1 className="text-2xl font-semibold mb-1">Appearance</h1>
              <p className="text-fg-muted text-sm mb-8">Choose how the application looks on this device.</p>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-10">
                {/* Theme Cards */}
                <div 
                  onClick={() => setTheme(false)}
                  className={cn(
                    "border-2 rounded p-4 cursor-pointer transition-all",
                    !isLight ? "border-accent bg-surface" : "border-default bg-base opacity-70 hover:opacity-100"
                  )}
                >
                  <div className="h-20 bg-[#111] rounded mb-4 flex items-center justify-center border border-[#333]">
                    <div className="w-8 h-1 bg-gray-500 rounded-full"></div>
                  </div>
                  <h3 className="font-medium text-sm text-fg">Dark Theme</h3>
                  <p className="text-xs text-fg-muted">Default</p>
                </div>

                <div 
                  onClick={() => setTheme(true)}
                  className={cn(
                    "border-2 rounded p-4 cursor-pointer transition-all",
                    isLight ? "border-accent bg-surface" : "border-default bg-white text-black opacity-70 hover:opacity-100"
                  )}
                >
                  <div className="h-20 bg-gray-100 rounded mb-4 flex items-center justify-center border border-gray-200">
                    <div className="w-8 h-1 bg-gray-300 rounded-full"></div>
                  </div>
                  <h3 className={cn("font-medium text-sm", isLight ? "text-fg" : "text-black")}>Light Theme</h3>
                  <p className={cn("text-xs", isLight ? "text-fg-muted" : "text-gray-500")}>Clean and bright</p>
                </div>

                <div className="border border-default rounded p-4 bg-emerald-950/30 cursor-pointer opacity-70 hover:opacity-100 transition-all">
                  <div className="h-20 bg-emerald-950 rounded mb-4 flex items-center justify-center border border-emerald-900">
                    <div className="w-8 h-1 bg-emerald-500 rounded-full"></div>
                  </div>
                  <h3 className="font-medium text-sm text-emerald-400">Green Theme</h3>
                  <p className="text-xs text-emerald-500/70">Natural and dark</p>
                </div>
              </div>

              <div className="mb-10">
                <h3 className="text-sm font-medium mb-4 text-fg">Accent Color</h3>
                <div className="flex gap-3">
                  <div className="w-7 h-7 rounded-full bg-white border-2 border-accent ring-2 ring-base ring-offset-1 ring-offset-accent cursor-pointer"></div>
                  <div className="w-7 h-7 rounded-full bg-blue-500 cursor-pointer hover:scale-110 transition-transform"></div>
                  <div className="w-7 h-7 rounded-full bg-teal-400 cursor-pointer hover:scale-110 transition-transform"></div>
                  <div className="w-7 h-7 rounded-full bg-purple-500 cursor-pointer hover:scale-110 transition-transform"></div>
                  <div className="w-7 h-7 rounded-full bg-yellow-500 cursor-pointer hover:scale-110 transition-transform"></div>
                  <div className="w-7 h-7 rounded-full bg-rose-500 cursor-pointer hover:scale-110 transition-transform"></div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-10">
                <div>
                  <div className="flex justify-between items-center mb-4">
                    <label className="text-sm font-medium text-fg">UI Scale</label>
                  </div>
                  <div className="relative pt-2">
                    <div className="h-1.5 w-full bg-surface rounded-full overflow-hidden border border-default">
                      <div className="h-full w-1/2 bg-accent rounded-full"></div>
                    </div>
                    <div className="absolute top-1 left-1/2 w-4 h-4 bg-white rounded-full -ml-2 shadow-md border border-gray-300"></div>
                    <div className="flex justify-between mt-3 text-xs text-fg-muted font-medium">
                      <span>Compact</span>
                      <span>Default</span>
                      <span>Large</span>
                    </div>
                  </div>
                </div>

                <div>
                  <label className="text-sm font-medium block mb-3 text-fg">Typography</label>
                  <select className="w-full bg-surface border border-default rounded py-2.5 px-3 text-sm text-fg focus:outline-none focus:border-accent">
                    <option>Monospace</option>
                    <option>Inter</option>
                    <option>System Default</option>
                  </select>
                </div>

                <div>
                  <label className="text-sm font-medium block mb-3 text-fg">Interface Roundness</label>
                  <select className="w-full bg-surface border border-default rounded py-2.5 px-3 text-sm text-fg focus:outline-none focus:border-accent">
                    <option>Default</option>
                    <option>Sharp</option>
                    <option>Rounded</option>
                  </select>
                </div>

                <div>
                  <label className="text-sm font-medium block mb-3 text-fg">App Opacity</label>
                  <select className="w-full bg-surface border border-default rounded py-2.5 px-3 text-sm text-fg focus:outline-none focus:border-accent">
                    <option>Transparent</option>
                    <option>Opaque</option>
                  </select>
                </div>
              </div>
            </>
          )}

        </div>
      </div>
    </div>
  );
}
