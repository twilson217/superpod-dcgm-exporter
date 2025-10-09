#!/bin/bash
#
# DCGM Job Mapping Epilog Script
#
# This script runs at job completion and removes the job ID from
# GPU-to-Job mapping files for DCGM exporter.
#
# This ensures that metrics no longer show labels for completed jobs.

set -e

# Configuration
DCGM_JOB_MAP_DIR="${DCGM_JOB_MAP_DIR:-/run/dcgm-job-map}"
LOG_FILE="/var/log/slurm/dcgm-epilog.log"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [EPILOG] $1" >> "$LOG_FILE"
}

log_message "Starting DCGM job cleanup for Job $SLURM_JOB_ID"

# Check if mapping directory exists
if [ ! -d "$DCGM_JOB_MAP_DIR" ]; then
    log_message "DCGM job mapping directory does not exist, nothing to clean"
    exit 0
fi

# Find all GPU mapping files that contain this job ID and remove the job ID
CLEANED=0
for gpu_file in "$DCGM_JOB_MAP_DIR"/*; do
    if [ -f "$gpu_file" ]; then
        # Check if this file contains our job ID
        if grep -q "^${SLURM_JOB_ID}$" "$gpu_file" 2>/dev/null; then
            # Remove the job ID from the file
            sed -i "/^${SLURM_JOB_ID}$/d" "$gpu_file"
            log_message "Removed job $SLURM_JOB_ID from $(basename "$gpu_file")"
            CLEANED=$((CLEANED + 1))
            
            # If file is now empty, remove it
            if [ ! -s "$gpu_file" ]; then
                rm -f "$gpu_file"
                log_message "Removed empty mapping file: $(basename "$gpu_file")"
            fi
        fi
    fi
done

if [ $CLEANED -eq 0 ]; then
    log_message "No DCGM mappings found for job $SLURM_JOB_ID"
else
    log_message "Cleaned DCGM mappings for job $SLURM_JOB_ID from $CLEANED GPU(s)"
fi

exit 0

