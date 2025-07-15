"""
wf2wf.core – Intermediate Representation (IR) classes and helpers.

This module defines the canonical, engine-agnostic data structures that all
importers must emit and all exporters must consume.  Validation utilities and
JSON/TOML (de)serialisers will be added in later iterations.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

# -----------------------------------------------------------------------------
# Universal Environment-Aware IR Implementation
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Environment-Specific Value Foundation (Multi-Environment Support)
# -----------------------------------------------------------------------------

@dataclass
class EnvironmentSpecificValue:
    """A value that can have different values for different execution environments."""
    
    # Each entry contains: value, environments
    values: List[Dict[str, Any]] = field(default_factory=list)
    
    # Explicit default value (separate from environment-specific values)
    default_value: Optional[Any] = None

    def __init__(self, value: Any = None, environments: Optional[List[str]] = None):
        self.values = []
        self.default_value = None
        
        if value is not None:
            if environments is None or not environments:
                # No environments specified = this is the default value
                self.default_value = value
            else:
                # Environments specified = this is environment-specific
                # Normalize environments: remove None values
                env_list = [env for env in environments if env is not None]
                if env_list:
                    self.values.append({
                        "value": value,
                        "environments": env_list
                    })

    def is_applicable_to(self, environment: str) -> bool:
        """Check if any value is applicable to the given environment."""
        # Check for environment-specific value
        for entry in self.values:
            if environment in entry["environments"]:
                return True
        # Check for default value
        return self.default_value is not None

    def get_value_for(self, environment: str) -> Optional[Any]:
        """Get the value for the given environment, or None if not set."""
        # Search for environment-specific value first
        for entry in reversed(self.values):
            if environment in entry["environments"]:
                return entry["value"]
        # No environment-specific value found
        return None

    def get_value_with_default(self, environment: str) -> Optional[Any]:
        """Get the value for the given environment, with fallback to default value."""
        # Try environment-specific value first
        value = self.get_value_for(environment)
        if value is not None:
            return value
        # Fallback to default value
        return self.default_value

    def add_environment(self, environment: str):
        """Add an environment to the most recent value's applicable environments."""
        if self.values and environment not in self.values[-1]["environments"]:
            self.values[-1]["environments"].append(environment)

    def remove_environment(self, environment: str):
        """Remove an environment from all values."""
        for entry in self.values:
            if environment in entry["environments"]:
                entry["environments"].remove(environment)

    def set_for_environment(self, value: Any, environment: Optional[str]):
        """Set a value for a specific environment (replaces if already present)."""
        if environment is None:
            # Setting default value
            self.default_value = value
            return
        
        # Remove any existing value for this environment
        self.values = [entry for entry in self.values if environment not in entry["environments"]]
        
        # Add new value
        self.values.append({
            "value": value,
            "environments": [environment]
        })

    def set_default_value(self, value: Any):
        """Set the default value explicitly."""
        self.default_value = value

    def get_default_value(self) -> Optional[Any]:
        """Get the default value."""
        return self.default_value

    def all_environments(self) -> Set[str]:
        """Get all environments that have values set."""
        envs = set()
        for entry in self.values:
            envs.update(entry["environments"])
        return envs

    def has_environment_specific_value(self, environment: str) -> bool:
        """Check if there's an environment-specific value for the given environment."""
        return self.get_value_for(environment) is not None

    def has_default_value(self) -> bool:
        """Check if there's a default value set."""
        return self.default_value is not None

    def copy(self) -> "EnvironmentSpecificValue":
        """Create a deep copy of this EnvironmentSpecificValue."""
        new_env_value = EnvironmentSpecificValue()
        new_env_value.default_value = self.default_value
        new_env_value.values = [entry.copy() for entry in self.values]
        return new_env_value

# -----------------------------------------------------------------------------
# Predefined Execution Environments
# -----------------------------------------------------------------------------

@dataclass
class ExecutionEnvironment:
    """Definition of an execution environment with its characteristics."""
    
    name: str  # e.g., "shared_filesystem", "distributed_computing", "cloud_native"
    display_name: str  # e.g., "Shared Filesystem", "Distributed Computing", "Cloud Native"
    description: str
    
    # Environment characteristics
    filesystem_type: str  # shared, distributed, hybrid, cloud_storage
    resource_management: str  # implicit, explicit, dynamic, cloud_managed
    environment_isolation: str  # none, conda, container, cloud_runtime
    file_transfer_mode: str  # none, manual, automatic, cloud_storage
    
    # Default behaviors
    default_file_transfer_mode: str = "auto"
    default_resource_specification: bool = False
    default_environment_isolation: bool = False
    default_error_handling: bool = False
    
    # Supported features
    supports_gpu: bool = True
    supports_checkpointing: bool = False
    supports_partial_results: bool = False
    supports_cloud_storage: bool = False
    
    # Metadata
    priority: int = 0  # For ordering in UI/CLI
    deprecated: bool = False
    experimental: bool = False

