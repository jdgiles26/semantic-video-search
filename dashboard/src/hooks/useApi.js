/**
 * Enhanced API hooks with caching, retry logic, and error handling.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
});

/**
 * Generic data fetching hook with caching and retry logic.
 */
export function useQuery(key, fetcher, options = {}) {
  const {
    enabled = true,
    refetchInterval = null,
    retryCount = 3,
    retryDelay = 1000,
    onError = null,
    onSuccess = null,
  } = options;

  const [data, setData] = useState(null);
  const [isLoading, setIsLoading] = useState(enabled);
  const [error, setError] = useState(null);
  const retryAttempt = useRef(0);
  const intervalRef = useRef(null);

  const fetch = useCallback(async (isRetry = false) => {
    if (!enabled) return;

    if (!isRetry) {
      setIsLoading(true);
      setError(null);
    }

    try {
      const result = await fetcher();
      setData(result);
      setError(null);
      retryAttempt.current = 0;
      onSuccess?.(result);
    } catch (err) {
      const isNetworkError = !err.response;
      const shouldRetry = isNetworkError && retryAttempt.current < retryCount;

      if (shouldRetry) {
        retryAttempt.current += 1;
        setTimeout(() => fetch(true), retryDelay * retryAttempt.current);
      } else {
        setError(err);
        onError?.(err);
      }
    } finally {
      if (!isRetry) {
        setIsLoading(false);
      }
    }
  }, [enabled, fetcher, retryCount, retryDelay, onError, onSuccess]);

  const refetch = useCallback(() => {
    retryAttempt.current = 0;
    return fetch();
  }, [fetch]);

  useEffect(() => {
    fetch();

    if (refetchInterval) {
      intervalRef.current = setInterval(fetch, refetchInterval);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [fetch, refetchInterval]);

  return { data, isLoading, error, refetch };
}

/**
 * Hook for paginated data fetching.
 */
export function usePaginatedQuery(key, fetcher, options = {}) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(options.pageSize || 20);
  const [total, setTotal] = useState(0);

  const paginatedFetcher = useCallback(async () => {
    const result = await fetcher({ page, pageSize });
    setTotal(result.total || 0);
    return result;
  }, [fetcher, page, pageSize]);

  const query = useQuery(`${key}-${page}`, paginatedFetcher, options);

  return {
    ...query,
    page,
    setPage,
    pageSize,
    setPageSize,
    total,
    totalPages: Math.ceil(total / pageSize),
  };
}

/**
 * Hook for mutations (POST, PUT, DELETE).
 */
export function useMutation(mutationFn, options = {}) {
  const { onError, onSuccess } = options;
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  const mutate = useCallback(async (...args) => {
    setIsLoading(true);
    setError(null);

    try {
      const result = await mutationFn(...args);
      setData(result);
      onSuccess?.(result);
      return result;
    } catch (err) {
      setError(err);
      onError?.(err);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [mutationFn, onError, onSuccess]);

  const reset = useCallback(() => {
    setData(null);
    setError(null);
    setIsLoading(false);
  }, []);

  return { mutate, isLoading, error, data, reset };
}

/**
 * Hook for optimistic updates.
 */
export function useOptimisticMutation(mutationFn, options = {}) {
  const { queryKey, currentData, setData, updateFn } = options;
  const mutation = useMutation(mutationFn, options);

  const optimisticMutate = useCallback(async (...args) => {
    const previousData = currentData;
    
    // Optimistically update
    if (updateFn && currentData) {
      setData(updateFn(currentData, ...args));
    }

    try {
      const result = await mutation.mutate(...args);
      return result;
    } catch (err) {
      // Rollback on error
      if (previousData !== undefined) {
        setData(previousData);
      }
      throw err;
    }
  }, [mutation, currentData, setData, updateFn]);

  return { ...mutation, mutate: optimisticMutate };
}

/**
 * Predefined API hooks for common operations.
 */
export function useStats(options = {}) {
  return useQuery('stats', () => api.get('/stats').then(r => r.data), {
    refetchInterval: 5000,
    ...options,
  });
}

export function useCameras(options = {}) {
  return useQuery('cameras', () => api.get('/cameras').then(r => r.data), {
    refetchInterval: 10000,
    ...options,
  });
}

export function useTasks(options = {}) {
  return useQuery('tasks', () => api.get('/tasks').then(r => r.data), {
    refetchInterval: 5000,
    ...options,
  });
}

export function useAssets(options = {}) {
  return useQuery('assets', () => api.get('/uploads/assets').then(r => r.data), {
    ...options,
  });
}

export function usePredictions(options = {}) {
  return useQuery('predictions', () => api.get('/predictions').then(r => r.data), {
    refetchInterval: 30000,
    ...options,
  });
}

export function useWatchAlert(options = {}) {
  return useQuery('watch-alert', () => api.get('/watch-alerts/active').then(r => r.data), {
    refetchInterval: 5000,
    ...options,
  });
}

export function useSearch(options = {}) {
  return useMutation(
    ({ query, searchMode = 'clip' }) => 
      api.get('/query', { params: { query, top_k: 20, mode: searchMode } }).then(r => r.data),
    options
  );
}

export function useRegisterStream(options = {}) {
  return useMutation(
    (data) => api.post('/streams/register', data).then(r => r.data),
    options
  );
}

export function useUploadVideo(options = {}) {
  return useMutation(
    (formData) => api.post('/uploads/videos', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }).then(r => r.data),
    options
  );
}

export function useUploadOpord(options = {}) {
  return useMutation(
    (formData) => api.post('/opord/upload-and-activate', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }).then(r => r.data),
    options
  );
}

export function useQueueUrl(options = {}) {
  return useMutation(
    (url) => api.post('/tasks/url', { url }).then(r => r.data),
    options
  );
}

export function useClearWatchAlert(options = {}) {
  return useMutation(
    (alertId) => api.post(`/watch-alerts/${alertId}/clear`).then(r => r.data),
    options
  );
}

export function useDispatchAlert(options = {}) {
  return useMutation(
    (data) => api.post('/alerts/dispatch', data).then(r => r.data),
    options
  );
}

export { api };
