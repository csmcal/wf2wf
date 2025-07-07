#!/usr/bin/env python3

import re

def test_memory_parsing():
    memory_str = '8.GB'
    memory_str = str(memory_str).strip().upper()
    print('Memory string:', repr(memory_str))
    
    # Test different regex patterns
    patterns = [
        r"(\d+(?:\.\d+)?)\s*([KMGT]?B?)?",
        r"(\d+(?:\.\d+)?)\s*([KMGT]?B*)?",
        r"(\d+(?:\.\d+)?)\s*([KMGT]B*)?",
        r"(\d+(?:\.\d+)?)\s*([KMGT]?B+)?",
        r"(\d+(?:\.\d+)?)\s*([KMGT]?B{0,2})?",
        r"(\d+(?:\.\d+)?)\s*([KMGT]?B{1,2})?",
    ]
    
    for i, pattern in enumerate(patterns):
        match = re.match(pattern, memory_str)
        print(f'Pattern {i+1}: {pattern}')
        print(f'  Match: {match}')
        if match:
            print(f'  Full match: {repr(match.group(0))}')
            print(f'  Number: {match.group(1)}')
            print(f'  Unit: {repr(match.group(2))}')
        print()

if __name__ == "__main__":
    test_memory_parsing() 