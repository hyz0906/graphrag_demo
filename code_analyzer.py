#!/usr/bin/env python3

import json
import os
import sys
import shutil
from clang.cindex import Index, CursorKind, TranslationUnit, Config
from typing import Dict, List, Set, Tuple

# Try to find libclang in common locations
def find_libclang():
    common_paths = [
        "/usr/lib/x86_64-linux-gnu/libclang-18.so",
        "/usr/lib/libclang.so",
        "/usr/local/lib/libclang.so",
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    # If not found, try to find it using ldconfig
    try:
        import subprocess
        result = subprocess.run(['ldconfig', '-p'], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if 'libclang' in line:
                path = line.split('=>')[1].strip()
                if os.path.exists(path):
                    return path
    except:
        pass
    
    return None

class CodeAnalyzer:
    def __init__(self, compile_commands_path: str):
        # Set the libclang library path
        libclang_path = find_libclang()
        if libclang_path:
            print(f"Using libclang at: {libclang_path}")
            Config.set_library_file(libclang_path)
        else:
            print("Warning: Could not find libclang. Please install it or set the path manually.")
            print("You can set the path by adding this line before creating the Index:")
            print("Config.set_library_file('/path/to/libclang.so')")
            sys.exit(1)
            
        self.index = Index.create()
        self.nodes = []
        self.edges = []
        self.node_ids = {}
        self.compile_commands = self._load_compile_commands(compile_commands_path)

    def _load_compile_commands(self, path: str) -> List[Dict]:
        with open(path, 'r') as f:
            return json.load(f)

    def _get_node_id(self, node_type: str, name: str) -> str:
        key = f"{node_type}:{name}"
        if key not in self.node_ids:
            self.node_ids[key] = len(self.node_ids)
            self.nodes.append({
                "id": self.node_ids[key],
                "type": node_type,
                "name": name
            })
        return self.node_ids[key]

    def _add_edge(self, source_id: int, target_id: int, edge_type: str):
        self.edges.append({
            "source": source_id,
            "target": target_id,
            "type": edge_type
        })

    def _process_cursor(self, cursor, parent_id: int = None):
        if cursor.kind == CursorKind.FUNCTION_DECL:
            func_id = self._get_node_id("function", cursor.spelling)
            if parent_id is not None:
                self._add_edge(parent_id, func_id, "contains")
            
            # Process function body
            for child in cursor.get_children():
                self._process_cursor(child, func_id)

        elif cursor.kind == CursorKind.CALL_EXPR:
            if parent_id is not None:
                called_func = cursor.get_definition()
                if called_func:
                    called_id = self._get_node_id("function", called_func.spelling)
                    self._add_edge(parent_id, called_id, "calls")

        elif cursor.kind == CursorKind.STRUCT_DECL:
            struct_id = self._get_node_id("struct", cursor.spelling)
            if parent_id is not None:
                self._add_edge(parent_id, struct_id, "contains")

        elif cursor.kind == CursorKind.TYPE_REF:
            if parent_id is not None:
                type_cursor = cursor.get_definition()
                if type_cursor:
                    type_id = self._get_node_id("type", type_cursor.spelling)
                    self._add_edge(parent_id, type_id, "uses")

    def analyze_file(self, file_path: str, compile_args: List[str]):
        tu = self.index.parse(file_path, args=compile_args)
        for cursor in tu.cursor.get_children():
            self._process_cursor(cursor)

    def analyze_project(self):
        for cmd in self.compile_commands:
            file_path = cmd["file"]
            if "/usr/include" in file_path:
                continue 
            
            # Handle both "command" and "arguments" formats
            if "command" in cmd:
                compile_args = cmd["command"].split()[1:]  # Skip the compiler name
            elif "arguments" in cmd:
                compile_args = cmd["arguments"][1:-1]  # Skip the compiler name
            else:
                print(f"Warning: No compilation command found for {file_path}")
                continue
                
            self.analyze_file(file_path, compile_args)

    def save_graph(self, output_path: str):
        # Format data for GraphRAG - it needs a list of objects with text fields
        formatted_data = []
        
        # Convert nodes to formatted entries
        for node in self.nodes:
            formatted_node = {
                "id": str(node["id"]),
                "text": f"{node['type']} {node['name']}",
                "type": node["type"],
                "name": node["name"]
            }
            formatted_data.append(formatted_node)
        
        # Convert edges to formatted entries with descriptive text
        for i, edge in enumerate(self.edges):
            source_node = next((n for n in self.nodes if n['id'] == edge['source']), None)
            target_node = next((n for n in self.nodes if n['id'] == edge['target']), None)
            
            if source_node and target_node:
                edge_id = f"e{i}"
                edge_text = f"{source_node['type']} '{source_node['name']}' {edge['type']} {target_node['type']} '{target_node['name']}'"
                
                formatted_edge = {
                    "id": edge_id,
                    "text": edge_text,
                    "source_id": str(edge["source"]),
                    "target_id": str(edge["target"]),
                    "relation": edge["type"]
                }
                formatted_data.append(formatted_edge)
        
        # Save as a flat list of items
        with open(output_path, 'w') as f:
            json.dump(formatted_data, f, indent=2)

def main():
    # Initialize GraphRAG if not already initialized
    try:
        os.system("graphrag init --root .")
    except Exception as e:
        print(f"Note: GraphRAG initialization failed, but we'll continue: {e}")
        print("This might be because GraphRAG is already initialized.")
    
    # Create the input directory if it doesn't exist
    os.makedirs("input", exist_ok=True)
    
    # Analyze the code
    analyzer = CodeAnalyzer("compile_commands.json")
    analyzer.analyze_project()
    
    # Save the graph
    analyzer.save_graph("input/code_graph.json")
    
    # Configure GraphRAG settings
    # settings = {
    #     "input": {
    #         "format": "json",
    #         "schema": {
    #             "nodes": ["id", "type", "name"],
    #             "edges": ["source", "target", "type"]
    #         }
    #     },
    #     "embedding": {
    #         "provider": "Other",
    #         "model": "BAAI/bge-large-en-v1.5",
    #         "api_base": "https://api.siliconflow.cn/v1"
    #     },
    #     "llm": {
    #         "provider": "Other",
    #         "model": "Qwen/Qwen2.5-Coder-7B-Instruct",
    #         "api_base": "https://api.siliconflow.cn/v1"
    #     }
    # }
    
    # with open("graphrag/settings.yaml", 'w') as f:
    #     import yaml
    #     yaml.dump(settings, f)
    
    # Index the graph
    os.system("graphrag index")
    
    # print("Code analysis complete. You can now query the graph using:")
    # print('graphrag query --method local --query "your query here"')

if __name__ == "__main__":
    main() 
