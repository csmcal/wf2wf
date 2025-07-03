# Full Data Analysis Workflow Example

This directory contains a complete data analysis workflow that demonstrates various Snakemake features and their translation to Condor DAG. The workflow (`data_analysis.smk`) implements a typical data analysis pipeline with the following stages:

1. Data Preprocessing
   - Raw data cleaning and sorting
   - Resource allocation (memory, disk)

2. Data Analysis
   - Python-based analysis with conda environment
   - Multi-threaded processing
   - Intermediate data generation

3. Statistical Analysis
   - Statistical computations with configurable parameters
   - JSON output format

4. Summary Generation
   - Multi-input dependency handling
   - Data summarization

5. Visualization
   - R-based plotting with dedicated conda environment
   - Resource management

6. Report Generation
   - HTML report creation
   - Multi-input integration
   - Configurable report title

7. Quality Control
   - Benchmarking capabilities
   - Log file generation
   - Quality checks

## Directory Structure

```
full_workflow/
├── data_analysis.smk    # Main workflow file
├── config.yaml         # Configuration file
├── data/              # Input data directory
├── envs/              # Conda environment definitions
│   ├── analysis.yaml
│   └── r_env.yaml
├── scripts/           # Analysis scripts
│   ├── analyze.py
│   ├── compute_stats.py
│   ├── create_plots.R
│   ├── generate_report.py
│   ├── intensive_analysis.py
│   ├── quality_check.py
│   └── summarize.py
└── results/           # Output directory (created during execution)
```

## Usage

To run this example:

```bash
snake2dagman --snakefile examples/full_workflow/data_analysis.smk
```

## Features Demonstrated

- ✅ Configuration file integration
- ✅ Resource allocation (memory, disk, threads)
- ✅ Conda environment management
- ✅ Script integration (Python and R)
- ✅ Multi-input/output handling
- ✅ Benchmarking
- ✅ Log file generation
- ✅ Parameter configuration
- ✅ Quality control
- ✅ Complex dependency chains
