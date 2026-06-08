import { Link, useLocation } from 'react-router-dom';

const Sidebar = ({ handleSignOut }) => {
  const location = useLocation();
  const path = location.pathname;

  return (
    <aside className="fixed left-0 top-16 h-[calc(100vh-64px)] w-64 bg-arctic-bg dark:bg-molten-bg border-r border-outline-variant dark:border-[#2A345E] hidden lg:flex flex-col p-4 space-y-2 transition-colors duration-500 z-40">
      <div className="mb-6 px-4 py-2">
        <h2 className="font-headline-sm text-headline-sm font-bold text-on-surface dark:text-molten-text">Aakashvani Ops</h2>
        <p className="font-body-sm text-body-sm text-arctic-text-muted dark:text-molten-text-muted">AI Voice Platform</p>
      </div>
      <nav className="space-y-1 flex-grow">
        <Link 
          to="/app"
          className={`flex items-center gap-3 px-4 py-3 rounded-lg font-bold transition-all ${
            path === '/app' || path.startsWith('/app/campaigns')
              ? 'bg-primary-container dark:bg-tertiary-container text-on-primary-container dark:text-on-tertiary-container active:scale-[0.98]'
              : 'text-arctic-text-muted dark:text-molten-text-muted hover:bg-surface-container dark:hover:bg-surface-variant/10 hover:translate-x-1'
          }`}
        >
          <span className="material-symbols-outlined">dashboard</span>
          <span className="font-label-md text-label-md">Dashboard</span>
        </Link>
        <Link 
          to="/app/calls"
          className={`flex items-center gap-3 px-4 py-3 rounded-lg font-bold transition-all ${
            path.startsWith('/app/calls')
              ? 'bg-primary-container dark:bg-tertiary-container text-on-primary-container dark:text-on-tertiary-container active:scale-[0.98]'
              : 'text-arctic-text-muted dark:text-molten-text-muted hover:bg-surface-container dark:hover:bg-surface-variant/10 hover:translate-x-1'
          }`}
        >
          <span className="material-symbols-outlined">description</span>
          <span className="font-label-md text-label-md">Logs</span>
        </Link>
        <Link 
          to="/app/settings"
          className={`flex items-center gap-3 px-4 py-3 rounded-lg font-bold transition-all ${
            path === '/app/settings'
              ? 'bg-primary-container dark:bg-tertiary-container text-on-primary-container dark:text-on-tertiary-container active:scale-[0.98]'
              : 'text-arctic-text-muted dark:text-molten-text-muted hover:bg-surface-container dark:hover:bg-surface-variant/10 hover:translate-x-1'
          }`}
        >
          <span className="material-symbols-outlined">settings</span>
          <span className="font-label-md text-label-md">Settings</span>
        </Link>
      </nav>
      <div className="pt-4 border-t border-outline-variant dark:border-[#2A345E] space-y-1">
        <button
          onClick={handleSignOut}
          className="w-full flex items-center gap-3 text-arctic-text-muted dark:text-molten-text-muted px-4 py-3 hover:bg-surface-container dark:hover:bg-surface-variant/10 rounded-lg transition-all cursor-pointer text-left"
        >
          <span className="material-symbols-outlined">logout</span>
          <span className="font-label-md text-label-md">Sign Out</span>
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;
