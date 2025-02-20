#!/usr/bin/env python

import hpccm
import hpccm.building_blocks as bb
from hpccm.primitives import baseimage, comment
import json
from pathlib import Path


# Get correct config
config_file = Path(USERARG.get("config-file", "../../configs/thea.json"))  # noqa: F821
if not config_file.exists():
    raise RuntimeError(
        "cannot access {}: No such file or directory".format(config_file)
    )

with open(config_file, "r") as json_file:
    config = json.load(json_file)

# Set base image
Stage0 += baseimage(  # noqa: F821
    image="docker.io/{}@{}".format(config["base_image"], config["digest_devel"]),
    _distro=config["base_os"],
    _arch=config["arch"],
    _as="devel",
)

# Microarchitecture specification
hpccm.config.set_cpu_target(config["march"])


################################################################################
Stage0 += comment("step1: start")
Stage0 += comment("Install GCC 12, Python and build tools over base image")

# Install Python with virtual environments support
python = bb.python(python2=False)
Stage0 += python
Stage0 += bb.packages(
    ospackages=[
        "python3-pip",
        "python3-venv",
        "python3-wheel",
        "python3-setuptools",
    ],
)

# Install CMake
Stage0 += bb.cmake(eula=True, version="3.27.8")

# Install Git and pkgconf
Stage0 += comment("Git, Pkgconf")
Stage0 += bb.packages(ospackages=["git", "pkgconf"])


################################################################################
Stage0 += comment("step2: start")
Stage0 += comment("Install network stack packages and OpenMPI")

# Get network stack configuration
netconfig = config["network_stack"]

# Install Mellanox OFED userspace libraries
mlnx_ofed = bb.mlnx_ofed(version=netconfig["mlnx_ofed"])
Stage0 += mlnx_ofed

# Install KNEM headers
if netconfig["knem"]:
    knem_prefix = "/usr/local/knem"
    knem = bb.knem(prefix=knem_prefix)
    Stage0 += knem
else:
    knem_prefix = False

# Install XPMEM userspace library
if netconfig["xpmem"]:
    xpmem_prefix = "/usr/local/xpmem"
    xpmem = bb.xpmem(prefix=xpmem_prefix)
    Stage0 += xpmem
else:
    xpmem_prefix = False

# Install gdrcopy userspace library
if netconfig["gdrcopy"]:
    gdrcopy_prefix = "/usr/local/gdrcopy"
    gdrcopy = bb.gdrcopy(prefix=gdrcopy_prefix)
    Stage0 += gdrcopy
else:
    gdrcopy_prefix = False

# Install UCX
ucx_prefix = "/usr/local/ucx"
ucx = bb.ucx(
    prefix=ucx_prefix,
    repository="https://github.com/openucx/ucx.git",
    branch="v{}".format(netconfig["ucx"]),
    cuda=True,
    ofed=True,
    knem=knem_prefix,
    xpmem=xpmem_prefix,
    gdrcopy=gdrcopy_prefix,
    enable_mt=True,
)
Stage0 += ucx

# Install PMIx
match netconfig["pmix"]:
    case "internal":
        pmix_prefix = "internal"
    case version:
        pmix_prefix = "/usr/local/pmix"
        pmix = bb.pmix(prefix=pmix_prefix, version=netconfig["pmix"])
        Stage0 += pmix

# Install OpenMPI
ompi = bb.openmpi(
    prefix="/usr/local/openmpi",
    version=netconfig["ompi"],
    ucx=ucx_prefix,
    pmix=pmix_prefix,
)
Stage0 += ompi


################################################################################
Stage0 += comment("step3: start")
Stage0 += comment("Compile and install OpenMPI benchmarks")

# Compile bundled source code
benchmarks_prefix = "/usr/local/benchmarks"
benchmarks_env = {
    "PATH": "{}/bin:$PATH".format(benchmarks_prefix),
    "LIBRARY_PATH": "{}/lib:$LIBRARY_PATH".format(benchmarks_prefix),
    "LD_LIBRARY_PATH": "{}/lib:$LD_LIBRARY_PATH".format(benchmarks_prefix),
}
benchmarks = bb.generic_cmake(
    repository="https://github.com/amasini0/mpi-benchmarks.git",
    prefix=benchmarks_prefix,
    cmake_opts=[
        "-DCMAKE_BUILD_TYPE=Release",
    ],
    devel_environment=benchmarks_env,
    runtime_environment=benchmarks_env,
)
Stage0 += benchmarks


################################################################################
Stage0 += comment("step4: start")
Stage0 += comment("Generate runtime image")

Stage1 += baseimage(  # noqa: F821
    image="docker.io/{}@{}".format(config["base_image"], config["digest_runtime"]),
    _distro=config["base_os"],
    _arch=config["arch"],
)

# Copy all default runtimes
Stage1 += Stage0.runtime()

# Manually add missing libraries
Stage1 += comment("Libraries missing from CUDA runtime image")
Stage1 += bb.packages(
    ospackages=[
        "libnuma1",
    ]
)
