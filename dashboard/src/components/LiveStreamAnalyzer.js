import React, { useEffect, useRef, useState, useCallback } from 'react';
import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

/**
 * LiveStreamAnalyzer - Real-time AI analysis overlay for live streams
 * 
 * Features:
 * - YOLO object detection overlay on video
 * - Real-time person/vehicle detection
 * - OPORD watch alert correlation
 * - AI-powered analysis of frames
 * - Detection history and statistics
 */

class LiveStreamDetector {
  constructor(videoElement, canvasElement, options = {}) {
    this.video = videoElement;
    this.canvas = canvasElement;
    this.ctx = canvasElement.getContext('2d');
    
    this.options = {
      detectionInterval: options.detectionInterval || 1000, // ms between detections
      confidenceThreshold: options.confidenceThreshold || 0.3,
      enableOverlay: options.enableOverlay !== false,
      enableAIAnalysis: options.enableAIAnalysis || false,
      cameraId: options.cameraId || 'unknown',
      watchAlert: options.watchAlert || null,
      onDetection: options.onDetection || null,
      onAlert: options.onAlert || null,
      ...options
    };
    
    this.isRunning = false;
    this.detectionTimer = null;
    this.lastFrameData = null;
    this.detectionHistory = [];
    this.frameCount = 0;
    this.detectionsCount = 0;
    
    // COCO class colors for visualization
    this.classColors = {
      person: '#FF6B6B',
      car: '#4ECDC4',
      truck: '#45B7D1',
      bus: '#96CEB4',
      motorcycle: '#FFEAA7',
      bicycle: '#DDA0DD',
      boat: '#98D8C8',
      airplane: '#F7DC6F',
      train: '#BB8FCE',
      backpack: '#85C1E9',
      handbag: '#F8C471',
      suitcase: '#82E0AA',
      cat: '#F1948A',
      dog: '#85C1E9',
      bird: '#F7DC6F',
      horse: '#D7BDE2',
      default: '#BB8FCE'
    };
  }
  
  start() {
    if (this.isRunning) return;
    this.isRunning = true;
    this.detectLoop();
    console.log('[LiveStreamDetector] Started for camera:', this.options.cameraId);
  }
  
  stop() {
    this.isRunning = false;
    if (this.detectionTimer) {
      clearTimeout(this.detectionTimer);
      this.detectionTimer = null;
    }
    this.clearOverlay();
    console.log('[LiveStreamDetector] Stopped for camera:', this.options.cameraId);
  }
  
  async detectLoop() {
    if (!this.isRunning) return;
    
    try {
      await this.captureAndDetect();
    } catch (err) {
      console.error('[LiveStreamDetector] Detection error:', err);
    }
    
    // Schedule next detection
    this.detectionTimer = setTimeout(() => this.detectLoop(), this.options.detectionInterval);
  }
  
  async captureAndDetect() {
    if (!this.video || this.video.paused || this.video.ended) return;
    
    // Ensure canvas matches video dimensions
    if (this.canvas.width !== this.video.videoWidth || 
        this.canvas.height !== this.video.videoHeight) {
      this.canvas.width = this.video.videoWidth;
      this.canvas.height = this.video.videoHeight;
    }
    
    // Capture frame
    this.ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
    this.frameCount++;
    
    // Get frame data as base64
    const frameData = this.canvas.toDataURL('image/jpeg', 0.8);
    this.lastFrameData = frameData;
    
    // Send to backend for detection
    try {
      const response = await axios.post(`${API_BASE_URL}/live/detect`, {
        camera_id: this.options.cameraId,
        frame_data: frameData,
        timestamp: Date.now()
      }, {
        timeout: 5000
      });
      
      if (response.data && response.data.detections) {
        this.handleDetections(response.data.detections, response.data.analysis);
      }
    } catch (err) {
      // Backend detection failed, use client-side fallback if enabled
      if (this.options.enableClientDetection) {
        this.runClientSideDetection();
      }
    }
  }
  
  handleDetections(detections, analysis) {
    this.detectionsCount += detections.length;
    
    // Add to history
    this.detectionHistory.push({
      timestamp: Date.now(),
      detections: detections,
      analysis: analysis
    });
    
    // Keep only last 100 entries
    if (this.detectionHistory.length > 100) {
      this.detectionHistory.shift();
    }
    
    // Draw overlay
    if (this.options.enableOverlay) {
      this.drawOverlay(detections);
    }
    
    // Check for watch alert matches
    if (this.options.watchAlert) {
      this.checkWatchAlertMatch(detections);
    }
    
    // Call callback
    if (this.options.onDetection) {
      this.options.onDetection(detections, analysis);
    }
  }
  
