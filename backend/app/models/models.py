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


class SurgeRankingSnapshot(Base):
    __tablename__ = "surge_ranking_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    ranking_type = Column(String, index=True)  # one_day_gain / three_day_gain / ... / custom_uploaded_ranking
    market = Column(String, index=True)
    snapshot_date = Column(String, index=True)
    source_name = Column(String)
    source_url = Column(Text)
    auto_generated = Column(Boolean, default=True)
    imported_by_user = Column(Boolean, default=False)
    total_items = Column(Integer, default=0)
    calculation_method = Column(String)
    created_at = Column(DateTime, server_default=func.now())


class SurgeRankingItem(Base):
    __tablename__ = "surge_ranking_items"
    id = Column(Integer, primary_key=True, index=True)
    snapshot_id = Column(Integer, index=True)
    symbol = Column(String, index=True)
    yahoo_symbol = Column(String)
    name = Column(String)
    market = Column(String)
    rank = Column(Integer)
    current_price = Column(Float)
    start_price = Column(Float)
    calculated_gain_percent = Column(Float)
    imported_gain_percent = Column(Float)
    gain_percent_diff = Column(Float)
    gain_amount = Column(Float)
    market_cap = Column(Float)
    volume = Column(Float)
    turnover = Column(Float)
    locked_flag = Column(Boolean, default=False)
    verified_by_ohlcv = Column(Boolean, default=False)
    verification_warning = Column(Text)
    captured_at = Column(String)
    created_at = Column(DateTime, server_default=func.now())


class Surge20Event(Base):
    __tablename__ = "surge_20_events"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    yahoo_symbol = Column(String)
    name = Column(String)
    market = Column(String, index=True)
    event_type = Column(String, index=True)
    # one_day_surge_20 / one_day_intraday_surge_20 / hit_20_within_3d /
    # hit_20_within_5d / hit_20_within_10d / hit_20_within_20d /
    # hit_20_within_1m / continuation_surge / pullback_reentry_surge /
    # late_chase_only
    event_start_date = Column(String, index=True)
    event_end_date = Column(String)
    days_to_hit_20 = Column(Integer)
    start_price = Column(Float)
    max_price = Column(Float)
    hit_20_date = Column(String)
    max_gain_percent = Column(Float)
    max_drawdown_before_hit = Column(Float)
    source_type = Column(String)  # detected_from_ohlcv / auto_generated_ranking / imported_from_ranking
    source_snapshot_id = Column(Integer)
    material_confirmed = Column(Boolean, default=False)
    catalyst_category = Column(String)
    entry_viability_label = Column(String)
    chase_warning = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())


class Surge20PreFeature(Base):
    __tablename__ = "surge_20_pre_features"
    id = Column(Integer, primary_key=True, index=True)
    surge_event_id = Column(Integer, index=True)
    symbol = Column(String, index=True)
    market = Column(String)
    asof_date = Column(String)
    relative_day = Column(String, index=True)  # T-20 / T-10 / T-5 / T-3 / T-1 / T0
    close = Column(Float)
    price_change_1d = Column(Float)
    price_change_3d = Column(Float)
    price_change_5d = Column(Float)
    price_change_10d = Column(Float)
    price_change_20d = Column(Float)
    volume_ratio_5d = Column(Float)
    volume_ratio_20d = Column(Float)
    turnover = Column(Float)
    ma5 = Column(Float)
    ma25 = Column(Float)
    ma75 = Column(Float)
    ma200 = Column(Float)
    ma25_deviation = Column(Float)
    support_line = Column(Float)
    resistance_line = Column(Float)
    support_distance = Column(Float)
    resistance_upside = Column(Float)
    range_position = Column(Float)
    high_close_flag = Column(Boolean, default=False)
    breakout_flag = Column(Boolean, default=False)
    squeeze_flag = Column(Boolean, default=False)
    reaccumulation_flag = Column(Boolean, default=False)
    selling_exhaustion_flag = Column(Boolean, default=False)
    pre_breakout_flag = Column(Boolean, default=False)
    material_confirmed = Column(Boolean, default=False)
    catalyst_category = Column(String)
    catalyst_quality_score = Column(Float)
    theme_score = Column(Float)
    liquidity_score = Column(Float)
    overextension_score = Column(Float)
    entry_viability_score = Column(Float)
    created_at = Column(DateTime, server_default=func.now())


