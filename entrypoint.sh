#!/bin/bash

# GitHub Action entrypoint script
set -e

# Set up logging
LOG_FILE="/tmp/action.log"
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "Starting AI Repository Analyzer GitHub Action"

# Validate required inputs
if [ -z "$REPO_URL" ]; then
    log "ERROR: repo_url input is required"
    exit 1
fi

# Set defaults
MODEL="${MODEL:-claude-sonnet}"
OUTPUT_DIR="/tmp/output"

# Check API key
if [ -z "$AI_API_KEY" ]; then
    log "ERROR: AI_API_KEY is required for all AI providers"
    exit 1
fi

export AI_API_KEY
log "Universal AI API key provided"

# Set GitHub token if provided
if [ -n "$GITHUB_TOKEN" ]; then
    export GITHUB_TOKEN
    log "GitHub token provided"
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"
export OUTPUT_DIR

log "Running full analysis for: $REPO_URL with model: $MODEL"

# Run the full analyzer script (includes dependency installation and build execution)
CMD="/action/run_repo_analyzer.sh \"$REPO_URL\" \"$MODEL\""
if [ -n "$CONFIG_FILE" ]; then
    CMD="$CMD \"$CONFIG_FILE\""
fi

if ! eval $CMD; then
    log "ERROR: Repository analysis failed"
    exit 1
fi

# Find the output file
OUTPUT_FILE=$(find "$OUTPUT_DIR" -name "*_latest.json" -type f | head -n 1)
if [ -z "$OUTPUT_FILE" ]; then
    OUTPUT_FILE=$(find /action -name "*_latest.json" -type f | head -n 1)
fi

if [ -f "$OUTPUT_FILE" ]; then
    log "Analysis completed. Output file: $OUTPUT_FILE"

    # Set GitHub Action outputs
    echo "analysis_file=$OUTPUT_FILE" >> $GITHUB_OUTPUT

    # Extract and set additional outputs
    TECHNOLOGIES=$(jq -r '.repository_analysis.technology_stack | join(",")' "$OUTPUT_FILE" 2>/dev/null || echo "")
    ARCHITECTURE=$(jq -r '.repository_analysis.architecture_type // "unknown"' "$OUTPUT_FILE" 2>/dev/null || echo "unknown")
    BUILD_COMMANDS=$(jq -c '.commands // {}' "$OUTPUT_FILE" 2>/dev/null || echo "{}")

    echo "technologies=$TECHNOLOGIES" >> $GITHUB_OUTPUT
    echo "architecture=$ARCHITECTURE" >> $GITHUB_OUTPUT
    echo "build_commands<<EOF" >> $GITHUB_OUTPUT
    echo "$BUILD_COMMANDS" >> $GITHUB_OUTPUT
    echo "EOF" >> $GITHUB_OUTPUT

    # Display summary
    log "=== ANALYSIS SUMMARY ==="
    jq -r '.repository_analysis | "Architecture: \(.architecture_type)\nPrimary Technology: \(.primary_technology)\nTechnologies: \(.technology_stack | join(", "))"' "$OUTPUT_FILE" || log "Could not parse analysis summary"

    log "Action completed successfully"
else
    log "ERROR: No analysis output file found"
    exit 1
fi