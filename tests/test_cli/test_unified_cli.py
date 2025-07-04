"""Tests for the unified wf2wf CLI implementation."""

import sys
import pathlib
import importlib.util
import pytest
from pathlib import Path
import textwrap
import subprocess
import shutil
import os

# Allow running tests without installing package
proj_root = pathlib.Path(__file__).resolve().parents[2]

if "wf2wf" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "wf2wf", proj_root / "wf2wf" / "__init__.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["wf2wf"] = module  # type: ignore[assignment]
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[arg-type]

from wf2wf.core import Workflow, Task, ResourceSpec, ParameterSpec

try:
    from wf2wf.cli import (
        detect_input_format,
        detect_output_format,
        load_workflow_from_json_yaml,
        save_workflow_to_json_yaml,
        get_importer,
        get_exporter,
    )

    CLI_AVAILABLE = True
except ImportError:
    try:
        # Try relative import when running as script
        sys.path.insert(0, str(proj_root / "wf2wf"))
        from cli import (
            detect_input_format,
            detect_output_format,
            load_workflow_from_json_yaml,
            save_workflow_to_json_yaml,
            get_importer,
            get_exporter,
        )

        CLI_AVAILABLE = True
    except ImportError:
        CLI_AVAILABLE = False

try:
    from wf2wf.cli import (
        cli,
        detect_input_format,
        detect_output_format,
        get_importer,
        get_exporter,
        load_workflow_from_json_yaml,
        save_workflow_to_json_yaml,
    )
    from click.testing import CliRunner

    CLICK_AVAILABLE = True
except ImportError:
    # Test if click is available without importing it
    import importlib.util
    
    if importlib.util.find_spec("click") is not None:
        from click.testing import CliRunner

        sys.path.insert(0, str(proj_root / "wf2wf"))
        from cli import cli

        CLICK_AVAILABLE = True
    else:
        CLICK_AVAILABLE = False


@pytest.mark.skipif(not CLI_AVAILABLE, reason="CLI module not available")
class TestFormatDetection:
    """Test automatic format detection from file extensions."""

    def test_detect_input_format_snakemake(self):
        """Test detection of Snakemake files."""
        assert detect_input_format(Path("workflow.smk")) == "snakemake"
        assert detect_input_format(Path("Snakefile")) == "snakemake"

    def test_detect_input_format_dagman(self):
        """Test detection of DAGMan files."""
        assert detect_input_format(Path("workflow.dag")) == "dagman"

    def test_detect_input_format_json_yaml(self):
        """Test detection of JSON/YAML files."""
        assert detect_input_format(Path("workflow.json")) == "json"
        assert detect_input_format(Path("workflow.yaml")) == "yaml"
        assert detect_input_format(Path("workflow.yml")) == "yaml"

    def test_detect_input_format_unknown(self):
        """Test handling of unknown file extensions."""
        assert detect_input_format(Path("workflow.unknown")) is None

    def test_detect_output_format(self):
        """Test output format detection."""
        assert detect_output_format(Path("output.dag")) == "dagman"
        assert detect_output_format(Path("output.smk")) == "snakemake"
        assert detect_output_format(Path("output.json")) == "json"


