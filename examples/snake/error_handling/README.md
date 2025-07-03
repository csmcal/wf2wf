# Error Handling Examples

This directory contains examples demonstrating error cases, edge conditions, and unsupported features in snake2dagman.

## Examples

### error.smk
Basic error handling examples:
- Invalid rule definitions
- Missing dependencies
- File access errors

### circular_dep.smk
Demonstrates circular dependency detection:
- Direct circular dependencies
- Indirect circular dependencies
- Error reporting

### unsupported.smk
Examples of unsupported Snakemake features:
- Dynamic file determination
- Pipe() usage
- Other unsupported patterns

### empty.smk
Demonstrates empty workflow handling:
- No rules defined
- Empty rule bodies
- Minimal workflow structure

## Usage

Run any example with:
```bash
snake2dagman --snakefile examples/error_handling/[example].smk
```

These examples are useful for:
- Testing error handling
- Understanding limitations
- Debugging workflow issues
- Learning about unsupported features
