#!/usr/bin/env python3
"""
Database setup script for AI Health Manager.

This script:
1. Creates recommended database indexes
2. Sets up connection pool
3. Verifies database optimization settings

Usage:
    python scripts/setup_database.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.db.optimizations import IndexManager
from app.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def setup_indexes():
    """Set up recommended database indexes."""
    logger.info("Setting up database indexes...")

    results = await IndexManager.setup_recommended_indexes()

    success_count = sum(1 for success in results.values() if success)
    total_count = len(results)

    logger.info(f"Index setup complete: {success_count}/{total_count} indexes ready")

    # Log details
    for index_name, success in results.items():
        status = "✓" if success else "✗"
        logger.info(f"  {status} {index_name}")

    return success_count == total_count


async def list_current_indexes():
    """List all current database indexes."""
    logger.info("Current database indexes:")

    indexes = await IndexManager.list_indexes()

    if not indexes:
        logger.info("  (No indexes found)")
        return

    for idx in indexes:
        logger.info(f"  - {idx['name']} on {idx['table']}")


async def main():
    """Main setup function."""
    logger.info("=" * 60)
    logger.info("AI Health Manager - Database Setup")
    logger.info("=" * 60)

    try:
        # Initialize database
        logger.info("\n1. Initializing database...")
        await init_db()
        logger.info("   Database initialized ✓")

        # List current indexes
        logger.info("\n2. Checking current indexes...")
        await list_current_indexes()

        # Set up recommended indexes
        logger.info("\n3. Setting up recommended indexes...")
        success = await setup_indexes()

        if success:
            logger.info("\n✓ Database setup completed successfully!")
        else:
            logger.warning("\n⚠ Database setup completed with some warnings.")

        logger.info("\n" + "=" * 60)

    except Exception as e:
        logger.error(f"\n✗ Database setup failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
