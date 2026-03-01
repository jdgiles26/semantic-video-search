import React from 'react';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const VideoThumbnail = ({ video, onSelect, isSelected }) => {
  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'Unknown';
    const date = new Date(timestamp * 1000);
    return date.toLocaleString();
  };

  const getSourceTypeIcon = (sourceType) => {
    switch (sourceType) {
      case 'live':
        return '📹';
      case 'url':
        return '🔗';
      case 'upload':
        return '📁';
      default:
        return '🎬';
    }
  };

  const getSourceTypeLabel = (sourceType) => {
    switch (sourceType) {
      case 'live':
        return 'Live';
      case 'url':
        return 'URL';
      case 'upload':
        return 'Upload';
      default:
        return 'Video';
    }
  };

  // Get thumbnail URL
  const getThumbnailUrl = (path) => {
    if (!path) return null;
    // Convert local path to API URL
    if (path.startsWith('/tmp/video_thumbnails/')) {
      const relPath = path.substring('/tmp/video_thumbnails/'.length);
      return `${API_BASE_URL}/thumbnails/${relPath}`;
    }
    return path;
  };

  const thumbnailUrl = getThumbnailUrl(video.thumbnail_path);

  return (
    <div 
      className={`video-thumbnail ${isSelected ? 'selected' : ''}`}
      onClick={() => onSelect(video)}
    >
      <div className="thumbnail-image">
        {thumbnailUrl ? (
          <img 
            src={thumbnailUrl} 
            alt={video.source_name}
            className="thumbnail-img"
            onError={(e) => {
              e.target.style.display = 'none';
              e.target.nextSibling.style.display = 'flex';
            }}
          />
        ) : null}
        <div className="thumbnail-placeholder" style={{ display: thumbnailUrl ? 'none' : 'flex' }}>
          {getSourceTypeIcon(video.source_type)}
        </div>
        {video.source_type === 'live' && (
          <div className="live-indicator">LIVE</div>
        )}
        <div className="source-type-badge">
          {getSourceTypeLabel(video.source_type)}
        </div>
      </div>
      
      <div className="thumbnail-info">
        <h4 className="thumbnail-title" title={video.source_name}>
          {video.source_name}
        </h4>
        
        <div className="thumbnail-meta">
          <span className="thumbnail-time">
            {formatDuration(video.start_offset || 0)} - {formatDuration(video.end_offset || 10)}
          </span>
          {video.score && (
            <span className="thumbnail-score" title="Cosine similarity score - higher is better match">
              {(video.score * 100).toFixed(1)}% match
            </span>
          )}
        </div>
        
        {video.timestamp && (
          <div className="thumbnail-timestamp">
            📅 {formatTimestamp(video.timestamp)}
          </div>
        )}
        
        {video.frame_count && (
          <div className="thumbnail-frames">
            🎬 {video.frame_count} frames analyzed
          </div>
        )}
        
        <div className="thumbnail-click-hint">
          👆 Click for details & playback
        </div>
      </div>
    </div>
  );
};

export default VideoThumbnail;
