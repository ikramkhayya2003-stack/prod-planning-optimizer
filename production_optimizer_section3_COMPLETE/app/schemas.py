from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class WeightsRequest(BaseModel):
    tardiness: float = Field(0.50, ge=0)
    setup: float = Field(0.20, ge=0)
    inventory: float = Field(0.15, ge=0)
    idle: float = Field(0.15, ge=0)

    @model_validator(mode="after")
    def validate_sum(self):
        total = self.tardiness + self.setup + self.inventory + self.idle
        if abs(total - 1.0) > 0.0001:
            raise ValueError("Weights must sum to 1.0")
        return self


class ScenarioRequest(BaseModel):
    type: str = Field(
        ...,
        pattern="^(demand_increase|machine_unavailable|supplier_lead_time)$",
    )
    demand_increase_pct: float = Field(0, ge=0, le=200)
    machine_id: Optional[str] = None
    machine_start: Optional[datetime] = None
    machine_end: Optional[datetime] = None
    supplier_id: Optional[str] = None
    lead_time_delta_days: int = Field(0, ge=0, le=365)

    @model_validator(mode="after")
    def validate_scenario(self):
        if self.type == "demand_increase" and self.demand_increase_pct <= 0:
            raise ValueError("demand_increase_pct must be > 0 for demand scenarios.")

        if self.type == "machine_unavailable":
            if not self.machine_id:
                raise ValueError("machine_id is required for machine scenarios.")
            if not self.machine_start or not self.machine_end:
                raise ValueError("machine_start and machine_end are required.")
            if self.machine_end <= self.machine_start:
                raise ValueError("machine_end must be after machine_start.")

        if self.type == "supplier_lead_time":
            if not self.supplier_id:
                raise ValueError("supplier_id is required for supplier scenarios.")
            if self.lead_time_delta_days <= 0:
                raise ValueError("lead_time_delta_days must be > 0.")

        return self


class OptimizeRequest(BaseModel):
    max_time_seconds: float = Field(
    default=300,
    gt=0,
    le=3600,
    description="Maximum CP-SAT solving time in seconds."
)
    num_workers: int = Field(8, ge=1, le=64)
    random_seed: int = Field(42, ge=0)
    weights: WeightsRequest = WeightsRequest()

    planning_start_date: Optional[date] = None
    planning_end_date: Optional[date] = None
    include_weekends: bool = False
    include_overtime: bool = False
    scenario: Optional[ScenarioRequest] = None

    @model_validator(mode="after")
    def validate_horizon(self):
        if self.planning_start_date and self.planning_end_date:
            if self.planning_end_date < self.planning_start_date:
                raise ValueError("planning_end_date must be on or after planning_start_date.")
        elif self.planning_start_date or self.planning_end_date:
            raise ValueError("planning_start_date and planning_end_date must be provided together.")
        return self


class OrderCreateRequest(BaseModel):
    customer: str
    product_id: str
    order_qty: int = Field(gt=0)
    requested_due_date: datetime
    priority_class: str = Field(pattern="^[ABC]$")
    is_urgent: bool = False


class BreakdownRequest(BaseModel):
    start: datetime
    end: datetime
    reason: str | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end <= self.start:
            raise ValueError("Breakdown end must be after start.")
        return self


class PlanningOperationUpdate(BaseModel):
    machine_id: str
    start_min: int
    end_min: int


class PlanningOperationUpdateResponse(BaseModel):
    valid: bool
    status: str
    message: str
    operation_id: int
    machine_id: str
    start_min: int
    end_min: int
    start_datetime: datetime
    end_datetime: datetime
    validation_errors: list[str] = []
