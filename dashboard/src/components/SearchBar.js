import React, { useState } from 'react';

const SearchBar = ({ onSearch, isLoading }) => {
  const [query, setQuery] = useState('');
  const [searchMode, setSearchMode] = useState('clip');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (query.trim() && !isLoading) {
      onSearch(query.trim(), searchMode);
    }
  };

  const modeDescriptions = {
    clip: 'Fast semantic search using CLIP',
    yolo_hybrid: 'CLIP + YOLO for better object accuracy',
    advanced_clip: 'Larger CLIP model (slower, more accurate)'
  };

  return (
    <form onSubmit={handleSubmit} className="search-bar-container">
      <div className="search-mode-selector">
        <div className="search-mode-options">
          <label className={`search-mode-option ${searchMode === 'clip' ? 'active' : ''}`}>
            <input
              type="radio"
              value="clip"
              checked={searchMode === 'clip'}
              onChange={(e) => setSearchMode(e.target.value)}
            />
            <span className="mode-icon">⚡</span>
            <span className="mode-label">Standard CLIP</span>
          </label>
          <label className={`search-mode-option ${searchMode === 'yolo_hybrid' ? 'active' : ''}`}>
            <input
              type="radio"
              value="yolo_hybrid"
              checked={searchMode === 'yolo_hybrid'}
              onChange={(e) => setSearchMode(e.target.value)}
            />
            <span className="mode-icon">🎯</span>
            <span className="mode-label">YOLO + CLIP</span>
          </label>
          <label className={`search-mode-option ${searchMode === 'advanced_clip' ? 'active' : ''}`}>
            <input
              type="radio"
              value="advanced_clip"
              checked={searchMode === 'advanced_clip'}
              onChange={(e) => setSearchMode(e.target.value)}
            />
            <span className="mode-icon">🧠</span>
            <span className="mode-label">Advanced CLIP</span>
          </label>
        </div>
        <div className="search-mode-description">
          {modeDescriptions[searchMode]}
        </div>
      </div>
      <div className="search-bar">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search videos... (e.g., 'person wearing red jacket')"
          className="search-input"
          disabled={isLoading}
        />
        <button type="submit" className="search-button" disabled={isLoading || !query.trim()}>
          {isLoading ? '🔍 Searching...' : '🔍 Search'}
        </button>
      </div>
    </form>
  );
};

export default SearchBar;
