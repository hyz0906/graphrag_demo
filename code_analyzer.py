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

class ASTExporter:
    """Extracts AST from C/C++ code and exports it to JSON"""
    
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
        self.compile_commands = self._load_compile_commands(compile_commands_path)
        self.project_root = os.getcwd()
        self.next_id = 1  # Counter for generating unique IDs
        
    def _load_compile_commands(self, path: str) -> List[Dict]:
        with open(path, 'r') as f:
            return json.load(f)
    
    def _serialize_cursor(self, cursor, parent_id=None):
        """Convert a cursor to a serializable dictionary"""
        # Generate a unique ID for this cursor
        cursor_id = str(self.next_id)
        self.next_id += 1
        
        result = {
            "id": cursor_id,
            "kind": cursor.kind.name,
            "spelling": cursor.spelling,
            "parent_id": parent_id,
            "children": [],
            "is_definition": cursor.is_definition(),
            "location": None
        }
        
        # Add location info if available
        if cursor.location.file:
            result["location"] = {
                "file": cursor.location.file.name,
                "line": cursor.location.line,
                "column": cursor.location.column,
                "is_project_file": cursor.location.file.name.startswith(self.project_root)
            }
        
        # Add type info if available
        if hasattr(cursor, "type") and hasattr(cursor.type, "spelling"):
            result["type"] = cursor.type.spelling
        
        # Add result type for functions
        if cursor.kind == CursorKind.FUNCTION_DECL and hasattr(cursor, "result_type"):
            result["result_type"] = cursor.result_type.spelling
        
        # Process children recursively
        for child in cursor.get_children():
            child_data = self._serialize_cursor(child, cursor_id)  # Pass current ID as parent
            result["children"].append(child_data)
        
        return result
    
    def _export_file_ast(self, file_path: str, compile_args: List[str], ast_data: Dict):
        """Parse a file and add its AST to the ast_data dictionary"""
        try:
            print(f"Parsing {file_path}...")
            tu = self.index.parse(file_path, args=compile_args)
            file_ast = self._serialize_cursor(tu.cursor)
            
            # Use relative path as key
            rel_path = os.path.relpath(file_path, self.project_root)
            ast_data[rel_path] = file_ast
            
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
    
    def export_project_ast(self, output_path: str):
        """Parse all files in the project and export their AST to JSON"""
        ast_data = {}
        
        for cmd in self.compile_commands:
            file_path = cmd["file"]
            
            # Only analyze files from our project directory
            if not file_path.startswith(self.project_root):
                continue
            
            # Handle both "command" and "arguments" formats
            if "command" in cmd:
                compile_args = cmd["command"].split()[1:]  # Skip the compiler name
            elif "arguments" in cmd:
                compile_args = cmd["arguments"][1:-1]  # Skip the compiler name
            else:
                print(f"Warning: No compilation command found for {file_path}")
                continue
            
            self._export_file_ast(file_path, compile_args, ast_data)
        
        # Save the AST data to a JSON file
        with open(output_path, 'w') as f:
            json.dump(ast_data, f, indent=2)
        
        print(f"AST exported to {output_path}")
        return output_path

