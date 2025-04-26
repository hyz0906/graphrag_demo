# C Code Knowledge Graph Generator

This project demonstrates how to generate a knowledge graph from C source code using Clang and GraphRAG.

## Project Structure

```
.
├── src/
│   ├── main.c
│   ├── utils.c
│   └── utils.h
├── Makefile
├── code_analyzer.py
├── requirements.txt
└── README.md
```

## Prerequisites

1. Install Clang and libclang:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install clang libclang-dev
   
   # For Ubuntu 24.04 (which uses Clang 18)
   sudo apt-get install clang-18 libclang-18-dev
   
   # macOS
   brew install llvm
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install GraphRAG:
   ```bash
   pip install graphrag
   ```

4. If you encounter libclang errors:
   - The code_analyzer.py script will try to automatically find the libclang library
   - If it fails, you can manually set the path by editing the script:
     ```python
     # Add this before creating the Index
     Config.set_library_file('/path/to/libclang.so')
     ```
   - Common paths for libclang:
     - Ubuntu 24.04: `/usr/lib/x86_64-linux-gnu/libclang-18.so`
     - Ubuntu 22.04: `/usr/lib/x86_64-linux-gnu/libclang-14.so`
     - Other systems: Check with `ldconfig -p | grep libclang`

## Building the C Project

1. Generate the compilation database:
   ```bash
   make compile_commands.json
   ```

2. Build the project:
   ```bash
   make
   ```

## Generating the Knowledge Graph

1. Run the code analyzer:
   ```bash
   python code_analyzer.py
   ```

2. The script will:
   - Initialize GraphRAG
   - Analyze the C code
   - Generate a knowledge graph
   - Save it to `graphrag/input/code_graph.json`
   - Configure GraphRAG settings
   - Index the graph

## Querying the Knowledge Graph

You can query the knowledge graph using the GraphRAG CLI:

```bash
graphrag query --method local --query "your query here"
```

Example queries:
- "What functions are called by main?"
- "What types are used in the Person struct?"
- "Show me all function definitions"

## Graph Structure

The generated graph contains:

- Nodes:
  - Functions
  - Structs
  - Types

- Edges:
  - "calls": Function calls
  - "contains": Struct/function containment
  - "uses": Type usage

## Local LLM Configuration

The project is configured to use a local LLM (Mistral 7B). To use a different model:

1. Edit `graphrag/settings.yaml`
2. Update the `llm` section with your preferred model and API settings 