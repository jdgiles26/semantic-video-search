#!/bin/bash
set -e

echo "=========================================="
echo "  Video Search System - Startup Script"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Parse arguments
BUILD_UI=false
USE_DOCKER=true
DEV_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --build-ui)
            BUILD_UI=true
            shift
            ;;
        --dev)
            DEV_MODE=true
            USE_DOCKER=false
            shift
            ;;
        --no-docker)
            USE_DOCKER=false
            shift
            ;;
        --help)
            echo "Usage: ./start.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --build-ui    Build the React UI before starting"
            echo "  --dev         Run in development mode (no Docker)"
            echo "  --no-docker   Run services locally without Docker"
            echo "  --help        Show this help message"
            echo ""
            echo "Environment Variables:"
            echo "  AI_PROVIDER       ollama|openai|webgpu (default: ollama)"
            echo "  OLLAMA_BASE_URL   Ollama API URL (default: http://localhost:11434)"
            echo "  OLLAMA_MODEL      Ollama model name (default: llava:7b)"
            echo "  OPENAI_API_KEY    OpenAI API key"
            echo "  OPENAI_MODEL      OpenAI model (default: gpt-4o-mini)"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Check for required tools
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${RED}Error: $1 is not installed${NC}"
        return 1
    fi
    return 0
}

echo -e "${BLUE}Checking prerequisites...${NC}"

if $USE_DOCKER; then
    check_command docker || exit 1
    check_command docker-compose || docker compose version &> /dev/null || exit 1
fi

# Build UI if requested
if $BUILD_UI; then
    echo -e "${YELLOW}Building React UI...${NC}"
    cd "$SCRIPT_DIR/dashboard"
    
    if [ ! -d "node_modules" ]; then
        echo "Installing npm dependencies..."
        npm install
    fi
    
    echo "Building production bundle..."
    npm run build
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}UI build completed successfully!${NC}"
    else
        echo -e "${RED}UI build failed!${NC}"
        exit 1
    fi
    
    cd "$SCRIPT_DIR"
fi

# Start services
if $USE_DOCKER; then
    echo -e "${BLUE}Starting services with Docker Compose...${NC}"
    
    # Create .env file if it doesn't exist
    if [ ! -f "$SCRIPT_DIR/deployment/.env" ]; then
        echo -e "${YELLOW}Creating default .env file...${NC}"
        cat > "$SCRIPT_DIR/deployment/.env" << 'EOF'
# AI Provider Settings
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llava:7b
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
WEBGPU_ENABLED=false

# LLM Summarizer Settings
LLM_API_BASE=
LLM_API_KEY=
LLM_MODEL=gpt-4o-mini

# Email Settings (optional)
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
ALERT_FROM_EMAIL=
EOF
    fi
    
    cd "$SCRIPT_DIR/deployment"
    
    echo -e "${YELLOW}Building and starting containers...${NC}"
    docker compose up -d --build
    
    if [ $? -eq 0 ]; then
        echo ""
        echo -e "${GREEN}=========================================="
        echo "  Services started successfully!"
        echo "==========================================${NC}"
        echo ""
        echo "Access the application:"
        echo -e "  ${BLUE}Dashboard:${NC}     http://localhost:3000"
        echo -e "  ${BLUE}API:${NC}           http://localhost:8000"
        echo -e "  ${BLUE}API Docs:${NC}      http://localhost:8000/docs"
        echo ""
        echo "AI Providers:"
        echo -e "  ${BLUE}Ollama:${NC}        Make sure Ollama is running locally"
        echo -e "  ${BLUE}OpenAI:${NC}        Set OPENAI_API_KEY in deployment/.env"
        echo -e "  ${BLUE}WebGPU:${NC}        Enable in dashboard AI settings"
        echo ""
        echo "Useful commands:"
        echo "  docker compose logs -f          # View logs"
        echo "  docker compose down             # Stop all services"
        echo "  docker compose ps               # Check status"
        echo ""
    else
        echo -e "${RED}Failed to start services!${NC}"
        exit 1
    fi
    
elif $DEV_MODE; then
    echo -e "${BLUE}Starting in development mode...${NC}"
    
    # Start API in background
    echo "Starting API server..."
    cd "$SCRIPT_DIR"
    python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload &
    API_PID=$!
    
    # Start frontend dev server
    echo "Starting React dev server..."
    cd "$SCRIPT_DIR/dashboard"
    npm start &
    UI_PID=$!
    
    echo -e "${GREEN}Development servers started!${NC}"
    echo "  API: http://localhost:8000"
    echo "  UI:  http://localhost:3000"
    echo ""
    echo "Press Ctrl+C to stop all services"
    
    # Wait and cleanup
    trap "kill $API_PID $UI_PID 2>/dev/null" EXIT
    wait
fi

echo -e "${GREEN}Done!${NC}"
