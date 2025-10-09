# DCGM Compatibility in BCM Environments

## Overview

This document addresses the compatibility of DCGM Exporter with BCM's existing use of DCGM (`nvidia-dcgm` service).

## BCM's Use of DCGM

In BCM-managed environments, the `nvidia-dcgm` service is typically installed and running. BCM uses DCGM to:
- Monitor GPU health and status
- Collect telemetry data
- Send metrics to BCM management interface
- Perform GPU diagnostics

## DCGM Architecture

DCGM (Data Center GPU Manager) consists of:
- **nv-hostengine**: The DCGM daemon process
- **DCGM client libraries**: Used by various tools to query GPU metrics
- **Multiple clients can connect**: DCGM is designed to support multiple simultaneous clients

## DCGM Exporter Operation Modes

DCGM Exporter can operate in two modes:

### 1. Embedded Mode (Default - Recommended)

```bash
dcgm-exporter -f /etc/dcgm-exporter/default-counters.csv
```

**How it works:**
- Starts its own embedded DCGM instance within the exporter process
- Isolated from other DCGM clients
- Does not interfere with BCM's use of DCGM

**Pros:**
- ✅ No conflicts with existing DCGM services
- ✅ Self-contained and isolated
- ✅ Easier to manage and troubleshoot
- ✅ Recommended for BCM environments

**Cons:**
- Slightly higher memory overhead (minimal)

### 2. Remote Mode (Alternative)

```bash
dcgm-exporter -r localhost:5555 -f /etc/dcgm-exporter/default-counters.csv
```

**How it works:**
- Connects to an existing DCGM hostengine (nv-hostengine)
- Shares DCGM instance with BCM and other clients
- Multiple clients can query the same hostengine

**Pros:**
- Shared DCGM instance
- Lower memory footprint

**Cons:**
- ⚠️ Requires existing nv-hostengine to be running
- ⚠️ Potential for conflicts if hostengine is restarted
- ⚠️ More complex troubleshooting

## Compatibility Testing

### Test 1: Embedded Mode with BCM DCGM

**Setup:**
- BCM environment with `nvidia-dcgm` service running
- DCGM Exporter in embedded mode

**Result:** ✅ **COMPATIBLE**
- No conflicts observed
- Both services operate independently
- BCM continues to collect metrics
- DCGM Exporter successfully exports metrics

**Commands to verify:**
```bash
# Check nvidia-dcgm service
systemctl status nvidia-dcgm

# Check dcgm-exporter service
systemctl status dcgm-exporter

# Verify metrics from dcgm-exporter
curl http://localhost:9400/metrics | grep DCGM_FI_DEV_GPU_TEMP

# Verify BCM can still access DCGM
dcgmi discovery -l
```

### Test 2: Remote Mode with BCM DCGM

**Setup:**
- BCM environment with `nvidia-dcgm` service running
- DCGM Exporter connecting to BCM's nv-hostengine

**Result:** ⚠️ **COMPATIBLE WITH CAVEATS**
- Works if nv-hostengine is accessible
- May have port conflicts (default port 5555)
- Requires coordination with BCM service management

## Recommendation for BCM Environments

### ✅ Use Embedded Mode (Default)

Our deployment uses **embedded mode** for the following reasons:

1. **No Conflicts**: Isolated from BCM's DCGM usage
2. **Service Independence**: Doesn't depend on BCM's service lifecycle
3. **Simpler Management**: One service, one process
4. **BCM Imaging Compatible**: Works seamlessly with BCM imaging workflow
5. **Proven Reliability**: Used in production by many customers

### Service Configuration

Our systemd service file configures embedded mode:

```ini
[Unit]
Description=NVIDIA DCGM Exporter for Prometheus
Wants=nvidia-dcgm.service
After=network-online.target nvidia-dcgm.service

[Service]
ExecStart=/usr/local/bin/dcgm-exporter \
    -f /etc/dcgm-exporter/default-counters.csv \
    --hpc-job-mapping-dir /run/dcgm-job-map
```

**Note:** `Wants=nvidia-dcgm.service` and `After=nvidia-dcgm.service` ensure proper ordering but don't create a hard dependency.

## Resource Usage

### Memory Footprint

- **DCGM Exporter (embedded)**: ~100-200 MB RSS
- **BCM nvidia-dcgm service**: ~50-100 MB RSS
- **Total overhead**: ~150-300 MB per node

For DGX nodes with 1TB+ RAM, this is negligible (<0.03%).

### CPU Usage

- **DCGM Exporter**: <1% CPU during normal operation
- **BCM nvidia-dcgm**: <1% CPU during normal operation
- **Total overhead**: <2% CPU per node

## Port Usage

| Service | Port | Protocol | Purpose |
|---------|------|----------|---------|
| nvidia-dcgm | 5555 | TCP | DCGM hostengine (if remote mode) |
| dcgm-exporter | 9400 | TCP | Prometheus metrics HTTP endpoint |

No port conflicts between services.

## Monitoring Both Services

```bash
# Check both services
systemctl status nvidia-dcgm dcgm-exporter

# Verify DCGM hostengine (if running)
ps aux | grep nv-hostengine

# Verify dcgm-exporter process
ps aux | grep dcgm-exporter

# Check DCGM via CLI (uses BCM's DCGM)
dcgmi discovery -l
dcgmi dmon -e 100

# Check metrics via exporter
curl http://localhost:9400/metrics | grep -E "DCGM_FI_DEV_(GPU_TEMP|GPU_UTIL)"
```

## Troubleshooting

### Issue: DCGM Exporter fails to start

**Symptoms:**
```
Failed to initialize DCGM
```

**Solutions:**
1. Verify GPUs are accessible:
   ```bash
   nvidia-smi
   ```

2. Check DCGM libraries:
   ```bash
   ldconfig -p | grep dcgm
   ```

3. Verify no port conflicts (if using remote mode):
   ```bash
   netstat -tulpn | grep 5555
   ```

### Issue: Metrics show no GPU data

**Symptoms:**
- `/metrics` endpoint returns no DCGM metrics
- Only Go process metrics visible

**Solutions:**
1. Check GPU driver:
   ```bash
   nvidia-smi
   ```

2. Verify DCGM can see GPUs:
   ```bash
   dcgmi discovery -l
   ```

3. Check exporter logs:
   ```bash
   journalctl -u dcgm-exporter -n 100
   ```

## Conclusion

DCGM Exporter in **embedded mode** is fully compatible with BCM-managed environments where `nvidia-dcgm` service is already running. Both can operate simultaneously without conflicts.

### Key Takeaways

✅ Embedded mode is recommended for BCM environments  
✅ No configuration changes needed for BCM's DCGM usage  
✅ Both services can run simultaneously  
✅ Negligible resource overhead  
✅ No port conflicts  
✅ Works with BCM imaging workflow  

## References

- [DCGM Architecture Documentation](https://docs.nvidia.com/datacenter/dcgm/latest/dcgm-api/dcgm-api-overview.html)
- [DCGM Exporter Documentation](https://docs.nvidia.com/datacenter/cloud-native/gpu-telemetry/dcgm-exporter.html)
- [BCM GPU Management](.bcm-documentation/)

