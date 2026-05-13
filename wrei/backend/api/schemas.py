from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Literal, Dict, Any

class HuntConfigSchema(BaseModel):
    city_slug: str = Field("warszawa", pattern="^[a-z-]+$")
    portals: List[str] = Field(default_factory=list)
    pages: int = Field(3, ge=1, le=20)
    min_price: Optional[int] = Field(None, ge=0)
    max_price: Optional[int] = Field(None, ge=0)
    min_area: Optional[float] = Field(None, ge=0)
    max_area: Optional[float] = Field(None, ge=0)
    rooms: Optional[Any] = None # Can be list or int or str
    districts: List[str] = Field(default_factory=list)
    direct_only: bool = False
    min_score_alert: float = Field(0.20, ge=0.0, le=1.0)

class AlertConfigSchema(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    city_slug: str = "warszawa"
    # condition_expr is the legacy eval() string, will be replaced by condition_json
    condition_expr: Optional[str] = None
    condition_json: Optional[Dict[str, Any]] = None
    channel: Literal["email", "telegram", "webhook"] = "email"
    target: str = Field(..., min_length=3)
    is_active: bool = True

class MarketStatsRequestSchema(BaseModel):
    city_slug: str = "warszawa"
    force_recalculate: bool = False
