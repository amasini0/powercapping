#!/bin/bash

# Script that splits "seissol_thea.def" in 8 partial steps. 
# The following .def files will be generated:
# step1.def: python,compiler, build tools;
# step2.def: ofed, ucx, openmpi;
# step3.def: sycl (adaptivecpp);
# step4.def: io and math libraries;
# step5.def: data acquisition tools;
# step6.def: code generation tools;
# step7.def: seissol build;
# step8.def: runtime image generation.

# .def files will be placed in a "steps" folder in the 
# same directory of this script and "seissol_thea.def"
STEPS_FOLDER=$(realpath "$(dirname $0)/steps")
mkdir -p $STEPS_FOLDER


# Get lines corresponding to each step's starting point
RECIPE_FILE=$(realpath "$(dirname $0)/seissol_thea.def")
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