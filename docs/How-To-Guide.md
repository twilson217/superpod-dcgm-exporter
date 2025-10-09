# DCGM Exporter on SuperPOD - How-To Guide

Complete step-by-step guide for deploying DCGM Exporter in BCM-managed SuperPOD environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Manual Deployment](#manual-deployment)
4. [Slurm Integration](#slurm-integration)
5. [BCM Role Monitor Setup](#bcm-role-monitor-setup)
6. [Prometheus Configuration](#prometheus-configuration)
7. [Grafana Dashboards](#grafana-dashboards)
8. [Verification](#verification)
9. [BCM Imaging Workflow](#bcm-imaging-workflow)

## Prerequisites

### System Requirements

- BCM-managed SuperPOD environment
- NVIDIA DGX nodes with GPUs
- Slurm workload manager
- Linux with systemd
- Python 3.8+ on deployment machine

### Access Requirements

- Root or sudo access on all nodes
- Passwordless SSH to all target nodes
- Access to BCM headnode (for role monitor)
- BCM admin certificates (for role monitor)

### Network Requirements

- DGX nodes can reach each other
- Prometheus server can reach DGX nodes on port 9400
- If using BCM role monitor: DGX nodes can reach BCM headnode on port 8081

## Quick Start

### 1. Clone Repository

```bash
git clone <repo-url>
cd superpod-dcgm-exporter
```

### 2. Run Setup Script

```bash
./setup.sh
```

The setup script will:
- Install `uv` package manager (if needed)
- Create configuration file (if needed)
- Launch automated deployment

### 3. Follow Prompts

Answer configuration questions:
- BCM headnode hostname
- DGX node list
- Slurm controller hostname
- Existing Prometheus (yes/no)

### 4. Select Deployment Mode

1. **Full automated** - Deploy everything automatically
2. **Dry-run** - Generate documentation only
3. **Resume** - Continue interrupted deployment

### 5. Verify Deployment

```bash
# Check service on a DGX node
ssh dgx-01 "systemctl status dcgm-exporter"

# Test metrics
curl http://dgx-01:9400/metrics | head -20
```

## Manual Deployment

If you prefer manual control or need to customize the deployment:

### Step 1: Build DCGM Exporter on DGX Node

```bash
# SSH to first DGX node
ssh dgx-01

# Install Go if needed
apt update && apt install -y golang-go

# Create working directory
mkdir -p /opt/dcgm-exporter-deployment
cd /opt/dcgm-exporter-deployment

# Clone DCGM exporter
git clone https://github.com/NVIDIA/dcgm-exporter.git
cd dcgm-exporter

# Build binary
make binary

# Install
make install

# Verify installation
/usr/local/bin/dcgm-exporter --version
ls -l /etc/dcgm-exporter/default-counters.csv
```

### Step 2: Create Job Mapping Directory

```bash
# Create directory for HPC job mappings
mkdir -p /run/dcgm-job-map
chmod 755 /run/dcgm-job-map
```

### Step 3: Install Systemd Service

```bash
# Copy service file from deployment machine
scp systemd/dcgm-exporter.service dgx-01:/tmp/

# On DGX node: Install service
ssh dgx-01 << 'EOF'
  mv /tmp/dcgm-exporter.service /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable dcgm-exporter
  systemctl start dcgm-exporter
EOF

# Verify
ssh dgx-01 "systemctl status dcgm-exporter"
```

### Step 4: Test Metrics

```bash
# Test metrics endpoint
curl http://dgx-01:9400/metrics | head -50

# Look for DCGM metrics
curl http://dgx-01:9400/metrics | grep -E "DCGM_FI_DEV_(GPU_TEMP|GPU_UTIL)" | head -10
```

### Step 5: Repeat for Other Nodes

```bash
# Use a loop for multiple nodes
for node in dgx-02 dgx-03 dgx-04; do
  echo "Deploying to $node..."
  # Repeat steps 1-4 for each node
done
```

## Slurm Integration

### Step 1: Deploy Scripts to Shared Storage

```bash
# On Slurm controller or any node with /cm/shared access
SHARED_DIR="/cm/shared/apps/slurm/var/cm"

# Copy prolog script
cp slurm/prolog.d/dcgm_job_map.sh $SHARED_DIR/prolog-dcgm.sh
chmod +x $SHARED_DIR/prolog-dcgm.sh

# Copy epilog script
cp slurm/epilog.d/dcgm_job_map.sh $SHARED_DIR/epilog-dcgm.sh
chmod +x $SHARED_DIR/epilog-dcgm.sh
```

### Step 2: Create Symlinks on Each Compute Node

```bash
# On each DGX node that runs Slurm jobs
PROLOG_DIR="/cm/local/apps/slurm/var/prologs"
EPILOG_DIR="/cm/local/apps/slurm/var/epilogs"

# Create directories if they don't exist
mkdir -p $PROLOG_DIR $EPILOG_DIR

# Create symlinks (60- prefix for execution order)
ln -sf /cm/shared/apps/slurm/var/cm/prolog-dcgm.sh \
    $PROLOG_DIR/60-prolog-dcgm.sh

ln -sf /cm/shared/apps/slurm/var/cm/epilog-dcgm.sh \
    $EPILOG_DIR/60-epilog-dcgm.sh

# Verify
ls -l $PROLOG_DIR/60-prolog-dcgm.sh
ls -l $EPILOG_DIR/60-epilog-dcgm.sh
```

### Step 3: Verify Slurm Configuration

```bash
# Check that BCM's generic prolog/epilog is configured
cmsh -c "wlm; show" | grep -E "(Prolog|Epilog)"

# Should see:
# Prolog: /cm/local/apps/cmd/scripts/prolog
# Epilog: /cm/local/apps/cmd/scripts/epilog

# These generic scripts will call all scripts in the prologs/ and epilogs/ directories
```

### Step 4: Test with a Job

```bash
# Submit a test GPU job
srun --gpus=1 --pty bash

# On the compute node, check mapping was created
ls -l /run/dcgm-job-map/
cat /run/dcgm-job-map/0  # Should show your job ID

# Check metrics include job label
curl http://localhost:9400/metrics | grep "hpcjob" | head -5

# Exit the job
exit

# Verify mapping was cleaned up
ssh <compute-node> "ls /run/dcgm-job-map/"
```

## BCM Role Monitor Setup

BCM role monitor automatically manages DCGM exporter service based on BCM role assignments.

### Step 1: Get BCM Admin Certificates

```bash
# On BCM headnode, locate admin certificates
ls -l /root/.cm/cmsh/admin.pem
ls -l /root/.cm/cmsh/admin.key

# Copy to deployment machine
scp bcm-headnode:/root/.cm/cmsh/admin.* .
```

### Step 2: Deploy Role Monitor to DGX Nodes

```bash
# Deploy using automation script
python automation/deploy_dcgm_exporter.py \
  --config automation/configs/config.json

# Or deploy manually to specific nodes
python automation/deploy_dcgm_exporter.py \
  --dgx-nodes dgx-01 dgx-02 dgx-03
```

### Step 3: Verify Role Monitor

```bash
# Check service status
ssh dgx-01 "systemctl status bcm-role-monitor"

# View logs
ssh dgx-01 "journalctl -u bcm-role-monitor -n 50"

# Check if node has slurmclient role
cmsh -c "device; use dgx-01; show roles"
```

### Step 4: Test Role Changes

```bash
# Add slurmclient role (if not already present)
cmsh -c "device; use dgx-01; roles; append slurmclient; commit"

# Within 60 seconds, check that services started
ssh dgx-01 "systemctl status dcgm-exporter"

# Check Prometheus target file was created
ls -l /cm/shared/apps/dcgm-exporter/prometheus-targets/dgx-01.json

# Remove role to test cleanup
cmsh -c "device; use dgx-01; roles; remove slurmclient; commit"

# Within 60 seconds, check that service stopped
ssh dgx-01 "systemctl status dcgm-exporter"
```

## Prometheus Configuration

### Option 1: File-Based Service Discovery (Recommended)

Add to `/etc/prometheus/prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'dcgm_exporter'
    file_sd_configs:
      - files:
          - '/cm/shared/apps/dcgm-exporter/prometheus-targets/*.json'
        refresh_interval: 30s
    relabel_configs:
      - source_labels: [job]
        regex: 'dcgm_exporter'
        action: keep
    metric_relabel_configs:
      - target_label: cluster
        replacement: slurm
      - source_labels: [__name__]
        regex: '^go_.*'
        action: drop
```

Reload Prometheus:
```bash
curl -X POST http://prometheus:9090/-/reload
```

Verify targets:
```bash
# Check targets page
http://prometheus:9090/targets

# Or via API
curl http://prometheus:9090/api/v1/targets | \
  jq '.data.activeTargets[] | select(.labels.job=="dcgm_exporter")'
```

### Option 2: Static Configuration

If not using BCM role monitor:

```yaml
scrape_configs:
  - job_name: 'dcgm_exporter'
    static_configs:
      - targets:
          - 'dgx-01:9400'
          - 'dgx-02:9400'
          - 'dgx-03:9400'
          - 'dgx-04:9400'
        labels:
          cluster: 'slurm'
```

## Grafana Dashboards

### Import Official DCGM Dashboard

1. **Download Dashboard JSON**
   ```bash
   # Method 1: From Grafana.com
   curl -o grafana/dcgm-dashboard.json \
     https://grafana.com/api/dashboards/12239/revisions/latest/download
   
   # Method 2: From DCGM exporter repo
   wget https://raw.githubusercontent.com/NVIDIA/dcgm-exporter/main/grafana/dcgm-exporter-dashboard.json \
     -O grafana/dcgm-dashboard.json
   ```

2. **Import in Grafana UI**
   - Open Grafana: `http://grafana:3000`
   - Go to: **Dashboards → Import**
   - Upload `grafana/dcgm-dashboard.json`
   - Select Prometheus data source
   - Click **Import**

3. **Customize for SuperPOD**
   - Edit panels to filter by `cluster="slurm"`
   - Add `hpcjob` label to panels showing job-specific metrics
   - Save modified dashboard

### Create Custom Dashboard

Example panel for GPU temperature with job labels:

```promql
DCGM_FI_DEV_GPU_TEMP{cluster="slurm"}
```

Example panel for GPU utilization by job:

```promql
avg(DCGM_FI_DEV_GPU_UTIL{cluster="slurm"}) by (hpcjob, hostname)
```

## Verification

### Complete Verification Checklist

```bash
# 1. Service Status
ssh dgx-01 "systemctl status dcgm-exporter"

# 2. Metrics Endpoint
curl http://dgx-01:9400/metrics | grep -c DCGM_FI
# Should return > 0

# 3. GPU Metrics
curl http://dgx-01:9400/metrics | \
  grep -E "DCGM_FI_DEV_(GPU_TEMP|GPU_UTIL|FB_USED)" | head -10

# 4. Job Mapping (submit a test job first)
srun --gpus=1 sleep 60 &
ssh dgx-01 "cat /run/dcgm-job-map/0"

# 5. Job Labels in Metrics
curl http://dgx-01:9400/metrics | grep hpcjob | head -5

# 6. Prometheus Discovery
curl 'http://prometheus:9090/api/v1/query?query=up{job="dcgm_exporter"}'

# 7. Prometheus Metrics
curl 'http://prometheus:9090/api/v1/query?query=DCGM_FI_DEV_GPU_TEMP' | \
  jq '.data.result[0]'

# 8. Grafana Dashboard
# Open in browser: http://grafana:3000/dashboards
```

### Test End-to-End

```bash
# 1. Submit GPU job
JOBID=$(sbatch --parsable --gpus=1 --wrap="sleep 300")
echo "Job ID: $JOBID"

# 2. Wait for job to start
watch squeue -j $JOBID

# 3. Find compute node
NODE=$(squeue -j $JOBID -h -o %N)
echo "Running on: $NODE"

# 4. Check job mapping
ssh $NODE "cat /run/dcgm-job-map/0"

# 5. Query metrics with job label
curl "http://$NODE:9400/metrics" | grep "hpcjob=\"$JOBID\""

# 6. Query in Prometheus
curl "http://prometheus:9090/api/v1/query?query=DCGM_FI_DEV_GPU_UTIL{hpcjob=\"$JOBID\"}"

# 7. View in Grafana
# Open dashboard, filter by job ID
```

## BCM Imaging Workflow

See [BCM-Imaging-Workflow.md](BCM-Imaging-Workflow.md) for complete instructions.

### Quick Reference

```bash
# 1. Deploy to representative node
./setup.sh
# Deploy to dgx-01

# 2. Test thoroughly
ssh dgx-01 "systemctl status dcgm-exporter"

# 3. Capture image
module load cmsh
cmsh -c 'device; use dgx-01; grabimage -w'

# 4. Deploy to other nodes
cmsh -c 'device; use dgx-02; set softwareimage dgx-01; commit'
cmsh -c 'device; use dgx-03; set softwareimage dgx-01; commit'
```

## Next Steps

1. **Monitor**: Check Grafana dashboards regularly
2. **Optimize**: Adjust Prometheus retention and scrape intervals
3. **Scale**: Use BCM imaging to deploy to additional nodes
4. **Maintain**: Update DCGM exporter when new versions are released

## Additional Resources

- [DCGM Exporter Documentation](https://docs.nvidia.com/datacenter/cloud-native/gpu-telemetry/dcgm-exporter.html)
- [Prometheus Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- [Grafana Dashboard Documentation](https://grafana.com/docs/grafana/latest/dashboards/)
- [Troubleshooting Guide](Troubleshooting.md)
- [DCGM Compatibility](DCGM-Compatibility.md)

