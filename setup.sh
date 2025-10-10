#!/bin/bash
# DCGM Exporter on SuperPOD - Setup Script
# This script prepares the environment and launches the automated deployment

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/automation/configs/config.json"

echo "=================================================="
echo "DCGM Exporter on SuperPOD - Automated Deployment"
echo "=================================================="
echo ""

# Check if running on a BCM headnode
CURRENT_HOSTNAME=$(hostname -s)
echo "Verifying BCM headnode requirement..."
echo -n "Current hostname: $CURRENT_HOSTNAME ... "

if command -v cmsh >/dev/null 2>&1; then
    # Get list of BCM headnodes
    BCM_HEADNODES=$(cmsh -c "device list --type headnode" 2>/dev/null | grep -i "headnode" | awk '{print $2}' | tr '\n' ' ')
    
    if echo "$BCM_HEADNODES" | grep -qw "$CURRENT_HOSTNAME"; then
        echo "✓ Running on BCM headnode"
    else
        echo "✗ NOT a BCM headnode"
        echo ""
        echo "WARNING: This script should be run from a BCM headnode."
        echo "Detected BCM headnodes: $BCM_HEADNODES"
        echo "Current hostname: $CURRENT_HOSTNAME"
        echo ""
        read -p "Continue anyway? (yes/no) [no]: " CONTINUE_ANYWAY
        if [[ ! "$CONTINUE_ANYWAY" =~ ^[Yy][Ee]?[Ss]?$ ]]; then
            echo "Exiting. Please run this script from a BCM headnode."
            exit 1
        fi
    fi
else
    echo "⚠ Cannot verify (cmsh not available)"
    echo ""
    echo "WARNING: cmsh command not found. Cannot verify if running on BCM headnode."
    echo "This script should be run from a BCM headnode for proper functionality."
    echo ""
    read -p "Continue anyway? (yes/no) [no]: " CONTINUE_ANYWAY
    if [[ ! "$CONTINUE_ANYWAY" =~ ^[Yy][Ee]?[Ss]?$ ]]; then
        echo "Exiting."
        exit 1
    fi
fi
echo ""

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to auto-detect BCM headnode hostname
detect_bcm_headnode() {
    # Check if cmsh is available
    if ! command_exists cmsh; then
        echo ""
        return 1
    fi
    
    # Run cmsh command and extract hostname
    local headnode=$(cmsh -c "device list --type headnode" 2>/dev/null | grep -i "headnode" | awk '{print $2}' | head -n 1)
    
    if [ -n "$headnode" ]; then
        echo "$headnode"
        return 0
    else
        echo ""
        return 1
    fi
}

# Check for required system tools
echo "Checking system requirements..."
MISSING_TOOLS=()

if ! command_exists python3; then
    MISSING_TOOLS+=("python3")
fi

if ! command_exists git; then
    MISSING_TOOLS+=("git")
fi

if ! command_exists ssh; then
    MISSING_TOOLS+=("ssh")
fi

