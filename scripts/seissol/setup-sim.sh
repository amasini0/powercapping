#!/bin/bash

function usage {
        echo ""
        echo "Usage: setup-sim.sh [OPTS] <folder-name>"
        echo ""
        echo "    --nodes=4|8  number of nodes to use for the simulation"
        echo ""
}

if [[ ! $# -eq 1 ]] && [[ ! $# -eq 2 ]]
then
        usage
        exit 1
fi

# Get number of nodes to use
num_nodes=4
if [[ $# -eq 2 ]]
then
        if [[ "$1" =~ --nodes=[4,8] ]]
        then
                num_nodes=$(echo $1 | cut -d '=' -f 2)
        else
                echo "Invalid option: $1"
                usage
                exit 1
        fi
fi

# Set simulation time for around 1h of walltime
sim_time="40.0"
if [[ $num_nodes -eq 8 ]]
then
        sim_time="60.0"
fi

# Move to where this script is located
cd $(realpath $(dirname $0))

# Get input and simulation directories
INPUT_DIR=$(realpath ./input)

if [[ "$#" -eq 2 ]]
then
        SIM_DIR=$(realpath $2)
else
        SIM_DIR=$(realpath $1)
fi

# Create sim directory
mkdir -p $SIM_DIR

# Create soft link to container
ln -s $INPUT_DIR/seissol.sif $SIM_DIR/seissol.sif

# Create soft link to input files
for file in $(find $INPUT_DIR/Turkey -type f -name *.yaml)
do
        ln -s $file $SIM_DIR/$(basename $file)
done

# Create soft links to mesh files
mkdir -p $SIM_DIR/mesh
for file in $(find $INPUT_DIR/Turkey/mesh -type f)
do
        ln -s $file $SIM_DIR/mesh/$(basename $file)
done

# Copy parameter file and slurm file
cp $INPUT_DIR/Turkey/parameters.par $SIM_DIR/parameters.par
sed -i "s/EndTime = 150.0/EndTime = $sim_time/g" $SIM_DIR/parameters.par

cp $INPUT_DIR/submit.slurm $SIM_DIR/submit.slurm
sed -i "s/#SBATCH --nodes=2/#SBATCH --nodes=$num_nodes/g" $SIM_DIR/submit.slurm
