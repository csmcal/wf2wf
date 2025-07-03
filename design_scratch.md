# wf2wf – A Generalised Workflow-to-Workflow Converter

*Version 0.1 – concept draft*

---

## 1  Motivation

Many research groups accumulate heterogeneous workflow definitions: Snakemake for
prototyping, HTCondor DAGMan for campus clusters, Nextflow for cloud / containers,
and CWL / WDL when sharing with external collaborators.

It would be ideal to "speak all of these dialects" through a **single loss-less
intermediate representation (IR)** and a set of thin *importers* & *exporters*.
That is the goal of **wf2wf**.

```
Snakemake  →┐
Nextflow    ├──►   wf-json   ───► DAGMan
CWL         ┤
WDL         ┘            (or back out to any of the others)
```

---

## 2  Guiding principles

1. **IR before code-gen** – never translate A→B directly; always A→IR→B.
2. **Round-tripable** – parsing a supported language and then re-emitting it
   should produce an *equivalent* workflow (allowing for syntactic re-ordering).
3. **Static graph** – the IR captures a *fully resolved* DAG (fan-in/fan-out
   explicit, no runtime dynamics).  Dynamic features can be encoded as template
   meta-data for partial fidelity.
4. **Metadata-rich** – retain conda envs, container images, resources, retry
   counts, labels, comments where possible.
5. **Extensible** – new engines added by writing one `Importer` + one `Exporter`.
6. **Schema-first** – JSON schema (or YAML) with versioned spec; tooling
   validates at each hop.

---

## 3  Choice of intermediate format

### 3.1  Existing standards considered

| Candidate | Pros | Cons |
|-----------|------|------|
| **CWL** | Widely adopted, JSON/YAML, type system | Verbose; limited support for some modern Nextflow/Snakemake conveniences; DAGMan features (RETRY, priority) need extensions |
| **WDL/V1.2** | Good for bio-pipelines; supports scatter/gather | Complex runtime model; Java/HPC bias |
| **RO-Crate (workflow profile)** | Metadata-rich | Not task-graph focussed |
| **DFDL / Airflow DAG JSON** | Simple nodes/edges | No bioinformatics semantics |

*Decision:* **Design a minimal "wf-json" schema** inspired by CWL but tailored
for static DAG interchange:

```jsonc
{
  "$schema": "https://wf2wf.dev/schemas/v0.1/wf.json",
  "name": "my_workflow",
  "version": "1.0",
  "tasks": {
    "task_id": {
      "command": "string | list",
      "inputs": ["fileA", "fileB"],
      "outputs": ["fileC"],
      "resources": {"cpu": 4, "mem_mb": 8000, "disk_mb": 5000, "gpu": 1},
      "environment": {"conda": "env.yaml", "container": "docker://..."},
      "retry": 2,
      "meta": {"tags": ["QC"]}
    }
  },
  "edges": [
    {"parent": "task_id", "child": "task_id2"}
  ]
}
```

This is *flat* and easy to process in any language.

---

## 4  High-level architecture

```
wf2wf
├── wf2wf/core.py          # IR dataclass + validation
├── wf2wf/importers/
│   ├── snakemake.py       # Snakefile → wfjson
│   ├── nextflow.py        # Nextflow DSL2 → wfjson
│   ├── dagman.py          # .dag + .sub bundle → wfjson
│   └── cwl.py             # CWL v1.2 → wfjson
├── wf2wf/exporters/
│   ├── snakemake.py       # wfjson → Snakefile
│   ├── nextflow.py        # wfjson → main.nf
│   ├── dagman.py          # wfjson → *.dag + *.sub
│   └── cwl.py             # wfjson → CWL pack
└── CLI
    └── wf2wf (click/typer)
```

Each importer/exposer is responsible only for mapping to/from the
`Workflow` dataclass, never for cross-translation.

---

## 5  Implementation plan

### 5.1  Phase 1 – Extract IR core
1. Create `wf2wf/core.py` with `Task`, `Edge`, `Workflow` dataclasses.
2. Move resource-parsing utilities there (unit normalisation, GPU keys…).

