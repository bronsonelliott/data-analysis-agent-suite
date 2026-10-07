"""Data loading utilities for report generation.

This module provides functions to load analysis results from JSON files
and visualization manifests from the @data-visualizer agent output.
"""

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from pathlib import Path

from src.output_files import sort_newest_first
from src.analysis import (
    AnalysisResult,
    AnalysisFinding,
    DescriptiveStats,
    Correlation,
    TrendAnalysis,
    SegmentComparison,
)
from src.visualization import (
    ChartManifest,
    ChartManifestEntry,
)


# =============================================================================
# REPORT INPUT DATACLASS
# =============================================================================

@dataclass
class ReportInput:
    """All inputs needed to generate a report."""

    source_file: str  # Original data file path
    analysis_result: AnalysisResult  # From @data-analyzer
    visualization_manifest: Optional[ChartManifest] = None  # From @data-visualizer
    audience: str = "business"  # Target audience
    context: str = ""  # Additional context from user
    emphasis_areas: List[str] = field(default_factory=list)  # Columns/topics to emphasize

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'source_file': self.source_file,
            'analysis_result': self.analysis_result.to_dict(),
            'visualization_manifest': (
                self.visualization_manifest.to_dict()
                if self.visualization_manifest else None
            ),
            'audience': self.audience,
            'context': self.context,
            'emphasis_areas': self.emphasis_areas,
        }

    @property
    def has_visualizations(self) -> bool:
        """Check if visualizations are available."""
        return (
            self.visualization_manifest is not None
            and len(self.visualization_manifest.charts) > 0
        )

    @property
    def finding_count(self) -> int:
        """Total number of findings."""
        return len(self.analysis_result.findings)

    @property
    def chart_count(self) -> int:
        """Total number of charts."""
        if self.visualization_manifest:
            return len(self.visualization_manifest.charts)
        return 0


# =============================================================================
# ANALYSIS RESULT LOADING
# =============================================================================

def load_analysis_result(filepath: str) -> AnalysisResult:
    """
    Load an AnalysisResult from a JSON file.

    Args:
        filepath: Path to the analysis JSON file

    Returns:
        Reconstructed AnalysisResult object

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON format is invalid
    """
    path = Path(filepath)

    if not path.exists():
        raise FileNotFoundError(f"Analysis file not found: {filepath}")

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return _reconstruct_analysis_result(data)


def _reconstruct_analysis_result(data: Dict[str, Any]) -> AnalysisResult:
    """
    Reconstruct an AnalysisResult from dictionary data.

    Args:
        data: Dictionary from JSON file

    Returns:
        AnalysisResult object
    """
    # Reconstruct findings
    findings = [
        _reconstruct_finding(f)
        for f in data.get('findings', [])
    ]

    # Reconstruct descriptive stats
    descriptive_stats = {}
    for col_name, stats_dict in data.get('descriptive_stats', {}).items():
        descriptive_stats[col_name] = _reconstruct_descriptive_stats(stats_dict)

    # Reconstruct correlations
    correlations = [
        _reconstruct_correlation(c)
        for c in data.get('correlations', [])
    ]

    # Reconstruct trends
    trends = [
        _reconstruct_trend(t)
        for t in data.get('trends', [])
    ]

    # Reconstruct segments
    segments = [
        _reconstruct_segment(s)
        for s in data.get('segments', [])
    ]

    return AnalysisResult(
        findings=findings,
        descriptive_stats=descriptive_stats,
        correlations=correlations,
        trends=trends,
        segments=segments,
        depth_level=data.get('depth_level', 'standard'),
        columns_analyzed=data.get('columns_analyzed', 0),
        rows_analyzed=data.get('rows_analyzed', 0),
    )


def _reconstruct_finding(data: Dict[str, Any]) -> AnalysisFinding:
    """Reconstruct an AnalysisFinding from dictionary data."""
    return AnalysisFinding(
        category=data.get('category', 'unknown'),
        title=data.get('title', 'Untitled Finding'),
        description=data.get('description', ''),
        affected_columns=data.get('affected_columns', []),
        importance=data.get('importance', 'low'),
        confidence=data.get('confidence', 0.5),
        actionable=data.get('actionable', False),
        recommendation=data.get('recommendation'),
        supporting_data=data.get('supporting_data', {}),
    )


def _reconstruct_descriptive_stats(data: Dict[str, Any]) -> DescriptiveStats:
    """Reconstruct a DescriptiveStats from dictionary data."""
    return DescriptiveStats(
        column=data.get('column', 'unknown'),
        count=data.get('count', 0),
        missing_count=data.get('missing_count', 0),
        mean=data.get('mean', 0.0),
        median=data.get('median', 0.0),
        std=data.get('std', 0.0),
        min=data.get('min', 0.0),
        max=data.get('max', 0.0),
        q25=data.get('q25', 0.0),
        q75=data.get('q75', 0.0),
        skewness=data.get('skewness', 0.0),
        kurtosis=data.get('kurtosis', 0.0),
    )


def _reconstruct_correlation(data: Dict[str, Any]) -> Correlation:
    """Reconstruct a Correlation from dictionary data."""
    return Correlation(
        column1=data.get('column1', ''),
        column2=data.get('column2', ''),
        coefficient=data.get('coefficient', 0.0),
        method=data.get('method', 'pearson'),
        strength=data.get('strength', 'none'),
        direction=data.get('direction', 'positive'),
        p_value=data.get('p_value'),
        is_significant=data.get('is_significant', True),
    )


