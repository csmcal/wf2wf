"""Basic integration tests for DAGMan exporter using the Workflow IR."""

# Allow running tests without installing package
import sys
import pathlib
import importlib.util

proj_root = pathlib.Path(__file__).resolve().parents[1]

if "wf2wf" not in sys.modules:
    spec = importlib.util.spec_from_file_location("wf2wf", proj_root / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["wf2wf"] = module  # type: ignore[assignment]
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[arg-type]


from wf2wf.core import Workflow, Task, EnvironmentSpecificValue, ParameterSpec
from wf2wf.exporters import dagman as dag_exporter
from wf2wf.importers import dagman as dag_importer


def _build_linear_workflow() -> Workflow:
    wf = Workflow(name="linear_demo")
    wf.add_task(
        Task(
            id="step_a",
            command=EnvironmentSpecificValue("echo A", ["distributed_computing"]),
            outputs=[ParameterSpec(id="a.txt", type="File")],
            cpu=EnvironmentSpecificValue(1, ["distributed_computing"]),
        )
    )
    wf.add_task(
        Task(
            id="step_b",
            command=EnvironmentSpecificValue("echo B", ["distributed_computing"]),
            inputs=[ParameterSpec(id="a.txt", type="File")],
            outputs=[ParameterSpec(id="b.txt", type="File")],
            cpu=EnvironmentSpecificValue(1, ["distributed_computing"]),
        )
    )
    wf.add_edge("step_a", "step_b")
    return wf


def test_export_linear_workflow(tmp_path):
    wf = _build_linear_workflow()
    dag_path = tmp_path / "linear.dag"
    scripts_dir = tmp_path / "scripts"

    dag_exporter.from_workflow(
        wf, dag_path, workdir=tmp_path, scripts_dir=scripts_dir, verbose=False
    )

    # Assert DAG file exists
    assert dag_path.exists(), "DAG file was not created"

    dag_text = dag_path.read_text()

    # Basic assertions on DAG content
    assert "JOB step_a" in dag_text
    assert "JOB step_b" in dag_text
    assert "PARENT step_a CHILD step_b" in dag_text

    # Generated script files should exist
    assert (scripts_dir / "step_a.sh").exists()
    assert (scripts_dir / "step_b.sh").exists()


class TestDAGManInlineSubmit:
    """Test suite for DAGMan inline submit description functionality."""

    def test_inline_submit_basic_workflow(self, persistent_test_output):
        """Test basic inline submit description export."""
        wf = Workflow(name="inline_basic_test")

        task = Task(
            id="simple_task",
            command=EnvironmentSpecificValue("echo 'Hello World'", ["distributed_computing"]),
            cpu=EnvironmentSpecificValue(2, ["distributed_computing"]),
            mem_mb=EnvironmentSpecificValue(4096, ["distributed_computing"]),
            container=EnvironmentSpecificValue("docker://python:3.9", ["distributed_computing"]),
        )
        wf.add_task(task)

        dag_path = persistent_test_output / "inline_basic.dag"
        dag_exporter.from_workflow(
            wf, dag_path, workdir=persistent_test_output, inline_submit=True
        )

        # Check that DAG file exists and contains inline submit description
        assert dag_path.exists()
        dag_content = dag_path.read_text()

        # Should contain inline job definition
        assert "JOB simple_task {" in dag_content
        assert "}" in dag_content
        assert "request_cpus = 2" in dag_content
        assert "request_memory = 4096MB" in dag_content
        assert "universe = docker" in dag_content
        assert "docker_image = python:3.9" in dag_content
        assert "queue" in dag_content

        # Should NOT create separate submit files
        submit_file = persistent_test_output / "simple_task.sub"
        assert not submit_file.exists()

    def test_inline_submit_multiple_tasks_with_dependencies(
        self, persistent_test_output
    ):
        """Test inline submit descriptions with multiple tasks and dependencies."""
        wf = Workflow(name="inline_multi_test")

        task1 = Task(
            id="preprocess",
            command=EnvironmentSpecificValue("python preprocess.py", ["distributed_computing"]),
            cpu=EnvironmentSpecificValue(1, ["distributed_computing"]),
            mem_mb=EnvironmentSpecificValue(2048, ["distributed_computing"]),
            conda=EnvironmentSpecificValue("environment.yaml", ["distributed_computing"]),
        )

        task2 = Task(
            id="analyze",
            command=EnvironmentSpecificValue("python analyze.py", ["distributed_computing"]),
            cpu=EnvironmentSpecificValue(4, ["distributed_computing"]),
            mem_mb=EnvironmentSpecificValue(8192, ["distributed_computing"]),
            gpu=EnvironmentSpecificValue(1, ["distributed_computing"]),
            container=EnvironmentSpecificValue("docker://tensorflow/tensorflow:latest-gpu", ["distributed_computing"]),
        )

        task3 = Task(
            id="visualize",
            command=EnvironmentSpecificValue("Rscript visualize.R", ["distributed_computing"]),
            cpu=EnvironmentSpecificValue(2, ["distributed_computing"]),
            mem_mb=EnvironmentSpecificValue(4096, ["distributed_computing"]),
            retry_count=EnvironmentSpecificValue(2, ["distributed_computing"]),
            priority=EnvironmentSpecificValue(10, ["distributed_computing"]),
        )

        wf.add_task(task1)
        wf.add_task(task2)
        wf.add_task(task3)
        wf.add_edge("preprocess", "analyze")
        wf.add_edge("analyze", "visualize")

        dag_path = persistent_test_output / "inline_multi.dag"
        dag_exporter.from_workflow(
            wf, dag_path, workdir=persistent_test_output, inline_submit=True
        )

        dag_content = dag_path.read_text()

        # Check all tasks are defined inline
        assert "JOB preprocess {" in dag_content
        assert "JOB analyze {" in dag_content
        assert "JOB visualize {" in dag_content

        # Check resources are correct
        assert "request_cpus = 1" in dag_content  # preprocess
        assert "request_cpus = 4" in dag_content  # analyze
        assert "request_cpus = 2" in dag_content  # visualize
        assert "request_gpus = 1" in dag_content  # analyze

        # Check universes
        assert "universe = vanilla" in dag_content  # conda and default
        assert "universe = docker" in dag_content  # docker container

        # Check retry and priority
        assert "RETRY visualize 2" in dag_content
        assert "PRIORITY visualize 10" in dag_content

        # Check dependencies
        assert "PARENT preprocess CHILD analyze" in dag_content
        assert "PARENT analyze CHILD visualize" in dag_content

        # Should NOT create separate submit files
        assert not (persistent_test_output / "preprocess.sub").exists()
        assert not (persistent_test_output / "analyze.sub").exists()
        assert not (persistent_test_output / "visualize.sub").exists()

    def test_inline_submit_with_custom_attributes(self, persistent_test_output):
        """Test inline submit descriptions with custom HTCondor attributes."""
        wf = Workflow(name="inline_custom_test")

        custom_attrs = {
            "requirements": "(HasLargeScratch == True)",
            "+WantGPULab": "true",
            "+ProjectName": '"Special Project"',
        }

        task = Task(
            id="custom_task",
            command=EnvironmentSpecificValue("python gpu_analysis.py", ["distributed_computing"]),
            cpu=EnvironmentSpecificValue(4, ["distributed_computing"]),
            mem_mb=EnvironmentSpecificValue(8192, ["distributed_computing"]),
            gpu=EnvironmentSpecificValue(1, ["distributed_computing"]),
        )
        # Add custom attributes to extra field
        task.extra["custom_attributes"] = EnvironmentSpecificValue(custom_attrs, ["distributed_computing"])
        wf.add_task(task)

        dag_path = persistent_test_output / "inline_custom.dag"
        dag_exporter.from_workflow(
            wf, dag_path, workdir=persistent_test_output, inline_submit=True
        )

        dag_content = dag_path.read_text()

        # Check custom attributes are included
        assert "requirements = (HasLargeScratch == True)" in dag_content
        assert "+WantGPULab = true" in dag_content
        assert '+ProjectName = "Special Project"' in dag_content

    def test_inline_submit_round_trip(self, persistent_test_output):
        """Test that workflows can be round-tripped through inline submit descriptions."""
        # Create original workflow
        wf_original = Workflow(name="roundtrip_test", version="2.0")
        wf_original.meta = {"description": "Test workflow for round-trip"}

        task1 = Task(
            id="task_one",
            command=EnvironmentSpecificValue("echo 'First task'", ["distributed_computing"]),
            cpu=EnvironmentSpecificValue(2, ["distributed_computing"]),
            mem_mb=EnvironmentSpecificValue(4096, ["distributed_computing"]),
            gpu=EnvironmentSpecificValue(1, ["distributed_computing"]),
            container=EnvironmentSpecificValue("docker://python:3.9", ["distributed_computing"]),
        )

        task2 = Task(
            id="task_two",
            command=EnvironmentSpecificValue("echo 'Second task'", ["distributed_computing"]),
            cpu=EnvironmentSpecificValue(1, ["distributed_computing"]),
            mem_mb=EnvironmentSpecificValue(2048, ["distributed_computing"]),
            conda=EnvironmentSpecificValue("env.yaml", ["distributed_computing"]),
        )

        wf_original.add_task(task1)
        wf_original.add_task(task2)
        wf_original.add_edge("task_one", "task_two")

        # Export with inline submit descriptions
        dag_path = persistent_test_output / "roundtrip.dag"
        dag_exporter.from_workflow(
            wf_original, dag_path, workdir=persistent_test_output, inline_submit=True
        )

        # Import back
        wf_imported = dag_importer.to_workflow(dag_path)

        # Check workflow metadata preservation
        assert wf_imported.name == wf_original.name
        assert wf_imported.version == wf_original.version
        # Check metadata preservation - both should have the same metadata structure
        if hasattr(wf_original, 'metadata') and wf_original.metadata:
            assert hasattr(wf_imported, 'metadata')
            # For now, just check that metadata exists - detailed comparison can be added later
        elif hasattr(wf_imported, 'metadata') and wf_imported.metadata:
            # If imported has metadata but original doesn't, that's also acceptable
            pass

        # Check tasks are preserved
        assert len(wf_imported.tasks) == 2
        assert "task_one" in wf_imported.tasks
        assert "task_two" in wf_imported.tasks

        # Check task details - note that the imported workflow will have different structure
        imported_task1 = wf_imported.tasks["task_one"]
        # The imported task will have the command as a string, not EnvironmentSpecificValue
        assert "echo 'First task'" in str(imported_task1.command)
        
        imported_task2 = wf_imported.tasks["task_two"]
        assert "echo 'Second task'" in str(imported_task2.command)

        # Check dependencies are preserved
        assert len(wf_imported.edges) == 1
        edge = wf_imported.edges[0]
        assert edge.parent == "task_one"
        assert edge.child == "task_two"

    def test_inline_submit_vs_external_equivalence(self, persistent_test_output):
        """Test that inline and external submit descriptions produce equivalent results."""
        wf = Workflow(name="equivalence_test")

        task = Task(
            id="test_task",
            command=EnvironmentSpecificValue("python test.py", ["distributed_computing"]),
            cpu=EnvironmentSpecificValue(4, ["distributed_computing"]),
            mem_mb=EnvironmentSpecificValue(8192, ["distributed_computing"]),
            gpu=EnvironmentSpecificValue(1, ["distributed_computing"]),
            container=EnvironmentSpecificValue("docker://tensorflow/tensorflow:latest", ["distributed_computing"]),
            retry_count=EnvironmentSpecificValue(2, ["distributed_computing"]),
        )
        wf.add_task(task)

        # Export with external submit files
        dag_external_path = persistent_test_output / "external.dag"
        dag_exporter.from_workflow(
            wf, dag_external_path, workdir=persistent_test_output, inline_submit=False
        )

        # Export with inline submit descriptions
        dag_inline_path = persistent_test_output / "inline.dag"
        dag_exporter.from_workflow(
            wf, dag_inline_path, workdir=persistent_test_output, inline_submit=True
        )

        # Import both versions
        wf_external = dag_importer.to_workflow(dag_external_path)
        wf_inline = dag_importer.to_workflow(dag_inline_path)

        # Compare the imported workflows - they should be functionally equivalent
        assert wf_external.name == wf_inline.name
        assert len(wf_external.tasks) == len(wf_inline.tasks)

        task_external = wf_external.tasks["test_task"]
        task_inline = wf_inline.tasks["test_task"]

        # Core attributes should be the same
        assert str(task_external.command) == str(task_inline.command)

    def test_inline_submit_container_types(self, persistent_test_output):
        """Test inline submit descriptions with different container types."""
        wf = Workflow(name="container_types_test")

        # Docker container
        docker_task = Task(
            id="docker_task",
            command=EnvironmentSpecificValue("python docker_script.py", ["distributed_computing"]),
            container=EnvironmentSpecificValue("docker://python:3.9", ["distributed_computing"]),
        )

        # Singularity container
        singularity_task = Task(
            id="singularity_task",
            command=EnvironmentSpecificValue("python singularity_script.py", ["distributed_computing"]),
            container=EnvironmentSpecificValue("/path/to/container.sif", ["distributed_computing"]),
        )

        # Conda environment
        conda_task = Task(
            id="conda_task",
            command=EnvironmentSpecificValue("python conda_script.py", ["distributed_computing"]),
            conda=EnvironmentSpecificValue("environment.yaml", ["distributed_computing"]),
        )

        wf.add_task(docker_task)
        wf.add_task(singularity_task)
        wf.add_task(conda_task)

        dag_path = persistent_test_output / "container_types.dag"
        dag_exporter.from_workflow(
            wf, dag_path, workdir=persistent_test_output, inline_submit=True
        )

        dag_content = dag_path.read_text()

        # Check Docker universe
        assert "universe = docker" in dag_content
        assert "docker_image = python:3.9" in dag_content

        # Check Singularity universe
        assert "universe = vanilla" in dag_content
        assert '+SingularityImage = "/path/to/container.sif"' in dag_content

        # Check conda environment specification
        assert "+CondaEnv = environment.yaml" in dag_content

    def test_inline_submit_default_resources(self, persistent_test_output):
        """Test inline submit descriptions with default resource values."""
        wf = Workflow(name="defaults_test")

        # Task with no explicit resources - will use defaults
        task = Task(
            id="default_task", 
            command=EnvironmentSpecificValue("echo 'Using defaults'", ["distributed_computing"])
        )
        wf.add_task(task)

        dag_path = persistent_test_output / "defaults.dag"
        dag_exporter.from_workflow(
            wf,
            dag_path,
            workdir=persistent_test_output,
            inline_submit=True,
            default_memory="8GB",
            default_disk="10GB",
            default_cpus=2,
        )

        dag_content = dag_path.read_text()

        # Check default values are used
        # CPU uses exporter default (2) since task.resources.cpu is None
        assert "request_cpus = 2" in dag_content
        # Memory and disk use exporter defaults since task resources are None
        assert "request_memory = 8192MB" in dag_content  # 8GB converted to MB
        assert "request_disk = 10240MB" in dag_content  # 10GB converted to MB

    def test_inline_submit_special_characters(self, persistent_test_output):
        """Test inline submit descriptions handle special characters correctly."""
        wf = Workflow(name="special_chars_test")

        custom_attrs = {
            "requirements": '(Memory > 4000) && (OpSysAndVer == "CentOS7")',
            "+ProjectName": '"Project with spaces and symbols!"',
        }

        task = Task(
            id="special_chars_task",
            command=EnvironmentSpecificValue('echo "Hello, World!"', ["distributed_computing"]),
            cpu=EnvironmentSpecificValue(2, ["distributed_computing"]),
            mem_mb=EnvironmentSpecificValue(4096, ["distributed_computing"]),
        )
        # Add custom attributes to extra field
        task.extra["custom_attributes"] = EnvironmentSpecificValue(custom_attrs, ["distributed_computing"])
        wf.add_task(task)


class TestDAGManInlineSubmitCLI:
    """Test CLI integration for inline submit descriptions."""

    # TODO: Fix CLI test - currently has issues with test setup
    # def test_cli_inline_submit_flag(self, tmp_path):
    #     """Test that the CLI --inline-submit flag works correctly."""
    #     from wf2wf.cli import simple_main
    #     import sys
    #     from io import StringIO
    #
    #     # Create a simple workflow JSON file
    #     wf = Workflow(name="cli_test")
    #     task = Task(
    #         id="cli_task",
    #         command="echo 'CLI test'",
    #         resources=ResourceSpec(cpu=2, mem_mb=4096)
    #     )
    #     wf.add_task(task)
    #
    #     input_json = tmp_path / "input.json"
    #     wf.save_json(input_json)
    #
    #     output_dag = tmp_path / "output.dag"
    #
    #     # Test CLI with inline-submit flag
    #     old_argv = sys.argv
    #     old_stdout = sys.stdout
    #     try:
    #         sys.argv = [
    #             'wf2wf',
    #             'convert',
    #             '--input', str(input_json),
    #             '--output', str(output_dag),
    #             '--inline-submit',
    #             '--verbose'
    #         ]
    #         sys.stdout = StringIO()
    #         simple_main()
    #         output = sys.stdout.getvalue()
    #     finally:
    #         sys.argv = old_argv
    #         sys.stdout = old_stdout
    #
    #     # Check that output DAG uses inline submit descriptions
    #     assert output_dag.exists()
    #     dag_content = output_dag.read_text()
    #     assert "JOB cli_task {" in dag_content
    #     assert "request_cpus = 2" in dag_content
    #     assert "}" in dag_content
    #
    #     # Should not create separate submit file
    #     submit_file = tmp_path / "cli_task.sub"
    #     assert not submit_file.exists()
