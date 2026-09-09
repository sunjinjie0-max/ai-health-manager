"""Test script for Agent API endpoints.

This script tests the specialized Agent APIs:
- /agents/nutrition/analyze
- /agents/environment/query
- /agents/exercise/plan
"""

import asyncio
import json
import sys
from typing import Any

import httpx

BASE_URL = "http://localhost:8000/api/v1"


class APITester:
    """API test runner."""

    def __init__(self):
        self.client = httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)
        self.results = []

    async def test_nutrition_analyze(self) -> dict[str, Any]:
        """Test nutrition analysis endpoint."""
        print("\n🧪 Testing /agents/nutrition/analyze...")

        test_cases = [
            {
                "description": "早餐吃了一碗燕麦粥、一个鸡蛋和一杯牛奶",
                "expected_keywords": ["燕麦", "鸡蛋", "牛奶"],
            },
            {
                "description": "午餐吃了米饭、番茄炒蛋、清蒸鱼和西兰花",
                "expected_keywords": ["米饭", "番茄", "鱼"],
            },
        ]

        results = []
        for i, test_case in enumerate(test_cases, 1):
            try:
                response = await self.client.post(
                    "/agents/nutrition/analyze",
                    data={"description": test_case["description"], "user_id": f"test_user_{i}"},
                )

                if response.status_code == 200:
                    data = response.json()
                    success = data.get("success", False)

                    if success:
                        # Check for expected keywords in response
                        response_text = data.get("response", "").lower()
                        keywords_found = [
                            kw for kw in test_case["expected_keywords"]
                            if kw in response_text
                        ]

                        results.append({
                            "test": f"Test case {i}",
                            "status": "✅ PASSED" if keywords_found else "⚠️ PARTIAL",
                            "keywords_found": keywords_found,
                            "health_score": data.get("health_score", 0),
                        })
                    else:
                        results.append({
                            "test": f"Test case {i}",
                            "status": "❌ FAILED",
                            "error": data.get("response", "Unknown error"),
                        })
                else:
                    results.append({
                        "test": f"Test case {i}",
                        "status": "❌ ERROR",
                        "status_code": response.status_code,
                    })

            except Exception as e:
                results.append({
                    "test": f"Test case {i}",
                    "status": "❌ EXCEPTION",
                    "error": str(e),
                })

        return {"endpoint": "/agents/nutrition/analyze", "results": results}

    async def test_environment_query(self) -> dict[str, Any]:
        """Test environment query endpoint."""
        print("\n🧪 Testing /agents/environment/query...")

        test_cases = [
            {
                "location": "北京市",
                "query_type": "all",
            },
            {
                "location": "上海市",
                "query_type": "air",
            },
        ]

        results = []
        for i, test_case in enumerate(test_cases, 1):
            try:
                response = await self.client.post(
                    "/agents/environment/query",
                    data={
                        "location": test_case["location"],
                        "query_type": test_case["query_type"],
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    success = data.get("success", False)

                    if success:
                        location_data = data.get("location", {})
                        results.append({
                            "test": f"Query {test_case['location']}",
                            "status": "✅ PASSED",
                            "city": location_data.get("city", "unknown"),
                            "air_quality": data.get("air_quality") is not None,
                            "weather": data.get("weather") is not None,
                        })
                    else:
                        results.append({
                            "test": f"Query {test_case['location']}",
                            "status": "⚠️ NO DATA",
                            "response": data.get("response", "")[:100],
                        })
                else:
                    results.append({
                        "test": f"Query {test_case['location']}",
                        "status": "❌ ERROR",
                        "status_code": response.status_code,
                    })

            except Exception as e:
                results.append({
                    "test": f"Query {test_case['location']}",
                    "status": "❌ EXCEPTION",
                    "error": str(e),
                })

        return {"endpoint": "/agents/environment/query", "results": results}

    async def test_exercise_plan(self) -> dict[str, Any]:
        """Test exercise plan endpoint."""
        print("\n🧪 Testing /agents/exercise/plan...")

        test_cases = [
            {
                "goal": "减脂",
                "fitness_level": "beginner",
                "time_minutes": 30,
            },
            {
                "goal": "增肌",
                "fitness_level": "intermediate",
                "time_minutes": 45,
            },
        ]

        results = []
        for i, test_case in enumerate(test_cases, 1):
            try:
                response = await self.client.post(
                    "/agents/exercise/plan",
                    data={
                        "goal": test_case["goal"],
                        "fitness_level": test_case["fitness_level"],
                        "time_minutes": test_case["time_minutes"],
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    success = data.get("success", False)

                    if success:
                        workout_plan = data.get("workout_plan", {})
                        exercises = data.get("exercises", [])

                        results.append({
                            "test": f"Plan {test_case['goal']}/{test_case['fitness_level']}",
                            "status": "✅ PASSED",
                            "exercise_count": len(exercises),
                            "plan_type": workout_plan.get("plan_type", "unknown"),
                            "total_duration": workout_plan.get("total_duration", 0),
                        })
                    else:
                        results.append({
                            "test": f"Plan {test_case['goal']}/{test_case['fitness_level']}",
                            "status": "❌ FAILED",
                            "error": data.get("response", "Unknown error"),
                        })
                else:
                    results.append({
                        "test": f"Plan {test_case['goal']}/{test_case['fitness_level']}",
                        "status": "❌ ERROR",
                        "status_code": response.status_code,
                    })

            except Exception as e:
                results.append({
                    "test": f"Plan {test_case['goal']}/{test_case['fitness_level']}",
                    "status": "❌ EXCEPTION",
                    "error": str(e),
                })

        return {"endpoint": "/agents/exercise/plan", "results": results}

    async def run_all_tests(self):
        """Run all API tests."""
        print("\n" + "=" * 60)
        print("🚀 Starting Agent API Tests")
        print("=" * 60)

        results = []

        # Test 1: Nutrition
        result = await self.test_nutrition_analyze()
        results.append(result)

        # Test 2: Environment
        result = await self.test_environment_query()
        results.append(result)

        # Test 3: Exercise
        result = await self.test_exercise_plan()
        results.append(result)

        # Print summary
        print("\n" + "=" * 60)
        print("📊 Test Summary")
        print("=" * 60)

        total_tests = 0
        passed_tests = 0

        for endpoint_result in results:
            endpoint = endpoint_result["endpoint"]
            test_results = endpoint_result["results"]

            print(f"\n{endpoint}:")
            for test in test_results:
                total_tests += 1
                status = test.get("status", "UNKNOWN")
                if "✅" in status:
                    passed_tests += 1
                print(f"  {test.get('test', 'Unknown')}: {status}")

        print("\n" + "=" * 60)
        print(f"📈 Results: {passed_tests}/{total_tests} passed")
        print("=" * 60)

        await self.client.aclose()

        return results


async def main():
    """Main entry point."""
    print("""
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║           🧪 Agent API Test Suite                          ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
    """)

    tester = APITester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
