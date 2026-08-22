"""Long-horizon research forecast persistence models.

These tables are intentionally separate from prediction_logs/prediction_outcomes,
which are optimized for short-term T+1/T+3/T+5/T+10/T+20 surge predictions.
"""
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class ResearchForecast(Base):
    __tablename__ = "research_forecasts"
    __table_args__ = (
        UniqueConstraint(
            "symbol", "analysis_asof", "forecast_version",
            name="uq_research_forecast_symbol_asof_version",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    yahoo_symbol = Column(String, index=True, nullable=False)
    name = Column(String)
    market = Column(String, index=True, nullable=False, default="JP")
    currency = Column(String, default="JPY")

    # Point-in-time snapshot identity. Keep the original timezone-bearing ISO string.
    analysis_asof = Column(String, index=True, nullable=False)
    analysis_date = Column(String, index=True, nullable=False)
    timezone = Column(String, default="Asia/Tokyo")
    forecast_version = Column(String, default="deep-research-v1", index=True)

    # Price used by the research report as the denominator for all forecast returns.
    base_price = Column(Float, nullable=False)
    base_price_date = Column(String)
    base_price_type = Column(String)  # realtime / delayed / close / previous_close / other
    base_price_source = Column(Text)

    source_label = Column(String, default="ChatGPT Deep Research")
    source_reference = Column(Text)
    notes = Column(Text)
    status = Column(String, default="open", index=True)  # open / complete / cancelled

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ResearchForecastCheckpoint(Base):
    __tablename__ = "research_forecast_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "forecast_id", "horizon",
            name="uq_research_forecast_checkpoint_horizon",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    forecast_id = Column(Integer, index=True, nullable=False)
    symbol = Column(String, index=True, nullable=False)
    horizon = Column(String, index=True, nullable=False)  # 1w / 1m / 3m / 6m / 1y
    horizon_label = Column(String)
    target_calendar_date = Column(String, index=True, nullable=False)
    evaluation_policy = Column(String, default="first_trading_day_on_or_after_target")

    # Forecast values frozen at save time.
    predicted_return_pct = Column(Float, nullable=False)
    predicted_price = Column(Float, nullable=False)
    center_range_low = Column(Float)
    center_range_high = Column(Float)
    upside_reference_price = Column(Float)
    downside_reference_price = Column(Float)
    confidence = Column(String)
    rationale = Column(Text)

    # Realized outcome. Raw close is the market quote on the check date. Comparable
    # close is converted back to the pre-split share basis so stock splits do not
    # create a false forecast miss. Cash dividends are intentionally not adjusted.
    actual_check_date = Column(String, index=True)
    actual_close_raw = Column(Float)
    split_adjustment_factor = Column(Float, default=1.0)
    actual_close_comparable = Column(Float)
    actual_return_pct = Column(Float)

    # Accuracy metrics.
    price_error = Column(Float)  # actual_comparable - predicted_price
    absolute_price_error = Column(Float)
    forecast_error_pct = Column(Float)  # (actual / predicted - 1) * 100
    absolute_percentage_error_pct = Column(Float)  # abs(actual-predicted)/actual * 100
    return_error_pct_points = Column(Float)  # actual return - predicted return
    direction_match = Column(Boolean)
    center_range_hit = Column(Boolean)
    outer_range_hit = Column(Boolean)

    status = Column(String, default="pending", index=True)  # pending / evaluated / error
    data_source = Column(String)
    last_error = Column(Text)
    evaluated_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
