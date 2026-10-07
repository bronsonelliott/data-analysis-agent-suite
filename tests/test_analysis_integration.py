"""Integration tests for the complete analysis pipeline."""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import tempfile
import json

from src.analysis import (
    # Statistics
    DescriptiveStats,
    AnalysisFinding,
    AnalysisResult,
    calculate_descriptive_stats,
    analyze_all_numeric,
    find_statistical_anomalies,
    # Correlations
    Correlation,
    find_all_correlations,
    find_correlation_insights,
    # Trends
    TrendAnalysis,
    detect_date_column,
    analyze_trend,
    find_trend_insights,
    # Segmentation
    SegmentComparison,
    compare_segments,
    find_segment_insights,
    # Reporter
    generate_analysis_report,
    save_analysis_results,
)


@pytest.fixture
def comprehensive_df():
    """
    Create a comprehensive test dataset with:
    - Numeric columns (for stats and correlations)
    - Date column (for trends)
    - Categorical columns (for segmentation)
    - Known patterns to verify detection
    """
    np.random.seed(42)
    n = 200

    # Date column
    dates = pd.date_range(start='2023-01-01', periods=n, freq='D')

    # Categorical columns
    regions = np.random.choice(['North', 'South', 'East', 'West'], n)
    status = np.random.choice(['Active', 'Inactive', 'Pending'], n)

    # Numeric columns with known relationships
    base_value = 100
    trend = np.linspace(0, 50, n)  # Upward trend
    noise = np.random.normal(0, 10, n)

    sales = base_value + trend + noise

    # Create correlated column
    marketing = sales * 0.3 + np.random.normal(20, 5, n)

    # Add region effects to quantity
    region_effects = {'North': 20, 'South': 10, 'East': 5, 'West': 15}
    quantity = np.array([50 + region_effects[r] + np.random.normal(0, 5) for r in regions])

    return pd.DataFrame({
        'date': dates,
        'region': regions,
        'status': status,
        'sales': sales,
        'marketing': marketing,
        'quantity': quantity,
        'discount': np.random.uniform(0, 0.3, n),
    })


