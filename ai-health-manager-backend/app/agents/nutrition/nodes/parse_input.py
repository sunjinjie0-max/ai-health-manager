"""Parse Input Node for Nutrition Agent."""

import logging
from typing import Any, Dict

from app.config import settings
from app.llm.deepseek import DeepSeekClient, mark_llm_degraded

logger = logging.getLogger(__name__)


async def parse_input(state: dict) -> dict:
    """Parse user input to understand the nutrition query."""
    logger.info(f"[parse_input] Parsing input: {state.get('user_message', '')[:100]}...")

    try:
        # Initialize LLM client
        llm = DeepSeekClient()

        # Build system prompt and user message for input parsing
        system_prompt = "You are a nutrition analysis assistant. Parse the user's input and extract structured information in JSON format."
        user_message = f"""Parse the following user input:

User Input: {state.get('user_message', '')}

Provide the following in JSON format:
1. food_description: Extract the food/meal description from the input
2. query_intent
必须从以下值中选择一个：

- "meal_analysis"
  用户描述已经吃过或准备吃的一顿饭，希望分析是否健康。
  示例：“午餐吃了炸鸡、米饭和奶茶，帮我分析一下。”

- "food_lookup"
  用户询问某种具体食物的热量、蛋白质、脂肪或其他营养信息。
  示例：“一个苹果大约有多少热量？”

- "food_comparison"
  用户希望比较两种或多种具体食物。
  示例：“米饭和面条哪个更适合减脂？”

- "general_advice"
  用户询问整体饮食方法、饮食目标或搭配建议，不依赖具体食物。
  示例：“减脂期间应该怎么吃？”

- "nutrition_knowledge"
  用户询问营养概念、营养素作用或一般营养知识。
  示例：“什么是优质蛋白质？”

- "unknown"
  输入信息不足、与营养无关，或者无法确定用户意图。

判断注意事项：

- 没有具体食物名称，不代表一定是 unknown。
- “怎么吃”“如何搭配”等问题通常属于 general_advice。
- “什么是”“有什么作用”等问题通常属于 nutrition_knowledge。
- 只有确实无法确定意图时才返回 unknown。
- 不要虚构用户没有提到的食物。

Return ONLY valid JSON without any markdown formatting or additional text."""

        # Call LLM
        response = await llm.json_chat(
            system_prompt=system_prompt,
            user_message=user_message,
            stage="nutrition.parse_input",
            deadline_monotonic=state.get("deadline_monotonic"),
            timeout_seconds=settings.specialist_llm_timeout_seconds,
        )

        # Parse response - response is already a dict from json_chat
        if "raw_response" in response:
            logger.error(f"[parse_input] LLM parsing error: {response}")
            # Fallback to simple parsing
            return {
                **state,
                "food_description": state.get('user_message', ''),
                "query_intent": "unknown",
            }

        parsed = response

        # Return only the changed keys
        result = {
            "food_description": parsed.get("food_description", state.get('user_message', '')),
            "query_intent": parsed.get("query_intent", "unknown"),
        }

        # Log results
        logger.info(f"[parse_input] Extracted food_description: {result['food_description'][:100]}...")

        return {
            **state,
            **result,
        }

    except Exception as e:
        logger.error(f"[parse_input] Error: {e}")
        mark_llm_degraded(state, stage="nutrition.parse_input", error=e)
        # Fallback
        return {
            **state,
            "food_description": state.get('user_message', ''),
            "query_intent": "unknown",
        }
