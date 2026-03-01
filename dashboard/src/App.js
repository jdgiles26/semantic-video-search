import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import VideoPlayer from './VideoPlayer';
import SearchBar from './components/SearchBar';
import VideoGrid from './VideoGrid';
import './App.css';

// API base URL - can be configured via environment variable
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
});

function App() {
  // Mode: 'search', 'live', or 'tasks'
  const [mode, setMode] = useState('search');
  
  // Search results
  const [searchResults, setSearchResults] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  
  // Live cameras
  const [cameras, setCameras] = useState([]);
  const [selectedCameras, setSelectedCameras] = useState([]);
  
  // Camera registration form
  const [newCameraId, setNewCameraId] = useState('');
  const [newCameraUrl, setNewCameraUrl] = useState('');
  
  // URL processing form
  const [videoUrl, setVideoUrl] = useState('');
  
  // Tasks
  const [tasks, setTasks] = useState([]);
  
  // Stats
  const [stats, setStats] = useState(null);
  
  // Selected search result for detail view
  const [selectedResult, setSelectedResult] = useState(null);
  
  // Loading states
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch stats
  const fetchStats = useCallback(async () => {
    try {
      const response = await api.get('/stats');
      setStats(response.data);
    } catch (err) {
      console.error('Error fetching stats:', err);
    }
  }, []);

  // Fetch cameras
  const fetchCameras = useCallback(async () => {
    try {
      const response = await api.get('/cameras');
      setCameras(response.data);
    } catch (err) {
      console.error('Error fetching cameras:', err);
    }
  }, []);

  // Fetch tasks
  const fetchTasks = useCallback(async () => {
    try {
      const response = await api.get('/tasks');
      setTasks(response.data);
    } catch (err) {
      console.error('Error fetching tasks:', err);
    }
  }, []);

  // Initial load and polling
  useEffect(() => {
    fetchStats();
    fetchCameras();
    fetchTasks();
    
    // Poll for updates every 5 seconds
    const interval = setInterval(() => {
      fetchStats();
      if (mode === 'live') {
        fetchCameras();
      }
      if (mode === 'tasks') {
        fetchTasks();
      }
    }, 5000);
    
    return () => clearInterval(interval);
  }, [fetchStats, fetchCameras, fetchTasks, mode]);

  // Handle search
  const handleSearch = async (query, searchMode = 'clip') => {
    if (!query.trim()) return;
    
    setSearchQuery(query);
    setIsSearching(true);
    setError(null);
    
    try {
      const response = await api.get('/query', {
        params: { query, top_k: 20, mode: searchMode }
      });
      
      // Transform results to match video format
      const videos = response.data.results.map(result => ({
        id: result.id,
        source_type: result.source_type,
        source_name: result.source_name,
        video_url: result.video_chunk_path,
        thumbnail_path: result.thumbnail_path,
        start_offset: result.start_offset,
        end_offset: result.end_offset,
        timestamp: result.timestamp,
        frame_count: result.frame_count,
        score: result.score,
        title: `${result.source_name} (${formatTime(result.start_offset)} - ${formatTime(result.end_offset)})`,
        description: `Match score: ${(result.score * 100).toFixed(1)}%`,
        tags: [result.source_type]
      }));
      
      setSearchResults(videos);
    } catch (err) {
      console.error('Search error:', err);
      setError('Search failed. Please try again.');
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  // Format time helper
  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Convert RTSP URL to HLS URL for browser playback
  const getHlsUrl = (rtspUrl) => {
    // Convert rtsp://rtsp-camera:8554/live to http://localhost:10588/live/index.m3u8
    if (rtspUrl && rtspUrl.startsWith('rtsp://')) {
      // Extract the path from the RTSP URL
      const match = rtspUrl.match(/rtsp:\/\/[^\/]+(\/.*)?/);
      if (match) {
        const path = match[1] || '/live';
        // Use localhost:10588 which maps to the container's HLS port (8888)
        return `http://localhost:10588${path}/index.m3u8`;
      }
    }
    return rtspUrl;
  };

  // Convert video chunk path to playable URL
  const getVideoUrl = (chunkPath) => {
    if (!chunkPath) return '';
    
    // Handle placeholder paths (RTSP streams that weren't saved)
    if (chunkPath.startsWith('placeholder://')) {
      // Extract source and time range from placeholder
      const match = chunkPath.match(/placeholder:\/\/(.+)#(\d+)-(\d+)/);
      if (match) {
        const source = match[1];
        // For RTSP placeholders, return HLS stream
        if (source.startsWith('rtsp://')) {
          return getHlsUrl(source);
        }
      }
      return '';
    }
    
    // Convert local path to API URL
    if (chunkPath.startsWith('/tmp/video_chunks/')) {
      const relPath = chunkPath.substring('/tmp/video_chunks/'.length);
      return `${API_BASE_URL}/video-chunks/${relPath}`;
    }
    
    return chunkPath;
  };

  // Handle video/camera selection
  const handleVideoSelect = (video) => {
    if (mode === 'search') {
      // In search mode, show detail view
      setSelectedResult(video);
    } else {
      // In live mode, toggle camera selection
      if (selectedCameras.some(c => c.id === video.id)) {
        setSelectedCameras(selectedCameras.filter(c => c.id !== video.id));
      } else {
        // Convert video URL for browser playback
        const videoWithPlayableUrl = {
          ...video,
          video_url: getVideoUrl(video.video_url),
          original_url: video.video_url // Keep original for reference
        };
        setSelectedCameras([...selectedCameras, videoWithPlayableUrl]);
      }
    }
  };

  // Close search result detail view
  const handleCloseDetail = () => {
    setSelectedResult(null);
  };

  // Play video from search result
  const handlePlayVideo = (video) => {
    const videoWithUrl = {
      ...video,
      video_url: getVideoUrl(video.video_url),
      original_url: video.video_url
    };
    setSelectedCameras([videoWithUrl]);
    setSelectedResult(null);
  };

  // Remove stream
  const handleRemoveStream = (id) => {
    setSelectedCameras(selectedCameras.filter(c => c.id !== id));
  };

  // Register new camera
  const handleRegisterCamera = async (e) => {
    e.preventDefault();
    if (!newCameraId.trim() || !newCameraUrl.trim()) return;
    
    setLoading(true);
    setError(null);
    
    try {
      await api.post('/cameras/register', {
        camera_id: newCameraId,
        rtsp_url: newCameraUrl
      });
      
      setNewCameraId('');
      setNewCameraUrl('');
      fetchCameras();
    } catch (err) {
      console.error('Error registering camera:', err);
      setError('Failed to register camera. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Stop camera
  const handleStopCamera = async (cameraId) => {
    try {
      await api.post(`/cameras/${cameraId}/stop`);
      fetchCameras();
    } catch (err) {
      console.error('Error stopping camera:', err);
    }
  };

  // Process video URL
  const handleProcessUrl = async (e) => {
    e.preventDefault();
    if (!videoUrl.trim()) return;
    
    setLoading(true);
    setError(null);
    
    try {
      await api.post('/videos/url', { url: videoUrl });
      setVideoUrl('');
      alert('Video URL queued for processing. Check the tasks section for status.');
    } catch (err) {
      console.error('Error processing URL:', err);
      setError('Failed to process URL. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Handle file upload
  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    setLoading(true);
    setError(null);
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      await api.post('/videos/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      alert('File uploaded and queued for processing. Check the tasks section for status.');
    } catch (err) {
      console.error('Error uploading file:', err);
      setError('Failed to upload file. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Get status badge class
  const getStatusClass = (status) => {
    switch (status) {
      case 'active': return 'active';
      case 'starting': return 'pending';
      case 'pending': return 'pending';
      case 'processing': return 'pending';
      case 'completed': return 'active';
      case 'error': return 'inactive';
      default: return 'inactive';
    }
  };

  // Check if camera view button should be enabled
  const isCameraViewable = (status) => {
    // Allow viewing if status is active or starting (stream is being established)
    return status === 'active' || status === 'starting';
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>🔍 Video Search System</h1>
        
        <div className="mode-toggle">
          <button 
            className={mode === 'search' ? 'active' : ''}
            onClick={() => setMode('search')}
          >
            🔍 Search
          </button>
          <button 
            className={mode === 'live' ? 'active' : ''}
            onClick={() => setMode('live')}
          >
            📹 Live
          </button>
          <button 
            className={mode === 'tasks' ? 'active' : ''}
            onClick={() => setMode('tasks')}
          >
            📋 Tasks
          </button>
        </div>
        
        {mode === 'search' && (
          <SearchBar onSearch={handleSearch} isLoading={isSearching} />
        )}
      </header>

      <div className="dashboard-content">
        {error && (
          <div className="error-message">{error}</div>
        )}

        {/* Stats Overview */}
        {stats && (
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-value">{stats.total_clips.toLocaleString()}</div>
              <div className="stat-label">Total Clips</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{stats.active_cameras}</div>
              <div className="stat-label">Active Cameras</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{stats.pending_tasks}</div>
              <div className="stat-label">Pending Tasks</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{stats.embedding_dim}D</div>
              <div className="stat-label">Embeddings</div>
            </div>
          </div>
        )}

        {mode === 'search' ? (
          <>
            {/* URL Processing Section */}
            <div className="url-input-section">
              <div className="section-header">
                <h2>🌐 Process Video URL</h2>
              </div>
              <form onSubmit={handleProcessUrl} className="url-input-form">
                <input
                  type="url"
                  value={videoUrl}
                  onChange={(e) => setVideoUrl(e.target.value)}
                  placeholder="Enter video URL (YouTube, Vimeo, etc.)"
                  className="url-input"
                />
                <button type="submit" className="search-button" disabled={loading}>
                  Process
                </button>
              </form>
            </div>

            {/* File Upload Section */}
            <div className="upload-section">
              <div className="section-header">
                <h2>📁 Upload Video</h2>
              </div>
              <div className="upload-area">
                <div className="upload-icon">📤</div>
                <div className="upload-text">Drag & drop a video file here</div>
                <div className="upload-hint">or click to browse (MP4, AVI, MOV, MKV)</div>
                <input
                  type="file"
                  accept=".mp4,.avi,.mov,.mkv,.webm"
                  onChange={handleFileUpload}
                  className="file-input"
                  id="file-upload"
                />
                <label htmlFor="file-upload" style={{ cursor: 'pointer' }}>
                  <button 
                    className="search-button" 
                    style={{ marginTop: '16px' }}
                    onClick={() => document.getElementById('file-upload').click()}
                    disabled={loading}
                  >
                    Select File
                  </button>
                </label>
              </div>
            </div>

            {/* Search Results */}
            <div className="video-grid-container">
              <div className="section-header">
                <h2>
                  {searchQuery 
                    ? `🔍 Search Results for "${searchQuery}"` 
                    : '📹 Available Videos'}
                </h2>
                {searchResults.length > 0 && (
                  <span>{searchResults.length} results found</span>
                )}
              </div>
              
              {isSearching ? (
                <div className="loading-spinner">Searching...</div>
              ) : searchResults.length > 0 ? (
                <VideoGrid
                  videos={searchResults}
                  onSelect={handleVideoSelect}
                  selectedVideos={selectedCameras}
                />
              ) : searchQuery ? (
                <div className="empty-state">
                  <div className="empty-state-icon">🔍</div>
                  <div className="empty-state-text">No results found. Try a different query.</div>
                </div>
              ) : (
                <div className="empty-state">
                  <div className="empty-state-icon">💡</div>
                  <div className="empty-state-text">
                    Enter a search query like "person wearing red jacket" or "white truck"
                  </div>
                </div>
              )}
            </div>

            {/* Search Result Detail Modal */}
            {selectedResult && (
              <div className="modal-overlay" onClick={handleCloseDetail}>
                <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                  <div className="modal-header">
                    <h2>🔍 Search Result Details</h2>
                    <button className="close-button" onClick={handleCloseDetail}>×</button>
                  </div>
                  <div className="modal-body">
                    <div className="detail-section">
                      <h3>📝 Your Search Query</h3>
                      <div className="query-box">"{searchQuery}"</div>
                      <p className="detail-text">
                        This query was converted into a semantic embedding using OpenCLIP (ViT-B-32 model). 
                        The model understands the meaning of your text and finds visually similar content.
                      </p>
                    </div>

                    <div className="detail-section">
                      <h3>🎯 Match Score: {(selectedResult.score * 100).toFixed(1)}%</h3>
                      <div className="score-bar">
                        <div 
                          className="score-fill" 
                          style={{ width: `${selectedResult.score * 100}%` }}
                        />
                      </div>
                      <p className="detail-text">
                        <strong>How this is calculated:</strong> The match percentage represents the 
                        <strong> cosine similarity</strong> between your search query's embedding and the video clip's 
                        embedding. Higher values (closer to 100%) mean stronger visual similarity.
                      </p>
                      <ul className="detail-list">
                        <li><strong>90-100%:</strong> Very strong match - highly relevant</li>
                        <li><strong>70-89%:</strong> Good match - likely relevant</li>
                        <li><strong>50-69%:</strong> Moderate match - somewhat related</li>
                        <li><strong>Below 50%:</strong> Weak match - may not be relevant</li>
                      </ul>
                    </div>

                    {selectedResult.thumbnail_path && (
                      <div className="detail-section">
                        <h3>🖼️ Preview</h3>
                        <div className="detail-thumbnail">
                          <img 
                            src={`${API_BASE_URL}/thumbnails/${selectedResult.thumbnail_path.replace('/tmp/video_thumbnails/', '')}`}
                            alt="Video preview"
                            onError={(e) => e.target.style.display = 'none'}
                          />
                        </div>
                      </div>
                    )}

                    <div className="detail-section">
                      <h3>📹 Video Clip Information</h3>
                      <table className="detail-table">
                        <tbody>
                          <tr>
                            <td>Source Type</td>
                            <td>{selectedResult.source_type === 'live' ? '📹 Live Stream' : selectedResult.source_type === 'url' ? '🔗 URL Video' : '📁 Uploaded Video'}</td>
                          </tr>
                          <tr>
                            <td>Source Name</td>
                            <td>{selectedResult.source_name}</td>
                          </tr>
                          <tr>
                            <td>Time Range</td>
                            <td>{Math.floor(selectedResult.start_offset / 60)}:{(selectedResult.start_offset % 60).toString().padStart(2, '0')} - {Math.floor(selectedResult.end_offset / 60)}:{(selectedResult.end_offset % 60).toString().padStart(2, '0')}</td>
                          </tr>
                          <tr>
                            <td>Duration</td>
                            <td>{selectedResult.end_offset - selectedResult.start_offset} seconds</td>
                          </tr>
                          <tr>
                            <td>Frames Analyzed</td>
                            <td>{selectedResult.frame_count} frames</td>
                          </tr>
                          <tr>
                            <td>Clip ID</td>
                            <td>{selectedResult.id}</td>
                          </tr>
                          <tr>
                            <td>Timestamp</td>
                            <td>{new Date(selectedResult.timestamp * 1000).toLocaleString()}</td>
                          </tr>
                          <tr>
                            <td>File Path</td>
                            <td className="file-path">{selectedResult.video_chunk_path}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>

                    <div className="detail-section">
                      <h3>🧠 How the AI Understands This Match</h3>
                      <p className="detail-text">
                        The OpenCLIP model (ViT-B-32) generates a <strong>512-dimensional embedding vector</strong> for both 
                        your text query and each video clip. The match score is computed using 
                        <strong> cosine similarity</strong> between these vectors:
                      </p>
                      <div className="formula-box">
                        similarity = (A · B) / (||A|| × ||B||)
                      </div>
                      <p className="detail-text">
                        Where A is your query embedding and B is the video clip embedding. The result ranges 
                        from -1 (opposite) to 1 (identical), which we convert to a percentage (0-100%).
                      </p>
                    </div>

                    <div className="modal-actions">
                      <button 
                        className="search-button"
                        onClick={() => handlePlayVideo(selectedResult)}
                      >
                        ▶️ Play Video
                      </button>
                      <button 
                        className="secondary-button"
                        onClick={handleCloseDetail}
                      >
                        Close
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </>
        ) : mode === 'live' ? (
          <>
            {/* Camera Registration */}
            <div className="camera-section">
              <div className="section-header">
                <h2>📹 Register RTSP Camera</h2>
              </div>
              <form onSubmit={handleRegisterCamera} className="camera-form">
                <input
                  type="text"
                  value={newCameraId}
                  onChange={(e) => setNewCameraId(e.target.value)}
                  placeholder="Camera ID (e.g., cam-001)"
                  className="camera-input"
                />
                <input
                  type="url"
                  value={newCameraUrl}
                  onChange={(e) => setNewCameraUrl(e.target.value)}
                  placeholder="RTSP URL (e.g., rtsp://camera-ip/stream)"
                  className="camera-input"
                />
                <button type="submit" className="search-button" disabled={loading}>
                  Register
                </button>
              </form>

              {/* Camera List */}
              <div className="camera-list">
                {cameras.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-state-text">No cameras registered yet.</div>
                  </div>
                ) : (
                  cameras.map(camera => (
                    <div key={camera.camera_id} className="camera-item">
                      <div className="camera-info">
                        <div className="camera-id">{camera.camera_id}</div>
                        <div className="camera-url">{camera.rtsp_url}</div>
                        {camera.error && (
                          <div className="camera-error" title={camera.error}>
                            ⚠️ {camera.error}
                          </div>
                        )}
                      </div>
                      <div className="camera-status">
                        <span className={`status-badge ${getStatusClass(camera.status)}`}>
                          {camera.status}
                        </span>
                        <button 
                          className="remove-button"
                          onClick={() => handleStopCamera(camera.camera_id)}
                          title="Stop camera"
                        >
                          ⏹
                        </button>
                        <button 
                          className="search-button"
                          onClick={() => handleVideoSelect({
                            id: camera.camera_id,
                            source_type: 'live',
                            source_name: camera.camera_id,
                            video_url: camera.rtsp_url,
                            title: camera.camera_id,
                            description: 'Live RTSP Stream',
                            tags: ['live']
                          })}
                          disabled={!isCameraViewable(camera.status)}
                          title={!isCameraViewable(camera.status) ? 'Camera is not ready yet' : 'Click to view live stream'}
                        >
                          {camera.status === 'starting' ? 'Starting...' : 'View'}
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </>
        ) : mode === 'tasks' ? (
          <>
            {/* Tasks Section */}
            <div className="tasks-section">
              <div className="section-header">
                <h2>📋 Processing Tasks</h2>
                <button 
                  className="search-button" 
                  onClick={fetchTasks}
                  style={{ padding: '8px 16px', fontSize: '14px' }}
                >
                  🔄 Refresh
                </button>
              </div>
              
              {tasks.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-state-icon">📋</div>
                  <div className="empty-state-text">No tasks found.</div>
                  <div className="upload-hint">Upload a video or process a URL to create a task.</div>
                </div>
              ) : (
                <div className="task-list">
                  {tasks.map(task => (
                    <div key={task.task_id} className="task-item">
                      <div className="task-info">
                        <div className="task-id" title={task.task_id}>
                          {task.task_id.substring(0, 8)}...
                        </div>
                        <div className="task-type">
                          {task.type === 'url' ? '🌐 URL' : task.type === 'upload' ? '📁 Upload' : task.type}
                        </div>
                        {task.url && (
                          <div className="task-url" title={task.url}>
                            {task.url.length > 50 ? task.url.substring(0, 50) + '...' : task.url}
                          </div>
                        )}
                        {task.filename && (
                          <div className="task-filename">📄 {task.filename}</div>
                        )}
                        {task.error && (
                          <div className="task-error">❌ Error: {task.error}</div>
                        )}
                      </div>
                      <div className="task-status">
                        <span className={`status-badge ${getStatusClass(task.status)}`}>
                          {task.status}
                        </span>
                        {(task.clips_processed > 0 || task.frames_processed > 0) && (
                          <div className="task-progress">
                            {task.clips_processed > 0 && <span>{task.clips_processed} clips</span>}
                            {task.frames_processed > 0 && <span>{task.frames_processed} frames</span>}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : null}

        {/* Active Streams / Selected Video */}
        {selectedCameras.length > 0 && (
          <div className="video-streams-container">
            <div className="section-header">
              <h2>
                {mode === 'search' ? '🎬 Selected Clip' : `📺 Active Streams (${selectedCameras.length})`}
              </h2>
            </div>
            <div className="video-streams">
              {selectedCameras.map((video) => (
                <VideoPlayer
                  key={video.id}
                  video={video}
                  onRemove={handleRemoveStream}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