class Surge20Candidate(Base):
    __tablename__ = "surge_20_candidates"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    market = Column(String, index=True)
    name = Column(String)
    candidate_date = Column(String, index=True)
    final_surge_20_score = Column(Float)
    candidate_label = Column(String, index=True)
    prediction_horizon = Column(String, default="within_20d")
    current_price = Column(Float)
    entry_zone_low = Column(Float)
    entry_zone_high = Column(Float)
    stop_loss = Column(Float)
    first_target = Column(Float)
    second_target = Column(Float)
    support_distance = Column(Float)
    resistance_upside = Column(Float)
    positive_similarity = Column(Float)
    negative_similarity = Column(Float)
    similarity_gap = Column(Float)
    overextension_score = Column(Float)
    similar_past_20_events = Column(JSON)
    failure_pattern_similarity = Column(Float)
    reason_summary = Column(Text)
    risk_summary = Column(Text)
    auto_saved_as_prediction = Column(Boolean, default=False)
    prediction_log_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())


class Surge20NegativeCase(Base):
    __tablename__ = "surge_20_negative_cases"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    market = Column(String)
    asof_date = Column(String)
    reason = Column(String, index=True)
    similar_positive_event_id = Column(Integer)
    max_gain_next_20d = Column(Float)
    hit_20_next_20d = Column(Boolean, default=False)
    failure_reason = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id = Column(Integer, primary_key=True, index=True)
    version_name = Column(String, unique=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    training_case_count = Column(Integer, default=0)
    positive_count = Column(Integer, default=0)
    negative_count = Column(Integer, default=0)
    review_count = Column(Integer, default=0)
    weight_config = Column(JSON)
    performance_summary = Column(JSON)
    active = Column(Boolean, default=False, index=True)


class ModelWeightHistory(Base):
    __tablename__ = "model_weight_history"
    id = Column(Integer, primary_key=True, index=True)
    model_version_id = Column(Integer, index=True)
    weight_name = Column(String, index=True)
    old_value = Column(Float)
    new_value = Column(Float)
    reason = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class AutomationJob(Base):
    __tablename__ = "automation_jobs"
    id = Column(Integer, primary_key=True, index=True)
    job_type = Column(String, index=True)
    market = Column(String)
    status = Column(String, index=True)
    trigger_type = Column(String)  # cron / manual / api
    run_key = Column(String)  # 重複防止用 yyyy-mm-dd-job_type-market
    started_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime)
    duration_seconds = Column(Float)
    total_symbols = Column(Integer, default=0)
    processed_symbols = Column(Integer, default=0)
    skipped_symbols = Column(Integer, default=0)
    failed_symbols = Column(Integer, default=0)
    detected_surge_count = Column(Integer, default=0)
    detected_semi_surge_count = Column(Integer, default=0)
    material_found_count = Column(Integer, default=0)
    material_confirmed_count = Column(Integer, default=0)
    positive_cases_created = Column(Integer, default=0)
    semi_positive_cases_created = Column(Integer, default=0)
    negative_cases_created = Column(Integer, default=0)
    aar_cases_created = Column(Integer, default=0)
    predictions_saved = Column(Integer, default=0)
    outcomes_updated = Column(Integer, default=0)
    reviews_created = Column(Integer, default=0)
    training_cases_created = Column(Integer, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AutomationError(Base):
    __tablename__ = "automation_errors"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, index=True)
    symbol = Column(String, index=True)
    market = Column(String)
    step = Column(String)
    error_type = Column(String)
    error_message = Column(Text)
    traceback = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class AutomationLock(Base):
    __tablename__ = "automation_locks"
    id = Column(Integer, primary_key=True, index=True)
    lock_key = Column(String, unique=True, index=True)
    locked_by = Column(String)
    locked_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime)


class AutomationSetting(Base):
    __tablename__ = "automation_settings"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)
    value = Column(Text)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class HistoricalOHLCV(Base):
    __tablename__ = "historical_ohlcv"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    yahoo_symbol = Column(String, index=True)
    market = Column(String, index=True)
    date = Column(String, index=True, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    adjusted_close = Column(Float)
    volume = Column(Float)
    turnover = Column(Float)
    data_source = Column(String)
    fetched_at = Column(DateTime, server_default=func.now())
    is_adjusted = Column(Boolean, default=True)
    corporate_action_flag = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())


