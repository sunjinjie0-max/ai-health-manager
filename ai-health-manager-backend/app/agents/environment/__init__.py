"""Environment Agent for health-related environmental analysis.

This agent provides environmental health insights including:
- Air quality assessment
- Weather-based health recommendations
- Environmental risk alerts
- Indoor air quality advice
"""

from .agent import EnvironmentAgent
from .state import EnvironmentState

__all__ = ["EnvironmentAgent", "EnvironmentState"]