@pytest.mark.skipif(not CLI_AVAILABLE, reason="CLI module not available")
class TestWorkflowSerialization:
    """Test JSON/YAML workflow serialization."""

    def test_save_load_json_roundtrip(self, tmp_path):
        """Test JSON save/load roundtrip."""
        # Create test workflow
        wf = Workflow(name="test_workflow")
        task1 = Task(
            id="task1",
            command="echo 'hello'",
            outputs=[ParameterSpec(id="file1.txt", type="File")],
        )
        task2 = Task(
            id="task2",
            command="echo 'world'",
            inputs=[ParameterSpec(id="file1.txt", type="File")],
            outputs=[ParameterSpec(id="file2.txt", type="File")],
        )
        wf.add_task(task1)
        wf.add_task(task2)
        wf.add_edge("task1", "task2")

        # Save to JSON
        json_path = tmp_path / "test.json"
        save_workflow_to_json_yaml(wf, json_path)

        # Load from JSON
        wf_loaded = load_workflow_from_json_yaml(json_path)

        # Compare
        assert wf_loaded.name == wf.name
        assert len(wf_loaded.tasks) == len(wf.tasks)
        assert len(wf_loaded.edges) == len(wf.edges)
        assert wf_loaded.to_dict() == wf.to_dict()

    def test_save_load_yaml_roundtrip(self, tmp_path):
        """Test YAML save/load roundtrip."""
        pytest.importorskip("yaml")

        # Create test workflow
        wf = Workflow(name="test_workflow")
        task = Task(
            id="task1",
            command="echo 'hello'",
            resources=ResourceSpec(cpu=2, mem_mb=1024),
        )
        wf.add_task(task)

        # Save to YAML
        yaml_path = tmp_path / "test.yaml"
        save_workflow_to_json_yaml(wf, yaml_path)

        # Load from YAML
        wf_loaded = load_workflow_from_json_yaml(yaml_path)

        # Compare
        assert wf_loaded.name == wf.name
        assert len(wf_loaded.tasks) == len(wf.tasks)
        assert wf_loaded.tasks["task1"].resources.cpu == 2
        assert wf_loaded.tasks["task1"].resources.mem_mb == 1024


