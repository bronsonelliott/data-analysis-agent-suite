"""File discovery utilities for pipeline resumption.

This module provides functions to:
- Validate input files
- Find existing outputs for a source file
- Discover resumable pipeline state from previous runs
"""

import os
import re
from glob import glob
from typing import Any, Dict, List, Optional, Tuple

from src.output_files import sort_newest_first

from .pipeline import PipelineStage, PipelineState


# Supported input file extensions
SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

# Output file patterns for each stage
# Pattern: {source_name}_{stage_suffix}_{timestamp}.{ext}
OUTPUT_PATTERNS = {
    PipelineStage.CLEANING: "{source}_cleaned_*.csv",
    PipelineStage.ANALYSIS: "{source}_analysis_*.json",
    PipelineStage.VISUALIZATION: "{source}_visualizations_*",
    PipelineStage.REPORT: "{source}_report_*.md",
    PipelineStage.SUMMARY: "{source}_executive_summary_*.md",
}

# Additional output patterns (secondary outputs)
SECONDARY_PATTERNS = {
    "analysis_md": "{source}_analysis_*.md",
}


def validate_input_file(file_path: str) -> Dict[str, Any]:
    """Validate that an input file exists and is a supported format.

    Args:
        file_path: Path to the input file

    Returns:
        Dictionary with validation results:
        - valid: bool indicating if file is valid
        - error: error message if invalid, None if valid
        - file_path: absolute path to the file
        - file_name: base name of the file
        - file_size: size in bytes
        - extension: file extension (lowercase)
    """
    result: Dict[str, Any] = {
        "valid": False,
        "error": None,
        "file_path": None,
        "file_name": None,
        "file_size": None,
        "extension": None,
    }

    # Convert to absolute path
    abs_path = os.path.abspath(file_path)
    result["file_path"] = abs_path

    # Check if file exists
    if not os.path.exists(abs_path):
        result["error"] = f"File not found: {abs_path}"
        return result

    # Check if it's a file (not directory)
    if not os.path.isfile(abs_path):
        result["error"] = f"Path is not a file: {abs_path}"
        return result

    # Get file info
    result["file_name"] = os.path.basename(abs_path)
    result["file_size"] = os.path.getsize(abs_path)

    # Check extension
    _, ext = os.path.splitext(abs_path)
    ext = ext.lower()
    result["extension"] = ext

    if ext not in SUPPORTED_EXTENSIONS:
        result["error"] = (
            f"Unsupported file format: {ext}. "
            f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
        return result

    # Check if file is empty
    if result["file_size"] == 0:
        result["error"] = "File is empty"
        return result

    result["valid"] = True
    return result


def get_source_name(file_path: str) -> str:
    """Extract the source name from a file path.

    The source name is the base name without extension, used for
    matching output files.

    Args:
        file_path: Path to the file

    Returns:
        Source name (e.g., 'sales_data' from '/path/to/sales_data.csv')
    """
    basename = os.path.basename(file_path)
    name, _ = os.path.splitext(basename)
    return name


def _extract_timestamp(filename: str, source_name: str) -> Optional[str]:
    """Extract timestamp from an output filename.

    Args:
        filename: Output filename
        source_name: Source file name (for pattern matching)

    Returns:
        Timestamp string or None if not found
    """
    # Pattern: {source}_{stage_suffix}_{timestamp}.{ext}
    # Timestamp format: YYYYMMDD_HHMMSS
    pattern = rf"^{re.escape(source_name)}_\w+_(\d{{8}}_\d{{6}})"
    match = re.search(pattern, filename)
    if match:
        return match.group(1)
    return None


def find_outputs_for_source(
    source_name: str,
    output_dir: str,
    timestamp: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Find existing output files for a source file.

    Args:
        source_name: Base name of the source file (without extension)
        output_dir: Directory to search for outputs
        timestamp: Optional specific timestamp to match

    Returns:
        Dictionary mapping output types to file paths (None if not found)
    """
    results: Dict[str, Optional[str]] = {
        "cleaned_csv": None,
        "analysis_json": None,
        "analysis_md": None,
        "visualization_dir": None,
        "report": None,
        "summary": None,
    }

    if not os.path.isdir(output_dir):
        return results

    # Map result keys to stages/patterns
    stage_to_key = {
        PipelineStage.CLEANING: "cleaned_csv",
        PipelineStage.ANALYSIS: "analysis_json",
        PipelineStage.VISUALIZATION: "visualization_dir",
        PipelineStage.REPORT: "report",
        PipelineStage.SUMMARY: "summary",
    }

    # Search for each stage's output
    for stage, key in stage_to_key.items():
        pattern = OUTPUT_PATTERNS[stage].format(source=source_name)
        full_pattern = os.path.join(output_dir, pattern)
        matches = glob(full_pattern)

        if matches:
            # Filter by timestamp if specified
            if timestamp:
                matches = [m for m in matches if timestamp in m]

            if matches:
                results[key] = sort_newest_first(matches)[0]

    # Search for secondary outputs (analysis markdown)
    for key, pattern in SECONDARY_PATTERNS.items():
        full_pattern = os.path.join(output_dir, pattern.format(source=source_name))
        matches = glob(full_pattern)
        if matches:
            if timestamp:
                matches = [m for m in matches if timestamp in m]
            if matches:
                results[key] = sort_newest_first(matches)[0]

    return results


def find_latest_outputs_for_source(
    source_name: str,
    output_dir: str,
) -> Tuple[Dict[str, Optional[str]], Optional[str]]:
    """Find the latest outputs for a source file.

    This function finds all outputs that share the same timestamp,
    representing a single pipeline run.

    Args:
        source_name: Base name of the source file
        output_dir: Directory to search

    Returns:
        Tuple of (outputs dict, timestamp) where outputs maps
        output types to file paths
    """
    if not os.path.isdir(output_dir):
        return {}, None

    # Find all cleaned files to get timestamps
    pattern = OUTPUT_PATTERNS[PipelineStage.CLEANING].format(source=source_name)
    full_pattern = os.path.join(output_dir, pattern)
    cleaned_files = glob(full_pattern)

    if not cleaned_files:
        # No previous runs found
        return find_outputs_for_source(source_name, output_dir), None

    # The newest cleaned file (by filename timestamp) identifies the latest run
    timestamps = [
        _extract_timestamp(os.path.basename(f), source_name)
        for f in sort_newest_first(cleaned_files)
    ]
    timestamps = [ts for ts in timestamps if ts]

    if not timestamps:
        return find_outputs_for_source(source_name, output_dir), None

    latest_ts = timestamps[0]

    # Find all outputs with this timestamp
    outputs = find_outputs_for_source(source_name, output_dir, timestamp=latest_ts)
    return outputs, latest_ts


def discover_resumable_state(
    source_file: str,
    output_dir: str,
) -> Dict[str, Any]:
    """Discover resumable pipeline state from previous runs.

    Examines existing output files to determine which stages have
    been completed and from which stage execution can resume.

    Args:
        source_file: Path to the source data file
        output_dir: Directory containing outputs

    Returns:
        Dictionary with:
        - can_resume: bool indicating if resumption is possible
        - timestamp: timestamp of the previous run
        - completed_stages: list of completed stage names
        - resume_from: suggested stage to resume from
        - outputs: dict of existing output paths
        - state: PipelineState if resumable, None otherwise
    """
    result: Dict[str, Any] = {
        "can_resume": False,
        "timestamp": None,
        "completed_stages": [],
        "resume_from": None,
        "outputs": {},
        "state": None,
    }

    source_name = get_source_name(source_file)
    outputs, timestamp = find_latest_outputs_for_source(source_name, output_dir)

    if not timestamp:
        return result

    result["timestamp"] = timestamp
    result["outputs"] = outputs

    # Determine completed stages based on existing outputs
    completed: List[str] = []

    cleaned_csv = outputs.get("cleaned_csv")
    if cleaned_csv is not None and os.path.exists(cleaned_csv):
        completed.append(PipelineStage.CLEANING.value)

    analysis_json = outputs.get("analysis_json")
    if analysis_json is not None and os.path.exists(analysis_json):
        completed.append(PipelineStage.ANALYSIS.value)

    viz_dir = outputs.get("visualization_dir")
    if viz_dir is not None and os.path.isdir(viz_dir):
        completed.append(PipelineStage.VISUALIZATION.value)

    report = outputs.get("report")
    if report is not None and os.path.exists(report):
        completed.append(PipelineStage.REPORT.value)

    summary = outputs.get("summary")
    if summary is not None and os.path.exists(summary):
        completed.append(PipelineStage.SUMMARY.value)

    result["completed_stages"] = completed

    if not completed:
        return result

    # Resume from the first stage with no output. A later stage's file
    # existing doesn't mean the earlier ones ran in this pipeline run.
    for stage in PipelineStage.get_order():
        if stage.value not in completed:
            result["resume_from"] = stage
            result["can_resume"] = True
            break

    # Build pipeline state
    state = PipelineState(
        source_file=source_file,
        timestamp=timestamp,
        cleaned_csv_path=outputs.get("cleaned_csv"),
        analysis_json_path=outputs.get("analysis_json"),
        analysis_md_path=outputs.get("analysis_md"),
        visualization_dir=outputs.get("visualization_dir"),
        report_path=outputs.get("report"),
        summary_path=outputs.get("summary"),
        completed_stages=completed,
    )
    result["state"] = state

    return result


def get_output_path(
    source_name: str,
    stage: PipelineStage,
    timestamp: str,
    output_dir: str,
) -> str:
    """Generate the expected output path for a stage.

    Args:
        source_name: Base name of the source file
        stage: Pipeline stage
        timestamp: Execution timestamp
        output_dir: Output directory

    Returns:
        Full path to the expected output file/directory
    """
    # Define output filenames for each stage
    filenames = {
        PipelineStage.CLEANING: f"{source_name}_cleaned_{timestamp}.csv",
        PipelineStage.ANALYSIS: f"{source_name}_analysis_{timestamp}.json",
        PipelineStage.VISUALIZATION: f"{source_name}_visualizations_{timestamp}",
        PipelineStage.REPORT: f"{source_name}_report_{timestamp}.md",
        PipelineStage.SUMMARY: f"{source_name}_executive_summary_{timestamp}.md",
    }

    filename = filenames.get(stage)
    if not filename:
        raise ValueError(f"Unknown stage: {stage}")

    return os.path.join(output_dir, filename)


def ensure_output_dir(output_dir: str) -> str:
    """Ensure the output directory exists.

    Args:
        output_dir: Path to output directory

    Returns:
        Absolute path to the output directory
    """
    abs_path = os.path.abspath(output_dir)
    os.makedirs(abs_path, exist_ok=True)
    return abs_path
