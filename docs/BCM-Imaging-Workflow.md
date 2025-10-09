# BCM Imaging Workflow for DCGM Exporter

## Overview

BCM's imaging system allows you to capture the software configuration of a representative node and deploy it to many nodes efficiently. This guide shows how to use BCM imaging for DCGM Exporter deployment.

## Benefits of BCM Imaging

✅ **Fast Scaling** - Deploy to 100+ nodes in minutes  
✅ **Consistency** - All nodes get identical configuration  
✅ **Easy Maintenance** - Update one node, re-image others  
✅ **Version Control** - Track software images over time  
✅ **Rollback Capability** - Revert to previous images if needed  

## Prerequisites

- Working DCGM Exporter installation on representative node
- BCM administrator access
- `cmsh` module loaded
- Understanding of BCM categories and software images

## Workflow

### Phase 1: Deploy to Representative Nodes

Deploy DCGM Exporter to one representative node of each type:

```bash
# Deploy to first DGX node
./setup.sh
# Select dgx-01 as target

# Verify deployment
ssh dgx-01 "systemctl status dcgm-exporter"
ssh dgx-01 "curl -s http://localhost:9400/metrics | head -20"

# Test with actual workload
srun --nodelist=dgx-01 --gpus=1 nvidia-smi
```

### Phase 2: Capture Software Image

Once verified, capture the node's software image:

```bash
# Load cmsh module
source /etc/profile.d/modules.sh
module load cmsh

# Capture image from dgx-01
cmsh -c 'device; use dgx-01; grabimage -w'
```

**What `grabimage -w` does:**
- Creates a snapshot of the node's software configuration
- Stores as a software image named after the node (e.g., "dgx-01")
- Includes all installed packages, services, and configurations
- `-w` flag waits for completion

**Output:**
```
Grabbing image for dgx-01...
Image successfully grabbed.
Software image 'dgx-01' is now available for deployment.
```

### Phase 3: Verify Image Contents

```bash
# List available software images
cmsh -c 'softwareimage; list'

# View details of captured image
cmsh -c 'softwareimage; use dgx-01; show'

# Check image includes our components
cmsh -c 'softwareimage; use dgx-01; show packages' | grep dcgm
```

### Phase 4: Deploy Image to Additional Nodes

#### Option 1: Deploy to Individual Nodes

```bash
# Set software image for dgx-02
cmsh -c 'device; use dgx-02; set softwareimage dgx-01; commit'

# Reboot node to apply image
cmsh -c 'device; use dgx-02; reboot'

# Wait for node to come back up
cmsh -c 'device; use dgx-02; power'

# Verify
ssh dgx-02 "systemctl status dcgm-exporter"
```

#### Option 2: Deploy to Multiple Nodes

```bash
# Deploy to all DGX nodes in a category
cmsh -c 'category; use dgx; set softwareimage dgx-01; commit'

# Reboot all nodes in category
cmsh -c 'category; use dgx; foreach -c "reboot"'
```

#### Option 3: Deploy Selectively

```bash
# Deploy to specific list of nodes
for node in dgx-02 dgx-03 dgx-04; do
  echo "Deploying to $node..."
  cmsh -c "device; use $node; set softwareimage dgx-01; commit"
  cmsh -c "device; use $node; reboot"
done
```

### Phase 5: Post-Deployment Verification

After nodes reboot, verify DCGM Exporter is running:

```bash
# Create verification script
cat > verify-dcgm-deployment.sh << 'EOF'
#!/bin/bash
NODES="$@"
echo "Verifying DCGM Exporter deployment on: $NODES"
echo ""

for node in $NODES; do
  echo "=== $node ==="
  
  # Check service status
  ssh $node "systemctl is-active dcgm-exporter" && echo "✓ Service running" || echo "✗ Service not running"
  
  # Check metrics endpoint
  METRIC_COUNT=$(ssh $node "curl -s http://localhost:9400/metrics | grep -c ^DCGM_FI" 2>/dev/null || echo 0)
  if [ "$METRIC_COUNT" -gt 0 ]; then
    echo "✓ Metrics available ($METRIC_COUNT metrics)"
  else
    echo "✗ No metrics"
  fi
  
  # Check Prometheus target file
  if ssh $node "ls /cm/shared/apps/dcgm-exporter/prometheus-targets/$node.json" 2>/dev/null; then
    echo "✓ Prometheus target file exists"
  else
    echo "✗ No Prometheus target file"
  fi
  
  echo ""
done
EOF

chmod +x verify-dcgm-deployment.sh

# Run verification
./verify-dcgm-deployment.sh dgx-02 dgx-03 dgx-04
```

## Important Considerations

### 1. Shared Storage Files

Files in `/cm/shared/` are **not** included in software images because they're on shared storage. These include:

- Prolog/epilog scripts (`/cm/shared/apps/slurm/var/cm/`)
- Prometheus target files (`/cm/shared/apps/dcgm-exporter/prometheus-targets/`)

**These only need to be deployed once** and are automatically available to all nodes via NFS.

### 2. Node-Specific Configuration

Some files may need per-node customization:
- Hostname-based Prometheus target files (automatically handled by role monitor)
- BCM role monitor state files (automatically created)

### 3. Service State

After imaging:
- Services are **enabled** but may not be **started**
- BCM role monitor will start services based on role assignment
- Manual start may be needed if not using role monitor

### 4. Certificates

BCM admin certificates in `/etc/bcm-role-monitor/` are included in the image. Ensure these are valid across all nodes.

## Advanced Imaging Scenarios

