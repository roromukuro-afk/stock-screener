from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, JSON
from sqlalchemy.sql import func
from app.database import Base


class Stock(Base):
    __tablename__ = "stocks"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, index=True, nullable=False)
    name = Column(String)
    market = Column(String)
    exchange = Column(String)
    sector = Column(String)
    industry = Column(String)
    currency = Column(String)
    country = Column(String)
    is_adr = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class DailyPrice(Base):
    __tablename__ = "daily_prices"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    date = Column(String, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    adjusted_close = Column(Float)
    volume = Column(Float)
    turnover = Column(Float)
    currency = Column(String)
    source = Column(String)
    created_at = Column(DateTime, server_default=func.now())


class Indicator(Base):
    __tablename__ = "indicators"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    date = Column(String, nullable=False)
    ma5 = Column(Float)
    ma25 = Column(Float)
    ma75 = Column(Float)
    ma200 = Column(Float)
    volume_avg5 = Column(Float)
    volume_avg20 = Column(Float)
    volume_ratio = Column(Float)
    price_change_1d = Column(Float)
    price_change_5d = Column(Float)
    price_change_20d = Column(Float)
    ma25_deviation = Column(Float)
    recent_high_20 = Column(Float)
    recent_low_20 = Column(Float)
    recent_high_60 = Column(Float)
    recent_low_60 = Column(Float)
    support_line = Column(Float)
    resistance_line = Column(Float)
    upside_to_resistance = Column(Float)
    support_distance = Column(Float)
    atr = Column(Float)
    rsi = Column(Float)
    trend_state = Column(String)
    range_state = Column(String)
    candle_state = Column(String)
    chart_pattern_primary = Column(String)
    chart_pattern_secondary = Column(String)
    chart_pattern_warning = Column(String)
    pattern_confidence = Column(Float)
    created_at = Column(DateTime, server_default=func.now())


class Material(Base):
    __tablename__ = "materials"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    date = Column(String)
    source_type = Column(String)
    title = Column(Text)
    url = Column(Text)
    summary = Column(Text)
    theme_tags = Column(JSON)
    catalyst_type = Column(String)
    catalyst_date = Column(String)
    freshness_score = Column(Float)
    created_at = Column(DateTime, server_default=func.now())


class ScreeningResult(Base):
    __tablename__ = "screening_results"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    date = Column(String, nullable=False)
    price = Column(Float)
    jpy_price = Column(Float)
    fx_rate = Column(Float)
    fx_rate_timestamp = Column(String)
    price_timestamp = Column(String)
    market_cap = Column(Float)
    volume = Column(Float)
    turnover = Column(Float)
    price_condition_pass = Column(Boolean, default=False)
    liquidity_condition_pass = Column(Boolean, default=False)
    upside_score = Column(Float, default=0)
    future_catalyst_score = Column(Float, default=0)
    chart_score = Column(Float, default=0)
    volume_cycle_score = Column(Float, default=0)
    material_theme_score = Column(Float, default=0)
    supply_score = Column(Float, default=0)
    archetype_score = Column(Float, default=0)
    risk_management_score = Column(Float, default=0)
    total_score = Column(Float, default=0)
    classification = Column(String)
    volume_cycle_state = Column(String)
    chart_cycle_state = Column(String)
    main_archetype = Column(String)
    sub_archetypes = Column(JSON)
    chart_types = Column(JSON)
    warning_types = Column(JSON)
    warning_flags = Column(JSON)
    exclude_flag = Column(Boolean, default=False)
    exclude_reason = Column(String)
    ai_comment = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class ExclusionList(Base):
    __tablename__ = "exclusion_list"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    name = Column(String)
    market = Column(String)
    reason = Column(String)
    source_file = Column(String)
    created_at = Column(DateTime, server_default=func.now())


class AppSetting(Base):
    __tablename__ = "app_settings"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    value = Column(Text)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ScreeningJob(Base):
    __tablename__ = "screening_jobs"
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String)
    market_scope = Column(String)
    total_count = Column(Integer, default=0)
    processed_count = Column(Integer, default=0)
    adopted_count = Column(Integer, default=0)
    conditional_count = Column(Integer, default=0)
    watch_count = Column(Integer, default=0)
    excluded_count = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime)


class AARRecord(Base):
    __tablename__ = "aar_records"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    date = Column(String)
    classification = Column(String)
    score_before_move = Column(Float)
    main_archetype = Column(String)
    sub_archetypes = Column(JSON)
    chart_types = Column(JSON)
    warning_types = Column(JSON)
    t3_sign = Column(Text)
    t2_sign = Column(Text)
    t1_sign = Column(Text)
    entry_possible = Column(String)
    entry_condition = Column(Text)
    stop_condition = Column(Text)
    watch_condition = Column(Text)
    result_after_1d = Column(Float)
    result_after_3d = Column(Float)
    result_after_5d = Column(Float)
    result_after_10d = Column(Float)
    result_after_20d = Column(Float)
    max_gain = Column(Float)
    max_drawdown = Column(Float)
    hit_20_percent = Column(Boolean)
    failure_reason = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