class SurgeEvent(Base):
    __tablename__ = "surge_events"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    yahoo_symbol = Column(String)
    name = Column(String)
    market = Column(String, index=True)
    event_date = Column(String, index=True, nullable=False)
    move_percent = Column(Float)
    threshold_type = Column(String, index=True)  # surge_20 / semi_surge_15
    close_t_minus_1 = Column(Float)
    close_t0 = Column(Float)
    volume_t0 = Column(Float)
    volume_ratio_t0 = Column(Float)
    detected_at = Column(DateTime, server_default=func.now())
    source = Column(String)
    is_valid = Column(Boolean, default=True)
    validation_warning = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class TrainingWindow(Base):
    __tablename__ = "training_windows"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    market = Column(String)
    event_date = Column(String, index=True)
    case_type = Column(String, index=True)
    # positive_surge / semi_positive_surge / negative_non_surge /
    # failed_overextended / failed_weak_material / failed_bad_news /
    # failed_material_exhaustion / watch_event
    window_start = Column(String)
    window_end = Column(String)
    t1_date = Column(String)
    t0_date = Column(String)
    max_gain_20d = Column(Float)
    max_drawdown_20d = Column(Float)
    hit_20_percent = Column(Boolean, default=False)
    hit_10_percent = Column(Boolean, default=False)
    stop_loss_like_drawdown = Column(Float)
    created_at = Column(DateTime, server_default=func.now())


class TrainingFeatureVector(Base):
    __tablename__ = "training_feature_vectors"
    id = Column(Integer, primary_key=True, index=True)
    training_window_id = Column(Integer, index=True)
    symbol = Column(String, index=True)
    market = Column(String)
    feature_asof_date = Column(String, index=True)
    case_type = Column(String, index=True)
    # 価格・出来高
    close = Column(Float)
    volume = Column(Float)
    price_change_1d = Column(Float)
    price_change_3d = Column(Float)
    price_change_5d = Column(Float)
    price_change_20d = Column(Float)
    volume_ratio_5d = Column(Float)
    volume_ratio_20d = Column(Float)
    # MA
    ma5 = Column(Float)
    ma25 = Column(Float)
    ma75 = Column(Float)
    ma200 = Column(Float)
    ma25_deviation = Column(Float)
    support_line = Column(Float)
    resistance_line = Column(Float)
    resistance_upside = Column(Float)
    support_distance = Column(Float)
    atr = Column(Float)
    range_position = Column(Float)
    # candle
    candle_state = Column(String)
    high_close_flag = Column(Boolean, default=False)
    low_close_flag = Column(Boolean, default=False)
    upper_shadow_ratio = Column(Float)
    lower_shadow_ratio = Column(Float)
    # 前夜サイン
    range_break_flag = Column(Boolean, default=False)
    squeeze_flag = Column(Boolean, default=False)
    prior_big_volume_flag = Column(Boolean, default=False)
    selling_exhaustion_flag = Column(Boolean, default=False)
    reaccumulation_flag = Column(Boolean, default=False)
    pre_breakout_flag = Column(Boolean, default=False)
    # スコア
    overextension_score = Column(Float)
    chart_volume_score = Column(Float)
    liquidity_score = Column(Float)
    risk_control_score = Column(Float)
    # 材料
    material_known_flag = Column(Boolean, default=False)
    catalyst_category = Column(String)
    catalyst_quality_score = Column(Float)
    catalyst_continuity_score = Column(Float)
    bad_news_flag = Column(Boolean, default=False)
    dilution_risk_flag = Column(Boolean, default=False)
    # ラベル
    label_hit_20_percent = Column(Boolean, default=False)
    label_max_gain_20d = Column(Float)
    label_max_drawdown_20d = Column(Float)
    label_success_class = Column(String, index=True)
    created_at = Column(DateTime, server_default=func.now())


class TrainingBuildJob(Base):
    __tablename__ = "training_build_jobs"
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, index=True)
    job_type = Column(String)
    market_scope = Column(String)
    start_date = Column(String)
    end_date = Column(String)
    total_symbols = Column(Integer, default=0)
    processed_symbols = Column(Integer, default=0)
    fetched_rows = Column(Integer, default=0)
    surge_events_found = Column(Integer, default=0)
    negative_cases_found = Column(Integer, default=0)
    feature_vectors_created = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime)


