import React from 'react';
import ReactPlayer from 'react-player';

const VideoPlayer = ({ video, onRemove }) => {
  return (
    <div className="video-player-container">
      <div className="video-player-header">
        <h3>{video.title}</h3>
        <button onClick={() => onRemove(video.id)} className="remove-button">
          ×
        </button>
      </div>
      <div className="video-player-wrapper">
        <ReactPlayer
          url={video.video_url}
          controls
          width="100%"
          height="100%"
          playing={false}
        />
      </div>
      <div className="video-info">
        <p>{video.description}</p>
        <div className="video-tags">
          {video.tags.map((tag, index) => (
            <span key={index} className="tag">
              {tag}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};

export default VideoPlayer;