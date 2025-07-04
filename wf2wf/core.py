"""
wf2wf.core – Intermediate Representation (IR) classes and helpers.

This module defines the canonical, engine-agnostic data structures that all
importers must emit and all exporters must consume.  Validation utilities and
JSON/TOML (de)serialisers will be added in later iterations.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
import hashlib


# ---------------------------------------------------------------------------
# 1️⃣  Enhanced sub-structures for advanced CWL/BCO support
# ---------------------------------------------------------------------------


@dataclass
class ProvenanceSpec:
    """Provenance and authorship information for workflows and tasks."""

    authors: List[Dict[str, str]] = field(
        default_factory=list
    )  # ORCID, name, affiliation
    contributors: List[Dict[str, str]] = field(default_factory=list)
    created: Optional[str] = None  # ISO 8601 timestamp
    modified: Optional[str] = None
    version: Optional[str] = None
    license: Optional[str] = None
    doi: Optional[str] = None
    citations: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    derived_from: Optional[str] = None  # Source workflow reference
    extras: Dict[str, Any] = field(
        default_factory=dict
    )  # namespaced or custom annotations


@dataclass
class DocumentationSpec:
    """Rich documentation for workflows and tasks."""

    description: Optional[str] = None
    label: Optional[str] = None
    doc: Optional[str] = None  # CWL-style documentation
    intent: List[str] = field(default_factory=list)  # Ontology IRIs
    usage_notes: Optional[str] = None
    examples: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TypeSpec:
    """CWL v1.2.1 type specification with advanced features."""

    type: str  # Base type: File, Directory, string, int, float, boolean, array, record, enum
    items: Optional[Union[str, "TypeSpec"]] = None  # For array types
    fields: Dict[str, "TypeSpec"] = field(default_factory=dict)  # For record types
    symbols: List[str] = field(default_factory=list)  # For enum types
    # Union types (CWL allows multiple non-null types)
    members: List["TypeSpec"] = field(default_factory=list)
    name: Optional[str] = None  # Symbolic name for record/enum schemas
    nullable: bool = False  # Optional type (type?)
    default: Any = None

    # ------------------------------------------------------------------
    # Friendly constructors & helpers
    # ------------------------------------------------------------------

    @classmethod
    def parse(cls, obj: Union[str, "TypeSpec", Dict[str, Any]]) -> "TypeSpec":
        """Return a :class:`TypeSpec` instance from *obj*.

        Accepts CWL‐style shorthand strings such as ``File``, ``string?`` (nullable),
        ``File[]`` (array of File), or fully fledged mapping objects produced by
        ``cwltool --print-pre``.  If *obj* is already a :class:`TypeSpec*`` it is
        returned unchanged.
        """

        if isinstance(obj, TypeSpec):
            return obj

        # --------------------------------------------------------------
        # Shorthand string – minimal parsing
        # --------------------------------------------------------------
        if isinstance(obj, str):
            nullable = obj.endswith("?")
            raw = obj[:-1] if nullable else obj

            # Handle array notation "File[]" or "string[]?"
            if raw.endswith("[]"):
                inner_raw = raw[:-2]
                inner_spec = cls.parse(inner_raw)
                return cls(type="array", items=inner_spec, nullable=nullable)

            return cls(type=raw, nullable=nullable)

        # --------------------------------------------------------------
        # Mapping – assume already expanded CWL type object
        # --------------------------------------------------------------
        if isinstance(obj, dict):
            # Ensure required key
            if "type" not in obj:
                raise ValueError("CWL type object must contain 'type' key")
            return cls(**obj)  # type: ignore[arg-type]

        # --------------------------------------------------------------
        # Union list style – e.g. ['null', 'File']
        # --------------------------------------------------------------
        if isinstance(obj, list):
            nullable = "null" in obj
            non_null = [t for t in obj if t != "null"]
            if len(non_null) == 1:
                base = cls.parse(non_null[0])
                base.nullable = base.nullable or nullable
                return base

            # Multi‐type union – preserve explicit members for fidelity
            members = [cls.parse(t) for t in non_null]
            return cls(type="union", members=members, nullable=nullable)

        raise TypeError(f"Cannot parse TypeSpec from object of type {type(obj)}")

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    _PRIMITIVES = {
        "File",
        "Directory",
        "string",
        "int",
        "long",
        "float",
        "double",
        "boolean",
        "Any",
    }

    def validate(self) -> None:
        """Semantic validation for the CWL type system.

        Raises
        ------
        ValueError
            If the type definition is semantically invalid.
        """

        # Base or complex type
        if self.type == "array":
            if self.items is None:
                raise ValueError("Array TypeSpec must define 'items'")
            # Recurse
            if isinstance(self.items, TypeSpec):
                self.items.validate()
            return

        if self.type == "record":
            if not self.fields:
                raise ValueError("Record TypeSpec requires 'fields'")
            for key, f in list(self.fields.items()):
                if not isinstance(f, TypeSpec):
                    self.fields[key] = TypeSpec.parse(f)
                    f = self.fields[key]
                f.validate()
            return

        if self.type == "enum":
            if not self.symbols:
                raise ValueError("Enum TypeSpec requires 'symbols'")
            return

        if self.type == "union":
            if not self.members:
                raise ValueError("Union TypeSpec requires 'members'")
            for m in self.members:
                m.validate()
            return

        # Primitive
        if self.type not in self._PRIMITIVES:
            raise ValueError(f"Unknown or unsupported CWL type '{self.type}'")

    # Equality helper so tests comparing to simple strings continue to work
    def __eq__(self, other):  # type: ignore[override]
        if isinstance(other, TypeSpec):
            return self.type == other.type and self.nullable == other.nullable
        if isinstance(other, str):
            return self.type == other
        return NotImplemented


@dataclass
class FileSpec:
    """Enhanced file specification with CWL features."""

    path: str
    class_type: str = "File"  # File or Directory
    format: Optional[str] = None  # File format ontology IRI
    checksum: Optional[str] = None  # sha1$... or md5$...
    size: Optional[int] = None  # File size in bytes
    secondary_files: List[str] = field(default_factory=list)
    contents: Optional[str] = None  # For small files
    listing: List["FileSpec"] = field(default_factory=list)  # For directories
    basename: Optional[str] = None
    dirname: Optional[str] = None
    nameroot: Optional[str] = None
    nameext: Optional[str] = None

    # ------------------------------------------------------------------
    # Convenience initialisation & helpers
    # ------------------------------------------------------------------

    def __post_init__(self):
        # Derive basename parts if not provided
        if self.basename is None:
            self.basename = Path(self.path).name
        if self.dirname is None:
            self.dirname = str(Path(self.path).parent)
        if self.nameroot is None or self.nameext is None:
            root, ext = Path(self.basename).stem, Path(self.basename).suffix
            self.nameroot = root
            self.nameext = ext

    def compute_stats(self, *, read_contents: bool = False) -> None:
        """Populate `checksum`, `size` and optionally `contents` if the path exists."""
        p = Path(self.path)
        if not p.exists():
            return
        h = hashlib.sha1()
        if p.is_file():
            data = p.read_bytes()
            h.update(data)
            self.size = len(data)
            if read_contents and self.size < 65536:  # arbitrary limit 64 KB
                self.contents = data.decode(errors="replace")
        else:
            # Directory checksum: hash of sorted file checksums
            parts = []
            for sub in sorted(p.rglob("*")):
                if sub.is_file():
                    parts.append(sub.read_bytes())
            for chunk in parts:
                h.update(chunk)
            self.size = sum(len(c) for c in parts)
        self.checksum = "sha1$" + h.hexdigest()

    # Simple semantic validation (path may not exist yet)
    def validate(self) -> None:
        if not self.path:
            raise ValueError("FileSpec.path cannot be empty")


@dataclass
class ParameterSpec:
    """CWL v1.2.1 parameter specification for inputs and outputs."""

    id: str
    type: Union[str, TypeSpec]
    label: Optional[str] = None
    doc: Optional[str] = None
    default: Any = None

    # File-specific attributes
    format: Optional[str] = None
    secondary_files: List[str] = field(default_factory=list)
    streamable: bool = False
    load_contents: bool = False
    load_listing: Optional[str] = None  # no_listing, shallow_listing, deep_listing

    # Input binding (for CommandLineTool)
    input_binding: Optional[Dict[str, Any]] = None

    # Output binding (for CommandLineTool)
    output_binding: Optional[Dict[str, Any]] = None

    # CWL Step-specific expression support
    value_from: Optional[str] = None  # CWL valueFrom expression

    # File transfer mode for distributed computing environments
    transfer_mode: str = "auto"  # auto, always, never, shared

    # ------------------------------------------------------------------
    # Post-initialisation normalisation
    # ------------------------------------------------------------------

    def __post_init__(self):
        # Normalise *type* to a TypeSpec instance for internal consistency
        self.type = TypeSpec.parse(self.type)  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> None:
        if not self.id:
            raise ValueError("ParameterSpec.id cannot be empty")
        # Validate type
        if isinstance(self.type, TypeSpec):
            self.type.validate()

    # Allow being used as dict keys / set members based on id
    def __hash__(self):  # type: ignore[override]
        return hash(self.id)


@dataclass
class ScatterSpec:
    """Scatter operation specification for parallel execution."""

    scatter: List[str]  # Parameters to scatter over
    scatter_method: str = (
        "dotproduct"  # dotproduct, nested_crossproduct, flat_crossproduct
    )


@dataclass
class RequirementSpec:
    """CWL requirement or hint specification."""

    class_name: str
    data: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.class_name:
            raise ValueError("RequirementSpec.class_name is mandatory")

        # Semantic checks for common CWL requirement classes
        if self.class_name == "DockerRequirement":
            needed = {"dockerPull", "dockerImageId", "dockerLoad", "dockerFile"}
            if not any(k in self.data for k in needed):
                raise ValueError(
                    "DockerRequirement must define one of dockerPull, dockerImageId, dockerLoad or dockerFile"
                )

        if self.class_name == "ResourceRequirement":
            allowed = {
                "coresMin",
                "coresMax",
                "ramMin",
                "ramMax",
                "tmpdirMin",
                "tmpdirMax",
                "outdirMin",
                "outdirMax",
            }
            unknown = set(self.data) - allowed
            if unknown:
                raise ValueError(
                    f"Unknown keys in ResourceRequirement: {', '.join(unknown)}"
                )

        # TODO: further per-class validations as needed


@dataclass
class ResourceSpec:
    """Normalised resource keys common across engines.

    Units:
        * memory -> MB (int)
        * disk   -> MB (int)
        * time   -> seconds (int)
        * gpu_mem -> MB (int) per GPU
    """

    cpu: Optional[int] = None
    mem_mb: Optional[int] = None
    disk_mb: Optional[int] = None
    gpu: Optional[int] = None
    gpu_mem_mb: Optional[int] = None
    time_s: Optional[int] = None  # wall-clock limit (not typically specified in workflows)
    threads: Optional[int] = None
    # Arbitrary extra site-specific attributes (e.g. HTCondor +WantGPULab)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourceProfile:
    """A named resource profile with metadata and resource specifications."""
    
    name: str
    description: str
    environment: str = "cluster"  # shared, cluster, cloud, hpc
    priority: str = "normal"  # low, normal, high, urgent
    resources: ResourceSpec = field(default_factory=ResourceSpec)


@dataclass
class EnvironmentSpec:
    """Execution environment definition."""

    conda: Optional[str] = None  # path or YAML file
    container: Optional[str] = None  # docker://… or /path/image.sif
    workdir: Optional[str] = None  # working directory override
    env_vars: Dict[str, str] = field(default_factory=dict)
    modules: List[str] = field(default_factory=list)  # e.g. Lmod modules


@dataclass
class BCOSpec:
    """BioCompute Object specification for regulatory compliance."""

    object_id: Optional[str] = None
    spec_version: str = "https://w3id.org/ieee/ieee-2791-schema/2791object.json"
    etag: Optional[str] = None

    # BCO Domains (IEEE 2791-2020)
    provenance_domain: Dict[str, Any] = field(default_factory=dict)
    usability_domain: List[str] = field(default_factory=list)
    extension_domain: List[Dict[str, Any]] = field(default_factory=list)
    description_domain: Dict[str, Any] = field(default_factory=dict)
    execution_domain: Dict[str, Any] = field(default_factory=dict)
    parametric_domain: List[Dict[str, Any]] = field(default_factory=list)
    io_domain: Dict[str, Any] = field(default_factory=dict)
    error_domain: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 2️⃣  Enhanced DAG structures
# ---------------------------------------------------------------------------


@dataclass
class Task:
    """A single executable node in the workflow DAG with enhanced CWL support."""

    # Core identification
    id: str
    label: Optional[str] = None
    doc: Optional[str] = None

    # Execution
    command: Optional[str] = None  # shell snippet or language‐specific command
    script: Optional[str] = None  # path to an external script (Python/R/…)

    # Enhanced I/O with CWL parameter specifications
    inputs: List[ParameterSpec] = field(default_factory=list)
    outputs: List[ParameterSpec] = field(default_factory=list)

    # Advanced execution features
    when: Optional[str] = None  # Conditional execution expression
    scatter: Optional[ScatterSpec] = None

    # Enhanced specifications
    resources: ResourceSpec = field(default_factory=ResourceSpec)
    environment: EnvironmentSpec = field(default_factory=EnvironmentSpec)
    requirements: List[RequirementSpec] = field(default_factory=list)
    hints: List[RequirementSpec] = field(default_factory=list)

    # Metadata and provenance
    provenance: Optional[ProvenanceSpec] = None
    documentation: Optional[DocumentationSpec] = None
    intent: List[str] = field(default_factory=list)  # Ontology IRIs

    # Legacy compatibility (deprecated but maintained for backward compatibility)
    params: Dict[str, Any] = field(default_factory=dict)  # engine-specific params
    priority: int = 0
    retry: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)  # arbitrary free-form extras

    # ------------------------------------------------------------------
    # Runtime helpers (non-persistent)
    # ------------------------------------------------------------------

    def is_active(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """Evaluate the *when* expression (if any) against *context* variables."""

        from wf2wf.expression import evaluate as _eval  # lazy import to avoid cycles

        if self.when is None:
            return True
        try:
            result = _eval(self.when, context or {})
        except Exception:
            # Conservative: if expression fails, assume task should run
            return True
        return bool(result)

    def scatter_bindings(self, runtime_inputs: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return a list of variable bindings for each scatter shard.

        If *scatter* is not defined this returns a single binding (empty dict).
        """
        from wf2wf.scatter import expand as _expand

        if self.scatter is None:
            return [{}]

        names = self.scatter.scatter
        values = [runtime_inputs.get(n, []) for n in names]
        spec = dict(zip(names, values))
        return _expand(spec, method=self.scatter.scatter_method)


@dataclass
class Edge:
    """Directed edge relating *parent* → *child* task."""

    parent: str
    child: str


@dataclass
class Workflow:
    """A collection of *Task*s plus dependency edges and optional metadata with enhanced CWL/BCO support."""

    # Core identification
    name: str
    version: str = "1.0"
    label: Optional[str] = None
    doc: Optional[str] = None

    # Workflow structure
    tasks: Dict[str, Task] = field(default_factory=dict)
    edges: List[Edge] = field(default_factory=list)

    # Enhanced I/O
    inputs: List[ParameterSpec] = field(default_factory=list)
    outputs: List[ParameterSpec] = field(default_factory=list)

    # Requirements and hints
    requirements: List[RequirementSpec] = field(default_factory=list)
    hints: List[RequirementSpec] = field(default_factory=list)

    # Metadata and provenance
    provenance: Optional[ProvenanceSpec] = None
    documentation: Optional[DocumentationSpec] = None
    intent: List[str] = field(default_factory=list)  # Ontology IRIs
    cwl_version: Optional[str] = None

    # BCO integration
    bco_spec: Optional[BCOSpec] = None

    # Legacy compatibility (deprecated but maintained for backward compatibility)
    config: Dict[str, Any] = field(default_factory=dict)  # merged config.yaml etc.
    meta: Dict[str, Any] = field(default_factory=dict)

    # Loss mapping entries captured during export (optional)
    loss_map: List[Dict[str, Any]] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience helpers (will be fleshed out later)
    # ------------------------------------------------------------------

    def add_task(self, task: Task):
        if task.id in self.tasks:
            raise ValueError(f"Duplicate task id: {task.id}")
        self.tasks[task.id] = task

    def add_edge(self, parent: str, child: str):
        # Prevent self-dependencies
        if parent == child:
            return  # Silently ignore self-dependencies

        # Check that both tasks exist
        if parent not in self.tasks:
            raise KeyError(f"Parent task '{parent}' not found in workflow")
        if child not in self.tasks:
            raise KeyError(f"Child task '{child}' not found in workflow")

        self.edges.append(Edge(parent, child))

    # TODO: validation, topological sort, resource summaries, etc.

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-Python representation ready for JSON/TOML dump."""

        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        import json

        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def save_json(self, path: Union[str, Path], *, indent: int = 2):
        """Write JSON representation to *path* (creates parent dirs)."""
        _p = Path(path)
        _p.parent.mkdir(parents=True, exist_ok=True)
        _p.write_text(self.to_json(indent=indent))

    @classmethod
    def load_json(cls, path: Union[str, Path]):
        """Load Workflow from a JSON file produced by :py:meth:`save_json`."""
        import json
        from pathlib import Path as _P

        data = json.loads(_P(path).read_text())
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Workflow":
        """Re-hydrate from `json.load(...)` result (best-effort)."""

        # Make a copy to avoid modifying the original
        data = data.copy()

        # Remove JSON Schema metadata that's not part of our dataclass
        data.pop("$schema", None)

        # Tasks
        tasks_data = data.pop("tasks", {})
        tasks = {}
        for tid, tdict in tasks_data.items():
            tdict = tdict.copy()
            # Reconstruct nested dataclasses
            if "resources" in tdict and not isinstance(
                tdict["resources"], ResourceSpec
            ):
                tdict["resources"] = ResourceSpec(**tdict["resources"])
            if "environment" in tdict and not isinstance(
                tdict["environment"], EnvironmentSpec
            ):
                tdict["environment"] = EnvironmentSpec(**tdict["environment"])

            # Parameter specs (inputs / outputs)
            def _make_params(items):
                converted = []
                for p in items:
                    if isinstance(p, ParameterSpec):
                        converted.append(p)
                    elif isinstance(p, str):
                        # Assume File for outputs, string for inputs (best effort)
                        converted.append(ParameterSpec(id=p, type="string"))
                    elif isinstance(p, dict):
                        converted.append(ParameterSpec(**p))
                    else:
                        raise TypeError(f"Unsupported parameter spec item: {p}")
                return converted

            if "inputs" in tdict:
                tdict["inputs"] = _make_params(tdict["inputs"])
            if "outputs" in tdict:
                tdict["outputs"] = _make_params(tdict["outputs"])

            tasks[tid] = Task(id=tid, **{k: v for k, v in tdict.items() if k != "id"})

        edges = [Edge(**e) for e in data.pop("edges", [])]

        # Workflow-level inputs / outputs
        def _make_params(items):
            converted = []
            for p in items:
                if isinstance(p, ParameterSpec):
                    converted.append(p)
                elif isinstance(p, str):
                    converted.append(ParameterSpec(id=p, type="string"))
                elif isinstance(p, dict):
                    converted.append(ParameterSpec(**p))
                else:
                    raise TypeError(f"Unsupported parameter spec item: {p}")
            return converted

        if "inputs" in data:
            data["inputs"] = _make_params(data["inputs"])
        if "outputs" in data:
            data["outputs"] = _make_params(data["outputs"])

        loss_map = data.pop("loss_map", [])
        return cls(tasks=tasks, edges=edges, loss_map=loss_map, **data)

    @classmethod
    def from_json(cls, json_str: str) -> "Workflow":
        """Re-hydrate from JSON string produced by :py:meth:`to_json`."""
        import json

        data = json.loads(json_str)
        return cls.from_dict(data)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Run JSON-Schema plus semantic validation checks.

        Raises
        ------
        ValueError or jsonschema.ValidationError if the workflow is invalid.
        """

        # 1. JSON-Schema structural validation
        from wf2wf.validate import (
            validate_workflow as _js_validate,
        )  # local import to avoid cycle

        _js_validate(self)

        # 2. Semantic checks
        #    – Task ids unique (already enforced by add_task)
        #    – Edge endpoints exist
        for e in self.edges:
            if e.parent not in self.tasks:
                raise ValueError(f"Edge parent '{e.parent}' not found in tasks")
            if e.child not in self.tasks:
                raise ValueError(f"Edge child '{e.child}' not found in tasks")

        #    – Validate each task
        for t in self.tasks.values():
            for p in t.inputs + t.outputs:
                p.validate()
            for req in t.requirements + t.hints:
                req.validate()

        #    – Workflow-level inputs/outputs
        for p in self.inputs + self.outputs:
            p.validate()

        #    – Requirements/hints
        for r in self.requirements + self.hints:
            r.validate()

    # TODO: add .save(path) / .load(path) convenience wrappers
