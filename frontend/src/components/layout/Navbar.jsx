import { useEffect, useRef, useState } from 'react';
import GlobalSearch from './GlobalSearch';
import './Navbar.css';

const Navbar = ({ clientName = 'Client', onMenuToggle, onSignOut }) => {
  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);
  const searchShortcut = isMac ? '⌘K' : 'Ctrl K';

  const [searchOpen, setSearchOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef(null);

  const initials = clientName.split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase();

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setSearchOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    const handleClick = (e) => {
      if (profileRef.current && !profileRef.current.contains(e.target)) setProfileOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  return (
    <>
      <header className="av-navbar av-navbar--glass">
        <div className="av-navbar__inner">
          <div className="av-navbar__left">
            <button type="button" className="av-navbar__menu-btn" onClick={onMenuToggle} aria-label="Toggle menu">
              <span className="material-symbols-outlined">menu</span>
            </button>
            <button type="button" className="av-navbar__search" onClick={() => setSearchOpen(true)} aria-label="Open search">
              <span className="material-symbols-outlined av-navbar__search-icon">search</span>
              <span className="av-navbar__search-placeholder">Search Campaigns...</span>
              <kbd className="av-navbar__search-kbd">{searchShortcut}</kbd>
            </button>
          </div>

          <div className="av-navbar__spacer" aria-hidden />

          <div className="av-navbar__right">
            <div className="av-navbar__dropdown-wrap" ref={profileRef}>
              <button
                type="button"
                className="av-navbar__profile"
                onClick={() => setProfileOpen((v) => !v)}
              >
                <span className="av-navbar__profile-name">{clientName}</span>
                <div className="av-navbar__avatar">{initials}</div>
              </button>
              {profileOpen && (
                <div className="ds-dropdown av-navbar__dropdown av-navbar__dropdown--profile">
                  <p className="ds-dropdown__header">{clientName}</p>
                  <div className="ds-dropdown__divider" />
                  <button type="button" className="ds-dropdown__item" onClick={onSignOut}>
                    <span className="ds-dropdown__item-icon ds-dropdown__item-icon--danger">
                      <span className="material-symbols-outlined">logout</span>
                    </span>
                    <p className="ds-dropdown__item-title">Logout</p>
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>
      <GlobalSearch open={searchOpen} onClose={() => setSearchOpen(false)} />
    </>
  );
};

export default Navbar;