### 5.2  Phase 2 – Implement *Exporter* for DAGMan
*Implement `write_condor_dag()` to accept a `Workflow` instance, and handle pipeline and job variables and configurations in a comprehensive manner*

### 5.3  Phase 3 – Implement Snakemake Importer
Use generalized parsing logic:
* `snakemake --dag` → edges + rule IDs
* Snakefile regex parse → templates
* `--dry-run` (optional) → resource enrichment
Put results into `Workflow` dataclass.

### 5.4  Phase 4 – New engines
| Engine | Effort | Notes |
|--------|--------|-------|
| **Nextflow** (export) | ⚫⚫⚪ | Map each task to a `process`; channel generation via file lists. |
| **Nextflow** (import) | ⚫⚫⚫ | DSL2 parsing; may need `nextflow graph` command. |
| **CWL pack** (export) | ⚫⚫⚪ | Straightforward JSON emission. |
| **CWL** (import) | ⚫⚫⚪ | Use `cwltool --print-pre` to get flattened graph. |
| **WDL** (export) | ⚫⚫⚫ | Scaffold only; translating scatter/gather semantics non-trivial. |

*Legend:* ⚫ = ~1 week dev.

### 5.5  Phase 5 – Unified CLI
```
wf2wf convert --in-format snakemake --out-format dagman \
              --snakefile Snakefile --out workflow.dag
```
The CLI will auto-detect formats by extension when possible.

---

## 6  Enhanced CWL/BCO Implementation Plan

Based on comprehensive research into CWL v1.2.1, BioCompute Objects (BCO) IEEE 2791-2020, and BCO-CWL integration, the following implementation plan will enhance wf2wf to fully preserve CWL standards and support regulatory compliance through BCO integration.

### 6.1  Enhanced IR Architecture

The current IR will be extended to support:

#### 6.1.1  Advanced Metadata and Provenance
- **Author Attribution**: ORCID integration, contributor tracking
- **Versioning**: Comprehensive version control and change tracking
- **Documentation**: Rich documentation with ontology support
- **Regulatory Metadata**: BCO domain mapping for FDA compliance

#### 6.1.2  Advanced Execution Features
- **Conditional Execution**: `when` expressions for step-level conditionals
- **Scatter/Gather**: Full scatter operation support (dotproduct, crossproduct)
- **Expression System**: JavaScript expression evaluation with security sandboxing
- **Step Input Expressions**: Dynamic input generation and transformation

#### 6.1.3  Enhanced File Management
- **Secondary Files**: Automatic secondary file discovery and staging
- **File Validation**: Checksum verification and format validation
- **Ontology Integration**: File format ontologies and semantic validation
- **Directory Handling**: Comprehensive directory listing and management

#### 6.1.4  Advanced Type System
- **CWL Types**: Full CWL v1.2.1 type system support
- **Schema Definitions**: Custom type definitions and validation
- **Record Types**: Complex nested data structures
- **Enum Types**: Controlled vocabulary support

#### 6.1.5  Requirements and Hints System
- **Execution Requirements**: Network access, work reuse, time limits
- **Environment Management**: Enhanced container and software management
- **Resource Optimization**: Advanced resource requirement specification
- **Platform Hints**: Platform-specific optimization hints

#### 6.1.6  BCO Integration
- **Nine BCO Domains**: Full IEEE 2791-2020 compliance
- **Regulatory Workflow**: FDA submission workflow support
- **Provenance Tracking**: Complete computational provenance
- **Validation Framework**: BCO validation and verification

### 6.2  Implementation Phases

#### Phase 6A: Enhanced Core IR (Week 1-2)
1. **Extended Dataclasses**: Add enhanced metadata, provenance, and documentation classes
2. **Type System**: Implement CWL type system with validation
3. **File Management**: Add comprehensive file and directory handling
4. **Requirements System**: Implement requirements and hints framework

#### Phase 6B: Advanced CWL Features (Week 3-4)
1. **Conditional Execution**: Implement `when` expression evaluation
2. **Scatter Operations**: Add scatter/gather with all scatter methods
3. **Expression Engine**: JavaScript expression evaluation with security
4. **Enhanced I/O**: Parameter specifications with full CWL feature support

