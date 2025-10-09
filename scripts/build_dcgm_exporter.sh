#!/bin/bash
#
# Build DCGM Exporter from Source
# This script builds dcgm-exporter binary on a DGX node
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DCGM_REPO_DIR="${DCGM_REPO_DIR:-$PROJECT_ROOT/dcgm-exporter}"
INSTALL_DIR="${INSTALL_DIR:-/usr/local/bin}"
CONFIG_DIR="${CONFIG_DIR:-/etc/dcgm-exporter}"

echo "=== Building DCGM Exporter ==="
echo "DCGM Repository: $DCGM_REPO_DIR"
echo "Install Directory: $INSTALL_DIR"
echo "Config Directory: $CONFIG_DIR"
echo ""

# Check if dcgm-exporter repo exists
if [ ! -d "$DCGM_REPO_DIR" ]; then
    echo "Error: DCGM exporter repository not found at $DCGM_REPO_DIR"
    echo "Expected to find the dcgm-exporter directory in the project root"
    exit 1
fi

# Check for Go
if ! command -v go &> /dev/null; then
    echo "Go compiler not found. Please install Go 1.24 or later."
    echo "On Ubuntu/Debian: apt install golang-go"
    exit 1
fi

GO_VERSION=$(go version | awk '{print $3}' | sed 's/go//')
echo "Found Go version: $GO_VERSION"
echo ""

# Build the binary
echo "Building dcgm-exporter..."
cd "$DCGM_REPO_DIR/cmd/dcgm-exporter"
go build -ldflags "-X main.BuildVersion=$(cat ../../hack/VERSION | head -1)"

if [ ! -f "dcgm-exporter" ]; then
    echo "Error: Build failed, dcgm-exporter binary not found"
    exit 1
fi

echo "✓ Build successful"
echo ""

# Install binary
echo "Installing dcgm-exporter to $INSTALL_DIR..."
install -m 755 dcgm-exporter "$INSTALL_DIR/dcgm-exporter"
echo "✓ Binary installed"
echo ""

# Install configuration
echo "Installing default configuration to $CONFIG_DIR..."
mkdir -p "$CONFIG_DIR"
install -m 644 "$DCGM_REPO_DIR/etc/default-counters.csv" "$CONFIG_DIR/default-counters.csv"
echo "✓ Configuration installed"
echo ""

# Verify installation
if [ -f "$INSTALL_DIR/dcgm-exporter" ]; then
    echo "=== Installation Complete ==="
    echo "Binary: $INSTALL_DIR/dcgm-exporter"
    echo "Config: $CONFIG_DIR/default-counters.csv"
    echo ""
    echo "Version:"
    "$INSTALL_DIR/dcgm-exporter" --version || echo "  (Version info not available)"
    echo ""
    echo "Next steps:"
    echo "1. Install systemd service: cp systemd/dcgm-exporter.service /etc/systemd/system/"
    echo "2. Create job mapping directory: mkdir -p /run/dcgm-job-map"
    echo "3. Enable service: systemctl enable dcgm-exporter"
    echo "4. Start service: systemctl start dcgm-exporter"
else
    echo "Error: Installation verification failed"
    exit 1
fi

