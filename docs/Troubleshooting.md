# DCGM Exporter Troubleshooting Guide

## Quick Diagnostic Commands

```bash
# Check service status
systemctl status dcgm-exporter

# View recent logs
journalctl -u dcgm-exporter -n 50

# Test metrics endpoint
curl http://localhost:9400/metrics | head -20

# Check GPU access
nvidia-smi

# Verify DCGM
dcgmi discovery -l

# Check job mapping directory
ls -la /run/dcgm-job-map/
```

## Common Issues

### 1. DCGM Exporter Service Won't Start

#### Symptom
```bash
$ systemctl status dcgm-exporter
● dcgm-exporter.service - NVIDIA DCGM Exporter
   Active: failed (Result: exit-code)
```

#### Possible Causes & Solutions

**A. Missing binary**
```bash
# Check if binary exists
ls -l /usr/local/bin/dcgm-exporter

# If missing, rebuild
cd /opt/dcgm-exporter-deployment/dcgm-exporter
make binary && make install
```

**B. DCGM initialization failed**
```bash
# Check logs
journalctl -u dcgm-exporter -n 100

# Look for errors like:
# "Failed to initialize DCGM"
# "No CUDA-capable devices detected"

# Verify GPUs
nvidia-smi

# Check DCGM daemon
systemctl status nvidia-dcgm
```

**C. Configuration file missing**
```bash
# Check if config exists
ls -l /etc/dcgm-exporter/default-counters.csv

# If missing, copy from source
cp dcgm-exporter/etc/default-counters.csv /etc/dcgm-exporter/
```

**D. Permissions issue**
```bash
# Check service file
cat /etc/systemd/system/dcgm-exporter.service | grep User

# Ensure binary is executable
chmod +x /usr/local/bin/dcgm-exporter

# Reload systemd
systemctl daemon-reload
systemctl restart dcgm-exporter
```

### 2. No Metrics Returned

#### Symptom
```bash
$ curl http://localhost:9400/metrics
# Empty or only Go metrics
```

#### Solutions

**A. Port not listening**
```bash
# Check if port is open
netstat -tulpn | grep 9400
ss -tulpn | grep 9400

# Check service logs
journalctl -u dcgm-exporter -f
```

**B. Firewall blocking**
```bash
# Check firewall
iptables -L -n | grep 9400
firewall-cmd --list-ports

# Add port if needed (temporary)
iptables -I INPUT -p tcp --dport 9400 -j ACCEPT
```

**C. GPUs not detected**
```bash
# Verify GPUs
nvidia-smi

# Check DCGM can see GPUs
dcgmi discovery -l

# Check DCGM fields
dcgmi dmon -e 100,101,102 -c 1
```

### 3. No HPC Job Labels in Metrics

#### Symptom
Metrics don't include `hpcjob` label even when jobs are running.

#### Solutions

**A. Job mapping directory doesn't exist**
```bash
# Create directory
mkdir -p /run/dcgm-job-map
chmod 755 /run/dcgm-job-map

# Restart exporter
systemctl restart dcgm-exporter
```

**B. Prolog/Epilog not configured**
```bash
# Check if scripts exist in shared storage
ls -l /cm/shared/apps/slurm/var/cm/prolog-dcgm.sh
ls -l /cm/shared/apps/slurm/var/cm/epilog-dcgm.sh

# Check symlinks on compute nodes
ls -l /cm/local/apps/slurm/var/prologs/60-prolog-dcgm.sh
ls -l /cm/local/apps/slurm/var/epilogs/60-epilog-dcgm.sh

# Create symlinks if missing
ln -sf /cm/shared/apps/slurm/var/cm/prolog-dcgm.sh \
    /cm/local/apps/slurm/var/prologs/60-prolog-dcgm.sh
ln -sf /cm/shared/apps/slurm/var/cm/epilog-dcgm.sh \
    /cm/local/apps/slurm/var/epilogs/60-epilog-dcgm.sh
```

