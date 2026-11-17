from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.recommendation import RecommendationReport
from app.services.recommendations import build_recommendation_report

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("", response_model=RecommendationReport)
def get_recommendations(
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
) -> RecommendationReport:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be on or before end_date",
        )
    return build_recommendation_report(db, start_date, end_date)
