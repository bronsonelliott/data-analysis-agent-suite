"""Tests for executive summary data loading utilities."""

import pytest
import json
from pathlib import Path
from src.summarization.loader import (
    SummaryInput,
    load_report,
    load_analysis_result,
    create_summary_input,
    find_report_files,
    find_latest_report,
    find_analysis_files,
    find_latest_analysis,
    find_visualization_directory,
    auto_discover_inputs,
    extract_title_from_report,
    extract_date_from_report,
)


class TestSummaryInput:
    """Tests for SummaryInput dataclass."""

    def test_has_report_true(self, sample_summary_input):
        """Test has_report returns True when report content exists."""
        assert sample_summary_input.has_report is True

    def test_has_report_false(self, sample_analysis_result):
        """Test has_report returns False when no report content."""
        input_data = SummaryInput(
            source_file='test.csv',
            analysis_result=sample_analysis_result,
        )
        assert input_data.has_report is False

    def test_has_analysis_true(self, sample_summary_input):
        """Test has_analysis returns True when analysis exists."""
        assert sample_summary_input.has_analysis is True

    def test_has_analysis_false(self, sample_report_content):
        """Test has_analysis returns False when no analysis."""
        input_data = SummaryInput(
            source_file='test.csv',
            report_content=sample_report_content,
        )
        assert input_data.has_analysis is False

    def test_finding_count(self, sample_summary_input):
        """Test finding_count returns correct count."""
        assert sample_summary_input.finding_count == 3

    def test_finding_count_no_analysis(self, sample_report_content):
        """Test finding_count returns 0 when no analysis."""
        input_data = SummaryInput(
            source_file='test.csv',
            report_content=sample_report_content,
        )
        assert input_data.finding_count == 0

    def test_has_visualizations_false(self, sample_summary_input):
        """Test has_visualizations returns False when no manifest."""
        assert sample_summary_input.has_visualizations is False

    def test_to_dict(self, sample_summary_input):
        """Test to_dict returns correct structure."""
        result = sample_summary_input.to_dict()
        assert 'source_file' in result
        assert 'has_report' in result
        assert 'has_analysis' in result
        assert 'finding_count' in result


class TestLoadReport:
    """Tests for load_report function."""

    def test_load_existing_report(self, sample_report_file):
        """Test loading an existing report file."""
        content = load_report(sample_report_file)
        assert '# Sales Data Analysis Report' in content

    def test_load_missing_report(self):
        """Test loading a non-existent report raises error."""
        with pytest.raises(FileNotFoundError):
            load_report('/nonexistent/path/report.md')


class TestLoadAnalysisResult:
    """Tests for load_analysis_result function."""

    def test_load_existing_analysis(self, sample_analysis_json):
        """Test loading an existing analysis file."""
        result = load_analysis_result(sample_analysis_json)
        assert result is not None
        assert len(result.findings) == 3

    def test_load_missing_analysis(self):
        """Test loading a non-existent analysis raises error."""
        with pytest.raises(FileNotFoundError):
            load_analysis_result('/nonexistent/path/analysis.json')


class TestFindReportFiles:
    """Tests for find_report_files function."""

    def test_find_reports_in_directory(self, sample_report_file):
        """Test finding reports in a directory."""
        directory = str(Path(sample_report_file).parent)
        reports = find_report_files(directory)
        assert len(reports) == 1
        assert sample_report_file in reports

    def test_find_reports_empty_directory(self, temp_output_dir):
        """Test finding reports in empty directory."""
        reports = find_report_files(temp_output_dir)
        assert len(reports) == 0

    def test_find_reports_nonexistent_directory(self):
        """Test finding reports in non-existent directory."""
        reports = find_report_files('/nonexistent/path')
        assert len(reports) == 0


class TestFindLatestReport:
    """Tests for find_latest_report function."""

    def test_find_latest_report(self, sample_report_file):
        """Test finding the latest report."""
        directory = str(Path(sample_report_file).parent)
        latest = find_latest_report(directory)
        assert latest == sample_report_file

    def test_find_latest_report_none(self, temp_output_dir):
        """Test finding latest report in empty directory."""
        latest = find_latest_report(temp_output_dir)
        assert latest is None


class TestFindAnalysisFiles:
    """Tests for find_analysis_files function."""

    def test_find_analysis_in_directory(self, sample_analysis_json):
        """Test finding analysis files in a directory."""
        directory = str(Path(sample_analysis_json).parent)
        analyses = find_analysis_files(directory)
        assert len(analyses) == 1

    def test_find_analysis_empty_directory(self, temp_output_dir):
        """Test finding analysis in empty directory."""
        analyses = find_analysis_files(temp_output_dir)
        assert len(analyses) == 0


class TestFindLatestAnalysis:
    """Tests for find_latest_analysis function."""

    def test_find_latest_analysis(self, sample_analysis_json):
        """Test finding the latest analysis."""
        directory = str(Path(sample_analysis_json).parent)
        latest = find_latest_analysis(directory)
        assert latest == sample_analysis_json

    def test_find_latest_analysis_none(self, temp_output_dir):
        """Test finding latest analysis in empty directory."""
        latest = find_latest_analysis(temp_output_dir)
        assert latest is None


