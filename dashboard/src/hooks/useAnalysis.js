import { useState, useCallback, useRef, useEffect } from 'react';

const ANALYSIS_TYPES = ['threats', 'predictions', 'correlations', 'mission-review'];

const ANALYSIS_LABELS = {
  'threats': 'Threat Analysis',
  'predictions': 'Predictions',
  'correlations': 'Correlations',
  'mission-review': 'Mission Review',
};

const ANALYSIS_ICONS = {
  'threats': '⚠️',
  'predictions': '📈',
  'correlations': '🔗',
  'mission-review': '📋',
};

/**
 * Hook for managing AI analysis functionality
 */
export function useAnalysis(api, aiConfig, webgpuService, context) {
  const [analysisLog, setAnalysisLog] = useState(() => {
    try {
      const saved = localStorage.getItem('video_search_analysis_log');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [expandedLogEntry, setExpandedLogEntry] = useState(null);
  const [autoAnalysisEnabled, setAutoAnalysisEnabled] = useState(false);
  const [runningTypes, setRunningTypes] = useState([]);
  const autoAnalysisInterval = useRef(null);

  // Persist analysis log
  useEffect(() => {
    localStorage.setItem('video_search_analysis_log', JSON.stringify(analysisLog.slice(-100)));
  }, [analysisLog]);

  const addToAnalysisLog = useCallback((type, result, ctx = {}) => {
    const entry = {
      id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      timestamp: Date.now(),
      type,
      result,
      context: ctx,
      provider: result.provider_used || result.provider || 'unknown',
      model: result.model_used || result.model || 'unknown',
      degraded: result.degraded || false,
      cached: result.cached || false
    };
    setAnalysisLog(prev => [entry, ...prev].slice(0, 100));
    return entry;
  }, []);

  const deleteLogEntry = useCallback((entryId) => {
    setAnalysisLog(prev => prev.filter(e => e.id !== entryId));
    if (expandedLogEntry === entryId) {
      setExpandedLogEntry(null);
    }
  }, [expandedLogEntry]);

  const clearAnalysisLog = useCallback(() => {
    if (window.confirm('Clear all analysis history?')) {
      setAnalysisLog([]);
      setExpandedLogEntry(null);
    }
  }, []);

  const runAIAnalysis = useCallback(async (type, addToLogFlag = true) => {
    if (!ANALYSIS_TYPES.includes(type)) {
      return { error: `Invalid analysis type: ${type}`, type };
    }

    setRunningTypes(prev => (prev.includes(type) ? prev : [...prev, type]));

    try {
      let result;
      
      if (aiConfig.provider === 'webgpu' && aiConfig.webgpu_enabled && webgpuService?.isReady()) {
        const handlers = {
          'threats': webgpuService.analyzeThreats,
          'predictions': webgpuService.analyzePredictions,
          'correlations': webgpuService.analyzeCorrelations,
          'mission-review': webgpuService.analyzeMissionReview,
        };
        result = await handlers[type](context);
      } else {
        const response = await api.get(`/ai/analyze/${type}`, { timeout: 60000 });
        result = response.data;
      }

      const enrichedResult = { ...result, type, timestamp: Date.now() };
      
      if (addToLogFlag) {
        addToAnalysisLog(type, enrichedResult, context);
      }
      
      return enrichedResult;
    } catch (err) {
      console.error('AI analysis error:', err);
      const errorResult = { 
        error: err?.message || 'Analysis failed',
        type,
        degraded: true,
        provider_used: 'fallback',
        timestamp: Date.now()
      };
      if (addToLogFlag) {
        addToAnalysisLog(type, errorResult);
      }
      return errorResult;
    } finally {
      setRunningTypes(prev => prev.filter(item => item !== type));
    }
  }, [api, aiConfig, webgpuService, context, addToAnalysisLog]);

  const runAllAIAnalyses = useCallback(async () => {
    for (const type of ANALYSIS_TYPES) {
      await runAIAnalysis(type);
      await new Promise(r => setTimeout(r, 500));
    }
  }, [runAIAnalysis]);

  // Auto-analysis interval
  useEffect(() => {
    if (autoAnalysisEnabled) {
      runAllAIAnalyses();
      autoAnalysisInterval.current = setInterval(runAllAIAnalyses, 60000);
    } else {
      if (autoAnalysisInterval.current) {
        clearInterval(autoAnalysisInterval.current);
      }
    }
    return () => {
      if (autoAnalysisInterval.current) {
        clearInterval(autoAnalysisInterval.current);
      }
    };
  }, [autoAnalysisEnabled, runAllAIAnalyses]);

  const getAnalysisLabel = useCallback((type) => ANALYSIS_LABELS[type] || type, []);
  const getAnalysisIcon = useCallback((type) => ANALYSIS_ICONS[type] || '🤖', []);
  const isAnalysisRunning = useCallback((type) => runningTypes.includes(type), [runningTypes]);

  return {
    analysisLog,
    expandedLogEntry,
    setExpandedLogEntry,
    autoAnalysisEnabled,
    setAutoAnalysisEnabled,
    runningTypes,
    anyAnalysisRunning: runningTypes.length > 0,
    isAnalysisRunning,
    addToAnalysisLog,
    deleteLogEntry,
    clearAnalysisLog,
    runAIAnalysis,
    runAllAIAnalyses,
    getAnalysisLabel,
    getAnalysisIcon,
    analysisTypes: ANALYSIS_TYPES,
  };
}

export default useAnalysis;
