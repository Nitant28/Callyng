import './SearchBar.css';

const SearchBar = ({ value, onChange, placeholder = 'Search calls, leads, transcripts…' }) => (
  <div className="cl-search">
    <span className="material-symbols-outlined cl-search__icon">search</span>
    <input
      type="search"
      className="cl-search__input"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
    />
    <kbd className="cl-search__hint">/</kbd>
  </div>
);

export default SearchBar;
