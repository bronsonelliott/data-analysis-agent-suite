# Data Analysis Agent Suite

> **Status: retired (2026-10-06).** No longer developed as a product; kept as a learning artifact. Anthropic's `data` plugin (anthropics/knowledge-work-plugins) covers the same jobs. The Python library works and is tested (647 tests), but the agents in `agents/` do not load in Claude Code. Decision record: `~/claude/lab/MEMORY.md`.

A suite of Claude Code subagents that automate data analysis workflows. Transform raw CSV/Excel data into clean datasets, statistical insights, interactive visualizations, and executive-ready reports.

## Agents

| Agent | Description |
|-------|-------------|
| `@data-cleaner` | Clean messy CSV/Excel data (duplicates, missing values, dates, outliers) |
| `@data-analyzer` | Discover patterns, correlations, trends, and statistical insights |
| `@data-visualizer` | Generate interactive Plotly charts and dashboards |
| `@report-writer` | Create comprehensive analysis reports (technical/business/executive styles) |
| `@exec-summarizer` | Distill findings into 1-2 page executive summaries |
| `@full-analysis` | **Pipeline orchestrator** - runs all agents end-to-end |

## Quick Start

### Prerequisites

- [Claude Code CLI](https://claude.ai/claude-code) installed
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd data-analysis-agent-suite

# Install dependencies
uv sync
```

### Usage

#### Option 1: Full Pipeline (Recommended)

Run the complete analysis pipeline on your data:

```
@full-analysis ./data/sales_q4.csv
```

This runs all 5 agents in sequence and produces:
- Cleaned dataset
- Statistical analysis (JSON + Markdown)
- Interactive dashboard with charts
- Comprehensive report
- Executive summary

#### Option 2: Individual Agents

Use agents independently for specific tasks:

```
# Clean messy data
@data-cleaner ./data/raw_sales.csv

# Analyze clean data
@data-analyzer ./output/raw_sales_cleaned_20260124.csv

# Create visualizations
@data-visualizer ./output/raw_sales_cleaned_20260124.csv

# Generate a report
@report-writer

# Create executive summary
@exec-summarizer
```

#### Option 3: Custom Combinations

Chain specific agents as needed:

```
# Clean → Visualize (skip analysis/reports)
@data-cleaner ./data/quarterly.csv
@data-visualizer ./output/quarterly_cleaned_20260124.csv

# Clean → Analyze → Executive Summary (skip visualizations/full report)
@data-cleaner ./data/metrics.xlsx
@data-analyzer ./output/metrics_cleaned_20260124.csv
@exec-summarizer
```

## Pipeline Flow

```
📥 Raw Data (CSV/Excel)
        ↓
   @data-cleaner
        ↓
   Cleaned CSV
        ↓
   @data-analyzer
        ↓
   Analysis JSON + Findings
        ↓
   ┌────┴────┐
   ↓         ↓
@data-     @report-
visualizer  writer
   ↓         ↓
Dashboard   Report
   └────┬────┘
        ↓
   @exec-summarizer
        ↓
📤 Executive Summary
```

## Output Files

All outputs are saved to `./output/` with timestamped filenames:

| Agent | Output |
|-------|--------|
| Data Cleaner | `{name}_cleaned_{timestamp}.csv` |
| Data Analyzer | `{name}_analysis_{timestamp}.json` |
| Data Visualizer | `{name}_visualizations_{timestamp}/index.html` |
| Report Writer | `{name}_report_{timestamp}.md` |
| Exec Summarizer | `{name}_executive_summary_{timestamp}.md` |

## Project Structure

```
data-analysis-agent-suite/
├── agents/                  # Agent prompt definitions
│   ├── data-cleaner.md
│   ├── data-analyzer.md
│   ├── data-visualizer.md
│   ├── report-writer.md
│   ├── exec-summarizer.md
│   └── full-analysis.md     # Pipeline orchestrator
├── src/                     # Python utility modules
│   ├── cleaning/            # Data cleaning utilities
│   ├── analysis/            # Statistical analysis
│   ├── visualization/       # Plotly chart generation
│   ├── reporting/           # Report generation
│   ├── summarization/       # Executive summaries
│   └── orchestration/       # Pipeline coordination
├── templates/               # Report/dashboard templates
├── examples/                # Sample data files
├── tests/                   # Test suite (627+ tests)
└── output/                  # Generated outputs
```

## Examples

Sample data files are included in `./examples/`:

```bash
# Try with the included sample data
@full-analysis ./examples/sample_data.csv
```

## Report Styles

The `@report-writer` agent supports three writing styles:

| Style | Best For | Characteristics |
|-------|----------|-----------------|
| `technical` | Data teams | Full statistics, methodology, confidence intervals |
| `business` | Stakeholders | Insight-focused, actionable recommendations |
| `executive` | Leadership | High-level, strategic, concise |

## Development

```bash
# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src

# Run specific test file
uv run pytest tests/test_loader.py
```

## Documentation

- `CLAUDE.md` - Technical reference for Claude (APIs, modules, conventions)
- `SPECIFICATION.md` - Full technical specification
- `TODO.md` - Development progress tracker

## License

[Add license information]
