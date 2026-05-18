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


class UniverseSymbol(Base):
    __tablename__ = "universe_symbols"
    id = Column(Integer, primary_key=True, index=True)
    raw_symbol = Column(String, index=True)
    symbol = Column(String, unique=True, index=True, nullable=False)
    yahoo_symbol = Column(String, index=True)
    name = Column(String)
    market = Column(String, index=True)
    exchange = Column(String)
    source = Column(String)
    country = Column(String)
    currency = Column(String)
    instrument_type = Column(String, index=True)  # common_stock / adr / etf / warrant / unit / right / preferred / fund / etn / note / bond / test_issue / spac / unknown
    is_common_stock = Column(Boolean, default=False)
    is_adr = Column(Boolean, default=False)
    is_etf = Column(Boolean, default=False)
    is_warrant = Column(Boolean, default=False)
    is_unit = Column(Boolean, default=False)
    is_right = Column(Boolean, default=False)
    is_preferred = Column(Boolean, default=False)
    is_spac = Column(Boolean, default=False)
    is_fund = Column(Boolean, default=False)
    is_test_issue = Column(Boolean, default=False)
    is_screening_eligible = Column(Boolean, default=False, index=True)
    exclusion_reason = Column(String)
    duplicate_key = Column(String, index=True)
    first_seen_at = Column(DateTime, server_default=func.now())
    last_seen_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PriceFreshness(Base):
    __tablename__ = "price_freshness"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    yahoo_symbol = Column(String, index=True)
    market = Column(String)
    data_source = Column(String)
    price = Column(Float)
    currency = Column(String)
    jpy_price = Column(Float)
    quote_date = Column(String, index=True)
    quote_time = Column(String)
    latest_trading_day = Column(String)
    fetched_at_utc = Column(String)
    fetched_at_jst = Column(String)
    exchange_timezone = Column(String)
    is_market_open_at_fetch = Column(Boolean)
    delay_minutes_estimated = Column(Float)
    is_realtime_or_delayed = Column(String)  # realtime / delayed / close / unknown
    freshness_status = Column(String, index=True)
    is_stale = Column(Boolean, default=False, index=True)
    stale_reason = Column(String)
    created_at = Column(DateTime, server_default=func.now())


class UniverseUpdateJob(Base):
    __tablename__ = "universe_update_jobs"
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, index=True)
    source = Column(String)
    total_raw_count = Column(Integer, default=0)
    normalized_count = Column(Integer, default=0)
    eligible_count = Column(Integer, default=0)
    excluded_count = Column(Integer, default=0)
    stale_price_count = Column(Integer, default=0)
    fresh_price_count = Column(Integer, default=0)
    failed_price_count = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime)


class AARInputCase(Base):
    __tablename__ = "aar_input_cases"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    yahoo_symbol = Column(String)
    name = Column(String)
    market = Column(String)
    move_date = Column(String, index=True)
    move_percent_user = Column(Float)
    move_percent_calculated = Column(Float)
    user_memo = Column(Text)
    material_url = Column(Text)
    source_file = Column(String)
    status = Column(String)  # pending / analyzed / failed
    error_message = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AARAnalysisCase(Base):
    __tablename__ = "aar_analysis_cases"
    id = Column(Integer, primary_key=True, index=True)
    input_case_id = Column(Integer, index=True)
    symbol = Column(String, index=True)
    yahoo_symbol = Column(String)
    name = Column(String)
    market = Column(String)
    move_date = Column(String, index=True)
    move_percent = Column(Float)

    # 材料分析
    catalyst = Column(Text)
    catalyst_category = Column(String, index=True)
    catalyst_timing = Column(String)
    catalyst_strength_score = Column(Float)
    catalyst_continuity_score = Column(Float)
    material_confirmed = Column(Boolean, default=False)
    material_source_rank = Column(String)

    # T-1判定
    t1_judgement = Column(String, index=True)
    t1_entry_possible = Column(String)
    t1_entry_type = Column(String)

    # 分類
    setup_type = Column(String, index=True)
    volume_type = Column(String, index=True)
    chart_type = Column(String, index=True)
    volatility_type = Column(String)
    ma_support_state = Column(String)

    # リスクスコア
    overextension_risk_score = Column(Float)
    bad_news_vacuum_score = Column(Float)
    material_exhaustion_risk_score = Column(Float)

    # 警告フラグ
    t0_only_flag = Column(Boolean, default=False)
    already_ran_flag = Column(Boolean, default=False)
    weak_material_flag = Column(Boolean, default=False)
    bad_news_unresolved_flag = Column(Boolean, default=False)
    dilution_risk_flag = Column(Boolean, default=False)

    # 兆候
    t3_signs = Column(Text)
    t2_signs = Column(Text)
    t1_signs = Column(Text)
    entry_condition = Column(Text)
    stop_condition = Column(Text)
    take_profit_condition = Column(Text)
    avoid_condition = Column(Text)
    failure_warnings = Column(Text)
    risk_reward = Column(String)

    tags = Column(JSON)
    nlm_data_raw = Column(Text)

    # ラベル
    is_positive_case = Column(Boolean, default=False)
    is_negative_case = Column(Boolean, default=False)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AAROHLCVSnapshot(Base):
    __tablename__ = "aar_ohlcv_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, index=True)
    symbol = Column(String, index=True)
    date = Column(String, index=True)
    relative_day = Column(String, index=True)  # T-60, T-3, T-2, T-1, T0, T+1, T+5, T+20
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    price_change_pct = Column(Float)
    volume_ratio_20d = Column(Float)
    ma5 = Column(Float)
    ma25 = Column(Float)
    ma75 = Column(Float)
    ma200 = Column(Float)
    ma25_deviation = Column(Float)
    support_line = Column(Float)
    resistance_line = Column(Float)
    resistance_upside = Column(Float)
    support_distance = Column(Float)
    candle_state = Column(String)
    created_at = Column(DateTime, server_default=func.now())


