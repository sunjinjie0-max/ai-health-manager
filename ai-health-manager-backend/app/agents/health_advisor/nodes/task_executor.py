"""Task Executor Node."""

import json
import logging

from app.agents.health_advisor.state import HealthAdvisorState

logger = logging.getLogger(__name__)


class TaskExecutor:
    """任务执行器节点 - 根据识别到的意图执行相应任务."""

    def __init__(self, config: dict = None):
        """初始化任务执行器."""
        self.config = config or {}

    def __call__(self, state: HealthAdvisorState):
        """执行任务."""
        try:
            intent = state.get("intent", "")
            message = state.get("user_message", "")
            response = ""
            citations = []
            suggested_questions = []

            # 根据不同意图生成响应
            if intent == "diet_analysis":
                response = self._handle_diet_analysis(message, state)
            elif intent == "exercise_recommendation":
                response = self._handle_exercise_recommendation(message, state)
            elif intent == "sleep_analysis":
                response = self._handle_sleep_analysis(message, state)
            elif intent == "air_quality":
                response = self._handle_air_quality(message, state)
            elif intent == "health_summary":
                response = self._handle_health_summary(message, state)
            else:
                # 通用聊天响应
                response = self._handle_general_chat(message, state)

            # 更新状态
            state["response"] = response
            state["citations"] = citations
            state["suggested_questions"] = suggested_questions
            state["status"] = "completed"

            return state
        except Exception as e:
            logger.error(f"Error in task execution: {e}")
            state["response"] = f"抱歉，处理您的请求时出现了错误: {str(e)}"
            state.status = "error"
            return state

    def _handle_diet_analysis(self, message: str, state: HealthAdvisorState) -> str:
        """Handle diet analysis intent."""
        return (
            f"🍎 **饮食分析**\n\n"
            f"您提到了：{message}\n\n"
            f"根据您的描述，我建议您：\n"
            f"1. 保持均衡饮食，多吃蔬菜水果\n"
            f"2. 控制糖分和油脂摄入\n"
            f"3. 注意蛋白质补充\n"
            f"4. 保持适量饮水\n\n"
            f"如果您需要更详细的分析，请提供更多具体信息。"
        )

    def _handle_exercise_recommendation(self, message: str, state: HealthAdvisorState) -> str:
        """Handle exercise recommendation intent."""
        return (
            f"🏃 **运动建议**\n\n"
            f"您提到了：{message}\n\n"
            f"基于您的需求，我推荐以下运动：\n"
            f"1. 有氧运动：快走、慢跑或游泳，每次30-45分钟\n"
            f"2. 力量训练：每周2-3次，针对主要肌群\n"
            f"3. 柔韧性训练：瑜伽或拉伸，每次10-15分钟\n"
            f"4. 日常活动：增加步行，少坐多站\n\n"
            f"请根据您的身体状况选择合适的运动强度。"
        )

    def _handle_sleep_analysis(self, message: str, state: HealthAdvisorState) -> str:
        """Handle sleep analysis intent."""
        return (
            f"😴 **睡眠分析**\n\n"
            f"您提到了：{message}\n\n"
            f"针对您的睡眠问题，我建议：\n"
            f"1. 规律作息：每天固定时间睡觉和起床\n"
            f"2. 睡前准备：睡前1小时避免使用电子设备\n"
            f"3. 环境优化：保持卧室安静、黑暗、凉爽\n"
            f"4. 饮食注意：避免睡前大量进食或饮用咖啡茶\n"
            f"5. 放松技巧：尝试冥想、深呼吸或渐进式肌肉放松\n\n"
            f"如果睡眠问题持续，建议咨询专业医生。"
        )

    def _handle_air_quality(self, message: str, state: HealthAdvisorState) -> str:
        """Handle air quality intent."""
        return (
            f"🌤️ **空气质量**\n\n"
            f"您提到了：{message}\n\n"
            f"关于空气质量，以下是建议：\n"
            f"1. 关注当地空气质量指数(AQI)报告\n"
            f"2. 空气质量差时减少户外活动\n"
            f"3. 室内使用空气净化器\n"
            f"4. 外出时佩戴防护口罩\n"
            f"5. 保持室内通风，选择合适时段开窗\n\n"
            f"如需查询具体地区的实时空气质量，请告诉我具体城市。"
        )

    def _handle_health_summary(self, message: str, state: HealthAdvisorState) -> str:
        """Handle health summary intent."""
        return (
            f"📊 **健康总结**\n\n"
            f"您提到了：{message}\n\n"
            f"基于当前信息，以下是健康概览：\n"
            f"1. 饮食：保持均衡饮食，注意营养摄入\n"
            f"2. 运动：建议每周至少150分钟中等强度运动\n"
            f"3. 睡眠：保持7-9小时优质睡眠\n"
            f"4. 心理：注意压力管理，保持积极心态\n"
            f"5. 预防：定期体检，关注身体变化\n\n"
            f"如需更详细的个性化分析，请提供更多健康数据。"
        )

    def _handle_general_chat(self, message: str, state: HealthAdvisorState) -> str:
        """Handle general chat intent."""
        return (
            f"您好！我是您的AI健康管家。👋\n\n"
            f"我可以帮助您：\n"
            f"🍎 分析饮食和提供营养建议\n"
            f"🏃 推荐适合的运动方案\n"
            f"😴 分析睡眠问题并提供改善建议\n"
            f"🌤️ 查询空气质量和健康提醒\n"
            f"📊 生成个人健康总结报告\n\n"
            f"您今天想了解哪方面的健康信息呢？"
        )
