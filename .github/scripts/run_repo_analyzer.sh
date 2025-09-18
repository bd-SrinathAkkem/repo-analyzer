#!/bin/bash

# Universal AI-Powered Repository Analyzer Runner for CI/CD
# Runs repo_analyzer.py, processes results, and installs detected technologies
# Usage: ./run_repo_analyzer.sh <github_repo_url> [model] [config_file]

set -e

# Default parameters
REPO_URL="${1:-$REPO_URL}"
MODEL="${2:-$MODEL:-claude-sonnet}"
CONFIG_FILE="${3:-$CONFIG_FILE}"
OUTPUT_DIR="${OUTPUT_DIR:-./output}"
LOG_FILE="${LOG_FILE:-scan.log}"

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Initialize logging
mkdir -p logs
chmod -R u+rw logs
log "Starting repository analysis"
log "Parameters: REPO_URL=$REPO_URL, MODEL=$MODEL, CONFIG_FILE=$CONFIG_FILE"

# Validate input
if [ -z "$REPO_URL" ]; then
    log "ERROR: REPO_URL is required"
    exit 1
fi

# Check Python 3.8+
if ! command -v python3.12 >/dev/null 2>&1; then
    log "Python 3.12 not found. Trying python3..."
    PYTHON_CMD=python3
    if ! command -v python3 >/dev/null 2>&1 || ! python3 --version | grep -q "3.[89]\|3.1[0-2]"; then
        log "ERROR: Python 3.8+ required"
        exit 1
    fi
else
    PYTHON_CMD=python3.12
fi
log "Using Python: $($PYTHON_CMD --version)"

# Set up virtual environment
VENV_DIR="$HOME/.venv_analyzer"
if [ ! -d "$VENV_DIR" ]; then
    log "Creating virtual environment at $VENV_DIR..."
    $PYTHON_CMD -m venv "$VENV_DIR"
    chmod -R u+rw "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# Install Python dependencies
REQUIRED_PACKAGES=("requests>=2.31.0" "openai>=1.0.0" "toml>=0.10.2" "PyYAML>=6.0")
for pkg in "${REQUIRED_PACKAGES[@]}"; do
    if ! pip show "$(echo "$pkg" | cut -d'>' -f1)" >/dev/null 2>&1; then
        log "Installing $pkg..."
        pip install --user "$pkg"
    else
        log "$pkg already installed"
    fi
done

# Verify API keys
API_KEYS=("ANTHROPIC_API_KEY" "OPENAI_API_KEY" "GOOGLE_API_KEY")
API_KEY_SET=false
for key in "${API_KEYS[@]}"; do
    if [ -n "${!key}" ]; then
        API_KEY_SET=true
        log "$key is set"
    fi
done
if [ "$API_KEY_SET" = false ]; then
    log "ERROR: At least one API key required"
    exit 2
fi
[ -z "$GITHUB_TOKEN" ] && log "WARNING: GITHUB_TOKEN not set"

# Ensure analyzer script exists
SCRIPT_NAME="repo_analyzer.py"
if [ ! -f "$SCRIPT_NAME" ]; then
    log "Downloading $SCRIPT_NAME..."
    curl -sSL "https://raw.githubusercontent.com/SrinathAkkem/repo-analyzer/main/repo_analyzer.py" -o "$SCRIPT_NAME"
    chmod u+x "$SCRIPT_NAME"
else
    chmod u+rw "$SCRIPT_NAME"
    log "$SCRIPT_NAME found"
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"
chmod -R u+rw "$OUTPUT_DIR"
log "Output directory: $OUTPUT_DIR"

# Run analyzer
log "Running analyzer for $REPO_URL..."
CMD="$PYTHON_CMD $SCRIPT_NAME $REPO_URL $MODEL"
[ -n "$CONFIG_FILE" ] && CMD="$CMD $CONFIG_FILE"
if ! $CMD; then
    log "ERROR: Analysis failed"
    exit 3
fi