class TrainingDataQualityReport(Base):
    __tablename__ = "training_data_quality_reports"
    id = Column(Integer, primary_key=True, index=True)
    report_date = Column(String)
    total_feature_vectors = Column(Integer, default=0)
    positive_cases = Column(Integer, default=0)
    negative_cases = Column(Integer, default=0)
    positive_negative_ratio = Column(Float)
    missing_price_count = Column(Integer, default=0)
    stale_price_count = Column(Integer, default=0)
    duplicate_case_count = Column(Integer, default=0)
    suspicious_split_count = Column(Integer, default=0)
    extreme_outlier_count = Column(Integer, default=0)
    leakage_check_pass = Column(Boolean, default=True)
    quality_score = Column(Float)
    warnings = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())


class PredictionLog(Base):
    __tablename__ = "prediction_logs"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    yahoo_symbol = Column(String)
    name = Column(String)
    market = Column(String)
    prediction_date = Column(String, index=True)
    prediction_datetime = Column(DateTime, server_default=func.now())
    current_price_at_prediction = Column(Float)
    jpy_price_at_prediction = Column(Float)
    prediction_label = Column(String, index=True)
    final_prediction_score = Column(Float)
    entry_timing_type = Column(String)
    entry_type = Column(String)
    entry_zone_a_low = Column(Float)
    entry_zone_a_high = Column(Float)
    entry_zone_b_low = Column(Float)
    entry_zone_b_high = Column(Float)
    breakout_trigger_price = Column(Float)
    stop_loss_price = Column(Float)
    take_profit_1 = Column(Float)
    take_profit_2 = Column(Float)
    max_chase_price = Column(Float)
    chase_prohibited = Column(Boolean, default=False)
    catalyst_quality_score = Column(Float)
    catalyst_continuity_score = Column(Float)
    pre_night_signal_score = Column(Float)
    pattern_similarity_score = Column(Float)
    positive_case_similarity = Column(Float)
    negative_case_similarity = Column(Float)
    overextension_risk_score = Column(Float)
    bad_news_vacuum_score = Column(Float)
    material_confirmed = Column(Boolean, default=False)
    catalyst_category = Column(String)
    matched_past_cases = Column(JSON)
    reason_summary = Column(Text)
    avoid_condition = Column(Text)
    data_freshness_status = Column(String)
    chart_state = Column(String)
    volume_cycle_state = Column(String)
    support_line = Column(Float)
    resistance_line = Column(Float)
    ma25_deviation = Column(Float)
    status = Column(String, default="open", index=True)  # open / reviewed / closed
    # 予測タイプ (default: tomorrow_prediction で後方互換)
    prediction_type = Column(String, index=True, default="tomorrow_prediction")
    # tomorrow_prediction / surge_20_prediction / continuation_prediction /
    # pullback_reentry_prediction / one_day_surge_prediction / material_reaction_prediction
    prediction_horizon = Column(String, default="next_day")
    # next_day / within_3d / within_5d / within_10d / within_20d / within_1m
    target_return = Column(Float, default=20.0)  # 目標到達率 (%)
    # watch保存対応
    auto_trade_candidate = Column(Boolean, default=True)
    watch_only = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PredictionOutcome(Base):
    __tablename__ = "prediction_outcomes"
    id = Column(Integer, primary_key=True, index=True)
    prediction_log_id = Column(Integer, index=True)
    symbol = Column(String, index=True)
    prediction_date = Column(String)
    check_date = Column(String)
    trading_days_elapsed = Column(Integer)
    close_price = Column(Float)
    high_price = Column(Float)
    low_price = Column(Float)
    volume = Column(Float)
    return_from_prediction = Column(Float)
    max_gain_so_far = Column(Float)
    max_drawdown_so_far = Column(Float)
    hit_20_percent = Column(Boolean, default=False)
    hit_take_profit_1 = Column(Boolean, default=False)
    hit_take_profit_2 = Column(Boolean, default=False)
    stop_loss_hit = Column(Boolean, default=False)
    invalidation_hit = Column(Boolean, default=False)
    trigger_hit = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())


