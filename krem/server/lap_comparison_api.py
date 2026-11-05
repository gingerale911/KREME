
"""REST API for comparing two persisted KREM laps."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from krem.pipeline.lap_comparison import compare_laps
from krem.storage.lap_repository import LapRepository


def create_lap_comparison_router(
    repository: LapRepository | None,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/laps/compare")
    async def compare_stored_laps(
        reference_id: str = Query(..., min_length=1),
        comparison_id: str = Query(..., min_length=1),
        grid_points: int = Query(201, ge=2, le=2001),
    ):
        """Compare two persisted laps using their stored telemetry."""

        if repository is None:
            raise HTTPException(
                status_code=503,
                detail="Lap storage is not configured",
            )

        if reference_id == comparison_id:
            raise HTTPException(
                status_code=400,
                detail="Choose two different laps",
            )

        reference = repository.get_lap(reference_id)
        comparison = repository.get_lap(comparison_id)

        if reference is None:
            raise HTTPException(
                status_code=404,
                detail="Reference lap not found",
            )

        if comparison is None:
            raise HTTPException(
                status_code=404,
                detail="Comparison lap not found",
            )

        reference_trace = repository.get_lap_trace(reference_id)
        comparison_trace = repository.get_lap_trace(comparison_id)

        if reference_trace is None or comparison_trace is None:
            raise HTTPException(
                status_code=404,
                detail="Lap telemetry trace not found",
            )

        try:
            result = compare_laps(
                reference_lap=reference,
                comparison_lap=comparison,
                reference_trace=reference_trace,
                comparison_trace=comparison_trace,
                grid_points=grid_points,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

        return result

    return router
