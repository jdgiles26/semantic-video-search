"""Email-related Pydantic models."""
from typing import List
from pydantic import BaseModel


class EmailConfig(BaseModel):
    """Email configuration."""
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    from_email: str = ""
    to_emails: List[str] = []
    alert_on_critical: bool = True
    alert_on_watch_match: bool = True


class EmailAlertRequest(BaseModel):
    """Email alert request."""
    config: EmailConfig
    alert_type: str
    data: dict
