#!/usr/bin/env python3
"""
BCM Role Monitor for DCGM Exporter
Monitors BCM role assignments and manages DCGM exporter service and Prometheus targets
Adapted from Jobstats BCM role monitor to include dcgm-exporter service management
"""

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
import time
import urllib.request
import ssl
from pathlib import Path
from typing import Dict, List, Optional, Set

# Default configuration
DEFAULT_CONFIG = {
    "bcm_headnodes": [],
    "bcm_port": 8081,
    "cert_path": "/etc/bcm-role-monitor/admin.pem",
    "key_path": "/etc/bcm-role-monitor/admin.key",
    "check_interval": 60,
    "retry_interval": 600,
    "max_retries": 3,
    "prometheus_targets_dir": "/cm/shared/apps/dcgm-exporter/prometheus-targets",
    "node_exporter_port": 9100,
    "cgroup_exporter_port": 9306,
    "nvidia_gpu_exporter_port": 9445,
    "dcgm_exporter_port": 9400,
    "cluster_name": "slurm",
}

# Services to manage
MANAGED_SERVICES = [
    "node_exporter",
    "cgroup_exporter",
    "nvidia_gpu_exporter",
    "dcgm-exporter",  # New: DCGM exporter
]

# State file location
STATE_DIR = "/var/lib/bcm-role-monitor"


