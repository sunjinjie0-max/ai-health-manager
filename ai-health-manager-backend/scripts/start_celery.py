#!/usr/bin/env python3
"""
Celery worker startup script for AI Health Manager.

Usage:
    python scripts/start_celery.py [worker|beat|flower]
"""

import sys
import subprocess
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def start_worker():
    """Start Celery worker."""
    cmd = [
        'celery',
        '-A', 'app.core.celery:celery_app',
        'worker',
        '--loglevel=info',
        '--queues=default,health,agent,notification',
        '--concurrency=4',
    ]
    print(f"Starting Celery worker...")
    print(f"Command: {' '.join(cmd)}")
    subprocess.run(cmd)


def start_beat():
    """Start Celery beat scheduler."""
    cmd = [
        'celery',
        '-A', 'app.core.celery:celery_app',
        'beat',
        '--loglevel=info',
    ]
    print(f"Starting Celery beat...")
    print(f"Command: {' '.join(cmd)}")
    subprocess.run(cmd)


def start_flower():
    """Start Flower monitoring."""
    cmd = [
        'celery',
        '-A', 'app.core.celery:celery_app',
        'flower',
        '--port=5555',
    ]
    print(f"Starting Flower...")
    print(f"Command: {' '.join(cmd)}")
    subprocess.run(cmd)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/start_celery.py [worker|beat|flower]")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == 'worker':
        start_worker()
    elif command == 'beat':
        start_beat()
    elif command == 'flower':
        start_flower()
    else:
        print(f"Unknown command: {command}")
        print("Usage: python scripts/start_celery.py [worker|beat|flower]")
        sys.exit(1)


if __name__ == '__main__':
    main()
