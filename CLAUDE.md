# Data Analysis Agent Suite

A suite of Claude Code subagents for automated data analysis workflows. Transform raw CSV/Excel data into clean datasets, statistical insights, interactive visualizations, and executive-ready reports.

---

## Agents

Six specialized agents work together or independently:

| Agent | Purpose | Invoke |
|-------|---------|--------|
| **Data Cleaner** | Clean messy CSV/Excel data | `@data-cleaner` |
| **Data Analyzer** | Statistical analysis & insights | `@data-analyzer` |
| **Data Visualizer** | Interactive Plotly charts | `@data-visualizer` |
| **Report Writer** | Comprehensive analysis reports | `@report-writer` |
| **Executive Summarizer** | 1-2 page BLUF summaries | `@exec-summarizer` |
| **Full Analysis** | Run complete pipeline | `@full-analysis` |

### Agent Definitions

Agent prompts are in `./agents/`:
- `agents/data-cleaner.md`
- `agents/data-analyzer.md`
- `agents/data-visualizer.md`
- `agents/report-writer.md`
- `agents/exec-summarizer.md`
- `agents/full-analysis.md` (orchestrator)

---

## Pipeline Flow

```
Raw Data (CSV/Excel)
       ↓
@data-cleaner → cleaned CSV
       ↓
@data-analyzer → analysis JSON + findings
       ↓
  ├→ @data-visualizer → HTML dashboard + charts
  └→ @report-writer → full report (technical/business/executive style)
           ↓
     @exec-summarizer → 1-2 page executive summary
```

---

## Project Structure

```
data-analysis-agent-suite/
├── agents/                  # Agent prompt definitions (markdown with YAML frontmatter)
├── src/                     # Python utility modules
│   ├── cleaning/            # Data cleaning utilities
│   ├── analysis/            # Statistical analysis utilities
│   ├── visualization/       # Plotly chart generation
│   ├── reporting/           # Report generation
│   ├── summarization/       # Executive summary generation
│   └── orchestration/       # Pipeline coordination
├── templates/               # Report/dashboard templates
├── examples/                # Sample data files (sample_data.csv, sample_data.xlsx)
├── tests/                   # Test suite (627+ tests)
├── output/                  # Generated outputs (gitignored)
├── pyproject.toml           # Python dependencies
└── SPECIFICATION.md         # Full technical specification
```

---

## Python Modules

### `src.cleaning`
```python
from src.cleaning import (
    load_file,                    # Load CSV/Excel with encoding detection
    profile_dataframe,            # Generate data profile
    validate_dataframe,           # Detect data quality issues
    trim_whitespace,              # Remove leading/trailing whitespace
    standardize_column_names,     # Convert to snake_case
    normalize_dates,              # Standardize date formats
    parse_currency,               # Convert currency strings to numeric
    handle_duplicates,            # Remove/flag duplicates
    handle_missing_values,        # Fill/drop missing values
    handle_outliers,              # Flag/cap outliers
    generate_cleaning_report,     # Generate audit trail report
)
```

### `src.analysis`
```python
from src.analysis import (
    # Statistics
    calculate_descriptive_stats,
    analyze_distribution,
    analyze_all_numeric,
    find_statistical_anomalies,
    # Correlations
    find_all_correlations,
    generate_correlation_matrix,
    find_correlation_insights,
    # Trends
    detect_date_column,
    analyze_trend,
    detect_seasonality,
    find_trend_insights,
    # Segmentation
    compare_segments,
    find_segment_insights,
    # Output
    generate_analysis_report,
    save_analysis_results,
)
```

### `src.visualization`
```python
from src.visualization import (
    recommend_visualizations,     # Auto-recommend charts based on data
    generate_all_charts,          # Generate all recommended charts
    generate_dashboard,           # Create index.html dashboard
    create_manifest,              # Create chart_manifest.json
    save_manifest,
    # Individual chart creators
    create_line_chart,
    create_bar_chart,
    create_scatter_chart,
    create_heatmap,
    create_box_plot,
    create_pie_chart,
    create_histogram,
)
```