# Predefined execution environments
EXECUTION_ENVIRONMENTS = {
    "shared_filesystem": ExecutionEnvironment(
        name="shared_filesystem",
        display_name="Shared Filesystem",
        description="Traditional shared filesystem environment (e.g., NFS, Lustre)",
        filesystem_type="shared",
        resource_management="implicit",
        environment_isolation="none",
        file_transfer_mode="none",
        default_file_transfer_mode="never",
        default_resource_specification=False,
        default_environment_isolation=False,
        default_error_handling=False,
        supports_gpu=True,
        supports_checkpointing=False,
        supports_partial_results=False,
        supports_cloud_storage=False,
        priority=1
    ),
    "distributed_computing": ExecutionEnvironment(
        name="distributed_computing",
        display_name="Distributed Computing",
        description="Distributed computing environment (e.g., HTCondor, SLURM)",
        filesystem_type="distributed",
        resource_management="explicit",
        environment_isolation="container",
        file_transfer_mode="manual",
        default_file_transfer_mode="explicit",
        default_resource_specification=True,
        default_environment_isolation=True,
        default_error_handling=True,
        supports_gpu=True,
        supports_checkpointing=True,
        supports_partial_results=True,
        supports_cloud_storage=False,
        priority=2
    ),
    "cloud_native": ExecutionEnvironment(
        name="cloud_native",
        display_name="Cloud Native",
        description="Cloud-native environment (e.g., AWS Batch, GCP Dataflow)",
        filesystem_type="cloud_storage",
        resource_management="dynamic",
        environment_isolation="cloud_runtime",
        file_transfer_mode="automatic",
        default_file_transfer_mode="cloud_storage",
        default_resource_specification=True,
        default_environment_isolation=True,
        default_error_handling=True,
        supports_gpu=True,
        supports_checkpointing=False,
        supports_partial_results=True,
        supports_cloud_storage=True,
        priority=3
    ),
    "hybrid": ExecutionEnvironment(
        name="hybrid",
        display_name="Hybrid",
        description="Hybrid environment (e.g., on-premises with cloud bursting)",
        filesystem_type="hybrid",
        resource_management="dynamic",
        environment_isolation="container",
        file_transfer_mode="automatic",
        default_file_transfer_mode="adaptive",
        default_resource_specification=True,
        default_environment_isolation=True,
        default_error_handling=True,
        supports_gpu=True,
        supports_checkpointing=True,
        supports_partial_results=True,
        supports_cloud_storage=True,
        priority=4
    ),
    "edge": ExecutionEnvironment(
        name="edge",
        display_name="Edge Computing",
        description="Edge computing environment (e.g., IoT devices, mobile)",
        filesystem_type="distributed",
        resource_management="constrained",
        environment_isolation="none",
        file_transfer_mode="minimal",
        default_file_transfer_mode="minimal",
        default_resource_specification=True,
        default_environment_isolation=False,
        default_error_handling=True,
        supports_gpu=False,
        supports_checkpointing=False,
        supports_partial_results=False,
        supports_cloud_storage=False,
        priority=5
    )
}

# -----------------------------------------------------------------------------
# Execution Model Specification
# -----------------------------------------------------------------------------

@dataclass
class ExecutionModelSpec:
    """Detailed specification of an execution model with transition analysis capabilities."""
    
    # Core model information
    model: str  # e.g., "shared_filesystem", "distributed_computing", "cloud_native"
    source_format: str  # Original workflow format
    detection_method: str  # "extension", "content", "user_specified"
    # detection_confidence: float  # 0.0 to 1.0 (REMOVED)
    
    # Execution environment characteristics
    filesystem_type: str = "unknown"  # shared, distributed, hybrid, cloud_storage, local
    resource_management: str = "unknown"  # implicit, explicit, dynamic, cloud_managed, constrained
    environment_isolation: str = "unknown"  # none, conda, container, cloud_runtime
    file_transfer_mode: str = "unknown"  # none, manual, automatic, cloud_storage, minimal
    
    # Requirements flags
    requires_file_transfer: bool = False
    requires_resource_specification: bool = False
    requires_environment_isolation: bool = False
    requires_error_handling: bool = False
    
    # Detection evidence
    detection_indicators: List[str] = field(default_factory=list)  # Evidence for the classification
    
    # Transition analysis
    transition_notes: List[str] = field(default_factory=list)  # Notes about transitions to other models
    
    # Metadata
    created_at: Optional[str] = None  # ISO 8601 timestamp
    modified_at: Optional[str] = None  # ISO 8601 timestamp
    
    def __post_init__(self):
        """Set creation timestamp if not provided."""
        if self.created_at is None:
            from datetime import datetime, timezone
            self.created_at = datetime.now(timezone.utc).isoformat()
    
    def update_modified(self):
        """Update the modified timestamp."""
        from datetime import datetime, timezone
        self.modified_at = datetime.now(timezone.utc).isoformat()
    
    def get_environment_characteristics(self) -> Dict[str, Any]:
        """Get environment characteristics as a dictionary."""
        return {
            "filesystem_type": self.filesystem_type,
            "resource_management": self.resource_management,
            "environment_isolation": self.environment_isolation,
            "file_transfer_mode": self.file_transfer_mode,
            "requires_file_transfer": self.requires_file_transfer,
            "requires_resource_specification": self.requires_resource_specification,
            "requires_environment_isolation": self.requires_environment_isolation,
            "requires_error_handling": self.requires_error_handling
        }
    
    def is_compatible_with(self, target_model: str) -> bool:
        """Check if this model is compatible with a target model."""
        # Same model is always compatible
        if self.model == target_model:
            return True
        
        # Shared filesystem is compatible with most models
        if self.model == "shared_filesystem":
            return True
        
        # Distributed computing is compatible with cloud and hybrid
        if self.model == "distributed_computing" and target_model in ["cloud_native", "hybrid"]:
            return True
        
        # Cloud native is compatible with hybrid
        if self.model == "cloud_native" and target_model == "hybrid":
            return True
        
        return False
    
    def get_transition_requirements(self, target_model: str) -> List[str]:
        """Get list of requirements for transitioning to target model."""
        requirements = []
        
        if target_model == "distributed_computing":
            if not self.requires_file_transfer:
                requirements.append("file_transfer_specification")
            if not self.requires_resource_specification:
                requirements.append("resource_specification")
            if not self.requires_environment_isolation:
                requirements.append("environment_isolation")
            if not self.requires_error_handling:
                requirements.append("error_handling_specification")
        
        elif target_model == "cloud_native":
            if not self.requires_file_transfer:
                requirements.append("cloud_storage_specification")
            if not self.requires_resource_specification:
                requirements.append("cloud_resource_specification")
            if not self.requires_environment_isolation:
                requirements.append("cloud_runtime_specification")
            if not self.requires_error_handling:
                requirements.append("cloud_error_handling")
        
        return requirements

# -----------------------------------------------------------------------------
# Enhanced Metadata Classes (Environment-Agnostic)
# -----------------------------------------------------------------------------

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
    """CWL v1.2.1 parameter specification for inputs and outputs with environment awareness."""

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

    # Wildcard pattern support (for Snakemake compatibility)
    wildcard_pattern: Optional[str] = None  # e.g., "data/{sample}_{replicate}.txt"

    # Environment-specific file transfer behavior
    transfer_mode: EnvironmentSpecificValue[str] = field(default_factory=lambda: EnvironmentSpecificValue("auto"))
    staging_required: EnvironmentSpecificValue[bool] = field(default_factory=lambda: EnvironmentSpecificValue(False))
    cleanup_after: EnvironmentSpecificValue[bool] = field(default_factory=lambda: EnvironmentSpecificValue(False))

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
    # Wildcard instances for each scatter instance (for Snakemake compatibility)
    wildcard_instances: List[Dict[str, str]] = field(default_factory=list)


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

