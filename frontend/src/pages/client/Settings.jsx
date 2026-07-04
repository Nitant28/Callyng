import { ThemeToggle } from '../../components/shared/ui';
import PageHeader from '../../components/ui/PageHeader';

const Settings = () => (
  <div className="app-page max-w-3xl">
    <PageHeader
      eyebrow="Settings"
      title="Settings"
      subtitle="Configure your preferences and system options."
      bordered
    />

    <section className="bg-arctic-surface dark:bg-molten-surface p-6 rounded-xl border border-outline-variant/50 dark:border-[#2A345E]/50 shadow-sm">
      <h2 className="section-title mb-4 border-b border-outline-variant/30 dark:border-[#2A345E] pb-2">
        Appearance
      </h2>

      <div className="flex items-center justify-between mt-4">
        <div>
          <h3 className="text-card-title font-semibold text-on-surface dark:text-molten-text">Theme Preference</h3>
          <p className="section-subtitle">Switch between light and dark mode</p>
        </div>
        <ThemeToggle />
      </div>
    </section>
  </div>
);

export default Settings;
