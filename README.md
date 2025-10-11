# DCGM Exporter on SuperPOD

Automated deployment of NVIDIA DCGM Exporter for BCM-managed SuperPOD environments running Slurm.

## Overview

This project provides automation to deploy DCGM Exporter as a **native system service** (not containerized) on NVIDIA DGX systems in a BCM-managed SuperPOD environment. It includes:

- **Automated deployment** scripts for building and installing DCGM exporter
- **Slurm integration** with prolog/epilog scripts for HPC job-to-GPU mapping
- **BCM role management** integration for automatic service lifecycle
- **Prometheus integration** with file-based service discovery
- **Grafana dashboards** for GPU metrics visualization

## Features

✅ **Native System Service** - Runs as systemd service, not containerized  
✅ **BCM-Integrated** - Automatic service management based on BCM roles  
✅ **Slurm-Aware** - Job IDs appear as labels in GPU metrics  
✅ **Default Metrics** - Uses NVIDIA's out-of-the-box default metrics  
✅ **Shared Storage** - Leverages `/cm/shared/` for efficiency  
✅ **Easy Scaling** - BCM imaging workflow for deployment to many nodes  
✅ **Coexists with BCM DCGM** - Works alongside existing `nvidia-dcgm` service  

## Quick Start

Deploy DCGM Exporter to your SuperPOD in 5 minutes:

```bash
# One-command deployment
./setup.sh
```

### Prerequisites

