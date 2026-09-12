"""Generate Recommendations Node for Nutrition Agent."""

import logging
from typing import Any, Dict, List

from app.llm.deepseek import DeepSeekClient

logger = logging.getLogger(__name__)


async def generate_recommendations(state: dict) -> dict:
    """Generate personalized nutrition recommendations.

    This node generates:
    - Dietary recommendations based on nutrition analysis
    - Alternative food suggestions
    - Tips for healthier eating

    Args:
        state: Current NutritionState

    Returns:
        Updated NutritionState with recommendations
    """
    logger.info(f"[generate_recommendations] Generating recommendations for user {state.get('user_id', 'unknown')}")

    try:
        # Get nutrition data
        total = state.get('total_nutrition', {})
        analysis = state.get('nutrition_analysis', '')
        health_score = state.get('health_score', 0)
        foods = state.get("extracted_foods", [])

        if not foods:
            state['recommendations'] = [
                "这次没有成功识别出具体食物，建议把每样食物名称、份量和做法说得更具体一些。",
                "例如可以描述为“午餐吃了一碗米饭、150g鸡胸肉和一份西兰花”，这样更容易得到准确分析。",
            ]
            state['alternative_foods'] = []
            return state

        # Get user health goals and restrictions
        goals = state.get('user_health_goals', [])
        restrictions = state.get('dietary_restrictions', [])

        # Initialize LLM
        llm = DeepSeekClient()

        # Build system prompt and user message for recommendations
        system_prompt = f"""You are a professional nutritionist.

Based only on the nutritional data and user context provided, generate:
1. A concise nutritional analysis.
2. Specific and actionable dietary recommendations.

Your response must be valid JSON.
Do not include Markdown, code fences, headings, or any text outside the JSON object.
All user-facing content must be written in Chinese."""
        user_message = f"""
Analyze the following meal and provide dietary recommendations.

Nutritional Summary:
- Total Calories: {total.get('calories', 0):.0f} kcal
- Protein: {total.get('protein', 0):.1f} g
- Carbohydrates: {total.get('carbs', 0):.1f} g
- Fat: {total.get('fat', 0):.1f} g
- Fiber: {total.get('fiber', 0):.1f} g

Calculated Assessment:
{analysis}

Health Score:
{health_score:.0f}/100

User Context:
- Health Goals: {', '.join(goals) if goals else 'Not specified'}
- Dietary Restrictions: {', '.join(restrictions) if restrictions else 'None specified'}

Return exactly one JSON object using this structure:

{{
  "nutrition_analysis": "A concise nutritional analysis in Chinese",
  "recommendations": [
    "A specific recommendation in Chinese",
    "A specific recommendation in Chinese",
    "A specific recommendation in Chinese"
  ]
}}

Requirements:
- The nutrition_analysis must contain 3 to 5 concise Chinese sentences.
- Cover overall nutritional balance, macronutrient distribution, strengths, and concerns.
- Return 3 to 5 recommendations.
- Each recommendation must be specific, practical, and actionable.
- Base every conclusion on the nutritional data provided above.
- Do not contradict the nutritional values or the calculated health score.
- Do not invent foods, quantities, health conditions, goals, or dietary restrictions.
- If some data is unavailable, explicitly acknowledge the limitation instead of guessing.
- Do not repeat the same information in both nutrition_analysis and recommendations.
- Do not provide a medical diagnosis.
- Return only valid JSON.
"""

        # Call LLM
        try:
            response = await llm.json_chat(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    stage="nutrition.analyze_and_recommend",
            )

        except Exception as e:
            logger.error(f"[generate_recommendations] LLM error: {e}")
            response = {}

        if not isinstance(response, dict) or "raw_response" in response:
            logger.error(f"[generate_recommendations] LLM returned invalid JSON")
            response = {}

        nutrition_analysis = response.get("nutrition_analysis", "").strip()

        recommendations = response.get("recommendations", [])
        if not isinstance(recommendations, list):
            recommendations=[]

        recommendations = [
            str(item).strip()
            for item in recommendations
            if str(item).strip()
        ]

        if nutrition_analysis:
            state['nutrition_analysis'] = nutrition_analysis
            state["nutrition_analysis_status"] = "generated"

        state['recommendations'] = (recommendations or _generate_fallback_recommendations(state))

        # Generate alternative food suggestions
        state['alternative_foods'] = _generate_alternatives(state)

        logger.info(f"[generate_recommendations] Generated {len(state['recommendations'])} recommendations")

        return state

    except Exception as e:
        logger.error(f"[generate_recommendations] Error: {e}")
        state['error'] = f"Failed to generate recommendations: {e}"
        state['recommendations'] = _generate_fallback_recommendations(state)
        return state


def _generate_fallback_recommendations(state: dict) -> List[str]:
    """Generate fallback recommendations when LLM fails."""
    recommendations = []
    total = state.get('total_nutrition', {})

    # Check protein
    if total.get("protein", 0) < 15:
        recommendations.append("考虑添加优质蛋白质来源，如鸡胸肉、鱼类或豆制品，有助于维持肌肉健康。")

    # Check fiber
    if total.get("fiber", 0) < 5:
        recommendations.append("建议增加蔬菜或全谷物的摄入，提高膳食纤维含量，有助于消化健康。")

    # Check fat
    if total.get("fat", 0) > 25:
        recommendations.append("这餐的脂肪含量较高，建议下一餐选择更清淡的烹饪方式。")

    # General advice
    recommendations.append("保持饮食多样化，确保摄入各类营养素，维持均衡饮食。")

    return recommendations


def _generate_alternatives(state: dict) -> List[Dict[str, Any]]:
    """Generate alternative food suggestions."""
    alternatives = []

    # Map of foods to healthier alternatives
    alternative_map = {
        "白米饭": [
            {"name": "糙米饭", "benefit": "富含膳食纤维，血糖上升更慢"},
            {"name": "燕麦", "benefit": "含有β-葡聚糖，有助于降低胆固醇"},
        ],
        "白面包": [
            {"name": "全麦面包", "benefit": "更高的纤维含量，饱腹感更强"},
        ],
        "炸鸡": [
            {"name": "烤鸡胸肉", "benefit": "减少脂肪摄入，保留优质蛋白"},
            {"name": "蒸鱼", "benefit": "富含Omega-3脂肪酸，有益心脏健康"},
        ],
        "猪肉": [
            {"name": "鸡胸肉", "benefit": "更低的脂肪含量，高蛋白"},
            {"name": "鱼类", "benefit": "优质蛋白，含有益心脏的脂肪酸"},
        ],
        "含糖饮料": [
            {"name": "无糖茶", "benefit": "零热量，含有抗氧化物质"},
            {"name": "柠檬水", "benefit": "清爽解渴，促进维生素C摄入"},
        ],
    }

    # Check for foods that have alternatives
    for food in state.get('extracted_foods', []):
        food_name = food.get("name", "")
        for key, alts in alternative_map.items():
            if key in food_name or food_name in key:
                for alt in alts:
                    alternatives.append({
                        "original_food": food_name,
                        "alternative": alt["name"],
                        "benefit": alt["benefit"],
                    })

    return alternatives[:5]  # Return top 5 alternatives