def _reconstruct_trend(data: Dict[str, Any]) -> TrendAnalysis:
    """Reconstruct a TrendAnalysis from dictionary data."""
    return TrendAnalysis(
        column=data.get('column', ''),
        date_column=data.get('date_column', ''),
        trend_direction=data.get('trend_direction', 'stable'),
        slope=data.get('slope', 0.0),
        r_squared=data.get('r_squared', 0.0),
        growth_rate_pct=data.get('growth_rate_pct'),
        seasonality_detected=data.get('seasonality_detected', False),
        seasonal_period=data.get('seasonal_period'),
        period=data.get('period'),
        aggregation=data.get('aggregation'),
    )


def _reconstruct_segment(data: Dict[str, Any]) -> SegmentComparison:
    """Reconstruct a SegmentComparison from dictionary data."""
    return SegmentComparison(
        segment_column=data.get('segment_column', ''),
        metric_column=data.get('metric_column', ''),
        segments=data.get('segments', {}),
        variance_ratio=data.get('variance_ratio', 0.0),
        notable_differences=data.get('notable_differences', []),
    )


# =============================================================================
# VISUALIZATION MANIFEST LOADING
# =============================================================================

def load_visualization_manifest(filepath: str) -> Optional[ChartManifest]:
    """
    Load a ChartManifest from a JSON file.

    Args:
        filepath: Path to the chart_manifest.json file

    Returns:
        ChartManifest object, or None if file doesn't exist

    Raises:
        ValueError: If JSON format is invalid
    """
    path = Path(filepath)

    if not path.exists():
        return None

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return _reconstruct_chart_manifest(data, str(path.parent))


def _reconstruct_chart_manifest(data: Dict[str, Any], base_dir: str) -> ChartManifest:
    """
    Reconstruct a ChartManifest from dictionary data.

    Args:
        data: Dictionary from JSON file
        base_dir: Base directory for resolving relative paths

    Returns:
        ChartManifest object
    """
    charts = [
        ChartManifestEntry(
            id=c.get('id', ''),
            chart_type=c.get('chart_type', ''),
            title=c.get('title', ''),
            filename=c.get('filename', ''),
            columns_used=c.get('columns_used', []),
            description=c.get('description', ''),
            generated_at=c.get('generated_at', ''),
        )
        for c in data.get('charts', [])
    ]

    return ChartManifest(
        source_file=data.get('source_file', ''),
        generated_at=data.get('generated_at', ''),
        output_dir=data.get('output_dir', base_dir),
        dashboard_file=data.get('dashboard_file', 'index.html'),
        charts=charts,
        version=data.get('version', '1.0'),
    )


# =============================================================================
# DISCOVERY FUNCTIONS
# =============================================================================

def find_analysis_files(directory: str) -> List[str]:
    """
    Find all analysis JSON files in a directory.

    Args:
        directory: Directory to search

    Returns:
        List of file paths matching *_analysis_*.json pattern
    """
    path = Path(directory)
    if not path.exists():
        return []

    # Look for analysis JSON files
    return sort_newest_first(list(path.glob("*_analysis_*.json")))


def find_visualization_manifest(directory: str) -> Optional[str]:
    """
    Find a visualization manifest in a directory or subdirectory.

    Args:
        directory: Directory to search

    Returns:
        Path to chart_manifest.json if found, else None
    """
    path = Path(directory)
    if not path.exists():
        return None

    # Check direct path
    direct = path / 'chart_manifest.json'
    if direct.exists():
        return str(direct)

    # Search visualization directories, newest first
    for viz_dir in sort_newest_first(list(path.glob("*_visualizations_*"))):
        manifest = Path(viz_dir) / 'chart_manifest.json'
        if manifest.exists():
            return str(manifest)

    # Fall back to any subdirectory with a manifest
    for subdir in sorted(path.iterdir()):
        if subdir.is_dir():
            manifest = subdir / 'chart_manifest.json'
            if manifest.exists():
                return str(manifest)

    return None


# =============================================================================
# MAIN CREATION FUNCTION
# =============================================================================

def create_report_input(
    analysis_path: str,
    viz_path: Optional[str] = None,
    audience: str = "business",
    context: str = "",
    emphasis_areas: Optional[List[str]] = None,
) -> ReportInput:
    """
    Create a ReportInput from file paths.

    This is the main entry point for loading all inputs needed for report generation.

    Args:
        analysis_path: Path to analysis JSON file
        viz_path: Optional path to visualization manifest or directory
        audience: Target audience ('technical', 'business', 'executive')
        context: Additional context for the report
        emphasis_areas: Columns or topics to emphasize

    Returns:
        ReportInput object ready for report generation

    Raises:
        FileNotFoundError: If analysis file doesn't exist
        ValueError: If analysis file is invalid
    """
    # Load analysis result
    analysis_result = load_analysis_result(analysis_path)

    # Determine source file from analysis metadata or path
    analysis_data_path = Path(analysis_path)
    source_file = analysis_data_path.stem.replace('_analysis_', '_').split('_')[0]

    # Try to get source from metadata if available
    try:
        with open(analysis_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if 'metadata' in data and 'source_file' in data['metadata']:
                source_file = data['metadata']['source_file']
    except (json.JSONDecodeError, KeyError):
        pass

    # Load visualization manifest if path provided
    viz_manifest = None
    if viz_path:
        viz_path_obj = Path(viz_path)
        if viz_path_obj.is_dir():
            # It's a directory, look for manifest inside
            manifest_file = viz_path_obj / 'chart_manifest.json'
            if manifest_file.exists():
                viz_manifest = load_visualization_manifest(str(manifest_file))
        elif viz_path_obj.exists():
            # It's a file
            viz_manifest = load_visualization_manifest(viz_path)

    return ReportInput(
        source_file=source_file,
        analysis_result=analysis_result,
        visualization_manifest=viz_manifest,
        audience=audience,
        context=context,
        emphasis_areas=emphasis_areas or [],
    )
