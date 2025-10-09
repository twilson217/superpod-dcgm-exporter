#!/bin/bash
#
# DCGM Job Mapping Prolog Script
# 
# This script runs at job start and creates GPU-to-Job mapping files
# for DCGM exporter to add job labels to GPU metrics.
#
# The mapping files follow DCGM's expected format:
# - Directory: /run/dcgm-job-map/ (or configured path)
# - One file per GPU, named by GPU index (0, 1, 2, etc.)
# - Each file contains one or more job IDs (one per line)
#
# This enables Slurm job information to appear in DCGM metrics labels.

set -e

# Configuration
DCGM_JOB_MAP_DIR="${DCGM_JOB_MAP_DIR:-/run/dcgm-job-map}"
LOG_FILE="/var/log/slurm/dcgm-prolog.log"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [PROLOG] $1" >> "$LOG_FILE"
}

log_message "Starting DCGM job mapping for Job $SLURM_JOB_ID"

# Create mapping directory if it doesn't exist
if [ ! -d "$DCGM_JOB_MAP_DIR" ]; then
    mkdir -p "$DCGM_JOB_MAP_DIR"
    chmod 755 "$DCGM_JOB_MAP_DIR"
    log_message "Created DCGM job mapping directory: $DCGM_JOB_MAP_DIR"
fi

# Get GPU devices allocated to this job
# CUDA_VISIBLE_DEVICES or SLURM_JOB_GPUS or SLURM_STEP_GPUS
GPU_IDS=""

if [ -n "$CUDA_VISIBLE_DEVICES" ]; then
    GPU_IDS="$CUDA_VISIBLE_DEVICES"
    log_message "Using CUDA_VISIBLE_DEVICES: $GPU_IDS"
elif [ -n "$SLURM_JOB_GPUS" ]; then
    # SLURM_JOB_GPUS might be in format like "0,1" or "0-1"
    GPU_IDS="$SLURM_JOB_GPUS"
    log_message "Using SLURM_JOB_GPUS: $GPU_IDS"
elif [ -n "$SLURM_STEP_GPUS" ]; then
    GPU_IDS="$SLURM_STEP_GPUS"
    log_message "Using SLURM_STEP_GPUS: $GPU_IDS"
else
    log_message "No GPU allocation found for job $SLURM_JOB_ID, skipping DCGM mapping"
    exit 0
fi

# Parse GPU IDs and create mapping files
# Handle comma-separated list and ranges
IFS=',' read -ra GPU_ARRAY <<< "$GPU_IDS"
for gpu_spec in "${GPU_ARRAY[@]}"; do
    # Check if it's a range (e.g., "0-3")
    if [[ $gpu_spec == *"-"* ]]; then
        IFS='-' read -r start end <<< "$gpu_spec"
        for ((i=start; i<=end; i++)); do
            GPU_FILE="$DCGM_JOB_MAP_DIR/$i"
            echo "$SLURM_JOB_ID" >> "$GPU_FILE"
            log_message "Mapped GPU $i to job $SLURM_JOB_ID"
        done
    else
        # Single GPU
        GPU_FILE="$DCGM_JOB_MAP_DIR/$gpu_spec"
        echo "$SLURM_JOB_ID" >> "$GPU_FILE"
        log_message "Mapped GPU $gpu_spec to job $SLURM_JOB_ID"
    fi
done

log_message "Completed DCGM job mapping for Job $SLURM_JOB_ID"

exit 0

