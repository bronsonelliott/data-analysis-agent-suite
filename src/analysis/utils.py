"""Shared utility functions for data analysis operations.

This module provides column type classification, confidence scoring,
and helper functions used across all analysis modules.
"""

import re
from typing import List, Optional, Tuple
from enum import Enum
import pandas as pd
import numpy as np


class ColumnType(Enum):
    """Classification of column data types for analysis."""
    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    DATE = "date"
    TEXT = "text"
    BOOLEAN = "boolean"
    UNKNOWN = "unknown"


def classify_column_type(series: pd.Series) -> ColumnType:
    """
    Classify a column's type for analysis purposes.

    This determines how the column should be analyzed:
    - NUMERIC: Use for correlations, statistics, trends
    - CATEGORICAL: Use for segmentation, grouping
    - DATE: Use for time-series analysis
    - TEXT: Free-form text, limited analysis
    - BOOLEAN: Binary classification

    Args:
        series: The pandas Series to classify

    Returns:
        ColumnType indicating the analysis category
    """
    non_null = series.dropna()

    if len(non_null) == 0:
        return ColumnType.UNKNOWN

    dtype_str = str(series.dtype).lower()

    # Check pandas dtype first
    if 'datetime' in dtype_str or 'timedelta' in dtype_str:
        return ColumnType.DATE

    if 'bool' in dtype_str:
        return ColumnType.BOOLEAN

    if 'int' in dtype_str or 'float' in dtype_str:
        return ColumnType.NUMERIC

    # For object dtype, infer from values
    if dtype_str == 'object' or 'string' in dtype_str:
        sample = non_null.head(100)
        unique_ratio = len(non_null.unique()) / len(non_null) if len(non_null) > 0 else 0

        # Check for boolean-like values
        bool_values = {'true', 'false', 'yes', 'no', '1', '0', 't', 'f', 'y', 'n'}
        if all(str(v).lower().strip() in bool_values for v in sample):
            return ColumnType.BOOLEAN

        # Check for date-like values
        try:
            pd.to_datetime(sample, errors='raise')
            return ColumnType.DATE
        except (ValueError, TypeError):
            pass

        # Check if numeric (including formatted numbers)
        import re
        numeric_count = 0
        for v in sample:
            s = str(v).strip()
            cleaned = re.sub(r'[$€£¥,\s()%]', '', s)
            try:
                float(cleaned)
                numeric_count += 1
            except (ValueError, TypeError):
                pass

        if numeric_count >= len(sample) * 0.8:
            return ColumnType.NUMERIC

        # Determine if categorical or free text
        # Categorical: low unique ratio, repeated values
        # Text: high unique ratio, likely unique values
        if unique_ratio < 0.5 or len(non_null.unique()) <= 50:
            return ColumnType.CATEGORICAL
        else:
            return ColumnType.TEXT

    return ColumnType.UNKNOWN


# Names like "id", "Row ID", "customer_id", "Date Key",
# and pandas' leftover index column "Unnamed: 0"
_ID_NAME_PATTERN = re.compile(r'(?:^|[\s_])(id|key)$|^unnamed:', re.IGNORECASE)

# "row_index" is an identifier but "consumer_price_index" is a metric,
# so names ending in "index" also need ID-like values (see below)
_INDEX_NAME_PATTERN = re.compile(r'(?:^|[\s_])index$', re.IGNORECASE)


def is_identifier_column(series: pd.Series) -> bool:
    """
    Detect numeric columns that are identifiers rather than measurements.

    IDs and keys are stored as numbers but have no numeric meaning, so
    trends, correlations and outlier checks on them produce nonsense
    findings ("strong upward trend in row_id").

    - Name ends in "id" or "key" as its own word, or is a pandas
      "Unnamed: N" index column -> identifier. Name alone decides, since a
      key like "Date Key" repeats across rows.
    - Name ends in "index" -> identifier only if the values are also
      unique whole numbers. A price index has decimals or repeats.

    A column whose values happen to be 1, 2, 3... but has no ID-like name
    is still treated as a metric.

    Args:
        series: The pandas Series to check (its name is used)

    Returns:
        True if the column looks like an identifier
    """
    name = str(series.name).strip() if series.name is not None else ''

    if _ID_NAME_PATTERN.search(name):
        return True

    if _INDEX_NAME_PATTERN.search(name):
        values = series.dropna()
        whole_numbers = pd.api.types.is_integer_dtype(values) or (
            pd.api.types.is_float_dtype(values) and (values % 1 == 0).all()
        )
        return bool(len(values) > 0 and whole_numbers and values.is_unique)

    return False


def identify_numeric_columns(df: pd.DataFrame, exclude_ids: bool = True) -> List[str]:
    """
    Identify all columns suitable for numeric analysis.

    Args:
        df: DataFrame to analyze
        exclude_ids: Skip identifier columns (IDs, keys, row counters)

    Returns:
        List of column names classified as numeric
    """
    numeric_cols = []
    for col in df.columns:
        if classify_column_type(df[col]) != ColumnType.NUMERIC:
            continue
        if exclude_ids and is_identifier_column(df[col]):
            continue
        numeric_cols.append(col)
    return numeric_cols


def identify_categorical_columns(df: pd.DataFrame, max_unique: int = 50) -> List[str]:
    """
    Identify columns suitable for categorical/segmentation analysis.

    Args:
        df: DataFrame to analyze
        max_unique: Maximum unique values to be considered categorical

    Returns:
        List of column names classified as categorical
    """
    categorical_cols = []
    for col in df.columns:
        col_type = classify_column_type(df[col])
        if col_type in (ColumnType.CATEGORICAL, ColumnType.BOOLEAN):
            # Verify unique count is reasonable for segmentation
            if df[col].nunique() <= max_unique:
                categorical_cols.append(col)
    return categorical_cols


