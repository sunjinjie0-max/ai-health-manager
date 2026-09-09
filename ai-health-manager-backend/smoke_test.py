#!/usr/bin/env python3
"""
Smoke test for AI Health Manager Backend.

This script performs basic checks to ensure the application is working:
1. Database connection
2. LLM client initialization
3. RAG retriever initialization
4. Agent initialization
5. Basic API endpoints

Usage:
    python smoke_test.py
"""

import asyncio
import sys
import traceback
from typing import List, Tuple


class SmokeTestResult:
    """Result of a smoke test."""
    def __init__(self, name: str, passed: bool, message: str = ""):
        self.name = name
        self.passed = passed
        self.message = message


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def print_result(result: SmokeTestResult):
    """Print a test result."""
    status = "✅ PASS" if result.passed else "❌ FAIL"
    print(f"{status} - {result.name}")
    if result.message:
        print(f"       {result.message}")


async def test_database() -> SmokeTestResult:
    """Test database connection."""
    try:
        from app.models.database import engine
        from sqlalchemy import text

        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

        return SmokeTestResult("Database Connection", True, "SQLite async connection working")
    except Exception as e:
        return SmokeTestResult("Database Connection", False, str(e))


async def test_llm_client() -> SmokeTestResult:
    """Test LLM client initialization."""
    try:
        from app.llm.deepseek import deepseek_client, DeepSeekClient

        assert deepseek_client is not None
        assert isinstance(deepseek_client, DeepSeekClient)
        assert deepseek_client.llm is not None

        return SmokeTestResult("LLM Client", True, "DeepSeek client initialized")
    except Exception as e:
        return SmokeTestResult("LLM Client", False, str(e))


async def test_rag_retriever() -> SmokeTestResult:
    """Test RAG retriever initialization."""
    try:
        from app.rag.retriever import rag_retriever, RAGRetriever

        assert rag_retriever is not None
        assert isinstance(rag_retriever, RAGRetriever)

        # Initialize and search
        await rag_retriever.initialize()
        results = await rag_retriever.retrieve("每天喝多少水")

        assert len(results) > 0
        assert "content" in results[0]

        return SmokeTestResult("RAG Retriever", True, f"Found {len(results)} documents")
    except Exception as e:
        return SmokeTestResult("RAG Retriever", False, str(e))


async def test_health_advisor_agent() -> SmokeTestResult:
    """Test Health Advisor Agent initialization."""
    try:
        from app.agents.health_advisor.agent import HealthAdvisorAgent

        agent = HealthAdvisorAgent()

        assert agent.name == "health_advisor"
        assert agent.graph is not None

        return SmokeTestResult("Health Advisor Agent", True, "Agent compiled successfully")
    except Exception as e:
        return SmokeTestResult("Health Advisor Agent", False, str(e))


async def test_memory_system() -> SmokeTestResult:
    """Test memory system components."""
    try:
        from app.memory.short_term import short_term_memory
        from app.memory.profile import merge_profile

        # Test short-term memory
        short_term_memory.add_message("test_session", "user", "你好")
        short_term_memory.add_message("test_session", "assistant", "你好！有什么可以帮助您的吗？")

        history = short_term_memory.get_history("test_session")
        assert len(history) == 2

        # Test profile merge
        current = {"age": 28, "allergies": ["花生"]}
        extracted = {"age": 29, "allergies": ["+海鲜"], "gender": "male"}

        result = merge_profile(current, extracted)
        assert result["age"] == 29
        assert "花生" in result["allergies"]
        assert "海鲜" in result["allergies"]
        assert result["gender"] == "male"

        return SmokeTestResult("Memory System", True, "Short-term memory and profile merge working")
    except Exception as e:
        return SmokeTestResult("Memory System", False, str(e))


async def run_all_tests() -> List[SmokeTestResult]:
    """Run all smoke tests."""
    tests = [
        test_database(),
        test_llm_client(),
        test_rag_retriever(),
        test_memory_system(),
        test_health_advisor_agent(),
    ]

    results = await asyncio.gather(*tests, return_exceptions=True)

    # Convert exceptions to failed results
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed_results.append(
                SmokeTestResult(f"Test {i}", False, str(result))
            )
        else:
            processed_results.append(result)

    return processed_results


def main():
    """Main entry point."""
    print_header("AI Health Manager - Smoke Test")

    print("Running smoke tests...\n")

    # Run tests
    results = asyncio.run(run_all_tests())

    # Print results
    passed = 0
    failed = 0

    for result in results:
        print_result(result)
        if result.passed:
            passed += 1
        else:
            failed += 1

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  Results: {passed} passed, {failed} failed, {passed + failed} total")
    print(f"{'=' * 60}\n")

    # Exit code
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
