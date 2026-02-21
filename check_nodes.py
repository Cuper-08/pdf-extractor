import json, re

with open('C:\\Users\\Cuper\\.gemini\\antigravity\\brain\\f1312b7a-601d-4daf-8b97-7daf1befc22e\\.system_generated\\steps\\1139\\output.txt', encoding='utf-8') as f:
    content = f.read()

# Try to find all nodes using regex since json parsing failed 
nodes = re.findall(r'"nodes":\s*{([\s\S]*?)(?:\Z|,\s*"connections")', content)
if nodes:
    nodes_content = nodes[0]
    # find node names which are top level keys inside nodes
    # e.g. "Extract_From_File": { "executionTime"
    node_names = re.findall(r'"([a-zA-Z0-9_ -]+)":\s*{\s*"executionTime"', nodes_content)
    print("Executed nodes:", node_names)
else:
    print("Could not find nodes block")