def identify_date_columns(df: pd.DataFrame) -> List[str]:
    """
    Identify columns suitable for time-series analysis.

    Args:
        df: DataFrame to analyze

    Returns:
        List of column names classified as dates
    """
    date_cols = []
    for col in df.columns:
        if classify_column_type(df[col]) == ColumnType.DATE:
            date_cols.append(col)
    return date_cols


def calculate_confidence_score(
    sample_size: int,
    effect_size: float,
    p_value: Optional[float] = None,
    min_samples: int = 30
) -> float:
    """
    Calculate a confidence score (0.0-1.0) for a statistical finding.

    Considers:
    - Sample size (more data = higher confidence)
    - Effect size (stronger effects = higher confidence)
    - P-value if available (lower = higher confidence)

    Args:
        sample_size: Number of observations
        effect_size: Magnitude of the effect (e.g., correlation coefficient)
        p_value: Optional statistical p-value
        min_samples: Minimum samples for reasonable confidence

    Returns:
        Confidence score between 0.0 and 1.0
    """
    # Sample size factor (sigmoid curve, asymptotes at 1.0)
    sample_factor = min(1.0, sample_size / (min_samples * 10))
    sample_factor = 0.3 + 0.7 * sample_factor  # Range 0.3 to 1.0

    # Effect size factor (absolute value, capped at 1.0)
    effect_factor = min(1.0, abs(effect_size))

    # P-value factor if provided
    if p_value is not None:
        if p_value < 0.001:
            p_factor = 1.0
        elif p_value < 0.01:
            p_factor = 0.9
        elif p_value < 0.05:
            p_factor = 0.8
        elif p_value < 0.10:
            p_factor = 0.6
        else:
            p_factor = 0.4
    else:
        p_factor = 0.7  # Neutral if not provided

    # Weighted combination
    confidence = (0.3 * sample_factor + 0.4 * effect_factor + 0.3 * p_factor)

    return round(min(1.0, max(0.0, confidence)), 2)


def classify_correlation_strength(coefficient: float) -> str:
    """
    Classify correlation strength based on coefficient magnitude.

    Uses standard interpretation thresholds:
    - 0.0 - 0.19: none/negligible
    - 0.20 - 0.39: weak
    - 0.40 - 0.59: moderate
    - 0.60 - 0.79: strong
    - 0.80 - 1.0: very strong

    Args:
        coefficient: Correlation coefficient (-1 to 1)

    Returns:
        Human-readable strength classification
    """
    abs_coef = abs(coefficient)

    if abs_coef < 0.20:
        return "none"
    elif abs_coef < 0.40:
        return "weak"
    elif abs_coef < 0.60:
        return "moderate"
    elif abs_coef < 0.80:
        return "strong"
    else:
        return "very_strong"


def classify_importance(
    effect_size: float,
    confidence: float,
    actionable: bool = False
) -> str:
    """
    Classify the importance of a finding for prioritization.

    Args:
        effect_size: Magnitude of the finding (0-1 scale)
        confidence: Confidence score (0-1)
        actionable: Whether the finding is actionable

    Returns:
        'high', 'medium', or 'low'
    """
    score = (effect_size * 0.5) + (confidence * 0.3) + (0.2 if actionable else 0.0)

    if score >= 0.6:
        return "high"
    elif score >= 0.35:
        return "medium"
    else:
        return "low"


def safe_numeric_conversion(series: pd.Series) -> pd.Series:
    """
    Safely convert a series to numeric, handling currency and formatting.

    Cleans common formats:
    - Currency symbols ($, €, £, ¥)
    - Thousands separators
    - Percentage signs
    - Parentheses for negatives

    Args:
        series: Series to convert

    Returns:
        Numeric Series with NaN for unconvertible values
    """
    import re

    def clean_value(val):
        if pd.isna(val):
            return np.nan
        s = str(val).strip()

        # Handle parentheses as negative
        is_negative = s.startswith('(') and s.endswith(')')
        if is_negative:
            s = s[1:-1]

        # Remove currency symbols and formatting
        s = re.sub(r'[$€£¥,\s%]', '', s)

        # Handle European decimal format (1.234,56 -> 1234.56)
        if ',' in s and '.' in s:
            if s.rfind(',') > s.rfind('.'):
                s = s.replace('.', '').replace(',', '.')
        elif ',' in s and '.' not in s:
            # Could be European decimal or thousands separator
            # If single comma with 2 digits after, treat as decimal
            parts = s.split(',')
            if len(parts) == 2 and len(parts[1]) == 2:
                s = s.replace(',', '.')
            else:
                s = s.replace(',', '')

        try:
            val = float(s)
            return -val if is_negative else val
        except (ValueError, TypeError):
            return np.nan

    return series.apply(clean_value)


def format_number(value: float, precision: int = 2) -> str:
    """
    Format a number for human-readable display.

    Args:
        value: The number to format
        precision: Decimal places

    Returns:
        Formatted string with thousands separators
    """
    if pd.isna(value):
        return "N/A"

    if abs(value) >= 1_000_000:
        return f"{value/1_000_000:,.{precision}f}M"
    elif abs(value) >= 1_000:
        return f"{value/1_000:,.{precision}f}K"
    else:
        return f"{value:,.{precision}f}"


def format_percentage(value: float, precision: int = 1) -> str:
    """
    Format a value as a percentage.

    Args:
        value: The value (0-1 scale or percentage)
        precision: Decimal places

    Returns:
        Formatted percentage string
    """
    if pd.isna(value):
        return "N/A"

    # Assume values > 1 are already percentages
    if abs(value) <= 1:
        value = value * 100

    return f"{value:.{precision}f}%"