#### Phase 6C: BCO Integration (Week 5-6)
1. **BCO Domain Mapping**: Map IR to nine BCO domains
2. **Regulatory Metadata**: Add FDA compliance metadata support
3. **BCO Export**: Generate IEEE 2791-2020 compliant BCO documents
4. **BCO-CWL Joint Export**: Combined BCO+CWL export for regulatory submissions

#### Phase 6D: Enhanced Importers/Exporters (Week 7-8)
1. **CWL Importer Enhancement**: Full CWL v1.2.1 feature preservation
2. **CWL Exporter Enhancement**: Generate compliant CWL with all features
3. **Cross-Engine Mapping**: Preserve advanced features across engines where possible
4. **Validation Framework**: Comprehensive validation and round-trip testing

### 6.3  Technical Specifications

#### 6.3.1  Enhanced Core Classes
```python
@dataclass
class EnhancedTask:
    """Task with full CWL v1.2.1 and BCO support."""
    # Core identification
    id: str
    label: Optional[str] = None
    doc: Optional[str] = None

    # Execution
    command: Optional[str] = None
    script: Optional[str] = None

    # Enhanced I/O with CWL parameter specifications
    inputs: List[ParameterSpec] = field(default_factory=list)
    outputs: List[ParameterSpec] = field(default_factory=list)

    # Advanced execution features
    when: Optional[str] = None  # Conditional execution
    scatter: Optional[ScatterSpec] = None
    scatter_method: Optional[str] = None

    # Enhanced specifications
    resources: ResourceSpec = field(default_factory=ResourceSpec)
    environment: EnvironmentSpec = field(default_factory=EnvironmentSpec)
    requirements: List[RequirementSpec] = field(default_factory=list)
    hints: List[RequirementSpec] = field(default_factory=list)

    # Metadata and provenance
    intent: List[str] = field(default_factory=list)  # Ontology IRIs

    # Legacy compatibility
    params: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    retry: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)

@dataclass
class EnhancedWorkflow:
    """Workflow with full CWL v1.2.1 and BCO support."""
    # Core identification
    name: str
    version: str = "1.0"
    label: Optional[str] = None
    doc: Optional[str] = None

    # Workflow structure
    tasks: Dict[str, EnhancedTask] = field(default_factory=dict)
    edges: List[Edge] = field(default_factory=list)

    # Enhanced I/O
    inputs: List[ParameterSpec] = field(default_factory=list)
    outputs: List[ParameterSpec] = field(default_factory=list)

    # Requirements and hints
    requirements: List[RequirementSpec] = field(default_factory=list)
    hints: List[RequirementSpec] = field(default_factory=list)

    # Metadata and provenance
    intent: List[str] = field(default_factory=list)
    cwl_version: Optional[str] = None

    # BCO integration
    bco_spec: Optional[BCOSpec] = None

    # Legacy compatibility
    config: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
```

#### 6.3.2  Advanced Feature Support
```python
@dataclass
class ParameterSpec:
    """CWL v1.2.1 parameter specification."""
    id: str
    type: Union[str, TypeSpec]
    label: Optional[str] = None
    doc: Optional[str] = None
    default: Any = None

    # File-specific
    format: Optional[str] = None
    secondary_files: List[str] = field(default_factory=list)
    streamable: bool = False
    load_contents: bool = False
    load_listing: Optional[str] = None

    # Input binding (deprecated but supported)
    input_binding: Optional[Dict[str, Any]] = None

@dataclass
class ScatterSpec:
    """Scatter operation specification."""
    scatter: List[str]  # Parameters to scatter over
    scatter_method: str = "dotproduct"  # dotproduct, nested_crossproduct, flat_crossproduct

@dataclass
class RequirementSpec:
    """CWL requirement or hint specification."""
    class_name: str
    data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class BCOSpec:
    """BioCompute Object specification for regulatory compliance."""
    object_id: Optional[str] = None
    spec_version: str = "https://w3id.org/ieee/ieee-2791-schema/2791object.json"
    etag: Optional[str] = None

    # BCO Domains
    provenance_domain: Dict[str, Any] = field(default_factory=dict)
    usability_domain: List[str] = field(default_factory=list)
    extension_domain: List[Dict[str, Any]] = field(default_factory=list)
    description_domain: Dict[str, Any] = field(default_factory=dict)
    execution_domain: Dict[str, Any] = field(default_factory=dict)
    parametric_domain: List[Dict[str, Any]] = field(default_factory=list)
    io_domain: Dict[str, Any] = field(default_factory=dict)
    error_domain: Dict[str, Any] = field(default_factory=dict)
```