@dataclass
class CheckpointSpec:
    strategy: Optional[str] = None  # e.g., "filesystem", "object_storage", "none"
    interval: Optional[int] = None  # seconds
    storage_location: Optional[str] = None
    enabled: Optional[bool] = None
    notes: Optional[str] = None

@dataclass
class LoggingSpec:
    log_level: Optional[str] = None  # e.g., "INFO", "DEBUG"
    log_format: Optional[str] = None  # e.g., "json", "text"
    log_destination: Optional[str] = None  # e.g., file path, cloud sink
    aggregation: Optional[str] = None  # e.g., "syslog", "cloudwatch"
    notes: Optional[str] = None

@dataclass
class SecuritySpec:
    encryption: Optional[str] = None  # e.g., "AES256", "KMS"
    access_policies: Optional[str] = None  # e.g., IAM role, ACL
    secrets: Optional[Dict[str, str]] = field(default_factory=dict)
    authentication: Optional[str] = None  # e.g., "kerberos", "oauth"
    notes: Optional[str] = None

@dataclass
class NetworkingSpec:
    network_mode: Optional[str] = None  # e.g., "host", "bridge", "vpc"
    allowed_ports: Optional[List[int]] = field(default_factory=list)
    egress_rules: Optional[List[str]] = field(default_factory=list)
    ingress_rules: Optional[List[str]] = field(default_factory=list)
    notes: Optional[str] = None

# -----------------------------------------------------------------------------
# Universal Environment-Aware Task
# -----------------------------------------------------------------------------