### `src.reporting`
```python
from src.reporting import (
    # Styles: "technical", "business", "executive"
    get_style,
    create_default_config,
    # Loading
    find_analysis_files,
    find_visualization_manifest,
    create_report_input,
    # Generation
    generate_report,
    save_report,
)
```

### `src.summarization`
```python
from src.summarization import (
    create_summary_input,
    extract_all,                  # Extract BLUF, metrics, findings, actions
    generate_summary,
    save_summary,
)
```

### `src.orchestration`
```python
from src.orchestration import (
    PipelineStage,
    PipelineConfig,
    PipelineState,
    validate_input_file,
    create_pipeline_manifest,
    save_pipeline_manifest,
)
```

---

## Development

### Setup
```bash
# Install dependencies
uv sync

# Install dev dependencies
uv sync --all-extras
```

### Running Tests
```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src

# Run specific test file
uv run pytest tests/test_loader.py

# Run tests matching pattern
uv run pytest -k "test_correlation"
```

### Python Version
- Requires Python 3.11+ (see `.python-version`)

### Dependencies
- pandas >= 2.0.0
- numpy >= 1.24.0
- scipy >= 1.10.0
- plotly >= 5.0.0
- openpyxl >= 3.1.0 (Excel support)
- chardet >= 5.0.0 (encoding detection)

---

## Output Conventions

All generated files go to `./output/` with timestamped filenames:

| Agent | Output Files |
|-------|--------------|
| Data Cleaner | `{source}_cleaned_{timestamp}.csv`, `{source}_cleaning_log_{timestamp}.md` |
| Data Analyzer | `{source}_analysis_{timestamp}.json`, `{source}_analysis_{timestamp}.md` |
| Data Visualizer | `{source}_visualizations_{timestamp}/` (directory with `index.html`, charts, `chart_manifest.json`) |
| Report Writer | `{source}_report_{timestamp}.md` |
| Exec Summarizer | `{source}_executive_summary_{timestamp}.md` |
| Full Analysis | All of the above + `{source}_pipeline_manifest_{timestamp}.json` |

---

## Agent Behavior Guidelines

### Auto-Fix vs Ask User

**Agents auto-fix obvious issues without asking:**
- Whitespace trimming
- Column name standardization (snake_case)
- Encoding issues (mojibake)
- Currency symbol parsing

**Agents always ask for ambiguous issues:**
- Missing value strategy (drop, fill, leave)
- Date format interpretation (01/02 = Jan 2 or Feb 1?)
- Duplicate handling strategy
- Outlier treatment

### Error Handling
- Agents explain errors clearly with suggested fixes
- After 3 failed attempts, stop and reassess with user
- Critical stages (cleaning, analysis) stop the pipeline on failure
- Optional stages (visualization, summary) log warnings and continue

### Report Writing Styles

| Style | Audience | Characteristics |
|-------|----------|-----------------|
| `technical` | Data teams | Full statistics, methodology, confidence intervals |
| `business` | Stakeholders | Insight-focused, actionable, plain language |
| `executive` | Leadership | High-level, strategic, concise (max 5 findings) |

---

## Sample Data

Test files are in `./examples/`:
- `sample_data.csv` - Sales data with intentional quality issues
- `sample_data.xlsx` - Same data in Excel format

---

## Key Files

- `SPECIFICATION.md` - Full technical specification with detailed agent behaviors
- `TODO.md` - Development progress tracker
- `sub-agents.md` - Agent design documentation

---

## Notes

- The `name` field in agent YAML frontmatter is the machine-readable identifier (e.g., `data-cleaner`)
- Agent invocation uses `@{name}` syntax (e.g., `@data-cleaner`)
- All agents are stateless - each invocation starts fresh
- Output files are timestamped to avoid overwrites