### 6.4  Benefits and Impact

#### 6.4.1  Complete CWL Fidelity
- **Round-trip Preservation**: All CWL v1.2.1 features preserved during conversion
- **Advanced Features**: Conditional execution, scatter/gather, expressions
- **Metadata Richness**: Full provenance, documentation, and type information

#### 6.4.2  Regulatory Compliance
- **FDA Approval**: Support for FDA-approved BCO standard
- **Reproducibility**: Enhanced computational reproducibility tracking
- **Validation**: Comprehensive validation and verification framework

#### 6.4.3  Enhanced Interoperability
- **Cross-Platform**: Better preservation of features across workflow engines
- **Standards Compliance**: Full compliance with scientific workflow standards
- **Future-Proof**: Extensible architecture for new standards and features

---

## 7  Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Feature mismatch (e.g. Nextflow dynamic channels) | Allow IR to store engine-specific `extensions` and warn on lossy conversions. |
| Explosion of exporter options | Keep exporters *opinionated*; advanced knobs via `--export-opts` JSON. |
| Schema drift | Version the JSON schema; CI round-trip tests for every engine. |
| Maintenance burden | Encourage plug-in architecture; extra engines can live in separate repos. |
| Enhanced IR Complexity | Maintain backward compatibility layer; gradual migration path for existing users. |
| BCO Compliance Overhead | Optional BCO features; core functionality remains lightweight. |

---

## 8 Intermediate Representation next steps

"Isolating a clean IR" means defining one authoritative, engine-agnostic description of a workflow and making every importer map into that representation and every exporter map out of it. Once you do that, no importer ever has to know anything about any exporter (and vice-versa). All cross-conversion logic is reduced to:

engine-A → IR → engine-B

rather than N×(N-1) bespoke translators.

Why an IR helps
1. Decoupling Importers and exporters can evolve independently.
2. Extensibility Adding "WDL" later only requires one importer + one exporter.
3. Validation A single JSON-Schema (or Pydantic model) lets you lint every step.
4. Round-trip tests A→IR→A should give an equivalent workflow—great for CI.
5. Rich metadata Attach annotations, provenance, comments, etc., once.

What "implementing an IR schema" entails
* Formal structure Pick the fields you need (we started with Workflow/Task/Edge).
* Constraints Data-types, required vs optional, allowed resource keys, etc.
* Serialisation spec JSON (with JSON-Schema), plus TOML/YAML if desired.
* Versioning Embed "$schema" and "version" so future changes are explicit.
* Helper library Dataclasses/Pydantic models that load, validate, and export.
* Loss-mapping policy Where a target engine can't express something, store it in
`meta` and warn—never silently drop data.

Recommended next steps (roughly in order)
1. Finish the IR spec
  * Flesh-out core.py: enumerate canonical resource keys (cpu, mem_mb, …), environment fields, retry/priority, container vs conda, etc.
  * Write a JSON-Schema file (schemas/v0.1/wf.json) and add a tiny validator utility (wf2wf/validate.py).
  * Add Workflow.to_json() / .from_json() helpers that use the schema.
2. Round-trip CI test
  * Tiny sample workflow → IR (json) → back to workflow via exporter → compare.
3. Refactor Snakemake importer
  * Move all parsing from wf2wf.py into importers/snakemake.py, have it return a Workflow object instead of the old dag_info dict.
  * Adjust exporters.dagman to accept a Workflow.
  * Delete the legacy DAG glue in wf2wf.py.
4. Update CLI
  * After the above, main program becomes:
    - wf = importers.load(fmt_in).to_workflow(input_path, **opts)
    - exporters.load(fmt_out).from_workflow(wf, output_path, **opts_out)
