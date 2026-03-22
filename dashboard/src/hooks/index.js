/**
 * Custom React hooks for the Video Search System.
 */

// Re-export all hooks from useApi
export {
  useQuery,
  usePaginatedQuery,
  useMutation,
  useOptimisticMutation,
  useStats,
  useCameras,
  useTasks,
  useAssets,
  usePredictions,
  useWatchAlert,
  useSearch,
  useRegisterStream,
  useUploadVideo,
  useUploadOpord,
  useQueueUrl,
  useClearWatchAlert,
  useDispatchAlert,
  api,
} from './useApi';

// Re-export other hooks
export { default as useLocalStorage } from './useLocalStorage';
export { default as useAnalysis } from './useAnalysis';
export { default as useWebGPU } from './useWebGPU';
