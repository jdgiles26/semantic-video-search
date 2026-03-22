# Video Search System

Real-time semantic video search platform with CLIP embeddings, YOLO object detection, risk prediction, and multi-provider AI analysis.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (React)                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐│
│  │ VideoPlayer │  │  SearchBar  │  │  VideoGrid  │  │  WebGPU AI Service  ││
│  │ (HLS/RTSP)  │  │ (CLIP/YOLO) │  │ (Results)   │  │  (In-Browser LLM)   ││
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            API LAYER (FastAPI)                              │
│  /query  /cameras  /tasks  /predictions  /ai/analyze  /logic/explanations  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          ▼                           ▼                           ▼
┌─────────────────┐      ┌─────────────────────┐      ┌─────────────────────┐
│   Milvus        │      │      Redis          │      │   AI Providers      │
│   Vector Store  │      │   Cache/Queue       │      │ Ollama/OpenAI/WebGPU│
│   (Embeddings)  │      │   (Metadata)        │      │                     │
└─────────────────┘      └─────────────────────┘      └─────────────────────┘
          ▲                           ▲
          │                           │
┌─────────────────────────────────────────────────────────────────────────────┐
│                          PROCESSING WORKERS                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐│
│  │ RTSPWorker   │  │ URLWorker    │  │ RiskPredictor│  │ MissionIntel     ││
│  │ (Live Feeds) │  │ (VOD Ingest) │  │ (Forecasts)  │  │ (Urgency/Alerts) ││
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

## Technology Stack

### Backend
| Component | Technology | Purpose |
|-----------|------------|---------|
| API Server | FastAPI 0.100+ | REST API, async request handling |
| Vector Database | Milvus 2.3+ | CLIP embedding storage, similarity search |
| Cache/Queue | Redis 7+ | Metadata cache, task queues, pub/sub |
| Embeddings | OpenCLIP (ViT-B-32) | 512-dim semantic video embeddings |
| Object Detection | YOLOv8 | Real-time object detection for hybrid search |
| Video Processing | FFmpeg, OpenCV | Frame extraction, HLS transcoding |

### Frontend
| Component | Technology | Purpose |
|-----------|------------|---------|
| Framework | React 18 | SPA dashboard |
| Video Player | ReactPlayer + HLS.js | Live stream and VOD playback |
| Styling | CSS3 (custom) | Dark theme with glow effects |
| In-Browser AI | @huggingface/transformers | WebGPU model inference |

### AI Providers
| Provider | Model | Use Case |
|----------|-------|----------|
| Ollama (Local) | llava:7b | Vision analysis, report generation |
| OpenAI | gpt-4o-mini | Cloud-based analysis fallback |
| WebGPU | LFM2.5-1.2B-Thinking | In-browser inference (no server) |

### Infrastructure
| Component | Technology | Purpose |
|-----------|------------|---------|
| Containers | Docker Compose | Service orchestration |
| Proxy | Nginx | Static file serving, reverse proxy |
| Storage | Local volumes | Video chunks, thumbnails |

## Core Components

### 1. Vector Store (`processing/vector_store.py`)
```python
class VideoVectorStore:
    """Milvus integration for CLIP embeddings.
    
    Schema: id, vector(512D), source_type, source_name, timestamp, 
            video_chunk_path, thumbnail_path, start_offset, end_offset
    
    Index: IVF_FLAT with Inner Product similarity
    """
```

### 2. Risk Predictor (`processing/risk_predictor_worker.py`)
```python
class RiskPredictorWorker:
    """Proactive risk forecasting from mission events.
    
    Formula: risk_score = 0.55 × min(1, signal_60m / 5) + 0.45 × min(1, trend)
    
    Where:
      - signal_60m: Weighted event accumulation over 60 minutes
      - trend: ratio of 15-min signal to 60-min signal (acceleration)
    """
```

### 3. Mission Intelligence (`processing/mission_intelligence.py`)
```python
class MissionIntelligenceEngine:
    """Urgency scoring and cross-source correlation.
    
    Urgency Levels:
      - Critical (0.45): active shooter, explosion, hostage
      - High (0.25): weapon, fire, assault, emergency
      - Medium (0.12): suspicious, accident, anomaly
    
    Correlation Score: Jaccard similarity of detected objects across sources
    """
```

### 4. AI Provider Service (`processing/ai_provider.py`)
```python
class AIProviderService:
    """Multi-backend AI with automatic fallback.
    
    Priority: Ollama (local) → OpenAI (cloud) → WebGPU (browser)
    
    Methods:
      - analyze(): General analysis with context
      - analyze_threat(): Threat assessment with confidence
      - predict_risk(): Risk trend analysis
      - correlate_sources(): Cross-source pattern detection
    """
```

