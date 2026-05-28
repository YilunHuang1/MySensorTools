import json
import sys
import os

def load_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def compare_dicts(d1, d2, path=""):
    changes = []
    
    # Check for keys in d1
    for k in d1:
        current_path = f"{path}.{k}" if path else k
        if k not in d2:
            changes.append(f"REMOVED: {current_path}")
        else:
            if isinstance(d1[k], dict) and isinstance(d2[k], dict):
                changes.extend(compare_dicts(d1[k], d2[k], current_path))
            elif isinstance(d1[k], list) and isinstance(d2[k], list):
                # Simple list comparison: check if identical
                if d1[k] != d2[k]:
                     changes.append(f"MODIFIED: {current_path} (List changed)")
                     # Optional: detailed list diff if needed, but simple is okay for now
                     changes.append(f"  OLD: {d1[k]}")
                     changes.append(f"  NEW: {d2[k]}")
            elif d1[k] != d2[k]:
                changes.append(f"MODIFIED: {current_path}")
                changes.append(f"  OLD: {d1[k]}")
                changes.append(f"  NEW: {d2[k]}")
    
    # Check for new keys in d2
    for k in d2:
        current_path = f"{path}.{k}" if path else k
        if k not in d1:
            changes.append(f"ADDED: {current_path}")
            
    return changes

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 compare_json.py <file1> <file2>")
        sys.exit(1)
        
    f1 = sys.argv[1]
    f2 = sys.argv[2]
    
    try:
        j1 = load_json(f1)
        j2 = load_json(f2)
        
        diffs = compare_dicts(j1, j2)
        
        print(f"Comparison: {os.path.basename(f1)} -> {os.path.basename(f2)}")
        if not diffs:
            print("No differences found.")
        else:
            for d in diffs:
                print(d)
                
    except Exception as e:
        print(f"Error: {e}")
