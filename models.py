from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

class Entity(BaseModel):
    source_url: str
    entity_type: Optional[str] = Field(default=None)
    name: Optional[str] = None
    address: Optional[str] = None
    locality: Optional[str] = None
    region: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    phones: List[str] = []
    emails: List[str] = []
    website: Optional[str] = None
    socials: Dict[str, str] = {}
    geo: Optional[Dict[str, float]] = None
    categories: List[str] = []
    rating: Optional[float] = None
    data_quality: float = 0.0
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
