# Automation Scripts

This directory contains automation scripts for deploying DCGM Exporter on BCM-managed SuperPOD.

## Quick Start

From the project root:
```bash
./setup.sh
```

## Scripts

### Primary Entry Point

**`../setup.sh`** - Main deployment script
- Interactive configuration
- Dependency management (uv)
- Launches Python automation
- Multiple modes: full/dry-run/resume

### Deployment Scripts

**`deploy_dcgm_exporter.py`** - Main deployment script for DGX nodes
```bash
# Deploy to specific nodes
python automation/deploy_dcgm_exporter.py \
  --dgx-nodes dgx-01 dgx-02

# Deploy using config file
python automation/deploy_dcgm_exporter.py \
  --config automation/configs/config.json
```

**`role-monitor/bcm_role_monitor_dcgm.py`** - BCM role monitoring service
- Runs on each DGX node
- Manages services based on BCM roles
- Handles Prometheus target files
- Deployed automatically by setup.sh

### Build Scripts

**`../scripts/build_dcgm_exporter.sh`** - Build DCGM exporter
- Called automatically during deployment
- Can be run manually if needed

## Configuration Files

### `configs/config.example.json`
Example configuration for new deployments:
- No existing Prometheus
- Default paths
- Basic setup

### `configs/config.existing-prometheus.json`
Example for environments with existing Prometheus:
- Custom Prometheus targets directory
- Integration with existing monitoring

### Creating Your Config

```bash
cp configs/config.example.json configs/config.json
# Edit config.json with your values
```

Or let `setup.sh` create it interactively.

## Directory Structure

```
automation/
├── README.md                      # This file
├── configs/
│   ├── config.example.json       # New deployment example
│   └── config.existing-prometheus.json  # Existing Prometheus example
├── role-monitor/
│   ├── bcm_role_monitor_dcgm.py  # Role monitoring service
│   ├── deploy_dcgm_exporter.py   # Main deployment automation
├── tools/                         # Future: testing/validation scripts
└── logs/                          # Deployment logs (generated)
```

## Usage Modes

### 1. Automated (Recommended)
```bash
./setup.sh
# Select: Full automated deployment
```

### 2. Dry-Run
```bash
./setup.sh
# Select: Dry-run
# Generates documentation without changes
```

### 3. Resume
```bash
./setup.sh
# Select: Resume
# Continues interrupted deployment
```

### 4. Manual Python Scripts
```bash
# Install dependencies first
uv sync

# Run deployment directly
python automation/deploy_dcgm_exporter.py \
  --config automation/configs/config.json \
  --verbose
```

## Configuration Parameters

Key parameters in `config.json`:

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
  }
}
```

## Dependencies

Managed by `uv` via `../pyproject.toml`:
- Python 3.8+
- requests (for BCM API)

Install:
```bash
uv sync
```

## Logs

Deployment logs are saved to:
```
automation/logs/
├── guided_setup_document.md    # Deployment documentation
└── guided_setup_progress.json  # Progress tracking
```

## Troubleshooting

If deployment fails:

1. **Check logs**: `automation/logs/`
2. **Verify SSH**: Passwordless SSH to all nodes
3. **Check permissions**: Root/sudo access required
4. **Review config**: Ensure all hostnames are correct
5. **Network**: Verify connectivity to BCM headnode and DGX nodes

## Manual Deployment

If automation fails, follow manual steps in:
- `docs/How-To-Guide.md` - Complete manual deployment guide

## Testing

After deployment, verify:

```bash
# Check service on DGX node
ssh dgx-01 "systemctl status dcgm-exporter"

# Test metrics
curl http://dgx-01:9400/metrics | head -20

# Verify Prometheus targets
ls -la /cm/shared/apps/dcgm-exporter/prometheus-targets/
```

## Next Steps

After successful deployment:

1. **Configure Prometheus** - See `../docs/prometheus-config-sample.yml`
2. **Import Grafana Dashboard** - Dashboard ID: 12239
3. **Scale with BCM** - See `../docs/BCM-Imaging-Workflow.md`

## Support

For issues:
1. Check `../docs/Troubleshooting.md`
2. Review deployment logs
3. Run diagnostic commands from documentation

