"""Pipeline manifest generation for tracking execution results.

This module provides functionality to create and save pipeline manifests
that document the complete execution of a pipeline run.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.output_files import sort_newest_first

from .pipeline import PipelineConfig, PipelineStage, PipelineState


@dataclass
class PipelineManifest:
    """Complete manifest of a pipeline execution.

    The manifest provides a comprehensive record of:
    - What source file was processed
    - What configuration was used
    - Which stages executed/skipped
    - What outputs were generated
    - How long execution took
    - Whether it succeeded or failed

    Attributes:
        source_file: Path to the original input file
        source_name: Base name of the source file
        timestamp: Execution timestamp
        config: Configuration used for this run
        stages_executed: List of stages that ran
        stages_skipped: List of stages that were skipped
        outputs: Dictionary mapping output types to file paths
        duration_seconds: Total execution time in seconds
        success: Whether the pipeline completed successfully
        error_stage: Stage where error occurred (if failed)
        error_message: Error message (if failed)
        created_at: ISO timestamp when manifest was created
    """
    source_file: str
    source_name: str
    timestamp: str
    config: Dict[str, Any]
    stages_executed: List[str]
    stages_skipped: List[str]
    outputs: Dict[str, Optional[str]]
    duration_seconds: float
    success: bool
    error_stage: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )

    @property
    def output_count(self) -> int:
        """Count of non-None outputs generated.

        Returns:
            Number of output files/directories created
        """
        return sum(1 for v in self.outputs.values() if v is not None)

    @property
    def stage_count(self) -> int:
        """Total number of stages executed.

        Returns:
            Number of stages that ran
        """
        return len(self.stages_executed)

    def get_output_summary(self) -> Dict[str, Optional[str]]:
        """Get a summary of outputs with just filenames.

        Returns:
            Dictionary mapping output types to filenames (not full paths)
        """
        return {
            k: os.path.basename(v) if v else None
            for k, v in self.outputs.items()
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "source_file": self.source_file,
            "source_name": self.source_name,
            "timestamp": self.timestamp,
            "config": self.config,
            "stages_executed": self.stages_executed,
            "stages_skipped": self.stages_skipped,
            "outputs": self.outputs,
            "duration_seconds": round(self.duration_seconds, 2),
            "success": self.success,
            "error_stage": self.error_stage,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "summary": {
                "output_count": self.output_count,
                "stage_count": self.stage_count,
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string.

        Args:
            indent: Indentation level for pretty printing

        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineManifest":
        """Create from dictionary.

        Args:
            data: Dictionary with manifest values

        Returns:
            PipelineManifest instance
        """
        return cls(
            source_file=data["source_file"],
            source_name=data["source_name"],
            timestamp=data["timestamp"],
            config=data["config"],
            stages_executed=data["stages_executed"],
            stages_skipped=data["stages_skipped"],
            outputs=data["outputs"],
            duration_seconds=data["duration_seconds"],
            success=data["success"],
            error_stage=data.get("error_stage"),
            error_message=data.get("error_message"),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "PipelineManifest":
        """Create from JSON string.

        Args:
            json_str: JSON string representation

        Returns:
            PipelineManifest instance
        """
        return cls.from_dict(json.loads(json_str))


def create_pipeline_manifest(
    state: PipelineState,
    config: PipelineConfig,
    start_time: datetime,
    end_time: Optional[datetime] = None,
) -> PipelineManifest:
    """Create a pipeline manifest from execution state.

    Args:
        state: Final pipeline state after execution
        config: Configuration used for the run
        start_time: When execution started
        end_time: When execution ended (defaults to now)

    Returns:
        PipelineManifest documenting the execution
    """
    if end_time is None:
        end_time = datetime.now()

    duration = (end_time - start_time).total_seconds()

    # Determine skipped stages
    all_stages = PipelineStage.get_order()
    executed = set(state.completed_stages)
    skipped = [
        s.value for s in all_stages
        if s.value not in executed and config.should_skip(s)
    ]

    return PipelineManifest(
        source_file=state.source_file,
        source_name=state.source_name,
        timestamp=state.timestamp,
        config=config.to_dict(),
        stages_executed=state.completed_stages.copy(),
        stages_skipped=skipped,
        outputs=state.get_all_outputs(),
        duration_seconds=duration,
        success=not state.is_failed,
        error_stage=state.failed_stage,
        error_message=state.error_message,
    )


def save_pipeline_manifest(
    manifest: PipelineManifest,
    output_dir: str,
) -> str:
    """Save a pipeline manifest to a JSON file.

    The manifest is saved with a filename following the pattern:
    {source_name}_pipeline_manifest_{timestamp}.json

    Args:
        manifest: The manifest to save
        output_dir: Directory to save the manifest

    Returns:
        Path to the saved manifest file
    """
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Generate filename
    filename = f"{manifest.source_name}_pipeline_manifest_{manifest.timestamp}.json"
    file_path = os.path.join(output_dir, filename)

    # Write manifest
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(manifest.to_json())

    return file_path


def load_pipeline_manifest(file_path: str) -> PipelineManifest:
    """Load a pipeline manifest from a JSON file.

    Args:
        file_path: Path to the manifest file

    Returns:
        PipelineManifest instance

    Raises:
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If the file isn't valid JSON
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return PipelineManifest.from_dict(data)


def find_manifests_for_source(
    source_name: str,
    output_dir: str,
) -> List[str]:
    """Find all manifest files for a source.

    Args:
        source_name: Base name of the source file
        output_dir: Directory to search

    Returns:
        List of manifest file paths, newest filename timestamp first
    """
    from glob import glob

    if not os.path.isdir(output_dir):
        return []

    pattern = os.path.join(output_dir, f"{source_name}_pipeline_manifest_*.json")
    matches = glob(pattern)

    return sort_newest_first(matches)


def get_latest_manifest(
    source_name: str,
    output_dir: str,
) -> Optional[PipelineManifest]:
    """Get the most recent manifest for a source.

    Args:
        source_name: Base name of the source file
        output_dir: Directory to search

    Returns:
        Most recent PipelineManifest, or None if none found
    """
    manifests = find_manifests_for_source(source_name, output_dir)
    if not manifests:
        return None
    return load_pipeline_manifest(manifests[0])