  drawOverlay(detections) {
    // Clear previous overlay (but keep the video frame)
    this.ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
    
    detections.forEach(det => {
      const { label, confidence, bbox } = det;
      const [x1, y1, x2, y2] = bbox || [0, 0, 0, 0];
      
      const color = this.classColors[label] || this.classColors.default;
      const isWatchMatch = this.isWatchTarget(label);
      
      // Draw bounding box
      this.ctx.strokeStyle = isWatchMatch ? '#FF0000' : color;
      this.ctx.lineWidth = isWatchMatch ? 4 : 2;
      this.ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
      
      // Draw label background
      const labelText = `${label} ${(confidence * 100).toFixed(0)}%`;
      this.ctx.font = isWatchMatch ? 'bold 16px Arial' : '14px Arial';
      const textMetrics = this.ctx.measureText(labelText);
      const textHeight = 20;
      
      this.ctx.fillStyle = isWatchMatch ? 'rgba(255, 0, 0, 0.8)' : color + 'CC';
      this.ctx.fillRect(x1, y1 - textHeight, textMetrics.width + 10, textHeight);
      
      // Draw label text
      this.ctx.fillStyle = '#FFFFFF';
      this.ctx.fillText(labelText, x1 + 5, y1 - 5);
      
      // Draw watch alert indicator
      if (isWatchMatch) {
        this.ctx.fillStyle = '#FF0000';
        this.ctx.beginPath();
        this.ctx.arc(x1 + 10, y1 + 10, 8, 0, 2 * Math.PI);
        this.ctx.fill();
        
        this.ctx.fillStyle = '#FFFFFF';
        this.ctx.font = 'bold 12px Arial';
        this.ctx.fillText('!', x1 + 7, y1 + 14);
      }
    });
    
    // Draw stats
    this.drawStats();
  }
  
  drawStats() {
    const statsY = this.canvas.height - 10;
    
    this.ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
    this.ctx.fillRect(10, statsY - 60, 200, 55);
    
    this.ctx.fillStyle = '#FFFFFF';
    this.ctx.font = '12px Arial';
    this.ctx.fillText(`Frames: ${this.frameCount}`, 15, statsY - 45);
    this.ctx.fillText(`Detections: ${this.detectionsCount}`, 15, statsY - 30);
    this.ctx.fillText(`Camera: ${this.options.cameraId}`, 15, statsY - 15);
    
    if (this.options.watchAlert) {
      this.ctx.fillStyle = '#FF6B6B';
      this.ctx.fillText(`WATCH: ${this.options.watchAlert.watch_phrase}`, 15, statsY - 55);
    }
  }
  
  isWatchTarget(label) {
    if (!this.options.watchAlert) return false;
    const watchLabels = this.options.watchAlert.watch_labels || [];
    return watchLabels.includes(label.toLowerCase());
  }
  
  checkWatchAlertMatch(detections) {
    if (!this.options.watchAlert) return;
    
    const watchLabels = this.options.watchAlert.watch_labels || [];
    const matches = detections.filter(det => 
      watchLabels.includes(det.label.toLowerCase()) &&
      det.confidence >= this.options.confidenceThreshold
    );
    
    if (matches.length > 0 && this.options.onAlert) {
      this.options.onAlert({
        type: 'watch_match',
        cameraId: this.options.cameraId,
        watchPhrase: this.options.watchAlert.watch_phrase,
        matches: matches,
        timestamp: Date.now()
      });
    }
  }
  
  clearOverlay() {
    if (this.ctx) {
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }
  }
  
  getStats() {
    return {
      frameCount: this.frameCount,
      detectionsCount: this.detectionsCount,
      detectionRate: this.frameCount > 0 ? (this.detectionsCount / this.frameCount).toFixed(2) : 0,
      recentDetections: this.detectionHistory.slice(-10)
    };
  }
}

/**
 * React component for live stream with AI overlay
 */
