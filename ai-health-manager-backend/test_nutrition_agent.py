"""Test script for NutritionAgent.

This script tests the NutritionAgent with sample inputs
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


async def test_nutrition_agent():
    """Test NutritionAgent with sample inputs."""

    print("\n" + "=" * 80)
    print("Testing NutritionAgent")
    print("=" * 80 + "\n")

    try:
        # Import the agent
        from app.agents.nutrition import NutritionAgent, NutritionState

        # Create agent instance
        agent = NutritionAgent()

        # Test cases
        test_cases = [
            {
                "name": "Simple breakfast",
                "input": "我早餐吃了一碗燕麦粥、一个鸡蛋和一杯牛奶",
            },
            {
                "name": "Lunch with multiple items",
                "input": "午餐吃了米饭、番茄炒蛋、清蒸鱼和一份西兰花",
            },
            {
                "name": "Simple snack",
                "input": "下午吃了一个苹果和一把坚果",
            },
        ]

        # Run each test case
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n{'=' * 80}")
            print(f"Test {i}: {test_case['name']}")
            print(f"Input: {test_case['input']}")
            print(f"{'=' * 80}\n")

            # Create state
            state = NutritionState(
                user_message=test_case['input'],
                user_id="test_user",
                session_id=f"test_session_{i}",
            )

            # Process
            try:
                result = await agent.process(state)

                # Print results
                print("✅ Test completed successfully!\n")
                print(f"Health Score: {result.get('health_score', 0):.0f}/100")
                print(f"Total Calories: {result.get('total_nutrition', {}).get('calories', 0):.0f} kcal")
                print(f"Number of foods: {len(result.get('extracted_foods', []))}")

                # Print recommendations
                recommendations = result.get('recommendations', [])
                if recommendations:
                    print(f"\nRecommendations ({len(recommendations)}):")
                    for j, rec in enumerate(recommendations[:3], 1):
                        print(f"  {j}. {rec}")

                # Print response preview
                response = result.get('response', '')
                if response:
                    print(f"\nResponse preview (first 200 chars):")
                    print(response[:200] + "...")

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
    asyncio.run(test_nutrition_agent())
