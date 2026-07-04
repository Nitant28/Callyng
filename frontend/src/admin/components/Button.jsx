import React from 'react';

export default function Button({ 
  children, 
  variant = 'primary', 
  onClick, 
  type = 'button', 
  disabled = false, 
  className = '', 
  icon = null 
}) {
  const baseClasses = 'btn flex items-center justify-center disabled:opacity-50 disabled:pointer-events-none';
  
  const variants = {
    primary: 'btn-primary',
    secondary: 'btn-secondary',
    danger: 'bg-error text-on-error hover:bg-error/90 border border-transparent',
    outline: 'border border-outline text-on-background hover:bg-surface-container-low',
    text: 'text-primary hover:bg-surface-container-low'
  };

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`${baseClasses} ${variants[variant]} ${className}`}
    >
      {icon && <span className="material-symbols-outlined mr-2 text-sm">{icon}</span>}
      {children}
    </button>
  );
}
