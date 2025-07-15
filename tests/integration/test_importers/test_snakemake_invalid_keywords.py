import tempfile
import warnings
import pytest
from pathlib import Path
from wf2wf.importers.snakemake import _parse_snakefile_for_rules, to_workflow


def write_temp_snakefile(content):
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.smk', delete=False)
    f.write(content)
    f.flush()
    return Path(f.name)


def test_valid_snakefile_import():
    content = '''
rule test_valid:
    input: "input.txt"
    output: "output.txt"
    resources:
        mem_mb: 8192
        cpus: 4
    shell: "echo 'test' > {output}"
'''
    path = write_temp_snakefile(content)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        parsed = _parse_snakefile_for_rules(path)
        assert 'test_valid' in parsed['rules']
        assert not w, f"Unexpected warnings: {w}"


def test_snakefile_with_invalid_directive_warns():
    content = '''
rule test_invalid:
    input: "input.txt"
    output: "output.txt"
    when: config.get("run_conditional", False)
    shell: "echo 'test' > {output}"
'''
    path = write_temp_snakefile(content)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        parsed = _parse_snakefile_for_rules(path)
        assert 'test_invalid' in parsed['rules']
        assert any('when' in str(warn.message) for warn in w), "Expected warning for 'when' directive"


def test_snakefile_with_multiple_invalid_directives_warns():
    content = '''
rule test_multi_invalid:
    input: "input.txt"
    output: "output.txt"
    when: config.get("run_conditional", False)
    env: PATH="/usr/local/bin:$PATH"
    shell: "echo 'test' > {output}"
'''
    path = write_temp_snakefile(content)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        parsed = _parse_snakefile_for_rules(path)
        assert 'test_multi_invalid' in parsed['rules']
        assert any('when' in str(warn.message) for warn in w)
        assert any('env' in str(warn.message) for warn in w)


def test_malformed_snakefile_fails():
    content = '''
rule malformed:
    when: config.get("run_conditional", False)
    # No input, output, shell, or script
'''
    path = write_temp_snakefile(content)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        with pytest.raises(Exception):
            to_workflow(path)
        # Verify that the warning was also emitted
        assert any('when' in str(warn.message) for warn in w), "Expected warning for 'when' directive" 