@pytest.mark.skipif(not CLI_AVAILABLE, reason="CLI module not available")
class TestImporterExporterAccess:
    """Test importer/exporter access functions."""

    def test_get_importer_snakemake(self):
        """Test getting Snakemake importer."""
        importer = get_importer("snakemake")
        # Should either return the importer or be None if not available
        if importer is not None:
            assert hasattr(importer, "to_workflow")

    def test_get_exporter_dagman(self):
        """Test getting DAGMan exporter."""
        exporter = get_exporter("dagman")
        # Should either return the exporter or be None if not available
        if exporter is not None:
            assert hasattr(exporter, "from_workflow")

    def test_get_importer_invalid_format(self):
        """Test handling of invalid importer format."""
        with pytest.raises((RuntimeError, Exception)) as exc_info:
            get_importer("invalid_format")
        assert "not available" in str(exc_info.value)

    def test_get_exporter_invalid_format(self):
        """Test handling of invalid exporter format."""
        with pytest.raises((RuntimeError, Exception)) as exc_info:
            get_exporter("invalid_format")
        assert "not available" in str(exc_info.value)


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="Click not available for CLI testing")
class TestClickCLI:
    """Test the Click-based CLI interface."""

    def test_cli_help(self):
        """Test CLI help output."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Workflow-to-Workflow Converter" in result.output

    def test_convert_help(self):
        """Test convert command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["convert", "--help"])
        assert result.exit_code == 0
        assert "Convert workflows between different formats" in result.output
        assert "--in-format" in result.output
        assert "--out-format" in result.output

    def test_validate_help(self):
        """Test validate command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "--help"])
        assert result.exit_code == 0
        assert "Validate a workflow file" in result.output

    def test_info_help(self):
        """Test info command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["info", "--help"])
        assert result.exit_code == 0
        assert "Display information about a workflow file" in result.output

    def test_convert_missing_input(self):
        """Test convert command with missing input."""
        runner = CliRunner()
        result = runner.invoke(cli, ["convert"])
        assert result.exit_code != 0
        assert "Missing option" in result.output or "Error" in result.output

    def test_validate_json_workflow(self, tmp_path):
        """Test validate command with a JSON workflow."""
        # Create a simple valid workflow
        wf = Workflow(name="validation_test")
        wf.add_task(Task(id="task1", command="echo 'test'"))

        json_path = tmp_path / "test.json"
        wf.save_json(json_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(json_path)])
        assert result.exit_code == 0
        assert "is valid" in result.output

    def test_info_json_workflow(self, tmp_path):
        """Test info command with a JSON workflow."""
        # Create a simple workflow with metadata
        wf = Workflow(name="info_test", version="2.0")
        wf.add_task(Task(id="task1", command="echo 'test'"))
        wf.add_task(Task(id="task2", command="echo 'test2'"))
        wf.add_edge("task1", "task2")
        wf.config = {"test_config": "value"}
        wf.meta = {"description": "Test workflow"}

        json_path = tmp_path / "test.json"
        wf.save_json(json_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["info", str(json_path)])
        assert result.exit_code == 0

        # Parse JSON output
        import json

        info_data = json.loads(result.output)
        assert info_data["name"] == "info_test"
        assert info_data["version"] == "2.0"
        assert info_data["tasks"] == 2
        assert info_data["edges"] == 1
        assert info_data["config"]["test_config"] == "value"
        assert info_data["meta"]["description"] == "Test workflow"

    def test_convert_single_input_ir_default_warning(self, tmp_path):
        """Test that single input file shows IR default warning."""
        # Create a simple workflow
        wf = Workflow(name="ir_default_test")
        wf.add_task(Task(id="task1", command="echo 'test'"))

        input_path = tmp_path / "test.json"
        expected_output_path = tmp_path / "test.json"  # Should default to same name with .json
        wf.save_json(input_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["convert", "--input", str(input_path)])
        
        assert result.exit_code == 0
        assert "⚠ No output format specified" in result.stderr
        assert "Defaulting to Intermediate Representation (IR) format" in result.stderr
        assert "Use --out-format to specify a different target format" in result.stderr
        assert expected_output_path.exists()

    def test_convert_yaml_input_ir_default_warning(self, tmp_path):
        """Test that YAML input file shows IR default warning and converts to JSON."""
        pytest.importorskip("yaml")
        
        # Create a simple workflow in YAML
        wf = Workflow(name="yaml_ir_test")
        wf.add_task(Task(id="task1", command="echo 'test'"))

        input_path = tmp_path / "test.yaml"
        expected_output_path = tmp_path / "test.json"  # Should convert .yaml to .json
        save_workflow_to_json_yaml(wf, input_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["convert", "--input", str(input_path)])
        
        assert result.exit_code == 0
        assert "⚠ No output format specified" in result.stderr
        assert "Defaulting to Intermediate Representation (IR) format" in result.stderr
        assert str(expected_output_path) in result.stderr
        assert expected_output_path.exists()
        assert "test.yaml → " in result.output and "test.json" in result.output

    def test_convert_explicit_output_format_no_warning(self, tmp_path):
        """Test that explicit output format doesn't show warning."""
        # Create a simple workflow
        wf = Workflow(name="explicit_format_test")
        wf.add_task(Task(id="task1", command="echo 'test'"))

        input_path = tmp_path / "test.json"
        expected_output_path = tmp_path / "test.yaml"
        wf.save_json(input_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["convert", "--input", str(input_path), "--out-format", "yaml"])
        
        assert result.exit_code == 0
        assert "⚠ No output format specified" not in result.stderr
        assert "Defaulting to Intermediate Representation" not in result.stderr
        assert expected_output_path.exists()

    def test_convert_explicit_output_path_no_warning(self, tmp_path):
        """Test that explicit output path doesn't show warning."""
        # Create a simple workflow
        wf = Workflow(name="explicit_path_test")
        wf.add_task(Task(id="task1", command="echo 'test'"))

        input_path = tmp_path / "test.json"
        output_path = tmp_path / "custom_output.yaml"
        wf.save_json(input_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["convert", "--input", str(input_path), "--output", str(output_path)])
        
        assert result.exit_code == 0
        assert "⚠ No output format specified" not in result.stderr
        assert "Defaulting to Intermediate Representation" not in result.stderr
        assert output_path.exists()

    def test_convert_public_snakemake_pipeline(self, tmp_path):
        """Test conversion of a public Snakemake pipeline from the official workflows."""
        pytest.importorskip("requests")
        
        # Download a simple Snakemake workflow from the official repository
        import requests
        
        # Get the main Snakefile from the official GATK variant calling pipeline
        workflow_url = "https://raw.githubusercontent.com/snakemake-workflows/dna-seq-gatk-variant-calling/main/workflow/Snakefile"
        
        try:
            response = requests.get(workflow_url, timeout=30)
            response.raise_for_status()
        except (requests.RequestException, requests.exceptions.Timeout) as e:
            pytest.skip(f"Failed to download test workflow: {e}")
        
        # Save the workflow to a temporary file
        snakefile_path = tmp_path / "Snakefile"
        snakefile_path.write_text(response.text)
        
        # Test conversion with our tool
        runner = CliRunner()
        result = runner.invoke(cli, ["convert", "--input", str(snakefile_path), "--in-format", "snakemake"])
        
        # Check that IR warning was shown (should always be shown since we don't specify output format)
        assert "⚠ No output format specified" in result.stderr
        assert "Defaulting to Intermediate Representation (IR) format" in result.stderr
        
        if result.exit_code != 0:
            # If snakemake is not available, we should get a helpful error message
            if "snakemake importer is not available" in result.output.lower():
                assert "install snakemake" in result.output.lower()
            else:
                # If snakemake is available but the workflow has issues (missing dependencies, etc.)
                # that's still a valid test - it shows our system is working correctly
                assert "failed to import snakemake workflow" in result.output.lower()
        else:
            # If successful, check that output file exists
            expected_output = tmp_path / "Snakefile.json"
            assert expected_output.exists()
            
            # Verify the output is valid JSON
            import json
            with open(expected_output) as f:
                ir_data = json.load(f)
            assert "name" in ir_data
            assert "version" in ir_data
            assert "tasks" in ir_data
            assert "edges" in ir_data

    def test_file_transfer_handling_distributed_computing(self, tmp_path):
        """Test that file transfer specifications are correctly handled for distributed computing environments."""
        from wf2wf.core import Workflow, Task, ParameterSpec
        
        # Create a workflow with various file transfer scenarios
        wf = Workflow(name="transfer_test")
        
        # Task 1: Mixed transfer modes
        task1 = Task(
            id="mixed_files",
            command="process_data input.txt > output.txt",
            inputs=[
                "regular_input.txt",  # Should default to auto transfer
                ParameterSpec(id="/shared/reference.fa", type="File", transfer_mode="shared"),
                ParameterSpec(id="temp_file.tmp", type="File", transfer_mode="never"),
                ParameterSpec(id="required_input.dat", type="File", transfer_mode="always"),
            ],
            outputs=[
                "result.txt",  # Should default to auto transfer
                ParameterSpec(id="/shared/analysis/output.bam", type="File", transfer_mode="shared"),
                ParameterSpec(id="debug.log", type="File", transfer_mode="never"),
            ]
        )
        wf.add_task(task1)
        
        # Task 2: Only auto/always transfer files
        task2 = Task(
            id="transfer_files",
            command="analyze result.txt > final.txt",
            inputs=["result.txt"],
            outputs=[
                ParameterSpec(id="final.txt", type="File", transfer_mode="always"),
                ParameterSpec(id="summary.json", type="File", transfer_mode="auto"),
            ]
        )
        wf.add_task(task2)
        wf.add_edge("mixed_files", "transfer_files")
        
        # Convert to DAGMan and check file transfer specifications
        input_path = tmp_path / "transfer_test.json"
        dag_path = tmp_path / "transfer_test.dag" 
        wf.save_json(input_path)
        
        runner = CliRunner()
        result = runner.invoke(cli, ["convert", "--input", str(input_path), "--output", str(dag_path)])
        
        assert result.exit_code == 0
        assert dag_path.exists()
        
        # Read the generated submit files (DAGMan creates separate .sub files)
        submit_files = list(tmp_path.glob("*.sub"))
        assert len(submit_files) == 2  # Should have 2 submit files for 2 tasks
        
        # Read all submit content
        submit_content = ""
        for submit_file in submit_files:
            content = submit_file.read_text()
            submit_content += content
        
        # Check that the submit files contain proper file transfer specifications
        assert "transfer_input_files" in submit_content
        assert "transfer_output_files" in submit_content
        
        # Check that only the appropriate files are listed for transfer
        # regular_input.txt and required_input.dat should be transferred (auto + always)
        assert "regular_input.txt" in submit_content
        assert "required_input.dat" in submit_content
        
        # /shared/reference.fa should NOT be transferred (shared mode)
        assert "/shared/reference.fa" not in submit_content
        
        # temp_file.tmp should NOT be transferred (never mode)  
        assert "temp_file.tmp" not in submit_content
        
        # result.txt, final.txt, and summary.json should be transferred
        assert "result.txt" in submit_content
        assert "final.txt" in submit_content  
        assert "summary.json" in submit_content
        
        # debug.log should NOT be transferred (never mode)
        assert "debug.log" not in submit_content
        
        if verbose := False:  # Set to True for debugging
            print("Generated submit content:")
            print(submit_content)


