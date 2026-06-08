import { useTheme } from '../../../hooks/useTheme';

import Sidebar from './Sidebar';
import { Link } from 'react-router-dom';

const Layout = ({ children }) => {
  const { theme, toggleTheme } = useTheme();

  const handleSignOut = () => {
    localStorage.removeItem('client_api_key');
    window.location.href = '/login';
  };

  return (
    <div className="bg-arctic-bg dark:bg-molten-bg text-on-surface dark:text-molten-text min-h-screen font-body-md selection:bg-primary/20 transition-colors duration-500">
      
      {/* TopNavBar */}
      <header className="fixed top-0 w-full z-50 bg-arctic-surface dark:bg-molten-surface border-b border-outline-variant dark:border-[#2A345E] shadow-[0_4px_20px_rgba(22,71,232,0.05)] dark:shadow-none transition-colors duration-500">
        <div className="flex justify-between items-center h-16 px-margin-desktop w-full mx-auto">
          <div className="flex items-center gap-8">
            <span className="font-headline-md text-headline-md font-extrabold text-primary dark:text-molten-primary">
              Aakashvani
            </span>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-primary/10 dark:bg-molten-primary/10 flex items-center justify-center text-primary dark:text-molten-primary font-bold border border-primary/20">
                P
              </div>
              <span className="font-label-md text-label-md font-bold text-on-surface dark:text-molten-text">
                Prowave
              </span>
            </div>
          </div>
        </div>
      </header>

      <Sidebar handleSignOut={handleSignOut} />

      {/* Main Content Area */}
      <main className="lg:ml-64 pt-24 px-margin-mobile md:px-margin-desktop pb-24 min-h-screen">
        <div className="max-w-container-max mx-auto">
          {children}
        </div>
      </main>

      {/* Mobile BottomNavBar */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-arctic-surface dark:bg-molten-surface border-t border-outline-variant dark:border-[#2A345E] flex justify-around items-center py-3 z-50">
        <Link className="flex flex-col items-center gap-1 text-on-surface-variant dark:text-molten-text-muted" to="/app">
          <span className="material-symbols-outlined">dashboard</span>
          <span className="text-[10px]">Home</span>
        </Link>
        <Link className="flex flex-col items-center gap-1 text-on-surface-variant dark:text-molten-text-muted" to="/app/calls">
          <span className="material-symbols-outlined">list_alt</span>
          <span className="text-[10px]">Logs</span>
        </Link>
      </nav>
      
    </div>
  );
};

export default Layout;
