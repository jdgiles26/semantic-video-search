# Video Search System

A unified video monitoring platform that ingests Live RTSP feeds, Video URLs (HTTP/S), and Uploaded files. The system samples frames, generates semantic embeddings using OpenCLIP, and allows natural language searching (e.g., "person wearing a red jacket") to return specific video segments or live camera matches.

## Features

- **Multi-Source Ingestion**: Support for RTSP streams, video URLs (YouTube, Vimeo, etc.), and file uploads
- **Semantic Search**: Natural language queries using OpenCLIP embeddings
- **Real-time Processing**: Live camera feed monitoring with motion detection
- **Vector Database**: High-speed similarity search using Milvus
- **Web Dashboard**: React-based UI for search, live viewing, and management

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   RTSP Streams  │     │   Video URLs    │     │  File Uploads   │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Ingestion Workers                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ RTSP Worker  │  │  URL Worker  │  │ Upload Worker│          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
         │                       │                       │
         │                       ▼                       │
         │              ┌─────────────────┐              │
         │              │  Frame Sampling │              │
         │              │   (1 fps)       │              │
         │              └────────┬────────┘              │
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    OpenCLIP Embedding Pipeline                   │
│              (ViT-B-32, 512-D embeddings)                        │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Milvus Vector DB                            │
│              (IVF_FLAT index, cosine similarity)                 │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Search API                            │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   React Dashboard                                │
│         (Search Mode / Live Mode / Upload & URL)                 │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- At least 8GB RAM (for Milvus and AI models)
- GPU optional (CUDA support for faster processing)

### Running with Docker Compose

1. Clone the repository and navigate to the project:
```bash
cd video_search_system
```

2. Start all services:
```bash
cd deployment
docker-compose up -d
```

3. Wait for services to initialize (Milvus may take 1-2 minutes on first run)

4. Access the dashboard:
   - Frontend: http://localhost:3000
   - API Docs: http://localhost:8000/docs

### Manual Setup (Development)

1. Install dependencies:
```bash
# Processing & API
pip install -r processing/requirements.txt
pip install -r api/requirements.txt

# Frontend
cd dashboard
npm install
```

2. Start infrastructure services:
```bash
# Start only Milvus, Redis, and MinIO
cd deployment
docker-compose up -d etcd minio milvus-standalone redis
```

3. Run the API:
```bash
cd api
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

4. Run workers (in separate terminals):
```bash
# RTSP Worker
python processing/rtsp_worker.py

# URL/Upload Worker
python processing/url_upload_worker.py
```

5. Run the frontend:
```bash
cd dashboard
npm start
```

## Usage

### 1. Register an RTSP Camera

Use the Live mode in the dashboard or API:

```bash
curl -X POST http://localhost:8000/cameras/register \
  -H "Content-Type: application/json" \
  -d '{
    "camera_id": "cam-001",
    "rtsp_url": "rtsp://your-camera-ip/stream"
  }'
```

### 2. Process a Video URL

```bash
curl -X POST http://localhost:8000/videos/url \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=...",
    "max_duration": 300
  }'
```

### 3. Upload a Video File

```bash
curl -X POST http://localhost:8000/videos/upload \
  -F "file=@/path/to/video.mp4"
```

### 4. Search Videos

```bash
curl "http://localhost:8000/query?query=person%20wearing%20red%20jacket&top_k=10"
```

Or use the web dashboard at http://localhost:3000

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/query` | GET | Search videos with natural language |
| `/cameras` | GET | List all cameras |
| `/cameras/register` | POST | Register new RTSP camera |
| `/cameras/{id}/stop` | POST | Stop camera stream |
| `/videos/url` | POST | Process video URL |
| `/videos/upload` | POST | Upload video file |
| `/tasks` | GET | List processing tasks |
| `/tasks/{id}` | GET | Get task status |
| `/stats` | GET | System statistics |

See full API documentation at http://localhost:8000/docs

## Configuration

Environment variables for all services:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | localhost | Redis server host |
| `REDIS_PORT` | 6379 | Redis server port |
| `MILVUS_HOST` | localhost | Milvus server host |
| `MILVUS_PORT` | 19530 | Milvus server port |
| `STORAGE_PATH` | /tmp/video_uploads | Storage directory |

## Data Flow

1. **Ingestion**: 
   - RTSP streams are continuously sampled (1 fps)
   - URLs are downloaded via yt-dlp and processed
   - Uploads are saved and processed

2. **Frame Processing**:
   - Frames sampled at 1 fps
   - Motion detection skips stagnant frames
   - 10-second clips are created

3. **Embedding Generation**:
   - OpenCLIP ViT-B-32 generates 512-D embeddings
   - Frame embeddings are averaged per clip
   - Embeddings are normalized

4. **Storage**:
   - Vector embeddings stored in Milvus
   - Video chunks stored locally (or S3/MinIO)
   - Metadata in Redis

5. **Search**:
   - Text query encoded via OpenCLIP
   - Cosine similarity search in Milvus
   - Results ranked by similarity score

## Scaling

To scale workers horizontally:

```bash
# Scale RTSP workers
docker-compose up -d --scale rtsp-worker=3

# Scale URL/Upload workers
docker-compose up -d --scale url-upload-worker=5
```

## Development

### Project Structure

```
video_search_system/
├── api/                    # FastAPI backend
│   ├── main.py            # API endpoints
│   └── requirements.txt
├── processing/            # Ingestion workers
│   ├── embedding.py       # OpenCLIP pipeline
│   ├── vector_store.py    # Milvus integration
│   ├── frame_sampler.py   # Frame extraction
│   ├── rtsp_worker.py     # RTSP processor
│   └── url_upload_worker.py
├── dashboard/             # React frontend
│   ├── src/
│   │   ├── App.js
│   │   ├── SearchBar.js
│   │   ├── VideoGrid.js
│   │   ├── VideoPlayer.js
│   │   └── VideoThumbnail.js
│   └── package.json
├── deployment/            # Docker & configs
│   ├── docker-compose.yml
│   ├── api.Dockerfile
│   ├── worker.Dockerfile
│   ├── frontend.Dockerfile
│   └── nginx.conf
└── README.md
```

## License

MIT License
