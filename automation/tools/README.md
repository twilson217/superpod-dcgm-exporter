# Testing and Validation Tools

Automated testing scripts for DCGM Exporter deployment.

## test_deployment.py

Comprehensive automated testing script that validates the entire DCGM exporter deployment.

### Features

- ✅ **SSH Connectivity** - Verifies access to all DGX nodes
- ✅ **Service Status** - Checks dcgm-exporter systemd service
- ✅ **Metrics Endpoint** - Tests HTTP endpoint and DCGM metrics
- ✅ **GPU Detection** - Validates GPU visibility and metrics
- ✅ **Job Mapping** - Checks HPC job mapping directory
- ✅ **Prolog/Epilog** - Validates Slurm integration scripts
- ✅ **Prometheus Targets** - Tests service discovery files
- ✅ **BCM Role Monitor** - Checks optional role monitor (if deployed)
- ✅ **Colored Output** - Easy-to-read results
- ✅ **JSON Export** - Export results for automation

### Usage

#### With Config File (Default)

```bash
# Run all tests using default config (automation/configs/config.json)
python automation/tools/test_deployment.py

# Export results to JSON
python automation/tools/test_deployment.py --export test-results.json

# Use custom config file
python automation/tools/test_deployment.py --config /path/to/custom-config.json
```

#### With Command Line

```bash
# Test specific nodes
python automation/tools/test_deployment.py --dgx-nodes dgx-01 dgx-02 dgx-03

# Export results
python automation/tools/test_deployment.py \
    --dgx-nodes dgx-01 dgx-02 \
    --export results-$(date +%Y%m%d).json
```

### Test Categories

#### 1. SSH Connectivity
- Tests passwordless SSH to all DGX nodes
- Verifies hostname resolution

#### 2. DCGM Exporter Service
- Checks if service is installed
- Verifies service is active
- Confirms service is enabled

#### 3. Metrics Endpoint
- Tests HTTP endpoint on port 9400
- Validates DCGM metrics presence
- Counts available metrics

#### 4. GPU Detection
- Runs nvidia-smi to detect GPUs
- Checks GPU count
- Verifies GPU labels in metrics

#### 5. Job Mapping Directory
- Checks /run/dcgm-job-map/ exists
- Validates permissions
- Tests writeability

#### 6. Prolog/Epilog Scripts
- Verifies shared storage scripts exist
- Checks if scripts are executable
- Validates symlinks on compute nodes

#### 7. Prometheus Targets
- Tests target directory exists
- Counts target JSON files
- Validates JSON format

#### 8. BCM Role Monitor (Optional)
- Checks if deployed
- Verifies service status
- Tests configuration

### Output Format

**Terminal Output:**
```
====================================================================
DCGM Exporter Deployment Test Suite
====================================================================

Testing 3 DGX node(s): dgx-01, dgx-02, dgx-03

=== Testing SSH Connectivity ===
✓ PASS SSH to dgx-01: Connected successfully (hostname: dgx-01)
✓ PASS SSH to dgx-02: Connected successfully (hostname: dgx-02)
✓ PASS SSH to dgx-03: Connected successfully (hostname: dgx-03)

=== Testing DCGM Exporter Service ===
✓ PASS Service status on dgx-01: Service is active
✓ PASS Service enabled on dgx-01: Service is enabled
...

====================================================================
Test Summary
====================================================================

Total tests: 45
Passed: 45
Failed: 0

Overall Result: ✓ ALL TESTS PASSED
====================================================================
```

**JSON Export:**
```json
{
  "timestamp": "2025-01-10T14:30:00",
  "dgx_nodes": ["dgx-01", "dgx-02", "dgx-03"],
  "total_tests": 45,
  "passed": 45,
  "failed": 0,
  "results": [
    {
      "name": "SSH to dgx-01",
      "passed": true,
      "message": "Connected successfully",
      "details": "",
      "timestamp": "2025-01-10T14:30:01"
    },
    ...
  ]
}
```

