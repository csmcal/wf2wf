"""wf2wf.importers.cwl – CWL v1.2 ➜ Workflow IR

This module imports Common Workflow Language (CWL) v1.2 workflows and converts
them to the wf2wf intermediate representation with full feature preservation.

Enhanced features supported:
- Advanced metadata and provenance tracking
- Conditional execution (when expressions)
- Scatter/gather operations with all scatter methods
- Complete parameter specifications with CWL type system
- Requirements and hints preservation
- File management with secondary files and validation
- BCO integration for regulatory compliance
"""

from __future__ import annotations

import json
import yaml
import subprocess
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from wf2wf.core import (
    Workflow,
    Task,
    Edge,
    ResourceSpec,
    EnvironmentSpec,
    ParameterSpec,
    ScatterSpec,
    RequirementSpec,
    ProvenanceSpec,
    DocumentationSpec,
)
from wf2wf.loss import apply as loss_apply
from wf2wf.loss import compute_checksum


def to_workflow(path: Union[str, Path], **opts: Any) -> Workflow:
    """Import a CWL workflow file and convert to wf2wf IR with full feature preservation.

    Args:
        path: Path to the CWL workflow file (.cwl)
        **opts: Additional options:
            - use_cwltool: bool = False - Use cwltool for complex parsing
            - preserve_metadata: bool = True - Preserve all CWL metadata
            - extract_provenance: bool = True - Extract provenance information
            - verbose: bool = False - Enable verbose output
            - debug: bool = False - Enable debug output

    Returns:
        Workflow: The converted workflow in wf2wf IR format with full CWL features

    Raises:
        RuntimeError: If the CWL file cannot be parsed or converted
        FileNotFoundError: If the CWL file doesn't exist
    """
    cwl_path = Path(path).resolve()
    if not cwl_path.exists():
        raise FileNotFoundError(f"CWL file not found: {cwl_path}")

    use_cwltool = opts.get("use_cwltool", False)
    preserve_metadata = opts.get("preserve_metadata", True)
    extract_provenance = opts.get("extract_provenance", True)
    verbose = opts.get("verbose", False)
    debug = opts.get("debug", False)

    if verbose:
        print(f"Importing CWL workflow with enhanced features: {cwl_path}")

    try:
        # Load CWL document
        cwl_doc = _load_cwl_document(cwl_path)

        # -------------------------------------------------------------
        # Direct class or $graph multi-document
        # -------------------------------------------------------------

        if "$graph" in cwl_doc:
            # Build mapping of id ➜ object
            graph_list = cwl_doc["$graph"]
            if not isinstance(graph_list, list):
                raise ValueError("$graph must be a list of CWL objects")

            graph_map = {}
            for obj in graph_list:
                obj_id = obj.get("id") or obj.get("label")
                if not obj_id:
                    raise ValueError("Each object in $graph must have an 'id' field")
                # Strip leading '#' if present
                graph_map[obj_id.lstrip("#")] = obj

            # Use the first Workflow object as entry point by default
            root_wf_obj = next(
                (o for o in graph_list if o.get("class") == "Workflow"), None
            )
            if root_wf_obj is None:
                raise ValueError("$graph does not contain a top-level Workflow object")

            workflow = _parse_cwl_workflow(
                root_wf_obj,
                cwl_path,
                preserve_metadata=preserve_metadata,
                extract_provenance=extract_provenance,
                verbose=verbose,
                debug=debug,
                graph_objects=graph_map,
            )

        # Single document Workflow
        elif cwl_doc.get("class") == "Workflow":
            workflow = _parse_cwl_workflow(
                cwl_doc,
                cwl_path,
                preserve_metadata=preserve_metadata,
                extract_provenance=extract_provenance,
                verbose=verbose,
                debug=debug,
            )
        elif cwl_doc.get("class") == "CommandLineTool":
            # Convert single tool to single-step workflow
            workflow = _convert_tool_to_workflow(
                cwl_doc, cwl_path, preserve_metadata=preserve_metadata, verbose=verbose
            )
        else:
            raise ValueError(f"Unsupported CWL class: {cwl_doc.get('class')}")

        # Enhanced parsing with cwltool if requested
        if use_cwltool:
            if not shutil.which("cwltool"):
                raise RuntimeError(
                    "The 'cwltool' executable was not found in your PATH. "
                    "Please install cwltool: 'pip install cwltool' or 'conda install cwltool'. "
                    "Alternatively, set use_cwltool=False to use direct parsing."
                )
            if verbose:
                print("Using cwltool for enhanced parsing...")
            workflow = _parse_with_cwltool(cwl_path, workflow, verbose=verbose)

        if verbose:
            print(
                f"Successfully imported CWL workflow with {len(workflow.tasks)} tasks"
            )
            print(
                f"Enhanced features: {len(workflow.requirements)} requirements, "
                f"{len(workflow.inputs)} inputs, {len(workflow.outputs)} outputs"
            )

        # ------------------------------------------------------------------
        # Reinject loss-map if sidecar exists
        # ------------------------------------------------------------------
        loss_path = cwl_path.with_suffix(".loss.json")
        if loss_path.exists():
            try:
                with open(loss_path) as fh:
                    doc = json.load(fh)
                    if doc.get("source_checksum") and doc[
                        "source_checksum"
                    ] != compute_checksum(workflow):
                        if verbose:
                            print(
                                f"Skipping loss-map from {loss_path} (checksum mismatch)"
                            )
                    else:
                        entries = doc.get("entries", [])
                        workflow.loss_map.extend(entries)
                        loss_apply(workflow, entries)  # best-effort reinjection
                        if verbose:
                            print(
                                f"Applied {len(entries)} loss-map entries from {loss_path}"
                            )
            except Exception as _e:
                if verbose:
                    print(f"Warning: could not apply loss-map ({_e})")

        return workflow

    except Exception as e:
        if debug:
            import traceback

            traceback.print_exc()
        raise RuntimeError(f"Failed to import CWL workflow: {e}")