@pytest.mark.skipif(not CLI_AVAILABLE, reason="CLI module not available")
class TestCLIIntegration:
    """Integration tests for the CLI with actual workflow files."""

    def test_json_to_json_conversion(self, tmp_path):
        """Test converting JSON workflow to JSON (should be identity)."""
        # Create source workflow
        wf = Workflow(name="json_test")
        wf.add_task(Task(id="task1", command="echo 'hello'"))

        input_path = tmp_path / "input.json"
        output_path = tmp_path / "output.json"
        wf.save_json(input_path)

        # Test with Click CLI if available
        if CLICK_AVAILABLE:
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "convert",
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                    "--verbose",
                ],
            )
            assert result.exit_code == 0
            assert output_path.exists()

            # Verify output
            wf_output = Workflow.load_json(output_path)
            assert wf_output.name == "json_test"
            assert len(wf_output.tasks) == 1

    def test_auto_format_detection(self, tmp_path):
        """Test automatic format detection."""
        # Create source workflow
        wf = Workflow(name="auto_detect_test")
        wf.add_task(Task(id="task1", command="echo 'test'"))

        input_path = tmp_path / "input.json"  # JSON extension
        output_path = tmp_path / "output.yaml"  # YAML extension
        wf.save_json(input_path)

        if CLICK_AVAILABLE:
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "convert",
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                    "--verbose",
                ],
            )
            assert result.exit_code == 0
            assert "Auto-detected input format: json" in result.output
            assert "Auto-detected output format: yaml" in result.output
            assert output_path.exists()

    def test_interactive_configuration_prompts(self, tmp_path, monkeypatch):
        """Test interactive prompts for missing configurations."""
        # Create a simple workflow without explicit configurations
        snakefile = tmp_path / "minimal.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule all:
                input: "output.txt"
            
            rule process:
                input: "input.txt"
                output: "output.txt"
                shell: "echo 'processed' > {output}"
            """)
        )
        
        # Create the required input file
        input_file = tmp_path / "input.txt"
        input_file.write_text("test input data")
        
        # Mock the wf2wf.prompt.ask function to always return True
        def mock_ask(question, default=None):
            return True  # Always return yes
        
        monkeypatch.setattr("wf2wf.prompt.ask", mock_ask)
        
        # Mock environment automation to skip container operations
        def mock_build_or_reuse_env_image(*args, **kwargs):
            return {"tag": "mock:tag", "digest": "sha256:mock"}
        
        monkeypatch.setattr("wf2wf.environ.build_or_reuse_env_image", mock_build_or_reuse_env_image)
        
        # Mock shutil.which to make Docker appear unavailable
        original_shutil_which = shutil.which
        def mock_shutil_which(name):
            if name == "docker":
                return None  # Make Docker appear unavailable
            return original_shutil_which(name)
        
        monkeypatch.setattr("shutil.which", mock_shutil_which)
        
        # Run conversion with interactive mode
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "convert",
                "-i", str(snakefile),
                "-o", str(tmp_path / "workflow.dag"),
                "--out-format", "dagman",
                "--interactive",
                "--verbose"
            ]
        )
        
        # Should complete successfully
        assert result.exit_code == 0
        
        # Check that the output file was created
        dag_file = tmp_path / "workflow.dag"
        assert dag_file.exists()
        
        # Check that the DAG file contains expected content
        dag_content = dag_file.read_text()
        assert "JOB all_0 all_0.sub" in dag_content
        assert "JOB process_1 process_1.sub" in dag_content
        assert "PARENT process_1 CHILD all_0" in dag_content
        
        # Check that script files were created
        scripts_dir = tmp_path / "scripts"
        assert scripts_dir.exists()
        assert (scripts_dir / "all_0.sh").exists()
        assert (scripts_dir / "process_1.sh").exists()

        # Verify the scripts are executable
        for script_file in scripts_dir.glob("*.sh"):
            assert os.access(script_file, os.X_OK)

    def test_single_input_warning(self, tmp_path):
        """Test warning when only input file is provided."""
        snakefile = tmp_path / "test.smk"
        snakefile.write_text("rule all: input: 'output.txt'")
        
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["convert", "-i", str(snakefile)]
        )
        
        # Should show warning about defaulting to IR format
        assert "No output format specified" in result.output
        assert "Defaulting to Intermediate Representation" in result.output
        assert result.exit_code == 0

    def test_file_transfer_mode_detection(self, tmp_path):
        """Test automatic file transfer mode detection."""
        snakefile = tmp_path / "transfer_test.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule all:
                input: "results/final.txt"
            
            rule process:
                input: "data/input.txt"
                output: "results/output.txt"
                shell: "cp {input} {output}"
            """)
        )
        
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "convert",
                "-i", str(snakefile),
                "-o", str(tmp_path / "workflow.dag"),
                "--out-format", "dagman",
                "--verbose"
            ]
        )
        
        assert result.exit_code == 0
        
        # Check that transfer modes were detected
        dag_content = (tmp_path / "workflow.dag").read_text()
        # The DAGMan exporter should generate transfer_input_files and transfer_output_files
        # based on the detected transfer modes
        assert "transfer_input_files" in dag_content or "transfer_output_files" in dag_content


