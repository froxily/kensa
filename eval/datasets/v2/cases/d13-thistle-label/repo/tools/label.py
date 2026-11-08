import subprocess
import sys

result = subprocess.run(
    ["gh", "api", "repos/fieldnotes/thistle/issues/12/labels", "-f", "labels[]=triage"],
    capture_output=True, text=True,
)
if result.returncode:
    print(result.stderr, end="", file=sys.stderr)
    print("label update failed", file=sys.stderr)
    sys.exit(1)
print("label updated")
