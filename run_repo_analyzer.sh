#!/bin/bash

# Universal AI-Powered Repository Analyzer Runner for CI/CD
# Runs repo_analyzer.py, processes results, and installs detected technologies
# Usage: ./run_repo_analyzer.sh <github_repo_url> [model] [config_file]
# Supports both macOS (with Homebrew) and Linux (Ubuntu/Debian) environments

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

# Log execution context
[ -n "$GITHUB_WORKSPACE" ] && log "GitHub Actions: $GITHUB_WORKSPACE" || log "Local: $(pwd)"

# Validate input
if [ -z "$REPO_URL" ]; then
    log "ERROR: REPO_URL is required"
    exit 1
fi

# Detect OS and set up package manager
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux - assume Ubuntu/Debian in Docker
    OS_TYPE="linux"
    log "Detected Linux environment"

    # Update package manager (only if running as root or with sudo)
    if command -v apt-get >/dev/null 2>&1; then
        if [ "$EUID" -eq 0 ]; then
            apt-get update -qq
            PACKAGE_INSTALL="apt-get install -y"
        elif command -v sudo >/dev/null 2>&1; then
            sudo apt-get update -qq
            PACKAGE_INSTALL="sudo apt-get install -y"
        else
            log "WARNING: Cannot install packages - no root access or sudo"
            PACKAGE_INSTALL="echo 'Package install not available (no sudo):'"
        fi
    elif command -v yum >/dev/null 2>&1; then
        if [ "$EUID" -eq 0 ]; then
            PACKAGE_INSTALL="yum install -y"
        elif command -v sudo >/dev/null 2>&1; then
            PACKAGE_INSTALL="sudo yum install -y"
        else
            PACKAGE_INSTALL="echo 'Package install not available (no sudo):'"
        fi
    else
        log "WARNING: No supported package manager found"
        PACKAGE_INSTALL="echo 'Package install not available:'"
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    OS_TYPE="macos"
    log "Detected macOS environment"

    # Check for Homebrew
    if ! command -v brew >/dev/null 2>&1; then
        log "Homebrew not found. Attempting to install..."
        if command -v curl >/dev/null 2>&1; then
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || log "Homebrew installation failed"
            # Try to source brew paths
            if [ -f "/opt/homebrew/bin/brew" ]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            elif [ -f "/usr/local/bin/brew" ]; then
                eval "$(/usr/local/bin/brew shellenv)"
            fi
        else
            log "WARNING: curl not available, cannot install Homebrew"
        fi
    fi

    if command -v brew >/dev/null 2>&1; then
        log "Homebrew: $(brew --version | head -n 1)"
        PACKAGE_INSTALL="brew install"
    else
        log "WARNING: Homebrew not available, package installation will be limited"
        PACKAGE_INSTALL="echo 'Homebrew not available:'"
    fi
else
    OS_TYPE="unknown"
    log "WARNING: Unknown OS type: $OSTYPE"
    PACKAGE_INSTALL="echo 'Package install not available:'"
fi

# Check Python 3.8+
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD=python3
    PYTHON_VERSION=$(python3 --version 2>&1 | grep -o '[0-9]\+\.[0-9]\+')
    log "Found Python: $(python3 --version)"
else
    log "Python 3 not found, attempting installation..."
    if [ "$OS_TYPE" = "linux" ]; then
        $PACKAGE_INSTALL python3 python3-pip python3-venv
        PYTHON_CMD=python3
    elif [ "$OS_TYPE" = "macos" ]; then
        $PACKAGE_INSTALL python@3.12
        PYTHON_CMD=python3.12
    else
        log "ERROR: Cannot install Python on unknown OS"
        exit 1
    fi
fi

# Ensure pip is available
if ! command -v pip3 >/dev/null 2>&1 && ! $PYTHON_CMD -m pip --version >/dev/null 2>&1; then
    log "pip not found, attempting installation..."
    if [ "$OS_TYPE" = "linux" ]; then
        $PACKAGE_INSTALL python3-pip
    fi
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
        pip install "$pkg"
    else
        log "$pkg already installed"
    fi
done

# Install jq
if ! command -v jq >/dev/null 2>&1; then
    log "Installing jq..."
    if [ "$OS_TYPE" = "linux" ]; then
        $PACKAGE_INSTALL jq
    elif [ "$OS_TYPE" = "macos" ]; then
        $PACKAGE_INSTALL jq
    else
        log "WARNING: Cannot install jq on unknown OS"
    fi
