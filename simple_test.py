#!/usr/bin/env python3
"""Simplified test without complex dependencies."""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ai-health-manager-backend'))

def test_basic():
    """Basic test without heavy dependencies."""
    print("🧪 Running basic tests...")
    print("")

    # Test 1: Import basic modules
    try:
        from app.agents.health_advisor.state import HealthAdvisorState
        print("✅ HealthAdvisorState imported successfully")
    except Exception as e:
        print(f"❌ Failed to import HealthAdvisorState: {e}")
        return False

    # Test 2: Create state object
    try:
        state = HealthAdvisorState(
            user_message="你好，我今天感觉有点累",
            user_id="test_user",
            session_id="test_session",
        )
        print(f"✅ State created: user_message='{state['user_message']}'")
    except Exception as e:
        print(f"❌ Failed to create state: {e}")
        return False

    # Test 3: Import prompts
    try:
        from app.agents.health_advisor.prompts import URGENT_REPLY_TEMPLATE
        print(f"✅ Prompts imported, urgent template length: {len(URGENT_REPLY_TEMPLATE)}")
    except Exception as e:
        print(f"❌ Failed to import prompts: {e}")
        return False

    print("")
    print("=" * 50)
    print("✅ All basic tests passed!")
    print("=" * 50)
    return True


if __name__ == "__main__":
    success = test_basic()
    sys.exit(0 if success else 1)
