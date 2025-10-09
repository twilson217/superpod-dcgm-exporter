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

### Prerequisites

- BCM-managed SuperPOD with Slurm
- NVIDIA DGX nodes with GPUs
- Passwordless SSH access to all nodes
- Python 3.8+ on the deployment machine
- Go compiler will be installed automatically if needed
- Internet access on DGX nodes (to clone [NVIDIA/dcgm-exporter](https://github.com/NVIDIA/dcgm-exporter.git))

### Basic Deployment

```bash
# Clone this repository
git clone <repo-url>
cd superpod-dcgm-exporter

# Run the setup script
./setup.sh
```

The setup script will:
1. Install `uv` package manager if needed
2. Guide you through configuration
3. Launch automated deployment
4. Clone [NVIDIA dcgm-exporter](https://github.com/NVIDIA/dcgm-exporter.git) on target nodes
5. Build and deploy DCGM exporter to all DGX nodes
6. Install Slurm prolog/epilog scripts
7. Optionally deploy BCM role monitor

**Note**: The NVIDIA dcgm-exporter repository is cloned automatically during deployment and is not included in this project.

### Configuration

During setup, you'll be asked:

- **BCM headnode hostname** - Your BCM head node
- **DGX nodes** - Comma-separated list of DGX nodes
- **Slurm controller** - Your Slurm controller node
- **Existing Prometheus?** - Whether you have an existing Prometheus server

Configuration is saved to `automation/configs/config.json` and can be modified later.

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
uv run python automation/role-monitor/deploy_dcgm_exporter.py \
    --dgx-nodes dgx-01 dgx-02

# Deploy using config file
uv run python automation/role-monitor/deploy_dcgm_exporter.py \
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
│   ├── configs/
│   │   ├── config.example.json      # Example configuration
│   │   └── config.existing-prometheus.json
│   ├── role-monitor/
│   │   ├── bcm_role_monitor_dcgm.py  # BCM role monitor
│   │   └── deploy_dcgm_exporter.py   # Deployment script
│   └── logs/                         # Deployment logs
├── systemd/
│   └── dcgm-exporter.service        # Systemd service file
├── slurm/
│   ├── prolog.d/
│   │   └── dcgm_job_map.sh          # Slurm prolog for job mapping
│   └── epilog.d/
│       └── dcgm_job_map.sh          # Slurm epilog for cleanup
├── scripts/
│   └── build_dcgm_exporter.sh       # Build script
├── docs/
│   └── prometheus-config-sample.yml  # Sample Prometheus config
└── dcgm-exporter/                    # NVIDIA DCGM exporter source (git submodule or copy)
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