if [ ${#MISSING_TOOLS[@]} -ne 0 ]; then
    echo "Error: Missing required tools: ${MISSING_TOOLS[*]}"
    echo "Please install these tools and try again."
    exit 1
fi

echo "✓ System requirements met"
echo ""

# Check/Install uv package manager
echo "Checking for uv package manager..."
if ! command_exists uv; then
    echo "uv not found. Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # Source the uv environment
    export PATH="$HOME/.cargo/bin:$PATH"
    
    if ! command_exists uv; then
        echo "Error: Failed to install uv. Please install manually from https://github.com/astral-sh/uv"
        exit 1
    fi
    echo "✓ uv installed successfully"
else
    echo "✓ uv already installed"
fi
echo ""

# Function to collect configuration
collect_configuration() {
    echo ""
    echo "=== Configuration Setup ==="
    echo ""
    
    # Auto-detect BCM headnode
    echo "Detecting BCM headnode..."
    BCM_HEADNODE=$(detect_bcm_headnode)
    if [ -n "$BCM_HEADNODE" ]; then
        echo "✓ Detected BCM headnode: $BCM_HEADNODE"
    else
        echo "⚠ Could not auto-detect BCM headnode (is cmsh available?)"
        read -p "Enter BCM headnode hostname [bcm-01]: " BCM_HEADNODE
        BCM_HEADNODE=${BCM_HEADNODE:-bcm-01}
    fi
    echo ""
    
    # Get DGX nodes
    read -p "Enter DGX node hostnames (comma-separated) [dgx-01]: " DGX_NODES
    DGX_NODES=${DGX_NODES:-dgx-01}
    
    # Get Slurm controller
    read -p "Enter Slurm controller hostname [slurmctl]: " SLURM_CONTROLLER
    SLURM_CONTROLLER=${SLURM_CONTROLLER:-slurmctl}
    
    # Ask about Prometheus
    echo ""
    echo "=== Prometheus Configuration ==="
    echo "Choose one of the following options:"
    echo "  1) Use existing Prometheus server"
    echo "  2) Deploy new Prometheus server (automated)"
    echo ""
    read -p "Select option [2]: " PROM_OPTION
    PROM_OPTION=${PROM_OPTION:-2}
    
    if [ "$PROM_OPTION" = "1" ]; then
        USE_EXISTING_PROMETHEUS="true"
        DEPLOY_PROMETHEUS="false"
        read -p "Enter existing Prometheus server hostname: " PROMETHEUS_SERVER
        read -p "Enter Prometheus targets directory [/cm/shared/apps/prometheus/targets]: " PROMETHEUS_TARGETS_DIR
        PROMETHEUS_TARGETS_DIR=${PROMETHEUS_TARGETS_DIR:-/cm/shared/apps/prometheus/targets}
    else
        USE_EXISTING_PROMETHEUS="false"
        DEPLOY_PROMETHEUS="true"
        PROMETHEUS_SERVER=""
        read -p "Enter hostname for new Prometheus server [$SLURM_CONTROLLER]: " PROMETHEUS_SERVER
        PROMETHEUS_SERVER=${PROMETHEUS_SERVER:-$SLURM_CONTROLLER}
        PROMETHEUS_TARGETS_DIR="/cm/shared/apps/dcgm-exporter/prometheus-targets"
    fi
    echo ""
    
    # Create config directory
    mkdir -p "$(dirname "$CONFIG_FILE")"
    
    # Generate config.json
    cat > "$CONFIG_FILE" <<EOF
{
  "cluster_name": "slurm",
  "bcm_headnode": "$BCM_HEADNODE",
  "use_existing_prometheus": $USE_EXISTING_PROMETHEUS,
  "deploy_prometheus": $DEPLOY_PROMETHEUS,
  "prometheus_server": "$PROMETHEUS_SERVER",
  "prometheus_targets_dir": "$PROMETHEUS_TARGETS_DIR",
  "prometheus_port": 9090,
  "dcgm_exporter_port": 9400,
  "hpc_job_mapping_dir": "/run/dcgm-job-map",
  "systems": {
    "dgx_nodes": [$(echo "$DGX_NODES" | sed 's/,/", "/g' | sed 's/^/"/' | sed 's/$/"/')],
    "slurm_controller": "$SLURM_CONTROLLER",
    "bcm_headnode": "$BCM_HEADNODE"
  },
  "deployment_options": {
    "deploy_dcgm_exporter": true,
    "deploy_slurm_prolog_epilog": true,
    "deploy_bcm_role_monitor": true,
    "deploy_prometheus": $DEPLOY_PROMETHEUS
  }
}
EOF
    echo "✓ Configuration saved: $CONFIG_FILE"
    echo ""
}

# Check if config.json exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Configuration file not found: $CONFIG_FILE"
    echo ""
    echo "Would you like to create a configuration file? (yes/no) [yes]"
    read -r CREATE_CONFIG
    CREATE_CONFIG=${CREATE_CONFIG:-yes}
    
    if [[ "$CREATE_CONFIG" =~ ^[Yy][Ee]?[Ss]?$ ]]; then
        collect_configuration
    else
        echo ""
        echo "Please create a configuration file and try again."
        echo "You can use automation/configs/config.example.json as a template."
        exit 1
    fi
else
    # Config exists - show it and ask to keep or change
    echo "Found existing configuration: $CONFIG_FILE"
    echo ""
    echo "=== Current Configuration ==="
    if command_exists jq && jq empty "$CONFIG_FILE" 2>/dev/null; then
        jq -r '
            "Cluster: \(.cluster_name)",
            "BCM Headnode: \(.bcm_headnode)",
            "DGX Nodes: \(.systems.dgx_nodes | join(", "))",
            "Slurm Controller: \(.systems.slurm_controller)",
            "Prometheus: \(if .deploy_prometheus then "Deploy new on \(.prometheus_server)" elif .use_existing_prometheus then "Use existing at \(.prometheus_server)" else "Not configured" end)",
            "Prometheus Targets Dir: \(.prometheus_targets_dir)",
            "HPC Job Mapping Dir: \(.hpc_job_mapping_dir)"
        ' "$CONFIG_FILE"
    else
        cat "$CONFIG_FILE"
    fi
    echo ""
    
    read -p "[K]eep or [C]hange these values? [K]: " CONFIG_CHOICE
    CONFIG_CHOICE=${CONFIG_CHOICE:-K}
    
    if [[ "$CONFIG_CHOICE" =~ ^[Cc]$ ]]; then
        collect_configuration
    else
        echo "✓ Keeping existing configuration"
        echo ""
    fi
fi

# Ask for deployment mode
echo "=== Deployment Mode ==="
echo "1) Full automated deployment (recommended)"
echo "2) View documentation (no changes)"
echo ""
read -p "Select mode [1]: " MODE
MODE=${MODE:-1}

echo ""
echo "Starting DCGM Exporter deployment..."
echo ""

# Launch Python automation
cd "$SCRIPT_DIR"

# Install dependencies if not already done
if [ ! -d ".venv" ]; then
    echo "Installing Python dependencies..."
    uv venv
    uv pip install -r <(echo "requests>=2.31.0")
fi

# Activate virtual environment and run
source .venv/bin/activate

case $MODE in
    1)
        echo "Running full automated deployment..."
        python automation/deploy_dcgm_exporter.py --config "$CONFIG_FILE" --verbose
        ;;
    2)
        echo "Running in dry-run mode..."
        echo "Note: Dry-run mode generates commands without executing."
        echo "See docs/How-To-Guide.md for manual deployment steps."
        exit 0
        ;;
    3)
        echo "Resuming previous deployment..."
        echo "Note: Resume is not implemented. Please run full deployment again."
        python automation/deploy_dcgm_exporter.py --config "$CONFIG_FILE" --verbose
        ;;
    *)
        echo "Invalid mode selected"
        exit 1
        ;;