5. Start a simple exporter (e.g. JSON pretty-print) to prove concept, then begin moving write_condor_dag into exporters.dagman.
6. Add validation & warnings
  * On every conversion run validate(wf) and surface schema violations.
  * Produce a "lossy conversion" report if fields can't be expressed.

Doing the schema & validation work first might feel abstract, but it crystallises what information must never be lost and gives importers/exporters a clear contract. Once that contract exists, the remaining refactor is mostly mechanical code movement.

---

## 9  Automated Environment & Container Generation Plan
*(micromamba + conda-lock + conda-pack  →  OCI image via docker-buildx **or** buildah/podman  →  SIF via Apptainer)*

### 9.1 Rationale
Many users run workflows on clusters where (a) Conda environments are preferred for native execution *or* (b) containers are required for isolation.  Creating these artefacts **by hand** is error-prone and hurts reproducibility.  The converter should therefore be able to *materialise and reference* fully reproducible software stacks while it rewrites the workflow.

### 9.2 Integration Points in wf2wf
1. **Importer** – Collect any existing environment hints *(`environment: {conda: env.yml | container: docker://…}`)* and store them verbatim in the IR.
2. **IR → Build Plan** – A new utility `wf2wf.environ.solve()` will:
   1. Generate a lock-file with **conda-lock** for every distinct Conda YAML it encounters (hash by content → deterministic name).
   2. Realise the environment with **micromamba** into a temp prefix.
   3. Create a relocatable tarball with **conda-pack** → `hash.tar.gz`.
3. **IR → OCI Image** – A builder backend interface
   ```python
   class OCIBuilder(Protocol):
       def build(self, tarball: Path, tag: str, labels: dict[str, str]) -> str: ...  # returns image digest
   ```
   • Implementation `DockerBuildxBuilder` (uses python-docker / BuildKit)
   • Implementation `BuildahBuilder` (shells out to buildah/podman)
4. **OCI → SIF (optional)** – If `--apptainer` is requested, call `apptainer build` (via `spython`) to convert the OCI image to `.sif` and push to the cluster mirror.
5. **Exporter** – When emitting CWL, Snakemake, DAGMan … inject the *digest-pinned* container reference (e.g. `docker://ghcr.io/org/img@sha256:…`) or the `.sif` path plus provenance annotations.
6. **Metadata Capture** – Embed the following into the IR for downstream reproducibility & BCO:
   ```jsonc
   "environment": {
     "conda_lock": "sha256:abcd…/env.lock",
     "tarball":    "sha256:abcd…/env.tar.gz",
     "oci_image":  "ghcr.io/org/img@sha256:1234…",
     "sif":        "/cvmfs/…/img_1234.sif",
     "sbom":       "sha256:…/sbom.spdx.json"
   }
   ```

### 9.3 CLI UX
```
# Build Conda envs and images while converting
wf2wf convert \
  --snakefile Snakefile \
  --out-format dagman \
  --auto-env build  \   # default: build images only if needed
  --oci-backend buildx   # or "podman"
  --push-registry ghcr.io/myorg \
  --apptainer            # also produce .sif files
```
Options:
• `--auto-env off|build|reuse` – skip, build new, or reuse existing by hash
• `--oci-backend buildx|podman` – choose builder
• `--push-registry` – where to push images (otherwise local daemon)
• `--apptainer` – convert to SIF and update job descriptors accordingly.

### 9.4 CWL & BCO Considerations
* **CWL** – The exporter must honour `hints/DockerRequirement`.  When `--auto-env build` is used, it should replace loose `DockerRequirement.dockerPull` strings with a *digest-pinned* `dockerPull` value and add a custom hint recording the original spec plus the Conda lock hash.
* **BCO** – Capture the full software stack in the *Execution Domain* and *Parametric Domain*:
  – Include SHA-256 digest of the OCI layer tar.
  – Attach the conda-lock file (or its hash) under `parametric_domain.software_prerequisites`.
  – List the build command & tool versions under `execution_domain.script_driver`.
* **Reproducibility** – Because the lock file + image digest are content-addressed, any third party can recreate / verify bit-for-bit identical environments.

