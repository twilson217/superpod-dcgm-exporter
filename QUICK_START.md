# DCGM Exporter on SuperPOD - Quick Start

Get DCGM Exporter running on your BCM-managed SuperPOD in 5 minutes.

## One-Command Deployment

```bash
./setup.sh
```

Follow the prompts to configure and deploy.

## What You'll Need

- BCM-managed SuperPOD with Slurm
- **Run from a BCM headnode** (auto-detects headnode)
- Passwordless SSH to DGX nodes
- 5 minutes

## Quick Configuration

When prompted:

| Question | Example Answer |
|----------|----------------|
| BCM headnode | Auto-detected (or prompted if needed) |
| DGX nodes | `dgx-01,dgx-02,dgx-03` |
| Slurm controller | `slurmctl` |
| Existing Prometheus? | `no` (or `yes` + hostname) |

## Quick Verification

```bash
# Check service
ssh dgx-01 "systemctl status dcgm-exporter"

# Test metrics
curl http://dgx-01:9400/metrics | head -20

# Test with GPU job
srun --gpus=1 nvidia-smi
curl http://<node>:9400/metrics | grep hpcjob
```

## What Gets Deployed

- ✅ DCGM Exporter on DGX nodes (port 9400)
- ✅ Systemd service management
- ✅ Slurm job-to-GPU mapping scripts
- ✅ BCM role-based automation (optional)
- ✅ Prometheus integration (optional)

## Next Steps

1. **Configure Prometheus** - See `docs/prometheus-config-sample.yml`
2. **Import Grafana Dashboard** - Dashboard ID: 12239
3. **Scale with BCM Imaging** - See `docs/BCM-Imaging-Workflow.md`

## Need Help?

- **Full Guide**: [How-To-Guide.md](docs/How-To-Guide.md)
- **Troubleshooting**: [Troubleshooting.md](docs/Troubleshooting.md)
- **Architecture**: [DCGM-Compatibility.md](docs/DCGM-Compatibility.md)

## Key Files

| File | Purpose |
|------|---------|
| `setup.sh` | Main deployment script |
| `automation/configs/config.json` | Your configuration |
| `docs/` | Complete documentation |
| `systemd/dcgm-exporter.service` | Service definition |

## Prometheus Configuration Example

```yaml
scrape_configs:
  - job_name: 'dcgm_exporter'
    file_sd_configs:
      - files:
          - '/cm/shared/apps/dcgm-exporter/prometheus-targets/*.json'
        refresh_interval: 30s
```

## Default Ports

| Service | Port |
|---------|------|
| DCGM Exporter | 9400 |
| Prometheus | 9090 |
| Grafana | 3000 |

## Support

Check logs if issues occur:
```bash
ssh <node> "journalctl -u dcgm-exporter -n 100"
```

---

**Ready to go!** Run `./setup.sh` to start deployment.

