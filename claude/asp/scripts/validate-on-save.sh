#!/bin/bash
# PostToolUse hook: Auto-validate ASP files after modification
# Triggers on Write|Edit of asp.yaml or universes/*.yaml

# Read JSON input from stdin
input=$(cat)

# Extract the file path that was modified
file_path=$(echo "$input" | jq -r '.tool_input.file_path // .tool_response.filePath // empty')

# Exit silently if no file path
if [ -z "$file_path" ]; then
    exit 0
fi

# Get the filename
filename=$(basename "$file_path")
dirpath=$(dirname "$file_path")
dirname=$(basename "$dirpath")

# Check if this is an ASP-related file
is_asp_file=false

# Check for asp.yaml (main analysis file)
if [ "$filename" = "asp.yaml" ]; then
    is_asp_file=true
    file_type="analysis"
fi

# Check for universe files (in universes/ directory)
if [ "$dirname" = "universes" ] && [[ "$filename" == *.yaml ]]; then
    is_asp_file=true
    file_type="universe"
fi

# Exit if not an ASP file
if [ "$is_asp_file" = false ]; then
    exit 0
fi

# Find the project root (where asp.yaml lives)
if [ "$file_type" = "analysis" ]; then
    project_root="$dirpath"
else
    # For universe files, go up one level
    project_root=$(dirname "$dirpath")
fi

# Check if asp command is available
if ! command -v asp &> /dev/null; then
    # ASP CLI not installed, skip validation
    exit 0
fi

# Run validation
cd "$project_root" 2>/dev/null || exit 0

if [ "$file_type" = "analysis" ]; then
    result=$(asp validate asp.yaml 2>&1)
    exit_code=$?
else
    result=$(asp validate "$file_path" 2>&1)
    exit_code=$?
fi

# Prepare response
if [ $exit_code -eq 0 ]; then
    # Validation passed
    echo "{\"hookSpecificOutput\": {\"hookEventName\": \"PostToolUse\", \"additionalContext\": \"ASP validation passed for $filename\"}}"
else
    # Validation failed - provide context to Claude
    # Escape the result for JSON (jq -Rs . adds quotes, so use it directly)
    escaped_result=$(echo "ASP validation FAILED for $filename:\n$result" | jq -Rs .)
    echo "{\"hookSpecificOutput\": {\"hookEventName\": \"PostToolUse\", \"additionalContext\": $escaped_result}}"
fi

exit 0
