"""
Health data schemas
"""

from typing import Optional, List, Any
from datetime import date
from pydantic import BaseModel, ConfigDict


# Base schemas
class StepsData(BaseModel):
    date: str
    steps: int
    distance: Optional[float] = None
    calories: Optional[int] = None


class SleepData(BaseModel):
    date: str
    duration: float
    deep_sleep: Optional[float] = None
    light_sleep: Optional[float] = None
    quality: Optional[str] = None


class HeartRateData(BaseModel):
    date: str
    resting: int
    max: Optional[int] = None
    avg: Optional[int] = None


# Response schemas
class HealthProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    records: dict  # Contains steps, sleep, heart_rate data
    summary: Optional[dict] = None


class HealthDataImportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str  # completed, partial, failed
    imported_count: int
    failed_count: int
    errors: List[str]


class HealthStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    data_type: str
    period: str
    total: Optional[float] = None
    average: Optional[float] = None
    max: Optional[float] = None
    min: Optional[float] = None
    count: int
    trend: Optional[str] = None  # up, down, stable


# Request schemas
class HealthDataImportRequest(BaseModel):
    format: str  # csv, json
    data_type: str  # steps, sleep, heart_rate, all


class HealthDataDeleteRequest(BaseModel):
    record_ids: Optional[List[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class HealthStatsRequest(BaseModel):
    data_type: str
    period: str = "30d"  # 7d, 30d, 90d, 1y
