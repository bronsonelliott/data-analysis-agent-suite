"""Data loading utilities for executive summary generation.

This module provides functions to load analysis results from JSON files,
markdown reports, and visualization manifests for summary generation.
"""

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from pathlib import Path

from src.analysis import AnalysisResult
from src.reporting.loader import (
    load_analysis_result as load_analysis_json,
    load_visualization_manifest,
)
from src.output_files import sort_newest_first


# =============================================================================
# SUMMARY INPUT DATACLASS
# =============================================================================

@dataclass
class SummaryInput:
    """All inputs needed to generate an executive summary."""

    source_file: str  # Original data file path
    report_content: Optional[str] = None  # Full report markdown
    analysis_result: Optional[AnalysisResult] = None  # From @data-analyzer
    visualization_manifest: Optional[Dict[str, Any]] = None  # Chart info
    context: str = ""  # Additional context from user
    emphasis_areas: List[str] = field(default_factory=list)  # Topics to emphasize

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'source_file': self.source_file,
            'has_report': self.has_report,
            'has_analysis': self.has_analysis,
            'finding_count': self.finding_count,
            'context': self.context,
            'emphasis_areas': self.emphasis_areas,
        }

    @property
    def has_report(self) -> bool:
        """Check if a report is available."""
        return self.report_content is not None and len(self.report_content) > 0

    @property
    def has_analysis(self) -> bool:
        """Check if analysis results are available."""
        return self.analysis_result is not None

    @property
    def finding_count(self) -> int:
        """Total number of findings from analysis."""
        if self.analysis_result:
            return len(self.analysis_result.findings)
        return 0

    @property
    def has_visualizations(self) -> bool:
        """Check if visualizations are available."""
        if self.visualization_manifest:
            charts = self.visualization_manifest.get('charts', [])
            return len(charts) > 0
        return False

    @property
    def chart_count(self) -> int:
        """Total number of charts available."""
        if self.visualization_manifest:
            return len(self.visualization_manifest.get('charts', []))
        return 0


# =============================================================================
# REPORT LOADING
# =============================================================================

