# Grafana Dashboards

This directory contains custom Grafana dashboards for DCGM metrics visualization.

## Available Dashboards

### 1. DCGM Single Job Stats (`dcgm-single-job-stats.json`)

**Purpose**: View GPU metrics for a specific Slurm job.

**Features**:
- **Job ID Input**: Enter any Slurm job number to filter metrics
- **Real-time Monitoring**: 5-second refresh rate for live job monitoring
- **Comprehensive GPU Metrics**:
  - GPU Utilization (%)
  - GPU Temperature (°C)
  - Power Usage (W)
  - Memory Usage (Used/Free)
  - Memory Copy Utilization
  - Clock Speeds (SM and Memory)
  - GPU Engine Activity
  - PCIe Bandwidth (TX/RX)
- **Summary Table**: Quick overview of all GPUs assigned to the job
- **Multi-GPU Support**: Visualizes all GPUs allocated to the job across all nodes

**Access**: 
```
http://prometheus:3000/d/dcgm-single-job/dcgm-single-job-stats
```

**How to Use**:
1. Navigate to the dashboard
2. Enter your Slurm Job ID in the "Slurm Job ID" field at the top
3. View real-time GPU metrics for your running job
4. Use the time range selector to view historical data for completed jobs

**Requirements**:
- HPC job mapping must be enabled on DCGM Exporter (configured automatically by deployment script)
- Slurm prolog/epilog scripts must be active (deployed to `/cm/shared/slurm/prolog.d/` and `/cm/shared/slurm/epilog.d/`)
- Job must have GPU allocations

### 2. NVIDIA DCGM Exporter Dashboard

The default dashboard from NVIDIA's DCGM Exporter repository is also deployed automatically. This dashboard provides cluster-wide GPU monitoring without job-specific filtering.

**Source**: https://github.com/NVIDIA/dcgm-exporter/blob/main/grafana/dcgm-exporter-dashboard.json

## Deployment

These dashboards are automatically deployed when you run `setup.sh` and choose to deploy Grafana.

To manually deploy or update dashboards:

```bash
# Copy to Grafana dashboards directory
scp grafana/*.json <grafana-server>:/var/lib/grafana/dashboards/

# Fix permissions
ssh <grafana-server> "chown -R grafana:grafana /var/lib/grafana/dashboards"
```

Grafana will automatically detect and load dashboards within 10 seconds.

## Customization

You can modify these dashboards:
1. In Grafana UI: Edit and save changes (enable "allowUiUpdates" in provisioning config)
2. Export JSON: Dashboard Settings → JSON Model → Copy to file
3. Version control your customizations in this directory

## Metrics Reference

All dashboards use DCGM metrics with the following labels:
- `hostname`: DGX node hostname
- `gpu`: GPU index (0-7 for DGX A100)
- `Slurm_job`: Slurm job ID (when HPC job mapping is enabled)
- `UUID`: GPU UUID
- `device`: GPU device name

Common DCGM metrics:
- `DCGM_FI_DEV_GPU_UTIL`: GPU utilization percentage
- `DCGM_FI_DEV_GPU_TEMP`: GPU temperature in Celsius
- `DCGM_FI_DEV_POWER_USAGE`: Power consumption in Watts
- `DCGM_FI_DEV_FB_USED`: GPU framebuffer memory used
- `DCGM_FI_DEV_FB_FREE`: GPU framebuffer memory free
- `DCGM_FI_DEV_MEM_COPY_UTIL`: Memory copy utilization
- `DCGM_FI_DEV_SM_CLOCK`: SM clock frequency (MHz)
- `DCGM_FI_DEV_MEM_CLOCK`: Memory clock frequency (MHz)
- `DCGM_FI_PROF_GR_ENGINE_ACTIVE`: Graphics engine active time
- `DCGM_FI_PROF_PCIE_TX_BYTES`: PCIe bytes transmitted
- `DCGM_FI_PROF_PCIE_RX_BYTES`: PCIe bytes received

For a complete list of available DCGM metrics, see:
https://docs.nvidia.com/datacenter/dcgm/latest/dcgm-api/dcgm-api-field-ids.html

