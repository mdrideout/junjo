#!/usr/bin/env python3
import os
import sys
import filecmp
import difflib

def compare_protos(sdk_proto_dir, studio_proto_dir):
    """
    Compares proto files in the SDK directory against the Studio directory.
    Fail if:
    1. A file exists in SDK but not in Studio (SDK should follow Studio's contract).
    2. Content differs.
    """
    print(f"Comparing SDK protos in '{sdk_proto_dir}' with Studio protos in '{studio_proto_dir}'...")

    # Get list of proto files in SDK
    sdk_files = [f for f in os.listdir(sdk_proto_dir) if f.endswith('.proto')]
    
    if not sdk_files:
        print("No proto files found in SDK directory.")
        sys.exit(1)

    errors = 0

    for filename in sdk_files:
        sdk_path = os.path.join(sdk_proto_dir, filename)
        studio_path = os.path.join(studio_proto_dir, filename)

        # Check existence
        if not os.path.exists(studio_path):
            print(f"❌ MISSING: '{filename}' exists in SDK but is missing in Studio ({studio_proto_dir})")
            errors += 1
            continue

        # Check content equality
        # We read files to handle potential whitespace/formatting differences if we wanted to be smarter,
        # but for now, strict equality (or simple text diff) is best for protos.
        with open(sdk_path, 'r') as f1, open(studio_path, 'r') as f2:
            sdk_content = f1.readlines()
            studio_content = f2.readlines()

        if sdk_content != studio_content:
            print(f"❌ MISMATCH: '{filename}' differs between SDK and Studio.")
            print("Diff:")
            sys.stdout.writelines(difflib.unified_diff(
                studio_content, sdk_content,
                fromfile=f"Studio/{filename}",
                tofile=f"SDK/{filename}",
            ))
            errors += 1
        else:
            print(f"✅ MATCH: '{filename}'")

    if errors > 0:
        print(f"\nFound {errors} discrepancies.")
        sys.exit(1)
    else:
        print("\nAll proto files match successfully!")
        sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: compare_protos.py <sdk_proto_dir> <studio_proto_dir>")
        sys.exit(1)
    
    compare_protos(sys.argv[1], sys.argv[2])
