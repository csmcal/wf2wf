import sys
import time

# This is a dummy script for a long-running process
print("Running intensive_analysis.py")

input_file = sys.argv[1]
output_file = sys.argv[2]

# Simulate a CPU-intensive task
time.sleep(5)

with open(output_file, "w") as f:
    f.write(f"Intensive analysis completed on {input_file}\\n")

print("Intensive analysis finished.")
