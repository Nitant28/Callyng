import React from 'react';

export const Button = React.forwardRef(({ 
  children, 
  variant = 'primary', 
  className = '', 
  isLoading, 
  disabled, 
  icon,
  ...props 
}, ref) => {
  const baseClasses = "flex items-center justify-center gap-2 py-4 px-8 rounded-lg font-headline-sm text-headline-sm transition-all duration-200 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed hover:-translate-y-[1px] active:scale-[0.98]";
  
  const variants = {
    primary: "bg-primary dark:bg-molten-primary text-on-primary dark:text-molten-bg inner-shadow-primary hover:shadow-lg",
    secondary: "bg-surface-container-high dark:bg-surface-variant/30 text-on-surface dark:text-molten-text hover:brightness-95",
    outline: "border border-outline-variant text-on-surface dark:text-molten-text hover:bg-surface-container dark:hover:bg-surface-variant/10",
    ghost: "text-primary dark:text-molten-primary hover:bg-primary/5",
    danger: "bg-error dark:bg-molten-error text-white hover:brightness-110",
  };

  return (
    <button 
      ref={ref}
      className={`${baseClasses} ${variants[variant]} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {children}
      {icon && !isLoading && (
        <span className="material-symbols-outlined transition-all">
          {icon}
        </span>
      )}
      {isLoading && (
        <div className="pulse-loader w-6 h-6 rounded-full border-2 border-current border-t-transparent animate-spin-custom"></div>
      )}
    </button>
  );
});

Button.displayName = 'Button';
