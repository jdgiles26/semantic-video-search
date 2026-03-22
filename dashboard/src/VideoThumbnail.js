import React from 'react';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const mediaIcons = {
  image: '🖼️',
  document: '📄',
  video: '🎬',
  live: '📹',
};

const sourceLabels = {
  live: 'Live',
  url: 'URL',
  upload: 'Upload',
};

const formatDuration = (seconds) => {
  const mins = Math.floor(Number(seconds || 0) / 60);
  const secs = Math.floor(Number(seconds || 0) % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

const formatTimestamp = (timestamp) => {
  if (!timestamp) return 'Unknown';
  return new Date(timestamp * 1000).toLocaleString();
};

const formatBytes = (bytes) => {
  const size = Number(bytes || 0);
  if (!size) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const exp = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
  const value = size / (1024 ** exp);
  return `${value.toFixed(exp === 0 ? 0 : 1)} ${units[exp]}`;
};

const getThumbnailUrl = (path) => {
  if (!path) return null;
  if (path.startsWith('/tmp/video_thumbnails/')) {
    const relPath = path.substring('/tmp/video_thumbnails/'.length);
    return `${API_BASE_URL}/thumbnails/${relPath}`;
  }
  return path;
};

const VideoThumbnail = ({ video, onSelect, isSelected }) => {
  const mediaKind = video.media_kind || (video.source_type === 'live' ? 'live' : 'video');
  const thumbnailUrl = getThumbnailUrl(video.thumbnail_path);
  const sourceTypeLabel = sourceLabels[video.source_type] || sourceLabels.upload || 'Media';
  const placeholderIcon = mediaIcons[mediaKind] || mediaIcons.video;
  const isLive = video.source_type === 'live';
  const isAsset = Boolean(video.asset_id);

  return (
    <div
      className={`video-thumbnail ${isSelected ? 'selected' : ''}`}
      onClick={() => onSelect(video)}
    >
      <div className={`thumbnail-image ${mediaKind === 'document' ? 'document' : ''}`}>
        {thumbnailUrl ? (
          <img
            src={thumbnailUrl}
            alt={video.source_name || video.title}
            className="thumbnail-img"
            onError={(e) => {
              e.target.style.display = 'none';
              if (e.target.nextSibling) {
                e.target.nextSibling.style.display = 'flex';
              }
            }}
          />
        ) : null}
        <div className="thumbnail-placeholder" style={{ display: thumbnailUrl ? 'none' : 'flex' }}>
          {placeholderIcon}
        </div>
        {isLive && <div className="live-indicator">LIVE</div>}
        <div className="source-type-badge">
          {isAsset ? `${sourceTypeLabel} ${mediaKind}` : sourceTypeLabel}
        </div>
        {video.urgency_level && video.urgency_level !== 'low' && (
          <div className={`source-type-badge urgency-badge urgency-${video.urgency_level}`}>
            {String(video.urgency_level).toUpperCase()}
          </div>
        )}
      </div>

      <div className="thumbnail-info">
        <h4 className="thumbnail-title" title={video.source_name || video.title}>
          {video.source_name || video.title}
        </h4>

        {mediaKind === 'video' && !isAsset ? (
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
        ) : (
          <div className="thumbnail-meta">
            <span className="thumbnail-time">{video.status || mediaKind}</span>
            {video.file_size ? (
              <span className="thumbnail-score">{formatBytes(video.file_size)}</span>
            ) : null}
          </div>
        )}

        {video.description && <div className="thumbnail-summary">{video.description}</div>}

        {video.mission_score && (
          <div className="thumbnail-frames">
            🚨 Mission confidence {(video.mission_score * 100).toFixed(1)}%
          </div>
        )}

        {video.timestamp && (
          <div className="thumbnail-timestamp">
            📅 {formatTimestamp(video.timestamp)}
          </div>
        )}

        {video.frame_count ? (
          <div className="thumbnail-frames">
            🎬 {video.frame_count} frames analyzed
          </div>
        ) : null}

        {video.excerpt && (
          <div className="thumbnail-summary">
            {video.excerpt.length > 120 ? `${video.excerpt.slice(0, 120)}...` : video.excerpt}
          </div>
        )}

        <div className="thumbnail-click-hint">
          {mediaKind === 'video' ? '👆 View details & playback' : mediaKind === 'image' ? '👆 View details & image' : '👆 View details & open file'}
        </div>
      </div>
    </div>
  );
};

export default VideoThumbnail;