### Scenario 1: Multiple Node Types

If you have different types of nodes (e.g., DGX A100 vs H100):

```bash
# Deploy and capture each type
# DGX A100
./setup.sh  # Deploy to dgx-a100-01
cmsh -c 'device; use dgx-a100-01; grabimage -w'

# DGX H100
./setup.sh  # Deploy to dgx-h100-01
cmsh -c 'device; use dgx-h100-01; grabimage -w'

# Deploy to categories
cmsh -c 'category; use dgx-a100; set softwareimage dgx-a100-01; commit'
cmsh -c 'category; use dgx-h100; set softwareimage dgx-h100-01; commit'
```

### Scenario 2: Incremental Updates

To update DCGM Exporter on all nodes:

```bash
# 1. Update representative node
ssh dgx-01
cd /opt/dcgm-exporter-deployment/dcgm-exporter
git pull
make binary && make install
systemctl restart dcgm-exporter

# 2. Verify update
systemctl status dcgm-exporter
/usr/local/bin/dcgm-exporter --version

# 3. Capture new image
exit  # Back to head node
cmsh -c 'device; use dgx-01; grabimage -w'

# 4. Deploy to all nodes
cmsh -c 'category; use dgx; set softwareimage dgx-01; commit'
cmsh -c 'category; use dgx; foreach -c "reboot"'
```

### Scenario 3: Testing Before Wide Deployment

```bash
# 1. Deploy to test node
cmsh -c 'device; use dgx-test; set softwareimage dgx-01; commit'
cmsh -c 'device; use dgx-test; reboot'

# 2. Test thoroughly
ssh dgx-test "systemctl status dcgm-exporter"
srun --nodelist=dgx-test --gpus=1 nvidia-smi

# 3. If successful, deploy to production nodes
cmsh -c 'category; use dgx-production; set softwareimage dgx-01; commit'
```

## Troubleshooting

### Issue: Service Not Running After Imaging

**Check:**
```bash
ssh <node> "systemctl status dcgm-exporter"
ssh <node> "journalctl -u dcgm-exporter -n 50"
```

**Solutions:**
1. Ensure service is enabled: `systemctl enable dcgm-exporter`
2. Check BCM role assignment: Node must have `slurmclient` role
3. Manually start if needed: `systemctl start dcgm-exporter`

### Issue: BCM Role Monitor State Issues

**Solution:**
```bash
# Clear state file on imaged node
ssh <node> "rm -f /var/lib/bcm-role-monitor/*_state.json"
ssh <node> "systemctl restart bcm-role-monitor"
```

### Issue: Old Hostname in Files

**Problem:** Files reference old hostname after imaging

**Solution:**
BCM role monitor automatically detects hostname changes and updates files. Give it 60 seconds after boot.

## BCM Category Management

### Create Category for DCGM Nodes

```bash
# Create category for nodes with DCGM exporter
cmsh -c 'category; add dcgm-exporter'
cmsh -c 'category; use dcgm-exporter; set softwareimage dgx-01'

# Add nodes to category
cmsh -c 'device; use dgx-02; set category dcgm-exporter; commit'
cmsh -c 'device; use dgx-03; set category dcgm-exporter; commit'

# Deploy to entire category
cmsh -c 'category; use dcgm-exporter; foreach -c "reboot"'
```

### Category-Based Service Management

```bash
# Start service on all nodes in category
cmsh -c 'category; use dcgm-exporter; foreach -c "systemctl start dcgm-exporter"'

# Check status on all nodes
cmsh -c 'category; use dcgm-exporter; foreach -c "systemctl status dcgm-exporter"'
```

## Best Practices

1. **Test First** - Always test on representative node before imaging
2. **Document Images** - Keep notes on what's in each software image
3. **Version Control** - Name images with dates: `dgx-01-20250110`
4. **Backup Images** - Keep previous images for rollback
5. **Staged Rollout** - Deploy to test category first, then production
6. **Monitor Closely** - Watch services after deployment
7. **Coordinate Downtime** - Plan reboots during maintenance windows

## Image Naming Convention

Recommended naming scheme:

```
<nodetype>-<date>-<version>
Examples:
  dgx-20250110-v1.0
  dgx-a100-20250110-dcgm
  dgx-prod-20250110-stable
```

Update in BCM:
```bash
# Rename software image
cmsh -c 'softwareimage; use dgx-01; set name dgx-20250110-v1.0; commit'

# Use named image
cmsh -c 'device; use dgx-02; set softwareimage dgx-20250110-v1.0; commit'
```

## Rollback Procedure

If issues arise after deployment:

```bash
# 1. Identify previous working image
cmsh -c 'softwareimage; list'

# 2. Revert nodes to previous image
cmsh -c 'device; use dgx-02; set softwareimage dgx-20241215-stable; commit'
cmsh -c 'device; use dgx-02; reboot'

# 3. Verify
ssh dgx-02 "systemctl status dcgm-exporter"
```

## Summary

BCM imaging workflow for DCGM Exporter:

1. ✅ Deploy to representative node
2. ✅ Test thoroughly
3. ✅ Capture image with `grabimage -w`
4. ✅ Deploy to additional nodes
5. ✅ Verify deployment
6. ✅ Monitor services

This workflow enables rapid, consistent deployment across large SuperPOD clusters while maintaining flexibility for updates and rollbacks.

## Additional Resources

- [BCM Documentation](.bcm-documentation/admin-manual.txt)
- [How-To Guide](How-To-Guide.md)
- [Troubleshooting](Troubleshooting.md)