esac

EXIT_CODE=$?

# Deactivate virtual environment
deactivate

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "=================================================="
    echo "Deployment completed successfully!"
    echo "=================================================="
    echo ""
    echo "Next steps:"
    echo "1. Verify DCGM exporter is running: ssh <dgx-node> 'systemctl status dcgm-exporter'"
    echo "2. Test metrics endpoint: curl http://<dgx-node>:9400/metrics"
    if grep -q '"deploy_prometheus": true' "$CONFIG_FILE" 2>/dev/null; then
        PROM_SERVER=$(jq -r '.prometheus_server // "prometheus-server"' "$CONFIG_FILE" 2>/dev/null)
        echo "3. Access Prometheus: http://${PROM_SERVER}:9090"
        echo "4. Verify DCGM targets in Prometheus: Status -> Targets"
    elif grep -q '"use_existing_prometheus": true' "$CONFIG_FILE" 2>/dev/null; then
        echo "3. Verify DCGM targets appear in your existing Prometheus server"
    else
        echo "3. Configure Prometheus to scrape DCGM exporter (see documentation)"
    fi
    echo "5. Import Grafana dashboard (grafana/dcgm-dashboard.json)"
    echo ""
else
    echo "=================================================="
    echo "Deployment encountered errors"
    echo "=================================================="
    echo ""
    echo "Check the logs for details."
    echo ""
    exit $EXIT_CODE
fi

