"""
wf2wf.importers.utils – Shared utilities for workflow importers.

This module provides common utilities that can be used across different
workflow format importers, such as text parsing, block extraction, and
other shared functionality.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_balanced_braces(text: str, start_pos: int) -> str:
    """
    Extract content within balanced braces starting from start_pos.
    
    This utility function can be used by any importer that needs to extract
    blocks with nested braces, such as WDL, Nextflow, or other formats
    that use brace-delimited blocks.
    
    Args:
        text: The text to search in
        start_pos: The position to start searching from (should be at an opening brace)
        
    Returns:
        The content within the balanced braces (excluding the braces themselves)
        
    Raises:
        ValueError: If braces are not properly balanced
    """
    brace_count = 0
    i = start_pos
    while i < len(text):
        if text[i] == "{":
            brace_count += 1
        elif text[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                return text[start_pos + 1 : i]
        i += 1
    
    # If we reach here, braces are not balanced
    raise ValueError(f"Unbalanced braces in text starting at position {start_pos}")


def extract_balanced_parens(text: str, start_pos: int) -> str:
    """
    Extract content within balanced parentheses starting from start_pos.
    
    Similar to extract_balanced_braces but for parentheses.
    
    Args:
        text: The text to search in
        start_pos: The position to start searching from (should be at an opening paren)
        
    Returns:
        The content within the balanced parentheses (excluding the parentheses themselves)
        
    Raises:
        ValueError: If parentheses are not properly balanced
    """
    paren_count = 0
    i = start_pos
    while i < len(text):
        if text[i] == "(":
            paren_count += 1
        elif text[i] == ")":
            paren_count -= 1
            if paren_count == 0:
                return text[start_pos + 1 : i]
        i += 1
    
    # If we reach here, parentheses are not balanced
    raise ValueError(f"Unbalanced parentheses in text starting at position {start_pos}")


def parse_key_value_pairs(text: str, separator: str = "=", comment_char: str = "#") -> Dict[str, str]:
    """
    Parse key-value pairs from text.
    
    This is a generic utility for parsing configuration-like text where
    each line contains a key-value pair separated by a specified character.
    
    Args:
        text: The text to parse
        separator: The character that separates keys from values (default: "=")
        comment_char: The character that indicates comments (default: "#")
        
    Returns:
        Dictionary of key-value pairs
    """
    result = {}
    
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith(comment_char):
            continue
        
        # Split on separator, but only on the first occurrence
        parts = line.split(separator, 1)
        if len(parts) == 2:
            key = parts[0].strip()
            value = parts[1].strip().strip('"\'')  # Remove quotes
            result[key] = value
    
    return result


def parse_section_blocks(content: str, section_pattern: str, block_start: str = "{", block_end: str = "}") -> List[Dict[str, Any]]:
    """
    Parse section blocks from content using a regex pattern.
    
    This is a generic utility for extracting named sections with blocks
    from text content. Useful for parsing workflow languages that have
    section-based syntax.
    
    Args:
        content: The content to parse
        section_pattern: Regex pattern to match section names
        block_start: Character that starts a block (default: "{")
        block_end: Character that ends a block (default: "}")
        
    Returns:
        List of dictionaries containing section name and block content
    """
    import re
    
    sections = []
    pattern = rf"{section_pattern}\s*\{block_start}"
    
    matches = re.finditer(pattern, content, re.DOTALL)
    for match in matches:
        section_name = match.group(1) if match.groups() else "unnamed"
        block_start_pos = match.end() - 1
        
        try:
            if block_start == "{":
                block_content = extract_balanced_braces(content, block_start_pos)
            elif block_start == "(":
                block_content = extract_balanced_parens(content, block_start_pos)
            else:
                # Fallback for other block types
                block_content = _extract_generic_block(content, block_start_pos, block_start, block_end)
            
            sections.append({
                "name": section_name,
                "content": block_content,
                "start_pos": match.start(),
                "end_pos": block_start_pos + len(block_content) + 1
            })
            
        except ValueError as e:
            logger.warning(f"Failed to extract block for section {section_name}: {e}")
            continue
    
    return sections


def _extract_generic_block(text: str, start_pos: int, start_char: str, end_char: str) -> str:
    """
    Extract content within balanced delimiters.
    
    Args:
        text: The text to search in
        start_pos: The position to start searching from
        start_char: The character that starts a block
        end_char: The character that ends a block
        
    Returns:
        The content within the balanced delimiters
        
    Raises:
        ValueError: If delimiters are not properly balanced
    """
    delimiter_count = 0
    i = start_pos
    while i < len(text):
        if text[i] == start_char:
            delimiter_count += 1
        elif text[i] == end_char:
            delimiter_count -= 1
            if delimiter_count == 0:
                return text[start_pos + 1 : i]
        i += 1
    
    raise ValueError(f"Unbalanced delimiters in text starting at position {start_pos}")


def normalize_whitespace(text: str) -> str:
    """
    Normalize whitespace in text.
    
    Removes extra whitespace, normalizes line endings, and trims
    leading/trailing whitespace.
    
    Args:
        text: The text to normalize
        
    Returns:
        Normalized text
    """
    # Replace multiple whitespace with single space
    text = " ".join(text.split())
    return text.strip()


def extract_comments(text: str, comment_chars: List[str] = None) -> List[str]:
    """
    Extract comments from text.
    
    Args:
        text: The text to extract comments from
        comment_chars: List of comment characters (default: ["#", "//", "/*"])
        
    Returns:
        List of comment strings
    """
    if comment_chars is None:
        comment_chars = ["#", "//", "/*"]
    
    comments = []
    lines = text.split("\n")
    
    for line in lines:
        line = line.strip()
        for comment_char in comment_chars:
            if line.startswith(comment_char):
                comment = line[len(comment_char):].strip()
                if comment:
                    comments.append(comment)
                break
    
    return comments 


def parse_memory_string(memory_str: str) -> Optional[int]:
    """
    Parse memory string and convert to MB.
    
    Supports various formats:
    - "8G" -> 8192
    - "4GB" -> 4096
    - "512M" -> 512
    - "2TB" -> 2097152
    
    Args:
        memory_str: Memory string to parse
        
    Returns:
        Memory in MB, or None if parsing fails
    """
    if not memory_str:
        return None
    
    memory_str = str(memory_str).strip().upper()
    
    # Extract number and unit
    import re
    match = re.match(r"(\d+(?:\.\d+)?)[\.\s]*([KMGT]B|[KMGT])?", memory_str)
    if not match:
        return None
    
    number = float(match.group(1))
    unit = match.group(2) or ""
    
    # Convert to MB
    multipliers = {
        "B": 1 / (1024 * 1024),
        "KB": 1 / 1024,
        "K": 1 / 1024,
        "MB": 1,
        "M": 1,
        "GB": 1024,
        "G": 1024,
        "TB": 1024 * 1024,
        "T": 1024 * 1024,
    }
    
    multiplier = multipliers.get(unit, 1)
    return int(number * multiplier)


def parse_disk_string(disk_str: str) -> Optional[int]:
    """
    Parse disk string and convert to MB.
    
    Similar to parse_memory_string but for disk space.
    
    Args:
        disk_str: Disk string to parse
        
    Returns:
        Disk space in MB, or None if parsing fails
    """
    return parse_memory_string(disk_str)


def parse_time_string(time_str: str) -> Optional[int]:
    """
    Parse time string and convert to seconds.
    
    Supports various formats:
    - "2h" -> 7200
    - "30m" -> 1800
    - "1d" -> 86400
    - "3600s" -> 3600
    
    Args:
        time_str: Time string to parse
        
    Returns:
        Time in seconds, or None if parsing fails
    """
    if not time_str:
        return None
    
    time_str = str(time_str).strip().lower()
    
    # Extract number and unit
    import re
    match = re.match(r"(\d+(?:\.\d+)?)\s*([smhd])?", time_str)
    if not match:
        return None
    
    number = float(match.group(1))
    unit = match.group(2) or "s"
    
    # Convert to seconds
    multipliers = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
    }
    
    multiplier = multipliers.get(unit, 1)
    return int(number * multiplier)


def parse_resource_value(value_str: Any) -> Any:
    """
    Parse a resource value, handling various formats.
    
    Args:
        value_str: Value to parse (string, int, float, etc.)
        
    Returns:
        Parsed value, or original value if parsing fails
    """
    if value_str is None:
        return None
    
    if isinstance(value_str, (int, float)):
        return value_str
    
    if isinstance(value_str, str):
        value_str = value_str.strip()
        
        # Try to parse as integer
        try:
            return int(value_str)
        except ValueError:
            pass
        
        # Try to parse as float
        try:
            return float(value_str)
        except ValueError:
            pass
        
        # Try to parse as boolean
        if value_str.lower() in ("true", "yes", "on", "1"):
            return True
        if value_str.lower() in ("false", "no", "off", "0"):
            return False
    
    return value_str


def extract_resource_specifications(content: str, resource_patterns: Dict[str, str]) -> Dict[str, Any]:
    """
    Extract resource specifications from content using regex patterns.
    
    Args:
        content: Content to search for resources
        resource_patterns: Dictionary mapping resource names to regex patterns
        
    Returns:
        Dictionary of extracted resource values
    """
    import re
    
    resources = {}
    
    for resource_name, pattern in resource_patterns.items():
        match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
        if match:
            value_str = match.group(1)
            if resource_name in ["memory", "mem", "ram"]:
                resources[resource_name] = parse_memory_string(value_str)
            elif resource_name in ["disk", "storage"]:
                resources[resource_name] = parse_disk_string(value_str)
            elif resource_name in ["time", "walltime", "runtime"]:
                resources[resource_name] = parse_time_string(value_str)
            else:
                resources[resource_name] = parse_resource_value(value_str)
    
    return resources


def extract_environment_specifications(content: str) -> Dict[str, Any]:
    """
    Extract environment specifications from content.
    
    Args:
        content: Content to search for environment specs
        
    Returns:
        Dictionary of environment specifications
    """
    import re
    
    env_specs = {}
    
    # Container specifications
    container_patterns = [
        r"container\s*['\"`]([^'\"`]+)['\"`]",
        r"docker\s*['\"`]([^'\"`]+)['\"`]",
        r"image\s*['\"`]([^'\"`]+)['\"`]",
    ]
    
    for pattern in container_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            env_specs["container"] = match.group(1)
            break
    
    # Conda environment specifications
    conda_patterns = [
        r"conda\s*['\"`]([^'\"`]+)['\"`]",
        r"conda\s*:\s*['\"`]([^'\"`]+)['\"`]",
    ]
    
    for pattern in conda_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            env_specs["conda"] = match.group(1)
            break
    
    # Working directory
    workdir_match = re.search(r"workdir\s*['\"`]([^'\"`]+)['\"`]", content, re.IGNORECASE)
    if workdir_match:
        env_specs["workdir"] = workdir_match.group(1)
    
    return env_specs


def extract_error_handling_specifications(content: str) -> Dict[str, Any]:
    """
    Extract error handling specifications from content.
    
    Args:
        content: Content to search for error handling specs
        
    Returns:
        Dictionary of error handling specifications
    """
    import re
    
    error_specs = {}
    
    # Retry count
    retry_patterns = [
        r"retry\s*(\d+)",
        r"maxRetries\s*(\d+)",
        r"max_retries\s*(\d+)",
    ]
    
    for pattern in retry_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            error_specs["retry_count"] = int(match.group(1))
            break
    
    # Retry delay
    delay_match = re.search(r"retryDelay\s*(\d+)", content, re.IGNORECASE)
    if delay_match:
        error_specs["retry_delay"] = int(delay_match.group(1))
    
    # Max runtime
    runtime_match = re.search(r"maxRuntime\s*(\d+)", content, re.IGNORECASE)
    if runtime_match:
        error_specs["max_runtime"] = int(runtime_match.group(1))
    
    return error_specs


def normalize_task_id(task_id: str) -> str:
    """
    Normalize task ID to ensure it's valid across different formats.
    
    Args:
        task_id: Original task ID
        
    Returns:
        Normalized task ID
    """
    import re
    
    # Replace invalid characters with underscores
    normalized = re.sub(r'[^a-zA-Z0-9_-]', '_', task_id)
    
    # Ensure it doesn't start with a number
    if normalized and normalized[0].isdigit():
        normalized = f"task_{normalized}"
    
    # Ensure it's not empty
    if not normalized:
        normalized = "unnamed_task"
    
    return normalized


def extract_file_patterns(content: str) -> List[str]:
    """
    Extract file patterns from content.
    
    Args:
        content: Content to search for file patterns
        
    Returns:
        List of file patterns found
    """
    import re
    
    patterns = []
    
    # Common file pattern regexes
    file_patterns = [
        r'["\']([^"\']*\.(?:fastq|fq|bam|sam|vcf|txt|csv|json|yaml|yml|xml|html|pdf|png|jpg|jpeg|gif|svg))["\']',
        r'["\']([^"\']*\{[^}]*\}[^"\']*)["\']',  # Wildcard patterns
        r'["\']([^"\']*\*[^"\']*)["\']',  # Star patterns
    ]
    
    for pattern in file_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        patterns.extend(matches)
    
    return list(set(patterns))  # Remove duplicates


def extract_dependencies_from_content(content: str, task_names: List[str]) -> List[tuple]:
    """
    Extract task dependencies from content.
    
    Args:
        content: Content to search for dependencies
        task_names: List of known task names
        
    Returns:
        List of (parent, child) dependency tuples
    """
    import re
    
    dependencies = []
    
    # Look for patterns that indicate dependencies
    for task_name in task_names:
        # Look for task_name being used as input to other tasks
        pattern = rf'\b{re.escape(task_name)}\b'
        matches = re.finditer(pattern, content)
        
        for match in matches:
            # Find the task that contains this reference
            line_start = content.rfind('\n', 0, match.start()) + 1
            line_end = content.find('\n', match.end())
            if line_end == -1:
                line_end = len(content)
            
            line = content[line_start:line_end]
            
            # Try to identify the containing task
            for other_task in task_names:
                if other_task != task_name:
                    # Check if this line is within the other task's definition
                    task_pattern = rf'\b{re.escape(other_task)}\b'
                    if re.search(task_pattern, line):
                        dependencies.append((task_name, other_task))
                        break
    
    return list(set(dependencies))  # Remove duplicates 


class GenericSectionParser:
    """
    Generic section parser that can be used across different workflow formats.
    
    This class provides common parsing functionality for sections like:
    - Input/output parameters
    - Resource specifications
    - Environment configurations
    - Metadata sections
    """
    
    @staticmethod
    def parse_parameters(params_text: str, param_type: str = "input", comment_chars: List[str] = None) -> Dict[str, Any]:
        """
        Parse parameter declarations from text.
        
        Args:
            params_text: Text containing parameter declarations
            param_type: Type of parameters ("input", "output", "param")
            comment_chars: List of comment characters (default: ["#", "//"])
            
        Returns:
            Dictionary of parameter specifications
        """
        if comment_chars is None:
            comment_chars = ["#", "//"]
        
        params = {}
        
        for line in params_text.split("\n"):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or any(line.startswith(char) for char in comment_chars):
                continue
            
            # Try different parameter patterns
            patterns = [
                # Type name = value
                r"([A-Za-z][A-Za-z0-9_\[\],\s]*)\s+(\w+)(?:\s*=\s*(.+))?",
                # Name = value (no type)
                r"(\w+)\s*=\s*(.+)",
                # Just name (no value)
                r"(\w+)",
            ]
            
            for pattern in patterns:
                import re
                match = re.match(pattern, line)
                if match:
                    if len(match.groups()) >= 2:
                        param_type_wdl = match.group(1).strip()
                        param_name = match.group(2)
                        default_value = match.group(3) if len(match.groups()) > 2 and match.group(3) else None
                    else:
                        param_name = match.group(1)
                        param_type_wdl = "string"  # Default type
                        default_value = None
                    
                    # Remove quotes from default value if it's a string
                    if default_value and default_value.startswith('"') and default_value.endswith('"'):
                        default_value = default_value[1:-1]
                    elif default_value and default_value.startswith("'") and default_value.endswith("'"):
                        default_value = default_value[1:-1]
                    
                    params[param_name] = {
                        "type": param_type_wdl,
                        "default": default_value,
                    }
                    break
        
        return params
    
    @staticmethod
    def parse_key_value_section(section_text: str, comment_chars: List[str] = None) -> Dict[str, Any]:
        """
        Parse a block of key-value pairs, inferring types (int, float, bool) where possible, and using resource parsers for memory/disk/time keys.
        """
        import re
        
        if comment_chars is None:
            comment_chars = ["#", "//"]
        result = {}
        for line in section_text.splitlines():
            line = line.strip()
            if not line or any(line.startswith(c) for c in comment_chars):
                continue
            # Match key = value or key value
            match = re.match(r"(\w+)\s*(?:=|:)\s*(.+)", line)
            if not match:
                match = re.match(r"(\w+)\s+(.+)", line)
            if match:
                key, value = match.group(1), match.group(2).strip().strip("'\"")
                # Resource-specific parsing
                if key.lower() in ("memory", "mem", "disk"):  # Add more as needed
                    from wf2wf.importers.utils import parse_memory_string, parse_disk_string
                    if key.lower() in ("memory", "mem"):
                        value = parse_memory_string(value)
                    elif key.lower() == "disk":
                        value = parse_disk_string(value)
                elif key.lower() == "time":
                    from wf2wf.importers.utils import parse_time_string
                    value = parse_time_string(value)
                # Type inference for other keys
                elif value.lower() in ("true", "false"):
                    value = value.lower() == "true"
                else:
                    try:
                        if "." in value:
                            value = float(value)
                        else:
                            value = int(value)
                    except Exception:
                        pass
                result[key] = value
        return result
    
    @staticmethod
    def parse_script_section(content: str, script_keywords: List[str] = None) -> Optional[str]:
        """
        Parse script content from various formats.
        
        Args:
            content: Content containing script
            script_keywords: List of script keywords to look for (default: ["script", "command", "exec"])
            
        Returns:
            Script content or None if not found
        """
        if script_keywords is None:
            script_keywords = ["script", "command", "exec"]
        
        import re
        
        for keyword in script_keywords:
            # Try different script patterns
            patterns = [
                rf"{keyword}\s*:\s*['\"`]([^'\"`]*)['\"`]",  # Single/double quotes
                rf"{keyword}\s*:\s*'''([^']*)'''",  # Triple quotes
                rf"{keyword}\s*:\s*\"\"\"([^\"]*)\"\"\"",  # Triple double quotes
                rf"{keyword}\s*:\s*`([^`]*)`",  # Backticks
            ]
            
            for pattern in patterns:
                match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
                if match:
                    return match.group(1).strip()
        
        return None
    
    @staticmethod
    def parse_requirements_section(content: str) -> Dict[str, Any]:
        """
        Parse requirements section from content.
        
        Args:
            content: Content containing requirements
            
        Returns:
            Dictionary of requirements
        """
        import re
        
        requirements = {}
        
        # Common requirement patterns
        requirement_patterns = {
            "cpu": [
                r"cpu\s*[:=]\s*(\d+)",
                r"cores\s*[:=]\s*(\d+)",
                r"threads\s*[:=]\s*(\d+)",
            ],
            "memory": [
                r"memory\s*[:=]\s*([^\s]+)",
                r"mem\s*[:=]\s*([^\s]+)",
                r"ram\s*[:=]\s*([^\s]+)",
            ],
            "disk": [
                r"disk\s*[:=]\s*([^\s]+)",
                r"storage\s*[:=]\s*([^\s]+)",
            ],
            "time": [
                r"time\s*[:=]\s*([^\s]+)",
                r"walltime\s*[:=]\s*([^\s]+)",
                r"runtime\s*[:=]\s*([^\s]+)",
            ],
            "gpu": [
                r"gpu\s*[:=]\s*(\d+)",
                r"accelerator\s*(\d+)",
            ],
        }
        
        for req_name, patterns in requirement_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    value_str = match.group(1)
                    if req_name == "memory":
                        requirements[req_name] = parse_memory_string(value_str)
                    elif req_name == "disk":
                        requirements[req_name] = parse_disk_string(value_str)
                    elif req_name == "time":
                        requirements[req_name] = parse_time_string(value_str)
                    else:
                        requirements[req_name] = parse_resource_value(value_str)
                    break
        
        return requirements
    
    @staticmethod
    def parse_metadata_section(content: str) -> Dict[str, Any]:
        """
        Parse metadata section from content.
        
        Args:
            content: Content containing metadata
            
        Returns:
            Dictionary of metadata
        """
        return GenericSectionParser.parse_key_value_section(content)
    
    @staticmethod
    def extract_sections(content: str, section_patterns: Dict[str, str]) -> Dict[str, str]:
        """
        Extract multiple sections from content using patterns.
        
        Args:
            content: Content to parse
            section_patterns: Dictionary mapping section names to regex patterns
            
        Returns:
            Dictionary mapping section names to their content
        """
        import re
        
        sections = {}
        
        for section_name, pattern in section_patterns.items():
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                sections[section_name] = match.group(1).strip()
        
        return sections 


def parse_file_format(file_path: Path) -> str:
    """
    Parse file format based on file extension.
    
    This utility function can be used by any importer to determine
    the format of a file based on its extension.
    
    Args:
        file_path: Path to the file
        
    Returns:
        File format string (json, yaml, yml, etc.)
    """
    extension = file_path.suffix.lower()
    
    format_map = {
        '.json': 'json',
        '.yaml': 'yaml',
        '.yml': 'yaml',
        '.cwl': 'cwl',  # CWL files can be either YAML or JSON
        '.wdl': 'wdl',
        '.nf': 'nextflow',
        '.smk': 'snakemake',
        '.dag': 'dagman',
        '.sub': 'dagman',
        '.ga': 'galaxy'
    }
    
    return format_map.get(extension, 'unknown') 


def parse_cwl_type(type_spec):
    """Parse CWL type specification into TypeSpec object."""
    from wf2wf.core import TypeSpec
    try:
        return TypeSpec.parse(type_spec)
    except Exception as e:
        logger.warning(f"Failed to parse CWL type {type_spec}: {e}")
        return TypeSpec.parse('string')


def parse_requirements(requirements):
    """Parse CWL requirements and hints into RequirementSpec objects."""
    from wf2wf.core import RequirementSpec
    
    if requirements is None:
        requirements = []
    
    logger.debug(f"Parsing {len(requirements)} requirements/hints")
    parsed_requirements = []
    for req in requirements:
        if isinstance(req, dict):
            class_name = req.get('class')
            if class_name:
                requirement_spec = RequirementSpec(
                    class_name=class_name,
                    data={k: v for k, v in req.items() if k != 'class'}
                )
                parsed_requirements.append(requirement_spec)
                logger.debug(f"Added requirement: {class_name}")
    return parsed_requirements


def parse_cwl_parameters(params, param_type):
    """Parse CWL parameters (inputs or outputs) into ParameterSpec list."""
    from wf2wf.core import ParameterSpec, TypeSpec
    logger.debug(f"Parsing CWL {param_type} parameters")
    parameters = []
    if isinstance(params, dict):
        for param_id, param_spec in params.items():
            if isinstance(param_spec, dict):
                type_spec = param_spec.get('type', 'string')
                param_type_spec = parse_cwl_type(type_spec)
                param = ParameterSpec(
                    id=param_id,
                    type=param_type_spec,
                    label=param_spec.get('label'),
                    doc=param_spec.get('doc'),
                    default=param_spec.get('default')
                )
                # Add extra fields if present
                if 'format' in param_spec:
                    param.format = param_spec['format']
                if 'secondaryFiles' in param_spec:
                    param.secondary_files = param_spec['secondaryFiles']
                if 'streamable' in param_spec:
                    param.streamable = param_spec['streamable']
                if 'loadContents' in param_spec:
                    param.load_contents = param_spec['loadContents']
                if 'loadListing' in param_spec:
                    param.load_listing = param_spec['loadListing']
                if 'outputBinding' in param_spec:
                    param.output_binding = param_spec['outputBinding']
                if 'inputBinding' in param_spec:
                    param.input_binding = param_spec['inputBinding']
            else:
                param_type_spec = parse_cwl_type(str(param_spec))
                param = ParameterSpec(
                    id=param_id,
                    type=param_type_spec
                )
            parameters.append(param)
            logger.debug(f"Added {param_type} parameter: {param_id} with type {param_type_spec}")
    elif isinstance(params, list):
        for param_id in params:
            param = ParameterSpec(
                id=param_id,
                type=TypeSpec.parse('string')
            )
            parameters.append(param)
            logger.debug(f"Added {param_type} parameter: {param_id}")
    return parameters 