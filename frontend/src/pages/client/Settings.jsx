import { ThemeToggle } from '../../components/shared/ui';

const Settings = () => {
  return (
    <div className="animate-fade-in space-y-stack-lg max-w-3xl">
      <div className="flex items-center gap-4 border-b border-outline-variant dark:border-[#2A345E] pb-4 mb-8">
        <div className="w-12 h-12 bg-primary-container rounded-xl flex items-center justify-center">
          <span className="material-symbols-outlined text-on-primary-container text-[24px]">settings</span>
        </div>
        <div>
          <h1 className="font-headline-lg text-headline-lg text-primary dark:text-molten-primary">Settings</h1>
          <p className="text-arctic-text-muted dark:text-molten-text-muted font-body-sm">Configure your preferences and system options.</p>
        </div>
      </div>

      <section className="bg-arctic-surface dark:bg-molten-surface p-6 rounded-xl border border-outline-variant/50 dark:border-[#2A345E]/50 shadow-sm">
        <h2 className="font-headline-sm text-headline-sm mb-4 border-b border-outline-variant/30 dark:border-[#2A345E] pb-2">Appearance</h2>
        
        <div className="flex items-center justify-between mt-4">
          <div>
            <h3 className="font-bold text-on-surface dark:text-molten-text">Theme Preference</h3>
            <p className="text-sm text-arctic-text-muted dark:text-molten-text-muted mt-1">Switch between light and dark mode</p>
          </div>
          <ThemeToggle />
        </div>
      </section>
      
    </div>
  );
};

export default Settings;