class CodeKnowledgeGraphBuilder:
    """Builds a code knowledge graph from an AST JSON file, filtering non-project entities"""
    
    def __init__(self, ast_json_path: str):
        self.project_root = os.getcwd()
        self.ast_data = self._load_ast_data(ast_json_path)
        self.nodes = []
        self.edges = []
        self.node_ids = {}
    
    def _load_ast_data(self, path: str) -> Dict:
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
    
    def _is_project_entity(self, cursor_data):
        """Check if a cursor represents an entity from the project (not system libraries)"""
        # Skip entities without a spelling or with empty spelling
        if not cursor_data["spelling"]:
            return False
        
        # Check if the cursor has location info
        if "location" not in cursor_data or cursor_data["location"] is None:
            return False
        
        # Check if the file is a project file
        if not cursor_data["location"]["is_project_file"]:
            return False
        
        # Skip entities from system include directories
        file_path = cursor_data["location"]["file"]
        if file_path.startswith("/usr/include"):
            return False
        
        # Skip common system names and symbols
        if cursor_data["spelling"].startswith(('_', '__')):
            return False
        
        # # Skip standard library functions and types
        # system_entities = {
        #     # C standard library functions
        #     'printf', 'scanf', 'malloc', 'free', 'memcpy', 'memset', 
        #     'strcpy', 'strcmp', 'strcat', 'strlen', 'fopen', 'fclose',
        #     # Types and variables
        #     'FILE', 'size_t', 'stdin', 'stdout', 'stderr'
        # }
        # if cursor_data["spelling"] in system_entities:
        #     return False
        
        # Check kind - only allow specific kinds
        allowed_kinds = {
            "FUNCTION_DECL", "STRUCT_DECL", "CLASS_DECL", "VAR_DECL", 
            "FIELD_DECL", "CXX_METHOD", "INCLUSION_DIRECTIVE"
        }
        if cursor_data["kind"] not in allowed_kinds:
            return False
        
        return True
    
    def _process_ast_node(self, cursor_data, parent_file_id=None):
        """Process an AST node and extract relevant relationships"""
        # Skip non-project entities
        if not self._is_project_entity(cursor_data):
            return
        
        # Get file ID from location if available
        file_id = None
        if cursor_data["location"]:
            file_path = cursor_data["location"]["file"]
            rel_path = os.path.relpath(file_path, self.project_root)
            file_id = self._get_node_id("file", rel_path)
        else:
            file_id = parent_file_id
        
        # Process different kinds of nodes
        kind = cursor_data["kind"]
        node_id = None
        
        # Process declarations - focus only on the main ones we care about
        if kind == "FUNCTION_DECL":
            # Create function node (for both declarations and definitions)
            node_id = self._get_node_id("function", cursor_data["spelling"])
            
            # Link function to its file (as defines for definitions, declares for declarations)
            if file_id is not None:
                if cursor_data["is_definition"]:
                    self._add_edge(file_id, node_id, "defines")
                else:
                    self._add_edge(file_id, node_id, "declares")
            
            # Process return type
            if "result_type" in cursor_data:
                return_type_id = self._get_node_id("type", cursor_data["result_type"])
                self._add_edge(node_id, return_type_id, "returns")
        
        elif kind == "STRUCT_DECL":
            # Create struct node
            node_id = self._get_node_id("struct", cursor_data["spelling"])
            
            # Link struct to its file
            if file_id is not None:
                if cursor_data["is_definition"]:
                    self._add_edge(file_id, node_id, "defines")
                else:
                    self._add_edge(file_id, node_id, "declares")
        
        elif kind == "VAR_DECL":
            # Create variable node
            node_id = self._get_node_id("variable", cursor_data["spelling"])
            
            # Link variable to its file
            if file_id is not None:
                self._add_edge(file_id, node_id, "defines")
            
            # Process variable type
            if "type" in cursor_data:
                type_id = self._get_node_id("type", cursor_data["type"])
                self._add_edge(node_id, type_id, "has_type")
        
        elif kind == "FIELD_DECL":
            # Create field node
            node_id = self._get_node_id("field", cursor_data["spelling"])
            
            # Look for parent struct/class
            if cursor_data["parent_id"]:
                # Find parent in the AST data
                for file_ast in self.ast_data.values():
                    parent = self._find_node_by_id(file_ast, cursor_data["parent_id"])
                    if parent and parent["kind"] == "STRUCT_DECL":
                        parent_id = self._get_node_id("struct", parent["spelling"])
                        self._add_edge(parent_id, node_id, "has_field")
                        break
        
        # Process includes - only care about "utils.h"
        elif kind == "INCLUSION_DIRECTIVE":
            if file_id is not None and cursor_data["spelling"]:
                # Only include project headers, not system headers with angle brackets
                if not cursor_data["spelling"].startswith('<') and not cursor_data["spelling"].startswith('/usr/include'):
                    included_id = self._get_node_id("file", cursor_data["spelling"])
                    self._add_edge(file_id, included_id, "includes")
        
        # Process children recursively
        for child in cursor_data["children"]:
            self._process_ast_node(child, file_id)
    
    def _find_node_by_id(self, node, node_id):
        """Find a node in the AST by its ID"""
        if node["id"] == node_id:
            return node
        
        for child in node["children"]:
            result = self._find_node_by_id(child, node_id)
            if result:
                return result
        
        return None
    
    def build_knowledge_graph(self):
        """Process the AST JSON and build a code knowledge graph"""
        # Process each file's AST
        for file_path, file_ast in self.ast_data.items():
            # Create a node for the file
            file_id = self._get_node_id("file", file_path)
            
            # Process the file's AST
            self._process_ast_node(file_ast, file_id)
    
    def save_graph(self, output_path: str):
        """Save the knowledge graph to a JSON file formatted for GraphRAG"""
        formatted_data = []
        
        # Format nodes
        for node in self.nodes:
            text = f"{node['type'].capitalize()}: {node['name']}"
            
            # Add more detailed descriptions for different node types
            if node['type'] == 'file':
                # Find what this file defines
                defines = []
                for edge in self.edges:
                    if edge['source'] == node['id'] and edge['type'] == 'defines':
                        target = next((n for n in self.nodes if n['id'] == edge['target']), None)
                        if target:
                            defines.append(f"{target['type']} {target['name']}")
                
                if defines:
                    text += f"\nDefines: {', '.join(defines)}"
            
            elif node['type'] == 'function' or node['type'] == 'method':
                # Find what this function returns
                for edge in self.edges:
                    if edge['source'] == node['id'] and edge['type'] == 'returns':
                        target = next((n for n in self.nodes if n['id'] == edge['target']), None)
                        if target:
                            text += f" returns {target['name']}"
            
            elif node['type'] == 'struct' or node['type'] == 'class':
                # Find fields of this struct/class
                fields = []
                for edge in self.edges:
                    if edge['source'] == node['id'] and edge['type'] == 'has_field':
                        target = next((n for n in self.nodes if n['id'] == edge['target']), None)
                        if target:
                            fields.append(target['name'])
                
                if fields:
                    text += f"\nFields: {', '.join(fields)}"
            
            formatted_node = {
                "id": str(node["id"]),
                "text": text,
                "type": node["type"],
                "name": node["name"]
            }
            formatted_data.append(formatted_node)
        
        # Format edges
        for i, edge in enumerate(self.edges):
            source = next((n for n in self.nodes if n['id'] == edge['source']), None)
            target = next((n for n in self.nodes if n['id'] == edge['target']), None)
            
            if source and target:
                # Create a descriptive text for the relationship
                relation_desc = {
                    "defines": "defines",
                    "includes": "includes",
                    "has_field": "has field",
                    "has_type": "has type",
                    "returns": "returns"
                }.get(edge["type"], edge["type"])
                
                edge_text = f"{source['type']} '{source['name']}' {relation_desc} {target['type']} '{target['name']}'"
                
                formatted_edge = {
                    "id": f"e{i}",
                    "text": edge_text,
                    "source_id": str(edge["source"]),
                    "target_id": str(edge["target"]),
                    "relation": edge["type"]
                }
                formatted_data.append(formatted_edge)
        
        # Save to JSON
        with open(output_path, 'w') as f:
            json.dump(formatted_data, f, indent=2)
        
        print(f"Knowledge graph saved to {output_path}")

