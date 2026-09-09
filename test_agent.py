"""Test script for Health Advisor Agent."""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ai-health-manager-backend'))

from app.agents.health_advisor import HealthAdvisorAgent, HealthAdvisorState


async def test_agent():
    """Test the Health Advisor Agent."""
    print("🧪 Testing Health Advisor Agent...\n")

    # Create agent instance
    agent = HealthAdvisorAgent()
    print(f"✅ Agent created: {agent.name}")
    print(f"   Description: {agent.description}")
    print(f"   Version: {agent.version}\n")

    # Test 1: General health question
    print("📝 Test 1: General health question")
    state1 = HealthAdvisorState(
        user_message="我今天感觉有点累，有什么建议吗？",
        user_id="test_user_1",
        session_id="test_session_1",
    )

    result1 = await agent.process(state1)
    print(f"   Intent: {result1.get('intent')}")
    print(f"   Response: {result1.get('response', 'No response')[:100]}...")
    print()

    # Test 2: Nutrition question
    print("📝 Test 2: Nutrition question")
    state2 = HealthAdvisorState(
        user_message="我今天吃了很多水果，这样健康吗？",
        user_id="test_user_1",
        session_id="test_session_1",
    )

    result2 = await agent.process(state2)
    print(f"   Intent: {result2.get('intent')}")
    print(f"   Response: {result2.get('response', 'No response')[:100]}...")
    print()

    # Test 3: Urgent symptom (should trigger safety warning)
    print("📝 Test 3: Urgent symptom (safety test)")
    state3 = HealthAdvisorState(
        user_message="我胸痛得厉害，呼吸困难",
        user_id="test_user_1",
        session_id="test_session_1",
    )

    result3 = await agent.process(state3)
    print(f"   Safety Flag: {result3.get('safety_flag')}")
    print(f"   Response: {result3.get('response', 'No response')[:100]}...")
    print()

    # Test 4: Exercise question
    print("📝 Test 4: Exercise question")
    state4 = HealthAdvisorState(
        user_message="我想开始跑步，有什么建议吗？",
        user_id="test_user_1",
        session_id="test_session_1",
    )

    result4 = await agent.process(state4)
    print(f"   Intent: {result4.get('intent')}")
    print(f"   Response: {result4.get('response', 'No response')[:100]}...")
    print()

    print("✅ All tests completed!")


if __name__ == "__main__":
    asyncio.run(test_agent())
