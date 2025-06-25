import pytest
import yaml
from pathlib import Path

from wf2wf.importers.cwl import to_workflow
from wf2wf.core import Workflow, Task, ScatterSpec, ParameterSpec, TypeSpec


def _write_tmp(path: Path, doc):
    path.write_text('#!/usr/bin/env cwl-runner\n' + yaml.dump(doc))
    return path


def _simple_tool(cmd_id: str):
    """Return minimal inline CommandLineTool for *cmd_id*."""
    return {
        'class': 'CommandLineTool',
        'baseCommand': ['echo', cmd_id],
        'inputs': {},
        'outputs': {
            'output_file': {
                'type': 'File',
                'outputBinding': {'glob': f'{cmd_id}.txt'}
            }
        }
    }


class TestCWLImporterAdvanced:
    def test_import_when_and_scatter(self, persistent_test_output):
        # Build minimal CWL workflow with scatter + when
        workflow_doc = {
            'cwlVersion': 'v1.2',
            'class': 'Workflow',
            'inputs': {
                'samples': {
                    'type': {'type': 'array', 'items': 'File'}
                },
                'run_optional': {'type': 'boolean', 'default': False}
            },
            'outputs': {
                'final': {
                    'type': 'File',
                    'outputSource': 'maybe_step/output_file'
                }
            },
            'steps': {
                'scatter_step': {
                    'run': _simple_tool('scatter'),
                    'in': {'input_file': 'samples'},
                    'scatter': 'input_file',
                    'scatterMethod': 'dotproduct',
                    'out': ['output_file']
                },
                'maybe_step': {
                    'run': _simple_tool('maybe'),
                    'in': {'input_file': 'scatter_step/output_file'},
                    'when': "$context.run_optional == true",
                    'out': ['output_file']
                }
            }
        }

        wf_path = _write_tmp(persistent_test_output / 'adv_workflow.cwl', workflow_doc)

        wf = to_workflow(wf_path)

        # Validate
        wf.validate()

        # Assertions
        assert 'scatter_step' in wf.tasks and 'maybe_step' in wf.tasks
        scat_task = wf.tasks['scatter_step']
        assert scat_task.scatter is not None
        assert scat_task.scatter.scatter == ['input_file'] or scat_task.scatter.scatter == 'input_file'
        maybe_task = wf.tasks['maybe_step']
        assert maybe_task.when is not None 