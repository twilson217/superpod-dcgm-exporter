#!/usr/bin/env python3
"""
DCGM Exporter Deployment Script for BCM-managed SuperPOD
Deploys DCGM exporter, prolog/epilog scripts, and optionally BCM role monitor
"""

import argparse
import json
import logging
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DCGMExporterDeployer:
    """Deploy DCGM Exporter to DGX nodes"""
    
    def __init__(self, config_path: Optional[str] = None, dgx_nodes: Optional[List[str]] = None, dry_run: bool = False):
        self.project_root = Path(__file__).parent.parent
        self.dry_run = dry_run
        
        if self.dry_run:
            logger.info("=" * 60)
            logger.info("DRY-RUN MODE - No commands will be executed")
            logger.info("=" * 60)
            logger.info("")
        
        if config_path:
            self.config = self._load_config(config_path)
            self.dgx_nodes = dgx_nodes or self.config.get("systems", {}).get("dgx_nodes", [])
        elif dgx_nodes:
            self.dgx_nodes = dgx_nodes
            self.config = self._get_default_config()
        else:
            logger.error("Must provide either config file or DGX node list")
            sys.exit(1)
    
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from file"""
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Config file not found: {config_path}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            sys.exit(1)
    
    def _get_default_config(self) -> Dict:
        """Get default configuration"""
        return {
            "prometheus_targets_dir": "/cm/shared/apps/dcgm-exporter/prometheus-targets",
            "hpc_job_mapping_dir": "/run/dcgm-job-map",
            "dcgm_exporter_port": 9400,
            "paths": {
                "shared_base": "/cm/shared/apps/dcgm-exporter",
                "prolog_shared": "/cm/shared/apps/slurm/var/cm",
                "prolog_local": "/cm/local/apps/slurm/var/prologs",
                "epilog_local": "/cm/local/apps/slurm/var/epilogs",
            }
        }
    
    def ssh_command(self, node: str, command: str, check=True) -> subprocess.CompletedProcess:
        """Execute command on remote node via SSH"""
        if self.dry_run:
            logger.info(f"[DRY-RUN] ssh {node} '{command}'")
            
            # Return appropriate mock output based on command
            mock_stdout = "[dry-run output]"
            if "systemctl is-active" in command:
                mock_stdout = "active"
            elif "which go" in command:
                mock_stdout = "/usr/bin/go"
            elif "curl" in command and "metrics" in command:
                mock_stdout = "DCGM_FI_DEV_GPU_TEMP{gpu=\"0\"} 45.0"
            elif "systemctl status" in command:
                mock_stdout = "● dcgm-exporter.service - DCGM Exporter\n   Loaded: loaded\n   Active: active (running)"
            
            result = subprocess.CompletedProcess(
                args=["ssh", node, command],
                returncode=0,
                stdout=mock_stdout,
                stderr=""
            )
            return result
        
        ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", node, command]
        logger.debug(f"Running on {node}: {command}")
        return subprocess.run(ssh_cmd, capture_output=True, text=True, check=check)
    
    def copy_file(self, local_path: Path, node: str, remote_path: str):
        """Copy file to remote node"""
        if self.dry_run:
            logger.info(f"[DRY-RUN] scp {local_path} {node}:{remote_path}")
            return
        
        scp_cmd = [
            "scp", "-o", "StrictHostKeyChecking=no",
            str(local_path), f"{node}:{remote_path}"
        ]
        logger.debug(f"Copying {local_path} to {node}:{remote_path}")
        subprocess.run(scp_cmd, check=True, capture_output=True)
    
    def deploy_to_node(self, node: str):
        """Deploy DCGM exporter to a single node"""
        logger.info(f"{'=' * 60}")
        logger.info(f"Deploying DCGM Exporter to {node}")
        logger.info(f"{'=' * 60}")
        
        # Step 1: Install Go if needed
        logger.info("Checking for Go compiler...")
        result = self.ssh_command(node, "which go", check=False)
        if result.returncode != 0:
            logger.info("Installing Go...")
            self.ssh_command(node, "apt update && apt install -y golang-go")
        else:
            logger.info("✓ Go already installed")
        
        # Step 2: Create working directory
        logger.info("Creating working directory...")
        self.ssh_command(node, "mkdir -p /opt/dcgm-exporter-deployment")
        
        # Step 3: Copy dcgm-exporter source (if in project)
        dcgm_source = self.project_root / "dcgm-exporter"
        if dcgm_source.exists():
            logger.info("Copying DCGM exporter source...")
            # Create tarball and copy
            subprocess.run(
                ["tar", "-czf", "/tmp/dcgm-exporter.tar.gz", 
                 "-C", str(self.project_root), "dcgm-exporter"],
                check=True
            )
            self.copy_file(
                Path("/tmp/dcgm-exporter.tar.gz"),
                node,
                "/opt/dcgm-exporter-deployment/"
            )
            self.ssh_command(
                node,
                "cd /opt/dcgm-exporter-deployment && "
                "tar -xzf dcgm-exporter.tar.gz && "
                "rm -f dcgm-exporter.tar.gz"  # Clean up remote tarball
            )
            subprocess.run(["rm", "-f", "/tmp/dcgm-exporter.tar.gz"])  # Clean up local tarball
        else:
            logger.info("Cloning DCGM exporter from GitHub...")
            self.ssh_command(
                node,
                "cd /opt/dcgm-exporter-deployment && "
                "git clone https://github.com/NVIDIA/dcgm-exporter.git"
            )
        
        # Step 4: Build DCGM exporter
        logger.info("Building DCGM exporter...")
        self.ssh_command(
            node,
            "cd /opt/dcgm-exporter-deployment/dcgm-exporter && "
            "make binary"
        )
        
        # Step 5: Install binary and config
        logger.info("Installing DCGM exporter...")
        self.ssh_command(
            node,
            "cd /opt/dcgm-exporter-deployment/dcgm-exporter && "
            "make install"
        )
        
        # Step 6: Create HPC job mapping directory
        logger.info("Creating HPC job mapping directory...")
        job_map_dir = self.config.get("hpc_job_mapping_dir", "/run/dcgm-job-map")
        self.ssh_command(node, f"mkdir -p {job_map_dir}")
        self.ssh_command(node, f"chmod 755 {job_map_dir}")
        
        # Create working directory for the service
        logger.info("Creating working directory for service...")
        self.ssh_command(node, "mkdir -p /var/lib/dcgm-exporter")
        self.ssh_command(node, "chmod 755 /var/lib/dcgm-exporter")
        
        # Step 7: Install systemd service
        logger.info("Installing systemd service...")
        service_file = self.project_root / "systemd" / "dcgm-exporter.service"
        self.copy_file(service_file, node, "/tmp/dcgm-exporter.service")
        self.ssh_command(
            node,
            "mv /tmp/dcgm-exporter.service /etc/systemd/system/ && "
            "systemctl daemon-reload"
        )
        
        # Step 8: Enable and start the service
        logger.info("Enabling and starting DCGM exporter service...")
        self.ssh_command(node, "systemctl enable dcgm-exporter")
        
        # Restart service to ensure clean start
        logger.info("Restarting DCGM exporter service...")
        self.ssh_command(node, "systemctl restart dcgm-exporter", check=False)
        
        # Wait for service to start (give it more time)
        logger.info("Waiting for service to start...")
        time.sleep(5)
        
        # Verify service started
        result = self.ssh_command(node, "systemctl is-active dcgm-exporter", check=False)
        if result.returncode == 0 and result.stdout.strip() == "active":
            logger.info(f"✓ DCGM Exporter service is active on {node}")
        else:
            logger.error(f"✗ DCGM Exporter service is NOT active on {node}")
            # Show detailed service status for debugging
            status_result = self.ssh_command(node, "systemctl status dcgm-exporter --no-pager", check=False)
            logger.error(f"Service status output:\n{status_result.stdout}")
            # Show journal logs
            journal_result = self.ssh_command(node, "journalctl -u dcgm-exporter -n 50 --no-pager", check=False)
            logger.error(f"Recent service logs:\n{journal_result.stdout}")
            raise RuntimeError(f"DCGM Exporter service failed to start on {node}")
        
        # Verify metrics endpoint
        dcgm_port = self.config.get("dcgm_exporter_port", 9400)
        logger.info("Verifying metrics endpoint...")
        
        # Try multiple times to give service time to be ready
        for attempt in range(3):
            metrics_test = self.ssh_command(
                node, 
                f"curl -s http://localhost:{dcgm_port}/metrics | head -20",
                check=False
            )
            if metrics_test.returncode == 0 and "DCGM" in metrics_test.stdout:
                logger.info(f"✓ Metrics endpoint responding on {node}:{dcgm_port}")
                logger.debug(f"Sample metrics:\n{metrics_test.stdout[:500]}")
                break
            else:
                if attempt < 2:
                    logger.warning(f"⚠ Metrics endpoint not ready yet (attempt {attempt + 1}/3), waiting...")
                    time.sleep(3)
                else:
                    logger.error(f"✗ Metrics endpoint failed to respond on {node}:{dcgm_port}")
                    logger.error(f"Curl output: {metrics_test.stdout}")
                    logger.error(f"Curl error: {metrics_test.stderr}")
                    raise RuntimeError(f"DCGM Exporter metrics endpoint not responding on {node}")
        
        # Cleanup: Remove entire deployment directory (binary and config are already installed)
        logger.info("Cleaning up temporary files...")
        self.ssh_command(
            node,
            "rm -rf /opt/dcgm-exporter-deployment",
            check=False  # Don't fail if already removed
        )
        logger.info("✓ Temporary deployment directory removed")
        
        logger.info(f"✓ Successfully deployed DCGM exporter to {node}")
    
    def deploy_prolog_epilog(self, slurm_controller: str):
        """Deploy prolog/epilog scripts to shared storage"""
        logger.info(f"{'=' * 60}")
        logger.info("Deploying Prolog/Epilog Scripts")
        logger.info(f"{'=' * 60}")
        
        prolog_shared = self.config.get("paths", {}).get(
            "prolog_shared", "/cm/shared/apps/slurm/var/cm"
        )
        
        # Copy prolog script to shared storage
        logger.info("Copying prolog script to shared storage...")
        prolog_script = self.project_root / "slurm" / "prolog.d" / "dcgm_job_map.sh"
        self.copy_file(
            prolog_script,
            slurm_controller,
            f"{prolog_shared}/prolog-dcgm.sh"
        )
        self.ssh_command(
            slurm_controller,
            f"chmod +x {prolog_shared}/prolog-dcgm.sh"
        )
        
        # Copy epilog script to shared storage
        logger.info("Copying epilog script to shared storage...")
        epilog_script = self.project_root / "slurm" / "epilog.d" / "dcgm_job_map.sh"
        self.copy_file(
            epilog_script,
            slurm_controller,
            f"{prolog_shared}/epilog-dcgm.sh"
        )
        self.ssh_command(
            slurm_controller,
            f"chmod +x {prolog_shared}/epilog-dcgm.sh"
        )
        
        logger.info("✓ Prolog/Epilog scripts deployed to shared storage")
        
        # Create symlinks on all DGX nodes
        logger.info("")
        logger.info("Creating symlinks on DGX nodes...")
        for node in self.dgx_nodes:
            logger.info(f"  Creating symlinks on {node}...")
            
            # Ensure local prolog/epilog directories exist
            self.ssh_command(node, "mkdir -p /cm/local/apps/slurm/var/prologs")
            self.ssh_command(node, "mkdir -p /cm/local/apps/slurm/var/epilogs")
            
            # Create symlinks
            self.ssh_command(
                node,
                f"ln -sf {prolog_shared}/prolog-dcgm.sh "
                f"/cm/local/apps/slurm/var/prologs/60-prolog-dcgm.sh"
            )
            self.ssh_command(
                node,
                f"ln -sf {prolog_shared}/epilog-dcgm.sh "
                f"/cm/local/apps/slurm/var/epilogs/60-epilog-dcgm.sh"
            )
            logger.info(f"  ✓ Symlinks created on {node}")
        
        logger.info("✓ Prolog/Epilog symlinks deployed to all nodes")
    
    def deploy_bcm_role_monitor(self):
        """Deploy BCM role monitor to all DGX nodes"""
        logger.info(f"{'=' * 60}")
        logger.info("Deploying BCM Role Monitor")
        logger.info(f"{'=' * 60}")
        
        # Discover BCM headnodes
        logger.info("Discovering BCM headnodes...")
        bcm_headnodes = self._discover_bcm_headnodes()
        if not bcm_headnodes:
            logger.error("No BCM headnodes discovered. BCM role monitor requires BCM headnodes.")
            return
        
        # Create shared Prometheus targets directory
        prometheus_targets_dir = self.config.get("prometheus_targets_dir")
        if prometheus_targets_dir:
            logger.info(f"Creating Prometheus targets directory: {prometheus_targets_dir}")
            bcm_headnode = self.config.get("bcm_headnode", "localhost")
            try:
                self.ssh_command(bcm_headnode, f"mkdir -p {prometheus_targets_dir}")
                self.ssh_command(bcm_headnode, f"chmod 755 {prometheus_targets_dir}")
                logger.info(f"✓ Created {prometheus_targets_dir}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to create Prometheus targets directory: {e}")
        
        # Get BCM certificates from headnode
        logger.info("Retrieving BCM admin certificates...")
        bcm_headnode = bcm_headnodes[0]
        
        # Try multiple possible certificate locations
        cert_locations = [
            ("/root/.cm/admin.pem", "/root/.cm/admin.key"),  # BCM default location
            ("/root/admin.pem", "/root/admin.key"),          # Alternative location
        ]
        
        cert_found = False
        for cert_path, key_path in cert_locations:
            try:
                # Test if certificates exist
                result = self.ssh_command(
                    bcm_headnode, 
                    f"test -f {cert_path} && test -f {key_path} && echo 'exists'",
                    check=False
                )
                
                if result.returncode == 0 and "exists" in result.stdout:
                    logger.info(f"Found certificates at: {cert_path}, {key_path}")
                    
                    # Copy certificates from BCM headnode to local temp
                    subprocess.run(
                        ["scp", "-o", "StrictHostKeyChecking=no", 
                         f"{bcm_headnode}:{cert_path}", "/tmp/admin.pem"],
                        check=True, capture_output=True
                    )
                    subprocess.run(
                        ["scp", "-o", "StrictHostKeyChecking=no",
                         f"{bcm_headnode}:{key_path}", "/tmp/admin.key"],
                        check=True, capture_output=True
                    )
                    logger.info("✓ Retrieved BCM admin certificates")
                    cert_found = True
                    break
            except subprocess.CalledProcessError:
                continue
        
        if not cert_found:
            logger.error("Failed to retrieve BCM certificates from any known location")
            logger.error("Tried locations:")
            for cert_path, key_path in cert_locations:
                logger.error(f"  - {cert_path} / {key_path}")
            return
        
        # Deploy to each DGX node
        for node in self.dgx_nodes:
            logger.info(f"Deploying BCM role monitor to {node}...")
            try:
                self._deploy_bcm_role_monitor_to_node(node, bcm_headnodes, prometheus_targets_dir)
                logger.info(f"✓ Deployed BCM role monitor to {node}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to deploy BCM role monitor to {node}: {e}")
                continue
        
        # Cleanup local temp files
        Path("/tmp/admin.pem").unlink(missing_ok=True)
        Path("/tmp/admin.key").unlink(missing_ok=True)
        
        logger.info("✓ BCM role monitor deployed to all nodes")
    
    def _discover_bcm_headnodes(self) -> List[str]:
        """Discover BCM headnodes using cmsh"""
        try:
            result = subprocess.run(
                ['cmsh', '-c', 'device list --type headnode'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                headnodes = []
                for line in result.stdout.strip().split('\n'):
                    line = line.strip()
                    if line and 'headnode' in line.lower():
                        parts = line.split()
                        if len(parts) >= 2:
                            hostname = parts[1]
                            if hostname:
                                headnodes.append(hostname)
                return headnodes
        except Exception as e:
            logger.warning(f"Failed to discover BCM headnodes: {e}")
        
        return []
    
    def _deploy_bcm_role_monitor_to_node(self, node: str, bcm_headnodes: List[str], prometheus_targets_dir: str):
        """Deploy BCM role monitor to a single node"""
        # Create config
        config = {
            "bcm_headnodes": bcm_headnodes,
            "bcm_port": 8081,
            "cert_path": "/etc/bcm-role-monitor-dcgm/admin.pem",
            "key_path": "/etc/bcm-role-monitor-dcgm/admin.key",
            "check_interval": 60,
            "retry_interval": 600,
            "max_retries": 3,
            "prometheus_targets_dir": prometheus_targets_dir or "/cm/shared/apps/dcgm-exporter/prometheus-targets",
            "dcgm_exporter_port": self.config.get("dcgm_exporter_port", 9400),
            "cluster_name": self.config.get("cluster_name", "slurm")
        }
        
        # Write config to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f, indent=2)
            config_temp = f.name
        
        try:
            # Create directories
            self.ssh_command(node, "mkdir -p /etc/bcm-role-monitor-dcgm")
            self.ssh_command(node, "mkdir -p /var/lib/bcm-role-monitor-dcgm")
            
            # Copy config
            self.copy_file(Path(config_temp), node, "/etc/bcm-role-monitor-dcgm/config.json")
            
            # Copy certificates
            self.copy_file(Path("/tmp/admin.pem"), node, "/etc/bcm-role-monitor-dcgm/admin.pem")
            self.copy_file(Path("/tmp/admin.key"), node, "/etc/bcm-role-monitor-dcgm/admin.key")
            self.ssh_command(node, "chmod 600 /etc/bcm-role-monitor-dcgm/admin.pem")
            self.ssh_command(node, "chmod 600 /etc/bcm-role-monitor-dcgm/admin.key")
            
            # Copy monitor script
            monitor_script = self.project_root / "automation" / "role-monitor" / "bcm_role_monitor.py"
            self.copy_file(monitor_script, node, "/usr/local/bin/bcm_role_monitor_dcgm.py")
            self.ssh_command(node, "chmod +x /usr/local/bin/bcm_role_monitor_dcgm.py")
            
            # Copy and install systemd service
            service_file = self.project_root / "automation" / "role-monitor" / "bcm-role-monitor-dcgm.service"
            self.copy_file(service_file, node, "/tmp/bcm-role-monitor-dcgm.service")
            self.ssh_command(node, "mv /tmp/bcm-role-monitor-dcgm.service /etc/systemd/system/")
            
            # Enable and start service
            self.ssh_command(node, "systemctl daemon-reload")
            self.ssh_command(node, "systemctl enable bcm-role-monitor-dcgm")
            self.ssh_command(node, "systemctl restart bcm-role-monitor-dcgm")
            
            # Verify service started
            time.sleep(2)
            result = self.ssh_command(node, "systemctl is-active bcm-role-monitor-dcgm", check=False)
            if result.returncode == 0:
                logger.info(f"  ✓ BCM role monitor service is active on {node}")
            else:
                logger.warning(f"  ⚠ BCM role monitor service may not be running on {node}")
        finally:
            Path(config_temp).unlink()
    
    def create_initial_prometheus_targets(self):
        """Create initial Prometheus target files for immediate functionality"""
        logger.info(f"{'=' * 60}")
        logger.info("Creating Initial Prometheus Targets")
        logger.info(f"{'=' * 60}")
        
        prometheus_targets_dir = self.config.get("prometheus_targets_dir")
        if not prometheus_targets_dir:
            logger.warning("No Prometheus targets directory configured, skipping")
            return
        
        dcgm_port = self.config.get("dcgm_exporter_port", 9400)
        cluster_name = self.config.get("cluster_name", "slurm")
        
        # Create directory on first node or slurm controller
        target_node = self.config.get("systems", {}).get("slurm_controller") or self.dgx_nodes[0]
        logger.info(f"Creating Prometheus targets directory on {target_node}...")
        try:
            self.ssh_command(target_node, f"mkdir -p {prometheus_targets_dir}")
            self.ssh_command(target_node, f"chmod 755 {prometheus_targets_dir}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create Prometheus targets directory: {e}")
            return
        
        # Create individual target file for each node
        logger.info("")
        for node in self.dgx_nodes:
            logger.info(f"Creating Prometheus target file for {node}...")
            target_data = [{
                "targets": [f"{node}:{dcgm_port}"],
                "labels": {
                    "job": "dcgm-exporter",
                    "cluster": cluster_name,
                    "hostname": node
                }
            }]
            
            # Create temp file locally
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(target_data, f, indent=2)
                temp_file = f.name
            
            try:
                # Copy to shared storage
                target_file = f"{prometheus_targets_dir}/{node}.json"
                self.copy_file(Path(temp_file), target_node, target_file)
                logger.info(f"  ✓ Created {target_file}")
            finally:
                Path(temp_file).unlink()
        
        logger.info("")
        logger.info("✓ Initial Prometheus targets created")
        logger.info("  Note: BCM role monitor will manage these dynamically going forward")
    
    def deploy_prometheus(self):
        """Deploy Prometheus server with DCGM exporter scrape config"""
        logger.info(f"{'=' * 60}")
        logger.info("Deploying Prometheus Server")
        logger.info(f"{'=' * 60}")
        
        prometheus_server = self.config.get("prometheus_server")
        if not prometheus_server:
            logger.error("No Prometheus server specified in configuration")
            return
        
        prometheus_port = self.config.get("prometheus_port", 9090)
        prometheus_targets_dir = self.config.get("prometheus_targets_dir", "/cm/shared/apps/dcgm-exporter/prometheus-targets")
        shared_base = "/cm/shared/apps/prometheus"
        
        logger.info(f"Deploying Prometheus to: {prometheus_server}")
        logger.info("")
        
        # Step 1: Install Prometheus
        logger.info("Installing Prometheus...")
        install_commands = f"""
            # Create directories
            mkdir -p {shared_base}/{{bin,config,data}}
            
            # Download and install Prometheus
            cd /tmp
            PROM_VERSION="2.48.0"
            wget -q https://github.com/prometheus/prometheus/releases/download/v${{PROM_VERSION}}/prometheus-${{PROM_VERSION}}.linux-amd64.tar.gz
            tar -xzf prometheus-${{PROM_VERSION}}.linux-amd64.tar.gz
            
            # Install binaries
            cp prometheus-${{PROM_VERSION}}.linux-amd64/prometheus {shared_base}/bin/
            cp prometheus-${{PROM_VERSION}}.linux-amd64/promtool {shared_base}/bin/
            chmod +x {shared_base}/bin/{{prometheus,promtool}}
            
            # Copy console files
            cp -r prometheus-${{PROM_VERSION}}.linux-amd64/consoles {shared_base}/
            cp -r prometheus-${{PROM_VERSION}}.linux-amd64/console_libraries {shared_base}/
            
            # Cleanup
            rm -rf prometheus-${{PROM_VERSION}}.linux-amd64*
        """
        
        try:
            self.ssh_command(prometheus_server, install_commands.strip())
            logger.info("✓ Prometheus installed")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install Prometheus: {e}")
            return
        
        # Step 2: Create Prometheus configuration
        logger.info("Creating Prometheus configuration...")
        cluster_name = self.config.get("cluster_name", "slurm")
        
        prometheus_config = f"""
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: '{cluster_name}'
    monitor: 'dcgm-exporter'

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:{prometheus_port}']
  
  - job_name: 'dcgm-exporter'
    file_sd_configs:
      - files:
          - '{prometheus_targets_dir}/*.json'
        refresh_interval: 30s
