#!/usr/bin/env python3

from wf2wf.importers.snakemake import SnakemakeImporter
import re

# Create importer and get data
importer = SnakemakeImporter(verbose=True)
data = importer._parse_source('examples/snake/advanced/scatter_gather.smk')
dot_output = data['dag_output']

print("DOT OUTPUT:")
print(dot_output)
print("\n" + "="*50 + "\n")

# Test the regex pattern
node_label_pattern = re.compile(r'^(\w+)\s*\[label\s*=\s*"([^"]+)"')
print("TESTING REGEX:")
for line in dot_output.splitlines():
    line = line.strip()
    if 'label' in line:
        print(f"Line: {line}")
        m = node_label_pattern.match(line)
        if m:
            node_id = m.group(1)
            label = m.group(2)
            print(f"  Node ID: '{node_id}'")
            print(f"  Label: '{label}'")
            rule_name = label.split("\n", 1)[0].strip()
            print(f"  Rule name: '{rule_name}'")
        else:
            print("  No match!")
        print("---") 