| Requirement | Details |
|------------|---------|
| **Environment** | BCM-managed SuperPOD with Slurm |
| **Location** | Run from a BCM headnode (auto-detected via `cmsh`) |
| **Access** | Root or sudo access, passwordless SSH to DGX nodes |
| **Software** | Python 3.9+ (will check), Go compiler (auto-installed) |
| **Network** | Internet access on DGX nodes to clone [NVIDIA/dcgm-exporter](https://github.com/NVIDIA/dcgm-exporter.git) |
| **Time** | ~5 minutes for first node, ~30 seconds per additional node |

### What Gets Deployed

The setup script will automatically:

✅ **Install Dependencies** - `uv` package manager, Go compiler on DGX nodes  
✅ **Clone DCGM Exporter** - From GitHub to `/opt/dcgm-exporter-deployment/` on each node  
✅ **Build from Source** - Compile and install to `/usr/bin/dcgm-exporter`  
✅ **Create Systemd Service** - Enable and start `dcgm-exporter.service`  
✅ **Configure Job Mapping** - Create `/run/dcgm-job-map/` for HPC job tracking  
✅ **Deploy Slurm Scripts** - Prolog/epilog scripts to `/cm/shared/` with symlinks  
✅ **Optional: BCM Role Monitor** - Automatic service lifecycle management  
✅ **Optional: Prometheus** - Deploy and configure Prometheus server  
✅ **Optional: Grafana** - Deploy with dashboards and datasources  

### Configuration

During setup, you'll be prompted for:

| Setting | Description | Example |
|---------|-------------|---------|
| **BCM Headnode** | Auto-detected using `cmsh` | `bcm-headnode` |
| **DGX Nodes** | Comma-separated list | `dgx-01,dgx-02,dgx-03` |
| **Slurm Controller** | Your Slurm controller hostname | `slurmctl` |
| **Prometheus** | Use existing, deploy new, or skip | Choose option |
| **Grafana** | Use existing, deploy new, or skip | Choose option |

Configuration is saved to `automation/configs/config.json` and can be reused or modified.

### Quick Verification

After deployment completes:

```bash
# Check service status
ssh dgx-01 "systemctl status dcgm-exporter"

# Test metrics endpoint
curl http://dgx-01:9400/metrics | head -20

# Submit GPU job and verify job labeling
srun --gpus=1 nvidia-smi
curl http://dgx-01:9400/metrics | grep hpc_job

# Access Grafana (if deployed)
# http://<grafana-server>:3000 (admin/admin)
```

## Architecture

### Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **DCGM Exporter** | `/usr/local/bin/dcgm-exporter` | Exports GPU metrics in Prometheus format |
| **Systemd Service** | `/etc/systemd/system/dcgm-exporter.service` | Manages DCGM exporter lifecycle |
| **Prolog Script** | `/cm/shared/apps/slurm/var/cm/prolog-dcgm.sh` | Creates GPU-to-job mappings at job start |
| **Epilog Script** | `/cm/shared/apps/slurm/var/cm/epilog-dcgm.sh` | Removes GPU-to-job mappings at job end |
| **BCM Role Monitor** | `/usr/local/bin/bcm_role_monitor_dcgm.py` | Manages services based on BCM roles |
| **Prometheus Targets** | `/cm/shared/apps/dcgm-exporter/prometheus-targets/` | Service discovery files |

### How It Works

1. **DCGM Exporter** runs as a system service on each DGX node
2. **Slurm prolog** creates mapping files (`/run/dcgm-job-map/<gpu_id>`) when jobs start
3. **DCGM Exporter** reads these mappings and adds `hpcjob` labels to metrics
4. **BCM Role Monitor** automatically starts/stops services based on `slurmclient` role
5. **Prometheus** discovers targets via JSON files in shared storage
6. **Grafana** visualizes GPU metrics with job information

## Metrics

DCGM Exporter provides detailed GPU metrics including:

- **Clocks**: SM and memory clock frequencies
- **Temperature**: GPU and memory temperature
- **Power**: Power usage and total energy consumption
- **Utilization**: GPU, memory copy, encoder, decoder utilization
- **Memory**: Framebuffer free, used, and reserved
- **Errors**: XID errors, PCIe replay counter
- **HPC Jobs**: Slurm job IDs as metric labels (when configured)

Default metrics configuration: `/etc/dcgm-exporter/default-counters.csv`

## Dependencies

### External Dependencies

**NVIDIA DCGM Exporter** - This project **does not include** the dcgm-exporter source code.

- **Source**: https://github.com/NVIDIA/dcgm-exporter
- **License**: Apache 2.0 (compatible with this project)
- **Deployment**: Automatically cloned from GitHub to `/opt/dcgm-exporter-deployment/dcgm-exporter` on each DGX node during deployment
- **Why not included?**:
  - Ensures you always get the latest version
  - Clear separation of upstream and automation code
  - Keeps this repository small and focused
  - No license mixing concerns

### System Dependencies

These are automatically installed or already present:

**On DGX Nodes:**
- **Go compiler** (`golang-go`) - Auto-installed for building dcgm-exporter
- **Git** - For cloning repositories
- **NVIDIA Drivers** - Already present on DGX systems
- **DCGM Libraries** - Already present (`nvidia-dcgm.service`)
- **Systemd** - Service management

**On Deployment Machine:**
- **Python 3.9+** - For running automation scripts
- **SSH** - For remote deployment
- **uv** - Python package manager (auto-installed by `setup.sh`)

### Python Dependencies

Managed by `uv` via `pyproject.toml`:
- `requests>=2.31.0` - For HTTP API calls (BCM, Prometheus, Grafana)

Automatically installed when you run `./setup.sh`.

### Network Dependencies

**During Deployment:**
- GitHub access to clone dcgm-exporter
- APT package repositories for Go compiler and system packages
- SSH access between deployment machine and DGX nodes

**After Deployment:**
- DGX nodes expose port 9400 for Prometheus scraping
- BCM role monitor needs port 8081 access to BCM headnode (if enabled)

### Offline Deployment

For air-gapped environments:

1. Pre-download dcgm-exporter and place in project root:
   ```bash
   git clone https://github.com/NVIDIA/dcgm-exporter.git
   ```

2. Pre-download Go packages:
   ```bash
   cd dcgm-exporter && go mod download
   ```

3. The deployment script will automatically detect and use the local copy instead of cloning from GitHub.

**Note**: After successful deployment, temporary build directories are automatically cleaned up to save disk space.

### Updating Dependencies

**Update DCGM Exporter to Latest Version:**
```bash
# Re-run deployment to get the latest version
./setup.sh

# This will:
# 1. Clone the latest dcgm-exporter from GitHub
# 2. Build and install the updated version
# 3. Restart the service
# 4. Clean up temporary files
```

**Update Python Dependencies:**
```bash
# Edit pyproject.toml if needed
uv sync
```

## Integration with Prometheus

### Option 1: Automatic (with BCM Role Monitor)

The BCM role monitor automatically manages Prometheus target files:

```yaml
scrape_configs:
  - job_name: 'dcgm_exporter'
    file_sd_configs:
      - files:
          - '/cm/shared/apps/dcgm-exporter/prometheus-targets/*.json'
        refresh_interval: 30s
```

### Option 2: Manual (static configuration)

```yaml
scrape_configs:
  - job_name: 'dcgm_exporter'
    static_configs:
      - targets:
          - 'dgx-01:9400'
          - 'dgx-02:9400'
```

See `docs/prometheus-config-sample.yml` for complete examples.

## Grafana Dashboards

Import the official NVIDIA DCGM-Exporter dashboard:

- Dashboard ID: 12239
- JSON file: `grafana/dcgm-dashboard.json` (to be downloaded)
- URL: https://grafana.com/grafana/dashboards/12239

## Deployment Options

### 1. Full Automated Deployment

```bash
./setup.sh
# Select mode 1 (Full automated deployment)
```

### 2. Dry-Run (Documentation Only)

```bash
./setup.sh
# Select mode 2 (Dry-run)
# Generates documentation without making changes
```

### 3. Manual Deployment

```bash
# Deploy to specific nodes
python automation/deploy_dcgm_exporter.py \
    --dgx-nodes dgx-01 dgx-02

# Deploy using config file
python automation/deploy_dcgm_exporter.py \
    --config automation/configs/config.json
```

## BCM Imaging Workflow

After successful deployment on representative nodes:

```bash
# Capture image
source /etc/profile.d/modules.sh
module load cmsh
cmsh -c 'device;use dgx-01;grabimage -w'

# Deploy image to additional nodes
cmsh -c 'device;use dgx-02;set softwareimage dgx-01;commit'
```

## Slurm Prolog/Epilog Integration

The automation creates symlinks following BCM's pattern:

```bash
# On each node that runs Slurm jobs
/cm/local/apps/slurm/var/prologs/60-prolog-dcgm.sh -> /cm/shared/apps/slurm/var/cm/prolog-dcgm.sh
/cm/local/apps/slurm/var/epilogs/60-epilog-dcgm.sh -> /cm/shared/apps/slurm/var/cm/epilog-dcgm.sh
```

Scripts automatically:
- Create `/run/dcgm-job-map/<gpu_id>` files at job start
- Add job IDs to GPU mapping files
- Remove job IDs at job completion

## Troubleshooting

### Check DCGM Exporter Status

```bash
# Check service status
ssh <dgx-node> "systemctl status dcgm-exporter"

# Check metrics endpoint
curl http://<dgx-node>:9400/metrics | head -20

# View logs
ssh <dgx-node> "journalctl -u dcgm-exporter -n 50"
```

### Verify Job Mapping

```bash
# Submit a GPU job
srun --gpus=1 --pty bash

# On the compute node, check mapping
ls -la /run/dcgm-job-map/
cat /run/dcgm-job-map/0  # Should show your job ID

# Check metrics for job label
curl http://localhost:9400/metrics | grep hpcjob
```

### Common Issues

**DCGM exporter fails to start:**
- Check if `nvidia-dcgm` service is running: `systemctl status nvidia-dcgm`
- Verify GPU access: `nvidia-smi`
- Check logs: `journalctl -u dcgm-exporter -n 100`

**No job labels in metrics:**
- Verify prolog/epilog symlinks exist
- Check `/run/dcgm-job-map/` directory exists
- Ensure `--hpc-job-mapping-dir` is set in service file
- Check Slurm logs: `/var/log/slurm/dcgm-prolog.log`

**Prometheus not discovering targets:**
- Verify target files exist: `ls /cm/shared/apps/dcgm-exporter/prometheus-targets/`
- Check Prometheus config for correct `file_sd_configs` path
- Reload Prometheus: `curl -X POST http://prometheus:9090/-/reload`

## File Structure

```
superpod-dcgm-exporter/
├── setup.sh                          # Main setup script
├── pyproject.toml                    # Python dependencies (uv)
├── README.md                         # This file
├── automation/
│   ├── deploy_dcgm_exporter.py      # Main deployment script
│   ├── configs/
│   │   ├── config.example.json      # Example configuration
│   │   └── config.existing-prometheus.json
│   ├── role-monitor/
│   │   ├── bcm_role_monitor.py      # BCM role monitor
│   │   └── bcm-role-monitor-dcgm.service
│   ├── tools/
│   │   ├── test_deployment.py       # Automated testing
│   │   └── README.md
│   └── README.md                    # Automation documentation
├── systemd/
│   └── dcgm-exporter.service        # Systemd service file
├── slurm/
│   ├── prolog.d/
│   │   └── dcgm_job_map.sh          # Slurm prolog for job mapping
│   └── epilog.d/
│       └── dcgm_job_map.sh          # Slurm epilog for cleanup
├── grafana/
│   ├── dcgm-single-job-stats.json   # Per-job dashboard
│   └── README.md                    # Dashboard documentation
└── docs/
    ├── How-To-Guide.md              # Manual deployment guide
    ├── Troubleshooting.md           # Problem solving
    ├── DCGM-Compatibility.md        # Version information
    └── prometheus-config-sample.yml # Sample Prometheus config

# Note: dcgm-exporter/ directory (NVIDIA's source) is NOT included
# It's automatically cloned during deployment to /opt/dcgm-exporter-deployment/
```

## Configuration Files

### Main Configuration (`automation/configs/config.json`)

```json
{
  "cluster_name": "slurm",
  "bcm_headnode": "bcm-01",
  "use_existing_prometheus": false,
  "prometheus_targets_dir": "/cm/shared/apps/dcgm-exporter/prometheus-targets",
  "dcgm_exporter_port": 9400,
  "hpc_job_mapping_dir": "/run/dcgm-job-map",
  "systems": {
    "dgx_nodes": ["dgx-01", "dgx-02"],
    "slurm_controller": "slurmctl"
  },
  "deployment_options": {
    "deploy_dcgm_exporter": true,
    "deploy_slurm_prolog_epilog": true,
    "deploy_bcm_role_monitor": true,
    "configure_prometheus": false
  }
}
```

## Additional Resources

- [NVIDIA DCGM Exporter Documentation](https://docs.nvidia.com/datacenter/cloud-native/gpu-telemetry/dcgm-exporter.html)
- [DCGM Exporter GitHub](https://github.com/NVIDIA/dcgm-exporter)
- [Grafana Dashboard #12239](https://grafana.com/grafana/dashboards/12239)
- [BCM Documentation](.bcm-documentation/)

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review deployment logs in `automation/logs/`
3. Check service logs: `journalctl -u dcgm-exporter`
4. Verify configuration files

## License

This deployment automation is provided as-is for use with NVIDIA products. Please refer to the DCGM Exporter repository for licensing information.

## Credits

Based on patterns from the [Jobstats on SuperPOD](Jobstats-on-SuperPOD/) deployment automation.

