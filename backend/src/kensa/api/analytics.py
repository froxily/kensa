"""Analytics endpoints for the dashboard (v1.1, D-055).

All reads; ``POST /analytics/refresh`` recomputes the days whose sources changed. Every query is
scoped to the request's workspace. By default only real observations count (``github_live``,
``pasted``); ``include_all_origins`` adds samples, evaluation fixtures and replays.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Query

from kensa.analytics import queries
from kensa.analytics.refresh import ALL_ORIGINS, REAL_ORIGINS, refresh_changed
from kensa.api.deps import SessionDep, SettingsDep, WorkspaceDep

router = APIRouter(tags=["analytics"])

Days = Annotated[int, Query(ge=1, le=366)]
Text = Annotated[str | None, Query(max_length=300)]


def _filters(
    days: int, repository: str | None, workflow: str | None, all_origins: bool
) -> queries.Filters:
    return queries.Filters.last_days(
        days,
        repository=repository or None,
        workflow=workflow or None,
        origins=ALL_ORIGINS if all_origins else REAL_ORIGINS,
    )


@router.post("/analytics/refresh")
def refresh(session: SessionDep, workspace: WorkspaceDep) -> dict[str, int]:
    with session.begin():
        return {"days_refreshed": refresh_changed(session, workspace.id)}


@router.get("/analytics/dashboard")
def dashboard(
    session: SessionDep,
    workspace: WorkspaceDep,
    days: Days = 30,
    repository: Text = None,
    workflow: Text = None,
    include_all_origins: bool = False,
    *,
    settings: SettingsDep,
) -> dict[str, Any]:
    """Everything the dashboard shows, in one response (refreshing changed days first).

    Recurring failures come from history matching, which is experimental and off by default
    (D-057): then they are neither counted nor listed."""
    with session.begin():
        refresh_changed(session, workspace.id)
    f = _filters(days, repository, workflow, include_all_origins)
    matching = settings.history_matching
    with session.begin():
        summary = queries.summary(session, workspace.id, f)
        if not matching:
            summary["recurring_failures"] = None
        return {
            "history_matching": matching,
            "filters": {
                "days": days,
                "start": f.start.isoformat(),
                "end": f.end.isoformat(),
                "repository": f.repository,
                "workflow": f.workflow,
                "origins": list(f.origins),
            },
            "summary": summary,
            "trends": queries.trends(session, workspace.id, f),
            "categories": queries.categories(session, workspace.id, f),
            "workflows": queries.workflows(session, workspace.id, f),
            "recurring": queries.recurring(session, workspace.id, f) if matching else [],
            "freshness": queries.freshness(session, workspace.id),
            "quality": queries.quality(session, workspace.id),
            "options": queries.options(session, workspace.id),
        }
