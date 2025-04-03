# Running the SeisSol container
In order to run the SeisSol container using the provided input files, the following steps must be followed:
1. Build the SeisSol container
2. Create a dedicated workspace directory where all data relative to the simulations (inputs and results for run) will be placed, e.g. a `seissol-workspace` folder.
3. Copy the contents of this folder (`powercapping/inputs/seissol`) inside the previously created folder.
4. Move to `seissol-workspace/inputs` and extract the `Turkey.zip` file. This should create a `seissol-workspace/input/Turkey` directory.
5. Copy the seissol container image inside the `input` folder and name it `seissol.sif` (i.e. copy it as`seissol-workspace/input/seissol.sif`).
6. Adjust the `seissol-workspace/input/submit.slurm` file changing the partition name, adding an account name if required (e.g. on Leonardo), and maybe adjusting the walltime (the value is tailored for Thea with 1 GH200 per node).
7. Move to `seissol-workspace` and run the `setup-sim.sh` script to generate a folder for the simulation. This takes the name of the folder as argument, and optionally a `--nodes=8` option to create a simulation for 8 nodes. By default it creates a simulation for 4 nodes.

    For example, running
    ```shell
    setup-sim-sh --nodes=8 pcap-default-8n` 
    ```
    will create a folder named `pcap-default-8n` with a parameter file and slurm script set up for an 8 node simulation lasting approximately 1h (measured on Thea).

8. To run the simulation just enter the folder and run `sbatch submit.slurm` (must be done from inside the simulation folder).