import { useState, useCallback, useEffect } from 'react';
import webgpuService from '../services/webgpuService';

/**
 * Hook for managing WebGPU functionality
 */
export function useWebGPU(aiConfig) {
  const [status, setStatus] = useState({ state: 'idle' });
  const [loadProgress, setLoadProgress] = useState(0);
  const [checking, setChecking] = useState(false);

  const checkStatus = useCallback(async () => {
    setChecking(true);
    try {
      const support = await webgpuService.checkWebGPUSupport();
      if (support.supported) {
        setStatus({
          state: webgpuService.isReady() ? 'ready' : 'supported',
          detail: support.adapter ? `GPU: ${support.adapter}` : 'WebGPU available',
          degraded: support.degraded,
          warning: support.warning
        });
      } else {
        setStatus({ 
          state: 'error', 
          error: support.error,
          degraded: true,
          actions: support.actions
        });
      }
    } catch (err) {
      setStatus({ 
        state: 'error', 
        error: err?.message || 'Failed to check WebGPU',
        degraded: true
      });
    } finally {
      setChecking(false);
    }
  }, []);

  const loadModel = useCallback(async (preferredModel = null) => {
    try {
      setStatus({ state: 'loading' });
      await webgpuService.loadModel(preferredModel);
      setStatus({
        state: 'ready',
        detail: 'Model loaded successfully'
      });
      return true;
    } catch (err) {
      setStatus({
        state: 'error',
        error: err.message,
        degraded: true
      });
      return false;
    }
  }, []);

  // Check status on mount if WebGPU is enabled
  useEffect(() => {
    if (aiConfig.webgpu_enabled) {
      checkStatus();
    }
  }, [aiConfig.webgpu_enabled, checkStatus]);

  return {
    status,
    loadProgress,
    checking,
    checkStatus,
    loadModel,
    isReady: webgpuService.isReady.bind(webgpuService),
    service: webgpuService,
  };
}

export default useWebGPU;
