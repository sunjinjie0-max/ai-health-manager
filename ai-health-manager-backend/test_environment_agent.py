"""Test script for EnvironmentAgent.

This script tests the EnvironmentAgent with sample inputs
to verify all nodes are working correctly.
"""

import asyncio
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


async def test_environment_agent():
    """Test EnvironmentAgent with sample inputs."""

    print("\n" + "=" * 80)
    print("Testing EnvironmentAgent")
    print("=" * 80 + "\n")

    try:
        # Import the agent
        from app.agents.environment import EnvironmentAgent, EnvironmentState

        # Create agent instance
        agent = EnvironmentAgent()

        # Test cases
        test_cases = [
            {
                "name": "Beijing air quality",
                "input": "北京市",
                "location_query": "北京市",
            },
            {
                "name": "Shanghai weather",
                "input": "上海市",
                "location_query": "上海市",
            },
            {
                "name": "Guangzhou environment",
                "input": "广州市",
                "location_query": "广州市",
            },
        ]

        # Run each test case
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n{'=' * 80}")
            print(f"Test {i}: {test_case['name']}")
            print(f"Location: {test_case['location_query']}")
            print(f"{'=' * 80}\n")

            # Create state
            state = EnvironmentState(
                user_message=test_case['input'],
                user_id="test_user",
                session_id=f"test_session_{i}",
                location_query=test_case['location_query'],
            )

            # Process
            try:
                result = await agent.process(state)

                # Print results
                print("✅ Test completed successfully!\n")
                print(f"Location: {result.get('location', {}).get('city', 'unknown')}")

                air_quality = result.get('air_quality', {})
                if air_quality:
                    print(f"AQI: {air_quality.get('aqi', 'N/A')} ({air_quality.get('level', 'unknown')})")

                weather = result.get('weather', {})
                if weather:
                    print(f"Weather: {weather.get('weather_description', 'unknown')}, {weather.get('temperature', 'N/A')}°C")

                health_risk = result.get('health_risk', {})
                if health_risk:
                    print(f"Overall Risk: {health_risk.get('overall_risk', 'unknown')}")

                recommendations = result.get('recommendations', [])
                print(f"Recommendations: {len(recommendations)}")

                # Print response preview
                response = result.get('response', '')
                if response:
                    print(f"\n📄 Response preview (first 500 chars):")
                    print(response[:500] + "...")

            except Exception as e:
                print(f"❌ Test failed with error: {e}")
                import traceback
                traceback.print_exc()

        print(f"\n{'=' * 80}")
        print("All tests completed!")
        print(f"{'=' * 80}\n")

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure you're running from the project root directory")
        print("and all dependencies are installed.")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run the test
    asyncio.run(test_environment_agent())
