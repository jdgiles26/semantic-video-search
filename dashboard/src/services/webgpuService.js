/**
 * WebGPU Service - Browser-based AI inference using Hugging Face Transformers
 * 
 * Uses Qwen2.5-VL for vision-language tasks
 * Falls back to degraded mode in air-gapped environments
 */

// Qwen2.5-VL is a vision-language model that works well for surveillance analysis
const MODEL_ID = 'onnx-community/Qwen2.5-VL-3B-Instruct-q4f16';
const LOAD_TIMEOUT_MS = 180000; // 3 minutes for larger model
const ANALYSIS_TIMEOUT_MS = 90000; // 90 seconds for analysis

// Fallback to smaller model if main fails
const FALLBACK_MODEL_ID = 'onnx-community/Llama-3.2-1B-Instruct-q4f16';

class WebGPUService {
  constructor() {
    this.generator = null;
    this.loadingPromise = null;
    this.status = { state: 'idle', degraded: false };
    this.onStatusChange = null;
    this.onProgress = null;
    this.transformersModule = null;
    this.abortController = null;
    this.currentModel = MODEL_ID;
    this.fallbackMode = false;
    this.analysisCache = new Map(); // Cache for analysis results
    this.maxCacheSize = 50;
  }

  setStatusCallback(callback) {
    this.onStatusChange = typeof callback === 'function' ? callback : null;
  }

  setProgressCallback(callback) {
    this.onProgress = typeof callback === 'function' ? callback : null;
  }

  updateStatus(newStatus) {
    this.status = { ...this.status, ...newStatus, timestamp: Date.now() };
    if (this.onStatusChange) {
      try {
        this.onStatusChange(this.status);
      } catch (e) {
        console.warn('Status callback error:', e);
      }
    }
  }

  isReady() {
    return this.status.state === 'ready' && this.generator !== null;
  }

  isLoading() {
    return this.status.state === 'loading';
  }

  isDegraded() {
    return this.status.degraded || this.fallbackMode;
  }

  async checkWebGPUSupport() {
    if (typeof navigator === 'undefined' || !navigator.gpu) {
      return { 
        supported: false, 
        degraded: true,
        error: 'WebGPU not available - requires Chrome 113+, Edge 113+, or Firefox Nightly',
        actions: ['Use Ollama local backend instead', 'Update to a supported browser']
      };
    }
    try {
      const adapter = await navigator.gpu.requestAdapter();
      if (!adapter) {
        return { 
          supported: false, 
          degraded: true,
          error: 'No WebGPU adapter found - check GPU drivers',
          actions: ['Update GPU drivers', 'Use Ollama local backend instead']
        };
      }
      const info = await adapter.requestAdapterInfo?.() || {};
      const isLowPower = info.architecture?.includes('integrated') || 
                        info.vendor?.toLowerCase().includes('intel');
      
      return { 
        supported: true, 
        degraded: isLowPower,
        adapter: info.description || info.vendor || 'Unknown GPU',
        info: info,
        warning: isLowPower ? 'Integrated GPU detected - performance may be limited' : null
      };
    } catch (err) {
      return { 
        supported: false, 
        degraded: true,
        error: `WebGPU init failed: ${err?.message || err}`,
        actions: ['Use Ollama local backend instead']
      };
    }
  }