def _load_cwl_document(cwl_path: Path) -> Dict[str, Any]:
    """Load and parse a CWL document from file."""
    try:
        with open(cwl_path, "r") as f:
            lines = f.readlines()
            if lines and lines[0].startswith("#!"):
                content = "".join(lines[1:])
            else:
                content = "".join(lines)

        try:
            return yaml.safe_load(content)
        except yaml.YAMLError as ye:
            raise RuntimeError(f"Failed to parse CWL YAML: {ye}")

    except Exception as e:
        raise RuntimeError(f"Failed to load CWL document: {e}")


def _parse_cwl_workflow(
    cwl_doc: Dict[str, Any],
    cwl_path: Path,
    preserve_metadata: bool = True,
    extract_provenance: bool = True,
    verbose: bool = False,
    debug: bool = False,
    graph_objects: Optional[Dict[str, Any]] = None,
) -> Workflow:
    """Parse a CWL workflow document into enhanced wf2wf IR."""

    # Extract workflow metadata
    workflow_name = cwl_doc.get("label", cwl_path.stem)
    workflow_version = "1.0"  # Default version

    # Create workflow with enhanced features
    workflow = Workflow(
        name=workflow_name,
        version=workflow_version,
        label=cwl_doc.get("label"),
        doc=cwl_doc.get("doc"),
        cwl_version=cwl_doc.get("cwlVersion", "v1.2"),
    )

    # Extract provenance information
    if extract_provenance and preserve_metadata:
        workflow.provenance = _extract_provenance_spec(cwl_doc)

    # Extract documentation
    if preserve_metadata:
        workflow.documentation = _extract_documentation_spec(cwl_doc)

    # Extract intent (ontology IRIs)
    if "intent" in cwl_doc:
        workflow.intent = (
            cwl_doc["intent"]
            if isinstance(cwl_doc["intent"], list)
            else [cwl_doc["intent"]]
        )

    # Parse workflow requirements and hints
    workflow.requirements = _parse_requirements(cwl_doc.get("requirements", []))
    workflow.hints = _parse_requirements(cwl_doc.get("hints", []))

    # Parse workflow inputs with enhanced parameter specifications
    workflow.inputs = _parse_parameter_specs(cwl_doc.get("inputs", {}), "input")

    # Parse workflow outputs with enhanced parameter specifications
    workflow.outputs = _parse_parameter_specs(cwl_doc.get("outputs", {}), "output")

    # Store original CWL metadata for backward compatibility
    workflow.meta = {
        "source_format": "cwl",
        "cwl_version": cwl_doc.get("cwlVersion", "v1.2"),
        "cwl_class": cwl_doc.get("class"),
        "original_cwl_doc": cwl_doc if preserve_metadata else {},
    }

    # Preserve expressionLib if present
    if "expressionLib" in cwl_doc:
        workflow.meta["expressionLib"] = cwl_doc["expressionLib"]

    # Parse workflow inputs as config for backward compatibility
    workflow.config = _parse_workflow_inputs_legacy(cwl_doc.get("inputs", {}))

    # Parse steps with enhanced features
    steps = cwl_doc.get("steps", {})
    if not steps:
        # Handle empty workflows gracefully
        if verbose:
            print(
                "Warning: CWL workflow has no steps defined - creating empty workflow"
            )
        return workflow

    tasks = {}
    edges = []

    for step_name, step_def in steps.items():
        if verbose:
            print(f"Processing step with enhanced features: {step_name}")

        # Parse the step with enhanced features
        task, step_edges = _parse_cwl_step_enhanced(
            step_name,
            step_def,
            cwl_path,
            preserve_metadata=preserve_metadata,
            verbose=verbose,
            debug=debug,
            graph_objects=graph_objects,
        )

        tasks[task.id] = task
        edges.extend(step_edges)

    # Add tasks and edges to workflow
    for task in tasks.values():
        workflow.add_task(task)

    for edge in edges:
        workflow.add_edge(edge.parent, edge.child)

    return workflow


