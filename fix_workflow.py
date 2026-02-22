import json
import subprocess

with open(r"C:\Users\Cuper\.gemini\antigravity\brain\c3ac2a0c-0e43-43d5-a857-eba6125a2a6f\.system_generated\steps\1343\output.txt", "r", encoding="utf8") as f:
    text = f.read()

# Try to find the JSON `{ "success": true, "data": { ... }`
# since the file has line numbers, we need to strip them.
lines = text.split("\n")
json_lines = []
for line in lines:
    if ": " in line:
        json_lines.append(line.split(": ", 1)[1])

json_str = "\n".join(json_lines)
try:
    data = json.loads(json_str)
    workflow_data = data["data"]
    
    # Save the clean JSON
    with open("workflow_clean.json", "w", encoding="utf8") as out:
        json.dump(workflow_data, out, indent=2)
    print("Saved workflow_clean.json successfully.")
except Exception as e:
    print("Error parsing JSON:", e)
