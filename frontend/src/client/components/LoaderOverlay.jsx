import React, { useEffect, useState } from 'react';

const LoaderOverlay = ({ isVisible, message = "System Initializing..." }) => {
  const [shouldRender, setShouldRender] = useState(isVisible);

  useEffect(() => {
    if (isVisible) {
      setShouldRender(true);
    } else {
      const timer = setTimeout(() => setShouldRender(false), 500); // Allow fade out
      return () => clearTimeout(timer);
    }
  }, [isVisible]);

  if (!shouldRender) return null;

  return (
    <div
      className={`fixed inset-0 z-[100] bg-arctic-bg/90 dark:bg-molten-bg/90 backdrop-blur-sm flex flex-col items-center justify-center transition-opacity duration-500 ${
        isVisible ? 'opacity-100' : 'opacity-0'
      }`}
    >
      <div className="flex items-center justify-center gap-2 h-16">
        {/*
          Light Mode: bg-primary (0031b9), shadow color 0031b9
          Dark Mode: bg-molten-primary (4D75FA), shadow color 4D75FA
          Accent (middle ones):
          Light Mode: bg-secondary (006b5c) or success (00C8AE), shadow color 00C8AE
          Dark Mode: bg-molten-success (FFB932), shadow color FFB932
        */}
        <style>{`
          .loader-bar-primary {
            background-color: var(--color-primary);
            box-shadow: 0 0 12px var(--color-primary);
          }
          .dark .loader-bar-primary {
            background-color: var(--color-molten-primary);
            box-shadow: 0 0 12px var(--color-molten-primary);
          }
          .loader-bar-accent {
            background-color: var(--color-secondary-fixed-dim);
            box-shadow: 0 0 12px var(--color-secondary-fixed-dim);
          }
          .dark .loader-bar-accent {
            background-color: var(--color-molten-success);
            box-shadow: 0 0 12px var(--color-molten-success);
          }
        `}</style>

        <div className="w-1.5 rounded-full loader-bar-primary animate-[soundwave_1.2s_ease-in-out_infinite]" style={{ animationDelay: '-1.2s' }}></div>
        <div className="w-1.5 rounded-full loader-bar-primary animate-[soundwave_1.2s_ease-in-out_infinite]" style={{ animationDelay: '-1.05s' }}></div>
        <div className="w-1.5 rounded-full loader-bar-accent animate-[soundwave_1.2s_ease-in-out_infinite]" style={{ animationDelay: '-0.9s' }}></div>
        <div className="w-1.5 rounded-full loader-bar-primary animate-[soundwave_1.2s_ease-in-out_infinite]" style={{ animationDelay: '-0.75s' }}></div>
        <div className="w-1.5 rounded-full loader-bar-primary animate-[soundwave_1.2s_ease-in-out_infinite]" style={{ animationDelay: '-0.6s' }}></div>
        <div className="w-1.5 rounded-full loader-bar-primary animate-[soundwave_1.2s_ease-in-out_infinite]" style={{ animationDelay: '-0.45s' }}></div>
        <div className="w-1.5 rounded-full loader-bar-accent animate-[soundwave_1.2s_ease-in-out_infinite]" style={{ animationDelay: '-0.3s' }}></div>
        <div className="w-1.5 rounded-full loader-bar-primary animate-[soundwave_1.2s_ease-in-out_infinite]" style={{ animationDelay: '-0.15s' }}></div>
        <div className="w-1.5 rounded-full loader-bar-primary animate-[soundwave_1.2s_ease-in-out_infinite]" style={{ animationDelay: '0s' }}></div>
      </div>
      <p className="mt-8 font-label-sm text-[12px] font-medium text-arctic-text-muted dark:text-molten-text-muted tracking-[2px] uppercase">
        {message}
      </p>
    </div>
  );
};

export default LoaderOverlay;