  async loadTransformersFromCDN() {
    if (this.transformersModule) return this.transformersModule;
    if (window.HFTransformers) {
      this.transformersModule = window.HFTransformers;
      return this.transformersModule;
    }

    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.type = 'module';
      script.innerHTML = `
        import * as transformers from 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.5.0';
        window.HFTransformers = transformers;
        window.dispatchEvent(new Event('transformers-loaded'));
      `;
      
      const handler = () => {
        window.removeEventListener('transformers-loaded', handler);
        this.transformersModule = window.HFTransformers;
        resolve(window.HFTransformers);
      };
      
      window.addEventListener('transformers-loaded', handler);
      
      script.onerror = (err) => {
        window.removeEventListener('transformers-loaded', handler);
        reject(new Error('Failed to load transformers library - check internet connection'));
      };
      
      document.head.appendChild(script);
      
      setTimeout(() => {
        if (!window.HFTransformers) {
          reject(new Error('Timeout loading transformers library - check connection'));
        }
      }, 60000);
    });
  }

  async loadModel(useFallback = false) {
    if (this.generator && !useFallback) {
      this.updateStatus({ state: 'ready' });
      return this.generator;
    }

    if (this.loadingPromise) {
      return this.loadingPromise;
    }

    const support = await this.checkWebGPUSupport();
    if (!support.supported) {
      this.updateStatus({ 
        state: 'error', 
        error: support.error,
        degraded: true,
        actions: support.actions
      });
      throw new Error(support.error);
    }

    this.currentModel = useFallback ? FALLBACK_MODEL_ID : MODEL_ID;
    this.fallbackMode = useFallback;

    this.loadingPromise = (async () => {
      try {
        this.updateStatus({ 
          state: 'loading', 
          message: useFallback ? 'Loading fallback model...' : 'Loading AI library...', 
          progress: 0,
          degraded: support.degraded
        });
        
        let transformers;
        try {
          transformers = await this.loadTransformersFromCDN();
        } catch (cdnErr) {
          // CDN failed - air-gapped or network issue
          this.updateStatus({
            state: 'error',
            error: 'Failed to load AI library from CDN - air-gapped?',
            degraded: true,
            actions: ['Use Ollama local backend', 'Check internet connection']
          });
          throw cdnErr;
        }
        
        this.updateStatus({ state: 'loading', message: 'Initializing WebGPU...', progress: 5 });

        // Configure pipeline with error handling
        const pipelineConfig = {
          dtype: 'q4',
          device: 'webgpu',
          progress_callback: (p) => {
            if (p.status === 'progress') {
              const progress = Math.round(p.progress);
              this.updateStatus({
                state: 'loading',
                message: `Downloading ${useFallback ? 'fallback ' : ''}model... ${progress}%`,
                progress: Math.max(5, progress)
              });
              if (this.onProgress) {
                this.onProgress(progress);
              }
            }
          }
        };

        let gen;
        try {
          gen = await transformers.pipeline('text-generation', this.currentModel, pipelineConfig);
        } catch (modelErr) {
          if (!useFallback) {
            console.warn('Primary model failed, trying fallback:', modelErr);
            this.loadingPromise = null;
            return this.loadModel(true);
          }
          throw modelErr;
        }

        this.generator = gen;
        this.updateStatus({ 
          state: 'ready',
          degraded: support.degraded || useFallback,
          model: this.currentModel
        });
        return gen;
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : String(err);
        this.updateStatus({ 
          state: 'error', 
          error: errorMsg,
          degraded: true
        });
        this.loadingPromise = null;
        throw err;
      }
    })();

    return this.loadingPromise;
  }

  getCacheKey(type, context) {
    // Simple hash of context for caching
    const str = JSON.stringify({ type, context });
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return hash.toString();
  }

  getCachedAnalysis(type, context) {
    const key = this.getCacheKey(type, context);
    const cached = this.analysisCache.get(key);
    if (cached && (Date.now() - cached.timestamp) < 300000) { // 5 min cache
      return cached.data;
    }
    return null;
  }

  setCachedAnalysis(type, context, data) {
    const key = this.getCacheKey(type, context);
    if (this.analysisCache.size >= this.maxCacheSize) {
      const firstKey = this.analysisCache.keys().next().value;
      this.analysisCache.delete(firstKey);
    }
    this.analysisCache.set(key, { data, timestamp: Date.now() });
  }

  async analyze(prompt, options = {}) {
    if (!prompt || typeof prompt !== 'string') {
      throw new Error('Invalid prompt provided');
    }
    
    // Check cache first
    const cacheKey = options.cacheType ? this.getCacheKey(options.cacheType, options.context || {}) : null;
    if (cacheKey && options.useCache !== false) {
      const cached = this.analysisCache.get(cacheKey);
      if (cached && (Date.now() - cached.timestamp) < 300000) {
        return { ...cached.data, cached: true };
      }
    }
    
    if (!this.generator) {
      await this.loadModel();
    }
    
    if (!this.generator) {
      throw new Error('Model not loaded');
    }

    const { maxTokens = 2048, timeout = ANALYSIS_TIMEOUT_MS } = options;

    const messages = [
      { role: 'user', content: prompt.slice(0, 8000) }
    ];

    let result = '';
    let reasoning = '';
    let inThinking = false;

    const transformers = this.transformersModule;
    if (!transformers?.TextStreamer) {
      throw new Error('Transformers library not properly loaded');
    }
    
    const streamer = new transformers.TextStreamer(this.generator.tokenizer, {
      skip_prompt: true,
      skip_special_tokens: false,
      callback_function: (token) => {
        if (!token || token === '<|im_end|>' || token === '<|end|>') return;

        if (token.includes('<think>') || token.includes('<|im_start|>think')) {
          inThinking = true;
          return;
        }
        if (token.includes('</think>') || token.includes('<|im_end|>')) {
          inThinking = false;
          return;
        }

        if (inThinking) {
          reasoning += token;
        } else {
          result += token;
        }
      }
    });

    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new Error('Analysis timed out')), timeout);
    });

    try {
      await Promise.race([
        this.generator(messages, {
          max_new_tokens: Math.min(maxTokens, 4096),
          streamer,
          do_sample: false
        }),
        timeoutPromise
      ]);

      const response = {
        result: (result || '').trim(),
        reasoning: (reasoning || '').trim(),
        provider: 'webgpu',
        model: this.currentModel,
        degraded: this.fallbackMode
      };

      // Cache the result
      if (cacheKey) {
        this.setCachedAnalysis(options.cacheType, options.context || {}, response);
      }

      return response;
    } catch (err) {
      if (err?.message?.includes('timed out')) {
        return {
          result: (result || 'Analysis timed out').trim(),
          reasoning: (reasoning || '').trim(),
          provider: 'webgpu',
          model: this.currentModel,
          partial: true,
          degraded: this.fallbackMode
        };
      }
      throw err;
    }
  }

  async analyzeThreats(context) {
    const cacheKey = 'threats';
    const cached = this.getCachedAnalysis(cacheKey, context);
    if (cached) return { ...cached, cached: true };

    const prompt = `Analyze the following video surveillance data for potential threats.

Context:
${JSON.stringify(context, null, 2)}

Respond ONLY with valid JSON:
{"threat_level":"low|medium|high|critical","threats":[],"confidence":0.5,"summary":"","recommendations":[],"analysis_factors":[]}`;

    try {
      const response = await this.analyze(prompt, { 
        maxTokens: 1024, 
        cacheType: cacheKey,
        context,
        useCache: true
      });

      try {
        const jsonMatch = response.result.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          const parsed = JSON.parse(jsonMatch[0]);
          const result = { 
            ...parsed, 
            provider_used: 'webgpu', 
            model_used: this.currentModel, 
            reasoning: response.reasoning,
            degraded: this.fallbackMode || response.degraded
          };
          this.setCachedAnalysis(cacheKey, context, result);
          return result;
        }
      } catch (e) {
        console.warn('Parse error:', e);
      }

      return {
        threat_level: 'unknown', threats: [], confidence: 0.5,
        summary: response.result, recommendations: [],
        provider_used: 'webgpu', model_used: this.currentModel, 
        reasoning: response.reasoning,
        degraded: this.fallbackMode
      };
    } catch (err) {
      // Return degraded response on failure
      return {
        threat_level: 'unknown',
        threats: [],
        confidence: 0,
        summary: 'WebGPU analysis failed - using fallback',
        recommendations: ['Switch to Ollama backend for local analysis'],
        provider_used: 'webgpu',
        model_used: this.currentModel,
        degraded: true,
        error: err.message
      };
    }
  }

  async analyzePredictions(context) {
    const cacheKey = 'predictions';
    const cached = this.getCachedAnalysis(cacheKey, context);
    if (cached) return { ...cached, cached: true };

    const prompt = `Analyze risk prediction data.

Data:
${JSON.stringify(context, null, 2)}

Respond ONLY with valid JSON:
{"threat_level":"low|medium|high","predictions":[],"confidence":0.5,"summary":"","recommendations":[],"analysis_factors":[]}`;

    try {
      const response = await this.analyze(prompt, { 
        maxTokens: 1024,
        cacheType: cacheKey,
        context,
        useCache: true
      });

      try {
        const jsonMatch = response.result.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          const parsed = JSON.parse(jsonMatch[0]);
          const result = { 
            ...parsed, 
            provider_used: 'webgpu', 
            model_used: this.currentModel, 
            reasoning: response.reasoning,
            degraded: this.fallbackMode
          };
          this.setCachedAnalysis(cacheKey, context, result);
          return result;
        }
      } catch (e) {
        console.warn('Parse error:', e);
      }

      return {
        threat_level: 'medium', predictions: [], confidence: 0.5,
        summary: response.result, recommendations: [],
        provider_used: 'webgpu', model_used: this.currentModel, 
        reasoning: response.reasoning,
        degraded: this.fallbackMode
      };
    } catch (err) {
      return {
        threat_level: 'unknown',
        predictions: [],
        confidence: 0,
        summary: 'WebGPU analysis failed - using fallback',
        provider_used: 'webgpu',
        degraded: true,
        error: err.message
      };
    }
  }

  async analyzeCorrelations(context) {
    const cacheKey = 'correlations';
    const cached = this.getCachedAnalysis(cacheKey, context);
    if (cached) return { ...cached, cached: true };

    const prompt = `Analyze correlations in intelligence data.

Data:
${JSON.stringify(context, null, 2)}

Respond ONLY with valid JSON:
{"threat_level":"low|medium|high","correlations":[],"confidence":0.5,"summary":"","recommendations":[],"analysis_factors":[]}`;

    try {
      const response = await this.analyze(prompt, { 
        maxTokens: 1024,
        cacheType: cacheKey,
        context,
        useCache: true
      });

      try {
        const jsonMatch = response.result.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          const parsed = JSON.parse(jsonMatch[0]);
          const result = { 
            ...parsed, 
            provider_used: 'webgpu', 
            model_used: this.currentModel, 
            reasoning: response.reasoning,
            degraded: this.fallbackMode
          };
          this.setCachedAnalysis(cacheKey, context, result);
          return result;
        }
      } catch (e) {
        console.warn('Parse error:', e);
      }

      return {
        threat_level: 'medium', correlations: [], confidence: 0.5,
        summary: response.result, recommendations: [],
        provider_used: 'webgpu', model_used: this.currentModel, 
        reasoning: response.reasoning,
        degraded: this.fallbackMode
      };
    } catch (err) {
      return {
        threat_level: 'unknown',
        correlations: [],
        confidence: 0,
        summary: 'WebGPU analysis failed - using fallback',
        provider_used: 'webgpu',
        degraded: true,
        error: err.message
      };
    }
  }

  async analyzeMissionReview(context) {
    const cacheKey = 'mission-review';
    const cached = this.getCachedAnalysis(cacheKey, context);
    if (cached) return { ...cached, cached: true };

    const prompt = `Perform a mission review across surveillance clips, uploaded images/documents, predictions, and live sources.

Data:
${JSON.stringify(context, null, 2)}

Respond ONLY with valid JSON:
{"threat_level":"low|medium|high|critical","summary":"","alerts":[],"predictions":[],"correlations":[],"priorities":[],"trends":[],"detected_themes":[],"recommendations":[],"confidence":0.5,"analysis_factors":[]}`;

    try {
      const response = await this.analyze(prompt, { 
        maxTokens: 1536,
        cacheType: cacheKey,
        context,
        useCache: true
      });

      try {
        const jsonMatch = response.result.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          const parsed = JSON.parse(jsonMatch[0]);
          const result = { 
            ...parsed, 
            provider_used: 'webgpu', 
            model_used: this.currentModel, 
            reasoning: response.reasoning,
            degraded: this.fallbackMode
          };
          this.setCachedAnalysis(cacheKey, context, result);
          return result;
        }
      } catch (e) {
        console.warn('Parse error:', e);
      }

      return {
        threat_level: 'medium', alerts: [], predictions: [], correlations: [], priorities: [],
        trends: [], detected_themes: [], confidence: 0.5,
        summary: response.result, recommendations: [],
        provider_used: 'webgpu', model_used: this.currentModel, 
        reasoning: response.reasoning,
        degraded: this.fallbackMode
      };
    } catch (err) {
      return {
        threat_level: 'unknown',
        alerts: [], predictions: [], correlations: [], priorities: [],
        trends: [], detected_themes: [], confidence: 0,
        summary: 'WebGPU analysis failed - using fallback',
        provider_used: 'webgpu',
        degraded: true,
        error: err.message
      };
    }
  }

  unload() {
    this.generator = null;
    this.loadingPromise = null;
    this.updateStatus({ state: 'idle', degraded: false });
  }

  clearCache() {
    this.analysisCache.clear();
  }
}

const webgpuService = new WebGPUService();
export { webgpuService };
export default webgpuService;