**C. Prolog/Epilog not executing**
```bash
# Check Slurm configuration
scontrol show config | grep -i prolog
scontrol show config | grep -i epilog

# Check prolog/epilog logs
tail -f /var/log/slurm/dcgm-prolog.log
tail -f /var/log/slurm/dcgm-epilog.log

# Test manually
export SLURM_JOB_ID=12345
export CUDA_VISIBLE_DEVICES=0,1
/cm/shared/apps/slurm/var/cm/prolog-dcgm.sh

# Check mapping files
ls -l /run/dcgm-job-map/
cat /run/dcgm-job-map/0
```

**D. Service not configured for HPC job mapping**
```bash
# Check service file
grep "hpc-job-mapping-dir" /etc/systemd/system/dcgm-exporter.service

# Should see:
# --hpc-job-mapping-dir /run/dcgm-job-map

# If missing, add and reload
systemctl daemon-reload
systemctl restart dcgm-exporter
```

### 4. Prometheus Not Scraping

#### Symptom
No DCGM metrics in Prometheus, or targets show as "down".

#### Solutions

**A. Check Prometheus targets**
```bash
# View targets in Prometheus UI
http://prometheus:9090/targets

# Or via API
curl http://prometheus:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="dcgm_exporter")'
```

**B. Target file doesn't exist**
```bash
# Check if BCM role monitor created target file
ls -la /cm/shared/apps/dcgm-exporter/prometheus-targets/

# Should see files like: dgx-01.json, dgx-02.json

# Check content
cat /cm/shared/apps/dcgm-exporter/prometheus-targets/dgx-01.json

# If missing, check role monitor
systemctl status bcm-role-monitor
journalctl -u bcm-role-monitor -n 50
```

**C. Prometheus config incorrect**
```bash
# Check Prometheus config
grep -A 10 "dcgm_exporter" /etc/prometheus/prometheus.yml

# Should include file_sd_configs or static_configs
# file_sd_configs:
#   - files:
#       - '/cm/shared/apps/dcgm-exporter/prometheus-targets/*.json'

# Reload Prometheus
curl -X POST http://prometheus:9090/-/reload
```

**D. Network connectivity**
```bash
# Test from Prometheus server
curl http://dgx-01:9400/metrics | head -20

# Check firewall
ssh dgx-01 "iptables -L -n | grep 9400"

# Check service is listening
ssh dgx-01 "netstat -tulpn | grep 9400"
```

### 5. High Resource Usage

#### Symptom
DCGM Exporter consuming excessive CPU or memory.

#### Solutions

**A. Check resource usage**
```bash
# Check process
top -p $(pgrep dcgm-exporter)
ps aux | grep dcgm-exporter

# Check system resources
free -h
uptime
```

**B. Reduce scrape frequency**
```yaml
# In Prometheus config
scrape_configs:
  - job_name: 'dcgm_exporter'
    scrape_interval: 60s  # Increase from 30s
```

**C. Reduce metric cardinality**
```bash
# Check number of time series
curl http://localhost:9400/metrics | grep -c ^DCGM

# Consider disabling some metrics in default-counters.csv
# Comment out unused metrics with # prefix
```

### 6. BCM Role Monitor Issues

#### Symptom
Services not starting/stopping when BCM role changes.

#### Solutions

**A. Check role monitor service**
```bash
systemctl status bcm-role-monitor
journalctl -u bcm-role-monitor -f
```

**B. Verify BCM API access**
```bash
# Test BCM API
curl -s --cert /etc/bcm-role-monitor/admin.pem \
     --key /etc/bcm-role-monitor/admin.key \
     --insecure \
     https://bcm-headnode:8081/rest/v1/device | jq '.'

# Check certificates
ls -l /etc/bcm-role-monitor/admin.pem
ls -l /etc/bcm-role-monitor/admin.key
```

**C. Check role assignment**
```bash
# On BCM headnode
cmsh -c "device; use dgx-01; show roles"

# Should include: slurmclient
```

