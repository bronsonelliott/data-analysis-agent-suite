"""Time-series trend detection and analysis utilities.

This module provides functions for detecting trends, seasonality,
and growth patterns in time-series data.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import pandas as pd
import numpy as np
from scipy import stats

from .utils import (
    identify_numeric_columns,
    identify_date_columns,
    calculate_confidence_score,
    classify_importance,
    safe_numeric_conversion,
    ColumnType,
    classify_column_type,
)
from .statistics import AnalysisFinding


@dataclass
class TrendAnalysis:
    """Time-based trend analysis for a numeric column."""
    column: str
    date_column: str
    trend_direction: str  # 'increasing', 'decreasing', 'stable', 'volatile'
    slope: float  # Rate of change per unit time
    r_squared: float  # Fit quality (0-1)
    growth_rate_pct: Optional[float] = None  # Percentage change over period
    seasonality_detected: bool = False
    seasonal_period: Optional[str] = None  # 'weekly', 'monthly', 'quarterly', 'yearly'
    period: Optional[str] = None  # Aggregation grain: 'daily', 'weekly', 'monthly'
    aggregation: Optional[str] = None  # How rows were rolled up: 'sum' or 'mean'

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'column': self.column,
            'date_column': self.date_column,
            'trend_direction': self.trend_direction,
            'slope': round(self.slope, 6),
            'r_squared': round(self.r_squared, 4),
            'growth_rate_pct': round(self.growth_rate_pct, 2) if self.growth_rate_pct is not None else None,
            'seasonality_detected': self.seasonality_detected,
            'seasonal_period': self.seasonal_period,
            'period': self.period,
            'aggregation': self.aggregation,
        }

    def describe(self) -> str:
        """Generate a human-readable description of the trend."""
        if self.trend_direction == 'stable':
            return f"'{self.column}' shows no significant trend over time."

        direction = self.trend_direction
        growth = f" ({self.growth_rate_pct:+.1f}%)" if self.growth_rate_pct is not None else ""
        seasonality = f" with {self.seasonal_period} seasonality" if self.seasonality_detected else ""

        return f"'{self.column}' is {direction}{growth}{seasonality}."


def detect_date_column(df: pd.DataFrame) -> Optional[str]:
    """
    Detect the most likely date column for time-series analysis.

    Prioritizes columns by:
    1. Already datetime dtype
    2. Column name contains 'date', 'time', 'timestamp'
    3. Successfully parseable as dates

    Args:
        df: DataFrame to analyze

    Returns:
        Column name of detected date column, or None if not found
    """
    candidates = []

    for col in df.columns:
        series = df[col]
        score = 0

        # Check if already datetime
        if pd.api.types.is_datetime64_any_dtype(series):
            score = 100
        else:
            # Check column name
            name_lower = col.lower()
            if any(kw in name_lower for kw in ['date', 'time', 'timestamp', 'created', 'updated']):
                score += 30

            # Try to parse as datetime
            if classify_column_type(series) == ColumnType.DATE:
                score += 50

        if score > 0:
            candidates.append((col, score))

    if not candidates:
        return None

    # Return the highest scoring candidate
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]


def _ensure_datetime(series: pd.Series) -> pd.Series:
    """
    Convert a series to timezone-naive datetime.

    Timezones are dropped (keeping local wall-clock time) because period
    grouping is timezone-naive; comparing the two raises a TypeError.
    """
    if not pd.api.types.is_datetime64_any_dtype(series):
        series = pd.to_datetime(series, errors='coerce')
    if getattr(series.dt, 'tz', None) is not None:
        series = series.dt.tz_localize(None)
    return series


# Seasonal lags to test, in periods, for each aggregation frequency
_SEASONAL_LAGS = {
    'D': [('weekly', 7), ('monthly', 30)],
    'W': [('monthly', 4), ('quarterly', 13), ('yearly', 52)],
    'M': [('quarterly', 3), ('yearly', 12)],
    'Q': [('yearly', 4)],
    'Y': [],
}

_PERIOD_NAMES = {'D': 'daily', 'W': 'weekly', 'M': 'monthly', 'Q': 'quarterly', 'Y': 'yearly'}

# Periods from finest to coarsest, with the shortest length (in days) each can have
_PERIOD_MIN_DAYS = [('D', 1), ('W', 7), ('M', 28), ('Q', 89), ('Y', 365)]


def _choose_period(days_spanned: int, native_spacing_days: float) -> str:
    """
    Pick an aggregation period.

    Two rules, and the coarser answer wins:
    - Enough points to fit a trend: monthly for 2+ years, weekly for 90+ days,
      otherwise daily.
    - Never finer than the data itself: quarterly figures are grouped by
      quarter, not spread across months with zeros in between.
    """
    if days_spanned >= 730:
        by_span = 'M'
    elif days_spanned >= 90:
        by_span = 'W'
    else:
        by_span = 'D'

    by_spacing = 'D'
    for code, min_days in _PERIOD_MIN_DAYS:
        if native_spacing_days >= min_days * 0.9:
            by_spacing = code

    order = [code for code, _ in _PERIOD_MIN_DAYS]
    return max(by_span, by_spacing, key=order.index)


def _native_spacing_days(dates: pd.Series) -> float:
    """Typical gap between distinct dates, in days (median, so a few gaps don't matter)."""
    distinct = dates.drop_duplicates().sort_values()
    if len(distinct) < 2:
        return 0.0
    return float(distinct.diff().dropna().dt.days.median())


def _is_rate_column(values: pd.Series) -> bool:
    """Values all between 0 and 1 are rates/percentages: average them, don't sum."""
    return bool(values.between(0, 1).all())


def aggregate_by_period(
    df: pd.DataFrame,
    value_col: str,
    date_col: str
) -> tuple:
    """
    Roll a column up to one value per time period.

    Trends must be measured on period totals, not individual rows. On
    transaction data, a regression over raw rows answers "is the typical
    order getting bigger?", not "is the business growing?".

    - Period comes from the date span and the data's own spacing
      (see _choose_period), so it is never finer than how often data is recorded.
    - Values are summed per period, except rate columns (all values 0-1),
      which are averaged.
    - When the data is finer than the period (e.g. daily orders grouped
      by month):
      - periods with no rows at all count as 0 for sums;
      - first/last periods missing more than half their days are dropped,
        so a half month doesn't look like a decline.
    - Periods whose rows all have a missing value are left out, not zeroed.

    Args:
        df: DataFrame containing the data
        value_col: Numeric column to aggregate
        date_col: Date column to group by

    Returns:
        Tuple of (Series indexed by Period, period code 'D'/'W'/'M'/'Q'/'Y',
        aggregation 'sum'/'mean'). The Series is empty if there is no
        usable data.
    """
    temp_df = df[[date_col, value_col]].copy()
    temp_df[date_col] = _ensure_datetime(temp_df[date_col])

    if not pd.api.types.is_numeric_dtype(temp_df[value_col]):
        temp_df[value_col] = safe_numeric_conversion(temp_df[value_col])

    # Keep rows with a missing value for now: they still show the period had activity
    temp_df = temp_df.dropna(subset=[date_col])
    if temp_df[value_col].isna().all():
        return pd.Series(dtype=float), 'D', 'sum'

    dates = temp_df[date_col]
    first_date, last_date = dates.min(), dates.max()
    spacing = _native_spacing_days(dates)
    freq = _choose_period((last_date - first_date).days, spacing)
    aggregation = 'mean' if _is_rate_column(temp_df[value_col].dropna()) else 'sum'

    periods = dates.dt.to_period(freq)
    by_period = temp_df.groupby(periods)[value_col]
    if aggregation == 'sum':
        grouped = by_period.sum(min_count=1)  # all-missing period -> NaN, not 0
    else:
        grouped = by_period.mean()

    full_range = pd.period_range(grouped.index.min(), grouped.index.max(), freq=freq)
    periods_with_rows = grouped.index
    grouped = grouped.reindex(full_range)

    period_min_days = dict(_PERIOD_MIN_DAYS)[freq]
    data_finer_than_period = spacing < period_min_days * 0.9

    if data_finer_than_period:
        # A period with no rows at all had no activity
        if aggregation == 'sum':
            no_rows = ~grouped.index.isin(periods_with_rows)
            grouped[no_rows] = 0.0

        # Drop an end period if the data misses more than half its days
        # (a month that starts on the 4th is fine; one that starts on the 20th isn't)
        if len(grouped) > 2:
            first_period, last_period = grouped.index[0], grouped.index[-1]
            days_in_period = (first_period.end_time.normalize() - first_period.start_time).days + 1
            missing_at_start = (first_date.normalize() - first_period.start_time).days
            missing_at_end = (last_period.end_time.normalize() - last_date.normalize()).days
            if missing_at_start > days_in_period / 2:
                grouped = grouped.iloc[1:]
            if missing_at_end > days_in_period / 2:
                grouped = grouped.iloc[:-1]

    return grouped.dropna().astype(float), freq, aggregation


def analyze_trend(
    df: pd.DataFrame,
    value_col: str,
    date_col: str
) -> TrendAnalysis:
    """
    Analyze the trend of a numeric column over time.

    Rolls the data up to period totals (see aggregate_by_period), then fits
    a linear regression to determine trend direction and strength.

    Args:
        df: DataFrame containing the data
        value_col: Numeric column to analyze
        date_col: Date column to use as time axis

    Returns:
        TrendAnalysis with trend metrics
    """
    series, freq, aggregation = aggregate_by_period(df, value_col, date_col)

    if len(series) < 5:
        return TrendAnalysis(
            column=value_col,
            date_column=date_col,
            trend_direction='unknown',
            slope=0.0,
            r_squared=0.0,
            period=_PERIOD_NAMES[freq],
            aggregation=aggregation,
        )

    # x = days since the first period, so slope stays "change per day"
    starts = series.index.to_timestamp()
    x = (starts - starts[0]).days.to_numpy()
    y = series.to_numpy()

    slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
    r_squared = r_value ** 2

    # Growth: average of the first quarter of periods vs the last quarter.
    # With 4 years of monthly data this is first-12-months vs last-12-months.
    k = max(1, len(y) // 4)
    first_value = y[:k].mean()
    last_value = y[-k:].mean()
    if first_value != 0:
        growth_rate_pct = ((last_value - first_value) / abs(first_value)) * 100
    else:
        growth_rate_pct = None

    # Determine trend direction
    # Consider both slope significance and coefficient of variation
    cv = np.std(y) / np.mean(y) if np.mean(y) != 0 else float('inf')

    # A flat series leaves only rounding noise for the regression to "fit"
    flat = np.std(y) < 1e-9 * max(1.0, abs(np.mean(y)))

    if flat or r_squared < 0.1 or p_value > 0.1:
        # Poor fit - check for volatility
        if cv > 0.5:
            trend_direction = 'volatile'
        else:
            trend_direction = 'stable'
    elif slope > 0:
        trend_direction = 'increasing'
    else:
        trend_direction = 'decreasing'

    seasonality_detected, seasonal_period = _detect_seasonality_in_series(series, freq)

    return TrendAnalysis(
        column=value_col,
        date_column=date_col,
        trend_direction=trend_direction,
        slope=float(slope),
        r_squared=float(r_squared),
        growth_rate_pct=float(growth_rate_pct) if growth_rate_pct is not None else None,
        seasonality_detected=seasonality_detected,
        seasonal_period=seasonal_period,
        period=_PERIOD_NAMES[freq],
        aggregation=aggregation,
    )


def _detect_seasonality_in_series(series: pd.Series, freq: str) -> tuple:
    """
    Check an aggregated series for repeating cycles.

    Removes the linear trend first (otherwise any trending series looks
    "seasonal"), then measures autocorrelation at each candidate lag.
    A lag counts only if the series covers at least two full cycles and
    the autocorrelation clears both 0.3 and the ~95% noise band (2/sqrt(n)).
    The shortest qualifying lag wins, since multiples of a cycle also correlate.

    Args:
        series: One value per period, from aggregate_by_period
        freq: Period code 'D', 'W' or 'M'

    Returns:
        Tuple of (is_seasonal: bool, period: Optional[str])
    """
    values = series.to_numpy(dtype=float)
    n = len(values)
    if n < 8:
        return (False, None)

    # Remove the linear trend
    x = np.arange(n)
    slope, intercept = np.polyfit(x, values, 1)
    residuals = values - (slope * x + intercept)

    # Perfectly linear data leaves only rounding noise, which isn't a cycle
    scale = max(1.0, np.abs(values).mean())
    if np.std(residuals) < 1e-9 * scale:
        return (False, None)

    threshold = max(0.3, 2 / np.sqrt(n))

    # Lags are listed shortest first. Report the shortest one that clears the
    # threshold: a 30-day cycle also correlates at 90 days, but it's monthly.
    for period_name, lag in _SEASONAL_LAGS[freq]:
        if n < 2 * lag:
            continue

        acf_at_lag = np.corrcoef(residuals[:-lag], residuals[lag:])[0, 1]

        if acf_at_lag > threshold:
            return (True, period_name)

    return (False, None)


def detect_seasonality(
    df: pd.DataFrame,
    value_col: str,
    date_col: str
) -> tuple:
    """
    Detect if there is seasonality in the data.

    Aggregates to period totals, removes the trend, and checks
    autocorrelation at weekly/monthly/quarterly/yearly lags as the
    data's time span allows.

    Args:
        df: DataFrame containing the data
        value_col: Numeric column to analyze
        date_col: Date column to use as time axis

    Returns:
        Tuple of (is_seasonal: bool, period: Optional[str])
    """
    series, freq, _ = aggregate_by_period(df, value_col, date_col)
    return _detect_seasonality_in_series(series, freq)


def find_trend_insights(
    df: pd.DataFrame,
    date_col: str
) -> List[AnalysisFinding]:
    """
    Analyze trends for all numeric columns and generate insights.

    Args:
        df: DataFrame to analyze
        date_col: Date column to use as time axis

    Returns:
        List of AnalysisFinding objects with trend insights
    """
    findings = []
    numeric_cols = identify_numeric_columns(df)

    for col in numeric_cols:
        if col == date_col:
            continue

        trend = analyze_trend(df, col, date_col)

        # Skip unknown/insufficient data
        if trend.trend_direction == 'unknown':
            continue

        if trend.trend_direction in ('increasing', 'decreasing'):
            if trend.r_squared >= 0.5:
                # Strong trend
                importance = 'high'
                strength = "strong"
            elif trend.r_squared >= 0.25:
                importance = 'medium'
                strength = "moderate"
            else:
                importance = 'low'
                strength = "weak"

            direction = "upward" if trend.trend_direction == 'increasing' else "downward"
            growth_str = f" ({trend.growth_rate_pct:+.1f}%)" if trend.growth_rate_pct is not None else ""

            title = f"{strength.title()} {direction} trend in {col}"
            description = (
                f"{trend.period.title()} {trend.aggregation} of '{col}' shows a "
                f"{strength} {direction} trend over time{growth_str}. "
                f"The trend explains {trend.r_squared*100:.1f}% of the variation."
            )

            recommendation = None
            if importance == 'high' and trend.trend_direction == 'decreasing':
                recommendation = f"Investigate the cause of declining '{col}' values."
            elif importance == 'high' and trend.trend_direction == 'increasing':
                recommendation = f"Monitor if '{col}' growth is sustainable."

            findings.append(AnalysisFinding(
                category='trend',
                title=title,
                description=description,
                affected_columns=[col, date_col],
                importance=importance,
                confidence=min(0.95, 0.5 + trend.r_squared * 0.5),
                actionable=importance in ('high', 'medium'),
                recommendation=recommendation,
                supporting_data=trend.to_dict(),
            ))

        elif trend.trend_direction == 'volatile':
            # High volatility finding
            findings.append(AnalysisFinding(
                category='trend',
                title=f"High volatility in {col}",
                description=(
                    f"{trend.period.title()} {trend.aggregation} of '{col}' varies a lot "
                    f"without a clear trend. "
                    f"This may indicate instability or seasonal fluctuations."
                ),
                affected_columns=[col, date_col],
                importance='medium',
                confidence=0.7,
                actionable=True,
                recommendation=(
                    f"Consider smoothing techniques or investigate "
                    f"what factors cause '{col}' volatility."
                ),
                supporting_data=trend.to_dict(),
            ))

        # Add seasonality findings
        if trend.seasonality_detected:
            findings.append(AnalysisFinding(
                category='trend',
                title=f"{trend.seasonal_period.title()} seasonality in {col}",
                description=(
                    f"'{col}' shows a {trend.seasonal_period} seasonal pattern. "
                    f"Values tend to repeat in {trend.seasonal_period} cycles."
                ),
                affected_columns=[col, date_col],
                importance='medium',
                confidence=0.7,
                actionable=True,
                recommendation=(
                    f"Account for {trend.seasonal_period} seasonality when "
                    f"forecasting or comparing '{col}' values across different periods."
                ),
                supporting_data={
                    'column': col,
                    'seasonal_period': trend.seasonal_period,
                },
            ))

    return findings
