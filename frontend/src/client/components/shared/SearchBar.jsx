import React from 'react';

const SearchBar = ({ value, onChange, placeholder = 'Search...', style }) => {
  return (
    <div className="cl-search-container" style={style}>
      <span className="material-symbols-outlined cl-search-icon">search</span>
      <input
        type="text"
        className="cl-search-input"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
};

export default SearchBar;