### 5. Hybrid Search (`processing/hybrid_search.py`)
```python
class HybridScorer:
    """Combines CLIP semantic + YOLO object detection.
    
    Final Score = α × CLIP_score + (1-α) × YOLO_match_score
    
    Where α adapts based on query type (object vs. scene)
    """
```

## API Endpoints

### Search & Query
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/query` | GET | Semantic search with CLIP/YOLO hybrid |
| `/cameras` | GET | List registered camera sources |
| `/cameras` | POST | Register new RTSP camera |
| `/process-url` | POST | Ingest video from URL |
| `/upload` | POST | Upload video file |

### Intelligence
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/predictions` | GET | Risk forecast data |
| `/mission/alerts` | GET | Urgent alerts from all sources |
| `/mission/correlations` | GET | Cross-source patterns |
| `/mission/sitrep` | GET | LLM-generated situation report |

### AI Analysis
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ai/providers` | GET | Available AI backends and status |
| `/ai/config` | POST | Update AI provider configuration |
| `/ai/analyze/{type}` | GET | Run threat/prediction/correlation analysis |
| `/logic/explanations` | GET | Programmatic logic documentation |

## Configuration

### Environment Variables
```bash
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530

# Storage
STORAGE_PATH=/app/storage

# AI Providers
AI_PROVIDER=ollama                    # ollama|openai|webgpu
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llava:7b
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
WEBGPU_ENABLED=false

# LLM Summarizer
LLM_API_BASE=http://localhost:11434
LLM_API_KEY=
LLM_MODEL=llama3.2
```

## Quick Start

### Docker (Recommended)
```bash
# From project root
./start.sh --build-ui

# Or manually
cd deployment
docker compose up -d --build

# Access
# Dashboard: http://localhost:3000
# API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

### Local Development
```bash
# Backend
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000

# Frontend
cd dashboard
npm install
npm start

# Workers (separate terminals)
python -m processing.rtsp_worker
python -m processing.risk_predictor_worker
```

## Search Modes

| Mode | Description | Best For |
|------|-------------|----------|
| `clip` | Pure CLIP semantic embedding search | Scene descriptions, concepts |
| `yolo` | YOLO object detection + CLIP hybrid | Specific objects (person, car) |
| `hybrid` | Adaptive blend based on query | General use (default) |

## Project Structure

```
video_search_system/
├── api/
│   ├── main.py              # FastAPI application
│   └── summarizer_service.py # LLM SITREP generation
├── processing/
│   ├── ai_provider.py       # Multi-backend AI service
│   ├── embedding.py         # CLIP embedding generation
│   ├── frame_sampler.py     # Video frame extraction
│   ├── hybrid_search.py     # CLIP + YOLO fusion
│   ├── mission_intelligence.py # Urgency & correlation
│   ├── object_detector.py   # YOLOv8 detection
│   ├── policy_router.py     # Alert routing rules
│   ├── risk_predictor_worker.py # Forecast worker
│   ├── rtsp_worker.py       # Live camera ingest
│   ├── summarizer_client.py # SITREP client
│   ├── thumbnail_generator.py # Thumbnail creation
│   ├── url_upload_worker.py # VOD ingest
│   └── vector_store.py      # Milvus integration
├── dashboard/
│   └── src/
│       ├── App.js           # Main React component
│       ├── App.css          # Styling with glow effects
│       ├── VideoPlayer.js   # HLS/RTSP player
│       ├── VideoGrid.js     # Search results grid
│       └── services/
│           └── webgpuService.js # In-browser AI
├── deployment/
│   ├── docker-compose.yml   # Service orchestration
│   ├── api.Dockerfile       # API container
│   └── dashboard.Dockerfile # Frontend container
├── start.sh                 # Quick start script
├── README.md                # This file
└── AGENTS.md               # AI agent guidance
```

## Scoring Formulas

### Risk Score (Proactive Forecast)
```
risk_score = 0.55 × min(1, signal_60m / 5) + 0.45 × min(1, trend)

signal_60m = Σ(0.5 × urgency_weight + 0.5 × mission_score) for events in 60min
trend = signal_15m / signal_60m
```

### Urgency Score (Mission Intelligence)
```
urgency = Σ(term_weights) capped at 1.0

term_weights:
  - critical terms: +0.45 each
  - high terms: +0.25 each  
  - medium terms: +0.12 each
```

### Correlation Score (Cross-Source)
```
correlation = |objects_A ∩ objects_B| / |objects_A ∪ objects_B|  (Jaccard)
```

## Future Improvements

- [ ] Multi-GPU CLIP inference for higher throughput
- [ ] WebRTC support for ultra-low latency live streams
- [ ] Persistent alert acknowledgment workflow
- [ ] Role-based access control (RBAC)
- [ ] Time-range search filters
- [ ] Batch video re-indexing
- [ ] Custom YOLO model fine-tuning interface
- [ ] Prometheus/Grafana metrics integration
- [ ] S3/MinIO storage backend option

## License

Proprietary - Internal Use Only
