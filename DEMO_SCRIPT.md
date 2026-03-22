# Video Search System - Demo Recording Script

## Pre-Recording Setup

```bash
# Start all services
cd /Users/joshua.giles/video_search_system
./start.sh --build-ui

# Verify services are running
curl http://localhost:8000/healthz
curl http://localhost:3000
```

**Recording Settings**: 1920x1080, 30fps, browser at 100% zoom

---

## Demo Script (5-7 minutes)

### Scene 1: Dashboard Overview (45 sec)

**Show**: Open `http://localhost:3000`

**Narration**:
> "This is the Video Search System - a real-time semantic video surveillance platform. 
> The dashboard shows live camera feeds, search results, and AI-powered threat analysis.
> Notice the dark theme with subtle glow effects for critical alerts."

**Actions**:
- Pan across the main dashboard
- Highlight the search bar at the top
- Point out the camera list on the left
- Show the AI Analysis panel

---

### Scene 2: Semantic Search with CLIP (90 sec)

**Show**: Search functionality

**Narration**:
> "The core feature is semantic video search powered by CLIP embeddings.
> Unlike keyword search, this understands the meaning of your query."

**Actions**:
1. Type in search bar: `person running near vehicle`
2. Show results loading with shimmer animation
3. Click a result to play the video clip
4. Point out the confidence scores

**Alternative Searches to Demo**:
- `suspicious activity at entrance`
- `crowd gathering`
- `abandoned package`

---

### Scene 3: Hybrid Search Mode (60 sec)

**Show**: YOLO + CLIP hybrid search

**Narration**:
> "For precise object detection, we combine CLIP's semantic understanding
> with YOLO's object recognition. This hybrid approach gives you the best of both worlds."

**Actions**:
1. Toggle search mode dropdown to "Hybrid"
2. Search for: `car` or `person`
3. Show detected objects overlay on results
4. Point out the object labels and confidence

---

### Scene 4: Risk Predictions (60 sec)

**Show**: Predictions panel

**Narration**:
> "The system proactively forecasts risk using time-series analysis.
> It looks at event patterns over 15 and 60 minute windows to predict 
> which cameras are likely to see incidents."

**Actions**:
1. Click "Predictions" tab
2. Show the risk scores per camera
3. Highlight any "high" or "critical" risk sources
4. Explain the trend indicator (acceleration)

---

### Scene 5: AI Analysis (90 sec)

**Show**: AI-powered threat analysis

**Narration**:
> "For deeper analysis, we integrate multiple AI backends.
> Ollama runs locally for privacy, OpenAI provides cloud fallback,
> and WebGPU enables in-browser inference with zero server load."

**Actions**:
1. Click "Threats" analysis button
2. Show the loading state with progress
3. Display the AI-generated threat assessment
4. Click "Correlations" to show cross-source patterns
5. Toggle WebGPU status indicator (if available)

---

### Scene 6: Mission Intelligence (45 sec)

**Show**: Alerts and urgency scoring

**Narration**:
> "Mission Intelligence automatically prioritizes events by urgency.
> Critical terms like 'active shooter' or 'explosion' trigger immediate alerts.
> The system correlates events across multiple cameras."

**Actions**:
1. Show the Alerts panel
2. Point out urgency levels (critical/high/medium)
3. Show correlation badges linking sources
4. Click an alert to jump to the video

---

### Scene 7: Architecture Recap (30 sec)

**Show**: Keep dashboard visible

**Narration**:
> "Under the hood: FastAPI backend, Milvus vector database for embeddings,
> Redis for caching, and a React frontend. The system scales horizontally
> and supports live RTSP cameras, URL imports, and direct uploads."

---

## Post-Recording

**Optional B-Roll**:
- Terminal showing `docker compose logs -f api`
- API docs at `http://localhost:8000/docs`
- Milvus admin UI (if available)

**Thumbnail Suggestions**:
- Dashboard with glowing critical alert
- Search results with bounding boxes
- Risk prediction graph

---

## Quick Reference - Key URLs

| URL | Description |
|-----|-------------|
| http://localhost:3000 | Dashboard |
| http://localhost:8000 | API |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/healthz | Health check |

## Troubleshooting During Recording

```bash
# If services stop responding
docker compose -f deployment/docker-compose.yml restart

# Check logs
docker compose -f deployment/docker-compose.yml logs -f api

# Quick Redis check  
redis-cli ping

# Milvus health
curl localhost:19530/healthz
```