def load_report(report_path: str) -> str:
    """
    Load a markdown report from file.

    Args:
        report_path: Path to the markdown report file

    Returns:
        Report content as string

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    path = Path(report_path)

    if not path.exists():
        raise FileNotFoundError(f"Report file not found: {report_path}")

    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def load_analysis_result(analysis_path: str) -> AnalysisResult:
    """
    Load an AnalysisResult from a JSON file.

    Args:
        analysis_path: Path to the analysis JSON file

    Returns:
        Reconstructed AnalysisResult object

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON format is invalid
    """
    # Delegate to reporting loader which has full reconstruction logic
    return load_analysis_json(analysis_path)


# =============================================================================
# DISCOVERY FUNCTIONS
# =============================================================================

def find_report_files(directory: str) -> List[str]:
    """
    Find all report markdown files in a directory.

    Args:
        directory: Directory to search

    Returns:
        List of file paths matching *_report_*.md pattern, newest first
    """
    path = Path(directory)
    if not path.exists():
        return []

    return sort_newest_first(list(path.glob("*_report_*.md")))


def find_latest_report(directory: str) -> Optional[str]:
    """
    Find the most recent report file in a directory.

    Args:
        directory: Directory to search

    Returns:
        Path to most recent report, or None if none found
    """
    reports = find_report_files(directory)
    return reports[0] if reports else None


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

    return sort_newest_first(list(path.glob("*_analysis_*.json")))


def find_latest_analysis(directory: str) -> Optional[str]:
    """
    Find the most recent analysis file in a directory.

    Args:
        directory: Directory to search

    Returns:
        Path to most recent analysis, or None if none found
    """
    analyses = find_analysis_files(directory)
    return analyses[0] if analyses else None


def find_visualization_directory(directory: str) -> Optional[str]:
    """
    Find a visualization directory with charts.

    Args:
        directory: Directory to search

    Returns:
        Path to visualization directory, or None if none found
    """
    path = Path(directory)
    if not path.exists():
        return None

    # Look for visualization directories
    viz_dirs = list(path.glob("*_visualizations_*"))
    for viz_dir in sort_newest_first(viz_dirs):
        manifest = Path(viz_dir) / 'chart_manifest.json'
        if manifest.exists():
            return viz_dir

    return None


# =============================================================================
# MAIN CREATION FUNCTION
# =============================================================================

def create_summary_input(
    report_path: Optional[str] = None,
    analysis_path: Optional[str] = None,
    viz_path: Optional[str] = None,
    context: str = "",
    emphasis_areas: Optional[List[str]] = None,
) -> SummaryInput:
    """
    Create a SummaryInput from file paths.

    This is the main entry point for loading all inputs needed for summary generation.
    At least one of report_path or analysis_path must be provided.

    Args:
        report_path: Path to markdown report file
        analysis_path: Path to analysis JSON file
        viz_path: Optional path to visualization manifest or directory
        context: Additional context for the summary
        emphasis_areas: Topics to emphasize

    Returns:
        SummaryInput object ready for summary generation

    Raises:
        ValueError: If neither report nor analysis path provided
        FileNotFoundError: If specified files don't exist
    """
    if not report_path and not analysis_path:
        raise ValueError("At least one of report_path or analysis_path must be provided")

    # Load report content
    report_content = None
    if report_path:
        report_content = load_report(report_path)

    # Load analysis result
    analysis_result = None
    if analysis_path:
        analysis_result = load_analysis_result(analysis_path)

    # Determine source file
    source_file = ""
    if analysis_path:
        # Try to extract from analysis metadata
        try:
            with open(analysis_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'metadata' in data and 'source_file' in data['metadata']:
                    source_file = data['metadata']['source_file']
        except (json.JSONDecodeError, KeyError):
            pass

        # Fallback to parsing filename
        if not source_file:
            source_file = Path(analysis_path).stem.split('_analysis_')[0]

    elif report_path:
        # Parse from report filename
        source_file = Path(report_path).stem.split('_report_')[0]

    # Load visualization manifest
    viz_manifest = None
    if viz_path:
        viz_path_obj = Path(viz_path)
        if viz_path_obj.is_dir():
            manifest_file = viz_path_obj / 'chart_manifest.json'
            if manifest_file.exists():
                with open(manifest_file, 'r', encoding='utf-8') as f:
                    viz_manifest = json.load(f)
        elif viz_path_obj.exists() and viz_path_obj.suffix == '.json':
            with open(viz_path_obj, 'r', encoding='utf-8') as f:
                viz_manifest = json.load(f)

    return SummaryInput(
        source_file=source_file,
        report_content=report_content,
        analysis_result=analysis_result,
        visualization_manifest=viz_manifest,
        context=context,
        emphasis_areas=emphasis_areas or [],
    )


# =============================================================================
# AUTO-DISCOVERY FUNCTION
# =============================================================================

def auto_discover_inputs(
    directory: str = "./output",
    context: str = "",
    emphasis_areas: Optional[List[str]] = None,
) -> Optional[SummaryInput]:
    """
    Automatically discover and load the latest analysis/report files.

    Args:
        directory: Directory to search (default ./output)
        context: Additional context for the summary
        emphasis_areas: Topics to emphasize

    Returns:
        SummaryInput if files found, None otherwise
    """
    report_path = find_latest_report(directory)
    analysis_path = find_latest_analysis(directory)
    viz_dir = find_visualization_directory(directory)

    if not report_path and not analysis_path:
        return None

    viz_path = None
    if viz_dir:
        viz_path = str(Path(viz_dir) / 'chart_manifest.json')
        if not Path(viz_path).exists():
            viz_path = viz_dir

    return create_summary_input(
        report_path=report_path,
        analysis_path=analysis_path,
        viz_path=viz_path,
        context=context,
        emphasis_areas=emphasis_areas,
    )


# =============================================================================
# REPORT PARSING HELPERS
# =============================================================================

def extract_title_from_report(report_content: str) -> str:
    """
    Extract the title from report markdown content.

    Args:
        report_content: Full markdown content

    Returns:
        Title string or default
    """
    lines = report_content.split('\n')
    for line in lines:
        if line.startswith('# '):
            return line[2:].strip()
    return "Analysis Report"


def extract_date_from_report(report_content: str) -> Optional[str]:
    """
    Extract the generation date from report markdown content.

    Args:
        report_content: Full markdown content

    Returns:
        Date string or None
    """
    lines = report_content.split('\n')
    for line in lines:
        if line.startswith('**Generated:**') or line.startswith('**Date:**'):
            parts = line.split(':', 1)
            if len(parts) > 1:
                return parts[1].strip().rstrip('*').strip()
    return None
