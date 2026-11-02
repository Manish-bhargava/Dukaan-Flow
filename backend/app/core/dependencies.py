from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database.session import get_db

# Shared FastAPI dependency aliases for route handlers.
DbSession = Annotated[Session, Depends(get_db)]