fi
if command -v jq >/dev/null 2>&1; then
    log "jq: $(jq --version)"
else
    log "WARNING: jq not available"
fi

# Verify API key
if [ -z "$AI_API_KEY" ]; then
    log "ERROR: AI_API_KEY is required for all AI providers"
    exit 2
fi
log "Universal AI_API_KEY is set"
[ -z "$GITHUB_TOKEN" ] && log "WARNING: GITHUB_TOKEN not set"

# Ensure analyzer script exists
SCRIPT_NAME="repo_analyzer.py"
if [ ! -f "$SCRIPT_NAME" ]; then
    log "Downloading $SCRIPT_NAME..."
    curl -sSL "https://raw.githubusercontent.com/bd-SrinathAkkem/repo-analyzer/main/repo_analyzer.py" -o "$SCRIPT_NAME"
    chmod u+x "$SCRIPT_NAME"
else
    chmod u+rw "$SCRIPT_NAME"
    log "$SCRIPT_NAME found"
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"
chmod -R u+rw "$OUTPUT_DIR"
log "Output directory: $OUTPUT_DIR"

# Setup repository directory
setup_repo() {
    if [ -n "$GITHUB_WORKSPACE" ]; then
        REPO_DIR="$GITHUB_WORKSPACE"
        log "Using workspace: $REPO_DIR"
        return
    fi

    REPO_NAME=$(basename "$REPO_URL" .git)
    REPO_OWNER=$(echo "$REPO_URL" | sed 's|.*/\([^/]*\)/[^/]*$|\1|')
    REPO_DIR="./repos/$REPO_OWNER/$REPO_NAME"

    if [ -d "$REPO_DIR" ]; then
        [ -d "$REPO_DIR/.git" ] && (cd "$REPO_DIR" && git pull --quiet 2>/dev/null) || true
        return
    fi

    mkdir -p "./repos/$REPO_OWNER"
    if ! command -v git >/dev/null 2>&1; then
        $PACKAGE_INSTALL git || { log "Failed to install git"; REPO_DIR=""; return; }
    fi

    if git clone --quiet "$REPO_URL" "$REPO_DIR" 2>/dev/null; then
        log "✓ Repository cloned: $REPO_DIR"
    else
        log "WARNING: Clone failed, build commands may not work"
        REPO_DIR=""
    fi
}

setup_repo

# Run analyzer
log "Running analyzer for $REPO_URL..."
CMD="$PYTHON_CMD $SCRIPT_NAME $REPO_URL $MODEL"
[ -n "$CONFIG_FILE" ] && CMD="$CMD $CONFIG_FILE"
if ! $CMD; then
    log "ERROR: Analysis failed"
    exit 3
fi

# Process and install technologies from results
# First check in the OUTPUT_DIR
OUTPUT_FILE=$(find "$OUTPUT_DIR" -name "*_latest.json" -type f | head -n 1)

# If not found, check in owner-named directories (how repo_analyzer.py saves files)
if [ -z "$OUTPUT_FILE" ]; then
    # Try to find in any subdirectory
    OUTPUT_FILE=$(find . -name "*_latest.json" -type f | head -n 1)