class PredictionReview(Base):
    __tablename__ = "prediction_reviews"
    id = Column(Integer, primary_key=True, index=True)
    prediction_log_id = Column(Integer, index=True, unique=True)
    symbol = Column(String, index=True)
    prediction_date = Column(String)
    review_date = Column(String)
    success_label = Column(String, index=True)  # 成功/条件付き成功/失敗/見送り正解/追いかけ禁止正解/未判定
    success_score = Column(Float)
    max_gain = Column(Float)
    max_drawdown = Column(Float)
    hit_20_percent = Column(Boolean, default=False)
    stop_loss_hit = Column(Boolean, default=False)
    trigger_hit = Column(Boolean, default=False)
    entry_plan_worked = Column(Boolean, default=False)
    failed_reason_category = Column(String)
    failed_reason_detail = Column(Text)
    ai_review_comment = Column(Text)
    should_save_as_positive_training = Column(Boolean, default=False)
    should_save_as_negative_training = Column(Boolean, default=False)
    saved_as_training = Column(Boolean, default=False)
    saved_aar_case_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PredictionFailurePattern(Base):
    __tablename__ = "prediction_failure_patterns"
    id = Column(Integer, primary_key=True, index=True)
    failure_pattern_name = Column(String, unique=True, index=True)
    description = Column(Text)
    conditions = Column(JSON)
    example_symbols = Column(JSON)
    penalty_weight = Column(Float, default=1.0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ===== Material research =====
class MaterialResearchJob(Base):
    __tablename__ = "material_research_jobs"
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, index=True)
    symbol = Column(String)
    market = Column(String)
    source_scope = Column(String)
    total_sources_checked = Column(Integer, default=0)
    found_count = Column(Integer, default=0)
    confirmed_count = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime)


class MaterialEvent(Base):
    __tablename__ = "material_events"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    yahoo_symbol = Column(String)
    market = Column(String)
    title = Column(Text)
    summary = Column(Text)
    source_url = Column(Text)
    source_type = Column(String)
    source_rank = Column(String)
    published_at = Column(String)
    detected_at = Column(DateTime, server_default=func.now())
    catalyst_category = Column(String, index=True)
    catalyst_timing = Column(String)
    catalyst_quality_score = Column(Float)
    catalyst_continuity_score = Column(Float)
    catalyst_freshness_score = Column(Float)
    catalyst_surprise_score = Column(Float)
    theme_tailwind_score = Column(Float)
    material_confirmed = Column(Boolean, default=False)
    material_text = Column(Text)
    ai_analysis = Column(Text)
    risk_flags = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())


class MaterialSourceCache(Base):
    __tablename__ = "material_source_cache"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    source_url = Column(Text)
    source_type = Column(String)
    fetched_at = Column(DateTime, server_default=func.now())
    content_hash = Column(String)
    title = Column(Text)
    text_excerpt = Column(Text)
    status = Column(String)
    error_message = Column(Text)


# ===== Entry plans =====
class EntryPlan(Base):
    __tablename__ = "entry_plans"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    screening_date = Column(String, index=True)
    entry_type = Column(String)
    entry_zone_a_low = Column(Float)
    entry_zone_a_high = Column(Float)
    entry_zone_b_low = Column(Float)
    entry_zone_b_high = Column(Float)
    entry_zone_c_low = Column(Float)
    entry_zone_c_high = Column(Float)
    breakout_trigger_price = Column(Float)
    reclaim_line = Column(Float)
    pullback_buy_zone_low = Column(Float)
    pullback_buy_zone_high = Column(Float)
    invalidation_price = Column(Float)
    stop_loss_price = Column(Float)
    take_profit_1 = Column(Float)
    take_profit_2 = Column(Float)
    take_profit_3 = Column(Float)
    risk_reward_1 = Column(Float)
    risk_reward_2 = Column(Float)
    max_chase_price = Column(Float)
    chase_prohibited = Column(Boolean, default=False)
    gap_up_warning = Column(Boolean, default=False)
    position_size_hint = Column(String)
    entry_comment = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


# ===== Auto training =====
class AutoTrainingJob(Base):
    __tablename__ = "auto_training_jobs"
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, index=True)
    target_date = Column(String)
    market_scope = Column(String)
    threshold_percent = Column(Float)
    total_universe_count = Column(Integer, default=0)
    surge_detected_count = Column(Integer, default=0)
    analyzed_count = Column(Integer, default=0)
    saved_case_count = Column(Integer, default=0)
    duplicate_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime)


class AutoTrainingResult(Base):
    __tablename__ = "auto_training_results"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, index=True)
    symbol = Column(String, index=True)
    market = Column(String)
    target_date = Column(String)
    move_percent = Column(Float)
    detected_as_surge = Column(Boolean, default=False)
    analyzed = Column(Boolean, default=False)
    saved_to_training = Column(Boolean, default=False)
    duplicate = Column(Boolean, default=False)
    aar_case_id = Column(Integer)
    catalyst_category = Column(String)
    t1_judgement = Column(String)
    prediction_label = Column(String)
    error_message = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


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
