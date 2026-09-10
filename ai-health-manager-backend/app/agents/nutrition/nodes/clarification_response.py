"""Nutrition request clarification node."""


async def clarification_response(state: dict) -> dict:
    """Ask the user to clarify an unknown nutrition request."""
    return {
        **state,
        "response": (
            "我还不能确定你希望进行哪一种营养分析。"
            "你可以补充说明：\n\n"
            "1. 分析一顿饭，例如“午餐吃了炸鸡、米饭和奶茶”；\n"
            "2. 查询一种食物，例如“一个苹果大约有多少热量”；\n"
            "3. 获取一般建议，例如“减脂期间应该怎么吃”。"
        ),
        "recommendations": [],
    }
