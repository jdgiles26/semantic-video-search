# AGENTS.md - AI Agent Guidance

Guidelines for AI agents working on the Video Search System codebase.

## Project Context

**Domain**: Real-time semantic video surveillance and search  
**Stack**: FastAPI backend, React frontend, Milvus vector DB, Redis cache  
**AI Pattern**: Multi-provider (Ollama local → OpenAI cloud → WebGPU browser)

## Critical Files Reference

| File | Purpose | Edit Caution |
|------|---------|--------------|
| `api/main.py` | FastAPI routes, lazy service init | HIGH - Core API |
| `processing/vector_store.py` | Milvus schema, embedding storage | HIGH - Data integrity |
| `processing/ai_provider.py` | Multi-backend AI abstraction | MEDIUM - Provider logic |
| `processing/opord_parser.py` | NLP OPORD parsing (BERT/HF) | MEDIUM - AI/NLP |
| `processing/object_detector.py` | YOLO real-time detection | MEDIUM - CV |
| `processing/risk_predictor_worker.py` | Risk scoring formula | MEDIUM - Algorithm |
| `processing/mission_intelligence.py` | Urgency/correlation scoring | MEDIUM - Algorithm |
| `dashboard/src/App.js` | Main React component | MEDIUM - UI state |
| `dashboard/src/components/LiveStreamAnalyzer.js` | Live YOLO overlay | MEDIUM - CV UI |
| `dashboard/src/services/webgpuService.js` | In-browser AI | HIGH - CDN/async |

## Code Conventions

### Python (Backend)
- Type hints required for public functions
- Async functions for I/O operations
- Use `logging` module, not print()
- Error handling: catch specific exceptions, log with context
- Lazy initialization pattern for expensive services

### JavaScript (Frontend)
- Functional components with hooks
- State management: useState/useRef (no Redux)
- CSS classes in App.css, not inline styles
- Defensive checks before array/object access
- Timeouts for all async operations

### CSS
- CSS custom properties (variables) for theming
- BEM-like naming: `.component-element--modifier`
- Animations via @keyframes, not JS
- Glow effects via box-shadow CSS variables

## Testing Commands

```bash
# Backend API
cd /path/to/project
uvicorn api.main:app --reload --port 8000
curl http://localhost:8000/healthz

# Frontend
cd dashboard
npm start  # Dev server
npm run build  # Production build

# Type checking (if configured)
cd dashboard && npm run lint
```

## Common Patterns

### Adding a New API Endpoint
```python
@app.get("/new-endpoint")
async def new_endpoint(param: str = Query(default="value")):
    try:
        service = get_service_instance()
        result = await service.process(param)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Endpoint failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
```

### Adding AI Analysis Type
1. Add method in `processing/ai_provider.py`
2. Add endpoint in `api/main.py`
3. Add analysis type to `runAIAnalysis()` in `dashboard/src/App.js`
4. Update `validTypes` array validation

### Adding OPORD Parser Backend
1. Add model to `DEFAULT_MODELS` in `processing/opord_parser.py`
2. Implement extraction method (e.g., `_extract_custom_entities`)
3. Call from `parse()` method
4. Update `ParsedOpord` dataclass if adding new fields

### Live Stream Detection Pattern
```python
# Backend: Add real-time detection endpoint
@app.post("/live/detect")
async def live_detect(request: LiveDetectRequest):
    # Decode base64 frame
    # Run YOLO detection
    # Check watch alert correlation
    # Return detections + analysis
```

### WebGPU Service Pattern
```javascript
// CDN loading required - do NOT npm install @huggingface/transformers
// CRA webpack cannot handle ES modules with import.meta

async loadTransformersFromCDN() {
  // Inject script tag with type="module"
  // Load from jsdelivr CDN
  // Wait for window.HFTransformers
}
```

## Known Issues & Workarounds

### WebGPU/CRA Compatibility
**Problem**: @huggingface/transformers uses `import.meta` unsupported by CRA webpack  
**Solution**: Dynamic CDN loading via injected script tag (see webgpuService.js)

### Milvus Connection Timeouts
**Problem**: First query after cold start can timeout  
**Solution**: `ensure_collection_loaded()` called on init

### Redis Pub/Sub Memory
**Problem**: Long-running workers accumulate messages  
**Solution**: TTL on all cached data, periodic cleanup

### Hugging Face Model Download
**Problem**: First use downloads large models (BERT ~400MB, BART ~1.6GB)  
**Solution**: Models cached in `~/.cache/huggingface/`. Pre-download for offline use.

### YOLO Detection on Live Streams
**Problem**: High CPU usage with real-time detection  
**Solution**: Configurable detection interval (default 1s), use YOLOv8-nano for speed

## Architecture Decisions

### Why Multi-Provider AI?
1. Ollama: Local inference, no API costs, privacy
2. OpenAI: Reliable cloud fallback, better models
3. WebGPU: Zero-server option, edge deployment

### Why CLIP + YOLO Hybrid?
- CLIP: Semantic understanding ("person running away")
- YOLO: Precise object detection ("person", "car", "weapon")
- Hybrid: Best of both, adaptive weighting

### Why Lazy Service Initialization?
- Expensive models (CLIP, YOLO) only loaded when needed
- Faster API startup time
- Memory efficiency when features unused

### Why Multi-Backend OPORD Parsing?
- **Hugging Face Local**: Free, no API key, works offline
- **Hugging Face API**: Fallback when local models unavailable
- **Ollama/OpenAI**: LLM-based parsing for complex documents
- Graceful degradation: tries local → API → LLM

### Why Real-Time YOLO Overlay?
- Immediate visual feedback for operators
- Watch alert correlation in real-time
- Bounding boxes help verify detections
- Canvas overlay preserves video controls

## Agent Task Guidelines

### When Adding Features
1. Check existing patterns in similar files
2. Follow type annotation conventions
3. Add error handling with logging
4. Update README if user-facing
5. Test before committing

### When Fixing Bugs
1. Reproduce issue first
2. Check related code for similar bugs
3. Add defensive checks where appropriate
4. Don't change algorithm unless necessary

### When Refactoring
1. Preserve existing behavior
2. Update tests if they exist
3. Document breaking changes
4. Keep commits atomic

### Documentation Updates
- README.md: User-facing, installation, quick start
- AGENTS.md: AI agent guidance, patterns, conventions
- Code comments: Only where logic is non-obvious

## File Ownership

Files agents should **rarely modify** without explicit request:
- `docker-compose.yml` - Infrastructure
- `requirements.txt` - Dependencies (version pinning)
- `package.json` - Frontend dependencies

Files agents can **safely modify**:
- `App.js` - UI logic, state management
- `App.css` - Styling, animations
- Python processing modules - Business logic
- README.md, AGENTS.md - Documentation

## Commit Message Format

```
type(scope): brief description

- Detail 1
- Detail 2

Types: feat, fix, refactor, docs, style, test
Scopes: api, frontend, processing, infra
```

Example:
```
fix(api): handle empty query results gracefully

- Add null check before iterating results
- Return empty array instead of error
```

## Emergency Contacts

For critical production issues, escalate via:
1. Check logs: `docker compose logs -f api`
2. Health endpoint: `curl localhost:8000/healthz`
3. Milvus status: `curl localhost:19530/healthz`
4. Redis status: `redis-cli ping`
