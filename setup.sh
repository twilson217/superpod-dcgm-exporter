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

# Check if running as root or with sudo
if [ "$EUID" -eq 0 ]; then
    echo "Warning: Running as root. This script should be run as a regular user with sudo access."
    echo "Some operations will require sudo, which will be requested when needed."
    echo ""
fi

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
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

# Check if config.json exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Configuration file not found: $CONFIG_FILE"
    echo ""
    echo "Would you like to create a basic configuration file? (yes/no)"
    read -r CREATE_CONFIG
    
    if [[ "$CREATE_CONFIG" =~ ^[Yy][Ee]?[Ss]?$ ]]; then
        echo ""
        echo "=== Basic Configuration Setup ==="
        echo ""
        
        # Get BCM headnode
        read -p "Enter BCM headnode hostname [bcm-01]: " BCM_HEADNODE
        BCM_HEADNODE=${BCM_HEADNODE:-bcm-01}
        
        # Get DGX nodes
        read -p "Enter DGX node hostnames (comma-separated) [dgx-01]: " DGX_NODES
        DGX_NODES=${DGX_NODES:-dgx-01}
        
        # Get Slurm controller
        read -p "Enter Slurm controller hostname [slurmctl]: " SLURM_CONTROLLER
        SLURM_CONTROLLER=${SLURM_CONTROLLER:-slurmctl}
        
        # Ask about Prometheus
        echo ""
        echo "Do you have an existing Prometheus server? (yes/no) [no]"
        read -r HAS_PROMETHEUS
        if [[ "$HAS_PROMETHEUS" =~ ^[Yy][Ee]?[Ss]?$ ]]; then
            USE_EXISTING_PROMETHEUS="true"
            read -p "Enter existing Prometheus server hostname: " PROMETHEUS_SERVER
            read -p "Enter Prometheus targets directory [/cm/shared/apps/prometheus/targets]: " PROMETHEUS_TARGETS_DIR
            PROMETHEUS_TARGETS_DIR=${PROMETHEUS_TARGETS_DIR:-/cm/shared/apps/prometheus/targets}
        else
            USE_EXISTING_PROMETHEUS="false"
            PROMETHEUS_SERVER=""
            PROMETHEUS_TARGETS_DIR="/cm/shared/apps/dcgm-exporter/prometheus-targets"
        fi
        
        # Create config directory
        mkdir -p "$(dirname "$CONFIG_FILE")"
        
        # Generate config.json
        cat > "$CONFIG_FILE" <<EOF
{
  "cluster_name": "slurm",
  "bcm_headnode": "$BCM_HEADNODE",
  "use_existing_prometheus": $USE_EXISTING_PROMETHEUS,
  "prometheus_server": "$PROMETHEUS_SERVER",
  "prometheus_targets_dir": "$PROMETHEUS_TARGETS_DIR",
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
    "configure_prometheus": false
  }
}
EOF
        echo ""
        echo "✓ Configuration file created: $CONFIG_FILE"
        echo ""
    else
        echo ""
        echo "Please create a configuration file and try again."
        echo "You can use automation/configs/config.example.json as a template."
        exit 1
    fi
fi

echo "Using configuration: $CONFIG_FILE"
echo ""

# Show configuration summary
echo "=== Configuration Summary ==="
if command_exists jq && jq empty "$CONFIG_FILE" 2>/dev/null; then
    jq -r '
        "Cluster: \(.cluster_name)",
        "BCM Headnode: \(.bcm_headnode)",
        "DGX Nodes: \(.systems.dgx_nodes | join(", "))",
        "Slurm Controller: \(.systems.slurm_controller)",
        "Use Existing Prometheus: \(.use_existing_prometheus)",
        (if .use_existing_prometheus then "Prometheus Server: \(.prometheus_server)" else empty end),
        "Prometheus Targets Dir: \(.prometheus_targets_dir)",
        "HPC Job Mapping Dir: \(.hpc_job_mapping_dir)"
    ' "$CONFIG_FILE"
else
    cat "$CONFIG_FILE"
fi
echo ""

# Ask for deployment mode
echo "=== Deployment Mode ==="
echo "1) Full automated deployment (recommended)"
echo "2) Dry-run (generate documentation without making changes)"
echo "3) Resume previous deployment"
echo ""
read -p "Select mode [1]: " MODE
MODE=${MODE:-1}

echo ""
echo "Starting DCGM Exporter deployment..."
echo ""

# Launch Python automation
cd "$SCRIPT_DIR"

case $MODE in
    1)
        echo "Running full automated deployment..."
        uv run python automation/guided_setup.py --config "$CONFIG_FILE"
        ;;
    2)
        echo "Running in dry-run mode..."
        uv run python automation/guided_setup.py --config "$CONFIG_FILE" --dry-run
        ;;
    3)
        echo "Resuming previous deployment..."
        uv run python automation/guided_setup.py --config "$CONFIG_FILE" --resume
        ;;
    *)
        echo "Invalid mode selected"
        exit 1
        ;;
esac

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "=================================================="
    echo "Deployment completed successfully!"
    echo "=================================================="
    echo ""
    echo "Next steps:"
    echo "1. Check the deployment documentation: automation/logs/guided_setup_document.md"
    echo "2. Verify DCGM exporter is running: ssh <dgx-node> 'systemctl status dcgm-exporter'"
    echo "3. Test metrics endpoint: curl http://<dgx-node>:9400/metrics"
    if grep -q '"use_existing_prometheus": false' "$CONFIG_FILE" 2>/dev/null; then
        echo "4. Configure Prometheus to scrape DCGM exporter (see documentation)"
    fi
    echo "5. Import Grafana dashboard (grafana/dcgm-dashboard.json)"
    echo ""
else
    echo "=================================================="
    echo "Deployment encountered errors"
    echo "=================================================="
    echo ""
    echo "Check the logs for details: automation/logs/"
    echo ""
    exit $EXIT_CODE
fi

