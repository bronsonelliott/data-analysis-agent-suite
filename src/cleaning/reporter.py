"""Report generation utilities for creating cleaning audit trails."""

from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import pandas as pd

from .profiler import DataProfile, profile_dataframe
from .utils import format_row_numbers, ensure_output_dir


def format_change_delta(before: int, after: int) -> str:
    """Format a change as +N, -N, or 'no change'."""
    diff = after - before
    if diff > 0:
        return f"+{diff}"
    elif diff < 0:
        return str(diff)
    else:
        return "—"


def generate_column_table(profile: DataProfile) -> str:
    """Generate markdown table rows for column overview."""
    lines = []

    for col in profile.columns:
        missing_pct = f"{col.missing_count / col.total_count * 100:.1f}%" if col.total_count > 0 else "0%"
        notes = []

        if col.inferred_type == 'date' and col.date_formats_detected:
            notes.append(f"formats: {', '.join(col.date_formats_detected[:2])}")
        if col.inferred_type == 'numeric' and col.min_value is not None:
            notes.append(f"range: {col.min_value:.2f} - {col.max_value:.2f}")

        notes_str = "; ".join(notes) if notes else "—"

        lines.append(
            f"| {col.name} | {col.inferred_type} | {missing_pct} | {col.unique_count:,} | {notes_str} |"
        )

    return "\n".join(lines)


def generate_change_log(changes: List[Dict[str, Any]]) -> str:
    """Generate detailed change log section."""
    if not changes:
        return "_No changes were made._"

    lines = []

    for i, change in enumerate(changes, 1):
        col_info = f" in `{change['column']}`" if change.get('column') else ""
        row_info = ""

        if change.get('row_numbers'):
            formatted_rows = format_row_numbers(change['row_numbers'][:50])
            if len(change['row_numbers']) > 50:
                formatted_rows += f" ... and {len(change['row_numbers']) - 50} more"
            row_info = f"\n   - Affected rows: {formatted_rows}"

        lines.append(f"### {i}. {change['operation'].replace('_', ' ').title()}{col_info}")
        lines.append(f"\n{change.get('description', 'No description')}{row_info}")

        # Show before/after samples
        if change.get('old_values') or change.get('new_values'):
            lines.append("\n**Sample changes:**")
            lines.append("| Before | After |")
            lines.append("|--------|-------|")

            old_vals = change.get('old_values', [])
            new_vals = change.get('new_values', [])

            for j in range(max(len(old_vals), len(new_vals))):
                old = f"`{old_vals[j]}`" if j < len(old_vals) else "—"
                new = f"`{new_vals[j]}`" if j < len(new_vals) else "—"
                lines.append(f"| {old} | {new} |")

        lines.append("")

    return "\n".join(lines)


def generate_auto_fixes_section(changes: List[Dict[str, Any]]) -> str:
    """Generate section listing auto-applied fixes."""
    auto_fixes = [
        c for c in changes
        if c['operation'] in ['trim_whitespace', 'standardize_column_names', 'fix_encoding', 'parse_currency']
    ]

    if not auto_fixes:
        return "_No automatic fixes were applied._"

    lines = []
    for fix in auto_fixes:
        col_info = f" in `{fix['column']}`" if fix.get('column') else ""
        count = fix.get('affected_count', len(fix.get('row_numbers', [])))
        lines.append(f"- **{fix['operation'].replace('_', ' ').title()}**{col_info}: {count} value(s)")

    return "\n".join(lines)


def generate_user_decisions_section(
    changes: List[Dict[str, Any]],
    decisions: Optional[Dict[str, Any]] = None
) -> str:
    """Generate section listing user decisions."""
    user_ops = [
        c for c in changes
        if c['operation'] in [
            'remove_duplicates', 'flag_duplicates',
            'drop_missing', 'fill_missing_mean', 'fill_missing_median',
            'fill_missing_mode', 'fill_missing_zero', 'fill_missing_custom',
            'forward_fill', 'backward_fill',
            'normalize_dates',
            'flag_outliers', 'remove_outliers', 'cap_outliers',
        ]
    ]

    if not user_ops:
        return "_No user decisions were required._"

    lines = []
    for op in user_ops:
        col_info = f" in `{op['column']}`" if op.get('column') else ""
        count = op.get('affected_count', len(op.get('row_numbers', [])))
        lines.append(f"- **{op['operation'].replace('_', ' ').title()}**{col_info}: {count} value(s)")

    return "\n".join(lines)


