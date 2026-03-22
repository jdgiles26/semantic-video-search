import React, { useEffect, useState } from 'react';
import ReactPlayer from 'react-player';
import { LiveStreamWithAI } from './components/LiveStreamAnalyzer';

const renderDocumentMessage = (mimeType) => {
  if ((mimeType || '').includes('pdf')) {
    return 'PDF preview is shown inline when supported by the browser.';
  }
  return 'This document format may open best in a separate tab or its native desktop application.';
};

const supportsNativeLiveAnalysis = (url, isLive) => {
  if (!isLive || !url) return false;
  const normalized = url.toLowerCase();
  return (
    normalized.includes('/video-chunks/') ||
    normalized.endsWith('.mp4') ||
    normalized.endsWith('.webm')
  );
};

const VideoPlayer = ({ video, onRemove }) => {
  const [isReady, setIsReady] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [liveAIEnabled, setLiveAIEnabled] = useState(Boolean(video.isRegisteredStream));
  const mediaKind = video.media_kind || (video.source_type === 'live' ? 'video' : 'video');
  const isLive = video.source_type === 'live' || video.tags?.includes('live');
  const isVideo = mediaKind === 'video';
  const isImage = mediaKind === 'image';
  const isDocument = mediaKind === 'document';
  const playbackUrl = video.video_url || video.playback_url || '';
  const supportsLiveAI = supportsNativeLiveAnalysis(playbackUrl, isLive);
  const waitingForSegment = isLive && video.stream_type === 'rtsp' && !playbackUrl && !hasError;

  useEffect(() => {
    setIsReady(false);
    setHasError(false);
  }, [playbackUrl]);

  useEffect(() => {
    if (!supportsLiveAI) {
      setLiveAIEnabled(false);
    }
  }, [supportsLiveAI]);

  const liveStatusLabel = hasError
    ? 'Error'
    : waitingForSegment
      ? 'Waiting'
      : isReady
        ? liveAIEnabled && supportsLiveAI ? 'LIVE + AI' : 'LIVE'
        : 'Connecting...';

  return (
    <div className="video-player-container">
      <div className="video-player-header">
        <h3>{video.title}</h3>
        <div className="player-header-controls">
          {isLive && (
            <span className={`player-status ${isReady ? 'connected' : 'connecting'}`}>
              {liveStatusLabel}
            </span>
          )}
          {isLive && isVideo && (
            <button
              type="button"
              className={`ai-toggle-button ${liveAIEnabled ? 'active' : ''}`}
              onClick={() => setLiveAIEnabled(enabled => !enabled)}
              disabled={!supportsLiveAI}
              title={supportsLiveAI ? 'Toggle live AI analysis' : 'Live AI analysis needs a browser-playable MP4 segment'}
            >
              {supportsLiveAI ? (liveAIEnabled ? 'AI On' : 'AI Off') : 'AI Unavailable'}
            </button>
          )}
          <button type="button" onClick={() => onRemove(video.id)} className="remove-button">
            ×
          </button>
        </div>
      </div>
      <div className={`video-player-wrapper ${isImage ? 'image-viewer' : isDocument ? 'document-viewer' : ''}`}>
        {isVideo && waitingForSegment && (
          <div className="player-loading">
            <div className="player-loading-spinner"></div>
            <span>Waiting for the first processed live segment...</span>
          </div>
        )}
        {isVideo && !playbackUrl && !waitingForSegment && !hasError && (
          <div className="player-loading">
            <div className="player-loading-spinner"></div>
            <span>{isLive ? 'Preparing live playback...' : 'Preparing media...'}</span>
          </div>
        )}
        {isVideo && !waitingForSegment && !playbackUrl && hasError && (
          <div className="player-error">
            <span>Playable media URL unavailable</span>
          </div>
        )}
        {isVideo && playbackUrl && !waitingForSegment && hasError && (
          <div className="player-error">
            <span>Unable to connect to stream</span>
          </div>
        )}
        {isVideo && playbackUrl && (
          liveAIEnabled && supportsLiveAI ? (
            <LiveStreamWithAI
              videoUrl={playbackUrl}
              cameraId={video.source_name || video.id}
              enabled
              showControls
              onReady={() => setIsReady(true)}
              onError={() => setHasError(true)}
            />
          ) : (
            <ReactPlayer
              url={playbackUrl}
              controls
              width="100%"
              height="100%"
              playing={isLive && isReady}
              muted={isLive}
              onReady={() => setIsReady(true)}
              onError={() => setHasError(true)}
              config={{
                file: {
                  forceHLS: playbackUrl.includes('.m3u8') || video.stream_type === 'hls',
                  attributes: { crossOrigin: 'anonymous' }
                }
              }}
            />
          )
        )}
        {isImage && (
          <img
            src={playbackUrl}
            alt={video.title}
            className="media-image-preview"
            onLoad={() => setIsReady(true)}
            onError={() => setHasError(true)}
          />
        )}
        {isDocument && (
          <iframe
            title={video.title}
            src={playbackUrl}
            className="document-frame"
            onLoad={() => setIsReady(true)}
            onError={() => setHasError(true)}
          />
        )}
      </div>
      <div className="video-info">
        <p>{video.description}</p>
        {isLive && video.stream_source_url && <p className="media-source-url">{video.stream_source_url}</p>}
        {isDocument && <p>{renderDocumentMessage(video.mime_type)}</p>}
        {video.excerpt && <p>{video.excerpt}</p>}
        <div className="video-tags">
          {Array.isArray(video.tags) && video.tags.map((tag, index) => (
            <span key={index} className="tag">
              {tag}
            </span>
          ))}
        </div>
        {(isImage || isDocument) && (
          <a className="media-open-link" href={playbackUrl} target="_blank" rel="noreferrer">
            Open original file
          </a>
        )}
      </div>
    </div>
  );
};

export default VideoPlayer;
