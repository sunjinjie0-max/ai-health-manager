#!/bin/bash

# AI Health Manager - Quick Start Script
# This script provides a simple way to start and test the application

echo "🚀 AI Health Manager - Quick Start"
echo "===================================="
echo ""

# Function to check if a port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Menu
echo "Choose an option:"
echo ""
echo "1) 🖥️  Start Backend Only (http://localhost:8000)"
echo "2) 🎨 Start Frontend Only (http://localhost:5173)"
echo "3) 🚀 Start Both (Full Application)"
echo "4) 🧪 Test Agent"
echo "5) 📚 View Test Guide"
echo "6) ❌ Exit"
echo ""

read -p "Enter your choice (1-6): " choice

case $choice in
    1)
        echo ""
        echo "🔧 Starting Backend..."
        echo "   API Docs: http://localhost:8000/docs"
        echo ""
        cd ai-health-manager-backend
        python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
        ;;

    2)
        echo ""
        echo "🎨 Starting Frontend..."
        echo "   URL: http://localhost:5173"
        echo ""
        cd ai-health-manager-frontend
        npm run dev
        ;;

    3)
        echo ""
        echo "🚀 Starting Full Application..."
        echo ""

        # Check if ports are already in use
        if check_port 8000; then
            echo "⚠️  Port 8000 is already in use. Please stop the existing backend first."
            exit 1
        fi

        if check_port 5173; then
            echo "⚠️  Port 5173 is already in use. Please stop the existing frontend first."
            exit 1
        fi

        # Start backend
        echo "🔧 Starting Backend (http://localhost:8000)..."
        cd ai-health-manager-backend
        python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > ../backend.log 2>&1 &
        BACKEND_PID=$!
        cd ..

        echo "   Backend PID: $BACKEND_PID"
        echo ""

        # Wait for backend to be ready
        echo "⏳ Waiting for backend to be ready..."
        sleep 3

        # Start frontend
        echo "🎨 Starting Frontend (http://localhost:5173)..."
        cd ai-health-manager-frontend
        npm run dev > ../frontend.log 2>&1 &
        FRONTEND_PID=$!
        cd ..

        echo "   Frontend PID: $FRONTEND_PID"
        echo ""

        # Summary
        echo "============================================"
        echo "🚀 Application Started!"
        echo "============================================"
        echo ""
        echo "📱 Frontend: http://localhost:5173"
        echo "📚 API Docs: http://localhost:8000/docs"
        echo "💚 Health: http://localhost:8000/health"
        echo ""
        echo "📁 Logs:"
        echo "   Backend: backend.log"
        echo "   Frontend: frontend.log"
        echo ""
        echo "Press Ctrl+C to stop all services"
        echo ""

        # Keep script running
        wait
        ;;

    4)
        echo ""
        echo "🧪 Testing Agent..."
        echo ""
        python3 test_agent.py
        ;;

    5)
        echo ""
        echo "📚 Opening Test Guide..."
        echo ""
        if command -v open &> /dev/null; then
            open 测试指南.md
        elif command -v xdg-open &> /dev/null; then
            xdg-open 测试指南.md
        else
            cat 测试指南.md | head -100
        fi
        ;;

    6)
        echo ""
        echo "👋 Goodbye!"
        exit 0
        ;;

    *)
        echo ""
        echo "❌ Invalid choice. Please enter a number between 1-6."
        exit 1
        ;;
esac