def _parse_workflow_inputs(inputs: Union[Dict, List]) -> Dict[str, Any]:
    """Parse CWL workflow inputs into config dictionary."""
    config = {}

    if isinstance(inputs, dict):
        for input_name, input_def in inputs.items():
            if isinstance(input_def, dict):
                default_value = input_def.get("default")
                if default_value is not None:
                    config[input_name] = default_value
            else:
                # Simple type definition
                config[input_name] = None
    elif isinstance(inputs, list):
        for input_def in inputs:
            if isinstance(input_def, dict) and "id" in input_def:
                input_name = input_def["id"]
                default_value = input_def.get("default")
                if default_value is not None:
                    config[input_name] = default_value

    return config


def _parse_cwl_step(
    step_name: str,
    step_def: Dict[str, Any],
    cwl_path: Path,
    verbose: bool = False,
    debug: bool = False,
) -> tuple[Task, List[Edge]]:
    """Parse a single CWL workflow step into a Task and edges."""

    # Get the tool reference
    run_ref = step_def.get("run")
    if not run_ref:
        raise ValueError(f"Step {step_name} has no 'run' reference")

    # Load the tool definition
    tool_def = _load_tool_definition(run_ref, cwl_path, verbose=verbose)

    # Create task
    task = Task(id=step_name)

    # Extract command from tool
    if tool_def.get("class") == "CommandLineTool":
        task.command = _extract_command_from_tool(tool_def)
    else:
        task.command = f"# CWL step: {step_name}"

    # Extract resource requirements
    task.resources = _extract_resource_requirements(tool_def)

    # Extract environment (Docker/container)
    task.environment = _extract_environment_spec(tool_def)

    # Store CWL-specific metadata
    task.meta = {
        "cwl_step": step_name,
        "cwl_run": run_ref,
        "cwl_tool_class": tool_def.get("class"),
        "cwl_doc": tool_def.get("doc", ""),
        "cwl_label": tool_def.get("label", ""),
        "step_inputs": step_def.get("in", {}),
        "step_outputs": step_def.get("out", []),
    }

    # Parse step dependencies from inputs
    edges = _parse_step_dependencies(step_name, step_def)

    return task, edges