@dataclass
class Task:
    """A single executable node in the workflow DAG with universal environment awareness."""

    # Core identification (environment-agnostic)
    id: str
    label: Optional[str] = None
    doc: Optional[str] = None

    # Execution (environment-specific)
    command: EnvironmentSpecificValue[str] = field(default_factory=lambda: EnvironmentSpecificValue(None))
    script: EnvironmentSpecificValue[str] = field(default_factory=lambda: EnvironmentSpecificValue(None))

    # I/O (environment-specific)
    inputs: List[ParameterSpec] = field(default_factory=list)
    outputs: List[ParameterSpec] = field(default_factory=list)

    # Advanced features (environment-specific)
    when: EnvironmentSpecificValue[str] = field(default_factory=lambda: EnvironmentSpecificValue(None))
    scatter: EnvironmentSpecificValue[ScatterSpec] = field(default_factory=lambda: EnvironmentSpecificValue(None))

    # Resources (universally environment-aware)
    cpu: EnvironmentSpecificValue[int] = field(default_factory=lambda: EnvironmentSpecificValue(1))
    mem_mb: EnvironmentSpecificValue[int] = field(default_factory=lambda: EnvironmentSpecificValue(4096))
    disk_mb: EnvironmentSpecificValue[int] = field(default_factory=lambda: EnvironmentSpecificValue(4096))
    gpu: EnvironmentSpecificValue[int] = field(default_factory=lambda: EnvironmentSpecificValue(0))
    gpu_mem_mb: EnvironmentSpecificValue[int] = field(default_factory=lambda: EnvironmentSpecificValue(0))
    time_s: EnvironmentSpecificValue[int] = field(default_factory=lambda: EnvironmentSpecificValue(3600))
    threads: EnvironmentSpecificValue[int] = field(default_factory=lambda: EnvironmentSpecificValue(1))

    # Environment isolation (environment-specific)
    conda: EnvironmentSpecificValue[str] = field(default_factory=lambda: EnvironmentSpecificValue(None))
    container: EnvironmentSpecificValue[str] = field(default_factory=lambda: EnvironmentSpecificValue(None))
    workdir: EnvironmentSpecificValue[str] = field(default_factory=lambda: EnvironmentSpecificValue(None))
    env_vars: EnvironmentSpecificValue[Dict[str, str]] = field(default_factory=lambda: EnvironmentSpecificValue({}))
    modules: EnvironmentSpecificValue[List[str]] = field(default_factory=lambda: EnvironmentSpecificValue([]))

    # Error handling (environment-specific)
    retry_count: EnvironmentSpecificValue[int] = field(default_factory=lambda: EnvironmentSpecificValue(0))
    retry_delay: EnvironmentSpecificValue[int] = field(default_factory=lambda: EnvironmentSpecificValue(60))
    retry_backoff: EnvironmentSpecificValue[str] = field(default_factory=lambda: EnvironmentSpecificValue("none"))
    max_runtime: EnvironmentSpecificValue[int] = field(default_factory=lambda: EnvironmentSpecificValue(None))
    checkpoint_interval: EnvironmentSpecificValue[int] = field(default_factory=lambda: EnvironmentSpecificValue(None))

    # Track whether retry settings were explicitly set by user (vs. inferred)
    _explicit_retry_settings: Set[str] = field(default_factory=set, init=False, repr=False, compare=False)  # Set of environments where retries were explicitly set

    # Failure handling (environment-specific)
    on_failure: EnvironmentSpecificValue[str] = field(default_factory=lambda: EnvironmentSpecificValue("stop"))
    failure_notification: EnvironmentSpecificValue[str] = field(default_factory=lambda: EnvironmentSpecificValue(None))
    cleanup_on_failure: EnvironmentSpecificValue[bool] = field(default_factory=lambda: EnvironmentSpecificValue(True))

    # Recovery options (environment-specific)
    restart_from_checkpoint: EnvironmentSpecificValue[bool] = field(default_factory=lambda: EnvironmentSpecificValue(False))
    partial_results: EnvironmentSpecificValue[bool] = field(default_factory=lambda: EnvironmentSpecificValue(False))

    # Priority and scheduling (environment-specific)
    priority: EnvironmentSpecificValue[int] = field(default_factory=lambda: EnvironmentSpecificValue(0))

    # File transfer (environment-specific)
    file_transfer_mode: EnvironmentSpecificValue[str] = field(default_factory=lambda: EnvironmentSpecificValue("auto"))
    staging_required: EnvironmentSpecificValue[bool] = field(default_factory=lambda: EnvironmentSpecificValue(False))
    cleanup_after: EnvironmentSpecificValue[bool] = field(default_factory=lambda: EnvironmentSpecificValue(False))

    # Cloud-specific options (environment-specific)
    cloud_provider: EnvironmentSpecificValue[str] = field(default_factory=lambda: EnvironmentSpecificValue(None))
    cloud_storage_class: EnvironmentSpecificValue[str] = field(default_factory=lambda: EnvironmentSpecificValue(None))
    cloud_encryption: EnvironmentSpecificValue[bool] = field(default_factory=lambda: EnvironmentSpecificValue(False))

    # Performance options (environment-specific)
    parallel_transfers: EnvironmentSpecificValue[int] = field(default_factory=lambda: EnvironmentSpecificValue(1))
    bandwidth_limit: EnvironmentSpecificValue[str] = field(default_factory=lambda: EnvironmentSpecificValue(None))

    # Requirements and hints (environment-specific)
    requirements: EnvironmentSpecificValue[List[RequirementSpec]] = field(default_factory=lambda: EnvironmentSpecificValue([]))
    hints: EnvironmentSpecificValue[List[RequirementSpec]] = field(default_factory=lambda: EnvironmentSpecificValue([]))

    # Add new environment-specific advanced features
    checkpointing: EnvironmentSpecificValue[CheckpointSpec] = field(default_factory=lambda: EnvironmentSpecificValue(None))
    logging: EnvironmentSpecificValue[LoggingSpec] = field(default_factory=lambda: EnvironmentSpecificValue(None))
    security: EnvironmentSpecificValue[SecuritySpec] = field(default_factory=lambda: EnvironmentSpecificValue(None))
    networking: EnvironmentSpecificValue[NetworkingSpec] = field(default_factory=lambda: EnvironmentSpecificValue(None))

    # Metadata and provenance (environment-agnostic)
    provenance: Optional[ProvenanceSpec] = None
    documentation: Optional[DocumentationSpec] = None
    intent: List[str] = field(default_factory=list)  # Ontology IRIs

    # Comprehensive metadata storage for uninterpreted data
    metadata: Optional[MetadataSpec] = None

    # Extensions
    extra: Dict[str, EnvironmentSpecificValue] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Environment Adaptation Methods
    # ------------------------------------------------------------------

    def get_for_environment(self, environment: str) -> Dict[str, Any]:
        """Get all values applicable to the given environment."""
        result = {}
        
        # Get all environment-specific values with default fallback
        for field_name, field_value in self.__dict__.items():
            if isinstance(field_value, EnvironmentSpecificValue):
                value = field_value.get_value_with_default(environment)
                if value is not None:
                    result[field_name] = value
            elif field_name not in ['id', 'label', 'doc', 'provenance', 'documentation', 'intent', 'inputs', 'outputs', 'extra']:
                # Non-environment-specific fields
                result[field_name] = field_value
        
        # Handle special cases
        if 'scatter' in result and result['scatter'] is not None:
            result['scatter'] = result['scatter']  # Already a ScatterSpec
        
        return result

    def set_for_environment(self, field_name: str, value: Any, environment: str):
        """Set a value for a specific environment."""
        if hasattr(self, field_name):
            field_value = getattr(self, field_name)
            if isinstance(field_value, EnvironmentSpecificValue):
                # Update existing EnvironmentSpecificValue
                field_value.set_for_environment(value, environment)
            else:
                # Create new EnvironmentSpecificValue
                env_value = EnvironmentSpecificValue(
                    value=value,
                    environments=[environment]
                )
                setattr(self, field_name, env_value)
        else:
            # Create new EnvironmentSpecificValue for extra field
            env_value = EnvironmentSpecificValue(
                value=value,
                environments=[environment]
            )
            self.extra[field_name] = env_value

    def add_environment_to_field(self, field_name: str, environment: str):
        """Add an environment to an existing field's applicable environments."""
        if hasattr(self, field_name):
            field_value = getattr(self, field_name)
            if isinstance(field_value, EnvironmentSpecificValue):
                field_value.add_environment(environment)
        elif field_name in self.extra:
            self.extra[field_name].add_environment(environment)

    def set_retry_explicitly(self, retry_count: int, environment: str):
        """Set retry count explicitly (user-specified, not inferred)."""
        self.retry_count.set_for_environment(retry_count, environment)
        self._explicit_retry_settings.add(environment)
    
    def set_retry_inferred(self, retry_count: int, environment: str):
        """Set retry count as inferred (system-specified, not user-specified)."""
        self.retry_count.set_for_environment(retry_count, environment)
        # Don't add to explicit settings
    
    def has_explicit_retry_for_environment(self, environment: str) -> bool:
        """Check if retry settings were explicitly set for the given environment."""
        return environment in self._explicit_retry_settings

    def copy(self) -> "Task":
        """Create a deep copy of this task."""
        # Create a new task with the same basic attributes
        new_task = Task(
            id=self.id,
            label=self.label,
            doc=self.doc,
            inputs=self.inputs.copy() if self.inputs else [],
            outputs=self.outputs.copy() if self.outputs else [],
            provenance=self.provenance,
            documentation=self.documentation,
            intent=self.intent.copy() if self.intent else [],
            metadata=self.metadata
        )
        
        # Copy all environment-specific values
        for field_name, field_value in self.__dict__.items():
            if isinstance(field_value, EnvironmentSpecificValue):
                # Create a new EnvironmentSpecificValue with the same values
                new_env_value = EnvironmentSpecificValue()
                new_env_value.default_value = field_value.default_value
                new_env_value.values = [entry.copy() for entry in field_value.values]
                setattr(new_task, field_name, new_env_value)
            elif field_name not in ['id', 'label', 'doc', 'inputs', 'outputs', 'provenance', 'documentation', 'intent', 'metadata', 'extra']:
                # Copy non-environment-specific fields
                setattr(new_task, field_name, field_value)
        
        # Copy extra fields
        for key, value in self.extra.items():
            if isinstance(value, EnvironmentSpecificValue):
                new_env_value = EnvironmentSpecificValue()
                new_env_value.default_value = value.default_value
                new_env_value.values = [entry.copy() for entry in value.values]
                new_task.extra[key] = new_env_value
            else:
                new_task.extra[key] = value
        
        # Copy explicit retry settings
        new_task._explicit_retry_settings = self._explicit_retry_settings.copy()
        
        return new_task

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary for JSON serialization, excluding internal fields."""
        result = {}
        for field_name, field_value in self.__dict__.items():
            if field_name.startswith('_'):
                continue  # Skip internal fields
            result[field_name] = field_value
        return result

    # ------------------------------------------------------------------
    # Runtime helpers (non-persistent)
    # ------------------------------------------------------------------

    def is_active(self, context: Optional[Dict[str, Any]] = None, environment: str = "shared_filesystem") -> bool:
        """Evaluate the *when* expression (if any) against *context* variables for the given environment."""

        from wf2wf.expression import evaluate as _eval  # lazy import to avoid cycles

        when_value = self.when.get_value_for(environment)
        if when_value is None:
            return True
        try:
            result = _eval(when_value, context or {})
        except Exception:
            # Conservative: if expression fails, assume task should run
            return True
        return bool(result)

    def scatter_bindings(self, runtime_inputs: Dict[str, Any], environment: str = "shared_filesystem") -> List[Dict[str, Any]]:
        """Return a list of variable bindings for each scatter shard for the given environment."""

        from wf2wf.scatter import expand as _expand

        scatter_value = self.scatter.get_value_for(environment)
        if scatter_value is None:
            return [{}]

        names = scatter_value.scatter
        values = [runtime_inputs.get(n, []) for n in names]
        spec = dict(zip(names, values))
        return _expand(spec, method=scatter_value.scatter_method)

# -----------------------------------------------------------------------------
# Workflow Structure
# -----------------------------------------------------------------------------

@dataclass
class Edge:
    """Directed edge relating *parent* → *child* task."""

    parent: str
    child: str


@dataclass
class Workflow:
    """A collection of *Task*s plus dependency edges and optional metadata with universal environment awareness."""

    # Core identification (environment-agnostic)
    name: str
    version: str = "1.0"
    label: Optional[str] = None
    doc: Optional[str] = None

    # Workflow structure (environment-agnostic)
    tasks: Dict[str, Task] = field(default_factory=dict)
    edges: List[Edge] = field(default_factory=list)

    # Enhanced I/O (environment-specific)
    inputs: List[ParameterSpec] = field(default_factory=list)
    outputs: List[ParameterSpec] = field(default_factory=list)

    # Requirements and hints (environment-specific)
    requirements: EnvironmentSpecificValue[List[RequirementSpec]] = field(default_factory=lambda: EnvironmentSpecificValue([]))
    hints: EnvironmentSpecificValue[List[RequirementSpec]] = field(default_factory=lambda: EnvironmentSpecificValue([]))

    # Metadata and provenance (environment-agnostic)
    provenance: Optional[ProvenanceSpec] = None
    documentation: Optional[DocumentationSpec] = None
    intent: List[str] = field(default_factory=list)  # Ontology IRIs
    cwl_version: Optional[str] = None

    # BCO integration (environment-agnostic)
    bco_spec: Optional[BCOSpec] = None

    # Loss mapping entries captured during export (optional)
    loss_map: List[Dict[str, Any]] = field(default_factory=list)

    # Comprehensive metadata storage for uninterpreted data
    metadata: Optional[MetadataSpec] = None

    # Extensions
    extra: Dict[str, EnvironmentSpecificValue] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Convenience helpers
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

    def copy(self) -> "Workflow":
        """Create a deep copy of this workflow."""
        # Create a new workflow with the same basic attributes
        new_workflow = Workflow(
            name=self.name,
            version=self.version,
            label=self.label,
            doc=self.doc,
            inputs=self.inputs.copy() if self.inputs else [],
            outputs=self.outputs.copy() if self.outputs else [],
            provenance=self.provenance,
            documentation=self.documentation,
            intent=self.intent.copy() if self.intent else [],
            cwl_version=self.cwl_version,
            bco_spec=self.bco_spec,
            loss_map=self.loss_map.copy() if self.loss_map else [],
            metadata=self.metadata
        )
        
        # Copy all environment-specific values
        for field_name, field_value in self.__dict__.items():
            if isinstance(field_value, EnvironmentSpecificValue):
                # Create a new EnvironmentSpecificValue with the same values
                new_env_value = EnvironmentSpecificValue()
                new_env_value.default_value = field_value.default_value
                new_env_value.values = [entry.copy() for entry in field_value.values]
                setattr(new_workflow, field_name, new_env_value)
            elif field_name not in ['name', 'version', 'label', 'doc', 'inputs', 'outputs', 'provenance', 'documentation', 'intent', 'cwl_version', 'bco_spec', 'loss_map', 'metadata', 'tasks', 'edges', 'extra']:
                # Copy non-environment-specific fields
                setattr(new_workflow, field_name, field_value)
        
        # Copy tasks
        for task_id, task in self.tasks.items():
            new_workflow.tasks[task_id] = task.copy()
        
        # Copy edges
        new_workflow.edges = [Edge(parent=edge.parent, child=edge.child) for edge in self.edges]
        
        # Copy extra fields
        for key, value in self.extra.items():
            if isinstance(value, EnvironmentSpecificValue):
                new_env_value = EnvironmentSpecificValue()
                new_env_value.default_value = value.default_value
                new_env_value.values = [entry.copy() for entry in value.values]
                new_workflow.extra[key] = new_env_value
            else:
                new_workflow.extra[key] = value
        
        return new_workflow

    def get_for_environment(self, environment: str) -> Dict[str, Any]:
        """Get workflow configuration for the given environment."""
        result = {
            'name': self.name,
            'version': self.version,
            'label': self.label,
            'doc': self.doc,
            'tasks': {},
            'edges': [{'parent': e.parent, 'child': e.child} for e in self.edges],
            'inputs': self.inputs,
            'outputs': self.outputs,
            'provenance': self.provenance,
            'documentation': self.documentation,
            'intent': self.intent,
            'cwl_version': self.cwl_version,
            'bco_spec': self.bco_spec,
            'loss_map': self.loss_map
        }
        
        # Get environment-specific requirements and hints
        requirements = self.requirements.get_value_for(environment)
        if requirements is not None:
            result['requirements'] = requirements
        else:
            result['requirements'] = []
            
        hints = self.hints.get_value_for(environment)
        if hints is not None:
            result['hints'] = hints
        else:
            result['hints'] = []
        
        # Get environment-specific task configurations
        for task_id, task in self.tasks.items():
            result['tasks'][task_id] = task.get_for_environment(environment)
            result['tasks'][task_id]['id'] = task_id  # Ensure ID is included
        
        # Get environment-specific execution model
        # execution_model = self.execution_model.get_value_for(environment) # This line is removed
        # if execution_model:
        #     result['execution_model'] = execution_model
        
        return result

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-Python representation ready for JSON/TOML dump."""
        result = asdict(self)
        
        # Remove _explicit_retry_settings from all tasks to avoid JSON schema validation issues
        for task_id, task_data in result.get('tasks', {}).items():
            if '_explicit_retry_settings' in task_data:
                del task_data['_explicit_retry_settings']
        
        return result

    def to_json(self, *, indent: int = 2) -> str:
        """Return JSON representation using custom encoder."""
        import json

        return json.dumps(self.to_dict(), indent=indent, cls=WF2WFJSONEncoder, sort_keys=True)

    def save_json(self, path: Union[str, Path], *, indent: int = 2):
        """Write JSON representation to path using custom encoder."""
        import json
        
        _p = Path(path)
        _p.parent.mkdir(parents=True, exist_ok=True)
        _p.write_text(json.dumps(self.to_dict(), indent=indent, cls=WF2WFJSONEncoder, sort_keys=True))

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
        
        # Define _make_params function before using it
        def _make_params(items):
            converted = []
            for p in items:
                if isinstance(p, ParameterSpec):
                    converted.append(p)
                elif isinstance(p, str):
                    converted.append(ParameterSpec(id=p, type="string"))
                elif isinstance(p, dict):
                    # Handle EnvironmentSpecificValue fields in ParameterSpec
                    for field_name, field_value in p.items():
                        if isinstance(field_value, dict) and "values" in field_value:
                            p[field_name] = WF2WFJSONDecoder.decode_environment_specific_value(field_value)
                    converted.append(ParameterSpec(**p))
                else:
                    raise TypeError(f"Unsupported parameter spec item: {p}")
            return converted
        
        for tid, tdict in tasks_data.items():
            tdict = tdict.copy()
            
            # Handle EnvironmentSpecificValue fields in task data
            for field_name, field_value in tdict.items():
                if isinstance(field_value, dict) and "values" in field_value:
                    # This is an EnvironmentSpecificValue
                    env_value = WF2WFJSONDecoder.decode_environment_specific_value(field_value)
                    
                    # Special handling for spec classes within EnvironmentSpecificValue
                    if field_name in ["checkpointing", "logging", "security", "networking"]:
                        # Decode spec objects within the EnvironmentSpecificValue
                        for entry in env_value.values:
                            if isinstance(entry.get("value"), dict):
                                if field_name == "checkpointing":
                                    entry["value"] = WF2WFJSONDecoder.decode_spec(entry["value"], CheckpointSpec)
                                elif field_name == "logging":
                                    entry["value"] = WF2WFJSONDecoder.decode_spec(entry["value"], LoggingSpec)
                                elif field_name == "security":
                                    entry["value"] = WF2WFJSONDecoder.decode_spec(entry["value"], SecuritySpec)
                                elif field_name == "networking":
                                    entry["value"] = WF2WFJSONDecoder.decode_spec(entry["value"], NetworkingSpec)
                    
                    tdict[field_name] = env_value
            
            # Convert inputs and outputs to ParameterSpec objects
            if "inputs" in tdict:
                tdict["inputs"] = _make_params(tdict["inputs"])
            if "outputs" in tdict:
                tdict["outputs"] = _make_params(tdict["outputs"])

            # Handle extra field specially - it contains EnvironmentSpecificValue objects
            if "extra" in tdict and isinstance(tdict["extra"], dict):
                extra_decoded = {}
                for key, value in tdict["extra"].items():
                    if isinstance(value, dict) and "values" in value:
                        # This is an EnvironmentSpecificValue
                        extra_decoded[key] = WF2WFJSONDecoder.decode_environment_specific_value(value)
                    else:
                        # This is a plain value, wrap it in EnvironmentSpecificValue
                        extra_decoded[key] = EnvironmentSpecificValue(value)
                tdict["extra"] = extra_decoded

            # Handle metadata field specially for Task
            if "metadata" in tdict and isinstance(tdict["metadata"], dict):
                tdict["metadata"] = MetadataSpec(**tdict["metadata"])

            tasks[tid] = Task(id=tid, **{k: v for k, v in tdict.items() if k != "id"})

        edges = [Edge(**e) for e in data.pop("edges", [])]

        # Workflow-level inputs / outputs
        if "inputs" in data:
            data["inputs"] = _make_params(data["inputs"])
        if "outputs" in data:
            data["outputs"] = _make_params(data["outputs"])

        # Handle EnvironmentSpecificValue fields in workflow data
        for field_name, field_value in data.items():
            if isinstance(field_value, dict) and "values" in field_value:
                data[field_name] = WF2WFJSONDecoder.decode_environment_specific_value(field_value)

        # Handle metadata field specially
        if "metadata" in data and isinstance(data["metadata"], dict):
            data["metadata"] = MetadataSpec(**data["metadata"])

        # Remove execution_model field if present (no longer part of Workflow IR)
        data.pop("execution_model", None)

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
            
            # Get requirements and hints values for validation
            requirements = t.requirements.get_value_for("shared_filesystem") or []
            hints = t.hints.get_value_for("shared_filesystem") or []
            for req in requirements + hints:
                req.validate()

        #    – Workflow-level inputs/outputs
        for p in self.inputs + self.outputs:
            p.validate()

        #    – Requirements/hints
        workflow_requirements = self.requirements.get_value_for("shared_filesystem") or []
        workflow_hints = self.hints.get_value_for("shared_filesystem") or []
        for r in workflow_requirements + workflow_hints:
            r.validate()

