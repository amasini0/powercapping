#!/usr/bin/env python

import hpccm
import hpccm.building_blocks as bb
from hpccm.primitives import baseimage, environment

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
