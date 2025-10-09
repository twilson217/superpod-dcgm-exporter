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
from pathlib import Path
from typing import List, Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DCGMExporterDeployer:
    """Deploy DCGM Exporter to DGX nodes"""
    
    def __init__(self, config_path: Optional[str] = None, dgx_nodes: Optional[List[str]] = None):
        self.project_root = Path(__file__).parent.parent
        
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
        ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", node, command]
        logger.debug(f"Running on {node}: {command}")
        return subprocess.run(ssh_cmd, capture_output=True, text=True, check=check)
    
    def copy_file(self, local_path: Path, node: str, remote_path: str):
        """Copy file to remote node"""
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
                "tar -xzf dcgm-exporter.tar.gz"
            )
            subprocess.run(["rm", "/tmp/dcgm-exporter.tar.gz"])
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
        self.ssh_command(node, "systemctl start dcgm-exporter")
        
        # Verify service started
        self.ssh_command(node, "systemctl is-active dcgm-exporter")
        
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
    
    def deploy_all(self):
        """Deploy to all configured nodes"""
        logger.info("Starting DCGM Exporter deployment")
        logger.info(f"Target nodes: {', '.join(self.dgx_nodes)}")
        logger.info("")
        
        # Create Prometheus targets directory on BCM headnode
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
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if not args.config and not args.dgx_nodes:
        parser.error("Must provide either --config or --dgx-nodes. "
                    f"Default config not found at: {default_config}")
    
    deployer = DCGMExporterDeployer(args.config, args.dgx_nodes)
    deployer.deploy_all()


if __name__ == "__main__":
    main()