# Process and install technologies from results
OUTPUT_FILE=$(find "$OUTPUT_DIR" -name "*_latest.json" -type f | head -n 1)
if [ -f "$OUTPUT_FILE" ]; then
    chmod u+rw "$OUTPUT_FILE"
    log "Results: $OUTPUT_FILE"
    log "=== ANALYSIS SUMMARY ==="
    jq -r '.repository_analysis | "Architecture: \(.architecture_type)\nPrimary Tech: \(.primary_technology)\nTechnologies: \(.technology_stack | join(", "))"' "$OUTPUT_FILE" | tee -a "$LOG_FILE"
    log "=== COMMANDS ==="
    jq -r '.commands | to_entries | .[] | select(.value != "N/A") | "\(.key): \(.value)"' "$OUTPUT_FILE" | tee -a "$LOG_FILE"
    log "===================="

    # Extract technologies and build tools
    TECHNOLOGIES=$(jq -r '.repository_analysis.technology_stack[]' "$OUTPUT_FILE")
    PACKAGE_MANAGERS=$(jq -r '.build_ecosystem.package_managers[]' "$OUTPUT_FILE")
    BUILD_TOOLS=$(jq -r '.build_ecosystem.build_tools[], .build_ecosystem.bundlers[]' "$OUTPUT_FILE")

    # Install Java-related tools
    if echo "$TECHNOLOGIES" | grep -qi "java"; then
        log "Installing Java (JDK 17) and Maven..."
        if ! command -v java >/dev/null 2>&1; then
            apt-get update
            apt-get install -y openjdk-17-jdk
        fi
        if ! command -v mvn >/dev/null 2>&1 && echo "$PACKAGE_MANAGERS" | grep -qi "maven"; then
            apt-get install -y maven
        fi
        log "Java: $(java -version 2>&1 | head -n 1)"
        [ -n "$(command -v mvn)" ] && log "Maven: $(mvn -version | head -n 1)"
    fi

    # Install Node.js-related tools
    if echo "$TECHNOLOGIES" | grep -qi "javascript\|typescript\|node.js"; then
        log "Installing Node.js 20 and npm..."
        if ! command -v node >/dev/null 2>&1; then
            curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
            apt-get install -y nodejs
        fi
        log "Node.js: $(node --version)"
        log "npm: $(npm --version)"
        if echo "$PACKAGE_MANAGERS" | grep -qi "yarn"; then
            log "Installing Yarn..."
            npm install -g yarn
            log "Yarn: $(yarn --version)"
        fi
        if echo "$BUILD_TOOLS" | grep -qi "webpack"; then
            log "Installing Webpack..."
            npm install -g webpack webpack-cli
        fi
        if echo "$BUILD_TOOLS" | grep -qi "vite"; then
            log "Installing Vite..."
            npm install -g vite
        fi
    fi

    # Install Python-related tools
    if echo "$TECHNOLOGIES" | grep -qi "python" && echo "$PACKAGE_MANAGERS" | grep -qi "pip"; then
        log "Installing additional Python tools (if specified)..."
        # Example: Install pytest if tests are detected
        if jq -r '.features.has_tests' "$OUTPUT_FILE" | grep -qi "true"; then
            pip install --user pytest
            log "pytest installed"
        fi
    fi

    # Install Go-related tools
    if echo "$TECHNOLOGIES" | grep -qi "go"; then
        log "Installing Go..."
        if ! command -v go >/dev/null 2>&1; then
            curl -fsSL https://golang.org/dl/go1.23.0.linux-amd64.tar.gz | tar -C /usr/local -xz
            export PATH=$PATH:/usr/local/go/bin
        fi
        log "Go: $(go version)"
    fi

    # Install Rust-related tools
    if echo "$TECHNOLOGIES" | grep -qi "rust"; then
        log "Installing Rust..."
        if ! command -v rustc >/dev/null 2>&1; then
            curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
            source "$HOME/.cargo/env"
        fi
        log "Rust: $(rustc --version)"
        if echo "$PACKAGE_MANAGERS" | grep -qi "cargo"; then
            log "Cargo: $(cargo --version)"
        fi
    fi

else
    log "WARNING: No output found in $OUTPUT_DIR"
fi

log "Scan complete"
exit 0