### Integration with CI/CD

```bash
#!/bin/bash
# ci-test.sh - Run in CI/CD pipeline

set -e

# Run tests
python automation/tools/test_deployment.py \
    --config automation/configs/config.json \
    --export test-results.json

# Check exit code
if [ $? -eq 0 ]; then
    echo "All tests passed!"
    exit 0
else
    echo "Tests failed!"
    cat test-results.json
    exit 1
fi
```

### Manual Job Testing

The script skips automatic job submission. To test job mapping manually:

```bash
# Submit a test job
srun --gpus=1 --time=1:00 nvidia-smi &
JOB_ID=$!

# Wait for job to start
sleep 5

# Check job mapping on compute node
NODE=$(squeue -j $JOB_ID -h -o %N)
ssh $NODE "cat /run/dcgm-job-map/0"  # Should show job ID

# Check metrics include job label
ssh $NODE "curl -s http://localhost:9400/metrics | grep hpcjob"

# Cancel job
scancel $JOB_ID

# Verify cleanup
ssh $NODE "ls /run/dcgm-job-map/"  # Should be empty or no file for GPU 0
```

### Troubleshooting

**Test fails with SSH timeout:**
- Check SSH keys are set up
- Verify network connectivity
- Check firewall rules

**Service tests fail:**
- Ensure deployment completed successfully
- Check service logs: `journalctl -u dcgm-exporter -n 50`
- Verify binary exists: `which dcgm-exporter`

**Metrics tests fail:**
- Check if service is running
- Test endpoint manually: `curl http://localhost:9400/metrics`
- Check firewall: `iptables -L -n | grep 9400`

**GPU detection fails:**
- Verify GPUs visible: `nvidia-smi`
- Check DCGM daemon: `systemctl status nvidia-dcgm`
- Test DCGM: `dcgmi discovery -l`

### Exit Codes

- `0` - All tests passed
- `1` - One or more tests failed

### Dependencies

- Python 3.9+
- SSH access to all nodes
- No additional Python packages required (stdlib only)

### Examples

**Quick test with default config:**
```bash
# Uses automation/configs/config.json automatically
python automation/tools/test_deployment.py
```

**Test specific nodes (no config needed):**
```bash
python automation/tools/test_deployment.py --dgx-nodes dgx-01 dgx-02
```

**Test all nodes and export:**
```bash
# Uses default config
python automation/tools/test_deployment.py --export results.json
```

**Test with custom config:**
```bash
python automation/tools/test_deployment.py \
    --config /path/to/custom-config.json \
    --export results.json
```

### Adding Custom Tests

To add your own tests, extend the `DCGMExporterTester` class:

```python
def test_custom_check(self) -> bool:
    """Your custom test"""
    print(f"\n{Colors.BOLD}=== Testing Custom Feature ==={Colors.END}")
    
    for node in self.dgx_nodes:
        # Your test logic
        returncode, stdout, stderr = self.ssh_command(node, "your-command")
        
        passed = returncode == 0
        self.add_result(
            f"Custom test on {node}",
            passed,
            "Success message" if passed else "Failure message",
            stderr if not passed else ""
        )
    
    return all_passed

# Add to run_all_tests() method:
tests = [
    ...
    ("Custom Test", self.test_custom_check),
]
```

### Best Practices

1. **Run after deployment** - Test immediately after deploying
2. **Run periodically** - Schedule regular testing (daily/weekly)
3. **Test after changes** - Run after configuration updates
4. **Export results** - Keep historical test records
5. **Automate** - Integrate with CI/CD pipelines

### See Also

- [How-To-Guide.md](../../docs/How-To-Guide.md) - Deployment instructions
- [Troubleshooting.md](../../docs/Troubleshooting.md) - Problem resolution
- [README.md](../../README.md) - Project overview

