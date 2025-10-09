# Project Dependencies

## External Dependencies

### NVIDIA DCGM Exporter

This project automates the deployment of NVIDIA's DCGM Exporter but does **not include** the dcgm-exporter source code.

**Source**: [https://github.com/NVIDIA/dcgm-exporter](https://github.com/NVIDIA/dcgm-exporter)

**How it's used**:
- The deployment script automatically clones dcgm-exporter from GitHub **on target DGX nodes**
- Cloned to `/opt/dcgm-exporter-deployment/dcgm-exporter` on each node
- Built from source during deployment
- Not included in this repository

**Deployment behavior**:
```python
# From automation/deploy_dcgm_exporter.py
if dcgm_source.exists():
    # Development: Use local copy if present
    logger.info("Copying DCGM exporter source...")
else:
    # Production: Clone from GitHub
    logger.info("Cloning DCGM exporter from GitHub...")
    self.ssh_command(
        node,
        "cd /opt/dcgm-exporter-deployment && "
        "git clone https://github.com/NVIDIA/dcgm-exporter.git"
    )
```

### Why Not Included?

1. **Separation of Concerns**: dcgm-exporter is NVIDIA's upstream project
2. **Always Current**: Cloning ensures customers get the latest version
3. **License Clarity**: No license mixing
4. **Repo Size**: Keeps this automation repo small
5. **Updates**: Easy to update by re-running deployment

## Python Dependencies

Managed by `uv` via `pyproject.toml`:

```toml
dependencies = [
    "requests>=2.31.0",
]
```

**Installation**:
```bash
# Automatic via setup.sh
./setup.sh

# Manual
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

## System Dependencies

Installed automatically during deployment:

### On DGX Nodes
- **Go compiler** (`golang-go`) - For building dcgm-exporter
- **Git** - For cloning repositories
- **NVIDIA drivers** - Already present on DGX
- **DCGM libraries** - Already present on DGX (nvidia-dcgm service)

### On Deployment Machine
- **Python 3.8+** - For running automation scripts
- **SSH** - For remote deployment
- **Git** - For version control

## Reference Materials (Not in Repo)

These directories are present in the lab environment for reference but **excluded from git**:

### `.bcm-documentation/`
- BCM product documentation
- Used for understanding BCM patterns
- Not distributed with this project

### `Jobstats-on-SuperPOD/`
- Previous successful deployment project
- Used as a pattern reference
- Not a dependency, just inspiration

### `dcgm-exporter/`
- Local copy for development/testing
- Not required for deployment
- Ignored by git

## Build-Time Dependencies

During DCGM exporter build:
- **Go 1.24+** - Required by dcgm-exporter
- **DCGM SDK** - Already installed on DGX via NVIDIA packages
- **Make** - Build automation

## Runtime Dependencies

On DGX nodes after deployment:
- **nvidia-dcgm.service** - DCGM daemon (already present on DGX)
- **systemd** - Service management
- **Slurm** - For prolog/epilog integration (already present)

## Network Dependencies

During deployment:
- **GitHub access** - To clone dcgm-exporter
- **Package repositories** - For apt packages
- **SSH access** - Between deployment machine and DGX nodes

## Verification

Check all dependencies are available:

```bash
# On deployment machine
./setup.sh  # Checks and installs uv

# On DGX nodes (checked during deployment)
go version
git --version
nvidia-smi
systemctl status nvidia-dcgm
```

## Updating Dependencies

### Update DCGM Exporter

```bash
# Re-run deployment to get latest version
./setup.sh

# Or manually on a node
ssh dgx-01
cd /opt/dcgm-exporter-deployment/dcgm-exporter
git pull
make binary && make install
systemctl restart dcgm-exporter
```

### Update Python Dependencies

```bash
# Edit pyproject.toml
vim pyproject.toml

# Update
uv sync
```

## Offline Deployment

For air-gapped environments:

1. **Pre-download dcgm-exporter**:
   ```bash
   git clone https://github.com/NVIDIA/dcgm-exporter.git
   # Place in deployment directory
   ```

2. **Pre-download Go packages**:
   ```bash
   cd dcgm-exporter
   go mod download
   ```

3. **Package everything**:
   ```bash
   tar -czf dcgm-exporter-offline.tar.gz dcgm-exporter/
   ```

4. **Deploy**: The deployment script will detect local copy and use it

## License Compatibility

- **This project**: Apache 2.0 (or your chosen license)
- **DCGM Exporter**: Apache 2.0
- **Compatible**: ✅ Both are Apache 2.0

## Support

If dependency issues occur:

1. **Check network**: Can DGX nodes reach GitHub?
2. **Check Go**: Is Go compiler installed?
3. **Check DCGM**: Is nvidia-dcgm service running?
4. **Manual clone**: Try cloning dcgm-exporter manually
5. **Check logs**: Review deployment logs in `automation/logs/`

## See Also

- [README.md](README.md) - Main project documentation
- [How-To-Guide.md](docs/How-To-Guide.md) - Deployment instructions
- [DCGM Exporter GitHub](https://github.com/NVIDIA/dcgm-exporter) - Upstream project