# -----------------------------------------------------------------------------
# Environment Adaptation
# -----------------------------------------------------------------------------

class EnvironmentAdapter:
    """Adapt workflows for specific execution environments."""
    
    def __init__(self, workflow: Workflow):
        self.workflow = workflow
    
    def adapt_for_environment(self, target_env: str) -> Workflow:
        """Adapt workflow for specific execution environment."""
        import copy
        adapted_workflow = copy.deepcopy(self.workflow)
        
        # Apply environment-specific optimizations
        for task in adapted_workflow.tasks.values():
            self._apply_environment_optimizations(task, target_env)
        
        return adapted_workflow
    
    def _apply_environment_optimizations(self, task: Task, env: str):
        """Apply environment-specific optimizations."""
        env_config = EXECUTION_ENVIRONMENTS.get(env)
        if not env_config:
            return
        
        # Apply default resource specifications if needed
        if env_config.default_resource_specification:
            if task.cpu.get_value_for(env) is None:
                task.cpu.set_for_environment(1, env)
            if task.mem_mb.get_value_for(env) is None:
                task.mem_mb.set_for_environment(4096, env)
            if task.disk_mb.get_value_for(env) is None:
                task.disk_mb.set_for_environment(4096, env)
        
        # Apply default error handling if needed
        if env_config.default_error_handling:
            if task.retry_count.get_value_for(env) is None:
                task.set_retry_inferred(2, env)
        
        # Apply default environment isolation if needed
        if env_config.default_environment_isolation:
            if task.container.get_value_for(env) is None and task.conda.get_value_for(env) is None:
                # Add default container for distributed/cloud environments
                if env in ["distributed_computing", "cloud_native"]:
                    task.container.set_for_environment("default-runtime:latest", env)

