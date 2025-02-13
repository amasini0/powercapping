#!/usr/bin/env python

import hpccm
import hpccm.building_blocks as bb
from hpccm.primitives import baseimage

CLUSTER_CONFIGS = {
    "leonardo": {
        "arch": "x86_64",
        "march": "skylake",
        "cuda_arch": "80",
        "base_image": "nvidia/cuda",
        "base_os": "ubuntu22",
        "cuda_version": "12.6",
        "tag_devel": "12.6.3-devel-ubuntu22.04",
        "digest_devel": "sha256:1608a19a5d6f013d36abfb9ad50a42b4c0ef86f4ab48e351c6899f0280b946c1",
        "tag_runtime": "12.6.3-runtime-ubuntu22.04",
        "digest_runtime": "sha256:4cf7f8137bdeeb099b1f2de126e505aa1f01b6e4471d13faf93727a9bf83d539",
        "network_stack": {
            "mlnx_ofed": "5.8-2.0.3.0",
            "knem": True,  # use default version 1.1.4
            "xpmem": True,  # use default version
            "ucx": "1.13.1",
            "pmix": "3.1.5",
            "ompi": "4.1.6",
        },
    },
    "thea": {
        "arch": "aarch64",
        "march": "neoverse_v2",
        "cuda_arch": "90",
        "base_image": "nvidia/cuda",
        "base_os": "ubuntu22",
        "cuda_version": "12.6",
        "tag_devel": "12.6.3-devel-ubuntu22.04",
        "digest_devel": "sha256:12cf7fda869f87f821113f010ee64b3a230a3fed2a56fb6d3c93fb8a82472816",
        "tag_runtime": "12.6.3-runtime-ubuntu22.04",
        "digest_runtime": "sha256:77e5fa9d1849bdba5a340be90d8ca30fb13d8f62fb433b1fa9d2903bb7a68498",
        "network_stack": {
            "mlnx_ofed": "24.04-0.7.0.0",
            "knem": True,  # use default version 1.1.4
            "xpmem": True,  # use default version
            "ucx": "1.18.0",
            "pmix": "internal",
            "ompi": "5.0.3",
        },
    },
}


# Get correct config
machine = USERARG.get("machine", "thea")

if machine is None:
    raise RuntimeError("Please specify a machine with --userarg machine=<name>")

if machine not in CLUSTER_CONFIGS.keys():
    raise RuntimeError("invalid machine name: {}".format(machine))

config = CLUSTER_CONFIGS[machine]

# Global HPCCM config for package installations
hpccm.config.set_cpu_target(config["march"])
hpccm.config.set_linux_distro(config["base_os"])

# Set base image
Stage0 += baseimage(
    image="docker.io/{}@{}".format(config["base_image"], config["digest_devel"]),
    _distro=config["base_os"],
    _arch=config["arch"],
    _as="devel",
)

# Install Python
python = bb.python(python2=False)
Stage0 += python

# Install network stack components and utilities
netconfig = config["network_stack"]

## Install Mellanox OFED userspace libraries
mlnx_ofed = bb.mlnx_ofed(version=netconfig["mlnx_ofed"])
Stage0 += mlnx_ofed

## Install KNEM headers
if netconfig["knem"]:
    knem_prefix = "/usr/local/knem"
    knem = bb.knem(prefix=knem_prefix)
    Stage0 += knem
else:
    knem_prefix = False

## Install XPMEM userspace library
if netconfig["xpmem"]:
    xpmem_prefix = "/usr/local/xpmem"
    xpmem = bb.xpmem(prefix=xpmem_prefix)
    Stage0 += xpmem
else:
    xpmem_prefix = False

## Install UCX
ucx_prefix = "/usr/local/ucx"
ucx = bb.ucx(
    prefix=ucx_prefix,
    repository="https://github.com/openucx/ucx.git",
    branch="v{}".format(netconfig["ucx"]),
    cuda=True,
    ofed=True,
    knem=knem_prefix,
    xpmem=xpmem_prefix,
)
Stage0 += ucx

## Install PMIx
match netconfig["pmix"]:
    case "internal":
        pmix_prefix = "internal"
    case version:
        pmix_prefix = "/usr/local/pmix"
        pmix = bb.pmix(prefix=pmix_prefix, version=netconfig["pmix"])
        Stage0 += pmix

## Install OpenMPI
ompi = bb.openmpi(
    prefix="/usr/local/openmpi",
    version=netconfig["ompi"],
    ucx=ucx_prefix,
    pmix=pmix_prefix,
)
Stage0 += ompi
