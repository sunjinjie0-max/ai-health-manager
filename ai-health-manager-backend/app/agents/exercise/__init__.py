"""Exercise Agent for fitness planning and workout recommendations.

This agent provides personalized exercise and fitness guidance including:
- Fitness level assessment
- Personalized workout plans
- Exercise data analysis
- Injury prevention advice
"""

from .agent import ExerciseAgent
from .state import ExerciseState

__all__ = ["ExerciseAgent", "ExerciseState"]