# -----------------------------------------------------------------------------
# JSON Serialization Support
# -----------------------------------------------------------------------------

class WF2WFJSONDecoder:
    """Custom JSON decoder for wf2wf dataclasses and objects. Only supports the new EnvironmentSpecificValue format."""
    
    @classmethod
    def decode_environment_specific_value(cls, data: Dict[str, Any]) -> EnvironmentSpecificValue:
        """Decode EnvironmentSpecificValue from JSON data (new format only)."""
        if not isinstance(data, dict):
            return EnvironmentSpecificValue()
        env_value = EnvironmentSpecificValue()
        
        # Handle default_value field
        if "default_value" in data:
            env_value.default_value = data["default_value"]
        
        try:
            if "values" in data and isinstance(data["values"], list):
                for value_entry in data["values"]:
                    if isinstance(value_entry, dict):
                        value = value_entry.get("value")
                        environments = value_entry.get("environments", [])
                        
                        # Normalize environments: flatten nested lists and remove None values
                        if isinstance(environments, list):
                            # Flatten any nested lists
                            flat_envs = []
                            for env in environments:
                                if isinstance(env, list):
                                    flat_envs.extend(env)
                                elif env is not None:
                                    flat_envs.append(env)
                            environments = flat_envs
                        else:
                            environments = []
                        
                        # Remove any remaining None values
                        environments = [e for e in environments if e is not None]
                        
                        # Handle spec objects within values
                        if isinstance(value, dict):
                            # Check if this looks like a spec object by checking for common fields
                            if any(key in value for key in ['strategy', 'interval', 'enabled', 'notes']):
                                # This looks like a CheckpointSpec
                                value = cls.decode_spec(value, CheckpointSpec)
                            elif any(key in value for key in ['log_level', 'log_format', 'log_destination', 'aggregation']):
                                # This looks like a LoggingSpec
                                value = cls.decode_spec(value, LoggingSpec)
                            elif any(key in value for key in ['encryption', 'access_policies', 'secrets', 'authentication']):
                                # This looks like a SecuritySpec
                                value = cls.decode_spec(value, SecuritySpec)
                            elif any(key in value for key in ['network_mode', 'allowed_ports', 'egress_rules', 'ingress_rules']):
                                # This looks like a NetworkingSpec
                                value = cls.decode_spec(value, NetworkingSpec)
                        
                        if value is not None:
                            # Remove any existing values for these environments
                            for env in environments:
                                env_value.remove_environment(env)
                            # Add new value with all environments
                            env_value.values.append({
                                "value": value,
                                "environments": environments
                            })
                        else:
                            # For each environment, check if it has a None value
                            envs_needing_none = []
                            for env in environments:
                                current_value = env_value.get_value_for(env)
                                if current_value is None:
                                    env_value.remove_environment(env)
                                    envs_needing_none.append(env)
                            
                            # Add None value for environments that need it
                            if envs_needing_none:
                                env_value.values.append({
                                    "value": None,
                                    "environments": envs_needing_none
                                })
        except Exception as e:
            print(f"Warning: Failed to decode EnvironmentSpecificValue: {e}")
            return EnvironmentSpecificValue()
        return env_value

    @classmethod
    def decode_spec(cls, data: Dict[str, Any], spec_class) -> Any:
        """Decode spec objects from JSON data."""
        if not isinstance(data, dict):
            return None
        try:
            # Get valid argument names for the spec_class constructor
            import inspect
            valid_args = set()
            for c in inspect.getmro(spec_class):
                if hasattr(c, '__dataclass_fields__'):
                    valid_args.update(c.__dataclass_fields__.keys())
            # Reconstruct EnvironmentSpecificValue fields if present
            for k, v in list(data.items()):
                if isinstance(v, dict) and "values" in v:
                    data[k] = cls.decode_environment_specific_value(v)
            # Filter out None values, keys starting with '_', and invalid keys
            filtered_data = {k: v for k, v in data.items() if v is not None and not k.startswith('_') and k in valid_args}
            
            # Check if we have enough data to create the spec object
            # Check if we have any required fields
            if not filtered_data:
                return None
            
            # Create the spec class instance
            return spec_class(**filtered_data)
        except Exception as e:
            print(f"Warning: Failed to decode {spec_class.__name__}: {e}")
            return None

