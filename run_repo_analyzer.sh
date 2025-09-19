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




    # Universal version management functions for all languages

    # Node.js version management
    check_and_install_node_version() {
        local required_version="$1"
        local required_npm="$2"

        if [ -n "$required_version" ] && [ "$required_version" != "latest" ] && [ "$required_version" != "null" ]; then
            log "Checking Node.js version requirement: $required_version"

            if command -v node >/dev/null 2>&1; then
                current_version=$(node --version | sed 's/v//')
                major_version=$(echo "$current_version" | cut -d. -f1)
                required_major=$(echo "$required_version" | sed 's/[.x]//g' | cut -d. -f1)

                if [ "$major_version" != "$required_major" ]; then
                    log "Installing Node.js $required_version..."
                    install_node_version "$required_version"
                fi
            else
                install_node_version "$required_version"
            fi
        fi

        # Check npm version if specified
        if [ -n "$required_npm" ] && [ "$required_npm" != "latest" ] && [ "$required_npm" != "null" ]; then
            if command -v npm >/dev/null 2>&1; then
                npm install -g npm@"$required_npm" 2>/dev/null || log "Failed to update npm to $required_npm"
            fi
        fi
    }

    install_node_version() {
        local version="$1"
        if [ "$OS_TYPE" = "macos" ]; then
            # Use Homebrew to install specific Node version
            case "$version" in
                "16"*|"16.x")
                    $PACKAGE_INSTALL node@16 || log "Failed to install Node.js 16"
                    export PATH="/opt/homebrew/opt/node@16/bin:$PATH"
                    ;;
                "18"*|"18.x")
                    $PACKAGE_INSTALL node@18 || log "Failed to install Node.js 18"
                    export PATH="/opt/homebrew/opt/node@18/bin:$PATH"
                    ;;
                "20"*|"20.x")
                    $PACKAGE_INSTALL node@20 || log "Failed to install Node.js 20"
                    export PATH="/opt/homebrew/opt/node@20/bin:$PATH"
                    ;;
                *)
                    $PACKAGE_INSTALL node || log "Failed to install Node.js"
                    ;;
            esac
        elif [ "$OS_TYPE" = "linux" ]; then
            # Use NodeSource repository for specific versions
            if command -v curl >/dev/null 2>&1; then
                case "$version" in
                    "16"*|"16.x")
                        curl -fsSL https://deb.nodesource.com/setup_16.x | bash - || log "NodeSource setup failed"
                        ;;
                    "18"*|"18.x")
                        curl -fsSL https://deb.nodesource.com/setup_18.x | bash - || log "NodeSource setup failed"
                        ;;
                    "20"*|"20.x")
                        curl -fsSL https://deb.nodesource.com/setup_20.x | bash - || log "NodeSource setup failed"
                        ;;
                esac
                $PACKAGE_INSTALL nodejs || log "Failed to install Node.js"
            fi
        fi
    }

    # Python version management
    check_and_install_python_version() {
        local required_version="$1"

        if [ -n "$required_version" ] && [ "$required_version" != "latest" ] && [ "$required_version" != "null" ]; then
            log "Checking Python version requirement: $required_version"

            if command -v python3 >/dev/null 2>&1; then
                current_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d. -f1-2)

                if [ "$current_version" != "$required_version" ]; then
                    log "Installing Python $required_version..."
                    install_python_version "$required_version"
                fi
            else
                install_python_version "$required_version"
            fi
        fi
    }

    install_python_version() {
        local version="$1"
        if [ "$OS_TYPE" = "macos" ]; then
            case "$version" in
                "3.8")
                    $PACKAGE_INSTALL python@3.8 || log "Failed to install Python 3.8"
                    export PATH="/opt/homebrew/opt/python@3.8/bin:$PATH"
                    ;;
                "3.9")
                    $PACKAGE_INSTALL python@3.9 || log "Failed to install Python 3.9"
                    export PATH="/opt/homebrew/opt/python@3.9/bin:$PATH"
                    ;;
                "3.10")
                    $PACKAGE_INSTALL python@3.10 || log "Failed to install Python 3.10"
                    export PATH="/opt/homebrew/opt/python@3.10/bin:$PATH"
                    ;;
                "3.11")
                    $PACKAGE_INSTALL python@3.11 || log "Failed to install Python 3.11"
                    export PATH="/opt/homebrew/opt/python@3.11/bin:$PATH"
                    ;;
                "3.12")
                    $PACKAGE_INSTALL python@3.12 || log "Failed to install Python 3.12"
                    export PATH="/opt/homebrew/opt/python@3.12/bin:$PATH"
                    ;;
            esac
        elif [ "$OS_TYPE" = "linux" ]; then
            case "$version" in
                "3.8")
                    $PACKAGE_INSTALL python3.8 python3.8-pip python3.8-venv || log "Failed to install Python 3.8"
                    ;;
                "3.9")
                    $PACKAGE_INSTALL python3.9 python3.9-pip python3.9-venv || log "Failed to install Python 3.9"
                    ;;
                "3.10")
                    $PACKAGE_INSTALL python3.10 python3.10-pip python3.10-venv || log "Failed to install Python 3.10"
                    ;;
                "3.11")
                    $PACKAGE_INSTALL python3.11 python3.11-pip python3.11-venv || log "Failed to install Python 3.11"
                    ;;
                "3.12")
                    $PACKAGE_INSTALL python3.12 python3.12-pip python3.12-venv || log "Failed to install Python 3.12"
                    ;;
            esac
        fi
    }

    # Go version management
    check_and_install_go_version() {
        local required_version="$1"

        if [ -n "$required_version" ] && [ "$required_version" != "latest" ] && [ "$required_version" != "null" ]; then
            log "Checking Go version requirement: $required_version"

            if command -v go >/dev/null 2>&1; then
                current_version=$(go version | cut -d' ' -f3 | sed 's/go//')
                if [ "$current_version" != "$required_version" ]; then
                    log "Installing Go $required_version..."
                    install_go_version "$required_version"
                fi
            else
                install_go_version "$required_version"
            fi
        fi
    }

    install_go_version() {
        local version="$1"
        if [ "$OS_TYPE" = "macos" ]; then
            $PACKAGE_INSTALL go || log "Failed to install Go"
        elif [ "$OS_TYPE" = "linux" ]; then
            # Download and install specific Go version
            if command -v curl >/dev/null 2>&1; then
                ARCH=$(uname -m)
                case "$ARCH" in
                    "x86_64") ARCH="amd64" ;;
                    "aarch64") ARCH="arm64" ;;
                esac

                GO_URL="https://go.dev/dl/go${version}.linux-${ARCH}.tar.gz"
                curl -L "$GO_URL" -o /tmp/go.tar.gz 2>/dev/null || log "Failed to download Go $version"

                if [ -f "/tmp/go.tar.gz" ]; then
                    rm -rf /usr/local/go 2>/dev/null
                    tar -C /usr/local -xzf /tmp/go.tar.gz 2>/dev/null || log "Failed to extract Go"
                    export PATH="/usr/local/go/bin:$PATH"
                    rm -f /tmp/go.tar.gz
                fi
            fi
        fi
    }

    # Check for specific Java version requirements from analysis
    check_and_install_java_version() {
        local required_version="$1"

        if [ -n "$required_version" ] && [ "$required_version" != "any" ] && [ "$required_version" != "null" ]; then
            log "Checking Java version requirement: $required_version"

            if command -v java >/dev/null 2>&1; then
                current_version=$(java -version 2>&1 | head -n 1 | cut -d'"' -f2 | cut -d'.' -f1)
                # Handle Java 1.8 format vs newer format
                if [ "$current_version" = "1" ]; then
                    current_version=$(java -version 2>&1 | head -n 1 | cut -d'"' -f2 | cut -d'.' -f2)
                fi

                log "Current Java version: $current_version, Required: $required_version"

                if [ "$current_version" != "$required_version" ]; then
                    log "Installing Java $required_version..."

                    if [ "$OS_TYPE" = "macos" ]; then
                        # Use Homebrew to install specific Java version
                        case "$required_version" in
                            "8")
                                $PACKAGE_INSTALL openjdk@8 || log "Failed to install Java 8"
                                export PATH="/opt/homebrew/opt/openjdk@8/bin:$PATH"
                                ;;
                            "11")
                                $PACKAGE_INSTALL openjdk@11 || log "Failed to install Java 11"
                                export PATH="/opt/homebrew/opt/openjdk@11/bin:$PATH"
                                ;;
                            "17")
                                $PACKAGE_INSTALL openjdk@17 || log "Failed to install Java 17"
                                export PATH="/opt/homebrew/opt/openjdk@17/bin:$PATH"
                                ;;
                            "21")
                                $PACKAGE_INSTALL openjdk@21 || log "Failed to install Java 21"
                                export PATH="/opt/homebrew/opt/openjdk@21/bin:$PATH"
                                ;;
                            *)
                                log "Unsupported Java version $required_version for macOS, keeping current"
                                ;;
                        esac
                    elif [ "$OS_TYPE" = "linux" ]; then
                        # Use system package manager for specific versions
                        case "$required_version" in
                            "8")
                                $PACKAGE_INSTALL openjdk-8-jdk || log "Failed to install Java 8"
                                ;;
                            "11")
                                $PACKAGE_INSTALL openjdk-11-jdk || log "Failed to install Java 11"
                                ;;
                            "17")
                                $PACKAGE_INSTALL openjdk-17-jdk || log "Failed to install Java 17"
                                ;;
                            "21")
                                $PACKAGE_INSTALL openjdk-21-jdk || log "Failed to install Java 21"
                                ;;
                            *)
                                log "Unsupported Java version $required_version for Linux, keeping current"
                                ;;
                        esac
                    fi

                    # Verify installation
                    if command -v java >/dev/null 2>&1; then
                        log "✓ Updated Java: $(java -version 2>&1 | head -n 1)"
                    fi
                fi
            fi
        fi
    }

    # Rust version management
    check_and_install_rust_version() {
        local required_version="$1"

        if [ -n "$required_version" ] && [ "$required_version" != "latest" ] && [ "$required_version" != "null" ]; then
            log "Checking Rust version requirement: $required_version"

            if command -v rustc >/dev/null 2>&1; then
                current_version=$(rustc --version | cut -d' ' -f2)
                if [ "$current_version" != "$required_version" ]; then
                    log "Installing Rust $required_version..."
                    install_rust_version "$required_version"
                fi
            else
                install_rust_version "$required_version"
            fi
        fi
    }

    install_rust_version() {
        local version="$1"
        if command -v curl >/dev/null 2>&1; then
            # Use rustup to install specific Rust version
            curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y || log "Failed to install rustup"
            export PATH="$HOME/.cargo/bin:$PATH"

            if [ "$version" != "stable" ] && [ "$version" != "latest" ]; then
                rustup install "$version" || log "Failed to install Rust $version"
                rustup default "$version" || log "Failed to set Rust $version as default"
            fi
        elif [ "$OS_TYPE" = "macos" ]; then
            $PACKAGE_INSTALL rust || log "Failed to install Rust via Homebrew"
        fi
    }

    # .NET version management
    check_and_install_dotnet_version() {
        local required_version="$1"

        if [ -n "$required_version" ] && [ "$required_version" != "latest" ] && [ "$required_version" != "null" ]; then
            log "Checking .NET version requirement: $required_version"

            if command -v dotnet >/dev/null 2>&1; then
                # Check if required version is installed
                if ! dotnet --list-sdks | grep -q "$required_version"; then
                    log "Installing .NET $required_version..."
                    install_dotnet_version "$required_version"
                fi
            else
                install_dotnet_version "$required_version"
            fi
        fi
    }

    install_dotnet_version() {
        local version="$1"
        if [ "$OS_TYPE" = "macos" ]; then
            $PACKAGE_INSTALL dotnet || log "Failed to install .NET"
        elif [ "$OS_TYPE" = "linux" ]; then
            # Install .NET using Microsoft's installation script
            if command -v curl >/dev/null 2>&1; then
                curl -sSL https://dot.net/v1/dotnet-install.sh | bash /dev/stdin --version "$version" || log "Failed to install .NET $version"
                export PATH="$HOME/.dotnet:$PATH"
            fi
        fi
    }

    # PHP version management
    check_and_install_php_version() {
        local required_version="$1"

        if [ -n "$required_version" ] && [ "$required_version" != "latest" ] && [ "$required_version" != "null" ]; then
            log "Checking PHP version requirement: $required_version"

            if command -v php >/dev/null 2>&1; then
                current_version=$(php -v | head -n 1 | cut -d' ' -f2 | cut -d. -f1-2)
                if [ "$current_version" != "$required_version" ]; then
                    log "Installing PHP $required_version..."
                    install_php_version "$required_version"
                fi
            else
                install_php_version "$required_version"
            fi
        fi
    }

    install_php_version() {
        local version="$1"
        if [ "$OS_TYPE" = "macos" ]; then
            case "$version" in
                "8.1")
                    $PACKAGE_INSTALL php@8.1 || log "Failed to install PHP 8.1"
                    export PATH="/opt/homebrew/opt/php@8.1/bin:$PATH"
                    ;;
                "8.2")
                    $PACKAGE_INSTALL php@8.2 || log "Failed to install PHP 8.2"
                    export PATH="/opt/homebrew/opt/php@8.2/bin:$PATH"
                    ;;
                "8.3")
                    $PACKAGE_INSTALL php || log "Failed to install PHP"
                    ;;
            esac
        elif [ "$OS_TYPE" = "linux" ]; then
            $PACKAGE_INSTALL php php-cli php-common || log "Failed to install PHP"
        fi

        # Install Composer if PHP is available
        if command -v php >/dev/null 2>&1 && ! command -v composer >/dev/null 2>&1; then
            log "Installing Composer..."
            if command -v curl >/dev/null 2>&1; then
                curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer 2>/dev/null || log "Failed to install Composer"
            fi
        fi
    }

    # Ruby version management
    check_and_install_ruby_version() {
        local required_version="$1"

        if [ -n "$required_version" ] && [ "$required_version" != "latest" ] && [ "$required_version" != "null" ]; then
            log "Checking Ruby version requirement: $required_version"

            if command -v ruby >/dev/null 2>&1; then
                current_version=$(ruby -v | cut -d' ' -f2 | cut -d. -f1-2)
                if [ "$current_version" != "$required_version" ]; then
                    log "Installing Ruby $required_version..."
                    install_ruby_version "$required_version"
                fi
            else
                install_ruby_version "$required_version"
            fi
        fi
    }

    install_ruby_version() {
        local version="$1"
        if [ "$OS_TYPE" = "macos" ]; then
            case "$version" in
                "3.0")
                    $PACKAGE_INSTALL ruby@3.0 || log "Failed to install Ruby 3.0"
                    export PATH="/opt/homebrew/opt/ruby@3.0/bin:$PATH"
                    ;;
                "3.1")
                    $PACKAGE_INSTALL ruby@3.1 || log "Failed to install Ruby 3.1"
                    export PATH="/opt/homebrew/opt/ruby@3.1/bin:$PATH"
                    ;;
                "3.2"|*)
                    $PACKAGE_INSTALL ruby || log "Failed to install Ruby"
                    ;;
            esac
        elif [ "$OS_TYPE" = "linux" ]; then
            $PACKAGE_INSTALL ruby ruby-dev || log "Failed to install Ruby"
        fi

        # Install Bundler if Ruby is available
        if command -v ruby >/dev/null 2>&1 && command -v gem >/dev/null 2>&1; then
            gem install bundler 2>/dev/null || log "Failed to install Bundler"
        fi
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

        # Check Java projects
        if echo "$TECHNOLOGIES" | grep -qi "java" || [ -n "$REQUIRED_JAVA_VERSION" ] && [ "$REQUIRED_JAVA_VERSION" != "null" ]; then
            log "📦 Java detected - installing Java environment..."
            check_and_install_java_version "$REQUIRED_JAVA_VERSION"
        fi

        # Check Node.js/JavaScript/TypeScript projects
        if echo "$TECHNOLOGIES" | grep -qi "javascript\|typescript\|node" || echo "$PACKAGE_MANAGERS" | grep -qi "npm\|yarn\|pnpm" || [ -n "$REQUIRED_NODE_VERSION" ] && [ "$REQUIRED_NODE_VERSION" != "null" ]; then
            log "📦 Node.js/JavaScript detected - installing Node.js environment..."
            check_and_install_node_version "$REQUIRED_NODE_VERSION" "$REQUIRED_NPM_VERSION"
        fi

        # Check Python projects
        if echo "$TECHNOLOGIES" | grep -qi "python" || echo "$PACKAGE_MANAGERS" | grep -qi "pip\|poetry\|pipenv" || [ -n "$REQUIRED_PYTHON_VERSION" ] && [ "$REQUIRED_PYTHON_VERSION" != "null" ]; then
            log "📦 Python detected - installing Python environment..."
            check_and_install_python_version "$REQUIRED_PYTHON_VERSION"
        fi

        # Check Go projects
        if echo "$TECHNOLOGIES" | grep -qi "go\|golang" || echo "$PACKAGE_MANAGERS" | grep -qi "go-mod\|go mod" || [ -n "$REQUIRED_GO_VERSION" ] && [ "$REQUIRED_GO_VERSION" != "null" ]; then
            log "📦 Go detected - installing Go environment..."
            check_and_install_go_version "$REQUIRED_GO_VERSION"
        fi

        # Check Rust projects
        if echo "$TECHNOLOGIES" | grep -qi "rust" || echo "$PACKAGE_MANAGERS" | grep -qi "cargo" || [ -n "$REQUIRED_RUST_VERSION" ] && [ "$REQUIRED_RUST_VERSION" != "null" ]; then
            log "📦 Rust detected - installing Rust environment..."
            check_and_install_rust_version "$REQUIRED_RUST_VERSION"
        fi

        # Check .NET projects
        if echo "$TECHNOLOGIES" | grep -qi "\.net\|c#\|f#\|csharp\|fsharp" || echo "$PACKAGE_MANAGERS" | grep -qi "dotnet\|nuget" || [ -n "$REQUIRED_DOTNET_VERSION" ] && [ "$REQUIRED_DOTNET_VERSION" != "null" ]; then
            log "📦 .NET detected - installing .NET environment..."
            check_and_install_dotnet_version "$REQUIRED_DOTNET_VERSION"
        fi

        # Check PHP projects
        if echo "$TECHNOLOGIES" | grep -qi "php" || echo "$PACKAGE_MANAGERS" | grep -qi "composer" || [ -n "$REQUIRED_PHP_VERSION" ] && [ "$REQUIRED_PHP_VERSION" != "null" ]; then
            log "📦 PHP detected - installing PHP environment..."
            check_and_install_php_version "$REQUIRED_PHP_VERSION"
        fi

        # Check Ruby projects
        if echo "$TECHNOLOGIES" | grep -qi "ruby" || echo "$PACKAGE_MANAGERS" | grep -qi "gem\|bundler" || [ -n "$REQUIRED_RUBY_VERSION" ] && [ "$REQUIRED_RUBY_VERSION" != "null" ]; then
            log "📦 Ruby detected - installing Ruby environment..."
            check_and_install_ruby_version "$REQUIRED_RUBY_VERSION"
        fi

        log "⚡ Optimization: Only installing detected languages - skipping unnecessary runtime installations"

        # Check for build files and attempt to create missing wrappers
        HAS_MAVEN_WRAPPER=$(jq -r '.environment_requirements.build_files_available.has_maven_wrapper // false' "$OUTPUT_FILE")
        POM_LOCATION=$(jq -r '.environment_requirements.build_files_available.maven_pom_location // empty' "$OUTPUT_FILE")

        if [ -f "pom.xml" ] || [ -n "$POM_LOCATION" ]; then
            if [ "$HAS_MAVEN_WRAPPER" = "false" ] && [ ! -f "./mvnw" ]; then
                log "Maven project detected without wrapper, attempting to generate mvnw..."
                if command -v mvn >/dev/null 2>&1; then
                    mvn -N wrapper:wrapper 2>/dev/null || log "Failed to generate Maven wrapper"
                    if [ -f "./mvnw" ]; then
                        chmod +x ./mvnw
                        log "✓ Generated Maven wrapper (mvnw)"
                    fi
                fi
            fi
        fi

        # Generate summary of installed tools
        log "📋 Environment Summary:"
        command -v java >/dev/null 2>&1 && log "  ✓ Java: $(java -version 2>&1 | head -n 1)"
        command -v node >/dev/null 2>&1 && log "  ✓ Node.js: $(node --version)"
        command -v npm >/dev/null 2>&1 && log "  ✓ npm: $(npm --version)"
        command -v python3 >/dev/null 2>&1 && log "  ✓ Python: $(python3 --version)"
        command -v go >/dev/null 2>&1 && log "  ✓ Go: $(go version | cut -d' ' -f3)"
        command -v rustc >/dev/null 2>&1 && log "  ✓ Rust: $(rustc --version | cut -d' ' -f2)"
        command -v dotnet >/dev/null 2>&1 && log "  ✓ .NET: $(dotnet --version)"
        command -v php >/dev/null 2>&1 && log "  ✓ PHP: $(php -v | head -n 1 | cut -d' ' -f2)"
        command -v ruby >/dev/null 2>&1 && log "  ✓ Ruby: $(ruby -v | cut -d' ' -f2)"
    fi

    # Function to safely execute commands with build wrapper fixes
    execute_command() {
        local cmd="$1"
        local desc="$2"
        if [ -n "$cmd" ] && [ "$cmd" != "null" ]; then
            # Fix build wrapper issues
            local fixed_cmd=$(fix_build_wrapper "$cmd")

            log "Executing $desc: $fixed_cmd"
            if [ "$fixed_cmd" != "$cmd" ]; then
                log "  (Fixed from: $cmd)"
            fi

            if eval "$fixed_cmd"; then
                log "✓ $desc completed successfully"
            else
                local exit_code=$?
                log "✗ $desc failed (exit code: $exit_code)"

                # Try fallback strategies for common failures
                if echo "$fixed_cmd" | grep -q "mvn\|maven" && [ $exit_code -eq 127 ]; then
                    log "Attempting to install Maven and retry..."
                    if [ "$OS_TYPE" = "macos" ]; then
                        $PACKAGE_INSTALL maven
                    elif [ "$OS_TYPE" = "linux" ]; then
                        $PACKAGE_INSTALL maven
                    fi
                    if command -v mvn >/dev/null 2>&1; then
                        log "Retrying with Maven now available..."
                        if eval "$fixed_cmd"; then
                            log "✓ $desc completed successfully on retry"
                            return 0
                        fi
                    fi
                fi

                return $exit_code
            fi
        else
            log "Skipping $desc (no command found)"
        fi
    }

    # Execute commands in logical order
    if [ -n "$CLEAN_INSTALL_CMD" ] && [ "$CLEAN_INSTALL_CMD" != "null" ]; then
        execute_command "$CLEAN_INSTALL_CMD" "clean install"
    elif [ -n "$INSTALL_CMD" ] && [ "$INSTALL_CMD" != "null" ]; then
        execute_command "$INSTALL_CMD" "dependency installation"
    fi

    # Build commands (try development first, then production)
    if [ -n "$BUILD_DEV_CMD" ] && [ "$BUILD_DEV_CMD" != "null" ]; then
        execute_command "$BUILD_DEV_CMD" "development build"
    elif [ -n "$BUILD_PROD_CMD" ] && [ "$BUILD_PROD_CMD" != "null" ]; then
        execute_command "$BUILD_PROD_CMD" "production build"
    fi

    # Optional: Start development server (commented out by default as it runs indefinitely)
    # if [ -n "$START_DEV_CMD" ] && [ "$START_DEV_CMD" != "null" ]; then
    #     log "Development server command available: $START_DEV_CMD"
    #     log "To start development server, run: $START_DEV_CMD"
    # fi

else
    log "WARNING: No output found in $OUTPUT_DIR"
fi

log "=== EXECUTION SUMMARY ==="
log "Analysis and setup completed successfully"
if [ -n "$START_DEV_CMD" ] && [ "$START_DEV_CMD" != "null" ]; then
    log "To start development server: $START_DEV_CMD"
fi
log "Scan complete"
exit 0