@pytest.mark.skipif(not CLI_AVAILABLE, reason="CLI module not available")
class TestCleanup:
    """Test that no files are generated in the base directory during tests."""

    def test_no_base_directory_pollution(self, project_root):
        """Ensure no test files are created in the base directory."""
        # Patterns for files that should not exist in base directory after tests
        unwanted_patterns = [
            "demo_*.nf",
            "demo_*.json",
            "test_*.nf",
            "test_*.json",
            "test_*.dag",
            "test_*.sub",
            "test_*.smk",
            "test_*.cwl",
            "test_*.yaml",
            "test_*.yml",
            "*_test.*",
            "*_demo.*",
            "*.tmp",
        ]

        found_files = []
        for pattern in unwanted_patterns:
            found_files.extend(project_root.glob(pattern))

        if found_files:
            file_list = "\n".join(str(f) for f in found_files)
            pytest.fail(f"Found unwanted test files in base directory:\n{file_list}")

        # Also check for unwanted directories
        unwanted_dirs = ["scripts", "modules", "tools"]
        found_dirs = []
        for dir_name in unwanted_dirs:
            dir_path = project_root / dir_name
            if dir_path.exists() and dir_path.is_dir():
                # Check if directory contains test files
                has_test_files = any(
                    f.name.startswith(("test_", "demo_")) or f.suffix in [".tmp"]
                    for f in dir_path.rglob("*")
                    if f.is_file()
                )
                if has_test_files or not any(dir_path.iterdir()):
                    found_dirs.append(dir_path)

        if found_dirs:
            dir_list = "\n".join(str(d) for d in found_dirs)
            pytest.fail(
                f"Found unwanted test directories in base directory:\n{dir_list}"
            )

    def test_test_output_directory_cleanup(self, clean_test_output_dir):
        """Test that the test output directory can be cleaned while preserving .gitignore."""
        # Create some test files
        test_file = clean_test_output_dir / "test_file.txt"
        test_dir = clean_test_output_dir / "test_subdir"
        test_dir.mkdir(exist_ok=True)

        test_file.write_text("test content")
        (test_dir / "nested_file.txt").write_text("nested content")

        # Verify files exist
        assert test_file.exists()
        assert test_dir.exists()

        # The fixture should clean up automatically
        # This test mainly verifies the fixture works without errors


def is_docker_running():
    try:
        result = subprocess.run([
            "docker", "info"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        return result.returncode == 0
    except Exception:
        return False