export function LiveStreamWithAI({ 
  videoUrl, 
  cameraId, 
  watchAlert,
  onDetection,
  onAlert,
  onReady,
  onError,
  enabled = true,
  showControls = true
}) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const detectorRef = useRef(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [stats, setStats] = useState({ frameCount: 0, detectionsCount: 0, detectionRate: 0 });
  const [recentDetections, setRecentDetections] = useState([]);
  const [aiAnalysis, setAiAnalysis] = useState(null);
  
  // Initialize detector
  useEffect(() => {
    if (!enabled || !videoRef.current || !canvasRef.current) return;
    
    detectorRef.current = new LiveStreamDetector(videoRef.current, canvasRef.current, {
      cameraId: cameraId || 'unknown',
      watchAlert: watchAlert,
      detectionInterval: 1000,
      confidenceThreshold: 0.3,
      enableOverlay: true,
      onDetection: (detections, analysis) => {
        setRecentDetections(prev => [...prev.slice(-9), { timestamp: Date.now(), detections }]);
        if (analysis) {
          setAiAnalysis(analysis);
        }
        if (onDetection) onDetection(detections, analysis);
      },
      onAlert: (alert) => {
        if (onAlert) onAlert(alert);
      }
    });
    
    return () => {
      if (detectorRef.current) {
        detectorRef.current.stop();
      }
    };
  }, [enabled, cameraId, watchAlert, onDetection, onAlert]);
  
  // Start/stop analysis when video plays/pauses
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !detectorRef.current) return;
    
    const handlePlay = () => {
      setIsAnalyzing(true);
      detectorRef.current.start();
      
      // Update stats periodically
      const statsInterval = setInterval(() => {
        if (detectorRef.current) {
          setStats(detectorRef.current.getStats());
        }
      }, 1000);
      
      video._statsInterval = statsInterval;
    };
    
    const handlePause = () => {
      setIsAnalyzing(false);
      detectorRef.current.stop();
      if (video._statsInterval) {
        clearInterval(video._statsInterval);
      }
    };
    
    video.addEventListener('play', handlePlay);
    video.addEventListener('pause', handlePause);
    video.addEventListener('ended', handlePause);
    
    // Auto-start if already playing
    if (!video.paused) {
      handlePlay();
    }
    
    return () => {
      video.removeEventListener('play', handlePlay);
      video.removeEventListener('pause', handlePause);
      video.removeEventListener('ended', handlePause);
      if (video._statsInterval) {
        clearInterval(video._statsInterval);
      }
    };
  }, []);
  
  const handleManualAnalyze = useCallback(async () => {
    if (!detectorRef.current) return;
    
    try {
      await detectorRef.current.captureAndDetect();
    } catch (err) {
      console.error('Manual analysis failed:', err);
    }
  }, []);
  
  return (
    <div className="live-stream-analyzer">
      <div className="video-container" style={{ position: 'relative' }}>
        <video
          ref={videoRef}
          src={videoUrl}
          controls
          autoPlay
          muted
          crossOrigin="anonymous"
          onCanPlay={() => {
            if (onReady) onReady();
          }}
          onError={(event) => {
            if (onError) onError(event);
          }}
          style={{ width: '100%', maxHeight: '500px' }}
        />
        <canvas
          ref={canvasRef}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            pointerEvents: 'none'
          }}
        />
        
        {isAnalyzing && (
          <div className="analysis-indicator" style={{
            position: 'absolute',
            top: 10,
            right: 10,
            background: 'rgba(0, 255, 0, 0.8)',
            color: 'black',
            padding: '4px 8px',
            borderRadius: '4px',
            fontSize: '12px',
            fontWeight: 'bold'
          }}>
            ● AI ANALYZING
          </div>
        )}
        
        {watchAlert && (
          <div className="watch-alert-indicator" style={{
            position: 'absolute',
            top: 10,
            left: 10,
            background: 'rgba(255, 0, 0, 0.8)',
            color: 'white',
            padding: '4px 8px',
            borderRadius: '4px',
            fontSize: '12px',
            fontWeight: 'bold'
          }}>
            🚨 WATCH: {watchAlert.watch_phrase}
          </div>
        )}
      </div>
      
      {showControls && (
        <div className="analysis-controls" style={{ marginTop: '10px' }}>
          <div className="stats-bar" style={{ 
            display: 'flex', 
            gap: '20px',
            padding: '10px',
            background: '#1a1a2e',
            borderRadius: '4px',
            fontSize: '12px'
          }}>
            <span>Frames: <strong>{stats.frameCount}</strong></span>
            <span>Detections: <strong>{stats.detectionsCount}</strong></span>
            <span>Rate: <strong>{stats.detectionRate}/frame</strong></span>
            <button 
              onClick={handleManualAnalyze}
              style={{
                marginLeft: 'auto',
                padding: '4px 12px',
                background: '#4ECDC4',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              Analyze Now
            </button>
          </div>
          
          {recentDetections.length > 0 && (
            <div className="recent-detections" style={{ marginTop: '10px' }}>
              <h4>Recent Detections</h4>
              <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                {recentDetections.slice(-5).map((det, idx) => (
                  <div key={idx} style={{
                    padding: '8px',
                    background: '#16213e',
                    borderRadius: '4px',
                    fontSize: '11px'
                  }}>
                    {det.detections.map((d, i) => (
                      <span key={i} style={{ 
                        color: d.confidence > 0.7 ? '#4ECDC4' : '#FFEAA7',
                        marginRight: '8px'
                      }}>
                        {d.label} ({(d.confidence * 100).toFixed(0)}%)
                      </span>
                    ))}
                    <span style={{ color: '#666' }}>
                      {new Date(det.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          {aiAnalysis && (
            <div className="ai-analysis" style={{ 
              marginTop: '10px',
              padding: '10px',
              background: '#0f3460',
              borderRadius: '4px',
              fontSize: '12px'
            }}>
              <h4>AI Analysis</h4>
              <p>{aiAnalysis.summary || 'Analysis in progress...'}</p>
              {aiAnalysis.threat_level && (
                <span style={{
                  padding: '2px 8px',
                  background: aiAnalysis.threat_level === 'critical' ? '#FF0000' : 
                             aiAnalysis.threat_level === 'high' ? '#FF6B6B' : '#4ECDC4',
                  borderRadius: '4px',
                  fontWeight: 'bold'
                }}>
                  {aiAnalysis.threat_level.toUpperCase()}
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default LiveStreamWithAI;
