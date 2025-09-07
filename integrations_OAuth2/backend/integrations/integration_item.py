from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

class IntegrationItem(BaseModel):
    """A standardized Pydantic model for items from various integrations."""
    id: Optional[str] = None
    type: Optional[str] = None
    name: Optional[str] = None
    parent_id: Optional[str] = None
    parent_path_or_name: Optional[str] = None
    creation_time: Optional[datetime] = None
    last_modified_time: Optional[datetime] = None
    url: Optional[str] = None
    mime_type: Optional[str] = None
    delta: Optional[str] = None
    drive_id: Optional[str] = None
    directory: bool = False
    visibility: bool = True
    children: List[str] = Field(default_factory=list)

    class Config:
        orm_mode = True
