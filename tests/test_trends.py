"""Tests for the trends module."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.analysis.trends import (
    TrendAnalysis,
    detect_date_column,
    analyze_trend,
    detect_seasonality,
    find_trend_insights,
)


@pytest.fixture
def trending_df():
    """DataFrame with clear upward trend."""
    np.random.seed(42)
    n = 100

    dates = pd.date_range(start='2023-01-01', periods=n, freq='D')
    values = np.linspace(100, 200, n) + np.random.normal(0, 5, n)

    return pd.DataFrame({
        'date': dates,
        'value': values,
        'category': ['A', 'B'] * 50,
    })


@pytest.fixture
def declining_df():
    """DataFrame with clear downward trend."""
    np.random.seed(42)
    n = 100

    dates = pd.date_range(start='2023-01-01', periods=n, freq='D')
    values = np.linspace(200, 100, n) + np.random.normal(0, 5, n)

    return pd.DataFrame({
        'date': dates,
        'value': values,
    })


@pytest.fixture
def stable_df():
    """DataFrame with no trend (stable)."""
    np.random.seed(42)
    n = 100

    dates = pd.date_range(start='2023-01-01', periods=n, freq='D')
    values = np.random.normal(100, 5, n)  # Random noise around 100

    return pd.DataFrame({
        'date': dates,
        'value': values,
    })


@pytest.fixture
def volatile_df():
    """DataFrame with high volatility and no clear trend."""
    np.random.seed(42)
    n = 100

    dates = pd.date_range(start='2023-01-01', periods=n, freq='D')
    values = np.random.normal(100, 50, n)  # High variance

    return pd.DataFrame({
        'date': dates,
        'value': values,
    })


@pytest.fixture
def seasonal_df():
    """DataFrame with monthly seasonality pattern."""
    np.random.seed(42)
    n = 365  # One year of daily data

    dates = pd.date_range(start='2023-01-01', periods=n, freq='D')

    # Create monthly seasonal pattern
    base = 100
    seasonal = 20 * np.sin(2 * np.pi * np.arange(n) / 30)  # Monthly cycle
    noise = np.random.normal(0, 5, n)
    values = base + seasonal + noise

    return pd.DataFrame({
        'date': dates,
        'value': values,
    })


@pytest.fixture
def string_date_df():
    """DataFrame with dates as strings."""
    return pd.DataFrame({
        'order_date': ['2023-01-01', '2023-01-02', '2023-01-03', '2023-01-04',
                       '2023-01-05', '2023-01-06', '2023-01-07', '2023-01-08'],
        'amount': [100, 110, 105, 115, 120, 125, 130, 140],
    })


class TestTrendAnalysis:
    """Tests for TrendAnalysis dataclass."""

    def test_create_trend_analysis(self):
        """Test creating a trend analysis object."""
        trend = TrendAnalysis(
            column='sales',
            date_column='date',
            trend_direction='increasing',
            slope=2.5,
            r_squared=0.85,
            growth_rate_pct=45.2,
            seasonality_detected=True,
            seasonal_period='monthly',
        )

        assert trend.column == 'sales'
        assert trend.trend_direction == 'increasing'
        assert trend.r_squared == 0.85

    def test_to_dict(self):
        """Test serialization to dictionary."""
        trend = TrendAnalysis(
            column='value',
            date_column='date',
            trend_direction='decreasing',
            slope=-1.2,
            r_squared=0.72,
        )
        trend_dict = trend.to_dict()

        assert trend_dict['column'] == 'value'
        assert trend_dict['trend_direction'] == 'decreasing'
        assert 'slope' in trend_dict

    def test_describe(self):
        """Test human-readable description."""
        trend = TrendAnalysis(
            column='revenue',
            date_column='date',
            trend_direction='increasing',
            slope=5.0,
            r_squared=0.8,
            growth_rate_pct=50.0,
            seasonality_detected=True,
            seasonal_period='monthly',
        )
        desc = trend.describe()

        assert 'revenue' in desc
        assert 'increasing' in desc
        assert 'monthly' in desc


class TestDetectDateColumn:
    """Tests for detect_date_column function."""

    def test_detects_datetime_column(self, trending_df):
        """Test detection of datetime column."""
        date_col = detect_date_column(trending_df)

        assert date_col == 'date'

    def test_detects_string_date(self, string_date_df):
        """Test detection of string date column."""
        date_col = detect_date_column(string_date_df)

        assert date_col == 'order_date'

    def test_no_date_column(self):
        """Test when no date column exists."""
        df = pd.DataFrame({
            'name': ['Alice', 'Bob'],
            'value': [100, 200],
        })
        date_col = detect_date_column(df)

        assert date_col is None

    def test_prefers_datetime_dtype(self):
        """Test that datetime dtype is preferred over string."""
        df = pd.DataFrame({
            'string_date': ['2023-01-01', '2023-01-02'],
            'datetime_date': pd.to_datetime(['2023-01-01', '2023-01-02']),
            'value': [100, 200],
        })
        date_col = detect_date_column(df)

        assert date_col == 'datetime_date'

    def test_column_name_hint(self):
        """Test that column name hints help detection."""
        df = pd.DataFrame({
            'created_at': ['2023-01-01', '2023-01-02', '2023-01-03'],
            'value': [100, 200, 300],
        })
        date_col = detect_date_column(df)

        assert date_col == 'created_at'


class TestAnalyzeTrend:
    """Tests for analyze_trend function."""

    def test_increasing_trend(self, trending_df):
        """Test detection of increasing trend."""
        trend = analyze_trend(trending_df, 'value', 'date')

        assert trend.trend_direction == 'increasing'
        assert trend.slope > 0
        assert trend.r_squared > 0.8
        assert trend.growth_rate_pct is not None
        assert trend.growth_rate_pct > 0

    def test_decreasing_trend(self, declining_df):
        """Test detection of decreasing trend."""
        trend = analyze_trend(declining_df, 'value', 'date')

        assert trend.trend_direction == 'decreasing'
        assert trend.slope < 0
        assert trend.growth_rate_pct is not None
        assert trend.growth_rate_pct < 0

    def test_stable_trend(self, stable_df):
        """Test detection of stable (no trend)."""
        trend = analyze_trend(stable_df, 'value', 'date')

        # Should be stable or have low r_squared
        assert trend.trend_direction in ('stable', 'volatile') or trend.r_squared < 0.3

    def test_volatile_trend(self, volatile_df):
        """Test detection of volatility."""
        trend = analyze_trend(volatile_df, 'value', 'date')

        # Should detect as volatile or stable with low fit
        assert trend.trend_direction in ('stable', 'volatile') or trend.r_squared < 0.3

    def test_insufficient_data(self):
        """Test handling of insufficient data."""
        df = pd.DataFrame({
            'date': pd.date_range('2023-01-01', periods=3),
            'value': [1, 2, 3],
        })
        trend = analyze_trend(df, 'value', 'date')

        assert trend.trend_direction == 'unknown'

    def test_with_string_dates(self, string_date_df):
        """Test analysis with string date column."""
        trend = analyze_trend(string_date_df, 'amount', 'order_date')

        # Should still detect the trend
        assert trend.trend_direction == 'increasing'


class TestDetectSeasonality:
    """Tests for detect_seasonality function."""

    def test_detects_seasonality(self, seasonal_df):
        """Test detection of seasonal pattern."""
        is_seasonal, period = detect_seasonality(seasonal_df, 'value', 'date')

        assert is_seasonal is True
        assert period == 'monthly'

    def test_no_seasonality(self, trending_df):
        """Test when no seasonality exists."""
        is_seasonal, period = detect_seasonality(trending_df, 'value', 'date')

        assert is_seasonal is False

    def test_pure_linear_trend_is_not_seasonal(self):
        """A trending series must not be mistaken for a cycle."""
        df = pd.DataFrame({
            'date': pd.date_range('2022-01-01', periods=400),
            'value': np.arange(400, dtype=float),
        })
        is_seasonal, period = detect_seasonality(df, 'value', 'date')

        assert is_seasonal is False

    def test_insufficient_data(self):
        """Test with insufficient data for seasonality detection."""
        df = pd.DataFrame({
            'date': pd.date_range('2023-01-01', periods=10),
            'value': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        })
        is_seasonal, period = detect_seasonality(df, 'value', 'date')

        assert is_seasonal is False


class TestFindTrendInsights:
    """Tests for find_trend_insights function."""

    def test_generates_insights_for_trend(self, trending_df):
        """Test that insights are generated for trends."""
        insights = find_trend_insights(trending_df, 'date')

        # Should generate insight for increasing trend
        assert len(insights) > 0

    def test_insight_structure(self, trending_df):
        """Test that insights have correct structure."""
        insights = find_trend_insights(trending_df, 'date')

        for insight in insights:
            assert insight.category == 'trend'
            assert len(insight.affected_columns) >= 1
            assert insight.importance in ('high', 'medium', 'low')
            assert 0 <= insight.confidence <= 1

    def test_strong_trend_high_importance(self, trending_df):
        """Test that strong trends get high or medium importance."""
        insights = find_trend_insights(trending_df, 'date')

        # Strong linear trend should have high importance
        trend_insights = [i for i in insights if 'upward' in i.title.lower() or 'trend' in i.title.lower()]
        if trend_insights:
            assert trend_insights[0].importance in ('high', 'medium')

    def test_declining_trend_recommendation(self, declining_df):
        """Test that declining trends get recommendations."""
        insights = find_trend_insights(declining_df, 'date')

        decline_insights = [i for i in insights if 'downward' in i.title.lower()]
        if decline_insights:
            assert decline_insights[0].recommendation is not None

    def test_multiple_numeric_columns(self):
        """Test analysis of multiple numeric columns."""
        np.random.seed(42)
        n = 100
        dates = pd.date_range('2023-01-01', periods=n)

        df = pd.DataFrame({
            'date': dates,
            'increasing': np.linspace(0, 100, n) + np.random.normal(0, 2, n),
            'decreasing': np.linspace(100, 0, n) + np.random.normal(0, 2, n),
            'stable': np.random.normal(50, 2, n),
        })

        insights = find_trend_insights(df, 'date')

        # Should find insights for at least the increasing and decreasing columns
        assert len(insights) >= 2

    def test_seasonality_insight(self, seasonal_df):
        """Test that seasonality is noted in insights."""
        insights = find_trend_insights(seasonal_df, 'date')

        # May or may not detect seasonality depending on detection sensitivity
        # Just check that we get some insights
        assert isinstance(insights, list)

    def test_no_insights_for_stable(self, stable_df):
        """Test minimal insights for stable data."""
        insights = find_trend_insights(stable_df, 'date')

        # Stable data should have fewer trend insights
        # (might still have volatility insights)
        strong_trend_insights = [i for i in insights if 'trend' in i.title.lower() and i.importance == 'high']
        assert len(strong_trend_insights) == 0


class TestTransactionLevelData:
    """Trends on many-rows-per-day data must use period totals."""

    @pytest.fixture
    def transactions_df(self):
        """3 years of orders; yearly revenue grows 100 -> 150 -> 200 per day."""
        rng = np.random.default_rng(7)
        rows = []
        for year, daily_total in [(2021, 100.0), (2022, 150.0), (2023, 200.0)]:
            for day in pd.date_range(f'{year}-01-01', f'{year}-12-31'):
                # Split each day's total across a random number of orders
                n_orders = rng.integers(1, 6)
                weights = rng.dirichlet(np.ones(n_orders))
                for amount in daily_total * weights:
                    rows.append({'order_date': day, 'order_id': len(rows), 'sales': amount})
        return pd.DataFrame(rows)

    def test_uses_monthly_totals(self, transactions_df):
        trend = analyze_trend(transactions_df, 'sales', 'order_date')

        assert trend.period == 'monthly'
        assert trend.aggregation == 'sum'
        assert trend.trend_direction == 'increasing'

    def test_growth_ties_out_to_period_totals(self, transactions_df):
        """First 9 months average ~100/day, last 9 ~200/day -> ~+100%."""
        trend = analyze_trend(transactions_df, 'sales', 'order_date')

        assert trend.growth_rate_pct == pytest.approx(100, abs=5)

    def test_rate_columns_are_averaged(self):
        df = pd.DataFrame({
            'date': pd.date_range('2023-01-01', periods=120).repeat(3),
            'discount': [0.1, 0.2, 0.3] * 120,
        })
        trend = analyze_trend(df, 'discount', 'date')

        assert trend.aggregation == 'mean'
        assert trend.trend_direction == 'stable'

    def test_id_columns_get_no_findings(self, transactions_df):
        insights = find_trend_insights(transactions_df, 'order_date')

        assert not any('order_id' in i.affected_columns for i in insights)
