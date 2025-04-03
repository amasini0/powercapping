#!/bin/bash

#SBATCH --job-name=seissol
#SBATCH --partition=gh
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=72
#SBATCH --time=01:30:00
#SBATCH --output=./%j.out

# Enter submission directory
cd $SLURM_SUBMIT_DIR

# Binding to cores explicitly for performance
COMPUTE_CORES=40
export APPTAINERENV_OMP_NUM_THREADS=$COMPUTE_CORES
export APPTAINERENV_OMP_PLACES="cores($COMPUTE_CORES)"
export APPTAINERENV_OMP_PROC_BIND="close"

# Cores for I/O and MPI background threads
export APPTAINERENV_SEISSOL_FREE_CPUS_MASK="$COMPUTE_CORES-71"

# Recommended I/O setup
export APPTAINERENV_XDMFWRITER_ALIGNMENT=8388608
export APPTAINERENV_XDMFWRITER_BLOCK_SIZE=8388608
export APPTAINERENV_ASYNC_MODE=THREAD
export APPTAINERENV_ASYNC_BUFFER_ALIGNMENT=8388608

# Available memory on device
export APPTAINERENV_DEVICE_STACK_MEM_SIZE=6

# Prevent known MPI warnings and errors
export APPTAINERENV_PMIX_MCA_psec=^munge

# Set soft host stack limit
ulimit -Ss 2097152

# Define absolute path to input directory
INPUT_DIR=$(realpath $SLURM_SUBMIT_DIR/../input)

# Launch containerized SeisSol
bind_mounts="--bind $INPUT_DIR:$INPUT_DIR"
seissol_bin="SeisSol_Release_ssm_90_cuda_6_elastic"
srun --mpi=pmix apptainer exec --nv ${bind_mounts} seissol.sif ${seissol_bin} parameters.par