### 9.5 Implementation Phases
| Phase | Duration | Key Deliverables | Notes |
|-------|----------|------------------|-------|
| **A** | 1 week | `wf2wf.environ` module: conda-lock → micromamba → conda-pack pipeline; returns tarball + lock hash | |
| **B** | 1.5 week | `DockerBuildxBuilder` & `BuildahBuilder` with **multi-arch build** support (`--platform`), BuildKit remote cache (`--build-cache`), and ability to push **conda-pack tarballs as OCI artifacts** via ORAS | |
| **C** | 0.5 week | **SBOM generation** with syft; store SPDX digest in IR and push as OCI referrer artifact | |
| **D** | 0.5 week | **Apptainer conversion** helper via spython + cache & dedup logic | |
| **E** | 1 week | IR & schema extension: new `image.signature` & `image.provenance` fields (placeholder for cosign/in-toto), plus CLI wiring (`--auto-env`, `--oci-backend`, `--apptainer`, `--build-cache`, `--sbom`, `--platform`) | |
| **F** | 1 week | Exporter updates (CWL `DockerRequirement`, DAGMan `docker_image`, Snakemake `container:`) incl. digest-pinned images & SBOM references | |
| **G** | 0.5 week | End-to-end integration tests: multi-arch build, registry dedup, SBOM presence, Apptainer path, remote cache efficacy | |
| **H** | backlog | **Image signing & provenance** (cosign + in-toto attestation) once IR fields have baked; policy checks, image slimming, incremental conda layers | |

### 9.6 Open Questions / Future Work
* **SBOM & CVE Scan** – integrate *syft* & *grype* for optional SBOM + vulnerability reports.
* **Layer Cache Sharing** – remote cache via BuildKit's `--export-cache` for faster rebuilds.
* **Spack Support** – experimental backend for HPC sites that forbid Conda.
* **Registry Auth** – support `~/.docker/config.json` and Podman auth files; allow `--registry-token` override for CI.

### 9.7 Local Index & Registry-Aware Deduplication
A build-once/reuse-everywhere strategy keeps CI quick and cluster storage small.

**Local index**
• A lightweight SQLite database at `~/.cache/wf2wf/env_index.db` keyed by the 64-byte *environment hash* (the SHA-256 of the conda-lock file) and significant build parameters (base image, Apptainer on/off, SBOM flag…).
• Columns: `lock_hash`, `oci_digest`, `image_tag`, `sif_path`, `built_at`, `builder`, `metadata_json` (labels, size, SBOM link…).
• On `--auto-env build` wf2wf first queries this DB; if a matching record exists **and** the local daemon or registry confirms the digest is present, no build is performed—the exporter merely re-uses the existing reference.

**OCI label convention**
Every image pushed by wf2wf carries two labels:
```
org.wf2wf.lock.sha256=<lock_hash>
org.wf2wf.build.v=<semver>
```
This lets wf2wf rediscover images that were copied to different registries by external CI flows: it lists tags/manifests, inspects labels, and matches on `lock_hash`.

**Remote registry probing algorithm**
1. Build a candidate registry list from `--push-registry` CLI flags plus `$WF2WF_REGISTRIES` (comma-separated).
2. Issue concurrent catalog or `skopeo search --digest` queries.
3. For each manifest found, inspect labels; the first image whose `org.wf2wf.lock.sha256` equals the desired lock hash is accepted and recorded in the local index.
4. If none found, proceed to build and then push.

**SIF deduplication**
Apptainer images are already content-addressed (`sha256` of rootfs). wf2wf creates a symbolic link `<hash>.sif` under a configurable cache directory (default `~/.cache/wf2wf/sif`). Before converting it checks for that path to skip redundant `apptainer build` runs.

**Cache pruning**
`wf2wf cache prune --days 60 --min-free-gb 5` removes tarballs/SIF files that have not been referenced lately and deletes index rows whose OCI digests are absent from all configured registries.

**Security considerations**
When pulling an image solely by matching the label, wf2wf verifies that the manifest digests *and* the embedded conda lock hash match expectations before updating the IR.

---

## 10  Proposed Near-Term Enhancement Bundles  *(AI co-author, 2025-06-21)*

