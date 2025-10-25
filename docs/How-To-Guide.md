# DCGM Exporter on SuperPOD - Manual Deployment Guide

Step-by-step manual guide for deploying DCGM Exporter in BCM-managed SuperPOD environments without using the automated deployment script.

> **Note**: If you prefer automated deployment, see the main README.md and run `./setup.sh` instead.

## Table of Contents

1. [Manual Deployment](#manual-deployment)
2. [Slurm Integration](#slurm-integration)
3. [BCM Role Monitor Setup](#bcm-role-monitor-setup)
4. [Prometheus Configuration](#prometheus-configuration)
5. [Grafana Dashboards](#grafana-dashboards)
6. [Verification](#verification)
7. [BCM Imaging Workflow](#bcm-imaging-workflow)

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
/usr/bin/dcgm-exporter --version
ls -l /etc/dcgm-exporter/default-counters.csv
```

### Step 2: Create Required Directories

```bash
# Create directory for HPC job mappings
mkdir -p /run/dcgm-job-map
chmod 755 /run/dcgm-job-map

# Create working directory for service
mkdir -p /var/lib/dcgm-exporter
chmod 755 /var/lib/dcgm-exporter
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

# Verify metrics with retry (service takes a few seconds to start)
for i in {1..3}; do
  if curl -s http://dgx-01:9400/metrics | grep -q "DCGM_FI"; then
    echo "✓ DCGM metrics available"
    break
  else
    echo "⚠ Waiting for metrics... (attempt $i/3)"
    sleep 3
  fi
done
```

### Step 5: Cleanup Temporary Files (Optional)

```bash
# Remove temporary build directory to save space (~500 MB)
ssh dgx-01 "rm -rf /opt/dcgm-exporter-deployment"

# Note: The automated deployment script does this automatically
# For manual deployments, you may want to keep it for easier updates
```

### Step 6: Repeat for Other Nodes

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
curl http://localhost:9400/metrics | grep "hpc_job" | head -5

# Exit the job
exit

# Verify mapping was cleaned up
ssh <compute-node> "ls /run/dcgm-job-map/"
```

## BCM Role Monitor Setup

BCM role monitor automatically manages DCGM exporter service based on BCM role assignments.

### Step 1: Get BCM Admin Certificates

```bash
# On BCM headnode, locate admin certificates (check common locations)
ls -l /root/.cm/admin.pem /root/.cm/admin.key     # BCM default location
# or
ls -l /root/.cm/cmsh/admin.pem /root/.cm/cmsh/admin.key  # Alternative location

# Copy to deployment machine (adjust path as needed)
scp bcm-headnode:/root/.cm/admin.* .
```

### Step 2: Create Prometheus Targets Directory

```bash
# On BCM headnode or node with access to shared storage
mkdir -p /cm/shared/apps/dcgm-exporter/prometheus-targets
chmod 755 /cm/shared/apps/dcgm-exporter/prometheus-targets

# Verify
ls -ld /cm/shared/apps/dcgm-exporter/prometheus-targets
```

### Step 3: Deploy Role Monitor to DGX Nodes

```bash
# Deploy using automation script
python automation/deploy_dcgm_exporter.py \
  --config automation/configs/config.json

# Or deploy manually to specific nodes
python automation/deploy_dcgm_exporter.py \
  --dgx-nodes dgx-01 dgx-02 dgx-03
```

### Step 4: Verify Role Monitor

```bash
# Check service status
ssh dgx-01 "systemctl status bcm-role-monitor-dcgm"

# View logs
ssh dgx-01 "journalctl -u bcm-role-monitor-dcgm -n 50"

# Check if node has slurmclient role
cmsh -c "device; use dgx-01; show roles"
```

### Step 5: Test Role Changes

```bash
# Add slurmclient role (if not already present)
cmsh -c "device; use dgx-01; roles; append slurmclient; commit"

# Within 60 seconds, check that services started
ssh dgx-01 "systemctl status dcgm-exporter"
ssh dgx-01 "systemctl status bcm-role-monitor-dcgm"

# Check Prometheus target file was created
ls -l /cm/shared/apps/dcgm-exporter/prometheus-targets/dgx-01.json

# Remove role to test cleanup
cmsh -c "device; use dgx-01; roles; remove slurmclient; commit"

# Within 60 seconds, check that service stopped and target removed
ssh dgx-01 "systemctl status dcgm-exporter"
ls /cm/shared/apps/dcgm-exporter/prometheus-targets/dgx-01.json  # Should be gone
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
   - Add `hpc_job` label to panels showing job-specific metrics
   - Save modified dashboard

### Create Custom Dashboard

Example panel for GPU temperature with job labels:

```promql
DCGM_FI_DEV_GPU_TEMP{cluster="slurm"}
```

Example panel for GPU utilization by job:

```promql
avg(DCGM_FI_DEV_GPU_UTIL{cluster="slurm"}) by (hpc_job, hostname)
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
curl http://dgx-01:9400/metrics | grep hpc_job | head -5

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
curl "http://$NODE:9400/metrics" | grep "hpc_job=\"$JOBID\""

# 6. Query in Prometheus
curl "http://prometheus:9090/api/v1/query?query=DCGM_FI_DEV_GPU_UTIL{hpc_job=\"$JOBID\"}"

# 7. View in Grafana
# Open dashboard, filter by job ID
```

## BCM Imaging Workflow

BCM's imaging system allows you to capture the software configuration of a representative node and deploy it to many nodes efficiently. This is the recommended approach for scaling DCGM Exporter to large clusters.

### Benefits of BCM Imaging

✅ **Fast Scaling** - Deploy to 100+ nodes in minutes  
✅ **Consistency** - All nodes get identical configuration  
✅ **Easy Maintenance** - Update one node, re-image others  
✅ **Version Control** - Track software images over time  
✅ **Rollback Capability** - Revert to previous images if needed  

### Prerequisites

- Working DCGM Exporter installation on representative node
- BCM administrator access
- `cmsh` module loaded
- Understanding of BCM categories and software images

### Phase 1: Clone Existing Image

Before deploying and capturing a new image, clone the existing software image to avoid overwriting it:

```bash
# Clone the current software image
cmsh -c "softwareimage;clone <current-image> <new-image>"
```

### Phase 2: Deploy to Representative Node

Deploy DCGM Exporter to one representative node first:
- By following the instructions earlier in this guide or by running the automation discussed in the README.md

### Phase 3: Capture Software Image

Once verified, capture the node's software image:

```bash
# Capture image from dgx-01
cmsh -c 'device; use dgx-01; grabimage -w'
```

**What `grabimage -w` does:**
- Copies the node as a BCM software image
- Overwrites the software image currently assigned to that node (so, make sure to clone first if you don't want to overwrite the old image)
- Includes all installed packages, services, and configurations
- `-w` flag means "write." without it the command will run as dry-run only.


### Phase 4: Deploy Image to Additional Nodes

#### Deploy to Multiple Nodes via Category

```bash
# Deploy to all DGX nodes in a category
cmsh -c 'category; use <current-category>; set softwareimage <new-image>; commit'
```
Note: Reboot each node for new image to take effect

### Phase 5: Post-Deployment Verification

After nodes reboot, verify DCGM Exporter is running:

```bash
# Quick check on all nodes
for node in dgx-02 dgx-03 dgx-04; do
  echo "=== $node ==="
  ssh $node "systemctl is-active dcgm-exporter" && echo "✓ Service running"
  ssh $node "curl -s http://localhost:9400/metrics | grep -c ^DCGM_FI" && echo "✓ Metrics available"
  echo ""
done
```

### Phase 6: Prometheus Target Validation

If using BCM role monitor, check that Prometheus target files are created:

```bash
# Check Prometheus targets directory
ls -la /cm/shared/apps/dcgm-exporter/prometheus-targets/

# Should see JSON files for each node:
# dgx-01.json  dgx-02.json  dgx-03.json  dgx-04.json

# Verify target file contents
cat /cm/shared/apps/dcgm-exporter/prometheus-targets/dgx-02.json

# Check in Prometheus UI
# http://prometheus:9090/targets
```

### Troubleshooting Imaging Issues

**Service not starting after imaging:**
```bash
# Check if systemd service was enabled
ssh dgx-02 "systemctl is-enabled dcgm-exporter"

# If disabled, enable it
ssh dgx-02 "systemctl enable dcgm-exporter && systemctl start dcgm-exporter"

# Check logs
ssh dgx-02 "journalctl -u dcgm-exporter -n 50"
```

**Binary missing after imaging:**
```bash
# Verify binary exists
ssh dgx-02 "ls -l /usr/bin/dcgm-exporter"

# If missing, re-run deployment on that node
./setup.sh
# Select only dgx-02
```

**Job mapping not working:**
```bash
# Verify prolog/epilog symlinks
ssh dgx-02 "ls -la /cm/local/apps/slurm/var/prologs/"
ssh dgx-02 "ls -la /cm/local/apps/slurm/var/epilogs/"

# Verify shared scripts exist
ls -la /cm/shared/apps/slurm/var/cm/prolog-dcgm.sh
ls -la /cm/shared/apps/slurm/var/cm/epilog-dcgm.sh
```

### Best Practices

1. **Always test on one node first** - Verify everything works before imaging
2. **Document your image version** - Track what's in each software image
3. **Maintain a reference node** - Keep dgx-01 as the golden node for updates
4. **Rolling updates** - Image a few nodes at a time, not all at once
5. **Backup configurations** - Save your `config.json` before major changes

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