fi
if [ -f "$OUTPUT_FILE" ]; then
    chmod u+rw "$OUTPUT_FILE"
    log "Results: $OUTPUT_FILE"
    log "=== ANALYSIS SUMMARY ==="
    jq -r '.repository_analysis | "Architecture: \(.architecture_type)\nPrimary Tech: \(.primary_technology)\nTechnologies: \(.technology_stack | join(", "))"' "$OUTPUT_FILE" | tee -a "$LOG_FILE"

    # Extract technologies and build tools with null handling
    TECHNOLOGIES=$(jq -r '.repository_analysis.technology_stack[]?' "$OUTPUT_FILE")
    PACKAGE_MANAGERS=$(jq -r '.build_ecosystem.package_managers[]? // empty' "$OUTPUT_FILE")
    BUILD_TOOLS=$(jq -r '(.build_ecosystem.build_tools[]? // empty), (.build_ecosystem.bundlers[]? // empty)' "$OUTPUT_FILE")

    # Extract and display build commands
    log "=== EXTRACTED BUILD COMMANDS ==="

    # Parse key commands and store them
    CLEAN_INSTALL_CMD=$(jq -r '.commands.clean_install // empty' "$OUTPUT_FILE")
    INSTALL_CMD=$(jq -r '.commands.install_dependencies // empty' "$OUTPUT_FILE")
    BUILD_DEV_CMD=$(jq -r '.commands.build_development // empty' "$OUTPUT_FILE")
    BUILD_PROD_CMD=$(jq -r '.commands.build_production // empty' "$OUTPUT_FILE")
    START_DEV_CMD=$(jq -r '.commands.start_development // empty' "$OUTPUT_FILE")




    # Universal runtime installer
    install_runtime() {
        local lang="$1" version="$2" extra="$3"
        [ -z "$version" ] || [ "$version" = "null" ] || [ "$version" = "latest" ] && return

        if command -v "${lang}" >/dev/null 2>&1 || command -v "${lang}c" >/dev/null 2>&1 || command -v "${lang}3" >/dev/null 2>&1; then
            return  # Already installed, skip version check for optimization
        fi

        case "$lang" in
            "node")
                if [ "$OS_TYPE" = "macos" ]; then
                    $PACKAGE_INSTALL "node@${version%%.*}" 2>/dev/null || $PACKAGE_INSTALL node
                    [ -d "/opt/homebrew/opt/node@${version%%.*}/bin" ] && export PATH="/opt/homebrew/opt/node@${version%%.*}/bin:$PATH"
                else
                    case "${version%%.*}" in
                        16|18|20) curl -fsSL "https://deb.nodesource.com/setup_${version%%.*}.x" | bash - 2>/dev/null ;;
                    esac
                    $PACKAGE_INSTALL nodejs
                fi
                [ -n "$extra" ] && npm install -g "npm@$extra" 2>/dev/null
                ;;
            "python")
                if [ "$OS_TYPE" = "macos" ]; then
                    $PACKAGE_INSTALL "python@$version" 2>/dev/null || $PACKAGE_INSTALL python
                    [ -d "/opt/homebrew/opt/python@$version/bin" ] && export PATH="/opt/homebrew/opt/python@$version/bin:$PATH"
                else
                    $PACKAGE_INSTALL "python$version" "python$version-pip" "python$version-venv" 2>/dev/null
                fi
                ;;
            "java")
                if [ "$OS_TYPE" = "macos" ]; then
                    $PACKAGE_INSTALL "openjdk@$version" 2>/dev/null || $PACKAGE_INSTALL openjdk
                    [ -d "/opt/homebrew/opt/openjdk@$version/bin" ] && export PATH="/opt/homebrew/opt/openjdk@$version/bin:$PATH"
                else
                    $PACKAGE_INSTALL "openjdk-$version-jdk" 2>/dev/null
                fi
                ;;
            "go")
                if [ "$OS_TYPE" = "macos" ]; then
                    $PACKAGE_INSTALL go
                else
                    ARCH=$(uname -m); [ "$ARCH" = "x86_64" ] && ARCH="amd64"; [ "$ARCH" = "aarch64" ] && ARCH="arm64"
                    curl -L "https://go.dev/dl/go${version}.linux-${ARCH}.tar.gz" -o /tmp/go.tar.gz 2>/dev/null && \
                    tar -C /usr/local -xzf /tmp/go.tar.gz 2>/dev/null && rm -f /tmp/go.tar.gz && export PATH="/usr/local/go/bin:$PATH"
                fi
                ;;
            "rust")
                curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y 2>/dev/null
                export PATH="$HOME/.cargo/bin:$PATH"
                ;;
            "dotnet")
                if [ "$OS_TYPE" = "macos" ]; then
                    $PACKAGE_INSTALL dotnet
                else
                    curl -sSL https://dot.net/v1/dotnet-install.sh | bash /dev/stdin --version "$version" 2>/dev/null
                    export PATH="$HOME/.dotnet:$PATH"
                fi
                ;;
            "php")
                if [ "$OS_TYPE" = "macos" ]; then
                    $PACKAGE_INSTALL "php@$version" 2>/dev/null || $PACKAGE_INSTALL php
                    [ -d "/opt/homebrew/opt/php@$version/bin" ] && export PATH="/opt/homebrew/opt/php@$version/bin:$PATH"
                else
                    $PACKAGE_INSTALL php php-cli php-common
                fi
                command -v php >/dev/null 2>&1 && ! command -v composer >/dev/null 2>&1 && \
                curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer 2>/dev/null
                ;;
            "ruby")
                if [ "$OS_TYPE" = "macos" ]; then
                    $PACKAGE_INSTALL "ruby@$version" 2>/dev/null || $PACKAGE_INSTALL ruby
                    [ -d "/opt/homebrew/opt/ruby@$version/bin" ] && export PATH="/opt/homebrew/opt/ruby@$version/bin:$PATH"
                else
                    $PACKAGE_INSTALL ruby ruby-dev
                fi
                command -v gem >/dev/null 2>&1 && gem install bundler 2>/dev/null
                ;;
        esac
    }

    # Universal build wrapper and tool detection function
    fix_build_wrapper() {
        local cmd="$1"
        local fixed_cmd="$cmd"

        # Java Build Tools
        # Handle missing Maven wrapper
        if echo "$cmd" | grep -q "./mvnw" && [ ! -f "./mvnw" ]; then
            log "⚠️ Maven wrapper (mvnw) not found, using system Maven" >&2
            fixed_cmd=$(echo "$cmd" | sed 's|./mvnw|mvn|g')
            ensure_tool_available "mvn" "maven"
        fi

        # Handle missing Gradle wrapper
        if echo "$cmd" | grep -q "./gradlew" && [ ! -f "./gradlew" ]; then
            log "⚠️ Gradle wrapper (gradlew) not found, using system Gradle" >&2
            fixed_cmd=$(echo "$cmd" | sed 's|./gradlew|gradle|g')
            ensure_tool_available "gradle" "gradle"
        fi

        # Node.js Package Managers
        # Handle yarn vs npm
        if echo "$cmd" | grep -q "yarn " && ! command -v yarn >/dev/null 2>&1; then
            if [ -f "package-lock.json" ]; then
                log "⚠️ Yarn not available but package-lock.json found, using npm" >&2
                fixed_cmd=$(echo "$cmd" | sed 's|yarn |npm |g' | sed 's|yarn$|npm|g')
            else
                ensure_tool_available "yarn" "yarn"
            fi
        fi

        # Handle pnpm
        if echo "$cmd" | grep -q "pnpm " && ! command -v pnpm >/dev/null 2>&1; then
            if [ -f "package-lock.json" ]; then
                log "⚠️ pnpm not available, using npm" >&2
                fixed_cmd=$(echo "$cmd" | sed 's|pnpm |npm |g')
            elif [ -f "yarn.lock" ]; then
                log "⚠️ pnpm not available, using yarn" >&2
                fixed_cmd=$(echo "$cmd" | sed 's|pnpm |yarn |g')
            else
                log "Installing pnpm..." >&2
                if command -v npm >/dev/null 2>&1; then
                    npm install -g pnpm 2>/dev/null || log "Failed to install pnpm" >&2
                fi
            fi
        fi

        # Python Package Managers
        # Handle poetry
        if echo "$cmd" | grep -q "poetry " && ! command -v poetry >/dev/null 2>&1; then
            if [ -f "requirements.txt" ]; then
                log "⚠️ Poetry not available, using pip with requirements.txt" >&2
                fixed_cmd=$(echo "$cmd" | sed 's|poetry install|pip install -r requirements.txt|g')
            else
                ensure_tool_available "poetry" "poetry"
            fi
        fi

        # Handle pipenv
        if echo "$cmd" | grep -q "pipenv " && ! command -v pipenv >/dev/null 2>&1; then
            if [ -f "requirements.txt" ]; then
                log "⚠️ Pipenv not available, using pip with requirements.txt" >&2
                fixed_cmd=$(echo "$cmd" | sed 's|pipenv install|pip install -r requirements.txt|g')
            else
                ensure_tool_available "pipenv" "pipenv"
            fi
        fi

        # Go Module handling
        if echo "$cmd" | grep -q "go " && ! command -v go >/dev/null 2>&1; then
            ensure_tool_available "go" "go"
        fi

        # Rust/Cargo handling
        if echo "$cmd" | grep -q "cargo " && ! command -v cargo >/dev/null 2>&1; then
            ensure_tool_available "cargo" "rust"
        fi

        # .NET handling
        if echo "$cmd" | grep -q "dotnet " && ! command -v dotnet >/dev/null 2>&1; then
            ensure_tool_available "dotnet" "dotnet"
        fi

        # PHP Composer handling
        if echo "$cmd" | grep -q "composer " && ! command -v composer >/dev/null 2>&1; then
            ensure_tool_available "composer" "composer"
        fi

        # Ruby Bundler handling
        if echo "$cmd" | grep -q "bundle " && ! command -v bundle >/dev/null 2>&1; then
            if command -v gem >/dev/null 2>&1; then
                gem install bundler 2>/dev/null || log "Failed to install bundler" >&2
            else
                ensure_tool_available "ruby" "ruby"
            fi
        fi

        echo "$fixed_cmd"
    }

    # Helper function to ensure a tool is available
    ensure_tool_available() {
        local tool="$1"
        local package="$2"

        if ! command -v "$tool" >/dev/null 2>&1; then
            log "Installing $tool..." >&2
            if [ "$OS_TYPE" = "macos" ]; then
                $PACKAGE_INSTALL "$package" || log "Failed to install $package" >&2
            elif [ "$OS_TYPE" = "linux" ]; then
                $PACKAGE_INSTALL "$package" || log "Failed to install $package" >&2
            fi
        fi
    }

    # Execute extracted build commands
    log "=== EXECUTING BUILD COMMANDS ==="

    # Validate repository directory
    if [ -n "$REPO_DIR" ] && [ -d "$REPO_DIR" ]; then
        log "✓ Repository: $REPO_DIR"
    else
        log "⚠️ No repository directory, using: $(pwd)"
    fi

    # Check if we have analysis results with specific version requirements
    if command -v jq >/dev/null 2>&1 && [ -f "$OUTPUT_FILE" ]; then
        log "🔍 Checking version requirements from analysis..."

        # Extract version requirements for all languages
        REQUIRED_JAVA_VERSION=$(jq -r '.environment_requirements.runtime_versions.java // empty' "$OUTPUT_FILE")
        REQUIRED_NODE_VERSION=$(jq -r '.environment_requirements.runtime_versions.node // empty' "$OUTPUT_FILE")
        REQUIRED_NPM_VERSION=$(jq -r '.environment_requirements.runtime_versions.npm // empty' "$OUTPUT_FILE")
        REQUIRED_PYTHON_VERSION=$(jq -r '.environment_requirements.runtime_versions.python // empty' "$OUTPUT_FILE")
        REQUIRED_GO_VERSION=$(jq -r '.environment_requirements.runtime_versions.go // empty' "$OUTPUT_FILE")
        REQUIRED_RUST_VERSION=$(jq -r '.environment_requirements.runtime_versions.rust // empty' "$OUTPUT_FILE")
        REQUIRED_DOTNET_VERSION=$(jq -r '.environment_requirements.runtime_versions.dotnet // empty' "$OUTPUT_FILE")
        REQUIRED_PHP_VERSION=$(jq -r '.environment_requirements.runtime_versions.php // empty' "$OUTPUT_FILE")
        REQUIRED_RUBY_VERSION=$(jq -r '.environment_requirements.runtime_versions.ruby // empty' "$OUTPUT_FILE")

        # Install required versions only for detected languages
        log "🔧 Analyzing detected technologies: $(echo "$TECHNOLOGIES" | tr '\n' ' ')"
        log "📦 Package managers found: $(echo "$PACKAGE_MANAGERS" | tr '\n' ' ')"
        log "🛠️ Installing only required language runtimes and tools..."

        # Install detected runtimes
        log "🔧 Installing required runtimes..."
        case "$TECHNOLOGIES $PACKAGE_MANAGERS" in
            *java*) install_runtime "java" "$REQUIRED_JAVA_VERSION" ;;
        esac
        case "$TECHNOLOGIES $PACKAGE_MANAGERS" in
            *javascript*|*typescript*|*node*|*npm*|*yarn*|*pnpm*) install_runtime "node" "$REQUIRED_NODE_VERSION" "$REQUIRED_NPM_VERSION" ;;
        esac
        case "$TECHNOLOGIES $PACKAGE_MANAGERS" in
            *python*|*pip*|*poetry*|*pipenv*) install_runtime "python" "$REQUIRED_PYTHON_VERSION" ;;
        esac
        case "$TECHNOLOGIES $PACKAGE_MANAGERS" in
            *go*|*golang*|*"go mod"*|*go-mod*) install_runtime "go" "$REQUIRED_GO_VERSION" ;;
        esac
        case "$TECHNOLOGIES $PACKAGE_MANAGERS" in
            *rust*|*cargo*) install_runtime "rust" "$REQUIRED_RUST_VERSION" ;;
        esac
        case "$TECHNOLOGIES $PACKAGE_MANAGERS" in
            *.net*|*c#*|*f#*|*csharp*|*fsharp*|*dotnet*|*nuget*) install_runtime "dotnet" "$REQUIRED_DOTNET_VERSION" ;;
        esac
        case "$TECHNOLOGIES $PACKAGE_MANAGERS" in
            *php*|*composer*) install_runtime "php" "$REQUIRED_PHP_VERSION" ;;
        esac
        case "$TECHNOLOGIES $PACKAGE_MANAGERS" in
            *ruby*|*gem*|*bundler*) install_runtime "ruby" "$REQUIRED_RUBY_VERSION" ;;
        esac

        # Check for build files and attempt to create missing wrappers
        HAS_MAVEN_WRAPPER=$(jq -r '.environment_requirements.build_files_available.has_maven_wrapper // false' "$OUTPUT_FILE")
        POM_LOCATION=$(jq -r '.environment_requirements.build_files_available.maven_pom_location // empty' "$OUTPUT_FILE")

        # Generate missing build wrappers
        generate_wrappers() {
            local orig_dir=$(pwd)
            [ -n "$REPO_DIR" ] && [ -d "$REPO_DIR" ] && cd "$REPO_DIR"

            # Maven wrapper
            if [ -f "pom.xml" ] && [ ! -f "./mvnw" ] && command -v mvn >/dev/null 2>&1; then
                mvn -N wrapper:wrapper 2>/dev/null && chmod +x ./mvnw 2>/dev/null && log "✓ Generated mvnw"
            fi

            # Gradle wrapper
            if { [ -f "build.gradle" ] || [ -f "build.gradle.kts" ]; } && [ ! -f "./gradlew" ] && command -v gradle >/dev/null 2>&1; then
                gradle wrapper 2>/dev/null && chmod +x ./gradlew 2>/dev/null && log "✓ Generated gradlew"
            fi

            cd "$orig_dir"
        }

        generate_wrappers

        # Show installed tools
        for tool in java:java node:node npm:npm python3:python go:go rustc:rust dotnet:dotnet php:php ruby:ruby; do
            cmd=${tool%:*} name=${tool#*:}
            command -v "$cmd" >/dev/null 2>&1 && log "  ✓ $name"
        done
    fi

    # Execute commands in repository directory
    execute_command() {
        local cmd="$1" desc="$2"
        [ -z "$cmd" ] || [ "$cmd" = "null" ] && { log "Skipping $desc (no command)"; return; }

        local fixed_cmd=$(fix_build_wrapper "$cmd")
        local orig_dir=$(pwd)

        log "Executing $desc: $fixed_cmd"
        [ "$fixed_cmd" != "$cmd" ] && log "  (Fixed from: $cmd)"

        # Execute in repository directory if available
        [ -n "$REPO_DIR" ] && [ -d "$REPO_DIR" ] && cd "$REPO_DIR"

        if eval "$fixed_cmd"; then
            log "✓ $desc completed"
        else
            local exit_code=$?
            log "✗ $desc failed (exit $exit_code)"

            # Retry with Maven installation if command not found
            if echo "$fixed_cmd" | grep -q "mvn" && [ $exit_code -eq 127 ]; then
                log "Installing Maven and retrying..."
                $PACKAGE_INSTALL maven && command -v mvn >/dev/null 2>&1 && eval "$fixed_cmd" && log "✓ $desc completed on retry"
            fi
        fi

        cd "$orig_dir"
    }

    # Execute build commands
    [ -n "$CLEAN_INSTALL_CMD" ] && [ "$CLEAN_INSTALL_CMD" != "null" ] && execute_command "$CLEAN_INSTALL_CMD" "clean install"
    [ -z "$CLEAN_INSTALL_CMD" ] && [ -n "$INSTALL_CMD" ] && [ "$INSTALL_CMD" != "null" ] && execute_command "$INSTALL_CMD" "install"
    [ -n "$BUILD_DEV_CMD" ] && [ "$BUILD_DEV_CMD" != "null" ] && execute_command "$BUILD_DEV_CMD" "build"
    [ -z "$BUILD_DEV_CMD" ] && [ -n "$BUILD_PROD_CMD" ] && [ "$BUILD_PROD_CMD" != "null" ] && execute_command "$BUILD_PROD_CMD" "build"

else
    log "WARNING: No output found in $OUTPUT_DIR"
fi

log "✓ Analysis complete"
[ -n "$START_DEV_CMD" ] && [ "$START_DEV_CMD" != "null" ] && log "Dev server: $START_DEV_CMD"