The following high-impact bundles can be tackled independently.  Pick the tranche that best matches short-term goals or staffing bandwidth.

### 10.1  Regulatory & Loss-Mapping
* **IEEE 2791 validation** – load the official JSON-Schema, validate emitted BCO, surface a structured error list.
* **Loss-mapping report** – during export collect any field that cannot be expressed in the target format, classify as *dropped / down-converted / engine-extension*, write JSON / Markdown next to the artefacts.
* **FDA submission bundle** – one CLI flag `--fda-package` that zips CWL + BCO + SBOM + Conda locks, ensures checksums match and manifests are machine-readable.

### 10.2  Environment & Container Automation (see §9)
* Implement `wf2wf.environ`: `conda-lock → micromamba → conda-pack → OCI → SIF` with local cache & remote registry probe.
* SBOM generation via Syft/Grype; optional cosign signing & provenance attestation.
* Exporters inject digest-pinned image references automatically; original env spec stored in a hint for round-trip fidelity.

### 10.3  Format Coverage
* **WDL**: finish importer/exporter incl. scatter, runtime, sub-workflows.
* **Nextflow**: channel analysis & module support, config parse.
* **Galaxy exporter**: round-trip `.ga` workflows.

### 10.4  Dynamic-Feature Modelling
* Add `DynamicSpec` placeholder so Snakemake/Nextflow dynamic constructs can round-trip (down-convert to warning where unsupported).
* Emit RETRY / PRIORITY / CLASSAD hints into DAGMan exporter.

### 10.5  Developer & Ops UX
* `--export-opts @file.json` for long option sets.
* Plugin discovery via `entry_points` so third-party engines drop in.
* Structured logging (`--log-format json`) using `rich` or similar.
* Micro-benchmark / profiling hooks to keep conversion latency predictable.

### 10.6  Usability Polish
* `wf2wf viz in.cwl --out graph.svg` (Mermaid / DOT).
* `wf2wf diff wf_old.cwl wf_new.cwl` – structural & metadata diff at IR level.
* Shell tab-completion for the CLI.

### 10.7  Quality Engineering
* Fuzzing harness mutating real workflows to ensure robustness.
* GH Actions matrix: Linux + macOS, Python 3.9 – 3.12.
* Mutation-testing (Mutmut) to keep mutation score high.

---

## Dev cleanup
Ran
`pip install -e .`
How to ensure clean env?
`pip uninstall wf2wf -y`

---

## 11  Loss-Mapping Completion Roadmap *(2025-06-22)*

The initial loss-map infra (schema field, CWL exporter/importer, shared utils) is merged. Remaining tasks:

A. Broaden loss recording
   • Add `loss.record()` calls in Snakemake, DAGMan, Nextflow exporters for every downgrading step (GPU, scatter, when, secondaryFiles, provenance extras…).
   • Provide helper functions if repetitive.

B. Reinjection fidelity
   • Extend `loss.apply()` to cope with ParameterSpec fields, workflow-level metadata, etc.
   • Mark entries as `status:"reapplied"` after successful reinjection to avoid ping-pong.

C. CLI surfacing
   • `wf2wf convert` prints summary and offers `--fail-on-loss`.
   • `wf2wf validate` checks unresolved user-loss entries.

D. Schema polish
   • Publish `loss.json` schema file.
   • Add checksum of originating IR; importer skips stale side-cars.
   • Add `severity` enum for future control.

E. Test coverage
   • Round-trip Snakemake→CWL→Snakemake restoring retry/priority.
   • Negative checksum test.

F. Documentation
   • Update CLI docs and DESIGN sections with examples.

## 12  User-Facing Reports & Interactive Conversion Modes *(2025-06-25)*

### 12.1  Human-Readable Conversion Report (`--report-md`)

**Goal** – After every conversion (or when explicitly requested) wf2wf should emit a concise Markdown document that:
1. Summarises the source & target formats, version information and timestamps.
2. Lists major actions performed (env-build, container digest pinning, SBOM generation, loss-mapping side-car, etc.).
3. Presents *Information Loss* in a readable table sorted by severity.
4. Provides *Next Steps* – e.g. "Push images with `--confirm-push`", "Run `wf2wf validate`", links to rendered BCO or DAG files.