class WF2WFJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for wf2wf dataclasses and objects."""
    
    def default(self, obj: Any) -> Any:
        """Convert wf2wf objects to JSON-serializable format."""
        
        # Handle EnvironmentSpecificValue objects
        if isinstance(obj, EnvironmentSpecificValue):
            try:
                if not obj.values and obj.default_value is None:
                    return {
                        "values": [],
                        "environments": [],
                        "default_value": None
                    }
                
                # Convert all values with proper environment handling
                serialized_values = []
                for entry in obj.values:
                    if isinstance(entry, dict) and "value" in entry:
                        serialized_values.append({
                            "value": entry["value"],
                            "environments": list(entry.get("environments", set())),  # Convert set to list
                        })
                
                return {
                    "values": serialized_values,
                    "environments": list(obj.all_environments()),  # Convert set to list
                    "default_value": obj.default_value
                }
            except Exception as e:
                # Fallback for malformed EnvironmentSpecificValue
                return {
                    "values": [],
                    "environments": [],
                    "default_value": None,
                    "_error": f"Failed to serialize EnvironmentSpecificValue: {str(e)}"
                }
        
        # Handle TypeSpec objects
        if isinstance(obj, TypeSpec):
            try:
                result = {
                    "type": obj.type,
                    "nullable": obj.nullable
                }
                # Only include non-None fields
                if obj.items is not None:
                    result["items"] = obj.items
                if obj.fields:
                    result["fields"] = obj.fields
                if obj.symbols:
                    result["symbols"] = obj.symbols
                if obj.members:
                    result["members"] = obj.members
                if obj.name is not None:
                    result["name"] = obj.name
                if obj.default is not None:
                    result["default"] = obj.default
                return result
            except Exception as e:
                return {"_error": f"Failed to serialize TypeSpec: {str(e)}"}
        
        # Handle ParameterSpec objects
        if isinstance(obj, ParameterSpec):
            try:
                result = {
                    "id": obj.id,
                    "type": obj.type
                }
                # Only include non-None fields
                if obj.label is not None:
                    result["label"] = obj.label
                if obj.doc is not None:
                    result["doc"] = obj.doc
                if obj.default is not None:
                    result["default"] = obj.default
                if obj.format is not None:
                    result["format"] = obj.format
                if obj.secondary_files:
                    result["secondary_files"] = obj.secondary_files
                if obj.streamable:
                    result["streamable"] = obj.streamable
                if obj.load_contents:
                    result["load_contents"] = obj.load_contents
                if obj.load_listing is not None:
                    result["load_listing"] = obj.load_listing
                if obj.wildcard_pattern is not None:
                    result["wildcard_pattern"] = obj.wildcard_pattern
                if obj.input_binding is not None:
                    result["input_binding"] = obj.input_binding
                if obj.output_binding is not None:
                    result["output_binding"] = obj.output_binding
                if obj.value_from is not None:
                    result["value_from"] = obj.value_from
                # Include environment-specific fields only if they have values
                if hasattr(obj, 'transfer_mode') and obj.transfer_mode.values:
                    result["transfer_mode"] = obj.transfer_mode
                if hasattr(obj, 'staging_required') and obj.staging_required.values:
                    result["staging_required"] = obj.staging_required
                if hasattr(obj, 'cleanup_after') and obj.cleanup_after.values:
                    result["cleanup_after"] = obj.cleanup_after
                return result
            except Exception as e:
                return {"_error": f"Failed to serialize ParameterSpec: {str(e)}"}
        
        # Handle new spec classes
        if isinstance(obj, (CheckpointSpec, LoggingSpec, SecuritySpec, NetworkingSpec, MetadataSpec)):
            try:
                result = {}
                for field_name, field_value in obj.__dict__.items():
                    if field_value is not None:
                        # Handle special cases for collections
                        if isinstance(field_value, (list, dict)) and not field_value:
                            continue  # Skip empty collections
                        result[field_name] = field_value
                return result
            except Exception as e:
                return {"_error": f"Failed to serialize {type(obj).__name__}: {str(e)}"}
        
        # Handle Path objects
        if isinstance(obj, Path):
            return str(obj)
        
        # Handle any other dataclass recursively
        if is_dataclass(obj):
            try:
                # Use asdict with proper handling of nested dataclasses
                return asdict(obj, dict_factory=lambda x: {k: v for k, v in x if v is not None})
            except Exception as e:
                return {"_error": f"Failed to serialize dataclass {type(obj).__name__}: {str(e)}"}
        
        # Handle sets (convert to lists)
        if isinstance(obj, set):
            return list(obj)
        
        # Handle other common types that might not be JSON serializable
        if hasattr(obj, '__dict__'):
            try:
                return obj.__dict__
            except Exception:
                pass
        
        # Fall back to parent class
        return super().default(obj)

@dataclass
class MetadataSpec:
    """Comprehensive metadata storage for preserving uninterpreted data and format-specific information."""
    
    # Source format information
    source_format: Optional[str] = None  # e.g., "snakemake", "cwl", "dagman"
    source_file: Optional[str] = None    # Original file path
    source_version: Optional[str] = None # Format version
    original_execution_environment: Optional[str] = None  # Original execution environment (e.g., "shared_filesystem", "distributed_computing")
    original_source_format: Optional[str] = None  # Original source format (e.g., "snakemake", "cwl", "dagman")
    
    # Parsing and conversion metadata
    parsing_notes: List[str] = field(default_factory=list)  # Warnings, notes from parsing
    conversion_warnings: List[str] = field(default_factory=list)  # Issues during conversion
    
    # Format-specific data that couldn't be mapped to IR fields
    format_specific: Dict[str, Any] = field(default_factory=dict)  # e.g., {"snakemake_config": {...}}
    
    # Uninterpreted fields from source
    uninterpreted: Dict[str, Any] = field(default_factory=dict)  # Raw data that couldn't be parsed
    
    # Custom annotations and extensions
    annotations: Dict[str, Any] = field(default_factory=dict)  # User or tool annotations
    
    # Environment-specific metadata
    environment_metadata: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # env -> metadata
    
    # Validation and quality information
    validation_errors: List[str] = field(default_factory=list)
    quality_metrics: Dict[str, Any] = field(default_factory=dict)
    
    def add_format_specific(self, key: str, value: Any):
        """Add format-specific data."""
        self.format_specific[key] = value
    
    def add_uninterpreted(self, key: str, value: Any):
        """Add uninterpreted data from source."""
        self.uninterpreted[key] = value
    
    def add_parsing_note(self, note: str):
        """Add a parsing note or warning."""
        self.parsing_notes.append(note)
    
    def add_environment_metadata(self, environment: str, key: str, value: Any):
        """Add environment-specific metadata."""
        if environment not in self.environment_metadata:
            self.environment_metadata[environment] = {}
        self.environment_metadata[environment][key] = value
    
    def get_environment_metadata(self, environment: str) -> Dict[str, Any]:
        """Get metadata for a specific environment."""
        return self.environment_metadata.get(environment, {})
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary for JSON serialization."""
        result = {}
        
        # Add all non-empty fields
        if self.source_format is not None:
            result["source_format"] = self.source_format
        if self.source_file is not None:
            result["source_file"] = self.source_file
        if self.source_version is not None:
            result["source_version"] = self.source_version
        if self.original_execution_environment is not None:
            result["original_execution_environment"] = self.original_execution_environment
        if self.original_source_format is not None:
            result["original_source_format"] = self.original_source_format
            
        if self.parsing_notes:
            result["parsing_notes"] = self.parsing_notes
        if self.conversion_warnings:
            result["conversion_warnings"] = self.conversion_warnings
        if self.format_specific:
            result["format_specific"] = self.format_specific
        if self.uninterpreted:
            result["uninterpreted"] = self.uninterpreted
        if self.annotations:
            result["annotations"] = self.annotations
        if self.environment_metadata:
            result["environment_metadata"] = self.environment_metadata
        if self.validation_errors:
            result["validation_errors"] = self.validation_errors
        if self.quality_metrics:
            result["quality_metrics"] = self.quality_metrics
        
        return result
