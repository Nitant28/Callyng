import './SwarnaHeroArt.css';

/** Soft 3D-style phone scene used on the access landing. */
const SwarnaHeroArt = () => (
  <div className="sw-hero-art" aria-hidden="true">
    <span className="sw-hero-art__blob sw-hero-art__blob--a" />
    <span className="sw-hero-art__blob sw-hero-art__blob--b" />
    <span className="sw-hero-art__chip sw-hero-art__chip--mail">
      <span className="material-symbols-outlined">mail</span>
    </span>
    <span className="sw-hero-art__chip sw-hero-art__chip--call">
      <span className="material-symbols-outlined">call</span>
    </span>
    <span className="sw-hero-art__chip sw-hero-art__chip--spark">
      <span className="material-symbols-outlined">auto_awesome</span>
    </span>
    <svg className="sw-hero-art__phone" viewBox="0 0 280 360" fill="none">
      <ellipse cx="140" cy="328" rx="78" ry="16" fill="#047857" opacity="0.12" />
      <path
        d="M86 86c0-22 18-40 40-40h28c22 0 40 18 40 40v188c0 22-18 40-40 40h-28c-22 0-40-18-40-40V86Z"
        fill="#fff"
        stroke="#D1FAE5"
        strokeWidth="3"
      />
      <rect x="104" y="58" width="72" height="10" rx="5" fill="#ECFDF5" />
      <circle cx="140" cy="278" r="14" fill="#047857" />
      <rect x="108" y="88" width="64" height="64" rx="18" fill="#D1FAE5" />
      <path d="M132 108v24l22-12-22-12Z" fill="#047857" />
      <circle cx="118" cy="176" r="10" fill="#A7F3D0" />
      <circle cx="140" cy="176" r="10" fill="#6EE7B7" />
      <circle cx="162" cy="176" r="10" fill="#047857" />
      <rect x="108" y="200" width="64" height="10" rx="5" fill="#ECFDF5" />
      <rect x="118" y="218" width="44" height="8" rx="4" fill="#D1FAE5" />
    </svg>
    <span className="sw-hero-art__ring" />
  </div>
);

export default SwarnaHeroArt;
