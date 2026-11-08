"""Request-scoped dependencies: settings, database sessions and the authorisation context."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from kensa.core.config import Settings
from kensa.db.models import DEFAULT_WORKSPACE_ID


@dataclass(frozen=True)
class Workspace:
    """Who the request acts for. Every query must filter by ``id`` (DECISIONS.md D-011)."""

    id: uuid.UUID


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_engine(request: Request) -> Engine:
    engine: Engine = request.app.state.engine
    return engine


def get_session(engine: Annotated[Engine, Depends(get_engine)]) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def get_workspace() -> Workspace:
    # Single local operator: every request acts in the default workspace. Adding real users
    # means resolving the workspace from the authenticated principal here, and nowhere else.
    return Workspace(DEFAULT_WORKSPACE_ID)


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
EngineDep = Annotated[Engine, Depends(get_engine)]
SessionDep = Annotated[Session, Depends(get_session)]
WorkspaceDep = Annotated[Workspace, Depends(get_workspace)]