**D. Manual service management**
```bash
# Manually start services if role monitor fails
systemctl start dcgm-exporter
systemctl start node_exporter
systemctl start cgroup_exporter
systemctl start nvidia_gpu_exporter
```

### 7. Metrics Not Appearing in Grafana

#### Symptom
Grafana dashboards show "No data" even though Prometheus has metrics.

#### Solutions

**A. Verify Prometheus data source**
```bash
# In Grafana UI:
# Configuration → Data Sources → Prometheus
# Click "Test" button

# Or via API
curl http://grafana:3000/api/datasources
```

**B. Check metric names**
```bash
# Query Prometheus directly
curl 'http://prometheus:9090/api/v1/query?query=DCGM_FI_DEV_GPU_TEMP'

# Check available metrics
curl http://prometheus:9090/api/v1/label/__name__/values | grep DCGM
```

**C. Time range issue**
```bash
# Ensure time range in Grafana covers recent data
# Check "Last 5 minutes" first

# Verify metrics are recent
curl 'http://prometheus:9090/api/v1/query?query=DCGM_FI_DEV_GPU_TEMP' | jq '.data.result[0]'
```

## Diagnostic Script

Create `/root/diagnose-dcgm-exporter.sh`:

```bash
#!/bin/bash
echo "=== DCGM Exporter Diagnostics ==="
echo ""
echo "=== Service Status ==="
systemctl status dcgm-exporter --no-pager

echo ""
echo "=== Recent Logs ==="
journalctl -u dcgm-exporter -n 20 --no-pager

echo ""
echo "=== Binary Check ==="
ls -l /usr/local/bin/dcgm-exporter
/usr/local/bin/dcgm-exporter --version 2>&1 || echo "Version check failed"

echo ""
echo "=== Config Files ==="
ls -l /etc/dcgm-exporter/

echo ""
echo "=== GPU Check ==="
nvidia-smi --query-gpu=index,name,driver_version --format=csv

echo ""
echo "=== DCGM Check ==="
dcgmi discovery -l

echo ""
echo "=== Network Check ==="
netstat -tulpn | grep 9400 || ss -tulpn | grep 9400

echo ""
echo "=== Metrics Sample ==="
curl -s http://localhost:9400/metrics | head -30

echo ""
echo "=== Job Mapping ==="
ls -la /run/dcgm-job-map/ 2>/dev/null || echo "Job mapping dir doesn't exist"

echo ""
echo "=== Prolog/Epilog Check ==="
ls -l /cm/local/apps/slurm/var/prologs/60-prolog-dcgm.sh 2>/dev/null
ls -l /cm/local/apps/slurm/var/epilogs/60-epilog-dcgm.sh 2>/dev/null
```

Run with:
```bash
chmod +x /root/diagnose-dcgm-exporter.sh
./diagnose-dcgm-exporter.sh
```

## Getting Help

If issues persist:

1. **Collect diagnostics:**
   ```bash
   ./diagnose-dcgm-exporter.sh > dcgm-diagnostics-$(hostname)-$(date +%Y%m%d).txt
   ```

2. **Check logs:**
   ```bash
   journalctl -u dcgm-exporter -n 200 > dcgm-logs-$(hostname)-$(date +%Y%m%d).txt
   ```

3. **Review configuration:**
   - Service file: `/etc/systemd/system/dcgm-exporter.service`
   - Config: `/etc/dcgm-exporter/default-counters.csv`
   - Prometheus: `/etc/prometheus/prometheus.yml`

4. **Contact support** with collected information

## Additional Resources

- [DCGM Exporter GitHub Issues](https://github.com/NVIDIA/dcgm-exporter/issues)
- [DCGM Documentation](https://docs.nvidia.com/datacenter/dcgm/)
- [Prometheus Troubleshooting](https://prometheus.io/docs/prometheus/latest/troubleshooting/)

