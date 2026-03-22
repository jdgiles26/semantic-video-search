import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import VideoPlayer from './VideoPlayer';
import SearchBar from './components/SearchBar';
import VideoGrid from './VideoGrid';
import { useLocalStorage, useAnalysis, useWebGPU } from './hooks';
import './App.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({ baseURL: API_BASE_URL, timeout: 30000 });

// Default configurations
const DEFAULT_AI_CONFIG = {
  provider: 'ollama',
  ollama_base_url: 'http://localhost:11434',
  ollama_model: 'llava:7b',
  openai_api_key: '',
  openai_base_url: 'https://api.openai.com/v1',
  openai_model: 'gpt-4o-mini',
  webgpu_enabled: false
};

const DEFAULT_EMAIL_CONFIG = {
  enabled: false,
  smtp_host: '',
  smtp_port: 587,
  smtp_user: '',
  smtp_password: '',
  from_email: '',
  to_emails: [],
  alert_on_critical: true,
  alert_on_watch_match: true
};

const DEFAULT_WEBHOOK_CONFIG = {
  enabled: false,
  webhook_url: '',
  unique_email: '',
  dns_name: '',
  use_webhook_site_cli: false,
  webhook_site_uuid: '',
  bidirectional_proxy: false,
  proxy_url: '',
  headers: {},
  retry_attempts: 3,
  timeout_seconds: 30,
  alert_on_critical: true,
  alert_on_watch_match: true,
  alert_on_analysis: false
};