#### 12.1.1  Implementation sketch
```
wf2wf convert … --report-md report.md
# or always
wf2wf config set reports.default on
```
• New utility `wf2wf.report.generate(wf_before, wf_after, opts, losses, artefacts) -> Path`.
• Inject into CLI after export phase.
• Template via Jinja2 with predefined sections so new exporters can register *report hooks* (plugin pattern).

#### 12.1.2  File layout & artefact bundling
When `--package` (e.g. eSTAR) is active, the report is placed in the root of the archive; otherwise next to the output files.

#### 12.1.3  Open questions
* Include inline diffs for modified YAML/JSON env files? (Y ☐ / N ☑)
* Provide HTML rendition alongside `.md`? Could be done via GitHub's Markdown rendering in the browser – low priority.

### 12.2  Interactive / Confirmation Mode (`--interactive`)

**Goal** – Improve trust & clarity by letting users approve optional or potentially destructive steps.

Scenarios:
• Auto-build environments – ask before network / Docker heavy operations.
• Lossy conversion detected (`loss.severity >= warn`) – offer *abort / continue*.
• Overwriting existing output files.

#### 12.2.1  UX guidelines
1. **Single flag** `-i/--interactive` enabling prompts; default remains non-interactive to keep CI flows stable.
2. Prompts stack with a simple `y/n/always/abort` choice set (similar to `git add -p`).
3. Respect `WF2WF_NO_PROMPT=1` env var to force headless mode even if the flag is set (useful for scripted runs).

#### 12.2.2  Technical approach
* Central helper `wf2wf.prompt.ask(question, default=False) -> bool` using `click.confirm` when `click` is present; falls back to `input()`.
* CLI pipeline emits `PromptEvent`s that importers/exporters can hook into.

```python
if interactive and potential_loss:
    if not prompt.ask("13 fields will be lost – continue?", default=False):
        raise ClickException("Aborted by user")
```

#### 12.2.3  Future extensions
• *Wizard* mode: step-through interactive conversion with coloured output.
• Integration with TUI libraries (e.g. `textual`) for richer choices.

### 12.3  Roadmap & Effort
| Feature | Effort | Deliverable | Notes |
|---------|--------|-------------|-------|
| Markdown report engine | ⚫⚫⚪ | `wf2wf.report` + CLI flag | Jinja2 Templates + tests |
| Interactive prompts | ⚫⚫⚪ | `wf2wf.prompt` util + `--interactive` | Ensure no breakage in CI |
| Reporter hooks for all exporters | ⚫⚪⚪ | Common interface | Minimal at first (CWL, DAGMan) |

(⚫ ≈ 0.5 week dev)

---

### 13  Collaborator-Ready & Publication Checklist *(added 2025-06-25)*

The following tasks make **wf2wf** trivially usable by external contributors and
ready for PyPI/conda-forge publication.

| Area | Action Items | Status |
|------|--------------|--------|
| Packaging | • Keep **pyproject.toml** as sole authoritative metadata<br/>• Remove legacy *setup.py* to avoid duplication<br/>• Fill `[project]` fields (name, version, authors, classifiers …)<br/>• Declare CLI entry-point: `wf2wf = wf2wf.cli:simple_main`<br/>• Add **MANIFEST.in** for schemas/examples | ⚙ in-progress (roadmap 0.3) |
| Builds | • Add `python -m build` workflow<br/>• GitHub-Actions job to upload to TestPyPI → PyPI on tag | ☐ |
| Conda | • Write recipe/meta.yaml referencing sdist<br/>• Submit staged-recipes PR | ☐ |
| CI Matrix | linux/macos × Py 3.9-3.12 with pytest + pre-commit | ☐ |
| Docs | Sphinx/MkDocs site on ReadTheDocs | ☐ |
| Community | CODE_OF_CONDUCT.md, ISSUE / PR templates | ☐ |

Once *Packaging* column is checked, a contributor can:
```bash
pip install wf2wf
wf2wf --help
```
from a clean environment, and the wheel will include schemas & examples.

---
