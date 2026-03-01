import React from 'react';
import VideoThumbnail from './VideoThumbnail';

const VideoGrid = ({ videos, onSelect, selectedVideos }) => {
  return (
    <div className="video-grid">
      {videos.map((video) => (
        <VideoThumbnail
          key={video.id}
          video={video}
          onSelect={onSelect}
          isSelected={selectedVideos.some(v => v.id === video.id)}
        />
      ))}
    </div>
  );
};

export default VideoGrid;