def _load_tool_definition(
    run_ref: Union[str, Dict[str, Any]],
    cwl_path: Path,
    graph_objects: Optional[Dict[str, Any]] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Load a tool definition, either from file or inline."""

    if isinstance(run_ref, dict):
        # Inline tool definition
        return run_ref
    elif isinstance(run_ref, str):
        # Reference to ID inside $graph
        if graph_objects is not None:
            key = run_ref.lstrip("#")
            if key in graph_objects:
                return graph_objects[key]

        # External file reference
        if run_ref.startswith("http://") or run_ref.startswith("https://"):
            raise NotImplementedError("HTTP tool references not yet supported")

        # Relative path from workflow file
        tool_path = cwl_path.parent / run_ref
        if not tool_path.exists():
            # Try absolute path
            tool_path = Path(run_ref)
            if not tool_path.exists():
                raise FileNotFoundError(f"Tool definition not found: {run_ref}")

        if verbose:
            print(f"Loading tool definition: {tool_path}")

        return _load_cwl_document(tool_path)
    else:
        raise ValueError(f"Invalid run reference: {run_ref}")


def _extract_command_from_tool(tool_def: Dict[str, Any]) -> str:
    """Extract command string from CWL CommandLineTool."""

    base_command = tool_def.get("baseCommand", [])
    arguments = tool_def.get("arguments", [])

    # Convert baseCommand to list if it's a string
    if isinstance(base_command, str):
        base_command = [base_command]

    # Build command parts
    command_parts = list(base_command)

    # Add arguments
    for arg in arguments:
        if isinstance(arg, str):
            command_parts.append(arg)
        elif isinstance(arg, dict):
            # Handle complex argument objects
            value = arg.get("valueFrom", arg.get("value", ""))
            if value:
                command_parts.append(str(value))

    return " ".join(command_parts) if command_parts else "# CWL CommandLineTool"


def _extract_resource_requirements(tool_def: Dict[str, Any]) -> ResourceSpec:
    """Extract resource requirements from CWL tool definition."""

    resources = ResourceSpec()

    # Check requirements section
    requirements = tool_def.get("requirements", [])
    hints = tool_def.get("hints", [])

    # Combine requirements and hints
    all_reqs = requirements + hints

    for req in all_reqs:
        if isinstance(req, dict):
            req_class = req.get("class")

            if req_class == "ResourceRequirement":
                # Extract resource specifications
                if "coresMin" in req:
                    resources.cpu = req["coresMin"]
                elif "coresMax" in req:
                    resources.cpu = req["coresMax"]

                if "ramMin" in req:
                    resources.mem_mb = req["ramMin"]  # CWL uses MB
                elif "ramMax" in req:
                    resources.mem_mb = req["ramMax"]

                if "tmpdirMin" in req:
                    resources.disk_mb = req["tmpdirMin"]
                elif "tmpdirMax" in req:
                    resources.disk_mb = req["tmpdirMax"]

                if "outdirMin" in req:
                    # Add output directory space to disk requirement
                    if resources.disk_mb:
                        resources.disk_mb += req["outdirMin"]
                    else:
                        resources.disk_mb = req["outdirMin"]

    return resources


def _extract_environment_spec(tool_def: Dict[str, Any]) -> Optional[EnvironmentSpec]:
    """Extract environment specification from CWL tool definition."""

    requirements = tool_def.get("requirements", [])
    hints = tool_def.get("hints", [])

    # Combine requirements and hints
    all_reqs = requirements + hints

    for req in all_reqs:
        if isinstance(req, dict):
            req_class = req.get("class")

            if req_class == "DockerRequirement":
                docker_pull = req.get("dockerPull")
                if docker_pull:
                    return EnvironmentSpec(container=f"docker://{docker_pull}")

            elif req_class == "SoftwareRequirement":
                # Handle software requirements (could map to conda)
                packages = req.get("packages", [])
                if packages:
                    # Create a simple conda-like environment spec
                    package_list = []
                    for pkg in packages:
                        if isinstance(pkg, dict):
                            name = pkg.get("package")
                            version = pkg.get("version", [""])
                            if name:
                                if version and version[0]:
                                    package_list.append(f"{name}={version[0]}")
                                else:
                                    package_list.append(name)

                    if package_list:
                        # Store as conda environment metadata
                        return EnvironmentSpec(conda={"dependencies": package_list})

    return None


def _parse_step_dependencies(step_name: str, step_def: Dict[str, Any]) -> List[Edge]:
    """Parse step dependencies from input references."""

    edges = []
    step_inputs = step_def.get("in", {})

    for input_name, input_def in step_inputs.items():
        if isinstance(input_def, dict):
            source = input_def.get("source")
        elif isinstance(input_def, str):
            source = input_def
        else:
            continue

        if source and "/" in source:
            # Reference to another step's output: "step_name/output_name"
            parent_step = source.split("/")[0]
            edges.append(Edge(parent=parent_step, child=step_name))

    return edges


def _convert_tool_to_workflow(
    tool_def: Dict[str, Any],
    cwl_path: Path,
    preserve_metadata: bool = True,
    verbose: bool = False,
) -> Workflow:
    """Convert a single CommandLineTool to a single-step workflow with enhanced features."""

    workflow_name = tool_def.get("label", cwl_path.stem)
    workflow = Workflow(
        name=workflow_name,
        version="1.0",
        label=tool_def.get("label"),
        doc=tool_def.get("doc"),
        cwl_version=tool_def.get("cwlVersion", "v1.2"),
    )

    # Extract enhanced metadata if requested
    if preserve_metadata:
        workflow.provenance = _extract_provenance_spec(tool_def)
        workflow.documentation = _extract_documentation_spec(tool_def)

    # Parse requirements and hints
    workflow.requirements = _parse_requirements(tool_def.get("requirements", []))
    workflow.hints = _parse_requirements(tool_def.get("hints", []))

    # Parse inputs and outputs with enhanced parameter specifications
    workflow.inputs = _parse_parameter_specs(tool_def.get("inputs", {}), "input")
    workflow.outputs = _parse_parameter_specs(tool_def.get("outputs", {}), "output")

    # Create enhanced single task from tool
    task = Task(id="main_tool", label=tool_def.get("label"), doc=tool_def.get("doc"))

    task.command = _extract_command_from_tool(tool_def)
    task.resources = _extract_resource_requirements_enhanced(tool_def, {})
    task.environment = _extract_environment_spec_enhanced(tool_def, {})

    # Parse enhanced I/O parameters
    if preserve_metadata:
        task.inputs = _parse_parameter_specs(tool_def.get("inputs", {}), "input")
        task.outputs = _parse_parameter_specs(tool_def.get("outputs", {}), "output")

    # Parse requirements and hints for the task
    task.requirements = _parse_requirements(tool_def.get("requirements", []))
    task.hints = _parse_requirements(tool_def.get("hints", []))

    # Extract provenance and documentation for the task
    if preserve_metadata:
        task.provenance = _extract_provenance_spec(tool_def)
        task.documentation = _extract_documentation_spec(tool_def)

    # Store enhanced metadata
    task.meta = {
        "cwl_tool_class": tool_def.get("class"),
        "cwl_tool_def": tool_def if preserve_metadata else {},
        "single_tool_conversion": True,
        "legacy_inputs": _extract_inputs_legacy({}, tool_def),
        "legacy_outputs": _extract_outputs_legacy({}, tool_def),
    }

    workflow.add_task(task)

    # Store enhanced workflow metadata
    workflow.meta = {
        "source_format": "cwl",
        "cwl_version": tool_def.get("cwlVersion", "v1.2"),
        "cwl_class": tool_def.get("class"),
        "single_tool_conversion": True,
        "original_cwl_doc": tool_def if preserve_metadata else {},
    }

    if verbose:
        print(f"Converted single CWL tool to enhanced workflow: {workflow_name}")

    return workflow


def _parse_with_cwltool(
    cwl_path: Path, fallback_workflow: Workflow, verbose: bool = False
) -> Workflow:
    """Use cwltool to parse complex CWL workflows (if available)."""

    if not shutil.which("cwltool"):
        if verbose:
            print("cwltool not found, using direct parsing")
        return fallback_workflow

    try:
        # Use cwltool to get workflow graph
        cmd = ["cwltool", "--print-pre", str(cwl_path)]
        subprocess.run(cmd, capture_output=True, text=True, check=True)

        # Parse cwltool output (this would need more sophisticated parsing)
        # For now, return the fallback workflow
        if verbose:
            print("cwltool parsing completed, using enhanced metadata")

        # Could enhance the workflow with cwltool insights here
        return fallback_workflow

    except subprocess.CalledProcessError as e:
        if verbose:
            print(f"cwltool failed: {e}, using direct parsing")
        return fallback_workflow
    except Exception as e:
        if verbose:
            print(f"cwltool error: {e}, using direct parsing")
        return fallback_workflow


def _extract_provenance_spec(cwl_doc: Dict[str, Any]) -> Optional[ProvenanceSpec]:
    """Extract provenance information from CWL document."""
    provenance = ProvenanceSpec()

    # Extract authors from various CWL fields
    if "author" in cwl_doc:
        authors = cwl_doc["author"]
        if isinstance(authors, list):
            provenance.authors = authors
        elif isinstance(authors, dict):
            provenance.authors = [authors]
        elif isinstance(authors, str):
            provenance.authors = [{"name": authors}]

    # Extract other provenance fields
    if "version" in cwl_doc:
        provenance.version = str(cwl_doc["version"])

    if "license" in cwl_doc:
        provenance.license = cwl_doc["license"]

    if "doi" in cwl_doc:
        provenance.doi = cwl_doc["doi"]

    if "keywords" in cwl_doc:
        keywords = cwl_doc["keywords"]
        if isinstance(keywords, list):
            provenance.keywords = keywords
        elif isinstance(keywords, str):
            provenance.keywords = [keywords]

    # Set creation timestamp
    from datetime import datetime

    provenance.created = datetime.now().isoformat()

    # Capture any namespaced provenance annotations (keys with ':')
    for k, v in cwl_doc.items():
        if ":" in k and k.split(":", 1)[0] not in {"input", "output", "steps"}:
            # Avoid doubling known fields
            provenance.extras[k] = v

    # Capture nested namespace dictionaries, e.g. prov: {wasGeneratedBy: X}
    for ns_key, ns_val in cwl_doc.items():
        if isinstance(ns_val, dict):
            # Skip known structural sections
            if ns_key in {"requirements", "hints", "inputs", "outputs", "steps"}:
                continue
            # Treat each entry as ns:key
            for inner_k, inner_v in ns_val.items():
                flat_key = f"{ns_key}:{inner_k}"
                if flat_key not in provenance.extras:
                    provenance.extras[flat_key] = inner_v

    return (
        provenance
        if any(
            [
                provenance.authors,
                provenance.version,
                provenance.license,
                provenance.doi,
                provenance.keywords,
                provenance.extras,
            ]
        )
        else None
    )


def _extract_documentation_spec(cwl_doc: Dict[str, Any]) -> Optional[DocumentationSpec]:
    """Extract documentation from CWL document."""
    doc_spec = DocumentationSpec()

    doc_spec.description = cwl_doc.get("doc")
    doc_spec.label = cwl_doc.get("label")
    doc_spec.doc = cwl_doc.get("doc")  # CWL-style documentation

    # Extract intent (ontology IRIs)
    if "intent" in cwl_doc:
        intent = cwl_doc["intent"]
        if isinstance(intent, list):
            doc_spec.intent = intent
        elif isinstance(intent, str):
            doc_spec.intent = [intent]

    return (
        doc_spec
        if any([doc_spec.description, doc_spec.label, doc_spec.doc, doc_spec.intent])
        else None
    )


def _parse_parameter_specs(
    params: Union[Dict, List], param_type: str
) -> List[ParameterSpec]:
    """Parse CWL parameters into enhanced ParameterSpec objects."""
    param_specs = []

    if isinstance(params, dict):
        for param_id, param_def in params.items():
            param_spec = _parse_single_parameter_spec(param_id, param_def, param_type)
            if param_spec:
                param_specs.append(param_spec)
    elif isinstance(params, list):
        for param_def in params:
            if isinstance(param_def, dict) and "id" in param_def:
                param_spec = _parse_single_parameter_spec(
                    param_def["id"], param_def, param_type
                )
                if param_spec:
                    param_specs.append(param_spec)

    return param_specs


def _parse_single_parameter_spec(
    param_id: str, param_def: Any, param_type: str
) -> Optional[ParameterSpec]:
    """Parse a single CWL parameter into ParameterSpec."""
    if isinstance(param_def, str):
        # Simple type definition
        return ParameterSpec(id=param_id, type=param_def)
    elif isinstance(param_def, dict):
        # Complex parameter definition
        param_spec = ParameterSpec(
            id=param_id,
            type=param_def.get("type", "string"),
            label=param_def.get("label"),
            doc=param_def.get("doc"),
            default=param_def.get("default"),
            value_from=param_def.get("valueFrom"),
        )

        # File-specific attributes
        param_spec.format = param_def.get("format")
        param_spec.secondary_files = param_def.get("secondaryFiles", [])
        param_spec.streamable = param_def.get("streamable", False)
        param_spec.load_contents = param_def.get("loadContents", False)
        param_spec.load_listing = param_def.get("loadListing")

        # Binding information
        if param_type == "input":
            param_spec.input_binding = param_def.get("inputBinding")
        elif param_type == "output":
            param_spec.output_binding = param_def.get("outputBinding")

        return param_spec

    return None


def _parse_requirements(requirements: List[Dict[str, Any]]) -> List[RequirementSpec]:
    """Parse CWL requirements/hints into RequirementSpec objects."""
    req_specs = []

    for req in requirements:
        if isinstance(req, dict) and "class" in req:
            req_spec = RequirementSpec(
                class_name=req["class"],
                data={k: v for k, v in req.items() if k != "class"},
            )
            req_specs.append(req_spec)

    return req_specs


def _parse_scatter_spec(step_def: Dict[str, Any]) -> Optional[ScatterSpec]:
    """Parse CWL scatter specification."""
    if "scatter" not in step_def:
        return None

    scatter = step_def["scatter"]
    scatter_list = scatter if isinstance(scatter, list) else [scatter]
    scatter_method = step_def.get("scatterMethod", "dotproduct")

    return ScatterSpec(scatter=scatter_list, scatter_method=scatter_method)


def _parse_cwl_step_enhanced(
    step_name: str,
    step_def: Dict[str, Any],
    cwl_path: Path,
    preserve_metadata: bool = True,
    verbose: bool = False,
    debug: bool = False,
    graph_objects: Optional[Dict[str, Any]] = None,
) -> tuple[Task, List[Edge]]:
    """Parse a single CWL workflow step into enhanced Task and edges."""

    # Get the tool reference
    run_ref = step_def.get("run")
    if not run_ref:
        raise ValueError(f"Step {step_name} has no 'run' reference")

    # Load the tool definition
    tool_def = _load_tool_definition(
        run_ref, cwl_path, graph_objects=graph_objects, verbose=verbose
    )

    # Create enhanced task
    task = Task(
        id=step_name,
        label=step_def.get("label") or tool_def.get("label"),
        doc=step_def.get("doc") or tool_def.get("doc"),
    )

    # Extract command from tool
    if tool_def.get("class") == "CommandLineTool":
        task.command = _extract_command_from_tool(tool_def)
    else:
        task.command = f"# CWL step: {step_name}"

    # Parse conditional execution
    if "when" in step_def:
        task.when = step_def["when"]

    # Parse scatter operations
    task.scatter = _parse_scatter_spec(step_def)

    # Parse enhanced I/O parameters
    if preserve_metadata:
        # Parse tool inputs and outputs as ParameterSpec
        tool_inputs = tool_def.get("inputs", {})
        tool_outputs = tool_def.get("outputs", {})

        task.inputs = _parse_parameter_specs(tool_inputs, "input")
        task.outputs = _parse_parameter_specs(tool_outputs, "output")

    # ------------------------------------------------------------------
    # Merge step-level input customisations such as valueFrom (step 'in')
    # ------------------------------------------------------------------
    step_inputs = step_def.get("in", {})
    if isinstance(step_inputs, dict):
        for inp_name, inp_def in step_inputs.items():
            # Locate ParameterSpec by matching id with tool input name
            pspec = next((p for p in task.inputs if p.id == inp_name), None)
            if pspec is None:
                continue

            if isinstance(inp_def, dict) and "valueFrom" in inp_def:
                pspec.value_from = inp_def["valueFrom"]

    # Extract resource requirements with enhanced parsing
    task.resources = _extract_resource_requirements_enhanced(tool_def, step_def)

    # Extract environment spec with enhanced parsing
    task.environment = _extract_environment_spec_enhanced(tool_def, step_def)

    # Parse requirements and hints
    step_requirements = step_def.get("requirements", [])
    tool_requirements = tool_def.get("requirements", [])
    task.requirements = _parse_requirements(step_requirements + tool_requirements)

    step_hints = step_def.get("hints", [])
    tool_hints = tool_def.get("hints", [])
    task.hints = _parse_requirements(step_hints + tool_hints)

    # Extract provenance and documentation if available
    if preserve_metadata:
        task.provenance = _extract_provenance_spec(tool_def)
        task.documentation = _extract_documentation_spec(tool_def)

    # Extract intent
    if "intent" in tool_def:
        intent = tool_def["intent"]
        task.intent = intent if isinstance(intent, list) else [intent]

    # Legacy compatibility - populate old fields for backward compatibility
    legacy_inputs = _extract_inputs_legacy(step_def, tool_def)
    legacy_outputs = _extract_outputs_legacy(step_def, tool_def)
    task.params = _extract_params_legacy(step_def)

    # Store legacy inputs/outputs in meta for backward compatibility
    task.meta["legacy_inputs"] = legacy_inputs
    task.meta["legacy_outputs"] = legacy_outputs

    # Store enhanced metadata
    task.meta = {
        "cwl_step_def": step_def if preserve_metadata else {},
        "cwl_tool_def": tool_def if preserve_metadata else {},
        "step_requirements": step_requirements,
        "tool_requirements": tool_requirements,
        "step_hints": step_hints,
        "tool_hints": tool_hints,
    }

    # Parse step dependencies with enhanced edge detection
    edges = _parse_step_dependencies_enhanced(step_name, step_def, verbose=verbose)

    return task, edges


def _extract_resource_requirements_enhanced(
    tool_def: Dict[str, Any], step_def: Dict[str, Any]
) -> ResourceSpec:
    """Extract resource requirements with enhanced CWL feature support."""
    resources = ResourceSpec()

    # Check both tool and step requirements
    all_requirements = []
    all_requirements.extend(tool_def.get("requirements", []))
    all_requirements.extend(step_def.get("requirements", []))
    all_requirements.extend(tool_def.get("hints", []))
    all_requirements.extend(step_def.get("hints", []))

    for req in all_requirements:
        if not isinstance(req, dict):
            continue

        req_class = req.get("class")

        if req_class == "ResourceRequirement":
            # Parse CPU requirements
            if "coresMin" in req:
                cpu_min = int(req["coresMin"])
                if resources.cpu is None:
                    resources.cpu = cpu_min
                else:
                    resources.cpu = max(resources.cpu, cpu_min)
            if "coresMax" in req:
                cpu_max = int(req["coresMax"])
                if resources.cpu is None:
                    resources.cpu = cpu_max
                else:
                    resources.cpu = max(resources.cpu, cpu_max)  # Use coresMax for CPU
                resources.threads = cpu_max

            # Parse memory requirements (convert to MB)
            if "ramMin" in req:
                ram_min = req["ramMin"]
                if isinstance(ram_min, str) and ram_min.endswith("G"):
                    mem_min = int(float(ram_min[:-1]) * 1024)
                elif isinstance(ram_min, (int, float)):
                    mem_min = int(ram_min)
                else:
                    continue
                
                if resources.mem_mb is None:
                    resources.mem_mb = mem_min
                else:
                    resources.mem_mb = max(resources.mem_mb, mem_min)

            if "ramMax" in req:
                ram_max = req["ramMax"]
                if isinstance(ram_max, str) and ram_max.endswith("G"):
                    mem_max = int(float(ram_max[:-1]) * 1024)
                elif isinstance(ram_max, (int, float)):
                    mem_max = int(ram_max)
                else:
                    continue
                
                if resources.mem_mb is None:
                    resources.mem_mb = mem_max
                else:
                    resources.mem_mb = max(resources.mem_mb, mem_max)

            # Parse disk requirements (convert to MB and add them together)
            total_disk_mb = 0

            if "outdirMin" in req:
                outdir_min = req["outdirMin"]
                if isinstance(outdir_min, str) and outdir_min.endswith("G"):
                    total_disk_mb += int(float(outdir_min[:-1]) * 1024)
                elif isinstance(outdir_min, (int, float)):
                    total_disk_mb += int(outdir_min)

            # Parse temporary disk requirements
            if "tmpdirMin" in req:
                tmpdir_min = req["tmpdirMin"]
                if isinstance(tmpdir_min, str) and tmpdir_min.endswith("G"):
                    total_disk_mb += int(float(tmpdir_min[:-1]) * 1024)
                elif isinstance(tmpdir_min, (int, float)):
                    total_disk_mb += int(tmpdir_min)

            if "tmpdirMax" in req:
                tmpdir_max = req["tmpdirMax"]
                if isinstance(tmpdir_max, str) and tmpdir_max.endswith("G"):
                    total_disk_mb += int(float(tmpdir_max[:-1]) * 1024)
                elif isinstance(tmpdir_max, (int, float)):
                    total_disk_mb += int(tmpdir_max)

            # Use the maximum of current disk_mb and total calculated disk
            if total_disk_mb > 0:
                if resources.disk_mb is None:
                    resources.disk_mb = total_disk_mb
                else:
                    resources.disk_mb = max(resources.disk_mb, total_disk_mb)

        elif req_class == "ToolTimeLimit":
            # Parse time limits
            if "timelimit" in req:
                resources.time_s = int(req["timelimit"])

        elif req_class == "NetworkAccess":
            # Store network access requirement in extra
            resources.extra["network_access"] = req.get("networkAccess", True)

        elif req_class == "WorkReuse":
            # Store work reuse setting in extra
            resources.extra["work_reuse"] = req.get("enableReuse", True)

    return resources


def _extract_environment_spec_enhanced(
    tool_def: Dict[str, Any], step_def: Dict[str, Any]
) -> EnvironmentSpec:
    """Extract environment spec with enhanced CWL feature support."""
    env_spec = EnvironmentSpec()

    # Check both tool and step requirements
    all_requirements = []
    all_requirements.extend(tool_def.get("requirements", []))
    all_requirements.extend(step_def.get("requirements", []))
    all_requirements.extend(tool_def.get("hints", []))
    all_requirements.extend(step_def.get("hints", []))

    for req in all_requirements:
        if not isinstance(req, dict):
            continue

        req_class = req.get("class")

        if req_class == "DockerRequirement":
            # Docker container specification
            if "dockerPull" in req:
                env_spec.container = f"docker://{req['dockerPull']}"
            elif "dockerImageId" in req:
                env_spec.container = f"docker://{req['dockerImageId']}"

        elif req_class == "SoftwareRequirement":
            # Software packages (convert to conda environment)
            packages = req.get("packages", [])
            if packages:
                # Create a minimal conda environment specification
                conda_spec = {"name": "cwl_env", "dependencies": []}

                for pkg in packages:
                    if isinstance(pkg, dict):
                        pkg_name = pkg.get("package")
                        pkg_version = (
                            pkg.get("version", [""])[0] if pkg.get("version") else ""
                        )
                        if pkg_name:
                            if pkg_version:
                                conda_spec["dependencies"].append(
                                    f"{pkg_name}={pkg_version}"
                                )
                            else:
                                conda_spec["dependencies"].append(pkg_name)

                # Store as dictionary for backward compatibility with tests
                # Tests expect conda to be a dict, not a YAML string
                env_spec.conda = conda_spec

        elif req_class == "EnvVarRequirement":
            # Environment variables
            env_vars = req.get("envDef", {})
            env_spec.env_vars.update(env_vars)

        elif req_class == "InitialWorkDirRequirement":
            # Working directory setup
            if "listing" in req:
                # For now, just note that initial work dir is required
                env_spec.workdir = "."  # Current directory

    return env_spec


def _parse_step_dependencies_enhanced(
    step_name: str, step_def: Dict[str, Any], verbose: bool = False
) -> List[Edge]:
    """Parse step dependencies with enhanced edge detection."""
    edges = []

    # Parse step inputs to find dependencies
    step_inputs = step_def.get("in", {})

    for input_name, input_def in step_inputs.items():
        if isinstance(input_def, dict):
            source = input_def.get("source")
        elif isinstance(input_def, str):
            source = input_def
        else:
            continue

        if source:
            # Handle multiple sources
            sources = source if isinstance(source, list) else [source]

            for src in sources:
                if isinstance(src, str) and "/" in src:
                    # Source is from another step: step_name/output_name
                    parent_step = src.split("/")[0]
                    if parent_step != step_name:  # Avoid self-dependencies
                        edges.append(Edge(parent=parent_step, child=step_name))
                        if verbose:
                            print(
                                f"  Found enhanced dependency: {parent_step} -> {step_name}"
                            )

    return edges


def _parse_workflow_inputs_legacy(inputs: Union[Dict, List]) -> Dict[str, Any]:
    """Parse CWL workflow inputs into config dictionary for backward compatibility."""
    config = {}

    if isinstance(inputs, dict):
        for input_name, input_def in inputs.items():
            if isinstance(input_def, dict):
                default_value = input_def.get("default")
                if default_value is not None:
                    config[input_name] = default_value
            else:
                # Simple type definition
                config[input_name] = None
    elif isinstance(inputs, list):
        for input_def in inputs:
            if isinstance(input_def, dict) and "id" in input_def:
                input_name = input_def["id"]
                default_value = input_def.get("default")
                if default_value is not None:
                    config[input_name] = default_value

    return config


def _extract_inputs_legacy(
    step_def: Dict[str, Any], tool_def: Dict[str, Any]
) -> List[str]:
    """Extract inputs in legacy format for backward compatibility."""
    inputs = []

    # Extract from tool inputs
    tool_inputs = tool_def.get("inputs", {})
    if isinstance(tool_inputs, dict):
        inputs.extend(tool_inputs.keys())
    elif isinstance(tool_inputs, list):
        for inp in tool_inputs:
            if isinstance(inp, dict) and "id" in inp:
                inputs.append(inp["id"])

    return inputs


def _extract_outputs_legacy(
    step_def: Dict[str, Any], tool_def: Dict[str, Any]
) -> List[str]:
    """Extract outputs in legacy format for backward compatibility."""
    outputs = []

    # Extract from tool outputs
    tool_outputs = tool_def.get("outputs", {})
    if isinstance(tool_outputs, dict):
        outputs.extend(tool_outputs.keys())
    elif isinstance(tool_outputs, list):
        for out in tool_outputs:
            if isinstance(out, dict) and "id" in out:
                outputs.append(out["id"])

    return outputs


def _extract_params_legacy(step_def: Dict[str, Any]) -> Dict[str, Any]:
    """Extract parameters in legacy format for backward compatibility."""
    params = {}

    # Extract step inputs as parameters
    step_inputs = step_def.get("in", {})
    for input_name, input_def in step_inputs.items():
        if isinstance(input_def, dict):
            # Store input configuration
            params[input_name] = input_def
        else:
            # Simple input reference
            params[input_name] = input_def

    return params