// Utility functions
const formatTime = (seconds) => {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

const formatTimestamp = (timestamp) => {
  if (!timestamp) return 'Unknown';
  const diff = Date.now() - timestamp;
  if (diff < 60000) return 'Just now';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return new Date(timestamp).toLocaleDateString();
};

const toApiMediaUrl = (value) => {
  if (!value) return '';
  if (value.startsWith('placeholder://')) {
    return '';
  }
  if (value.startsWith('/')) {
    return `${API_BASE_URL}${value}`;
  }
  return value;
};

const resolveCameraPlaybackUrl = (camera) => {
  if (camera?.playback_url) {
    return toApiMediaUrl(camera.playback_url);
  }
  if (camera?.stream_type === 'rtsp') {
    return '';
  }
  return toApiMediaUrl(camera?.rtsp_url);
};

const normalizeCamera = (camera) => ({
  ...camera,
  playback_url: resolveCameraPlaybackUrl(camera),
  stream_source_url: camera?.rtsp_url || '',
});

function App() {
  // ==================== UI STATE ====================
  const [mode, setMode] = useLocalStorage('vss_mode', 'search');
  const [showAISettings, setShowAISettings] = useLocalStorage('vss_panel_ai', false);
  const [showEmailSettings, setShowEmailSettings] = useLocalStorage('vss_panel_email', false);
  const [showWebhookSettings, setShowWebhookSettings] = useLocalStorage('vss_panel_webhook', false);
  const [showLogicPanel, setShowLogicPanel] = useLocalStorage('vss_panel_logic', false);
  const [showAnalysisLog, setShowAnalysisLog] = useLocalStorage('vss_panel_log', false);

  // ==================== DATA STATE ====================
  const [searchResults, setSearchResults] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [cameras, setCameras] = useState([]);
  const [selectedCameras, setSelectedCameras] = useState([]);
  const [newCameraId, setNewCameraId] = useState('');
  const [newCameraUrl, setNewCameraUrl] = useState('');
  const [streamType, setStreamType] = useState('auto');
  
  // URL Upload state
  const [videoUrl, setVideoUrl] = useState('');
  const [urlUploadLoading, setUrlUploadLoading] = useState(false);
  
  // OPORD Upload state
  const [opordFile, setOpordFile] = useState(null);
  const [opordUploading, setOpordUploading] = useState(false);
  const [opordPreview, setOpordPreview] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [uploadedAssets, setUploadedAssets] = useState([]);
  const [stats, setStats] = useState(null);
  const [predictions, setPredictions] = useState([]);
  const [missionAlerts, setMissionAlerts] = useState([]);
  const [activeWatchAlert, setActiveWatchAlert] = useState(null);
  const [lastWatchFindingCount, setLastWatchFindingCount] = useState(0);
  const [error, setError] = useState(null);
  const [dispatchStatus, setDispatchStatus] = useState(null);

  // ==================== CONFIG STATE ====================
  const [aiConfig, setAiConfig] = useLocalStorage('vss_ai_config', DEFAULT_AI_CONFIG);
  const [emailConfig, setEmailConfig] = useLocalStorage('vss_email_config', DEFAULT_EMAIL_CONFIG);
  const [webhookConfig, setWebhookConfig] = useLocalStorage('vss_webhook_config', DEFAULT_WEBHOOK_CONFIG);
  const [aiConfigMessage, setAiConfigMessage] = useState(null);
  const [emailTestStatus, setEmailTestStatus] = useState(null);
  const [webhookTestStatus, setWebhookTestStatus] = useState(null);
  const [webhookHistory, setWebhookHistory] = useState([]);
  const [logicExplanations, setLogicExplanations] = useState([]);
  const [ollamaStatus, setOllamaStatus] = useState(null);
  const [ollamaModels, setOllamaModels] = useState([]);

  // ==================== HOOKS ====================
  const webgpu = useWebGPU(aiConfig);
  const analysis = useAnalysis(api, aiConfig, webgpu.service, {
    predictions: predictions.slice(0, 5),
    alerts: missionAlerts.slice(0, 5),
    cameras: cameras.slice(0, 5),
    assets: uploadedAssets.slice(0, 8),
    results: searchResults.slice(0, 8),
    stats: stats || {}
  });

  // ==================== DATA FETCHING ====================
  const fetchStats = useCallback(async () => {
    try {
      const { data } = await api.get('/stats');
      setStats(data);
    } catch (err) {
      console.error('Failed to fetch stats:', err);
    }
  }, []);

  const fetchCameras = useCallback(async () => {
    try {
      const { data } = await api.get('/cameras');
      setCameras((data || []).map(normalizeCamera));
    } catch (err) {
      console.error('Failed to fetch cameras:', err);
    }
  }, []);

  const fetchTasks = useCallback(async () => {
    try {
      const { data } = await api.get('/tasks');
      setTasks(data);
    } catch (err) {
      console.error('Failed to fetch tasks:', err);
    }
  }, []);

  const fetchAssets = useCallback(async () => {
    try {
      const { data } = await api.get('/uploads/assets');
      setUploadedAssets(data || []);
    } catch (err) {
      console.error('Failed to fetch assets:', err);
    }
  }, []);

  const fetchPredictions = useCallback(async () => {
    try {
      const { data } = await api.get('/predictions');
      setPredictions(data.items || []);
    } catch (err) {
      console.error('Failed to fetch predictions:', err);
    }
  }, []);

  const fetchWatchAlert = useCallback(async () => {
    try {
      const { data } = await api.get('/watch-alerts/active');
      setActiveWatchAlert(data);
      
      const count = Number(data?.findings_count || 0);
      setLastWatchFindingCount(prev => {
        if (data && count > 0 && count > prev) {
          // Trigger alerts
          if (emailConfig.enabled && emailConfig.alert_on_watch_match) {
            sendEmailAlert('watch_match', data);
          }
          if (webhookConfig.enabled && webhookConfig.alert_on_watch_match) {
            sendWebhookAlert('watch_match', data);
          }
        }
        return count;
      });
    } catch (err) {
      console.error('Failed to fetch watch alert:', err);
    }
  }, [emailConfig, webhookConfig]);

  const fetchLogicExplanations = useCallback(async () => {
    try {
      const { data } = await api.get('/logic/explanations');
      setLogicExplanations(data || []);
    } catch (err) {
      console.error('Failed to fetch logic explanations:', err);
    }
  }, []);

  const fetchOllamaModels = useCallback(async () => {
    try {
      const { data } = await api.get('/ai/ollama/models');
      setOllamaModels(data.models || []);
      if (data.status) setOllamaStatus(data.status);
    } catch (err) {
      console.error('Failed to fetch Ollama models:', err);
      setOllamaModels([]);
      setOllamaStatus({
        available: false,
        detail: err?.response?.data?.detail || 'Unable to query Ollama status',
        actions: ['Verify the API is running and Ollama is reachable from the backend'],
      });
    }
  }, []);

  const fetchAIConfig = useCallback(async () => {
    try {
      const { data } = await api.get('/ai/config');
      setAiConfig(prev => ({
        ...prev,
        ...data,
        openai_api_key: prev.openai_api_key || ''
      }));
    } catch (err) {
      console.error('Failed to fetch AI config:', err);
    }
  }, [setAiConfig]);

  // ==================== INITIAL LOAD & POLLING ====================
  useEffect(() => {
    const loadInitialData = async () => {
      await Promise.all([
        fetchStats(),
        fetchCameras(),
        fetchTasks(),
        fetchAssets(),
        fetchPredictions(),
        fetchWatchAlert(),
        fetchLogicExplanations(),
      ]);
    };
    loadInitialData();

    const interval = setInterval(() => {
      fetchStats();
      fetchWatchAlert();
      if (mode === 'live') fetchCameras();
      if (mode === 'tasks') { fetchTasks(); fetchAssets(); }
      if (mode === 'search') fetchPredictions();
    }, 5000);

    return () => clearInterval(interval);
  }, [
    mode,
    fetchAssets,
    fetchCameras,
    fetchLogicExplanations,
    fetchPredictions,
    fetchStats,
    fetchTasks,
    fetchWatchAlert
  ]);

  useEffect(() => {
    fetchAIConfig();
    fetchOllamaModels();
  }, [fetchAIConfig, fetchOllamaModels]);

  useEffect(() => {
    setSelectedCameras(prev => {
      const cameraMap = new Map(cameras.map(camera => [camera.camera_id, camera]));

      return prev
        .filter(video => {
          if (!video.isRegisteredStream) return true;
          return cameraMap.has(video.id);
        })
        .map(video => {
          if (!video.isRegisteredStream) return video;
          const camera = cameraMap.get(video.id);
          if (!camera) return video;

          const nextVideoUrl = camera.playback_url || video.video_url || '';
          return {
            ...video,
            title: camera.camera_id,
            description: camera.stream_source_url || camera.rtsp_url || '',
            video_url: nextVideoUrl,
            playback_url: camera.playback_url,
            stream_source_url: camera.stream_source_url || camera.rtsp_url || '',
            stream_type: camera.stream_type,
            status: camera.status,
          };
        });
    });
  }, [cameras]);

  useEffect(() => {
    if (showAISettings && aiConfig.provider === 'ollama') {
      fetchOllamaModels();
    }
  }, [aiConfig.provider, fetchOllamaModels, showAISettings]);

  // ==================== KEYBOARD SHORTCUTS ====================
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      
      const keyMap = {
        '1': () => setMode('search'),
        '2': () => setMode('live'),
        '3': () => setMode('tasks'),
        '4': () => setMode('analysis'),
        'Escape': () => {
          setShowAISettings(false);
          setShowEmailSettings(false);
          setShowWebhookSettings(false);
          setShowLogicPanel(false);
          setShowAnalysisLog(false);
        },
        'l': () => setShowLogicPanel(p => !p),
        'L': () => setShowLogicPanel(p => !p),
        'g': () => setShowAnalysisLog(p => !p),
        'G': () => setShowAnalysisLog(p => !p),
        'a': () => setShowAISettings(p => !p),
        'A': () => setShowAISettings(p => !p),
        'e': () => setShowEmailSettings(p => !p),
        'E': () => setShowEmailSettings(p => !p),
        'w': () => setShowWebhookSettings(p => !p),
        'W': () => setShowWebhookSettings(p => !p),
      };

      if (keyMap[e.key]) {
        e.preventDefault();
        keyMap[e.key]();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // ==================== ALERTS ====================
  const sendEmailAlert = async (alertType, data) => {
    if (!emailConfig.enabled) return;
    try {
      await api.post('/alerts/email', { config: emailConfig, alert_type: alertType, data });
    } catch (err) {
      console.error('Email alert failed:', err);
    }
  };

  const sendWebhookAlert = async (alertType, data) => {
    if (!webhookConfig.enabled || !webhookConfig.webhook_url) return;
    
    try {
      const payload = {
        alert_type: alertType,
        timestamp: new Date().toISOString(),
        data,
        source: 'video_search_system'
      };
      
      const headers = {
        'Content-Type': 'application/json',
        ...webhookConfig.headers
      };
      
      if (webhookConfig.use_webhook_site_cli && webhookConfig.webhook_site_uuid) {
        headers['X-Webhook-Site-UUID'] = webhookConfig.webhook_site_uuid;
      }
      
      const response = await fetch(webhookConfig.webhook_url, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(webhookConfig.timeout_seconds * 1000)
      });
      
      setWebhookHistory(prev => [{
        id: Date.now(),
        timestamp: Date.now(),
        alert_type: alertType,
        url: webhookConfig.webhook_url,
        status: response.status,
        success: response.ok
      }, ...prev].slice(0, 50));
      
    } catch (err) {
      console.error('Webhook alert failed:', err);
      setWebhookHistory(prev => [{
        id: Date.now(),
        timestamp: Date.now(),
        alert_type: alertType,
        url: webhookConfig.webhook_url,
        status: 0,
        success: false,
        error: err.message
      }, ...prev].slice(0, 50));
    }
  };

  const testWebhook = async () => {
    setWebhookTestStatus('Testing...');
    try {
      const testPayload = {
        alert_type: 'test',
        timestamp: new Date().toISOString(),
        message: 'Test webhook from Video Search System',
        source: 'video_search_system'
      };
      
      const headers = {
        'Content-Type': 'application/json',
        ...webhookConfig.headers
      };
      
      if (webhookConfig.use_webhook_site_cli && webhookConfig.webhook_site_uuid) {
        headers['X-Webhook-Site-UUID'] = webhookConfig.webhook_site_uuid;
      }
      
      const response = await fetch(webhookConfig.webhook_url, {
        method: 'POST',
        headers,
        body: JSON.stringify(testPayload),
        signal: AbortSignal.timeout(webhookConfig.timeout_seconds * 1000)
      });
      
      setWebhookTestStatus(response.ok ? `Success! Status: ${response.status}` : `Failed: HTTP ${response.status}`);
    } catch (err) {
      setWebhookTestStatus(`Error: ${err.message}`);
    }
  };

  // ==================== EVENT HANDLERS ====================
  const handleSearch = async (query, searchMode = 'clip') => {
    if (!query.trim()) return;
    setSearchQuery(query);
    setIsSearching(true);
    setError(null);
    
    try {
      const { data } = await api.get('/query', {
        params: { query, top_k: 20, mode: searchMode }
      });
      
      const videos = data.results.map(result => ({
        id: result.id,
        media_kind: 'video',
        source_type: result.source_type,
        source_name: result.source_name,
        video_url: result.video_chunk_path,
        thumbnail_path: result.thumbnail_path,
        start_offset: result.start_offset,
        end_offset: result.end_offset,
        timestamp: result.timestamp,
        frame_count: result.frame_count,
        score: result.score,
        urgency_level: result.urgency_level,
        detected_objects: result.detected_objects || [],
        title: `${result.source_name} (${formatTime(result.start_offset)} - ${formatTime(result.end_offset)})`,
        description: `Match: ${(result.score * 100).toFixed(1)}%`,
        tags: [result.source_type]
      }));
      
      setSearchResults(videos);
      setMissionAlerts(data.alerts || []);
    } catch (err) {
      setError('Search failed. Please try again.');
      setSearchResults([]);
      setMissionAlerts([]);
    } finally {
      setIsSearching(false);
    }
  };

  const handleVideoSelect = (video) => {
    if (selectedCameras.some(c => c.id === video.id)) {
      setSelectedCameras(prev => prev.filter(c => c.id !== video.id));
    } else {
      setSelectedCameras(prev => [...prev, {
        ...video,
        video_url: toApiMediaUrl(video.video_url),
        original_url: video.video_url
      }]);
    }
  };

  const handleCameraView = (camera) => {
    const playableUrl = camera.playback_url || '';
    handleVideoSelect({
      id: camera.camera_id,
      source_type: 'live',
      source_name: camera.camera_id,
      stream_type: camera.stream_type,
      stream_source_url: camera.stream_source_url || camera.rtsp_url,
      playback_url: camera.playback_url,
      video_url: playableUrl,
      title: camera.camera_id,
      description: camera.stream_source_url || camera.rtsp_url,
      status: camera.status,
      tags: ['live', camera.stream_type].filter(Boolean),
      isRegisteredStream: true
    });
  };

  const handleRemoveCamera = async (cameraId) => {
    try {
      await api.delete(`/cameras/${cameraId}`);
      setSelectedCameras(prev => prev.filter(camera => camera.id !== cameraId));
      await fetchCameras();
      setDispatchStatus(`Removed stream ${cameraId}`);
      setTimeout(() => setDispatchStatus(null), 3000);
    } catch (err) {
      setError(`Failed to remove stream ${cameraId}.`);
    }
  };

  const handleRegisterCamera = async (e) => {
    e.preventDefault();
    if (!newCameraId.trim() || !newCameraUrl.trim()) return;
    
    try {
      await api.post('/cameras/streams/register', {
        stream_id: newCameraId,
        stream_url: newCameraUrl,
        stream_type: streamType
      });
      setNewCameraId('');
      setNewCameraUrl('');
      await fetchCameras();
      setDispatchStatus('Stream registered successfully');
      setTimeout(() => setDispatchStatus(null), 3000);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to register stream.');
    }
  };

  const handleUrlUpload = async (e) => {
    e.preventDefault();
    if (!videoUrl.trim()) return;
    
    setUrlUploadLoading(true);
    try {
      await api.post('/videos/url', {
        url: videoUrl,
        max_duration: null
      });
      setVideoUrl('');
      fetchTasks();
      setDispatchStatus('Video URL queued for processing');
      setTimeout(() => setDispatchStatus(null), 3000);
    } catch (err) {
      setError('Failed to queue video URL.');
    } finally {
      setUrlUploadLoading(false);
    }
  };

  const handleOpordUpload = async (e) => {
    e.preventDefault();
    if (!opordFile) return;
    
    setOpordUploading(true);
    setOpordPreview(null);
    
    const formData = new FormData();
    formData.append('file', opordFile);
    
    try {
      const { data } = await api.post('/opord/upload-and-activate', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setOpordPreview(data);
      setOpordFile(null);
      fetchWatchAlert();
      setDispatchStatus('OPORD activated - Watch alert created');
      setTimeout(() => setDispatchStatus(null), 3000);
    } catch (err) {
      setError('Failed to upload and activate OPORD.');
    } finally {
      setOpordUploading(false);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      await api.post('/videos/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      fetchAssets();
      fetchTasks();
      setDispatchStatus('File uploaded successfully');
      setTimeout(() => setDispatchStatus(null), 3000);
      e.target.value = '';
    } catch (err) {
      setError('Failed to upload file.');
    }
  };

  const handleClearWatchAlert = async () => {
    if (!activeWatchAlert?.alert_id) return;
    try {
      await api.post(`/watch-alerts/${activeWatchAlert.alert_id}/clear`);
      setActiveWatchAlert(null);
      setLastWatchFindingCount(0);
    } catch (err) {
      setError('Failed to clear watch alert.');
    }
  };

  const handleSaveAIConfig = async () => {
    try {
      const payload = {
        ...aiConfig,
        ollama_base_url: aiConfig.ollama_base_url.trim(),
        ollama_model: aiConfig.ollama_model.trim(),
        openai_base_url: aiConfig.openai_base_url.trim(),
        openai_model: aiConfig.openai_model.trim(),
      };
      const { data } = await api.post('/ai/config', payload);
      if (data?.config) {
        setAiConfig(prev => ({
          ...prev,
          ...data.config,
          openai_api_key: payload.openai_api_key || prev.openai_api_key || ''
        }));
      }
      const ollamaProvider = data?.providers?.find(provider => provider.provider === 'ollama');
      if (ollamaProvider) {
        setOllamaStatus(ollamaProvider);
      }
      setAiConfigMessage('Configuration saved');
      await fetchOllamaModels();
      setTimeout(() => setAiConfigMessage(null), 3000);
    } catch (err) {
      setAiConfigMessage(err?.response?.data?.detail || 'Failed to save configuration');
    }
  };

  // ==================== RENDER ====================
  return (
    <div className="App">
      <header className="App-header">
        <div className="header-glow" />
        <div className="header-top">
          <div className="logo">
            <div className="logo-icon">
              <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M2 17L12 22L22 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M2 12L12 17L22 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <h1>Video Search System</h1>
          </div>
          
          <nav className="main-nav">
            {[
              { key: 'search', icon: '🔍', label: 'Search', kbd: '1' },
              { key: 'live', icon: '📹', label: 'Live', kbd: '2' },
              { key: 'tasks', icon: '📋', label: 'Tasks', kbd: '3' },
              { key: 'analysis', icon: '🤖', label: 'Analysis', kbd: '4' },
            ].map(({ key, icon, label, kbd }) => (
              <button
                key={key}
                className={mode === key ? 'active' : ''}
                onClick={() => setMode(key)}
                title={`Hotkey: ${kbd}`}
              >
                {icon} {label} <kbd>{kbd}</kbd>
              </button>
            ))}
          </nav>
          
          <div className="settings-nav">
            {[
              { key: 'logic', state: showLogicPanel, toggle: setShowLogicPanel, icon: '📊', label: 'Logic', kbd: 'L' },
              { key: 'log', state: showAnalysisLog, toggle: setShowAnalysisLog, icon: '📜', label: 'Log', kbd: 'G', badge: analysis.analysisLog.length },
              { key: 'ai', state: showAISettings, toggle: setShowAISettings, icon: '🤖', label: 'AI', kbd: 'A' },
              { key: 'email', state: showEmailSettings, toggle: setShowEmailSettings, icon: '📧', label: 'Email', kbd: 'E' },
              { key: 'webhook', state: showWebhookSettings, toggle: setShowWebhookSettings, icon: '🔗', label: 'Webhook', kbd: 'W' },
            ].map(({ key, state, toggle, icon, label, kbd, badge }) => (
              <button
                key={key}
                className={state ? 'active' : ''}
                onClick={() => toggle(!state)}
                title={`Hotkey: ${kbd}`}
              >
                {icon} {label} <kbd>{kbd}</kbd>
                {badge > 0 && <span className="badge-count">{badge}</span>}
              </button>
            ))}
          </div>
        </div>
        
        {mode === 'search' && (
          <div className="header-search">
            <SearchBar onSearch={handleSearch} isLoading={isSearching} />
          </div>
        )}
      </header>

      <div className="main-container">
        {/* Left Sidebar */}
        <div className="sidebar-panels">
          {showLogicPanel && (
            <div className="sidebar-panel">
              <div className="panel-header">
                <h3>📊 Logic Explanations</h3>
                <button className="close-btn" onClick={() => setShowLogicPanel(false)}>×</button>
              </div>
              <div className="panel-content">
                {logicExplanations.map((logic, idx) => (
                  <div key={idx} className="logic-card">
                    <h4>{logic.component}</h4>
                    <p>{logic.description}</p>
                    <code>{logic.formula}</code>
                  </div>
                ))}
              </div>
            </div>
          )}

          {showAnalysisLog && (
            <div className="sidebar-panel">
              <div className="panel-header">
                <h3>📜 Analysis Log ({analysis.analysisLog.length})</h3>
                <button className="close-btn" onClick={() => setShowAnalysisLog(false)}>×</button>
              </div>
              <div className="panel-content">
                <button className="clear-btn" onClick={analysis.clearAnalysisLog}>Clear All</button>
                {analysis.analysisLog.map(entry => (
                  <div 
                    key={entry.id} 
                    className={`log-entry ${analysis.expandedLogEntry === entry.id ? 'expanded' : ''}`}
                    onClick={() => analysis.setExpandedLogEntry(analysis.expandedLogEntry === entry.id ? null : entry.id)}
                  >
                    <div className="log-header">
                      <span>{analysis.getAnalysisIcon(entry.type)} {analysis.getAnalysisLabel(entry.type)}</span>
                      <span className="log-time">{formatTimestamp(entry.timestamp)}</span>
                      <button className="delete-btn" onClick={(e) => { e.stopPropagation(); analysis.deleteLogEntry(entry.id); }}>×</button>
                    </div>
                    {analysis.expandedLogEntry === entry.id && (
                      <div className="log-details">
                        <p><strong>Provider:</strong> {entry.provider}</p>
                        <p><strong>Summary:</strong> {entry.result?.summary}</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Center Content */}
        <div className="center-content">
          {error && <div className="error-banner">{error}</div>}
          {dispatchStatus && <div className="status-banner">{dispatchStatus}</div>}

          {activeWatchAlert && (
            <div className={`watch-alert priority-${activeWatchAlert.priority}`}>
              <div>
                <strong>🚨 OPORD Watch Active: {activeWatchAlert.watch_phrase}</strong>
                <p>{activeWatchAlert.banner_message}</p>
              </div>
              <div className="actions">
                <button onClick={handleClearWatchAlert}>Clear</button>
              </div>
            </div>
          )}

          {/* AI Dashboard */}
          <div className="ai-dashboard">
            <div className="dashboard-header">
              <h2>🤖 AI Analysis Dashboard</h2>
              <div className="controls">
                <label>
                  <input 
                    type="checkbox" 
                    checked={analysis.autoAnalysisEnabled} 
                    onChange={(e) => analysis.setAutoAnalysisEnabled(e.target.checked)} 
                  />
                  Auto-run
                </label>
                <button
                  onClick={analysis.runAllAIAnalyses}
                  disabled={analysis.autoAnalysisEnabled || analysis.anyAnalysisRunning}
                >
                  {analysis.anyAnalysisRunning ? 'Running…' : 'Run All Now'}
                </button>
              </div>
            </div>
            
            <div className="analysis-grid">
              {analysis.analysisTypes.map(type => {
                const latest = analysis.analysisLog.find(a => a.type === type);
                return (
                  <div key={type} className={`analysis-card ${latest?.result?.degraded ? 'degraded' : ''}`}>
                    <div className="card-header">
                      <span>{analysis.getAnalysisIcon(type)} {analysis.getAnalysisLabel(type)}</span>
                      {analysis.isAnalysisRunning(type) && <span className="badge">running</span>}
                      {latest?.cached && <span className="badge cached">cached</span>}
                      {latest?.result?.degraded && <span className="badge degraded">degraded</span>}
                    </div>
                    <div className="card-body">
                      {latest ? (
                        <>
                          <span className={`threat-level ${latest.result?.threat_level || 'unknown'}`}>
                            {latest.result?.threat_level?.toUpperCase() || 'UNKNOWN'}
                          </span>
                          <p>{latest.result?.summary?.substring(0, 60)}...</p>
                          <small>{formatTimestamp(latest.timestamp)}</small>
                        </>
                      ) : (
                        <p className="no-data">No analysis yet</p>
                      )}
                    </div>
                    <button
                      className="run-btn"
                      onClick={() => analysis.runAIAnalysis(type)}
                      disabled={analysis.isAnalysisRunning(type)}
                    >
                      {analysis.isAnalysisRunning(type) ? 'Running…' : 'Run'}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Stats */}
          {stats && (
            <div className="stats-row">
              {[
                { value: stats.total_clips.toLocaleString(), label: 'Clips' },
                { value: stats.active_cameras, label: 'Cameras' },
                { value: stats.pending_tasks, label: 'Tasks' },
                { value: analysis.analysisLog.length, label: 'Analyses' },
              ].map(({ value, label }) => (
                <div key={label} className="stat-box">
                  <span className="value">{value}</span>
                  <span className="label">{label}</span>
                </div>
              ))}
            </div>
          )}

          {/* Mode Content */}
          {mode === 'search' && (
            <>
              {predictions.length > 0 && (
                <div className="section">
                  <h3>📈 Risk Forecasts</h3>
                  <div className="predictions-row">
                    {predictions.slice(0, 4).map(p => (
                      <div key={p.source_name} className={`prediction-pill ${p.risk_level}`}>
                        <span>{p.source_name}</span>
                        <span>{Math.round(p.risk_score * 100)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {missionAlerts.length > 0 && (
                <div className="section">
                  <h3>🚨 Mission Alerts</h3>
                  <div className="alerts-row">
                    {missionAlerts.map(alert => (
                      <div key={alert.id} className={`alert-pill ${alert.urgency_level}`}>
                        <span>{alert.source_name}</span>
                        <span>{(alert.urgency_score * 100).toFixed(0)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="section">
                <h3>{searchQuery ? `Results for "${searchQuery}"` : 'Videos'}</h3>
                {isSearching ? (
                  <div className="loading">Searching...</div>
                ) : searchResults.length > 0 ? (
                  <VideoGrid videos={searchResults} onSelect={handleVideoSelect} selectedVideos={selectedCameras} />
                ) : (
                  <div className="empty">{searchQuery ? 'No results' : 'Enter a search query'}</div>
                )}
              </div>
            </>
          )}

          {mode === 'live' && (
            <div className="section">
              <h3>📹 Live Stream Management</h3>
              <form onSubmit={handleRegisterCamera} className="camera-form stream-form">
                <input 
                  placeholder="Stream ID (e.g., cam-001, youtube-live-1)" 
                  value={newCameraId} 
                  onChange={e => setNewCameraId(e.target.value)} 
                />
                <input 
                  placeholder="Stream URL (RTSP, HLS .m3u8, YouTube Live)" 
                  value={newCameraUrl} 
                  onChange={e => setNewCameraUrl(e.target.value)} 
                />
                <select value={streamType} onChange={e => setStreamType(e.target.value)}>
                  <option value="auto">🔍 Auto-detect</option>
                  <option value="rtsp">📹 RTSP Camera</option>
                  <option value="hls">📡 HLS Stream (.m3u8)</option>
                  <option value="youtube_live">▶️ YouTube Live</option>
                </select>
                <button type="submit">Add Stream</button>
              </form>
              
              <div className="stream-type-hints">
                <div className="hint">
                  <span className="hint-icon">📹</span>
                  <span>RTSP: <code>rtsp://camera-ip:554/stream</code></span>
                </div>
                <div className="hint">
                  <span className="hint-icon">📡</span>
                  <span>HLS: <code>https://server.com/stream.m3u8</code></span>
                </div>
                <div className="hint">
                  <span className="hint-icon">▶️</span>
                  <span>YouTube: <code>youtube.com/live/CHANNEL_ID</code></span>
                </div>
              </div>
              
              <div className="camera-list">
                {cameras.map(camera => (
                  <div key={camera.camera_id} className="camera-row">
                    <div>
                      <strong>{camera.camera_id}</strong>
                      <small>{camera.rtsp_url}</small>
                      <small className="stream-playback-hint">
                        {camera.playback_url
                          ? 'Playback ready'
                          : camera.stream_type === 'rtsp'
                            ? 'Waiting for latest processed segment'
                            : 'Playback will use direct stream URL'}
                      </small>
                      {camera.stream_type && (
                        <span className="stream-type-badge">{camera.stream_type}</span>
                      )}
                    </div>
                    <div className="actions">
                      <span className={`status ${camera.status}`}>{camera.status}</span>
                      <button type="button" onClick={() => handleCameraView(camera)}>
                        {selectedCameras.some(item => item.id === camera.camera_id && item.isRegisteredStream) ? 'Hide' : 'View'}
                      </button>
                      <button type="button" className="secondary" onClick={() => handleRemoveCamera(camera.camera_id)}>
                        Remove
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {mode === 'tasks' && (
            <div className="tasks-container">
              {/* Video URL Upload */}
              <div className="section">
                <h3>🌐 Video URL</h3>
                <p className="section-desc">Process videos from YouTube, Vimeo, or direct HTTP/HTTPS URLs</p>
                <form onSubmit={handleUrlUpload} className="url-upload-form">
                  <input 
                    type="url" 
                    placeholder="https://youtube.com/watch?v=... or https://example.com/video.mp4"
                    value={videoUrl}
                    onChange={e => setVideoUrl(e.target.value)}
                    disabled={urlUploadLoading}
                  />
                  <button type="submit" disabled={urlUploadLoading || !videoUrl.trim()}>
                    {urlUploadLoading ? '⏳ Queuing...' : '📥 Queue URL'}
                  </button>
                </form>
                <div className="url-hints">
                  <span>Supports: YouTube, Vimeo, direct MP4/WebM links</span>
                </div>
              </div>

              {/* OPORD Document Upload */}
              <div className="section opord-section">
                <h3>📜 OPORD Upload & Activation</h3>
                <p className="section-desc">Upload an Operations Order to activate AI watch alerts</p>
                
                {opordPreview ? (
                  <div className="opord-preview">
                    <div className="opord-header">
                      <span className="opord-status">✅ Activated</span>
                      <button className="close-btn" onClick={() => setOpordPreview(null)}>×</button>
                    </div>
                    <div className="opord-content">
                      <div className="opord-field">
                        <label>Watch Phrase</label>
                        <span className="watch-phrase">{opordPreview.parsed?.watch_phrase}</span>
                      </div>
                      <div className="opord-field">
                        <label>Priority</label>
                        <span className={`priority-badge priority-${opordPreview.parsed?.priority}`}>
                          {opordPreview.parsed?.priority}
                        </span>
                      </div>
                      <div className="opord-field">
                        <label>Keywords</label>
                        <div className="keyword-tags">
                          {opordPreview.parsed?.keywords?.map((kw, i) => (
                            <span key={i} className="keyword-tag">{kw}</span>
                          ))}
                        </div>
                      </div>
                      {opordPreview.parsed?.persons?.length > 0 && (
                        <div className="opord-field">
                          <label>Persons of Interest</label>
                          <div className="keyword-tags">
                            {opordPreview.parsed?.persons?.map((p, i) => (
                              <span key={i} className="person-tag">👤 {p}</span>
                            ))}
                          </div>
                        </div>
                      )}
                      {opordPreview.parsed?.locations?.length > 0 && (
                        <div className="opord-field">
                          <label>Locations</label>
                          <div className="keyword-tags">
                            {opordPreview.parsed?.locations?.map((loc, i) => (
                              <span key={i} className="location-tag">📍 {loc}</span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <form onSubmit={handleOpordUpload} className="opord-upload-form">
                    <div className="opord-dropzone">
                      <input 
                        type="file" 
                        accept=".pdf,.docx,.doc,.txt,.md"
                        onChange={e => setOpordFile(e.target.files[0])}
                        id="opord-file-input"
                        disabled={opordUploading}
                      />
                      <label htmlFor="opord-file-input" className="dropzone-label">
                        {opordFile ? (
                          <>
                            <span className="file-icon">📄</span>
                            <span className="file-name">{opordFile.name}</span>
                            <span className="file-size">({(opordFile.size / 1024).toFixed(1)} KB)</span>
                          </>
                        ) : (
                          <>
                            <span className="upload-icon">📜</span>
                            <span className="upload-text">Drop OPORD here or click to browse</span>
                            <span className="upload-hint">PDF, DOCX, TXT, MD supported</span>
                          </>
                        )}
                      </label>
                    </div>
                    <button 
                      type="submit" 
                      disabled={opordUploading || !opordFile}
                      className="opord-submit-btn"
                    >
                      {opordUploading ? '🔍 Parsing & Activating...' : '🚨 Upload & Activate Watch'}
                    </button>
                  </form>
                )}
              </div>

              {/* File Upload */}
              <div className="section">
                <h3>📁 File Upload</h3>
                <p className="section-desc">Upload local video, image, or document files</p>
                <div className="upload-area">
                  <input type="file" onChange={handleFileUpload} />
                </div>
              </div>
              
              {/* Tasks List */}
              <div className="section">
                <h3>📋 Processing Tasks</h3>
                <div className="task-list">
                  {tasks.length === 0 ? (
                    <div className="empty-tasks">No active tasks</div>
                  ) : (
                    tasks.map(task => (
                      <div key={task.task_id} className="task-row">
                        <div>
                          <code>{task.task_id?.slice(0, 8)}</code>
                          <span className="task-type">{task.type}</span>
                          {task.filename && <small>{task.filename}</small>}
                        </div>
                        <span className={`status ${task.status}`}>{task.status}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}

          {mode === 'analysis' && (
            <div className="section">
              <h3>📊 Analysis History</h3>
              <button onClick={() => {
                const sitrep = analysis.analysisLog.map(a => 
                  `[${new Date(a.timestamp).toLocaleString()}] ${analysis.getAnalysisLabel(a.type)}: ${a.result?.threat_level || 'N/A'}`
                ).join('\n');
                alert(`SITREP:\n\n${sitrep || 'No analyses yet'}`);
              }}>Generate SITREP</button>
            </div>
          )}

          {selectedCameras.length > 0 && (
            <div className="section streams-section">
              <h3>📺 Active Streams ({selectedCameras.length})</h3>
              <div className="streams-grid">
                {selectedCameras.map(video => (
                  <VideoPlayer 
                    key={video.id} 
                    video={video} 
                    onRemove={(id) => setSelectedCameras(prev => prev.filter(c => c.id !== id))} 
                  />
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right Sidebar - Settings */}
        <div className="right-sidebar">
          {showAISettings && (
            <div className="settings-panel">
              <div className="panel-header">
                <h3>⚙️ AI Settings</h3>
                <button className="close-btn" onClick={() => setShowAISettings(false)}>×</button>
              </div>
              <div className="panel-content">
                <div className="form-group">
                  <label>Provider</label>
                  <select value={aiConfig.provider} onChange={e => setAiConfig({...aiConfig, provider: e.target.value})}>
                    <option value="ollama">Ollama</option>
                    <option value="openai">OpenAI</option>
                    <option value="webgpu">WebGPU</option>
                  </select>
                </div>

                {aiConfig.provider === 'ollama' && (
                  <>
                    <div className="form-group">
                      <label>Ollama URL</label>
                      <input
                        value={aiConfig.ollama_base_url}
                        onChange={e => setAiConfig({...aiConfig, ollama_base_url: e.target.value})}
                        placeholder="http://localhost:11434"
                      />
                    </div>
                    <div className="form-group">
                      <label>Model</label>
                      <input
                        list="ollama-models"
                        value={aiConfig.ollama_model}
                        onChange={e => setAiConfig({...aiConfig, ollama_model: e.target.value})}
                        placeholder="llava:7b"
                      />
                      <datalist id="ollama-models">
                        {ollamaModels.map(model => (
                          <option key={model.name} value={model.name}>
                            {model.name}
                          </option>
                        ))}
                      </datalist>
                    </div>
                    <div className="ai-setup-note">
                      <strong>Local Ollama:</strong> run `ollama serve`, then pull a vision model such as `ollama pull llava:7b`.
                      If the API is running in Docker, the backend will also try `http://host.docker.internal:11434`.
                    </div>
                    <div className="button-row">
                      <button type="button" onClick={fetchOllamaModels}>Refresh Models</button>
                      <button type="button" onClick={handleSaveAIConfig}>Save</button>
                    </div>
                  </>
                )}

                {aiConfig.provider === 'openai' && (
                  <>
                    <div className="form-group">
                      <label>API Key</label>
                      <input
                        type="password"
                        value={aiConfig.openai_api_key}
                        onChange={e => setAiConfig({...aiConfig, openai_api_key: e.target.value})}
                        placeholder="sk-..."
                      />
                    </div>
                    <div className="form-group">
                      <label>Base URL</label>
                      <input
                        value={aiConfig.openai_base_url}
                        onChange={e => setAiConfig({...aiConfig, openai_base_url: e.target.value})}
                      />
                    </div>
                    <div className="form-group">
                      <label>Model</label>
                      <input
                        value={aiConfig.openai_model}
                        onChange={e => setAiConfig({...aiConfig, openai_model: e.target.value})}
                      />
                    </div>
                    <button type="button" onClick={handleSaveAIConfig}>Save</button>
                  </>
                )}

                {aiConfig.provider === 'webgpu' && (
                  <>
                    <div className="form-group">
                      <label className="checkbox">
                        <input type="checkbox" checked={aiConfig.webgpu_enabled} onChange={e => setAiConfig({...aiConfig, webgpu_enabled: e.target.checked})} />
                        Enable WebGPU
                      </label>
                    </div>
                    <div className="ai-setup-note">
                      WebGPU runs analysis in the browser. Enable it only on machines with browser GPU support.
                    </div>
                    <button type="button" onClick={handleSaveAIConfig}>Save</button>
                  </>
                )}

                {aiConfigMessage && <div className="message">{aiConfigMessage}</div>}
                
                {ollamaStatus && (
                  <div className="status-indicator">
                    <span className={`dot ${ollamaStatus.available ? 'online' : 'offline'}`} />
                    Ollama {ollamaStatus.available ? 'Online' : 'Offline'}
                    {ollamaStatus.model ? ` • ${ollamaStatus.model}` : ''}
                  </div>
                )}
                {ollamaStatus?.detail && (
                  <div className="ai-status-detail">{ollamaStatus.detail}</div>
                )}
                {Array.isArray(ollamaStatus?.actions) && ollamaStatus.actions.length > 0 && (
                  <div className="ai-status-actions">
                    {ollamaStatus.actions.map(action => (
                      <div key={action}>{action}</div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {showEmailSettings && (
            <div className="settings-panel">
              <div className="panel-header">
                <h3>📧 Email Settings</h3>
                <button className="close-btn" onClick={() => setShowEmailSettings(false)}>×</button>
              </div>
              <div className="panel-content">
                <label className="checkbox">
                  <input type="checkbox" checked={emailConfig.enabled} onChange={e => setEmailConfig({...emailConfig, enabled: e.target.checked})} />
                  Enable Email Alerts
                </label>
                <div className="form-group">
                  <label>SMTP Host</label>
                  <input value={emailConfig.smtp_host} onChange={e => setEmailConfig({...emailConfig, smtp_host: e.target.value})} />
                </div>
                <div className="form-group">
                  <label>Port</label>
                  <input type="number" value={emailConfig.smtp_port} onChange={e => setEmailConfig({...emailConfig, smtp_port: parseInt(e.target.value)})} />
                </div>
                <div className="form-group">
                  <label>Username</label>
                  <input value={emailConfig.smtp_user} onChange={e => setEmailConfig({...emailConfig, smtp_user: e.target.value})} />
                </div>
                <div className="form-group">
                  <label>Password</label>
                  <input type="password" value={emailConfig.smtp_password} onChange={e => setEmailConfig({...emailConfig, smtp_password: e.target.value})} />
                </div>
                <div className="form-group">
                  <label>To Emails</label>
                  <input value={emailConfig.to_emails.join(', ')} onChange={e => setEmailConfig({...emailConfig, to_emails: e.target.value.split(',').map(s => s.trim()).filter(Boolean)})} />
                </div>
                <button onClick={async () => {
                  try {
                    await api.post('/alerts/email/test', { config: emailConfig });
                    setEmailTestStatus('Test email sent!');
                  } catch (err) {
                    setEmailTestStatus(`Failed: ${err.message}`);
                  }
                }}>Test</button>
                {emailTestStatus && <div className="message">{emailTestStatus}</div>}
              </div>
            </div>
          )}

          {showWebhookSettings && (
            <div className="settings-panel">
              <div className="panel-header">
                <h3>🔗 Webhook Settings</h3>
                <button className="close-btn" onClick={() => setShowWebhookSettings(false)}>×</button>
              </div>
              <div className="panel-content webhook-settings">
                <label className="checkbox">
                  <input type="checkbox" checked={webhookConfig.enabled} onChange={e => setWebhookConfig({...webhookConfig, enabled: e.target.checked})} />
                  Enable Webhook Alerts
                </label>

                <div className="form-group">
                  <label>Webhook URL</label>
                  <input placeholder="https://webhook.site/unique-id" value={webhookConfig.webhook_url} onChange={e => setWebhookConfig({...webhookConfig, webhook_url: e.target.value})} />
                </div>

                <div className="form-group">
                  <label>Unique Email</label>
                  <input placeholder="unique-id@webhook.site" value={webhookConfig.unique_email} onChange={e => setWebhookConfig({...webhookConfig, unique_email: e.target.value})} />
                </div>

                <div className="form-group">
                  <label>DNS Name (Optional)</label>
                  <input placeholder="your-name.webhook.site" value={webhookConfig.dns_name} onChange={e => setWebhookConfig({...webhookConfig, dns_name: e.target.value})} />
                </div>

                <div className="webhook-site-cli-section">
                  <h4>Webhook.site CLI</h4>
                  <label className="checkbox">
                    <input type="checkbox" checked={webhookConfig.use_webhook_site_cli} onChange={e => setWebhookConfig({...webhookConfig, use_webhook_site_cli: e.target.checked})} />
                    Use webhook.site CLI
                  </label>

                  {webhookConfig.use_webhook_site_cli && (
                    <>
                      <div className="form-group">
                        <label>Webhook.site UUID</label>
                        <input placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" value={webhookConfig.webhook_site_uuid} onChange={e => setWebhookConfig({...webhookConfig, webhook_site_uuid: e.target.value})} />
                      </div>
                      <label className="checkbox">
                        <input type="checkbox" checked={webhookConfig.bidirectional_proxy} onChange={e => setWebhookConfig({...webhookConfig, bidirectional_proxy: e.target.checked})} />
                        Bidirectional Proxy
                      </label>
                      {webhookConfig.bidirectional_proxy && (
                        <div className="form-group">
                          <label>Proxy URL</label>
                          <input placeholder="http://localhost:8080" value={webhookConfig.proxy_url} onChange={e => setWebhookConfig({...webhookConfig, proxy_url: e.target.value})} />
                        </div>
                      )}
                    </>
                  )}
                </div>

                <div className="form-group">
                  <label>Timeout (seconds)</label>
                  <input type="number" value={webhookConfig.timeout_seconds} onChange={e => setWebhookConfig({...webhookConfig, timeout_seconds: parseInt(e.target.value) || 30})} />
                </div>

                <div className="alert-options">
                  <h4>Alert On:</h4>
                  <label className="checkbox">
                    <input type="checkbox" checked={webhookConfig.alert_on_critical} onChange={e => setWebhookConfig({...webhookConfig, alert_on_critical: e.target.checked})} />
                    Critical Events
                  </label>
                  <label className="checkbox">
                    <input type="checkbox" checked={webhookConfig.alert_on_watch_match} onChange={e => setWebhookConfig({...webhookConfig, alert_on_watch_match: e.target.checked})} />
                    Watch Match
                  </label>
                  <label className="checkbox">
                    <input type="checkbox" checked={webhookConfig.alert_on_analysis} onChange={e => setWebhookConfig({...webhookConfig, alert_on_analysis: e.target.checked})} />
                    Analysis Complete
                  </label>
                </div>

                <div className="button-row">
                  <button onClick={testWebhook}>Test Webhook</button>
                  <button className="secondary" onClick={() => setWebhookConfig(DEFAULT_WEBHOOK_CONFIG)}>Reset</button>
                </div>

                {webhookTestStatus && (
                  <div className={`message ${webhookTestStatus.includes('Success') ? 'success' : 'error'}`}>
                    {webhookTestStatus}
                  </div>
                )}

                {webhookHistory.length > 0 && (
                  <div className="webhook-history">
                    <h4>Recent Deliveries</h4>
                    {webhookHistory.slice(0, 5).map(h => (
                      <div key={h.id} className={`history-item ${h.success ? 'success' : 'failed'}`}>
                        <span>{new Date(h.timestamp).toLocaleTimeString()}</span>
                        <span>{h.alert_type}</span>
                        <span>{h.status}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
      
      <footer className="app-footer">
        <div className="shortcuts-hint">
          <span><kbd>1-4</kbd> Modes</span>
          <span><kbd>L</kbd> Logic</span>
          <span><kbd>G</kbd> Log</span>
          <span><kbd>A</kbd> AI</span>
          <span><kbd>E</kbd> Email</span>
          <span><kbd>W</kbd> Webhook</span>
          <span><kbd>Esc</kbd> Close All</span>
        </div>
      </footer>
    </div>
  );
}

export default App;