class BCMRoleMonitor:
    """Monitor BCM roles and manage exporter services"""

    def __init__(self, config_path: str, prometheus_targets_dir: Optional[str] = None):
        self.config = self._load_config(config_path)
        
        # Override prometheus targets dir if provided
        if prometheus_targets_dir:
            self.config["prometheus_targets_dir"] = prometheus_targets_dir
        
        self.hostname = socket.gethostname().split(".")[0]
        self.state_file = Path(STATE_DIR) / f"{self.hostname}_state.json"
        self.state = self._load_state()
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
        )
        self.logger = logging.getLogger(__name__)
        
        # Ensure state directory exists
        Path(STATE_DIR).mkdir(parents=True, exist_ok=True)
        
        # Ensure prometheus targets directory exists
        targets_dir = Path(self.config["prometheus_targets_dir"])
        if not targets_dir.exists():
            self.logger.warning(
                f"Prometheus targets directory does not exist: {targets_dir}"
            )
            self.logger.info(f"Attempting to create: {targets_dir}")
            try:
                targets_dir.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"Created Prometheus targets directory: {targets_dir}")
            except Exception as e:
                self.logger.error(f"Failed to create targets directory: {e}")

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from file"""
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
            # Merge with defaults
            merged_config = DEFAULT_CONFIG.copy()
            merged_config.update(config)
            return merged_config
        except FileNotFoundError:
            logging.error(f"Config file not found: {config_path}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON in config file: {e}")
            sys.exit(1)

    def _load_state(self) -> Dict:
        """Load persistent state"""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logging.warning(f"Could not load state file: {e}")
        return {"has_role": False, "service_retries": {}}

    def _save_state(self):
        """Save persistent state"""
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            self.logger.error(f"Could not save state file: {e}")

    def check_bcm_role(self) -> bool:
        """Check if this node has the slurmclient role in BCM"""
        for headnode in self.config["bcm_headnodes"]:
            try:
                url = f"https://{headnode}:{self.config['bcm_port']}/rest/v1/device"
                
                # Create SSL context
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                context.load_cert_chain(
                    self.config["cert_path"], self.config["key_path"]
                )
                
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, context=context, timeout=10) as response:
                    data = json.loads(response.read().decode())
                    
                    # Find this node in the devices
                    for device in data.get("data", []):
                        if device.get("hostname", "").split(".")[0] == self.hostname:
                            roles = device.get("roles", [])
                            has_role = "slurmclient" in roles
                            self.logger.debug(
                                f"Node {self.hostname} roles: {roles}, "
                                f"has slurmclient: {has_role}"
                            )
                            return has_role
                    
                    self.logger.warning(
                        f"Node {self.hostname} not found in BCM device list"
                    )
                    return False
                    
            except Exception as e:
                self.logger.warning(
                    f"Failed to check BCM role on {headnode}: {e}"
                )
                continue
        
        self.logger.error("Could not reach any BCM headnode")
        return False

    def manage_service(self, service: str, action: str) -> bool:
        """Start or stop a systemd service"""
        try:
            if action == "start":
                subprocess.run(
                    ["systemctl", "start", service],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["systemctl", "enable", service],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.logger.info(f"Started and enabled service: {service}")
            elif action == "stop":
                subprocess.run(
                    ["systemctl", "stop", service],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.logger.info(f"Stopped service: {service}")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to {action} service {service}: {e.stderr}")
            return False

    def write_prometheus_targets(self):
        """Write Prometheus target file for all exporters (single file)"""
        targets_dir = Path(self.config["prometheus_targets_dir"])
        target_file = targets_dir / f"{self.hostname}.json"
        
        targets = [
            {
                "targets": [f"{self.hostname}:{self.config['node_exporter_port']}"],
                "labels": {
                    "job": "node_exporter",
                    "cluster": self.config["cluster_name"],
                    "hostname": self.hostname,
                },
            },
            {
                "targets": [f"{self.hostname}:{self.config['cgroup_exporter_port']}"],
                "labels": {
                    "job": "cgroup_exporter",
                    "cluster": self.config["cluster_name"],
                    "hostname": self.hostname,
                },
            },
            {
                "targets": [f"{self.hostname}:{self.config['nvidia_gpu_exporter_port']}"],
                "labels": {
                    "job": "gpu_exporter",
                    "cluster": self.config["cluster_name"],
                    "hostname": self.hostname,
                },
            },
            {
                "targets": [f"{self.hostname}:{self.config['dcgm_exporter_port']}"],
                "labels": {
                    "job": "dcgm_exporter",
                    "cluster": self.config["cluster_name"],
                    "hostname": self.hostname,
                },
            },
        ]
        
        try:
            with open(target_file, "w") as f:
                json.dump(targets, f, indent=2)
            self.logger.info(f"Created Prometheus target file: {target_file}")
        except Exception as e:
            self.logger.error(f"Failed to write Prometheus target file: {e}")

    def remove_prometheus_targets(self):
        """Remove Prometheus target file"""
        targets_dir = Path(self.config["prometheus_targets_dir"])
        target_file = targets_dir / f"{self.hostname}.json"
        
        if target_file.exists():
            try:
                target_file.unlink()
                self.logger.info(f"Removed Prometheus target file: {target_file}")
            except Exception as e:
                self.logger.error(f"Failed to remove Prometheus target file: {e}")

    def handle_role_added(self):
        """Handle when slurmclient role is added"""
        self.logger.info(f"Node {self.hostname} assigned slurmclient role")
        
        # Start all managed services
        for service in MANAGED_SERVICES:
            success = self.manage_service(service, "start")
            if not success:
                # Track retry count
                retries = self.state["service_retries"].get(service, 0)
                self.state["service_retries"][service] = retries + 1
                
                if retries < self.config["max_retries"]:
                    self.logger.warning(
                        f"Will retry starting {service} "
                        f"(attempt {retries + 1}/{self.config['max_retries']})"
                    )
            else:
                # Reset retry count on success
                self.state["service_retries"][service] = 0
        
        # Write Prometheus targets
        self.write_prometheus_targets()
        
        self.state["has_role"] = True
        self._save_state()

    def handle_role_removed(self):
        """Handle when slurmclient role is removed"""
        self.logger.info(f"Node {self.hostname} removed from slurmclient role")
        
        # Stop all managed services
        for service in MANAGED_SERVICES:
            self.manage_service(service, "stop")
        
        # Remove Prometheus targets
        self.remove_prometheus_targets()
        
        self.state["has_role"] = False
        self.state["service_retries"] = {}
        self._save_state()

    def run(self):
        """Main monitoring loop"""
        self.logger.info(
            f"Starting BCM role monitor for node {self.hostname}"
        )
        self.logger.info(
            f"Prometheus targets directory: {self.config['prometheus_targets_dir']}"
        )
        
        while True:
            try:
                has_role = self.check_bcm_role()
                
                if has_role and not self.state["has_role"]:
                    self.handle_role_added()
                elif not has_role and self.state["has_role"]:
                    self.handle_role_removed()
                else:
                    self.logger.debug(
                        f"No role change detected (has_role={has_role})"
                    )
                
                time.sleep(self.config["check_interval"])
                
            except KeyboardInterrupt:
                self.logger.info("Received interrupt signal, shutting down")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in monitoring loop: {e}")
                time.sleep(self.config["check_interval"])


def main():
    parser = argparse.ArgumentParser(
        description="BCM Role Monitor for DCGM Exporter and Jobstats Exporters"
    )
    parser.add_argument(
        "--config",
        default="/etc/bcm-role-monitor/config.json",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--prometheus-targets-dir",
        help="Override Prometheus targets directory from config",
    )
    
    args = parser.parse_args()
    
    monitor = BCMRoleMonitor(args.config, args.prometheus_targets_dir)
    monitor.run()


if __name__ == "__main__":
    main()

