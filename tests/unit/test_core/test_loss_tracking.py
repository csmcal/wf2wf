"""
Comprehensive tests for the updated loss tracking system with new IR support.
Tests environment-specific losses, spec class losses, and comprehensive loss tracking features.
"""

import json
import pytest
from pathlib import Path
from wf2wf.core import (
    Workflow, Task, EnvironmentSpecificValue,
    CheckpointSpec, LoggingSpec, SecuritySpec, NetworkingSpec
)
from wf2wf.loss import (
    reset, record, as_list, generate_summary, create_loss_document,
    record_environment_adaptation, record_spec_class_loss,
    record_environment_specific_loss, record_resource_specification_loss,
    record_file_transfer_loss, record_error_handling_loss,
    apply, prepare, compute_checksum
)


class TestLossTracking:
    """Test the comprehensive loss tracking system."""

    def setup_method(self):
        """Reset loss tracking before each test."""
        reset()

    def test_basic_loss_recording(self):
        """Test basic loss recording functionality."""
        record(
            json_pointer="/tasks/task1/cpu",
            field="cpu",
            lost_value=4,
            reason="Target format does not support CPU specification",
            origin="user",
            severity="warn",
            category="resource_specification"
        )
        
        entries = as_list()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["json_pointer"] == "/tasks/task1/cpu"
        assert entry["field"] == "cpu"
        assert entry["lost_value"] == 4
        assert entry["category"] == "resource_specification"
        assert entry["severity"] == "warn"
        assert entry["origin"] == "user"
        assert entry["status"] == "lost"

    def test_environment_adaptation_recording(self):
        """Test recording environment adaptation information."""
        record_environment_adaptation(
            source_env="shared_filesystem",
            target_env="distributed_computing",
            adaptation_type="filesystem_to_distributed",
            details={
                "resource_changes": ["cpu", "memory", "disk"],
                "file_transfer_added": True
            },
            severity="info"
        )
        
        entries = as_list()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["category"] == "execution_model"
        assert entry["field"] == "environment_adaptation"
        assert entry["lost_value"]["source_environment"] == "shared_filesystem"
        assert entry["lost_value"]["target_environment"] == "distributed_computing"
        assert "resource_changes" in entry["lost_value"]["details"]

    def test_environment_specific_loss_recording(self):
        """Test recording environment-specific value losses."""
        env_value = EnvironmentSpecificValue(value=4, environments=["shared_filesystem"])
        env_value.set_for_environment(8, "distributed_computing")
        
        record_environment_specific_loss(
            json_pointer="/tasks/task1/cpu",
            field="cpu",
            env_value=env_value,
            target_environment="cloud_native",
            reason="Cloud environment does not support environment-specific CPU values",
            severity="warn"
        )
        
        entries = as_list()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["category"] == "environment_specific"
        assert "shared_filesystem" in entry["environment_context"]["applicable_environments"]
        assert "distributed_computing" in entry["environment_context"]["applicable_environments"]
        assert entry["environment_context"]["target_environment"] == "cloud_native"
        assert len(entry["recovery_suggestions"]) > 0

    def test_spec_class_loss_recording(self):
        """Test recording spec class object losses."""
        checkpoint_spec = CheckpointSpec(
            strategy="filesystem",
            interval=300,
            storage_location="/tmp/checkpoints"
        )
        
        record_spec_class_loss(
            json_pointer="/tasks/task1/checkpointing",
            field="checkpointing",
            spec_object=checkpoint_spec,
            spec_type="checkpointing",
            reason="Target format does not support checkpointing specifications",
            severity="warn"
        )
        
        entries = as_list()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["category"] == "specification_class"
        # Convert spec object to dict for assertion
        from wf2wf.core import WF2WFJSONEncoder
        spec_dict = json.loads(json.dumps(checkpoint_spec, cls=WF2WFJSONEncoder))
        assert spec_dict["strategy"] == "filesystem"
        assert spec_dict["interval"] == 300
        assert "checkpointing" in entry["recovery_suggestions"][0]

    def test_resource_specification_loss_recording(self):
        """Test recording resource specification losses."""
        record_resource_specification_loss(
            task_id="task1",
            resource_field="gpu",
            original_value=2,
            target_environment="shared_filesystem",
            reason="Shared filesystem environment does not support GPU specifications",
            severity="warn"
        )
        
        entries = as_list()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["json_pointer"] == "/tasks/task1/gpu"
        assert entry["field"] == "gpu"
        assert entry["lost_value"] == 2
        assert entry["category"] == "resource_specification"
        assert entry["environment_context"]["target_environment"] == "shared_filesystem"

    def test_file_transfer_loss_recording(self):
        """Test recording file transfer specification losses."""
        record_file_transfer_loss(
            task_id="task1",
            transfer_field="file_transfer_mode",
            original_value="explicit",
            target_environment="shared_filesystem",
            reason="Shared filesystem does not require explicit file transfer",
            severity="info"
        )
        
        entries = as_list()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["category"] == "file_transfer"
        assert entry["lost_value"] == "explicit"
        assert "file transfer" in entry["recovery_suggestions"][0]

    def test_error_handling_loss_recording(self):
        """Test recording error handling specification losses."""
        record_error_handling_loss(
            task_id="task1",
            error_field="retry_count",
            original_value=3,
            target_environment="shared_filesystem",
            reason="Shared filesystem environment does not support retry specifications",
            severity="warn"
        )
        
        entries = as_list()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["category"] == "error_handling"
        assert entry["lost_value"] == 3
        assert "error handling" in entry["recovery_suggestions"][0]

    def test_loss_deduplication(self):
        """Test that duplicate losses are not recorded."""
        record(
            json_pointer="/tasks/task1/cpu",
            field="cpu",
            lost_value=4,
            reason="Test reason",
            origin="user"
        )
        
        # Try to record the same loss again
        record(
            json_pointer="/tasks/task1/cpu",
            field="cpu",
            lost_value=4,
            reason="Test reason 2",
            origin="user"
        )
        
        entries = as_list()
        assert len(entries) == 1  # Should not duplicate

    def test_lost_again_status(self):
        """Test that previously reapplied losses are marked as 'lost_again'."""
        # Simulate a previously reapplied entry
        prev_entries = [{
            "json_pointer": "/tasks/task1/cpu",
            "field": "cpu",
            "status": "reapplied"
        }]
        prepare(prev_entries)
        
        # Record the same loss again
        record(
            json_pointer="/tasks/task1/cpu",
            field="cpu",
            lost_value=4,
            reason="Test reason",
            origin="user"
        )
        
        entries = as_list()
        assert len(entries) == 1
        assert entries[0]["status"] == "lost_again"

    def test_summary_generation(self):
        """Test summary statistics generation."""
        # Record various types of losses
        record(
            json_pointer="/tasks/task1/cpu",
            field="cpu",
            lost_value=4,
            reason="Test 1",
            origin="user",
            severity="warn",
            category="resource_specification"
        )
        
        record(
            json_pointer="/tasks/task1/gpu",
            field="gpu",
            lost_value=1,
            reason="Test 2",
            origin="wf2wf",
            severity="info",
            category="resource_specification"
        )
        
        record(
            json_pointer="/tasks/task1/checkpointing",
            field="checkpointing",
            lost_value={},
            reason="Test 3",
            origin="user",
            severity="error",
            category="checkpointing"
        )
        
        summary = generate_summary()
        assert summary["total_entries"] == 3
        assert summary["by_category"]["resource_specification"] == 2
        assert summary["by_category"]["checkpointing"] == 1
        assert summary["by_severity"]["warn"] == 1
        assert summary["by_severity"]["info"] == 1
        assert summary["by_severity"]["error"] == 1
        assert summary["by_origin"]["user"] == 2
        assert summary["by_origin"]["wf2wf"] == 1

    def test_loss_document_creation(self):
        """Test comprehensive loss document creation."""
        record(
            json_pointer="/tasks/task1/cpu",
            field="cpu",
            lost_value=4,
            reason="Test reason",
            origin="user"
        )
        
        environment_adaptation = {
            "source_environment": "shared_filesystem",
            "target_environment": "distributed_computing",
            "adaptation_type": "filesystem_to_distributed"
        }
        
        doc = create_loss_document(
            target_engine="dagman",
            source_checksum="sha256:1234567890abcdef",
            environment_adaptation=environment_adaptation
        )
        
        assert doc["wf2wf_version"] == "0.3.0"
        assert doc["target_engine"] == "dagman"
        assert doc["source_checksum"] == "sha256:1234567890abcdef"
        assert "timestamp" in doc
        assert len(doc["entries"]) == 1
        assert "summary" in doc
        assert doc["environment_adaptation"] == environment_adaptation

    def test_workflow_checksum_computation(self):
        """Test workflow checksum computation."""
        workflow = Workflow(name="test_workflow")
        task = Task(id="task1")
        workflow.add_task(task)
        
        # Use the workflow's built-in JSON serialization for checksum
        checksum = compute_checksum(workflow)
        assert checksum.startswith("sha256:")
        assert len(checksum) == 71  # "sha256:" + 64 hex chars

    def test_loss_reinjection(self):
        """Test loss reinjection into workflow."""
        # Create a workflow
        workflow = Workflow(name="test_workflow")
        task = Task(id="task1")
        workflow.add_task(task)
        
        # Create a loss entry with simple integer value
        loss_entry = {
            "json_pointer": "/tasks/task1/cpu",
            "field": "cpu",
            "lost_value": 4,
            "status": "lost"
        }
        
        # Apply the loss entry
        apply(workflow, [loss_entry])
        
        # Check that the value was reinjected
        assert loss_entry["status"] == "reapplied"
        assert workflow.tasks["task1"].cpu.default_value == 4

    def test_loss_reinjection_failure(self):
        """Test loss reinjection failure handling."""
        workflow = Workflow(name="test_workflow")
        task = Task(id="task1")
        workflow.add_task(task)
        
        # Create an invalid loss entry
        loss_entry = {
            "json_pointer": "/tasks/nonexistent/cpu",
            "field": "cpu",
            "lost_value": 4,
            "status": "lost"
        }
        
        # Apply the loss entry (should fail gracefully)
        apply(workflow, [loss_entry])
        
        # Check that the status remains "lost"
        assert loss_entry["status"] == "lost"

    def test_multiple_loss_categories(self):
        """Test recording losses in multiple categories."""
        categories = [
            ("resource_specification", "/tasks/task1/cpu", "cpu", 4),
            ("file_transfer", "/tasks/task1/file_transfer_mode", "file_transfer_mode", "explicit"),
            ("error_handling", "/tasks/task1/retry_count", "retry_count", 3),
            ("checkpointing", "/tasks/task1/checkpointing", "checkpointing", {}),
            ("logging", "/tasks/task1/logging", "logging", {}),
            ("security", "/tasks/task1/security", "security", {}),
            ("networking", "/tasks/task1/networking", "networking", {}),
            ("metadata", "/provenance", "provenance", {}),
            ("metadata", "/metadata/original_execution_environment", "original_execution_environment", "shared_filesystem"),
            ("advanced_features", "/tasks/task1/when", "when", "condition"),
            ("legacy_compatibility", "/tasks/task1/legacy_field", "legacy_field", "value")
        ]
        
        for category, pointer, field, value in categories:
            record(
                json_pointer=pointer,
                field=field,
                lost_value=value,
                reason=f"Test {category}",
                category=category
            )
        
        entries = as_list()
        assert len(entries) == len(categories)
        
        summary = generate_summary()
        assert summary["total_entries"] == len(categories)
        
        # Check that all categories are represented
        for category, _, _, _ in categories:
            assert category in summary["by_category"]
            assert summary["by_category"][category] >= 1 