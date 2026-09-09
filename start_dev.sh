#!/bin/bash

# AI Health Manager - Development Startup Script
# This script starts both backend and frontend services

echo "🚀 Starting AI Health Manager Development Environment..."
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to cleanup processes on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down services..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    exit 0
}

trap cleanup INT TERM

# Check if we're in the right directory
if [ ! -d "ai-health-manager-backend" ] || [ ! -d "ai-health-manager-frontend" ]; then
    echo "❌ Error: Please run this script from the AI健康管家 root directory"
    exit 1
fi

echo "${BLUE}📁 Project root: $(pwd)${NC}"
echo ""

# Start Backend
echo "${YELLOW}🔧 Starting Backend...${NC}"
cd ai-health-manager-backend

# Check if virtual environment exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# Start backend server
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > backend.log 2>&1 &
BACKEND_PID=$!

cd ..
echo "${GREEN}✅ Backend started (PID: $BACKEND_PID)${NC}"
echo "   API Docs: http://localhost:8000/docs"
echo "   Health: http://localhost:8000/health"
echo ""

# Wait for backend to be ready
echo "${YELLOW}⏳ Waiting for backend to be ready...${NC}"
sleep 3

# Start Frontend
echo "${YELLOW}🎨 Starting Frontend...${NC}"
cd ai-health-manager-frontend

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "${YELLOW}📦 Installing frontend dependencies...${NC}"
    npm install
fi

# Start frontend dev server
npm run dev > frontend.log 2>&1 &
FRONTEND_PID=$!

cd ..
echo "${GREEN}✅ Frontend started (PID: $FRONTEND_PID)${NC}"
echo "   URL: http://localhost:5173"
echo ""

# Summary
echo "${GREEN}🚀 Development environment is ready!${NC}"
echo ""
echo "${BLUE}📊 Service Status:${NC}"
echo "   Backend: http://localhost:8000 (PID: $BACKEND_PID)"
echo "   Frontend: http://localhost:5173 (PID: $FRONTEND_PID)"
echo ""
echo "${BLUE}📁 Logs:${NC}"
echo "   Backend: ai-health-manager-backend/backend.log"
echo "   Frontend: ai-health-manager-frontend/frontend.log"
echo ""
echo "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Keep script running
wait