class AARFeatureVector(Base):
    __tablename__ = "aar_feature_vectors"
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, index=True)
    symbol = Column(String, index=True)
    move_date = Column(String, index=True)
    feature_asof_date = Column(String, index=True)  # T-1 date

    # T-1のスナップショット
    t1_close = Column(Float)
    t1_volume = Column(Float)
    t1_volume_ratio_20d = Column(Float)
    t2_volume_ratio_20d = Column(Float)
    t3_volume_ratio_20d = Column(Float)
    t1_price_change_1d = Column(Float)
    t1_price_change_3d = Column(Float)
    t1_price_change_5d = Column(Float)
    t1_price_change_20d = Column(Float)
    t1_ma5_deviation = Column(Float)
    t1_ma25_deviation = Column(Float)
    t1_support_distance = Column(Float)
    t1_resistance_upside = Column(Float)
    t1_range_break_flag = Column(Boolean)
    t1_high_close_flag = Column(Boolean)
    t1_lower_shadow_flag = Column(Boolean)
    t1_upper_shadow_flag = Column(Boolean)
    t1_gap_risk = Column(Float)
    t1_overextension_score = Column(Float)

    # T-1の材料判定
    t1_fresh_material_flag = Column(Boolean)
    t1_known_event_flag = Column(Boolean)
    t1_unknown_material_flag = Column(Boolean)
    t1_stale_material_flag = Column(Boolean)
    t1_bad_news_risk_flag = Column(Boolean)
    t1_dilution_risk_flag = Column(Boolean)
    t1_earnings_cross_flag = Column(Boolean)
    t1_theme_tailwind_flag = Column(Boolean)

    # ラベル (T0以降, 検証用)
    t0_result_move_percent = Column(Float)
    t1_to_t5_max_gain = Column(Float)
    t1_to_t20_max_gain = Column(Float)
    t1_to_t20_max_drawdown = Column(Float)
    hit_20_percent = Column(Boolean)

    created_at = Column(DateTime, server_default=func.now())


class PatternLibrary(Base):
    __tablename__ = "pattern_library"
    id = Column(Integer, primary_key=True, index=True)
    pattern_name = Column(String, unique=True, index=True)
    pattern_category = Column(String, index=True)
    description = Column(Text)
    required_conditions = Column(JSON)
    positive_conditions = Column(JSON)
    negative_conditions = Column(JSON)
    exclusion_conditions = Column(JSON)
    example_symbols = Column(JSON)
    confidence_weight = Column(Float, default=1.0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CurrentPredictionMatch(Base):
    __tablename__ = "current_prediction_matches"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    screening_date = Column(String, index=True)
    matched_pattern_id = Column(Integer)
    similarity_score = Column(Float)
    matched_cases = Column(JSON)
    matched_conditions = Column(JSON)
    missing_conditions = Column(JSON)
    contradiction_conditions = Column(JSON)
    t1_entry_possible_estimate = Column(String)
    prediction_label = Column(String, index=True)
    entry_timing_type = Column(String)
    final_prediction_score = Column(Float)
    reason_summary = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class UniverseSourceFile(Base):
    __tablename__ = "universe_source_files"
    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, index=True)
    source_url = Column(Text)
    file_name = Column(String)
    row_count = Column(Integer, default=0)
    fetched_at = Column(DateTime, server_default=func.now())
    checksum = Column(String)
    file_creation_time = Column(String)
    status = Column(String)
    error_message = Column(Text)


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