def generate_cleaning_report(
    original_df: pd.DataFrame,
    cleaned_df: pd.DataFrame,
    source_file: str,
    changes: List[Dict[str, Any]],
    output_dir: Optional[str] = None,
    decisions: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate a comprehensive markdown cleaning report.

    Args:
        original_df: The original DataFrame before cleaning
        cleaned_df: The cleaned DataFrame
        source_file: Path to the source file
        changes: List of change records from transformations
        output_dir: Optional output directory (defaults to ./output)
        decisions: Optional dict of user decisions made

    Returns:
        The generated markdown report as a string

    Example:
        >>> report = generate_cleaning_report(
        ...     original_df=df_before,
        ...     cleaned_df=df_after,
        ...     source_file="data.csv",
        ...     changes=all_changes,
        ... )
        >>> print(report)
    """
    # Profile both DataFrames
    original_profile = profile_dataframe(original_df)
    cleaned_profile = profile_dataframe(cleaned_df)

    # Calculate metrics
    rows_before = original_profile.total_rows
    rows_after = cleaned_profile.total_rows
    cols_before = original_profile.total_columns
    cols_after = cleaned_profile.total_columns

    missing_before = sum(c.missing_count for c in original_profile.columns)
    missing_after = sum(c.missing_count for c in cleaned_profile.columns)

    duplicates_before = original_profile.duplicate_row_count
    duplicates_after = cleaned_profile.duplicate_row_count

    # Ensure output directory
    output_path = ensure_output_dir(output_dir)

    # Generate output filenames
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    source_name = Path(source_file).stem
    output_csv = f"{source_name}_cleaned_{timestamp}.csv"
    output_report = f"{source_name}_cleaning_log_{timestamp}.md"

    # Read template
    template_path = Path(__file__).parent.parent.parent / "templates" / "cleaning_report.md"

    if template_path.exists():
        template = template_path.read_text()
    else:
        # Fallback inline template
        template = """# Data Cleaning Report

**Generated:** {timestamp}
**Source File:** `{source_file}`

## Summary

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Rows | {rows_before:,} | {rows_after:,} | {rows_change} |
| Columns | {cols_before} | {cols_after} | {cols_change} |
| Missing Values | {missing_before:,} | {missing_after:,} | {missing_change} |
| Duplicate Rows | {duplicates_before:,} | {duplicates_after:,} | {duplicates_change} |

**Total Changes Made:** {total_changes}

## Column Overview

{column_table}

## Detailed Change Log

{change_log}

## Auto-Applied Fixes

{auto_fixes}

## User Decisions

{user_decisions}

## Output Files

- **Cleaned Data:** `{output_csv}`
- **This Report:** `{output_report}`
"""

    # Format the report
    report = template.format(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        source_file=source_file,
        rows_before=rows_before,
        rows_after=rows_after,
        rows_change=format_change_delta(rows_before, rows_after),
        cols_before=cols_before,
        cols_after=cols_after,
        cols_change=format_change_delta(cols_before, cols_after),
        missing_before=missing_before,
        missing_after=missing_after,
        missing_change=format_change_delta(missing_before, missing_after),
        duplicates_before=duplicates_before,
        duplicates_after=duplicates_after,
        duplicates_change=format_change_delta(duplicates_before, duplicates_after),
        total_changes=len(changes),
        column_table=generate_column_table(cleaned_profile),
        change_log=generate_change_log(changes),
        auto_fixes=generate_auto_fixes_section(changes),
        user_decisions=generate_user_decisions_section(changes, decisions),
        output_csv=output_csv,
        output_report=output_report,
    )

    return report


def save_cleaning_results(
    cleaned_df: pd.DataFrame,
    report: str,
    source_file: str,
    output_dir: Optional[str] = None,
) -> Dict[str, str]:
    """
    Save cleaned DataFrame and report to output directory.

    Args:
        cleaned_df: The cleaned DataFrame to save
        report: The markdown report string
        source_file: Original source filename (for naming)
        output_dir: Optional output directory (defaults to ./output)

    Returns:
        Dict with paths to saved files {'csv': path, 'report': path}
    """
    output_path = ensure_output_dir(output_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    source_name = Path(source_file).stem

    csv_filename = f"{source_name}_cleaned_{timestamp}.csv"
    report_filename = f"{source_name}_cleaning_log_{timestamp}.md"

    csv_path = output_path / csv_filename
    report_path = output_path / report_filename

    # Save files
    cleaned_df.to_csv(csv_path, index=False)
    report_path.write_text(report)

    return {
        'csv': str(csv_path),
        'report': str(report_path),
    }