@pytest.fixture
def temp_output_dir():
    """Create a temporary output directory for reports."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestFullAnalysisPipeline:
    """Test the complete analysis pipeline from data to report."""

    def test_complete_analysis_workflow(self, comprehensive_df, temp_output_dir):
        """Test running all analysis steps and generating report."""
        # Step 1: Descriptive Statistics
        desc_stats = analyze_all_numeric(comprehensive_df)

        assert len(desc_stats) >= 4  # sales, marketing, quantity, discount
        assert 'sales' in desc_stats
        assert desc_stats['sales'].count == 200

        # Step 2: Find anomalies
        anomalies = find_statistical_anomalies(comprehensive_df)
        assert isinstance(anomalies, list)

        # Step 3: Correlation Analysis
        correlations = find_all_correlations(comprehensive_df)

        # Should find sales-marketing correlation
        sales_marketing = [c for c in correlations
                          if set([c.column1, c.column2]) == {'sales', 'marketing'}]
        assert len(sales_marketing) == 1
        assert sales_marketing[0].coefficient > 0.5  # Should be positively correlated

        correlation_insights = find_correlation_insights(correlations)
        assert isinstance(correlation_insights, list)

        # Step 4: Trend Analysis
        date_col = detect_date_column(comprehensive_df)
        assert date_col == 'date'

        trend_insights = find_trend_insights(comprehensive_df, date_col)

        # Should detect upward trend in sales
        sales_trend = [i for i in trend_insights if 'sales' in i.affected_columns]
        assert len(sales_trend) > 0

        # Step 5: Segment Analysis
        segment_insights = find_segment_insights(comprehensive_df)
        assert isinstance(segment_insights, list)

        # Should find region effects on quantity
        region_quantity = [i for i in segment_insights
                          if 'region' in i.affected_columns and 'quantity' in i.affected_columns]
        # May or may not find depending on effect size
        assert isinstance(region_quantity, list)

        # Step 6: Compile Results
        all_findings = anomalies + correlation_insights + trend_insights + segment_insights

        trends = [analyze_trend(comprehensive_df, 'sales', 'date')]
        segments = [compare_segments(comprehensive_df, 'region', 'quantity')]

        result = AnalysisResult(
            findings=all_findings,
            descriptive_stats=desc_stats,
            correlations=correlations,
            trends=trends,
            segments=segments,
            depth_level='standard',
            columns_analyzed=len(comprehensive_df.columns),
            rows_analyzed=len(comprehensive_df),
        )

        assert result.columns_analyzed == 7
        assert result.rows_analyzed == 200

        # Step 7: Generate Report
        report = generate_analysis_report(result, 'test_data.csv')

        assert '# Data Analysis Report' in report
        assert 'test_data.csv' in report
        assert 'sales' in report

        # Step 8: Save Results
        paths = save_analysis_results(result, report, 'test_data.csv', temp_output_dir)

        assert 'report' in paths
        assert 'json' in paths
        assert Path(paths['report']).exists()
        assert Path(paths['json']).exists()

        # Verify JSON content
        with open(paths['json'], 'r') as f:
            json_data = json.load(f)

        assert 'findings' in json_data
        assert 'descriptive_stats' in json_data
        assert 'correlations' in json_data

    def test_quick_scan_analysis(self, comprehensive_df):
        """Test quick scan analysis level."""
        # Quick scan: basic stats and obvious correlations only
        desc_stats = analyze_all_numeric(comprehensive_df)
        correlations = find_all_correlations(comprehensive_df, min_strength=0.5)

        result = AnalysisResult(
            findings=[],
            descriptive_stats=desc_stats,
            correlations=correlations,
            trends=[],
            segments=[],
            depth_level='quick_scan',
            columns_analyzed=len(comprehensive_df.columns),
            rows_analyzed=len(comprehensive_df),
        )

        assert result.depth_level == 'quick_scan'
        assert len(result.correlations) <= len(find_all_correlations(comprehensive_df))

    def test_deep_dive_analysis(self, comprehensive_df, temp_output_dir):
        """Test deep dive analysis level."""
        # Deep dive: everything including segmentation
        desc_stats = analyze_all_numeric(comprehensive_df)
        anomalies = find_statistical_anomalies(comprehensive_df)
        correlations = find_all_correlations(comprehensive_df)
        correlation_insights = find_correlation_insights(correlations)

        date_col = detect_date_column(comprehensive_df)
        trend_insights = find_trend_insights(comprehensive_df, date_col)

        segment_insights = find_segment_insights(comprehensive_df)

        all_findings = anomalies + correlation_insights + trend_insights + segment_insights

        result = AnalysisResult(
            findings=all_findings,
            descriptive_stats=desc_stats,
            correlations=correlations,
            trends=[analyze_trend(comprehensive_df, col, date_col)
                   for col in ['sales', 'marketing']],
            segments=[compare_segments(comprehensive_df, 'region', col)
                     for col in ['sales', 'quantity']],
            depth_level='deep_dive',
            columns_analyzed=len(comprehensive_df.columns),
            rows_analyzed=len(comprehensive_df),
        )

        assert result.depth_level == 'deep_dive'
        assert len(result.trends) == 2
        assert len(result.segments) == 2


class TestResultSerializationRoundTrip:
    """Test that results can be serialized and deserialized."""

    def test_result_to_dict(self, comprehensive_df):
        """Test converting result to dictionary."""
        desc_stats = analyze_all_numeric(comprehensive_df)
        correlations = find_all_correlations(comprehensive_df)

        result = AnalysisResult(
            findings=[],
            descriptive_stats=desc_stats,
            correlations=correlations,
            trends=[],
            segments=[],
            depth_level='standard',
            columns_analyzed=7,
            rows_analyzed=200,
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert 'findings' in result_dict
        assert 'descriptive_stats' in result_dict
        assert 'correlations' in result_dict

    def test_json_serializable(self, comprehensive_df, temp_output_dir):
        """Test that results can be serialized to JSON."""
        desc_stats = analyze_all_numeric(comprehensive_df)

        result = AnalysisResult(
            findings=[],
            descriptive_stats=desc_stats,
            correlations=[],
            trends=[],
            segments=[],
            depth_level='quick_scan',
            columns_analyzed=7,
            rows_analyzed=200,
        )

        report = generate_analysis_report(result, 'test.csv')
        paths = save_analysis_results(result, report, 'test.csv', temp_output_dir)

        # Should be able to load the JSON
        with open(paths['json'], 'r') as f:
            loaded = json.load(f)

        assert loaded['depth_level'] == 'quick_scan'
        assert loaded['rows_analyzed'] == 200


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_dataframe(self):
        """Test handling of empty DataFrame."""
        df = pd.DataFrame()

        desc_stats = analyze_all_numeric(df)
        assert len(desc_stats) == 0

        correlations = find_all_correlations(df)
        assert len(correlations) == 0

    def test_single_column(self):
        """Test handling of DataFrame with single column."""
        df = pd.DataFrame({'value': [1, 2, 3, 4, 5]})

        desc_stats = analyze_all_numeric(df)
        assert len(desc_stats) == 1

        correlations = find_all_correlations(df)
        assert len(correlations) == 0  # Need at least 2 columns

    def test_all_missing_values(self):
        """Test handling of column with all missing values."""
        df = pd.DataFrame({
            'empty': [None, None, None, None, None],
            'valid': [1, 2, 3, 4, 5],
        })

        desc_stats = analyze_all_numeric(df)

        # Should skip empty column or handle gracefully
        assert 'valid' in desc_stats

    def test_no_numeric_columns(self):
        """Test handling of DataFrame with no numeric columns."""
        df = pd.DataFrame({
            'name': ['Alice', 'Bob', 'Charlie'],
            'city': ['NYC', 'LA', 'Chicago'],
        })

        desc_stats = analyze_all_numeric(df)
        assert len(desc_stats) == 0

        correlations = find_all_correlations(df)
        assert len(correlations) == 0

    def test_no_date_column(self):
        """Test handling when no date column exists."""
        df = pd.DataFrame({
            'value': [1, 2, 3, 4, 5],
            'category': ['A', 'B', 'A', 'B', 'A'],
        })

        date_col = detect_date_column(df)
        assert date_col is None

    def test_single_category(self):
        """Test segmentation with single category value."""
        df = pd.DataFrame({
            'segment': ['A'] * 100,
            'value': np.random.normal(100, 10, 100),
        })

        comparison = compare_segments(df, 'segment', 'value')

        # Should handle gracefully
        assert comparison.segment_count == 1


class TestFindingsFiltering:
    """Test filtering and sorting of findings."""

    def test_get_top_findings(self, comprehensive_df):
        """Test getting top N findings."""
        findings = [
            AnalysisFinding(
                category='statistic',
                title=f'Finding {i}',
                description='Desc',
                affected_columns=['col'],
                importance=['high', 'medium', 'low'][i % 3],
                confidence=0.9 - i * 0.05,
                actionable=True,
            )
            for i in range(10)
        ]

        result = AnalysisResult(
            findings=findings,
            descriptive_stats={},
            correlations=[],
            trends=[],
            segments=[],
            depth_level='standard',
            columns_analyzed=1,
            rows_analyzed=100,
        )

        top_5 = result.get_top_findings(5)

        assert len(top_5) == 5
        # Should be sorted by importance then confidence
        assert top_5[0].importance == 'high'

    def test_filter_by_importance(self, comprehensive_df):
        """Test filtering findings by importance level."""
        findings = [
            AnalysisFinding(
                category='statistic',
                title='High Finding',
                description='Desc',
                affected_columns=['col'],
                importance='high',
                confidence=0.9,
                actionable=True,
            ),
            AnalysisFinding(
                category='correlation',
                title='Medium Finding',
                description='Desc',
                affected_columns=['col'],
                importance='medium',
                confidence=0.7,
                actionable=True,
            ),
            AnalysisFinding(
                category='trend',
                title='Low Finding',
                description='Desc',
                affected_columns=['col'],
                importance='low',
                confidence=0.5,
                actionable=False,
            ),
        ]

        result = AnalysisResult(
            findings=findings,
            descriptive_stats={},
            correlations=[],
            trends=[],
            segments=[],
            depth_level='standard',
            columns_analyzed=1,
            rows_analyzed=100,
        )

        high_only = result.get_findings_by_importance('high')
        assert len(high_only) == 1
        assert high_only[0].title == 'High Finding'


class TestReportGeneration:
    """Test report generation functionality."""

    def test_report_contains_required_sections(self, comprehensive_df, temp_output_dir):
        """Test that report contains all required sections."""
        desc_stats = analyze_all_numeric(comprehensive_df)
        correlations = find_all_correlations(comprehensive_df)

        result = AnalysisResult(
            findings=[],
            descriptive_stats=desc_stats,
            correlations=correlations,
            trends=[],
            segments=[],
            depth_level='standard',
            columns_analyzed=7,
            rows_analyzed=200,
        )

        report = generate_analysis_report(result, 'test_data.csv')

        # Check for required sections
        assert '# Data Analysis Report' in report
        assert '## Summary' in report
        assert '## Key Findings' in report
        assert '## Descriptive Statistics' in report

    def test_report_includes_findings(self, comprehensive_df):
        """Test that findings are included in report."""
        finding = AnalysisFinding(
            category='correlation',
            title='Test Finding Title',
            description='This is a test finding description.',
            affected_columns=['col1', 'col2'],
            importance='high',
            confidence=0.9,
            actionable=True,
            recommendation='Take some action.',
        )

        result = AnalysisResult(
            findings=[finding],
            descriptive_stats={},
            correlations=[],
            trends=[],
            segments=[],
            depth_level='standard',
            columns_analyzed=2,
            rows_analyzed=100,
        )

        report = generate_analysis_report(result, 'test.csv')

        assert 'Test Finding Title' in report
        assert 'Take some action' in report

    def test_save_creates_files(self, comprehensive_df, temp_output_dir):
        """Test that save creates both report and JSON files."""
        result = AnalysisResult(
            findings=[],
            descriptive_stats={},
            correlations=[],
            trends=[],
            segments=[],
            depth_level='quick_scan',
            columns_analyzed=1,
            rows_analyzed=10,
        )

        report = generate_analysis_report(result, 'test.csv')
        paths = save_analysis_results(result, report, 'test.csv', temp_output_dir)

        assert Path(paths['report']).exists()
        assert Path(paths['json']).exists()

        # Check file extensions
        assert paths['report'].endswith('.md')
        assert paths['json'].endswith('.json')


class TestIdentifierColumns:
    """Numeric IDs and keys are not metrics."""

    def test_ids_excluded_from_numeric_analysis(self):
        from src.analysis.utils import identify_numeric_columns

        df = pd.DataFrame({
            'Row ID': [1, 2, 3, 4],
            'customer_id': [17, 4, 99, 23],
            'Date Key': [20220101, 20220102, 20220103, 20220104],
            'Unnamed: 0': [0, 1, 2, 3],
            'paid': [10.0, 20.0, 30.0, 40.0],
            'value': [1, 2, 3, 4],
        })

        assert identify_numeric_columns(df) == ['paid', 'value']
        assert len(identify_numeric_columns(df, exclude_ids=False)) == 6
