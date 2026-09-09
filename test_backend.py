#!/usr/bin/env python3
"""Quick test script for backend API."""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ai-health-manager-backend'))

def test_imports():
    """Test that key modules can be imported."""
    print("🧪 Testing imports...")

    try:
        from app.agents.health_advisor import HealthAdvisorAgent, HealthAdvisorState
        print("  ✅ HealthAdvisorAgent imported")
    except Exception as e:
        print(f"  ❌ HealthAdvisorAgent import failed: {e}")
        return False

    try:
        from app.agents.orchestrator import orchestrator
        print("  ✅ orchestrator imported")
    except Exception as e:
        print(f"  ❌ orchestrator import failed: {e}")
        return False

    return True


def test_agent():
    """Test the Health Advisor Agent."""
    import asyncio

    print("\n🧪 Testing Health Advisor Agent...")

    from app.agents.health_advisor import HealthAdvisorAgent, HealthAdvisorState

    async def run_test():
        agent = HealthAdvisorAgent()
        print(f"  ✅ Agent created: {agent.name}")

        # Test 1: General health question
        state = HealthAdvisorState(
            user_message="我今天感觉有点累，有什么建议吗？",
            user_id="test_user_1",
            session_id="test_session_1",
        )

        result = await agent.process(state)
        print(f"  ✅ Response generated")
        print(f"     Intent: {result.get('intent')}")
        print(f"     Response: {result.get('response', '')[:100]}...")

        # Test 2: Urgent symptom
        state2 = HealthAdvisorState(
            user_message="我胸痛得厉害，呼吸困难",
            user_id="test_user_1",
            session_id="test_session_1",
        )

        result2 = await agent.process(state2)
        print(f"  ✅ Urgent response generated")
        print(f"     Safety Flag: {result2.get('safety_flag')}")
        print(f"     Response: {result2.get('response', '')[:100]}...")

    try:
        asyncio.run(run_test())
        return True
    except Exception as e:
        print(f"  ❌ Agent test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test function."""
    print("=" * 60)
    print("🚀 AI Health Manager - Backend Test")
    print("=" * 60)
    print()

    # Test imports
    if not test_imports():
        print("\n❌ Import tests failed!")
        sys.exit(1)

    # Test agent
    if not test_agent():
        print("\n❌ Agent tests failed!")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
