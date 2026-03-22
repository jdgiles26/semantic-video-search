# OPORD Parsing & Real-Time Live Stream Detection

This document describes the advanced OPORD (Operation Order) parsing and real-time live stream detection capabilities added to the Video Search System.

## Table of Contents

1. [OPORD Document Parsing](#opord-document-parsing)
2. [Real-Time Live Stream Detection](#real-time-live-stream-detection)
3. [Setup & Configuration](#setup--configuration)
4. [API Endpoints](#api-endpoints)
5. [Frontend Components](#frontend-components)

---

## OPORD Document Parsing

### Overview

The system now includes advanced NLP-based OPORD parsing that extracts structured intelligence from operation order documents using:

- **Hugging Face Transformers** (local models - FREE, no API key required)
- **Hugging Face Inference API** (optional, requires HF_API_KEY)
- **Ollama LLM** (local fallback)
- **OpenAI API** (cloud fallback)

### Features

#### 1. Named Entity Recognition (NER)
Extracts entities from OPORD documents:
- **Persons** - Names of individuals of interest
- **Locations** - Facilities, addresses, geographic areas
- **Organizations** - Agencies, groups, companies

#### 2. Watch Phrase Detection
Automatically identifies watch targets:
- `suspicious person` → Critical priority, watch_labels: ["person"]
- `suspicious vehicle` → High priority, watch_labels: ["car", "truck", "bus"]
- `armed person` → Critical priority, watch_labels: ["person"]
- `boat` / `vessel` → High priority, watch_labels: ["boat"]

#### 3. Topic Classification
Classifies OPORD into security topics:
- Security / Surveillance / Perimeter
- Maritime / Aviation / Transportation
- Emergency Response / Medical / Fire
- VIP Protection / Event Security

#### 4. Keyword Extraction
Extracts mission-critical keywords for search correlation.

### File: `processing/opord_parser.py`

```python
from processing.opord_parser import parse_opord_document

# Parse an OPORD document
parsed = parse_opord_document(
    text="...document content...",
    source_filename="operation_order.pdf",
    mime_type="application/pdf"
)

# Access extracted intelligence
print(parsed.watch_phrase)      # "suspicious person"
print(parsed.priority)          # "critical"
print(parsed.persons)           # ["John Doe", "Jane Smith"]
print(parsed.locations)         # ["Building A", "North Gate"]
print(parsed.topics)            # ["security", "surveillance"]
print(parsed.keywords)          # ["patrol", "monitor", "report"]
```

### Models Used

| Task | Default Model | Local | API |
|------|--------------|-------|-----|
| NER | dslim/bert-base-NER | ✅ | ✅ |
| Classification | facebook/bart-large-mnli | ✅ | ✅ |
| Summarization | facebook/bart-large-cnn | ✅ | ✅ |
| Keywords | yanekyuk/bert-keyword-extractor | ✅ | ❌ |

---

## Real-Time Live Stream Detection

### Overview

Real-time YOLO object detection overlay for live RTSP streams with:

- **Live bounding box overlay** on video playback
- **Person/vehicle detection** in real-time
- **OPORD watch alert correlation** - highlights watch targets
- **AI-powered frame analysis** - threat assessment per frame

### Components

#### 1. LiveStreamAnalyzer (React Component)

File: `dashboard/src/components/LiveStreamAnalyzer.js`

```jsx
import { LiveStreamWithAI } from './components/LiveStreamAnalyzer';

function MyComponent() {
  return (
    <LiveStreamWithAI
      videoUrl="http://localhost:10588/live/index.m3u8"
      cameraId="cam-001"
      watchAlert={{
        watch_phrase: "suspicious person",
        watch_labels: ["person"],
        priority: "critical"
      }}
      onDetection={(detections, analysis) => {
        console.log('Detected:', detections);
      }}
      onAlert={(alert) => {
        console.log('Watch alert match!', alert);
      }}
    />
  );
}
```

#### 2. Backend Detection Endpoint

**POST** `/live/detect`

Accepts base64-encoded frame, returns YOLO detections:

```json
{
  "camera_id": "cam-001",
  "frame_data": "data:image/jpeg;base64,/9j/4AAQ...",
  "timestamp": 1709823456789
}
```

Response:

```json
{
  "camera_id": "cam-001",
  "timestamp": 1709823456789,
  "detections": [
    {
      "label": "person",
      "confidence": 0.87,
      "bbox": [100, 200, 300, 500]
    }
  ],
  "analysis": {
    "summary": "Single person detected in frame",
    "threat_level": "medium",
    "watch_assessment": {...}
  },
  "watch_match": true,
  "watch_phrase": "suspicious person"
}
```

### Detection Features

| Feature | Description |
|---------|-------------|
| Bounding Boxes | Real-time overlay with class colors |
| Confidence Scores | Displayed as percentage |
| Watch Alert Highlighting | Red boxes + "!" indicator for watch targets |
| Detection History | Last 100 detections stored per camera |
| AI Analysis | Optional LLM analysis of detected objects |

### COCO Class Colors

```javascript
{
  person: '#FF6B6B',    // Red
  car: '#4ECDC4',       // Teal
  truck: '#45B7D1',     // Blue
  bus: '#96CEB4',       // Green
  boat: '#98D8C8',      // Mint
  // ... etc
}
```

---

## Setup & Configuration

### 1. Install Dependencies

```bash
# Backend dependencies (already in requirements.txt)
pip install transformers torch ultralytics opencv-python

# For PDF parsing
pip install pypdf

# For DOCX parsing
pip install python-docx
```

### 2. Environment Variables

```bash
# Hugging Face (optional - for API fallback)
export HF_API_KEY="hf_..."

# Ollama (optional - for LLM fallback)
export OLLAMA_BASE_URL="http://localhost:11434"

# OpenAI (optional - for cloud fallback)
export OPENAI_API_KEY="sk-..."
```

### 3. Local Model Download (First Run)

On first use, the system will automatically download:
- `yolov8n.pt` - YOLOv8 nano (fastest, ~6MB)
- `dslim/bert-base-NER` - NER model (~400MB)
- `facebook/bart-large-mnli` - Classification model (~1.6GB)

Models are cached in `~/.cache/huggingface/`

### 4. Verify Setup

```bash
# Check OPORD parser status
curl http://localhost:8000/opord/parser/status

# Check YOLO is working
curl http://localhost:8000/ai/providers
```

---

## API Endpoints

### OPORD Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/opord/parse` | POST | Parse OPORD text with NLP |
| `/opord/upload-and-activate` | POST | Upload file, parse, activate watch |
| `/opord/parser/status` | GET | Get parser status & backends |

### Live Detection Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/live/detect` | POST | Run YOLO on frame |
| `/live/detections/{camera_id}` | GET | Get recent detections |

### Example: Parse OPORD

```bash
curl -X POST http://localhost:8000/opord/parse \
  -H "Content-Type: application/json" \
  -d '{
    "text": "OPORD 001: Monitor suspicious persons near the north gate...",
    "source_filename": "opord_001.txt"
  }'
```

### Example: Upload & Activate OPORD

```bash
curl -X POST http://localhost:8000/opord/upload-and-activate \
  -F "file=@operation_order.pdf"
```

### Example: Live Detection

```bash
curl -X POST http://localhost:8000/live/detect \
  -H "Content-Type: application/json" \
  -d '{
    "camera_id": "cam-001",
    "frame_data": "data:image/jpeg;base64,/9j/4AAQ...",
    "timestamp": 1709823456789
  }'
```

---

## Frontend Components

### LiveStreamWithAI Props

| Prop | Type | Description |
|------|------|-------------|
| `videoUrl` | string | HLS/RTSP stream URL |
| `cameraId` | string | Camera identifier |
| `watchAlert` | object | Active watch alert config |
| `onDetection` | function | Callback on detection |
| `onAlert` | function | Callback on watch match |
| `enabled` | boolean | Enable/disable analysis |
| `showControls` | boolean | Show stats panel |

### Watch Alert Object

```javascript
{
  watch_phrase: "suspicious person",
  watch_labels: ["person"],
  priority: "critical",
  topics: ["security", "surveillance"],
  keywords: ["monitor", "patrol"]
}
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React)                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  LiveStreamWithAI Component                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │   │
│  │  │ Video Player│  │ YOLO Overlay│  │ Detection Stats │  │   │
│  │  │  (HLS.js)   │  │  (Canvas)   │  │    (Panel)      │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ POST /live/detect
┌─────────────────────────────────────────────────────────────────┐
│                         API (FastAPI)                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ /live/detect│  │/opord/parse │  │  /opord/upload-and-act  │ │
│  │   (YOLO)    │  │   (NLP)     │  │       (NLP+Watch)       │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  YOLOv8 (Local) │  │ HF Transformers │  │  Ollama/OpenAI  │
│  - Person       │  │  - BERT NER     │  │   (Fallback)    │
│  - Vehicle      │  │  - BART Classify│  │                 │
│  - Objects      │  │  - Keywords     │  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

---

## Performance

| Component | Latency | Hardware |
|-----------|---------|----------|
| YOLOv8-nano | ~50ms | CPU |
| YOLOv8-nano | ~10ms | GPU |
| BERT NER | ~100ms | CPU |
| BERT NER | ~20ms | GPU |
| Live Analysis | ~500ms | With AI review |

---

## Troubleshooting

### Issue: "ultralytics not installed"
```bash
pip install ultralytics
```

### Issue: "transformers not installed"
```bash
pip install transformers torch
```

### Issue: "OpenCV not available"
```bash
pip install opencv-python
```

### Issue: Models downloading slowly
Models are downloaded from HuggingFace on first use. For offline use:
```bash
# Pre-download models
python -c "from transformers import pipeline; pipeline('ner', model='dslim/bert-base-NER')"
```

### Issue: YOLO not detecting persons
1. Check confidence threshold (default: 0.3)
2. Verify video quality/lighting
3. Try YOLOv8-s (small) for better accuracy:
   ```python
   detector = ObjectDetector(model_size='s')
   ```

---

## Future Enhancements

- [ ] Multi-object tracking across frames
- [ ] Behavior analysis (loitering, running, etc.)
- [ ] Facial recognition integration
- [ ] License plate recognition
- [ ] Custom YOLO model training for specific threats
- [ ] Edge deployment (NVIDIA Jetson, etc.)
