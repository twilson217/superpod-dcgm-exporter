#!/usr/bin/env python3
"""
DCGM Exporter Deployment Testing Script

Comprehensive automated testing for DCGM exporter deployment on BCM-managed SuperPOD.
Tests all components: services, metrics, job mapping, Prometheus targets, etc.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


class TestResult:
    """Test result container"""
    def __init__(self, name: str, passed: bool, message: str, details: str = ""):
        self.name = name
        self.passed = passed
        self.message = message
        self.details = details
        self.timestamp = datetime.now()


class DCGMExporterTester:
    """Comprehensive DCGM Exporter deployment tester"""
    
    def __init__(self, config_path: Optional[str] = None, dgx_nodes: Optional[List[str]] = None):
        self.results: List[TestResult] = []
        self.config = self._load_config(config_path) if config_path else {}
        self.dgx_nodes = dgx_nodes or self.config.get("systems", {}).get("dgx_nodes", [])
        self.slurm_controller = self.config.get("systems", {}).get("slurm_controller")
        self.prometheus_targets_dir = self.config.get(
            "prometheus_targets_dir",
            "/cm/shared/apps/dcgm-exporter/prometheus-targets"
        )
        self.dcgm_port = self.config.get("dcgm_exporter_port", 9400)
        self.job_map_dir = self.config.get("hpc_job_mapping_dir", "/run/dcgm-job-map")
    
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"{Colors.YELLOW}Warning: Could not load config: {e}{Colors.END}")
            return {}
    
    def ssh_command(self, node: str, command: str, timeout: int = 30) -> Tuple[int, str, str]:
        """Execute SSH command and return exit code, stdout, stderr"""
        ssh_cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=5",
            node,
            command
        ]
        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"Command timed out after {timeout}s"
        except Exception as e:
            return -1, "", str(e)
    
    def add_result(self, name: str, passed: bool, message: str, details: str = ""):
        """Add test result"""
        result = TestResult(name, passed, message, details)
        self.results.append(result)
        
        # Print result immediately
        status = f"{Colors.GREEN}✓ PASS{Colors.END}" if passed else f"{Colors.RED}✗ FAIL{Colors.END}"
        print(f"{status} {name}: {message}")
        if details and not passed:
            print(f"      {details}")
    
    def test_ssh_connectivity(self) -> bool:
        """Test SSH connectivity to all nodes"""
        print(f"\n{Colors.BOLD}=== Testing SSH Connectivity ==={Colors.END}")
        
        all_passed = True
        for node in self.dgx_nodes:
            returncode, stdout, stderr = self.ssh_command(node, "hostname")
            passed = returncode == 0
            all_passed &= passed
            
            if passed:
                self.add_result(
                    f"SSH to {node}",
                    True,
                    f"Connected successfully (hostname: {stdout.strip()})"
                )
            else:
                self.add_result(
                    f"SSH to {node}",
                    False,
                    "SSH connection failed",
                    stderr
                )
        
        return all_passed
    
    def test_dcgm_service(self) -> bool:
        """Test DCGM exporter service status on all nodes"""
        print(f"\n{Colors.BOLD}=== Testing DCGM Exporter Service ==={Colors.END}")
        
        all_passed = True
        for node in self.dgx_nodes:
            # Check if service exists
            returncode, stdout, stderr = self.ssh_command(
                node,
                "systemctl list-unit-files | grep dcgm-exporter"
            )
            
            if returncode != 0:
                self.add_result(
                    f"Service installed on {node}",
                    False,
                    "dcgm-exporter.service not found"
                )
                all_passed = False
                continue
            
            # Check if service is active
            returncode, stdout, stderr = self.ssh_command(
                node,
                "systemctl is-active dcgm-exporter"
            )
            
            is_active = stdout.strip() == "active"
            self.add_result(
                f"Service status on {node}",
                is_active,
                f"Service is {stdout.strip()}" if is_active else "Service not active",
                stderr if not is_active else ""
            )
            all_passed &= is_active
            
            # Check if service is enabled
            returncode, stdout, stderr = self.ssh_command(
                node,
                "systemctl is-enabled dcgm-exporter"
            )
            
            is_enabled = stdout.strip() == "enabled"
            self.add_result(
                f"Service enabled on {node}",
                is_enabled,
                f"Service is {stdout.strip()}" if is_enabled else "Service not enabled"
            )
        
        return all_passed
    
    def test_metrics_endpoint(self) -> bool:
        """Test DCGM metrics endpoint accessibility and content"""
        print(f"\n{Colors.BOLD}=== Testing Metrics Endpoint ==={Colors.END}")
        
        all_passed = True
        for node in self.dgx_nodes:
            # Test endpoint accessibility
            returncode, stdout, stderr = self.ssh_command(
                node,
                f"curl -s -m 5 http://localhost:{self.dcgm_port}/metrics | head -20"
            )
            
            if returncode != 0:
                self.add_result(
                    f"Metrics endpoint on {node}",
                    False,
                    f"Cannot reach http://localhost:{self.dcgm_port}/metrics",
                    stderr
                )
                all_passed = False
                continue
            
            # Check for DCGM metrics
            has_dcgm_metrics = "DCGM_FI_" in stdout
            self.add_result(
                f"DCGM metrics on {node}",
                has_dcgm_metrics,
                "DCGM metrics found" if has_dcgm_metrics else "No DCGM metrics in output",
                f"Sample output:\n{stdout[:200]}..." if not has_dcgm_metrics else ""
            )
            all_passed &= has_dcgm_metrics
            
            # Count metrics
            returncode, stdout, stderr = self.ssh_command(
                node,
                f"curl -s http://localhost:{self.dcgm_port}/metrics | grep -c '^DCGM_FI_'"
            )
            
            try:
                metric_count = int(stdout.strip())
                passed = metric_count > 0
                self.add_result(
                    f"Metric count on {node}",
                    passed,
                    f"Found {metric_count} DCGM metrics" if passed else "No metrics found"
                )
                all_passed &= passed
            except ValueError:
                self.add_result(
                    f"Metric count on {node}",
                    False,
                    "Could not count metrics"
                )
                all_passed = False
        
        return all_passed
    
    def test_gpu_detection(self) -> bool:
        """Test that GPUs are detected and reported"""
        print(f"\n{Colors.BOLD}=== Testing GPU Detection ==={Colors.END}")
        
        all_passed = True
        for node in self.dgx_nodes:
            # Check nvidia-smi
            returncode, stdout, stderr = self.ssh_command(
                node,
                "nvidia-smi --query-gpu=index,name,uuid --format=csv,noheader | wc -l"
            )
            
            if returncode != 0:
                self.add_result(
                    f"nvidia-smi on {node}",
                    False,
                    "nvidia-smi command failed",
                    stderr
                )
                all_passed = False
                continue
            
            try:
                gpu_count = int(stdout.strip())
                passed = gpu_count > 0
                self.add_result(
                    f"GPU count on {node}",
                    passed,
                    f"Found {gpu_count} GPU(s)" if passed else "No GPUs detected"
                )
                all_passed &= passed
                
                # Check that metrics include GPU labels
                returncode, stdout, stderr = self.ssh_command(
                    node,
                    f"curl -s http://localhost:{self.dcgm_port}/metrics | grep -c 'gpu=\"'"
                )
                
                has_gpu_labels = int(stdout.strip()) > 0
                self.add_result(
                    f"GPU labels in metrics on {node}",
                    has_gpu_labels,
                    f"GPU labels present" if has_gpu_labels else "No GPU labels found"
                )
                
            except ValueError:
                self.add_result(
                    f"GPU count on {node}",
                    False,
                    "Could not parse GPU count"
                )
                all_passed = False
        
        return all_passed
    
    def test_job_mapping_directory(self) -> bool:
        """Test HPC job mapping directory setup"""
        print(f"\n{Colors.BOLD}=== Testing Job Mapping Setup ==={Colors.END}")
        
        all_passed = True
        for node in self.dgx_nodes:
            # Check if directory exists
            returncode, stdout, stderr = self.ssh_command(
                node,
                f"test -d {self.job_map_dir} && echo 'exists' || echo 'missing'"
            )
            
            exists = stdout.strip() == "exists"
            self.add_result(
                f"Job mapping dir on {node}",
                exists,
                f"{self.job_map_dir} exists" if exists else f"{self.job_map_dir} not found"
            )
            all_passed &= exists
            
            if exists:
                # Check permissions
                returncode, stdout, stderr = self.ssh_command(
                    node,
                    f"ls -ld {self.job_map_dir}"
                )
                
                self.add_result(
                    f"Job mapping permissions on {node}",
                    True,
                    f"Permissions: {stdout.strip()}"
                )
        
        return all_passed
    
    def test_prolog_epilog_scripts(self) -> bool:
        """Test Slurm prolog/epilog script installation"""
        print(f"\n{Colors.BOLD}=== Testing Prolog/Epilog Scripts ==={Colors.END}")
        
        if not self.slurm_controller:
            print(f"{Colors.YELLOW}Skipping: No Slurm controller configured{Colors.END}")
            return True
        
        all_passed = True
        
        # Check shared storage scripts
        for script_type, script_name in [
            ("prolog", "prolog-dcgm.sh"),
            ("epilog", "epilog-dcgm.sh")
        ]:
            returncode, stdout, stderr = self.ssh_command(
                self.slurm_controller,
                f"test -f /cm/shared/apps/slurm/var/cm/{script_name} && echo 'exists' || echo 'missing'"
            )
            
            exists = stdout.strip() == "exists"
            self.add_result(
                f"Shared {script_type} script",
                exists,
                f"/cm/shared/apps/slurm/var/cm/{script_name} " + 
                ("exists" if exists else "not found")
            )
            all_passed &= exists
            
            if exists:
                # Check if executable
                returncode, stdout, stderr = self.ssh_command(
                    self.slurm_controller,
                    f"test -x /cm/shared/apps/slurm/var/cm/{script_name} && echo 'executable' || echo 'not executable'"
                )
                
                is_exec = stdout.strip() == "executable"
                self.add_result(
                    f"Shared {script_type} executable",
                    is_exec,
                    f"Script is {'executable' if is_exec else 'not executable'}"
                )
        
        # Check symlinks on DGX nodes
        for node in self.dgx_nodes:
            for script_type, script_path in [
                ("prolog", "/cm/local/apps/slurm/var/prologs/60-prolog-dcgm.sh"),
                ("epilog", "/cm/local/apps/slurm/var/epilogs/60-epilog-dcgm.sh")
            ]:
                returncode, stdout, stderr = self.ssh_command(
                    node,
                    f"test -L {script_path} && echo 'exists' || echo 'missing'"
                )
                
                exists = stdout.strip() == "exists"
                self.add_result(
                    f"{script_type.capitalize()} symlink on {node}",
                    exists,
                    f"{script_path} " + ("exists" if exists else "not found")
                )
        
        return all_passed
    
    def test_prometheus_targets(self) -> bool:
        """Test Prometheus target file generation"""
        print(f"\n{Colors.BOLD}=== Testing Prometheus Target Files ==={Colors.END}")
        
        # Check if directory exists
        returncode, stdout, stderr = self.ssh_command(
            self.dgx_nodes[0] if self.dgx_nodes else "localhost",
            f"test -d {self.prometheus_targets_dir} && echo 'exists' || echo 'missing'"
        )
        
        dir_exists = stdout.strip() == "exists"
        self.add_result(
            "Prometheus targets directory",
            dir_exists,
            f"{self.prometheus_targets_dir} " + ("exists" if dir_exists else "not found")
        )
        
        if not dir_exists:
            return False
        
        all_passed = True
        
        # Check for target files
        returncode, stdout, stderr = self.ssh_command(
            self.dgx_nodes[0] if self.dgx_nodes else "localhost",
            f"ls {self.prometheus_targets_dir}/*.json 2>/dev/null | wc -l"
        )
        
        try:
            file_count = int(stdout.strip())
            self.add_result(
                "Prometheus target files",
                file_count > 0,
                f"Found {file_count} target file(s)" if file_count > 0 else "No target files found"
            )
            
            if file_count > 0:
                # Check file format
                returncode, stdout, stderr = self.ssh_command(
                    self.dgx_nodes[0] if self.dgx_nodes else "localhost",
                    f"cat {self.prometheus_targets_dir}/*.json | head -1"
                )
                
                try:
                    json.loads(stdout)
                    self.add_result(
                        "Target file format",
                        True,
                        "Valid JSON format"
                    )
                except json.JSONDecodeError:
                    self.add_result(
                        "Target file format",
                        False,
                        "Invalid JSON format",
                        stdout[:200]
                    )
                    all_passed = False
        
        except ValueError:
            self.add_result(
                "Prometheus target files",
                False,
                "Could not count target files"
            )
            all_passed = False
        
        return all_passed
    
    def test_with_sample_job(self) -> bool:
        """Test job mapping with a sample Slurm job"""
        print(f"\n{Colors.BOLD}=== Testing with Sample Job (Optional) ==={Colors.END}")
        
        if not self.slurm_controller:
            print(f"{Colors.YELLOW}Skipping: No Slurm controller configured{Colors.END}")
            return True
        
        print(f"{Colors.YELLOW}Note: This test requires submitting a Slurm job{Colors.END}")
        print(f"{Colors.YELLOW}Skipping automatic job submission - run manually to test{Colors.END}")
        
        self.add_result(
            "Sample job test",
            True,
            "Skipped - run manually with: srun --gpus=1 nvidia-smi"
        )
        
        return True
    
    def test_bcm_role_monitor(self) -> bool:
        """Test BCM role monitor service (if deployed)"""
        print(f"\n{Colors.BOLD}=== Testing BCM Role Monitor (Optional) ==={Colors.END}")
        
        all_passed = True
        deployed_count = 0
        
        for node in self.dgx_nodes:
            # Check if service exists
            returncode, stdout, stderr = self.ssh_command(
                node,
                "systemctl list-unit-files | grep -c bcm-role-monitor"
            )
            
            if returncode == 0 and int(stdout.strip()) > 0:
                deployed_count += 1
                
                # Check service status
                returncode, stdout, stderr = self.ssh_command(
                    node,
                    "systemctl is-active bcm-role-monitor"
                )
                
                is_active = stdout.strip() == "active"
                self.add_result(
                    f"BCM role monitor on {node}",
                    is_active,
                    f"Service is {stdout.strip()}"
                )
                all_passed &= is_active
        
        if deployed_count == 0:
            print(f"{Colors.YELLOW}BCM role monitor not deployed (optional component){Colors.END}")
        
        return all_passed
    
    def run_all_tests(self) -> bool:
        """Run all tests and return overall pass/fail"""
        print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}DCGM Exporter Deployment Test Suite{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
        
        if not self.dgx_nodes:
            print(f"\n{Colors.RED}Error: No DGX nodes specified{Colors.END}")
            print("Use --dgx-nodes or provide a config file with systems.dgx_nodes")
            return False
        
        print(f"\nTesting {len(self.dgx_nodes)} DGX node(s): {', '.join(self.dgx_nodes)}")
        print(f"DCGM Exporter port: {self.dcgm_port}")
        print(f"Job mapping directory: {self.job_map_dir}")
        print(f"Prometheus targets: {self.prometheus_targets_dir}")
        
        # Run all tests
        tests = [
            ("SSH Connectivity", self.test_ssh_connectivity),
            ("DCGM Service", self.test_dcgm_service),
            ("Metrics Endpoint", self.test_metrics_endpoint),
            ("GPU Detection", self.test_gpu_detection),
            ("Job Mapping Setup", self.test_job_mapping_directory),
            ("Prolog/Epilog Scripts", self.test_prolog_epilog_scripts),
            ("Prometheus Targets", self.test_prometheus_targets),
            ("BCM Role Monitor", self.test_bcm_role_monitor),
            ("Sample Job Test", self.test_with_sample_job),
        ]
        
        for test_name, test_func in tests:
            try:
                test_func()
            except Exception as e:
                print(f"\n{Colors.RED}Error in {test_name}: {e}{Colors.END}")
                self.add_result(test_name, False, f"Test crashed: {e}")
        
        # Print summary
        self.print_summary()
        
        # Return overall pass/fail
        return all(r.passed for r in self.results)
    
    def print_summary(self):
        """Print test summary"""
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)
        
        print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
        print(f"{Colors.BOLD}Test Summary{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
        
        print(f"\nTotal tests: {total}")
        print(f"{Colors.GREEN}Passed: {passed}{Colors.END}")
        if failed > 0:
            print(f"{Colors.RED}Failed: {failed}{Colors.END}")
        
        if failed > 0:
            print(f"\n{Colors.RED}{Colors.BOLD}Failed Tests:{Colors.END}")
            for result in self.results:
                if not result.passed:
                    print(f"  • {result.name}: {result.message}")
        
        print(f"\n{Colors.BOLD}Overall Result: ", end="")
        if failed == 0:
            print(f"{Colors.GREEN}✓ ALL TESTS PASSED{Colors.END}")
        else:
            print(f"{Colors.RED}✗ SOME TESTS FAILED{Colors.END}")
        
        print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}\n")
    
    def export_results(self, output_file: str):
        """Export test results to JSON file"""
        results_data = {
            "timestamp": datetime.now().isoformat(),
            "dgx_nodes": self.dgx_nodes,
            "total_tests": len(self.results),
            "passed": sum(1 for r in self.results if r.passed),
            "failed": sum(1 for r in self.results if not r.passed),
            "results": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "message": r.message,
                    "details": r.details,
                    "timestamp": r.timestamp.isoformat()
                }
                for r in self.results
            ]
        }
        
        with open(output_file, "w") as f:
            json.dump(results_data, f, indent=2)
        
        print(f"Results exported to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Test DCGM Exporter deployment on BCM-managed SuperPOD"
    )
    parser.add_argument(
        "--config",
        help="Path to configuration JSON file"
    )
    parser.add_argument(
        "--dgx-nodes",
        nargs="+",
        help="List of DGX nodes to test"
    )
    parser.add_argument(
        "--export",
        help="Export results to JSON file"
    )
    
    args = parser.parse_args()
    
    if not args.config and not args.dgx_nodes:
        parser.error("Must provide either --config or --dgx-nodes")
    
    tester = DCGMExporterTester(args.config, args.dgx_nodes)
    success = tester.run_all_tests()
    
    if args.export:
        tester.export_results(args.export)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

