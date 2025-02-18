#!/bin/bash

# Script that splits a singularity definition files in steps.
# Takes as input the .def file to be split.
# Produces a set of .def files corresponding to each step.

if [[ ! $# -eq 1 ]]
then
    echo "Usage: $0 <my-container.def>"
    exit 1
fi

# The starting point of each step must be indicated in the
# original .def file through comments like the following:
#
# step <N>: start
#
# where N is a consecutive number representing the step.

# .def files for each step will be placed in a "steps" folder 
# in the same directory of this script and "seissol_thea.def"
STEPS_FOLDER=$(realpath "$(dirname $1)/steps")
mkdir -p $STEPS_FOLDER

# Get lines corresponding to each step's starting point
RECIPE_FILE=$(realpath "$1")
start_lines=($(grep -n "step[0-9]: start" $RECIPE_FILE | cut -d ':' -f 1))

for i in $(seq 1 $((${#start_lines[@]})))
do
    step_file=$STEPS_FOLDER/step$i.def
    step_start=${start_lines[$((i-1))]}
    step_end=${start_lines[$i]}

    if [[ $i -eq 1 ]]
    then 
        # Copy bootstrap image from original file
        # and remove "Stage: devel" command
        cat $RECIPE_FILE \
        | head -n +$((step_start-2)) \
        | sed "/Stage: devel/d" \
        > $step_file
    else
        # Bootstrap from previous step image"
        echo "BootStrap: localimage" > $step_file
        echo "From: step$((i-1)).sif" >> $step_file
        
        # Add "Stage: devel" to runtime image def file
        if [[ $i -eq ${#start_lines[@]} ]]
        then
            echo "Stage: devel" >> $step_file
        fi
    fi

    # Isolate section relative to the current step
    cat $RECIPE_FILE \
    | head -n "$((step_end-1))" \
    | tail -n "+$((step_start+1))" \
    >> $step_file
done