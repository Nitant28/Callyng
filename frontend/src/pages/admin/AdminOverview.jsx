import React, { useState, useEffect } from 'react';
import adminApi from '../../api/admin';
import './AdminOverview.css';

const AnimatedCounter = ({ targetValue }) => {
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (targetValue === undefined || targetValue === null) return;
    const duration = 1500;
    const frameDuration = 1000 / 60;
    const totalFrames = Math.round(duration / frameDuration);
    let frame = 0;

    const easeOutQuad = t => t * (2 - t);

    const update = () => {
      frame++;
      const progress = easeOutQuad(frame / totalFrames);
      setValue(Math.round(targetValue * progress));

      if (frame < totalFrames) {
        requestAnimationFrame(update);
      } else {
        setValue(targetValue);
      }
    };

    update();
  }, [targetValue]);

  return <>{value.toLocaleString()}</>;
};

export default function AdminOverview() {
  const [stats, setStats] = useState({
    total_calls_today: 0,
    active_campaigns: 0,
    credits_burned: 0,
  });
  
  const [health, setHealth] = useState({
    status: 'unknown',
    plivo_balance: null,
    dialer_tasks: 0,
    active_calls: 0,
    pool: { size: 0, idle: 0 },
  });
  const [error, setError] = useState(null);

  const [barsHeights, setBarsHeights] = useState([12, 16, 8, 14, 10, 15]);

  useEffect(() => {
    // Equalizer height randomization
    const interval = setInterval(() => {
      setBarsHeights(prev => prev.map(() => Math.floor(Math.random() * (24 - 8 + 1)) + 8));
    }, 150);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statsRes, healthRes] = await Promise.all([
          adminApi.get('/internal/stats'),
          adminApi.get('/internal/health')
        ]);
        
        setStats({
          total_calls_today: statsRes.data.total_calls_today || 0,
          active_campaigns: statsRes.data.active_campaigns || 0,
          credits_burned: statsRes.data.total_credits_used_today || 0,
        });
        
        setHealth({
          status: healthRes.data.status || 'unknown',
          plivo_balance: healthRes.data.plivo_balance,
          dialer_tasks: healthRes.data.dialer_tasks || 0,
          active_calls: healthRes.data.active_calls || 0,
          pool: healthRes.data.pool || { size: 0, idle: 0 },
        });
        setError(null);
      } catch (err) {
        console.error("Failed to fetch admin overview data", err);
        setError("Failed to fetch dashboard stats.");
      }
    };
    
    fetchData();
    const pollInterval = setInterval(fetchData, 10000); // Poll every 10s
    return () => clearInterval(pollInterval);
  }, []);

  return (
    <>
      <header className="mb-stack-lg stagger-in" style={{ animationDelay: '0.1s' }}>
        <h1 className="font-headline-lg text-headline-lg text-on-background dark:text-molten-text">Admin Overview</h1>
        <p className="font-body-md text-body-md text-on-surface-variant dark:text-molten-text-muted">Real-time telecommunications infrastructure monitoring.</p>
        {error && (
          <div className="mt-4 p-4 bg-error-container text-on-error-container rounded-lg flex items-center gap-2">
            <span className="material-symbols-outlined">error</span>
            <span>{error}</span>
          </div>
        )}
      </header>

      {/* Big Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-gutter mb-stack-lg">
        {/* Card 1: Total Calls Today */}
        <div className="arctic-card molten-card p-6 stagger-in" style={{ animationDelay: '0.2s' }}>
          <div className="flex justify-between items-start mb-4">
            <span className="text-on-surface-variant dark:text-molten-text-muted font-label-md">Total Calls Today</span>
            <span className="material-symbols-outlined text-primary dark:text-molten-primary">call</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="font-headline-xl text-headline-xl text-on-background dark:text-molten-text tabular-nums">
              <AnimatedCounter targetValue={stats.total_calls_today} />
            </span>
            <div className="flex items-center text-secondary dark:text-molten-success font-label-sm">
              <span className="material-symbols-outlined text-sm">trending_up</span>
              <span>+12%</span>
            </div>
          </div>
          <div className="mt-4 w-full h-1 bg-surface-container-low dark:bg-[#2A345E] rounded-full overflow-hidden">
            <div className="h-full bg-primary dark:bg-molten-primary w-3/4"></div>
          </div>
        </div>

        {/* Card 2: Active Campaigns */}
        <div className="arctic-card molten-card p-6 stagger-in" style={{ animationDelay: '0.3s' }}>
          <div className="flex justify-between items-start mb-4">
            <span className="text-on-surface-variant dark:text-molten-text-muted font-label-md">Active Campaigns</span>
            <span className="material-symbols-outlined text-primary dark:text-molten-primary">rocket_launch</span>
          </div>
          <div className="flex items-center gap-6">
            <span className="font-headline-xl text-headline-xl text-on-background dark:text-molten-text tabular-nums">
              <AnimatedCounter targetValue={stats.active_campaigns} />
            </span>
            {/* Live Equalizer SVG Animation */}
            <div className="flex items-end gap-[3px] h-8 mb-1">
              <div className="wave-bar w-1 bg-primary dark:bg-molten-primary rounded-full" style={{ animationDelay: '0s', height: `${barsHeights[0]}px` }}></div>
              <div className="wave-bar w-1 bg-secondary dark:bg-molten-success rounded-full" style={{ animationDelay: '0.2s', height: `${barsHeights[1]}px` }}></div>
              <div className="wave-bar w-1 bg-primary dark:bg-molten-primary rounded-full" style={{ animationDelay: '0.4s', height: `${barsHeights[2]}px` }}></div>
              <div className="wave-bar w-1 bg-secondary dark:bg-molten-success rounded-full" style={{ animationDelay: '0.1s', height: `${barsHeights[3]}px` }}></div>
              <div className="wave-bar w-1 bg-primary dark:bg-molten-primary rounded-full" style={{ animationDelay: '0.3s', height: `${barsHeights[4]}px` }}></div>
              <div className="wave-bar w-1 bg-secondary dark:bg-molten-success rounded-full" style={{ animationDelay: '0.5s', height: `${barsHeights[5]}px` }}></div>
            </div>
          </div>
          <p className="mt-4 font-body-sm text-body-sm text-on-surface-variant dark:text-molten-text-muted italic">Pulse detection: Normal</p>
        </div>

        {/* Card 3: Credits Burned */}
        <div className="arctic-card molten-card p-6 stagger-in" style={{ animationDelay: '0.4s' }}>
          <div className="flex justify-between items-start mb-4">
            <span className="text-on-surface-variant dark:text-molten-text-muted font-label-md">Credits Burned</span>
            <span className="material-symbols-outlined text-primary dark:text-molten-primary">payments</span>
          </div>
          <div className="flex items-baseline gap-1">
            <span className="font-headline-xl text-headline-xl text-on-background dark:text-molten-text">₹</span>
            <span className="font-headline-xl text-headline-xl text-on-background dark:text-molten-text tabular-nums">
              <AnimatedCounter targetValue={stats.credits_burned} />
            </span>
            <div className="flex items-center text-error dark:text-molten-error font-label-sm ml-2">
              <span className="material-symbols-outlined text-sm">trending_down</span>
              <span>-5%</span>
            </div>
          </div>
          <p className="mt-4 font-body-sm text-body-sm text-on-surface-variant dark:text-molten-text-muted">Estimated burn rate: ₹2.4k/hr</p>
        </div>
      </div>

      {/* Bento Layout Sections */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-gutter stagger-in" style={{ animationDelay: '0.5s' }}>
        {/* Infrastructure Status */}
        <div className="lg:col-span-8 arctic-card molten-card p-6 overflow-hidden relative">
          <div className="flex justify-between items-center mb-6">
            <h2 className="font-headline-sm text-headline-sm text-on-background dark:text-molten-text">Infrastructure Status</h2>
            <div className="flex gap-2">
              <span className={`px-3 py-1 text-xs font-bold rounded-full border ${health.status === 'ok' ? 'bg-secondary-fixed-dim/15 text-secondary dark:text-molten-success border-secondary/20' : 'bg-surface-container-high dark:bg-[#1A1C24] text-on-surface-variant dark:text-molten-text-muted border-outline dark:border-[#2A345E]'}`}>
                {health.status === 'ok' ? 'All Systems Nominal' : 'Systems Checking...'}
              </span>
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
            <div className="p-4 bg-surface-container-low dark:bg-[#1A1C24] rounded-lg">
              <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mb-1">Plivo Balance</p>
              <p className="text-xl font-bold text-on-background dark:text-molten-text">
                {health.plivo_balance !== null && health.plivo_balance !== undefined ? `₹${(health.plivo_balance * 80.0229).toFixed(2)}` : 'N/A'}
              </p>
            </div>
            <div className="p-4 bg-surface-container-low dark:bg-[#1A1C24] rounded-lg">
              <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mb-1">Dialer Tasks</p>
              <p className="text-xl font-bold text-on-background dark:text-molten-text">
                {health.dialer_tasks} <span className="text-xs font-normal text-on-surface-variant">active</span>
              </p>
            </div>
            <div className="p-4 bg-surface-container-low dark:bg-[#1A1C24] rounded-lg">
              <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mb-1">DB Pool Size</p>
              <p className="text-xl font-bold text-on-background dark:text-molten-text">
                {health.pool.size} <span className="text-xs font-normal text-on-surface-variant">conns</span>
              </p>
            </div>
            <div className="p-4 bg-surface-container-low dark:bg-[#1A1C24] rounded-lg">
              <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mb-1">DB Pool Idle</p>
              <p className="text-xl font-bold text-on-background dark:text-molten-text">
                {health.pool.idle} <span className="text-xs font-normal text-on-surface-variant">idle</span>
              </p>
            </div>
          </div>
        </div>

        {/* Recent Activity / Logs */}
        <div className="lg:col-span-4 arctic-card molten-card p-6 flex flex-col">
          <h2 className="font-headline-sm text-headline-sm text-on-background dark:text-molten-text mb-6">Security Logs</h2>
          <div className="space-y-4 overflow-y-auto max-h-64 pr-2">
            <div className="flex gap-4 items-start p-3 hover:bg-surface-container-low dark:hover:bg-[#1A1C24] rounded-lg transition-colors cursor-pointer">
              <span className="material-symbols-outlined text-secondary dark:text-molten-success">verified_user</span>
              <div>
                <p className="font-label-md text-label-md text-on-background dark:text-molten-text">Admin Login</p>
                <p className="font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted">IP: 192.168.1.45 • 2m ago</p>
              </div>
            </div>
            <div className="flex gap-4 items-start p-3 hover:bg-surface-container-low dark:hover:bg-[#1A1C24] rounded-lg transition-colors cursor-pointer">
              <span className="material-symbols-outlined text-error dark:text-molten-error">lock_reset</span>
              <div>
                <p className="font-label-md text-label-md text-on-background dark:text-molten-text">API Key Rotation</p>
                <p className="font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted">Campaign: Alpha-Niner • 15m ago</p>
              </div>
            </div>
            <div className="flex gap-4 items-start p-3 hover:bg-surface-container-low dark:hover:bg-[#1A1C24] rounded-lg transition-colors cursor-pointer">
              <span className="material-symbols-outlined text-primary dark:text-molten-primary">info</span>
              <div>
                <p className="font-label-md text-label-md text-on-background dark:text-molten-text">New Client Onboarded</p>
                <p className="font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted">Studio Flux Inc. • 1h ago</p>
              </div>
            </div>
          </div>
          <button className="mt-auto pt-4 text-center font-label-md text-primary dark:text-molten-primary hover:underline transition-all">View All Logs</button>
        </div>
      </div>

      {/* Global Map Section */}
      <div className="mt-stack-lg arctic-card molten-card p-0 overflow-hidden h-[400px] relative stagger-in" style={{ animationDelay: '0.6s' }}>
        <div className="absolute top-6 left-6 z-10 p-4 bg-arctic-surface/80 dark:bg-molten-surface/80 backdrop-blur-md rounded-lg border border-outline-variant/30">
          <h3 className="font-headline-sm text-headline-sm text-on-background dark:text-molten-text">Call Distribution</h3>
          <p className="font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted">Real-time global connectivity</p>
        </div>
        <img 
          className="w-full h-full object-cover grayscale opacity-60 dark:opacity-40 map-glow transition-all duration-700" 
          alt="A highly detailed global world map visualization on a dark background." 
          src="https://lh3.googleusercontent.com/aida-public/AB6AXuC7miZYDITZfupetGGSJ3KT673NlHQZWY38MSIm_rHFObajwouuK72mvHx1Ve-TZ4LtX98Hmv6cv7UuPzwZIFuiDEgigwt3zIw6ZxGk4cGWwpezVvcnJT8QuxQfLFYS89mhzKaZ2Zi6KGEOrUo_KLx93RZscVghZLsLCKN05S6VmWuyoFjz7ms8pCv9_whXaC82rKnewkgf6-dOoU_sUn1CSzIRMIxsjMypXUGz-kBiy9-MLjSW-3d-tO2XaCGfDYpkS6aqGWjKEGw" 
        />
        <div className="absolute inset-0 bg-gradient-to-t from-arctic-bg dark:from-molten-bg to-transparent opacity-60"></div>
      </div>
    </>
  );
}
