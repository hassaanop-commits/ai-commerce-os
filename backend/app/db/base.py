from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Imported after Base is defined, and only for the side effect of registering every
# model on Base.metadata (models import Base back from this module). Required so
# Base.metadata is complete wherever this module is imported, e.g. by Alembic.
from app.models import *  # noqa: E402,F401
