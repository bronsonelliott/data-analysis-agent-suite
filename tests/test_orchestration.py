"""Tests for the orchestration module.

This module tests:
- PipelineStage enum and ordering
- PipelineConfig validation and serialization
- PipelineState tracking and serialization
- File discovery and validation
- Pipeline manifest generation
"""

import json
import os
import tempfile
from datetime import datetime, timedelta

import pytest

from src.orchestration import (
    PipelineStage,
    PipelineConfig,
    PipelineState,
    PipelineManifest,
    validate_input_file,
    get_source_name,
    find_outputs_for_source,
    discover_resumable_state,
    get_output_path,
    ensure_output_dir,
    create_pipeline_manifest,
    save_pipeline_manifest,
    load_pipeline_manifest,
    find_manifests_for_source,
    get_latest_manifest,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def sample_csv(temp_dir):
    """Create a sample CSV file."""
    path = os.path.join(temp_dir, "sample_data.csv")
    with open(path, "w") as f:
        f.write("id,name,value\n1,Alice,100\n2,Bob,200\n")
    return path


@pytest.fixture
def sample_xlsx(temp_dir):
    """Create a sample XLSX file (minimal content)."""
    path = os.path.join(temp_dir, "sample_data.xlsx")
    # Create a minimal file (not valid Excel, but for testing purposes)
    with open(path, "wb") as f:
        f.write(b"PK\x03\x04")  # ZIP magic bytes
    return path


@pytest.fixture
def empty_file(temp_dir):
    """Create an empty file."""
    path = os.path.join(temp_dir, "empty.csv")
    with open(path, "w") as f:
        pass
    return path


@pytest.fixture
def output_dir(temp_dir):
    """Create an output directory."""
    out_dir = os.path.join(temp_dir, "output")
    os.makedirs(out_dir)
    return out_dir


@pytest.fixture
def sample_outputs(output_dir):
    """Create sample output files for discovery tests."""
    timestamp = "20260124_100000"
    source = "sales_data"

    files = {
        "cleaned": f"{source}_cleaned_{timestamp}.csv",
        "analysis_json": f"{source}_analysis_{timestamp}.json",
        "analysis_md": f"{source}_analysis_{timestamp}.md",
        "report": f"{source}_report_{timestamp}.md",
        "summary": f"{source}_executive_summary_{timestamp}.md",
    }

    # Create files
    for key, filename in files.items():
        path = os.path.join(output_dir, filename)
        with open(path, "w") as f:
            f.write(f"# {key} content")
        files[key] = path

    # Create visualization directory
    viz_dir = os.path.join(output_dir, f"{source}_visualizations_{timestamp}")
    os.makedirs(viz_dir)
    with open(os.path.join(viz_dir, "index.html"), "w") as f:
        f.write("<html></html>")
    files["viz_dir"] = viz_dir

    return {
        "timestamp": timestamp,
        "source": source,
        "files": files,
        "output_dir": output_dir,
    }


@pytest.fixture
def basic_config():
    """Create a basic pipeline configuration."""
    return PipelineConfig()


@pytest.fixture
def basic_state(sample_csv):
    """Create a basic pipeline state."""
    return PipelineState(source_file=sample_csv)


# =============================================================================
# PipelineStage Tests
# =============================================================================


class TestPipelineStage:
    """Tests for PipelineStage enum."""

    def test_all_stages_defined(self):
        """All expected stages are defined."""
        expected = {"cleaning", "analysis", "visualization", "report", "summary"}
        actual = {s.value for s in PipelineStage}
        assert actual == expected

    def test_get_order_returns_correct_sequence(self):
        """get_order returns stages in execution order."""
        order = PipelineStage.get_order()
        assert len(order) == 5
        assert order[0] == PipelineStage.CLEANING
        assert order[1] == PipelineStage.ANALYSIS
        assert order[2] == PipelineStage.VISUALIZATION
        assert order[3] == PipelineStage.REPORT
        assert order[4] == PipelineStage.SUMMARY

    def test_get_index_returns_correct_position(self):
        """get_index returns correct zero-based position."""
        assert PipelineStage.CLEANING.get_index() == 0
        assert PipelineStage.ANALYSIS.get_index() == 1
        assert PipelineStage.VISUALIZATION.get_index() == 2
        assert PipelineStage.REPORT.get_index() == 3
        assert PipelineStage.SUMMARY.get_index() == 4

    def test_from_string_with_exact_values(self):
        """from_string works with exact enum values."""
        assert PipelineStage.from_string("cleaning") == PipelineStage.CLEANING
        assert PipelineStage.from_string("analysis") == PipelineStage.ANALYSIS
        assert PipelineStage.from_string("visualization") == PipelineStage.VISUALIZATION
        assert PipelineStage.from_string("report") == PipelineStage.REPORT
        assert PipelineStage.from_string("summary") == PipelineStage.SUMMARY

    def test_from_string_with_aliases(self):
        """from_string works with common aliases."""
        assert PipelineStage.from_string("cleaned") == PipelineStage.CLEANING
        assert PipelineStage.from_string("clean") == PipelineStage.CLEANING
        assert PipelineStage.from_string("analyzed") == PipelineStage.ANALYSIS
        assert PipelineStage.from_string("viz") == PipelineStage.VISUALIZATION
        assert PipelineStage.from_string("reported") == PipelineStage.REPORT
        assert PipelineStage.from_string("summarized") == PipelineStage.SUMMARY

    def test_from_string_case_insensitive(self):
        """from_string is case insensitive."""
        assert PipelineStage.from_string("CLEANING") == PipelineStage.CLEANING
        assert PipelineStage.from_string("Analysis") == PipelineStage.ANALYSIS
        assert PipelineStage.from_string("  report  ") == PipelineStage.REPORT

    def test_from_string_invalid_raises_error(self):
        """from_string raises ValueError for invalid input."""
        with pytest.raises(ValueError, match="Unknown pipeline stage"):
            PipelineStage.from_string("invalid")

    def test_is_critical_for_required_stages(self):
        """is_critical returns True for cleaning and analysis."""
        assert PipelineStage.CLEANING.is_critical() is True
        assert PipelineStage.ANALYSIS.is_critical() is True

    def test_is_critical_for_optional_stages(self):
        """is_critical returns False for optional stages."""
        assert PipelineStage.VISUALIZATION.is_critical() is False
        assert PipelineStage.REPORT.is_critical() is False
        assert PipelineStage.SUMMARY.is_critical() is False


# =============================================================================
# PipelineConfig Tests
# =============================================================================


class TestPipelineConfig:
    """Tests for PipelineConfig dataclass."""

    def test_default_values(self):
        """Default configuration has expected values."""
        config = PipelineConfig()
        assert config.skip_stages == []
        assert config.writing_style == "business"
        assert config.analysis_depth == "standard"
        assert config.resume_from is None
        assert config.output_dir == "./output"

    def test_custom_values(self):
        """Configuration accepts custom values."""
        config = PipelineConfig(
            skip_stages=[PipelineStage.VISUALIZATION],
            writing_style="executive",
            analysis_depth="deep_dive",
            resume_from=PipelineStage.ANALYSIS,
            output_dir="/custom/output",
        )
        assert config.skip_stages == [PipelineStage.VISUALIZATION]
        assert config.writing_style == "executive"
        assert config.analysis_depth == "deep_dive"
        assert config.resume_from == PipelineStage.ANALYSIS
        assert config.output_dir == "/custom/output"

    def test_invalid_writing_style_raises_error(self):
        """Invalid writing_style raises ValueError."""
        with pytest.raises(ValueError, match="Invalid writing_style"):
            PipelineConfig(writing_style="informal")

    def test_invalid_analysis_depth_raises_error(self):
        """Invalid analysis_depth raises ValueError."""
        with pytest.raises(ValueError, match="Invalid analysis_depth"):
            PipelineConfig(analysis_depth="superficial")

    def test_valid_writing_styles(self):
        """All valid writing styles are accepted."""
        for style in ("technical", "business", "executive"):
            config = PipelineConfig(writing_style=style)
            assert config.writing_style == style

    def test_valid_analysis_depths(self):
        """All valid analysis depths are accepted."""
        for depth in ("quick_scan", "standard", "deep_dive"):
            config = PipelineConfig(analysis_depth=depth)
            assert config.analysis_depth == depth

    def test_should_skip_returns_true_for_skipped(self):
        """should_skip returns True for skipped stages."""
        config = PipelineConfig(skip_stages=[PipelineStage.VISUALIZATION])
        assert config.should_skip(PipelineStage.VISUALIZATION) is True
        assert config.should_skip(PipelineStage.CLEANING) is False

    def test_get_stages_to_execute_with_no_skips(self):
        """get_stages_to_execute returns all stages when none skipped."""
        config = PipelineConfig()
        stages = config.get_stages_to_execute()
        assert len(stages) == 5
        assert stages == PipelineStage.get_order()

    def test_get_stages_to_execute_with_skips(self):
        """get_stages_to_execute excludes skipped stages."""
        config = PipelineConfig(skip_stages=[PipelineStage.VISUALIZATION])
        stages = config.get_stages_to_execute()
        assert PipelineStage.VISUALIZATION not in stages
        assert len(stages) == 4

    def test_get_stages_to_execute_with_resume(self):
        """get_stages_to_execute starts from resume point."""
        config = PipelineConfig(resume_from=PipelineStage.VISUALIZATION)
        stages = config.get_stages_to_execute()
        assert stages[0] == PipelineStage.VISUALIZATION
        assert len(stages) == 3  # visualization, report, summary

    def test_get_stages_to_execute_with_resume_and_skips(self):
        """get_stages_to_execute handles both resume and skips."""
        config = PipelineConfig(
            resume_from=PipelineStage.ANALYSIS,
            skip_stages=[PipelineStage.VISUALIZATION],
        )
        stages = config.get_stages_to_execute()
        assert stages[0] == PipelineStage.ANALYSIS
        assert PipelineStage.VISUALIZATION not in stages
        assert len(stages) == 3  # analysis, report, summary

    def test_to_dict_serialization(self):
        """to_dict produces correct dictionary."""
        config = PipelineConfig(
            skip_stages=[PipelineStage.VISUALIZATION],
            writing_style="executive",
            resume_from=PipelineStage.ANALYSIS,
        )
        d = config.to_dict()
        assert d["skip_stages"] == ["visualization"]
        assert d["writing_style"] == "executive"
        assert d["resume_from"] == "analysis"

    def test_from_dict_deserialization(self):
        """from_dict creates correct instance."""
        data = {
            "skip_stages": ["visualization", "summary"],
            "writing_style": "technical",
            "analysis_depth": "quick_scan",
            "resume_from": "report",
            "output_dir": "/custom",
        }
        config = PipelineConfig.from_dict(data)
        assert len(config.skip_stages) == 2
        assert config.writing_style == "technical"
        assert config.resume_from == PipelineStage.REPORT

    def test_roundtrip_serialization(self):
        """to_dict -> from_dict preserves values."""
        original = PipelineConfig(
            skip_stages=[PipelineStage.VISUALIZATION],
            writing_style="executive",
            analysis_depth="deep_dive",
            resume_from=PipelineStage.ANALYSIS,
        )
        restored = PipelineConfig.from_dict(original.to_dict())
        assert restored.skip_stages == original.skip_stages
        assert restored.writing_style == original.writing_style
        assert restored.analysis_depth == original.analysis_depth
        assert restored.resume_from == original.resume_from


# =============================================================================
# PipelineState Tests
# =============================================================================


class TestPipelineState:
    """Tests for PipelineState dataclass."""

    def test_minimal_initialization(self, sample_csv):
        """State can be created with just source file."""
        state = PipelineState(source_file=sample_csv)
        assert state.source_file == sample_csv
        assert state.timestamp is not None
        assert state.completed_stages == []
        assert state.is_failed is False

    def test_source_name_property(self, sample_csv):
        """source_name extracts base name correctly."""
        state = PipelineState(source_file=sample_csv)
        assert state.source_name == "sample_data"

    def test_is_failed_property(self, sample_csv):
        """is_failed reflects failure state."""
        state = PipelineState(source_file=sample_csv)
        assert state.is_failed is False

        state.mark_stage_failed(PipelineStage.CLEANING, "Test error")
        assert state.is_failed is True

    def test_is_complete_property(self, sample_csv):
        """is_complete reflects completion state."""
        state = PipelineState(source_file=sample_csv)
        assert state.is_complete is False  # No stages completed

        state.mark_stage_complete(PipelineStage.CLEANING)
        assert state.is_complete is True

        state.mark_stage_failed(PipelineStage.ANALYSIS, "Error")
        assert state.is_complete is False

    def test_mark_stage_complete(self, sample_csv):
        """mark_stage_complete adds stage to completed list."""
        state = PipelineState(source_file=sample_csv)
        state.mark_stage_complete(PipelineStage.CLEANING)
        state.mark_stage_complete(PipelineStage.ANALYSIS)

        assert "cleaning" in state.completed_stages
        assert "analysis" in state.completed_stages
        assert len(state.completed_stages) == 2

    def test_mark_stage_complete_idempotent(self, sample_csv):
        """mark_stage_complete doesn't duplicate entries."""
        state = PipelineState(source_file=sample_csv)
        state.mark_stage_complete(PipelineStage.CLEANING)
        state.mark_stage_complete(PipelineStage.CLEANING)

        assert state.completed_stages.count("cleaning") == 1

    def test_mark_stage_failed(self, sample_csv):
        """mark_stage_failed sets failure info."""
        state = PipelineState(source_file=sample_csv)
        state.mark_stage_failed(PipelineStage.ANALYSIS, "Connection error")

        assert state.failed_stage == "analysis"
        assert state.error_message == "Connection error"
        assert state.is_failed is True

    def test_get_stage_output(self, sample_csv):
        """get_stage_output returns correct paths."""
        state = PipelineState(
            source_file=sample_csv,
            cleaned_csv_path="/path/to/cleaned.csv",
            analysis_json_path="/path/to/analysis.json",
        )
        assert state.get_stage_output(PipelineStage.CLEANING) == "/path/to/cleaned.csv"
        assert state.get_stage_output(PipelineStage.ANALYSIS) == "/path/to/analysis.json"
        assert state.get_stage_output(PipelineStage.VISUALIZATION) is None

    def test_set_stage_output(self, sample_csv):
        """set_stage_output updates correct field."""
        state = PipelineState(source_file=sample_csv)

        state.set_stage_output(PipelineStage.CLEANING, "/path/cleaned.csv")
        assert state.cleaned_csv_path == "/path/cleaned.csv"

        state.set_stage_output(PipelineStage.VISUALIZATION, "/path/viz")
        assert state.visualization_dir == "/path/viz"

    def test_get_all_outputs(self, sample_csv):
        """get_all_outputs returns all output paths."""
        state = PipelineState(
            source_file=sample_csv,
            cleaned_csv_path="/path/cleaned.csv",
            report_path="/path/report.md",
        )
        outputs = state.get_all_outputs()
        assert outputs["cleaned_csv"] == "/path/cleaned.csv"
        assert outputs["report"] == "/path/report.md"
        assert outputs["analysis_json"] is None

    def test_to_dict_serialization(self, sample_csv):
        """to_dict produces correct dictionary."""
        state = PipelineState(
            source_file=sample_csv,
            timestamp="20260124_100000",
            cleaned_csv_path="/path/cleaned.csv",
        )
        state.mark_stage_complete(PipelineStage.CLEANING)

        d = state.to_dict()
        assert d["source_file"] == sample_csv
        assert d["timestamp"] == "20260124_100000"
        assert d["cleaned_csv_path"] == "/path/cleaned.csv"
        assert "cleaning" in d["completed_stages"]

    def test_from_dict_deserialization(self, sample_csv):
        """from_dict creates correct instance."""
        data = {
            "source_file": sample_csv,
            "timestamp": "20260124_100000",
            "cleaned_csv_path": "/path/cleaned.csv",
            "completed_stages": ["cleaning"],
            "failed_stage": None,
        }
        state = PipelineState.from_dict(data)
        assert state.source_file == sample_csv
        assert state.cleaned_csv_path == "/path/cleaned.csv"
        assert "cleaning" in state.completed_stages

    def test_roundtrip_serialization(self, sample_csv):
        """to_dict -> from_dict preserves values."""
        original = PipelineState(
            source_file=sample_csv,
            timestamp="20260124_100000",
            cleaned_csv_path="/path/cleaned.csv",
            analysis_json_path="/path/analysis.json",
        )
        original.mark_stage_complete(PipelineStage.CLEANING)

        restored = PipelineState.from_dict(original.to_dict())
        assert restored.source_file == original.source_file
        assert restored.timestamp == original.timestamp
        assert restored.cleaned_csv_path == original.cleaned_csv_path
        assert restored.completed_stages == original.completed_stages


# =============================================================================
# Discovery Tests
# =============================================================================


class TestValidateInputFile:
    """Tests for validate_input_file function."""

    def test_valid_csv_file(self, sample_csv):
        """Valid CSV file passes validation."""
        result = validate_input_file(sample_csv)
        assert result["valid"] is True
        assert result["error"] is None
        assert result["extension"] == ".csv"
        assert result["file_size"] > 0

    def test_valid_xlsx_file(self, sample_xlsx):
        """Valid XLSX file passes validation."""
        result = validate_input_file(sample_xlsx)
        assert result["valid"] is True
        assert result["extension"] == ".xlsx"

    def test_nonexistent_file(self, temp_dir):
        """Nonexistent file fails validation."""
        path = os.path.join(temp_dir, "nonexistent.csv")
        result = validate_input_file(path)
        assert result["valid"] is False
        assert "not found" in result["error"].lower()

    def test_empty_file(self, empty_file):
        """Empty file fails validation."""
        result = validate_input_file(empty_file)
        assert result["valid"] is False
        assert "empty" in result["error"].lower()

    def test_unsupported_extension(self, temp_dir):
        """Unsupported file type fails validation."""
        path = os.path.join(temp_dir, "data.json")
        with open(path, "w") as f:
            f.write("{}")
        result = validate_input_file(path)
        assert result["valid"] is False
        assert "unsupported" in result["error"].lower()

    def test_directory_fails(self, temp_dir):
        """Directory fails validation."""
        result = validate_input_file(temp_dir)
        assert result["valid"] is False
        assert "not a file" in result["error"].lower()

    def test_returns_absolute_path(self, sample_csv, temp_dir):
        """Validation returns absolute path."""
        # Create relative path
        original_dir = os.getcwd()
        try:
            os.chdir(temp_dir)
            result = validate_input_file("sample_data.csv")
            assert os.path.isabs(result["file_path"])
        finally:
            os.chdir(original_dir)


class TestGetSourceName:
    """Tests for get_source_name function."""

    def test_extracts_base_name(self):
        """Extracts base name from path."""
        assert get_source_name("/path/to/sales_data.csv") == "sales_data"
        assert get_source_name("quarterly_report.xlsx") == "quarterly_report"

    def test_handles_multiple_dots(self):
        """Handles filenames with multiple dots."""
        assert get_source_name("sales.2024.data.csv") == "sales.2024.data"

    def test_handles_no_extension(self):
        """Handles files without extension."""
        assert get_source_name("/path/to/data") == "data"


class TestFindOutputsForSource:
    """Tests for find_outputs_for_source function."""

    def test_finds_existing_outputs(self, sample_outputs):
        """Finds all output files for a source."""
        outputs = find_outputs_for_source(
            sample_outputs["source"],
            sample_outputs["output_dir"],
        )
        assert outputs["cleaned_csv"] is not None
        assert outputs["analysis_json"] is not None
        assert outputs["visualization_dir"] is not None

    def test_returns_none_for_missing_outputs(self, output_dir):
        """Returns None for missing output types."""
        outputs = find_outputs_for_source("nonexistent", output_dir)
        assert outputs["cleaned_csv"] is None
        assert outputs["analysis_json"] is None

    def test_filters_by_timestamp(self, sample_outputs):
        """Filters outputs by specific timestamp."""
        outputs = find_outputs_for_source(
            sample_outputs["source"],
            sample_outputs["output_dir"],
            timestamp=sample_outputs["timestamp"],
        )
        assert outputs["cleaned_csv"] is not None

    def test_returns_empty_for_nonexistent_dir(self):
        """Returns empty results for nonexistent directory."""
        outputs = find_outputs_for_source("source", "/nonexistent/dir")
        assert all(v is None for v in outputs.values())


class TestDiscoverResumableState:
    """Tests for discover_resumable_state function."""

    def test_discovers_completed_stages(self, sample_outputs, sample_csv):
        """Discovers which stages have completed."""
        # Create source file with matching name
        source_file = os.path.join(
            os.path.dirname(sample_outputs["output_dir"]),
            f"{sample_outputs['source']}.csv"
        )
        with open(source_file, "w") as f:
            f.write("id,value\n1,100\n")

        result = discover_resumable_state(source_file, sample_outputs["output_dir"])

        assert result["can_resume"] is False  # All stages complete
        assert "cleaning" in result["completed_stages"]
        assert "analysis" in result["completed_stages"]

    def test_returns_no_resume_for_fresh_start(self, sample_csv, output_dir):
        """Returns no resume state for fresh start."""
        result = discover_resumable_state(sample_csv, output_dir)
        assert result["can_resume"] is False
        assert result["completed_stages"] == []
        assert result["state"] is None

    def test_builds_pipeline_state(self, sample_outputs, temp_dir):
        """Builds PipelineState from discovered outputs."""
        source_file = os.path.join(temp_dir, f"{sample_outputs['source']}.csv")
        with open(source_file, "w") as f:
            f.write("id,value\n1,100\n")

        result = discover_resumable_state(source_file, sample_outputs["output_dir"])

        state = result["state"]
        assert state is not None
        assert state.cleaned_csv_path is not None


class TestGetOutputPath:
    """Tests for get_output_path function."""

    def test_generates_correct_paths(self):
        """Generates correct output paths for each stage."""
        path = get_output_path("sales", PipelineStage.CLEANING, "20260124_100000", "/out")
        assert path == "/out/sales_cleaned_20260124_100000.csv"

        path = get_output_path("sales", PipelineStage.ANALYSIS, "20260124_100000", "/out")
        assert path == "/out/sales_analysis_20260124_100000.json"

        path = get_output_path("sales", PipelineStage.VISUALIZATION, "20260124_100000", "/out")
        assert path == "/out/sales_visualizations_20260124_100000"

        path = get_output_path("sales", PipelineStage.REPORT, "20260124_100000", "/out")
        assert path == "/out/sales_report_20260124_100000.md"

        path = get_output_path("sales", PipelineStage.SUMMARY, "20260124_100000", "/out")
        assert path == "/out/sales_executive_summary_20260124_100000.md"


class TestEnsureOutputDir:
    """Tests for ensure_output_dir function."""

    def test_creates_directory(self, temp_dir):
        """Creates directory if it doesn't exist."""
        new_dir = os.path.join(temp_dir, "new_output")
        result = ensure_output_dir(new_dir)
        assert os.path.isdir(result)

    def test_returns_absolute_path(self, temp_dir):
        """Returns absolute path."""
        result = ensure_output_dir(temp_dir)
        assert os.path.isabs(result)

    def test_handles_existing_directory(self, output_dir):
        """Handles already existing directory."""
        result = ensure_output_dir(output_dir)
        assert result == os.path.abspath(output_dir)


# =============================================================================
# Manifest Tests
# =============================================================================


class TestPipelineManifest:
    """Tests for PipelineManifest dataclass."""

    def test_basic_initialization(self):
        """Manifest can be created with required fields."""
        manifest = PipelineManifest(
            source_file="/path/to/data.csv",
            source_name="data",
            timestamp="20260124_100000",
            config={"writing_style": "business"},
            stages_executed=["cleaning", "analysis"],
            stages_skipped=[],
            outputs={"cleaned_csv": "/path/cleaned.csv"},
            duration_seconds=45.5,
            success=True,
        )
        assert manifest.source_name == "data"
        assert manifest.success is True

    def test_output_count_property(self):
        """output_count counts non-None outputs."""
        manifest = PipelineManifest(
            source_file="/path/to/data.csv",
            source_name="data",
            timestamp="20260124_100000",
            config={},
            stages_executed=[],
            stages_skipped=[],
            outputs={
                "cleaned_csv": "/path/cleaned.csv",
                "analysis_json": "/path/analysis.json",
                "report": None,
            },
            duration_seconds=10,
            success=True,
        )
        assert manifest.output_count == 2

    def test_stage_count_property(self):
        """stage_count returns number of executed stages."""
        manifest = PipelineManifest(
            source_file="/path/to/data.csv",
            source_name="data",
            timestamp="20260124_100000",
            config={},
            stages_executed=["cleaning", "analysis", "report"],
            stages_skipped=["visualization"],
            outputs={},
            duration_seconds=10,
            success=True,
        )
        assert manifest.stage_count == 3

    def test_get_output_summary(self):
        """get_output_summary returns filenames only."""
        manifest = PipelineManifest(
            source_file="/path/to/data.csv",
            source_name="data",
            timestamp="20260124_100000",
            config={},
            stages_executed=[],
            stages_skipped=[],
            outputs={
                "cleaned_csv": "/long/path/to/cleaned.csv",
                "report": None,
            },
            duration_seconds=10,
            success=True,
        )
        summary = manifest.get_output_summary()
        assert summary["cleaned_csv"] == "cleaned.csv"
        assert summary["report"] is None

    def test_to_dict_includes_summary(self):
        """to_dict includes summary section."""
        manifest = PipelineManifest(
            source_file="/path/to/data.csv",
            source_name="data",
            timestamp="20260124_100000",
            config={},
            stages_executed=["cleaning"],
            stages_skipped=[],
            outputs={"cleaned_csv": "/path/cleaned.csv"},
            duration_seconds=10.123,
            success=True,
        )
        d = manifest.to_dict()
        assert "summary" in d
        assert d["summary"]["output_count"] == 1
        assert d["summary"]["stage_count"] == 1
        assert d["duration_seconds"] == 10.12  # Rounded

    def test_to_json(self):
        """to_json produces valid JSON."""
        manifest = PipelineManifest(
            source_file="/path/to/data.csv",
            source_name="data",
            timestamp="20260124_100000",
            config={"key": "value"},
            stages_executed=["cleaning"],
            stages_skipped=[],
            outputs={},
            duration_seconds=10,
            success=True,
        )
        json_str = manifest.to_json()
        parsed = json.loads(json_str)
        assert parsed["source_name"] == "data"

    def test_from_dict(self):
        """from_dict creates correct instance."""
        data = {
            "source_file": "/path/to/data.csv",
            "source_name": "data",
            "timestamp": "20260124_100000",
            "config": {"writing_style": "business"},
            "stages_executed": ["cleaning"],
            "stages_skipped": ["visualization"],
            "outputs": {"cleaned_csv": "/path/cleaned.csv"},
            "duration_seconds": 45.5,
            "success": True,
            "error_stage": None,
            "error_message": None,
        }
        manifest = PipelineManifest.from_dict(data)
        assert manifest.source_name == "data"
        assert manifest.stages_skipped == ["visualization"]

    def test_from_json(self):
        """from_json parses JSON correctly."""
        json_str = json.dumps({
            "source_file": "/path/to/data.csv",
            "source_name": "data",
            "timestamp": "20260124_100000",
            "config": {},
            "stages_executed": ["cleaning"],
            "stages_skipped": [],
            "outputs": {},
            "duration_seconds": 10,
            "success": True,
        })
        manifest = PipelineManifest.from_json(json_str)
        assert manifest.source_name == "data"

    def test_roundtrip_serialization(self):
        """to_json -> from_json preserves values."""
        original = PipelineManifest(
            source_file="/path/to/data.csv",
            source_name="data",
            timestamp="20260124_100000",
            config={"writing_style": "executive"},
            stages_executed=["cleaning", "analysis"],
            stages_skipped=["visualization"],
            outputs={"cleaned_csv": "/path/cleaned.csv"},
            duration_seconds=123.45,
            success=True,
            error_stage=None,
            error_message=None,
        )
        restored = PipelineManifest.from_json(original.to_json())
        assert restored.source_file == original.source_file
        assert restored.stages_executed == original.stages_executed
        assert restored.config == original.config


class TestCreatePipelineManifest:
    """Tests for create_pipeline_manifest function."""

    def test_creates_manifest_from_state(self, sample_csv):
        """Creates manifest from state and config."""
        state = PipelineState(
            source_file=sample_csv,
            timestamp="20260124_100000",
            cleaned_csv_path="/path/cleaned.csv",
        )
        state.mark_stage_complete(PipelineStage.CLEANING)

        config = PipelineConfig()
        start_time = datetime.now() - timedelta(seconds=30)

        manifest = create_pipeline_manifest(state, config, start_time)

        assert manifest.source_file == sample_csv
        assert "cleaning" in manifest.stages_executed
        assert manifest.duration_seconds >= 30
        assert manifest.success is True

    def test_includes_failed_info(self, sample_csv):
        """Includes failure information in manifest."""
        state = PipelineState(source_file=sample_csv)
        state.mark_stage_failed(PipelineStage.ANALYSIS, "Connection error")

        config = PipelineConfig()
        manifest = create_pipeline_manifest(state, config, datetime.now())

        assert manifest.success is False
        assert manifest.error_stage == "analysis"
        assert manifest.error_message == "Connection error"

    def test_tracks_skipped_stages(self, sample_csv):
        """Tracks skipped stages correctly."""
        state = PipelineState(source_file=sample_csv)
        state.mark_stage_complete(PipelineStage.CLEANING)
        state.mark_stage_complete(PipelineStage.ANALYSIS)

        config = PipelineConfig(skip_stages=[PipelineStage.VISUALIZATION])
        manifest = create_pipeline_manifest(state, config, datetime.now())

        assert "visualization" in manifest.stages_skipped


class TestSavePipelineManifest:
    """Tests for save_pipeline_manifest function."""

    def test_saves_manifest_to_file(self, output_dir):
        """Saves manifest to JSON file."""
        manifest = PipelineManifest(
            source_file="/path/to/data.csv",
            source_name="data",
            timestamp="20260124_100000",
            config={},
            stages_executed=["cleaning"],
            stages_skipped=[],
            outputs={},
            duration_seconds=10,
            success=True,
        )

        path = save_pipeline_manifest(manifest, output_dir)

        assert os.path.exists(path)
        assert path.endswith(".json")
        assert "data_pipeline_manifest" in path

    def test_creates_output_dir_if_needed(self, temp_dir):
        """Creates output directory if it doesn't exist."""
        new_dir = os.path.join(temp_dir, "new_output")
        manifest = PipelineManifest(
            source_file="/path/to/data.csv",
            source_name="data",
            timestamp="20260124_100000",
            config={},
            stages_executed=[],
            stages_skipped=[],
            outputs={},
            duration_seconds=10,
            success=True,
        )

        path = save_pipeline_manifest(manifest, new_dir)
        assert os.path.exists(path)


class TestLoadPipelineManifest:
    """Tests for load_pipeline_manifest function."""

    def test_loads_saved_manifest(self, output_dir):
        """Loads manifest from file."""
        manifest = PipelineManifest(
            source_file="/path/to/data.csv",
            source_name="data",
            timestamp="20260124_100000",
            config={"key": "value"},
            stages_executed=["cleaning"],
            stages_skipped=[],
            outputs={"cleaned_csv": "/path/cleaned.csv"},
            duration_seconds=45.5,
            success=True,
        )
        path = save_pipeline_manifest(manifest, output_dir)

        loaded = load_pipeline_manifest(path)

        assert loaded.source_name == manifest.source_name
        assert loaded.config == manifest.config
        assert loaded.outputs == manifest.outputs

    def test_raises_for_nonexistent_file(self):
        """Raises FileNotFoundError for nonexistent file."""
        with pytest.raises(FileNotFoundError):
            load_pipeline_manifest("/nonexistent/manifest.json")


class TestFindManifestsForSource:
    """Tests for find_manifests_for_source function."""

    def test_finds_manifests(self, output_dir):
        """Finds all manifests for a source."""
        # Create multiple manifests
        for ts in ["20260124_100000", "20260124_110000"]:
            manifest = PipelineManifest(
                source_file="/path/to/data.csv",
                source_name="data",
                timestamp=ts,
                config={},
                stages_executed=[],
                stages_skipped=[],
                outputs={},
                duration_seconds=10,
                success=True,
            )
            save_pipeline_manifest(manifest, output_dir)

        manifests = find_manifests_for_source("data", output_dir)
        assert len(manifests) == 2

    def test_returns_empty_for_no_manifests(self, output_dir):
        """Returns empty list when no manifests found."""
        manifests = find_manifests_for_source("nonexistent", output_dir)
        assert manifests == []


class TestGetLatestManifest:
    """Tests for get_latest_manifest function."""

    def test_returns_latest_manifest(self, output_dir):
        """Returns the most recent manifest."""
        import time

        # Create manifests with slight delay
        manifest1 = PipelineManifest(
            source_file="/path/to/data.csv",
            source_name="data",
            timestamp="20260124_100000",
            config={},
            stages_executed=["cleaning"],
            stages_skipped=[],
            outputs={},
            duration_seconds=10,
            success=True,
        )
        save_pipeline_manifest(manifest1, output_dir)

        time.sleep(0.1)  # Ensure different mtime

        manifest2 = PipelineManifest(
            source_file="/path/to/data.csv",
            source_name="data",
            timestamp="20260124_110000",
            config={},
            stages_executed=["cleaning", "analysis"],
            stages_skipped=[],
            outputs={},
            duration_seconds=20,
            success=True,
        )
        save_pipeline_manifest(manifest2, output_dir)

        latest = get_latest_manifest("data", output_dir)
        assert latest is not None
        assert latest.timestamp == "20260124_110000"

    def test_returns_none_when_no_manifests(self, output_dir):
        """Returns None when no manifests exist."""
        latest = get_latest_manifest("nonexistent", output_dir)
        assert latest is None


# =============================================================================
# Integration Tests
# =============================================================================


class TestOrchestrationIntegration:
    """Integration tests for the orchestration module."""

    def test_full_workflow(self, sample_csv, output_dir):
        """Test complete workflow: validate -> state -> manifest."""
        # Validate input
        validation = validate_input_file(sample_csv)
        assert validation["valid"] is True

        # Create config and state
        config = PipelineConfig(
            writing_style="executive",
            output_dir=output_dir,
        )

        state = PipelineState(
            source_file=validation["file_path"],
            timestamp="20260124_100000",
        )

        # Simulate stage completion
        cleaned_path = get_output_path(
            state.source_name,
            PipelineStage.CLEANING,
            state.timestamp,
            output_dir,
        )
        state.set_stage_output(PipelineStage.CLEANING, cleaned_path)
        state.mark_stage_complete(PipelineStage.CLEANING)

        # Create manifest
        start_time = datetime.now() - timedelta(seconds=60)
        manifest = create_pipeline_manifest(state, config, start_time)

        assert manifest.success is True
        assert "cleaning" in manifest.stages_executed

        # Save and reload
        path = save_pipeline_manifest(manifest, output_dir)
        loaded = load_pipeline_manifest(path)

        assert loaded.source_name == state.source_name
        assert loaded.config["writing_style"] == "executive"

    def test_resume_workflow(self, sample_outputs, temp_dir):
        """Test resume discovery and continuation."""
        # Create source file matching existing outputs
        source_file = os.path.join(temp_dir, f"{sample_outputs['source']}.csv")
        with open(source_file, "w") as f:
            f.write("id,value\n1,100\n")

        # Discover resumable state
        result = discover_resumable_state(source_file, sample_outputs["output_dir"])

        assert len(result["completed_stages"]) > 0
        assert result["outputs"]["cleaned_csv"] is not None

        # If resumable, continue from discovered state
        if result["can_resume"]:
            state = result["state"]
            assert state is not None
            assert state.cleaned_csv_path is not None


class TestResumeFromFirstMissingStage:
    """A later stage's output must not cause earlier stages to be skipped."""

    def test_missing_analysis_is_rerun(self, tmp_path):
        from src.orchestration.discovery import discover_resumable_state

        ts = "20260101_120000"
        (tmp_path / f"sales_cleaned_{ts}.csv").write_text("a\n1\n")
        (tmp_path / f"sales_report_{ts}.md").write_text("# report")

        state = discover_resumable_state("sales.csv", str(tmp_path))

        assert state["resume_from"].value == "analysis"