class TestFindVisualizationDirectory:
    """Tests for find_visualization_directory function."""

    def test_find_viz_directory(self, sample_visualization_manifest):
        """Test finding visualization directory."""
        parent_dir = str(Path(sample_visualization_manifest).parent.parent)
        viz_dir = find_visualization_directory(parent_dir)
        assert viz_dir is not None
        assert 'visualizations' in viz_dir

    def test_find_viz_directory_none(self, temp_output_dir):
        """Test finding viz directory when none exists."""
        viz_dir = find_visualization_directory(temp_output_dir)
        assert viz_dir is None


class TestCreateSummaryInput:
    """Tests for create_summary_input function."""

    def test_create_with_analysis_only(self, sample_analysis_json):
        """Test creating input with analysis only."""
        input_data = create_summary_input(analysis_path=sample_analysis_json)
        assert input_data.has_analysis is True
        assert input_data.has_report is False

    def test_create_with_report_only(self, sample_report_file):
        """Test creating input with report only."""
        input_data = create_summary_input(report_path=sample_report_file)
        assert input_data.has_report is True
        assert input_data.has_analysis is False

    def test_create_with_both(self, sample_analysis_json, sample_report_file):
        """Test creating input with both analysis and report."""
        input_data = create_summary_input(
            analysis_path=sample_analysis_json,
            report_path=sample_report_file,
        )
        assert input_data.has_analysis is True
        assert input_data.has_report is True

    def test_create_with_context(self, sample_analysis_json):
        """Test creating input with context."""
        input_data = create_summary_input(
            analysis_path=sample_analysis_json,
            context='Test context',
        )
        assert input_data.context == 'Test context'

    def test_create_with_emphasis(self, sample_analysis_json):
        """Test creating input with emphasis areas."""
        input_data = create_summary_input(
            analysis_path=sample_analysis_json,
            emphasis_areas=['revenue', 'sales'],
        )
        assert 'revenue' in input_data.emphasis_areas

    def test_create_with_neither_raises(self):
        """Test creating input with neither raises ValueError."""
        with pytest.raises(ValueError):
            create_summary_input()

    def test_create_with_visualization(self, sample_analysis_json, sample_visualization_manifest):
        """Test creating input with visualization manifest."""
        input_data = create_summary_input(
            analysis_path=sample_analysis_json,
            viz_path=sample_visualization_manifest,
        )
        assert input_data.has_visualizations is True


class TestAutoDiscoverInputs:
    """Tests for auto_discover_inputs function."""

    def test_auto_discover_with_files(self, sample_analysis_json, sample_report_file):
        """Test auto-discovering inputs."""
        directory = str(Path(sample_analysis_json).parent)
        # Create report in same directory
        report_dest = Path(directory) / 'test_report_business_20240124_144500.md'
        report_dest.write_text(Path(sample_report_file).read_text())

        input_data = auto_discover_inputs(directory)
        assert input_data is not None

    def test_auto_discover_empty_directory(self, temp_output_dir):
        """Test auto-discovering in empty directory."""
        input_data = auto_discover_inputs(temp_output_dir)
        assert input_data is None


class TestExtractTitleFromReport:
    """Tests for extract_title_from_report function."""

    def test_extract_title(self, sample_report_content):
        """Test extracting title from report."""
        title = extract_title_from_report(sample_report_content)
        assert title == 'Sales Data Analysis Report'

    def test_extract_title_no_heading(self):
        """Test extracting title when no heading exists."""
        title = extract_title_from_report('Just some text without heading.')
        assert title == 'Analysis Report'


class TestExtractDateFromReport:
    """Tests for extract_date_from_report function."""

    def test_extract_date(self, sample_report_content):
        """Test extracting date from report."""
        date = extract_date_from_report(sample_report_content)
        assert date is not None
        assert '2024-01-24' in date

    def test_extract_date_not_found(self):
        """Test extracting date when not present."""
        date = extract_date_from_report('Just some text.')
        assert date is None


class TestNewestFirstDiscovery:
    """'Latest' must mean newest timestamp, not last alphabetically."""

    def test_latest_report_is_newest_not_alphabetical(self, tmp_path):
        from src.summarization.loader import find_latest_report

        (tmp_path / "zeta_report_20240101_120000.md").write_text("# old")
        (tmp_path / "alpha_report_20260101_120000.md").write_text("# new")

        assert find_latest_report(str(tmp_path)).endswith("alpha_report_20260101_120000.md")

    def test_cleaning_log_is_not_a_report(self, tmp_path):
        from src.summarization.loader import find_report_files

        (tmp_path / "sales_cleaning_log_20260101_120000.md").write_text("# audit")
        (tmp_path / "sales_cleaned_report_20250101_120000.md").write_text("# report")

        assert [Path(p).name for p in find_report_files(str(tmp_path))] == [
            "sales_cleaned_report_20250101_120000.md"
        ]
