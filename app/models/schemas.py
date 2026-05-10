"""Pydantic schemas for request/response validation."""
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID


class ActionPlanCreate(BaseModel):
    """Schema for creating an action plan."""
    department_id: UUID
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2020, le=2100)
    goal: str = ""


class ActionPlanUpdate(BaseModel):
    """Schema for updating an action plan."""
    month: Optional[int] = Field(None, ge=1, le=12)
    year: Optional[int] = Field(None, ge=2020, le=2100)
    goal: Optional[str] = None


class ActivityCreate(BaseModel):
    """Schema for creating an activity."""
    plan_id: UUID
    description: str = ""
    location: str = ""
    logistics: str = ""


class ActivityUpdate(BaseModel):
    """Schema for updating an activity."""
    description: Optional[str] = None
    location: Optional[str] = None
    logistics: Optional[str] = None


class ActivityScheduleUpdate(BaseModel):
    """Schema for updating activity schedule (day checkboxes)."""
    monday: bool = False
    tuesday: bool = False
    wednesday: bool = False
    thursday: bool = False
    friday: bool = False
    saturday: bool = False
    sunday: bool = False


class UserCreate(BaseModel):
    """Schema for creating a user (admin)."""
    email: str
    password: str
    full_name: str = ""
    role: str
    department_id: Optional[UUID] = None


class UserUpdate(BaseModel):
    """Schema for updating a user (admin)."""
    full_name: Optional[str] = None
    role: Optional[str] = None
    department_id: Optional[UUID] = None
