# wf2wf: Universal Workflow Format Converter

**Version 0.2 – Production Implementation with Enhanced Metadata Preservation**

---

## 📋 **Implementation Status Notice**  *(last update 2025-06-25)*

**This design document presents both current implementation and future vision. Key status indicators:**

- ✅ **Implemented**: Features currently working in the codebase
- 🚧 **Partial**: Basic implementation exists, enhancements planned
- ❌ **Planned**: Future development, not yet implemented

**Quick Status Summary:**
- **Core Formats**: ✅ Snakemake, DAGMan, CWL, 🚧 Nextflow, ✅ WDL, ✅ Galaxy
- **Advanced Features**: ✅ Metadata preservation, 🚧 Environment management, ❌ Dynamic workflows
- **Enterprise Features**: ❌ Workflow registries, monitoring, regulatory compliance tools

See [Implementation Status and Roadmap](#implementation-status-and-roadmap) for complete details.

---

## Table of Contents

1. [Vision and Motivation](#vision-and-motivation)
2. [Core Architecture](#core-architecture)
3. [Intermediate Representation](#intermediate-representation)
4. [Current Implementation Status](#current-implementation-status)
5. [Workflow Analysis Pipeline](#workflow-analysis-pipeline)
6. [Environment Management](#environment-management)
7. [HTCondor Integration](#htcondor-integration)
8. [Enhanced CWL/BCO Support](#enhanced-cwlbco-support)
9. [Testing & CI](#testing--ci)
10. [Future Roadmap](#future-roadmap)

---

## Vision and Motivation

### The Multi-Format Challenge

Modern computational research groups accumulate heterogeneous workflow definitions across multiple platforms:

- **Snakemake**: Rapid prototyping and development
- **HTCondor DAGMan**: Campus cluster execution
- **Nextflow**: Cloud and container-based workflows
- **CWL/WDL**: Collaborative sharing and regulatory compliance
- **Galaxy**: User-friendly interfaces and teaching

Each format has distinct strengths but creates silos that limit collaboration and reproducibility.

### The wf2wf Solution

`wf2wf` provides a **universal workflow converter** built around a lossless intermediate representation (IR) that preserves complete metadata across format conversions.

```
Snakemake  ─┐
Nextflow   ─┼─► Enhanced IR ─► DAGMan
CWL        ─┤   (wf-json)     ├─► Nextflow
WDL        ─┘                 ├─► CWL
                              └─► Snakemake
```

### Core Principles

1. **Lossless Conversion**: Full round-trip fidelity with comprehensive metadata preservation
2. **IR-Centric Architecture**: Never translate A→B directly; always A→IR→B
3. **Standards Compliance**: Full CWL v1.2.1 and BCO IEEE 2791-2020 support
4. **Production Ready**: Robust error handling, extensive testing, and real-world validation
5. **Extensible Design**: Plugin architecture for new workflow engines
6. **Regulatory Support**: FDA-compliant BCO integration for pharmaceutical workflows

---

## Core Architecture

### High-Level System Design

```
┌─────────────────────────────────────────────────────────────────┐
│                        wf2wf Core System                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────────┐    ┌─────────────┐     │
│  │  Importers  │    │ Enhanced IR     │    │  Exporters  │     │
│  │             │    │ (wf-json)       │    │             │     │
│  │ ┌─────────┐ │    │                 │    │ ┌─────────┐ │     │
│  │ │Snakemake│ │    │ ┌─────────────┐ │    │ │ DAGMan  │ │     │
│  │ │   CWL   │ ├───►│ │ Workflow    │ │◄───┤ │Nextflow │ │     │
│  │ │ DAGMan  │ │    │ │   Tasks     │ │    │ │   CWL   │ │     │
│  │ │Nextflow │ │    │ │   Edges     │ │    │ │Snakemake│ │     │
│  │ └─────────┘ │    │ │ Metadata    │ │    │ └─────────┘ │     │
│  └─────────────┘    │ │ Provenance  │ │    └─────────────┘     │
│                     │ │   BCO       │ │                        │
│                     │ └─────────────┘ │                        │
│                     └─────────────────┘                        │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐     │
│  │   Schema    │    │ Validation  │    │  CLI & Config   │     │
│  │ Management  │    │ Framework   │    │   Management    │     │
│  └─────────────┘    └─────────────┘    └─────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

- **Importers**: Parse native workflow formats into the enhanced IR
- **Exporters**: Generate native workflow formats from the enhanced IR
- **Enhanced IR**: Unified data model preserving all metadata across formats
- **Schema Management**: Versioned JSON schemas with validation
- **CLI Framework**: User-friendly command-line interface with configuration management

---

## Intermediate Representation

### Design Philosophy

The Enhanced IR serves as the universal "Rosetta Stone" for workflow formats, designed to:

- **Preserve Complete Metadata**: Author information, documentation, provenance
- **Support Advanced Features**: Conditional execution, scatter/gather, expressions
- **Enable Regulatory Compliance**: BCO integration for FDA submissions
- **Maintain Backward Compatibility**: Legacy format support during transition

### Core Data Structures

```python
@dataclass
class Workflow:
    """Enhanced workflow representation with full metadata support."""
    # Core identification
    name: str
    version: str = "1.0"
    label: Optional[str] = None
    doc: Optional[str] = None

    # Workflow structure
    tasks: Dict[str, Task] = field(default_factory=dict)
    edges: List[Edge] = field(default_factory=list)

    # Enhanced I/O with CWL parameter specifications
    inputs: List[ParameterSpec] = field(default_factory=list)
    outputs: List[ParameterSpec] = field(default_factory=list)

    # Requirements and hints system
    requirements: List[RequirementSpec] = field(default_factory=list)
    hints: List[RequirementSpec] = field(default_factory=list)

    # Metadata and provenance
    provenance: Optional[ProvenanceSpec] = None
    documentation: Optional[DocumentationSpec] = None
    intent: List[str] = field(default_factory=list)  # Ontology IRIs
    cwl_version: Optional[str] = None

    # BCO integration for regulatory compliance
    bco_spec: Optional[BCOSpec] = None

    # Legacy compatibility
    config: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Task:
    """Enhanced task representation supporting all workflow engine features."""
    # Core identification
    id: str
    label: Optional[str] = None
    doc: Optional[str] = None

    # Execution specifications
    command: Optional[str] = None
    script: Optional[str] = None

    # Enhanced I/O
    inputs: List[ParameterSpec] = field(default_factory=list)
    outputs: List[ParameterSpec] = field(default_factory=list)

    # Advanced execution features
    when: Optional[str] = None  # Conditional execution
    scatter: Optional[ScatterSpec] = None

    # Resource and environment specifications
    resources: ResourceSpec = field(default_factory=ResourceSpec)
    environment: EnvironmentSpec = field(default_factory=EnvironmentSpec)
    requirements: List[RequirementSpec] = field(default_factory=list)
    hints: List[RequirementSpec] = field(default_factory=list)

    # Metadata and provenance
    provenance: Optional[ProvenanceSpec] = None
    documentation: Optional[DocumentationSpec] = None
    intent: List[str] = field(default_factory=list)

    # Legacy compatibility
    params: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    retry: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)
```

### Schema Versioning and Validation

The IR uses versioned JSON schemas for validation and evolution:

```json
{
  "$schema": "https://wf2wf.dev/schemas/v0.1/wf.json",
  "name": "example_workflow",
  "version": "1.0",
  "tasks": {
    "analyze_data": {
      "command": "python analyze.py",
      "inputs": [{"id": "input_file", "type": "File"}],
      "outputs": [{"id": "results", "type": "File"}],
      "resources": {"cpu": 4, "mem_mb": 8000, "gpu": 1},
      "environment": {"container": "docker://python:3.9"},
      "requirements": [{"class_name": "DockerRequirement"}],
      "meta": {"tags": ["analysis", "gpu"]}
    }
  },
  "edges": [{"parent": "preprocess", "child": "analyze_data"}]
}
```

### 3.6  Why the IR is *not* literally CWL

> TL;DR – CWL is an excellent design reference, but using it *as‐is* for the
> intermediate representation would restrict support for engines whose concepts
> cannot be modelled in pure CWL.  A lean, CWL-inspired but engine-agnostic IR
> gives us the best of both worlds.

**Pros of re-using CWL verbatim**
1.  Open, versioned standard & existing tooling (`cwltool`, validators, GUIs).
2.  Rich type system plus `scatter`, `when`, `requirements`, `expressionLib` –
    we already need most of that.
3.  Removes one mapping hop for the *CWL → IR → CWL* path.

**Why it becomes limiting**
1.  *Engine-specific constructs*: HTCondor's `RETRY`/`PRIORITY`, Snakemake's
    dynamic checkpoints, Nextflow's channel semantics, Galaxy UI metadata, WDL
    runtime dictionaries – none of these have first-class CWL equivalents.  We
    would end up inventing non-standard extensions anyway.
2.  *Static DAG assumption*: CWL forbids cycles and loops; other engines allow
    conditional re-entrancy or iterative channels.
3.  *Verbosity & developer ergonomics*: CWL YAML for record/enum types is
    verbose; a purpose-built dataclass IR keeps importer/exporter code small
    and fixtures readable.
4.  *Governance friction*: tying IR changes to the CWL release cycle slows
    iteration.  We already added BCO fields and environment-build provenance
    without waiting for a CWL spec update.
5.  *Asymmetric lossiness*: If CWL is the IR, every non-CWL exporter must cope
    with CWL constructs it cannot express – making loss-mapping harder.

**Design stance** – wf2wf therefore keeps a *CWL-inspired* schema (`TypeSpec`,
`ParameterSpec`, `ScatterSpec`, …) but retains neutral fields (`resources`,
`environment`, `meta`, engine-specific extensions).  Importers/exporters map to
CWL faithfully, while other engines can ignore or down-convert features they do
not support without breaking the IR contract.

---

## Current Implementation Status

### Production-Ready Components

#### ✅ Snakemake → DAGMan Conversion
- **Comprehensive Snakefile Parsing**: Handles wildcards, resources, containers, conda environments
- **Dual-Source Analysis**: Static parsing + dynamic dry-run execution
- **Advanced Environment Management**: Conda, Docker, Apptainer integration
- **Robust Error Handling**: Graceful degradation and detailed warnings
- **Production Deployment**: Used in real HPC environments

#### ✅ DAGMan Enhanced Support
- **Inline Submit Descriptions**: Modern HTCondor inline job syntax support
- **Traditional Submit Files**: Backward compatibility with external .sub files
- **Mixed Format Support**: Seamless handling of hybrid DAG files
- **Complete Round-Trip**: DAGMan → IR → DAGMan with full metadata preservation
- **Resource Translation**: Comprehensive CPU/memory/disk/GPU mapping

#### ✅ Core Infrastructure
- **Enhanced IR Implementation**: Full dataclass hierarchy with validation
- **Schema Management**: Versioned JSON schemas with migration support
- **CLI Framework**: User-friendly command-line interface
- **Comprehensive Testing**: 100+ tests covering edge cases and error conditions
- **Configuration System**: JSON-based config with CLI overrides

### Implementation Highlights

#### DAGMan Inline Submit Support
Recent enhancement supporting HTCondor's modern inline submit syntax:

```dag
JOB analyze_task {
    executable = /path/to/script.sh
    request_cpus = 4
    request_memory = 8192MB
    request_gpus = 1
    universe = docker
    docker_image = tensorflow/tensorflow:latest
    queue
}
```

**Features:**
- Full resource specification support
- Container integration (Docker, Singularity)
- Custom HTCondor attributes
- Round-trip preservation
- CLI flag: `--inline-submit`

#### Advanced Environment Management (Planned)
```python
# Planned: Automatic conda environment setup
wf2wf convert --snakefile workflow.smk \
              --out-format dagman \
              --auto-conda-setup \
              --conda-prefix /shared/envs

# Planned: Docker container integration
wf2wf convert --snakefile workflow.smk \
              --out-format dagman \
              --auto-docker-build \
              --docker-registry myregistry.com
```

---

## Workflow Analysis Pipeline

### Multi-Stage Conversion Process

#### Stage 1: Source Analysis
```python
def analyze_workflow_source(input_path, format_hint=None, **opts):
    """Comprehensive workflow source analysis."""
    # Format detection and validation
    # Static parsing for structure extraction
    # Dynamic analysis for runtime information
    # Metadata extraction and validation
```

#### Stage 2: IR Construction
```python
def build_enhanced_ir(analysis_results, preservation_level="full"):
    """Construct enhanced IR with configurable preservation."""
    # Core workflow structure mapping
    # Metadata and provenance integration
    # Advanced feature preservation
    # Validation and consistency checking
```

#### Stage 3: Target Generation
```python
def generate_target_format(workflow_ir, target_format, **export_opts):
    """Generate target format with optimization options."""
    # Format-specific optimization
    # Feature mapping and warnings
    # Output validation
    # Documentation generation
```

### Snakemake Analysis Deep Dive

#### Static Parsing Capabilities
- **Rule Extraction**: Complete rule definition parsing with multi-line support
- **Resource Parsing**: Memory, CPU, disk, GPU specifications with unit conversion
- **Environment Detection**: Conda, container, and module specifications
- **Script Handling**: Shell commands, run blocks, and external scripts
- **Wildcard Analysis**: Pattern extraction and constraint identification

#### Dynamic Analysis Integration
```python
# Snakemake dry-run integration
def extract_dynamic_information(snakefile_path, workdir=None):
    """Extract runtime workflow information."""
    jobs = run_snakemake_dryrun(snakefile_path, workdir)
    dependencies = extract_dag_structure(snakefile_path, workdir)
    return synthesize_workflow_data(jobs, dependencies)
```

**Benefits:**
- Concrete job enumeration with wildcard resolution
- Accurate dependency graph extraction
- Resource requirement validation
- Input/output file tracking

---

## Environment Management

### Multi-Platform Environment Support

#### Conda Environment Handling
```python
@dataclass
class CondaEnvironmentSpec:
    """Conda environment specification with content hashing."""
    file_path: str
    content_hash: str
    dependencies: List[str]
    channels: List[str]
    setup_strategy: str = "manual"  # manual, auto, docker, apptainer
```

**Strategies:**
1. **Manual Setup**: User-managed environments with validation warnings
2. **Automatic Setup**: Dedicated setup jobs with dependency injection
3. **Docker Integration**: Containerized environments with registry support
4. **Apptainer Conversion**: HPC-optimized container format

#### Container Integration
```python
def handle_container_environments(workflow_ir, container_backend="docker"):
    """Comprehensive container environment management."""
    # Docker image building and registry management
    # Apptainer/Singularity conversion for HPC
    # Container optimization and caching
    # Security scanning and validation
```

### Advanced Features (Planned)
- **Content-Based Deduplication**: Identical environments shared across jobs
- **Dependency Injection**: Automatic setup job creation and ordering
- **Registry Management**: Private registry support with authentication
- **Container Optimization**: Layer caching and efficient builds

---

## HTCondor Integration

### Enhanced DAGMan Support

#### Submit File Generation
```python
def generate_condor_submit_files(workflow_ir, inline_submit=False, **opts):
    """Generate HTCondor submit descriptions with advanced features."""
    if inline_submit:
        return generate_inline_submit_dag(workflow_ir, **opts)
    else:
        return generate_traditional_submit_files(workflow_ir, **opts)
```

#### Resource Translation Matrix
| Workflow Engine | HTCondor Equivalent | Conversion Notes |
|----------------|-------------------|------------------|
| `threads` | `request_cpus` | Direct mapping |
| `mem_mb` / `mem_gb` | `request_memory` | Unit normalization |
| `disk_mb` / `disk_gb` | `request_disk` | Unit normalization |
| `gpu` | `request_gpus` | GPU count specification |
| `gpu_mem_mb` | `gpus_minimum_memory` | GPU memory requirements |
| `gpu_capability` | `gpus_minimum_capability` | CUDA compute capability |
| Custom attributes | `+ClassAd` / `requirements` | HTCondor-specific features |

#### Advanced HTCondor Features
- **Custom ClassAds**: Full support for HTCondor-specific attributes
- **Requirements Expressions**: Complex job placement constraints
- **Priority Management**: Job priority and preemption handling
- **Retry Logic**: Sophisticated error recovery strategies
- **Monitoring Integration**: HTCondor monitoring and reporting tools

### Inline Submit Description Support
Modern HTCondor syntax with comprehensive feature support:

```dag
# Workflow metadata preservation
# Original workflow name: bioinformatics_pipeline
# Original workflow version: 2.1.0

JOB preprocess_data {
    executable = scripts/preprocess.sh
    request_cpus = 2
    request_memory = 4096MB
    request_disk = 10240MB
    universe = docker
    docker_image = bioconda/bioconda-utils:latest
    requirements = (OpSysAndVer == "CentOS7")
    +WantGPULab = false
    +ProjectName = "BioinformaticsWorkflow"
    queue
}

JOB analyze_variants {
    executable = scripts/analyze.sh
    request_cpus = 8
    request_memory = 16384MB
    request_gpus = 1
    universe = docker
    docker_image = broadinstitute/gatk:latest
    requirements = (Memory > 16000) && (HasGPU == True)
    +WantGPULab = true
    queue
}

PARENT preprocess_data CHILD analyze_variants
RETRY analyze_variants 2
PRIORITY analyze_variants 10
```

---

## Enhanced CWL/BCO Support

### Complete CWL v1.2.1 Integration

#### Advanced CWL Features
- **Conditional Execution**: `when` expressions for step-level conditionals
- **Scatter/Gather Operations**: Full scatter support (dotproduct, crossproduct)
- **Expression System**: JavaScript expression evaluation with security sandboxing
- **Secondary Files**: Automatic secondary file discovery and staging
- **Advanced Type System**: Record types, enum types, and custom schemas

#### CWL Round-Trip Preservation
```python
def preserve_cwl_metadata(cwl_workflow, target_format):
    """Ensure complete CWL metadata preservation across conversions."""
    # Preserve all CWL-specific attributes in IR metadata
    # Map advanced features to target format equivalents
    # Generate warnings for lossy conversions
    # Maintain provenance tracking
```

### BCO Integration for Regulatory Compliance

#### IEEE 2791-2020 Support
```python
@dataclass
class BCOSpec:
    """BioCompute Object specification for regulatory compliance."""
    object_id: str
    spec_version: str = "https://w3id.org/ieee/ieee-2791-schema/2791object.json"

    # Nine BCO Domains
    provenance_domain: Dict[str, Any]    # Workflow provenance and authorship
    usability_domain: List[str]          # Scientific application domains
    description_domain: Dict[str, Any]   # Human-readable description
    execution_domain: Dict[str, Any]     # Computational environment
    parametric_domain: List[Dict]        # Input parameters and datasets
    io_domain: Dict[str, Any]           # Input and output specifications
    error_domain: Dict[str, Any]        # Error handling and validation
    extension_domain: List[Dict]        # Custom extensions
```

#### FDA Submission Workflow (Planned)
```python
def generate_fda_submission_package(workflow_ir, submission_type="510k"):
    """Generate FDA-compliant submission package."""
    # BCO document generation
    # CWL workflow packaging
    # Validation report generation
    # Provenance documentation
    # Reproducibility verification
```

### Benefits for Regulatory Science (Future)
- **Reproducibility**: Complete computational provenance tracking
- **Validation**: Comprehensive validation frameworks
- **Documentation**: Rich metadata and documentation generation
- **Compliance**: FDA-approved BCO standard support

---

## Testing & CI

### Comprehensive Test Strategy

#### Test Categories
1. **Unit Tests**: Individual component validation (Currently: ~150 tests)
2. **Integration Tests**: End-to-end conversion workflows (Currently: ~40 tests)
3. **Round-Trip Tests**: Format preservation validation (Currently: ~20 tests)
4. **Error Handling Tests**: Robustness and recovery testing (Currently: ~9 tests)
5. **Specialized Tests**: Advanced features and edge cases (Total: 219 tests)

#### Test Infrastructure
```python
# Automated test data management
@pytest.fixture
def persistent_test_output(test_output_dir, request):
    """Create test-specific output directories."""
    test_dir = test_output_dir / request.node.name
    test_dir.mkdir(exist_ok=True)
    return test_dir

# Round-trip validation framework
def test_format_round_trip(workflow_path, format_pair):
    """Validate lossless round-trip conversion."""
    original = load_workflow(workflow_path)
    converted = convert_workflow(original, format_pair[0], format_pair[1])
    restored = convert_workflow(converted, format_pair[1], format_pair[0])
    assert workflows_equivalent(original, restored)
```

#### Quality Metrics
- **Code Coverage**: >95% test coverage across all modules (Currently: ~219 test functions)
- **Error Recovery**: Graceful degradation for all failure modes
- **Round-Trip Validation**: Lossless conversion verification for all supported formats

### Real-World Validation

#### Current Deployments
- **Academic Research**: Used in computational biology and bioinformatics workflows
- **HPC Integration**: Tested with HTCondor clusters for job submission
- **Format Conversion**: Proven Snakemake → DAGMan conversion in production use

#### Example Workflows
```
examples/
├── basic/                    # Simple workflow patterns
│   ├── linear.smk           # Sequential processing
│   ├── parallel.smk         # Parallel processing
│   └── mixed.smk            # Mixed patterns
├── advanced/                # Complex workflow features
│   ├── checkpoints.smk      # Dynamic workflows
│   ├── containers.smk       # Container integration
│   └── gpu_workflows.smk    # GPU acceleration
├── real_world/              # Production workflows
│   ├── genomics_pipeline/   # Variant calling pipeline
│   ├── ml_training/         # Machine learning workflows
│   └── image_processing/    # Computer vision pipelines
└── regulatory/              # Compliance examples
    ├── fda_submission/      # FDA 510(k) example
    └── gmp_validation/      # GMP compliance example
```

---

## Implementation Status and Roadmap

### ✅ **Currently Implemented (Production Ready)**

#### Core Infrastructure
- **Enhanced IR**: Complete dataclass hierarchy with CWL v1.2.1 and BCO support
- **Schema Management**: Versioned JSON schemas with validation
- **CLI Framework**: Comprehensive command-line interface with auto-detection
- **Testing Framework**: 219 test functions across unit, integration, and round-trip tests

#### Format Support (Fully Implemented)
- **Snakemake Import/Export**: Complete static parsing + dynamic dry-run analysis
- **DAGMan Import/Export**: Traditional submit files + modern inline submit descriptions
- **CWL Import/Export**: Full v1.2.1 support with advanced metadata preservation
- **Nextflow Import/Export**: Basic DSL2 support with process and workflow parsing

#### Advanced Features (Implemented)
- **Metadata Preservation**: Complete provenance, documentation, and BCO integration
- **Environment Management**: Conda, Docker, and Apptainer container support
- **Resource Translation**: Comprehensive CPU/memory/disk/GPU mapping across formats
- **DAGMan Inline Submit**: Modern HTCondor syntax with full feature parity

### 🚧 **Partially Implemented (Needs Enhancement)**

#### CWL/BCO Integration
- **Status**: Data structures complete, basic import/export working
- **Missing**: Advanced BCO validation, FDA submission workflows, regulatory compliance tools
- **Timeline**: Enhancement planned for Q2 2024

#### Nextflow Support
- **Status**: Basic DSL2 import/export implemented
- **Missing**: Advanced channel analysis, module/subworkflow support, configuration management
- **Timeline**: Full implementation planned for Q3 2024

#### Environment Management
- **Status**: Basic environment specifications implemented
- **Missing**: Automatic environment setup, content-based deduplication, registry management
- **Timeline**: Advanced features planned for Q4 2024

### ❌ **Not Implemented (Future Development)**

#### Missing Workflow Engines
- **WDL Support**: Complete import/export for Workflow Description Language
- **Galaxy Integration**: Galaxy workflow format support
- **Apache Airflow**: DAG format interoperability

#### Advanced Features (Future)
- **Dynamic Workflows**: Advanced checkpoint handling, conditional execution
- **Parameter Sweeps**: Automated parameter exploration workflows
- **Workflow Registries**: Enterprise workflow management and versioning
- **Advanced Monitoring**: Conversion analytics and usage tracking

#### Enterprise Features (Long-term Vision)
- **Regulatory Compliance**: 21 CFR Part 11, GDPR compliance frameworks
- **Audit Trails**: Comprehensive logging and reporting
- **Cloud Integration**: Native cloud platform execution support

---

## Development Roadmap

### **Phase 1: Core Completion (Q2 2024)**
**Goal**: Complete implementation of core workflow engines

#### WDL Support Implementation
```python
# Priority: High - Complete missing core format
class WDLImporter:
    def to_workflow(self, wdl_file_path):
        """Convert WDL to enhanced IR."""
        # Task and workflow parsing
        # Scatter operation handling
        # Runtime specification extraction
```

#### Enhanced Environment Management
- Automatic conda environment setup with dependency injection
- Docker registry integration with authentication
- Content-based environment deduplication

#### CWL/BCO Enhancement
- Complete BCO validation framework
- FDA submission package generation
- Advanced CWL feature testing

### **Phase 2: Advanced Features (Q3-Q4 2024)**
**Goal**: Implement advanced workflow features and integrations

#### Dynamic Workflow Support
- Advanced checkpoint integration for Snakemake workflows
- Conditional execution support across all formats
- Parameter sweep automation

#### Galaxy Integration
- Galaxy workflow format import/export
- Tool integration and dependency management
- Workflow sharing and collaboration features

#### Enhanced Testing
- Large-scale workflow testing
- Cross-platform compatibility validation
- Regulatory compliance testing

### **Phase 3: Enterprise Features (2025)**
**Goal**: Enterprise-grade features for production deployment

#### Workflow Registries
```python
class WorkflowRegistry:
    """Enterprise workflow registry with versioning."""
    def publish_workflow(self, workflow_ir, registry_url):
        """Publish workflow to enterprise registry."""
        # Version management and tagging
        # Dependency tracking and resolution
        # Access control and permissions
```

#### Monitoring and Analytics
- Conversion statistics and reporting
- Usage pattern analysis
- Error tracking and prevention

#### Regulatory Compliance
- 21 CFR Part 11 electronic records compliance
- GDPR data privacy features
- Comprehensive audit trails

### **Phase 4: Ecosystem Integration (2025+)**
**Goal**: Broad ecosystem integration and standards participation

#### Cloud Platform Integration
- AWS Batch, GCP Dataflow, Azure Batch native support
- Kubernetes workflow execution
- Serverless workflow deployment

#### Standards Development
- Active participation in workflow standards committees
- Cross-platform interoperability initiatives
- Open source ecosystem collaboration

---

## Implementation Guidelines

### Development Priorities

1. **Complete Core Formats First**: WDL support is highest priority
2. **Maintain Backward Compatibility**: Never break existing functionality
3. **Test-Driven Development**: All new features require comprehensive test coverage
4. **Documentation First**: Design documents before implementation
5. **User-Centric Design**: Focus on real-world use cases and user feedback

### Contribution Framework

```python
# Plugin architecture for new workflow engines
class WorkflowImporter(ABC):
    @abstractmethod
    def to_workflow(self, input_path: Path, **opts) -> Workflow:
        """Convert native format to enhanced IR."""
        pass

class WorkflowExporter(ABC):
    @abstractmethod
    def from_workflow(self, workflow: Workflow, output_path: Path, **opts):
        """Convert enhanced IR to native format."""
        pass
```

### Quality Standards
- **Code Review**: All changes require peer review
- **Automated Testing**: CI/CD pipeline with comprehensive testing
- **Documentation**: Complete API documentation and user guides
- **Security Scanning**: Automated security vulnerability scanning

---

## Conclusion

`wf2wf` provides a solid foundation for universal workflow format conversion with lossless metadata preservation. The current implementation successfully demonstrates the core vision with production-ready Snakemake → DAGMan conversion and comprehensive CWL/BCO support.

**Current Strengths:**
- ✅ Robust IR-centric architecture with comprehensive metadata support
- ✅ Production-ready core format conversions (Snakemake, DAGMan, CWL)
- ✅ Advanced DAGMan features including inline submit descriptions
- ✅ Comprehensive testing framework with 219+ test functions
- ✅ Schema-based validation and versioning
- ✅ Enhanced CWL v1.2.1 support with BCO integration structures

**Near-term Development Focus:**
- 🎯 Complete WDL support to achieve universal core format coverage
- 🎯 Enhanced environment management with automation features
- 🎯 Advanced CWL/BCO regulatory compliance implementation
- 🎯 Galaxy integration for broader ecosystem support

**Long-term Vision:**
- 🚀 Enterprise workflow registries and management
- 🚀 Advanced monitoring and analytics
- 🚀 Complete regulatory compliance framework
- 🚀 Cloud-native execution integration

The foundation is solid, the immediate roadmap is clear, and the long-term vision provides direction for continued evolution to meet the growing needs of the computational research community.

### 10.8  Loss-Mapping & Reinjection Strategy *(added 2025-06-22)*

When a target engine cannot represent an IR field (e.g. GPU resources in CWL), wf2wf
will:

1. **Record** a *loss entry* with JSON-Pointer path, original value, reason and
   `origin` (user | wf2wf).
2. **Serialize** all entries to `<output>.loss.json` next to the exported files.
3. **Store** the same list in `Workflow.loss_map` so further in-memory processing
   can reason about losses.
4. **Importers** look for a sibling `.loss.json` and attempt to re-inject each
   entry whose path is still resolvable, thereby restoring information for a
   subsequent conversion back to a richer format.

Schema sketch (`schemas/v0.1/loss.json`):
```jsonc
{
  "$schema": "https://wf2wf.dev/schemas/v0.1/loss.json",
  "wf2wf_version": "0.3.0",
  "target_engine": "cwl",
  "timestamp": "2025-06-22T14:03:11Z",
  "entries": [
    {
      "json_pointer": "/tasks/align/resources/gpu",
      "field": "gpu",
      "lost_value": 1,
      "reason": "CWL ResourceRequirement has no GPU fields",
      "origin": "user"
    }
  ]
}
```

Shared helper module `wf2wf.loss` provides `record()`, `reset()`, `write()` and
`as_list()` so exporters/importers remain loosely coupled.  Exporter
pseudo-workflow:
```python
from wf2wf import loss
loss.reset()
...
loss.record(ptr, field, val, reason, origin)
...
loss.write(output.with_suffix('.loss.json'))
wf.loss_map = loss.as_list()
```
This design delivers auditability and round-trip fidelity with minimal runtime
cost and without entangling exporter code.

#### 10.8.4  Side-car schema (v0.1)

Located at `schemas/v0.1/loss.json` – Draft 2020-12.  Key additions:

* `source_checksum` – `sha256:<64 hex>` checksum of the **pre-export** IR.  Importers skip the side-car if this mismatches, avoiding accidental cross-pollination.
* `severity` – enum `info|warn|error` for future fine-grained handling (e.g. `--fail-on-loss=error`).
* `status` – now `lost|lost_again|reapplied`.

```jsonc
{
  "wf2wf_version": "0.3.0",
  "target_engine": "cwl",
  "source_checksum": "sha256:39d6…",
  "entries": [
    {"json_pointer": "/tasks/align/retry", "field": "retry", "lost_value": 3,
     "reason": "CWL has no retry field", "origin": "user", "status":"lost",
     "severity":"warn"}
  ]
}
```

#### 10.8.5  CLI integration *(2025-06-23)*

* `wf2wf convert --fail-on-loss` – aborts (exit 1) if **any** unresolved loss entry remains after conversion.
* Summary line printed regardless: `⚠ Conversion losses: 2 (lost), 0 (lost again), 5 (reapplied)`.
* `wf2wf validate` fails if a side-car contains user-origin losses that are not `reapplied`.

Example:

```bash
wf2wf convert -i analysis.cwl -o pipeline.smk --out-format snakemake --fail-on-loss -v
# → exits with message: Conversion resulted in 1 unresolved losses.
```

These UX touches make loss transparency a first-class feature.
