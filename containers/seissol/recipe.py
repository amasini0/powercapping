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

################################################################################
# DEVEL STAGE                                                                  #
################################################################################

# Set base image
Stage0 += baseimage(
    image="docker.io/{}@{}".format(config["base_image"], config["digest_devel"]),
    _distro=config["base_os"],
    _arch=config["arch"],
    _as="devel",
)

# Install CMake
Stage0 += bb.cmake(eula=True, version="3.27.8")

# Install Python
python = bb.python(python2=False)
Stage0 += python

# Install LLVM
# Passing _trunk_version="0.1" to force correct toolchain installation from upstream
# repos, which otherwise fails due to incorrect package name specification
llvm = bb.llvm(version="18", upstream=True, toolset=True, _trunk_version="0.1")
Stage0 += llvm

# match config["arch"]:
#     case "aarch64":
#         llvm_cpu_target = "AARCH64"
#     case "x86_64":
#         llvm_cpu_target = "X86"
#     case _:
#         raise RuntimeError("Invalid CPU architecture")

# llvm = bb.generic_cmake(
#     repository="https://github.com/llvm/llvm-project.git",
#     branch="llvmorg-18.1.8",
#     prefix="/usr/local/llvm",
#     cmake_opts=[
#         "-DCMAKE_BUILD_TYPE=Release",
#         "-DLLVM_ENABLE_PROJECTS=clang,lld,polly",
#         "-DLLVM_ENABLE_RUNTIMES=compiler-rt,openmp",
#         "-DLLVM_TARGETS_TO_BUILD={};NVPTX".format(llvm_cpu_target),
#         "-DLLVM_BUILD_LLVM_DYLIB=ON",
#         "-DLLVM_ENABLE_ASSERTIONS=OFF",
#         "-DLLVM_ENABLE_BINDINGS=OFF",
#         "-DLLVM_ENABLE_DUMP=OFF",
#         "-DLLVM_ENABLE_OCAMLDOC=OFF",
#         "-DLLVM_INCLUDE_BENCHMARKS=OFF",
#         "-DLLVM_INCLUDE_EXAMPLES=OFF",
#         "-DLLVM_INCLUDE_TESTS=OFF",
#         "-DLLVM_TEMPORARILY_ALLOW_OLD_TOOLCHAIN=OFF",
#         "-DOPENMP_ENABLE_LIBOMPTARGET=OFF",
#     ]
# )

# Stage0 += llvm
# Stage0 += environment(
#     variables={
#         "PATH": "/usr/local/llvm/bin:$PATH",
#         "CPATH": "/usr/local/llvm/include:$CPATH",
#         "LIBRARY_PATH": "/usr/local/llvm/lib:$LIBRARY_PATH",
#         "LD_LIBRARY_PATH": "/usr/local/llvm/lib:$LD_LIBRARY_PATH",
#         "LLVM_HOME": "/usr/local/llvm",
#         "LLVM_INC": "/usr/local/llvm/include",
#         "LLVM_INCLUDE": "/usr/local/llvm/include",
#         "LLVM_LIB": "/usr/local/llvm/lib",
#         "CMAKE_PREFIX_PATH": "/usr/local/llvm",
#     },
#     _export=True
# )

# Install Boost
boost = bb.boost(
    version="1.86.0",
    baseurl="https://archives.boost.io/release/1.86.0/source",  # Download from boost official archives
    prefix="/usr/local/boost",
    bootstrap_opts=[
        "--with-libraries=fiber,context,atomic,filesystem",
        "--show-libraries",
    ],
    b2_opts=[
        "variant=release",
        "threading=multi",
        "link=shared",
        "visibility=hidden",
        'cxxflags="-std=c++17"',
        "address-model=64",
        "architecture={}".format(config["arch"].split("_")[0]),
        "--with-fiber",
        "--with-context",
        "--with-atomic",
        "--with-filesystem",
        "--prefix=/usr/local/boost",
    ],
)
Stage0 += boost

# Install Git
Stage0 += bb.packages(ospackages=["git"])

# Install AdaptiveCpp
adaptive_cpp_prefix = "/usr/local/acpp"
adaptive_cpp = bb.generic_cmake(
    repository="https://github.com/AdaptiveCpp/AdaptiveCpp.git",
    branch="v24.06.0",
    prefix=adaptive_cpp_prefix,
    cmake_opts=[
        "-DCMAKE_BUILD_TYPE=Release",
        "-DACPP_COMPILER_FEATURE_PROFILE=minimal",
        "-DDEFAULT_TARGETS=cuda:sm_{}".format(config["cuda_arch"]),
    ],
)

Stage0 += adaptive_cpp
Stage0 += environment(
    variables={
        "PATH": "{}/bin:$PATH".format(adaptive_cpp_prefix),
        "CPATH": "{}/include:$CPATH".format(adaptive_cpp_prefix),
        "LIBRARY_PATH": "{}/lib:$LIBRARY_PATH".format(adaptive_cpp_prefix),
        "LD_LIBRARY_PATH": "{}/lib:$LD_LIBRARY_PATH".format(adaptive_cpp_prefix),
        "ACPP_HOME": adaptive_cpp_prefix,
        "ACPP_INC": "{}/include".format(adaptive_cpp_prefix),
        "ACPP_INCLUDE": "{}/include".format(adaptive_cpp_prefix),
        "ACPP_LIB": "{}/lib".format(adaptive_cpp_prefix),
        "CMAKE_PREFIX_PATH": adaptive_cpp_prefix,
    }
)

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

# Install parallel HDF5
hdf5_prefix = "/usr/local/hdf5"
hdf5 = bb.hdf5(
    toolchain=ompi.toolchain,
    prefix=hdf5_prefix,
    version="1.14.5",
    configure_opts=[],  # remove --enable-fortran and --enable-cxx
    enable_parallel=True,
    disable_shared=True,
    with_zlib=True,
)
Stage0 += hdf5


# Install Eigen

# Install easi

# Install libxsmm / PSpaMM

# Install ParMETIS

# Install NetCDF

# Install ASAGI

# Install gemmforge

# Install chainforge


################################################################################
# RUNTIME STAGE                                                                #
################################################################################

# Stage1 += baseimage(
#     image="{}@{}".format(config["base_image"], config["digest_runtime"]),
#     _distro=config["base_os"],
#     _arch=config["arch"]
# )
# Stage1 += python.runtime()
# Stage1 += llvm.runtime()
# Stage1 += boost.runtime()
# Stage1 += adaptive_cpp.runtime()