def main():
    # Stage 1: Export AST to JSON
    ast_exporter = ASTExporter("compile_commands.json")
    ast_json_path = ast_exporter.export_project_ast("ast_output.json")
    
    # Stage 2: Build knowledge graph from AST, filtering non-project entities
    graph_builder = CodeKnowledgeGraphBuilder(ast_json_path)
    graph_builder.build_knowledge_graph()
    
    # Initialize GraphRAG if not already initialized
    try:
        os.system("graphrag init --root .")
    except Exception as e:
        print(f"Note: GraphRAG initialization failed, but we'll continue: {e}")
        print("This might be because GraphRAG is already initialized.")
    
    # Create the GraphRAG input directory
    os.makedirs("graphrag/input", exist_ok=True)
    
    # Save the graph to GraphRAG input directory
    graph_builder.save_graph("graphrag/input/code_graph.json")
    
    # Configure GraphRAG settings
    # settings = {
    #     "input": {
    #         "format": "json",
    #         "schema": {
    #             "id": "id",
    #             "text": "text"
    #         }
    #     }
    # }
    
    # with open("settings.yaml", 'w') as f:
    #     import yaml
    #     yaml.dump(settings, f)
    
    # Index the graph
    os.system("graphrag index")
    
    print("Code analysis complete. You can now query the graph using:")
    print('graphrag query --query "What functions are defined in this project?"')
    print('graphrag query --query "Show me the structure of the Person struct"')

if __name__ == "__main__":
    main() 