"""
        
        # Write config to temp file and copy
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write(prometheus_config)
            temp_config = f.name
        
        try:
            self.copy_file(Path(temp_config), prometheus_server, f"{shared_base}/config/prometheus.yml")
            logger.info("✓ Prometheus configuration created")
        finally:
            Path(temp_config).unlink()
        
        # Step 3: Create systemd service
        logger.info("Creating Prometheus systemd service...")
        
        service_content = f"""[Unit]
Description=Prometheus Monitoring System
Documentation=https://prometheus.io/docs/introduction/overview/
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
ExecStart={shared_base}/bin/prometheus \\
  --config.file={shared_base}/config/prometheus.yml \\
  --storage.tsdb.path={shared_base}/data \\
  --web.console.templates={shared_base}/consoles \\
  --web.console.libraries={shared_base}/console_libraries \\
  --web.listen-address=0.0.0.0:{prometheus_port}

Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=prometheus

[Install]
WantedBy=multi-user.target
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.service', delete=False) as f:
            f.write(service_content)
            temp_service = f.name
        
        try:
            self.copy_file(Path(temp_service), prometheus_server, "/tmp/prometheus.service")
            self.ssh_command(
                prometheus_server,
                "mv /tmp/prometheus.service /etc/systemd/system/ && systemctl daemon-reload"
            )
            logger.info("✓ Prometheus systemd service created")
        finally:
            Path(temp_service).unlink()
        
        # Step 4: Enable and start Prometheus
        logger.info("Starting Prometheus service...")
        self.ssh_command(prometheus_server, "systemctl enable prometheus")
        self.ssh_command(prometheus_server, "systemctl restart prometheus")
        
        # Wait and verify
        time.sleep(3)
        result = self.ssh_command(prometheus_server, "systemctl is-active prometheus", check=False)
        if result.returncode == 0 and result.stdout.strip() == "active":
            logger.info(f"✓ Prometheus service is active on {prometheus_server}")
            logger.info(f"  Access Prometheus at: http://{prometheus_server}:{prometheus_port}")
        else:
            logger.error(f"✗ Prometheus service failed to start on {prometheus_server}")
            status = self.ssh_command(prometheus_server, "systemctl status prometheus --no-pager", check=False)
            logger.error(f"Service status:\n{status.stdout}")
        
        logger.info("")
        logger.info("✓ Prometheus deployment complete")
    
    def deploy_grafana(self):
        """Deploy Grafana server with Prometheus datasource and DCGM dashboard"""
        logger.info(f"{'=' * 60}")
        logger.info("Deploying Grafana Server")
        logger.info(f"{'=' * 60}")
        
        grafana_server = self.config.get("grafana_server")
        if not grafana_server:
            logger.error("No Grafana server specified in configuration")
            return
        
        grafana_port = self.config.get("grafana_port", 3000)
        prometheus_server = self.config.get("prometheus_server", "localhost")
        prometheus_port = self.config.get("prometheus_port", 9090)
        shared_base = "/cm/shared/apps/grafana"
        
        logger.info(f"Deploying Grafana to: {grafana_server}")
        logger.info("")
        
        # Step 1: Install Grafana
        logger.info("Installing Grafana...")
        install_commands = f"""
            # Install dependencies
            apt-get update && apt-get install -y apt-transport-https software-properties-common wget
            
            # Add Grafana GPG key and repository
            wget -q -O /usr/share/keyrings/grafana.key https://apt.grafana.com/gpg.key
            echo "deb [signed-by=/usr/share/keyrings/grafana.key] https://apt.grafana.com stable main" | tee /etc/apt/sources.list.d/grafana.list
            
            # Install Grafana
            apt-get update
            apt-get install -y grafana
        """
        
        try:
            self.ssh_command(grafana_server, install_commands.strip())
            logger.info("✓ Grafana installed")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install Grafana: {e}")
            return
        
        # Step 2: Configure Grafana
        logger.info("Configuring Grafana...")
        grafana_config = f"""
[server]
protocol = http
http_port = {grafana_port}
domain = {grafana_server}

[security]
admin_user = admin
admin_password = admin

[auth.anonymous]
enabled = false

[paths]
provisioning = /etc/grafana/provisioning
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ini', delete=False) as f:
            f.write(grafana_config)
            temp_config = f.name
        
        try:
            self.copy_file(Path(temp_config), grafana_server, "/tmp/grafana.ini")
            self.ssh_command(grafana_server, "mv /tmp/grafana.ini /etc/grafana/grafana.ini")
            self.ssh_command(grafana_server, "chown grafana:grafana /etc/grafana/grafana.ini")
            self.ssh_command(grafana_server, "chmod 640 /etc/grafana/grafana.ini")
            logger.info("✓ Grafana configuration created")
        finally:
            Path(temp_config).unlink()
        
        # Step 3: Configure Prometheus datasource
        logger.info("Configuring Prometheus datasource...")
        datasource_config = f"""
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://{prometheus_server}:{prometheus_port}
    isDefault: true
    editable: false
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(datasource_config)
            temp_datasource = f.name
        
        try:
            self.ssh_command(grafana_server, "mkdir -p /etc/grafana/provisioning/datasources")
            self.copy_file(Path(temp_datasource), grafana_server, "/etc/grafana/provisioning/datasources/prometheus.yaml")
            self.ssh_command(grafana_server, "chown -R grafana:grafana /etc/grafana/provisioning/datasources")
            logger.info("✓ Prometheus datasource configured")
        finally:
            Path(temp_datasource).unlink()
        
        # Step 4: Import DCGM dashboard from cloned dcgm-exporter repo
        logger.info("Importing DCGM dashboard...")
        
        # Check if dcgm-exporter is available locally
        dcgm_source = self.project_root / "dcgm-exporter"
        dashboard_source = dcgm_source / "grafana" / "dcgm-exporter-dashboard.json"
        
        if dashboard_source.exists():
            logger.info(f"Found DCGM dashboard at: {dashboard_source}")
            
            # Create dashboard provisioning config
            dashboard_provisioning = """
apiVersion: 1

providers:
  - name: 'DCGM Exporter'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
"""
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(dashboard_provisioning)
                temp_provisioning = f.name
            
            try:
                # Create dashboard directory and copy provisioning config
                self.ssh_command(grafana_server, "mkdir -p /etc/grafana/provisioning/dashboards")
                self.ssh_command(grafana_server, "mkdir -p /var/lib/grafana/dashboards")
                self.copy_file(Path(temp_provisioning), grafana_server, "/etc/grafana/provisioning/dashboards/dcgm.yaml")
                
                # Copy default DCGM dashboard from nvidia repo
                self.copy_file(dashboard_source, grafana_server, "/var/lib/grafana/dashboards/dcgm-exporter-dashboard.json")
                logger.info("✓ Default DCGM dashboard imported")
                
                # Copy single-job dashboard from project
                single_job_dashboard = self.project_root / "grafana" / "dcgm-single-job-stats.json"
                if single_job_dashboard.exists():
                    self.copy_file(single_job_dashboard, grafana_server, "/var/lib/grafana/dashboards/dcgm-single-job-stats.json")
                    logger.info("✓ Single Job Stats dashboard imported")
                else:
                    logger.warning("Single Job Stats dashboard not found in project grafana/ directory")
                
                # Fix permissions for Grafana user
                self.ssh_command(grafana_server, "chown -R grafana:grafana /etc/grafana/provisioning/dashboards")
                self.ssh_command(grafana_server, "chown -R grafana:grafana /var/lib/grafana/dashboards")
                
                logger.info("✓ DCGM dashboards imported")
            finally:
                Path(temp_provisioning).unlink()
        else:
            logger.warning("DCGM dashboard not found in dcgm-exporter repository")
            logger.warning("Dashboard can be manually imported later from: https://github.com/NVIDIA/dcgm-exporter/tree/main/grafana")
        
        # Step 5: Enable and start Grafana
        logger.info("Starting Grafana service...")
        self.ssh_command(grafana_server, "systemctl enable grafana-server")
        self.ssh_command(grafana_server, "systemctl restart grafana-server")
        
        # Wait and verify
        time.sleep(5)
        result = self.ssh_command(grafana_server, "systemctl is-active grafana-server", check=False)
        if result.returncode == 0 and result.stdout.strip() == "active":
            logger.info(f"✓ Grafana service is active on {grafana_server}")
            logger.info(f"  Access Grafana at: http://{grafana_server}:{grafana_port}")
            logger.info(f"  Default credentials: admin / admin")
            logger.info(f"  DCGM Dashboard: http://{grafana_server}:{grafana_port}/d/Oxed_c6Wz/nvidia-dcgm-exporter-dashboard")
            logger.info(f"  Single Job Stats: http://{grafana_server}:{grafana_port}/d/dcgm-single-job/dcgm-single-job-stats")
        else:
            logger.error(f"✗ Grafana service failed to start on {grafana_server}")
            status = self.ssh_command(grafana_server, "systemctl status grafana-server --no-pager", check=False)
            logger.error(f"Service status:\n{status.stdout}")
        
        logger.info("")
        logger.info("✓ Grafana deployment complete")
    
    def deploy_all(self):
        """Deploy to all configured nodes"""
        logger.info("Starting DCGM Exporter deployment")
        logger.info(f"Target nodes: {', '.join(self.dgx_nodes)}")
        logger.info("")
        
        # Deploy to each DGX node
        for node in self.dgx_nodes:
            try:
                self.deploy_to_node(node)
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to deploy to {node}: {e}")
                logger.error(f"stdout: {e.stdout}")
                logger.error(f"stderr: {e.stderr}")
                continue
        
        # Deploy prolog/epilog if we have a slurm controller
        if "systems" in self.config:
            slurm_controller = self.config["systems"].get("slurm_controller")
            if slurm_controller:
                try:
                    self.deploy_prolog_epilog(slurm_controller)
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to deploy prolog/epilog: {e}")
        
        # Create initial Prometheus targets for immediate functionality
        logger.info("")
        try:
            self.create_initial_prometheus_targets()
        except Exception as e:
            logger.error(f"Failed to create initial Prometheus targets: {e}")
        
        # Deploy Prometheus if requested
        logger.info("")
        deploy_prometheus_option = self.config.get("deployment_options", {}).get("deploy_prometheus", False)
        if deploy_prometheus_option:
            try:
                self.deploy_prometheus()
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to deploy Prometheus: {e}")
            except Exception as e:
                logger.error(f"Error deploying Prometheus: {e}")
        elif self.config.get("use_existing_prometheus", False):
            logger.info("Using existing Prometheus server - skipping Prometheus deployment")
        else:
            logger.info("Prometheus deployment not configured")
        
        # Deploy Grafana if requested
        logger.info("")
        deploy_grafana_option = self.config.get("deployment_options", {}).get("deploy_grafana", False)
        if deploy_grafana_option:
            try:
                self.deploy_grafana()
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to deploy Grafana: {e}")
            except Exception as e:
                logger.error(f"Error deploying Grafana: {e}")
        elif self.config.get("use_existing_grafana", False):
            logger.info("Using existing Grafana server - skipping Grafana deployment")
        else:
            logger.info("Grafana deployment not configured")
        
        # Deploy BCM role monitor (manages Prometheus targets dynamically going forward)
        logger.info("")
        deploy_bcm_role_monitor_option = self.config.get("deployment_options", {}).get("deploy_bcm_role_monitor", True)
        if deploy_bcm_role_monitor_option:
            try:
                self.deploy_bcm_role_monitor()
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to deploy BCM role monitor: {e}")
            except Exception as e:
                logger.error(f"Error deploying BCM role monitor: {e}")
        else:
            logger.info("Skipping BCM role monitor deployment (disabled in config)")
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("Deployment Complete!")
        logger.info("=" * 60)


def main():
    # Determine default config path relative to script location
    script_dir = Path(__file__).parent
    default_config = script_dir / "configs" / "config.json"
    
    parser = argparse.ArgumentParser(
        description="Deploy DCGM Exporter to DGX nodes"
    )
    parser.add_argument(
        "--config",
        default=str(default_config) if default_config.exists() else None,
        help=f"Path to configuration file (default: {default_config})"
    )
    parser.add_argument(
        "--dgx-nodes",
        nargs="+",
        help="List of DGX nodes to deploy to"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show commands without executing them"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if not args.config and not args.dgx_nodes:
        parser.error("Must provide either --config or --dgx-nodes. "
                    f"Default config not found at: {default_config}")
    
    deployer = DCGMExporterDeployer(args.config, args.dgx_nodes, dry_run=args.dry_run)
    deployer.deploy_all()


if __name__ == "__main__":
    main()

