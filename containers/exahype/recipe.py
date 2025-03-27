#!/usr/bin/env python

import hpccm
import hpccm.building_blocks as bb
from hpccm.primitives import baseimage, comment, copy, environment, shell
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
Stage0 += comment("Install build tools over base image")

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
Stage0 += bb.cmake(eula=True, version="3.31.4")

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
Stage0 += comment("Enable OpenMP offload and SYCL support")

# Install LLVM with NVPTX support (2-stage build)
match config["arch"]:
    case "x86_64":
        llvm_host_target = "X86"
    case "aarch64":
        llvm_host_target = "AArch64"

llvm_prefix = "/usr/local/llvm"
llvm_env = {
    "PATH": "{}/bin:$PATH".format(llvm_prefix),
    "CPATH": "{}/include:$CPATH".format(llvm_prefix),
    "LIBRARY_PATH": "{}/lib:$LIBRARY_PATH".format(llvm_prefix),
    "LD_LIBRARY_PATH": "{}/lib:$LD_LIBRARY_PATH".format(llvm_prefix),
    "CMAKE_PREFIX_PATH": "{}/lib/cmake:$CMAKE_PREFIX_PATH".format(llvm_prefix),
}
llvm_stage_1 = [
    "cmake",
    "-S /var/tmp/llvm-project/llvm",
    "-B /var/tmp/llvm-project/stage1-build",
    "-DCMAKE_BUILD_TYPE=Release",
    '-DLLVM_ENABLE_PROJECTS="clang;lld;polly"',
    '-DLLVM_ENABLE_RUNTIMES="compiler-rt;openmp"',
    '-DLLVM_TARGETS_TO_BUILD="{};NVPTX"'.format(llvm_host_target),
    "-DLLVM_BUILD_LLVM_DYLIB=ON",
    "-DLLVM_ENABLE_ASSERTIONS=OFF",
    "-DLLVM_ENABLE_OCAMLDOC=OFF",
    "-DLLVM_ENABLE_BINDINGS=OFF",
    "-DLLVM_ENABLE_DUMP=OFF",
    "-DLLVM_INCLUDE_BENCHMARKS=OFF",
    "-DLLVM_INCLUDE_EXAMPLES=OFF",
    "-DLLVM_INCLUDE_TESTS=OFF",
    "-DLLVM_TEMPORARILY_ALLOW_OLD_TOOLCHAIN=OFF",
    "-DLIBOMPTARGET_DEVICE_ARCHITECTURES=sm_90",
]
llvm_stage_2 = [
    "cmake",
    "-S /var/tmp/llvm-project/llvm",
    "-B /var/tmp/llvm-project/stage2-build",
    "-DCMAKE_C_COMPILER=/var/tmp/llvm-project/stage1-build/bin/clang",
    "-DCMAKE_CXX_COMPILER=/var/tmp/llvm-project/stage1-build/bin/clang++",
    "-DCMAKE_INSTALL_PREFIX={}".format(llvm_prefix),
    "-DCMAKE_BUILD_TYPE=Release",
    '-DLLVM_ENABLE_PROJECTS="clang;lld;polly"',
    '-DLLVM_ENABLE_RUNTIMES="compiler-rt;openmp"',
    '-DLLVM_TARGETS_TO_BUILD="{};NVPTX"'.format(llvm_host_target),
    "-DLLVM_BUILD_LLVM_DYLIB=ON",
    "-DLLVM_ENABLE_ASSERTIONS=OFF",
    "-DLLVM_ENABLE_OCAMLDOC=OFF",
    "-DLLVM_ENABLE_BINDINGS=OFF",
    "-DLLVM_ENABLE_DUMP=OFF",
    "-DLLVM_INCLUDE_BENCHMARKS=OFF",
    "-DLLVM_INCLUDE_EXAMPLES=OFF",
    "-DLLVM_INCLUDE_TESTS=OFF",
    "-DLLVM_TEMPORARILY_ALLOW_OLD_TOOLCHAIN=OFF",
    "-DLIBOMPTARGET_DEVICE_ARCHITECTURES=sm_90",
]
llvm = bb.generic_build(
    repository="https://github.com/llvm/llvm-project.git",
    branch="llvmorg-18.1.8",
    prefix=llvm_prefix,
    build=[
        "echo 'Start stage 1 build ...'",
        " ".join(llvm_stage_1),
        "cmake --build /var/tmp/llvm-project/stage1-build --parallel",
        "echo 'Start stage 2 build ...'",
        " ".join(llvm_stage_2),
        "cmake --build /var/tmp/llvm-project/stage2-build --parallel --target install",
    ],
    devel_environment=llvm_env,
    runtime_environment=llvm_env,
)
Stage0 += llvm

# Install Boost
match config["arch"]:
    case "x86_64":
        boost_arch = "x86"
    case "aarch64":
        boost_arch = "arm"
    case _:
        raise ValueError(
            "Invalid or unsupported architecture: {}".format(config["arch"])
        )

boost_prefix = "/usr/local/boost"
boost_env = {
    "CPATH": "{}/include:$CPATH".format(boost_prefix),
    "LIBRARY_PATH": "{}/lib:$LIBRARY_PATH".format(boost_prefix),
    "LD_LIBRARY_PATH": "{}/lib:$LD_LIBRARY_PATH".format(boost_prefix),
    "CMAKE_PREFIX_PATH": "{}/lib/cmake:$CMAKE_PREFIX_PATH".format(boost_prefix),
}
boost = bb.boost(
    version="1.86.0",
    baseurl="https://archives.boost.io/release/1.86.0/source",  # force installation from official archive
    prefix=boost_prefix,
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
        "architecture={}".format(boost_arch),
        "--with-fiber",
        "--with-context",
        "--with-atomic",
        "--with-filesystem",
        "--prefix=/usr/local/boost",
    ],
    environment=False,
)
Stage0 += boost
Stage0 += environment(
    variables=boost_env,
)

# Install AdaptiveCpp
adaptive_cpp_prefix = "/usr/local/acpp"
adaptive_cpp_env = {
    "PATH": "{}/bin:$PATH".format(adaptive_cpp_prefix),
    "CPATH": "{}/include:$CPATH".format(adaptive_cpp_prefix),
    "LIBRARY_PATH": "{}/lib:$LIBRARY_PATH".format(adaptive_cpp_prefix),
    "LD_LIBRARY_PATH": "{}/lib:$LD_LIBRARY_PATH".format(adaptive_cpp_prefix),
    "CMAKE_PREFIX_PATH": "{}/lib/cmake:$CMAKE_PREFIX_PATH".format(adaptive_cpp_prefix),
}
adaptive_cpp = bb.generic_cmake(
    repository="https://github.com/AdaptiveCpp/AdaptiveCpp.git",
    branch="v24.06.0",
    prefix=adaptive_cpp_prefix,
    cmake_opts=[
        "-DCMAKE_BUILD_TYPE=Release",
        "-DACPP_COMPILER_FEATURE_PROFILE=full",
    ],
    devel_environment=adaptive_cpp_env,
    runtime_environment=adaptive_cpp_env,
)
Stage0 += adaptive_cpp


################################################################################
Stage0 += comment("step4: start")
Stage0 += comment("Install optional dependencies")


# Install parallel HDF5
def hdf5_download_latest(self):
    """Construct the series of shell commands, i.e., fill in
    self.__commands"""
    # The download URL has the format contains vMAJOR.MINOR in the
    # path and the tarball contains MAJOR.MINOR.REVISION, so pull
    # apart the full version to get the MAJOR and MINOR components.
    import re

    match = re.match(r"(?P<major>\d+)\.(?P<minor>\d+)", self._hdf5__version)
    major_minor = "v{0}_{1}".format(
        match.groupdict()["major"], match.groupdict()["minor"]
    )
    tarball = "hdf5-{}.tar.gz".format(self._hdf5__version)
    self._hdf5__url = "{0}/{1}/v{2}/downloads/{3}".format(
        self._hdf5__baseurl, major_minor, self._hdf5__version.replace(".", "_"), tarball
    )


## Monkey patch building block to get latest version
setattr(bb.hdf5, "_hdf5__download", hdf5_download_latest)

hdf5_prefix = "/usr/local/hdf5"
hdf5_toolchain = ompi.toolchain.__copy__()
hdf5_toolchain.CFLAGS = "-fPIC"
hdf5 = bb.hdf5(
    baseurl="https://support.hdfgroup.org/releases/hdf5",
    version="1.14.5",  # tested only with 1.14.5
    toolchain=hdf5_toolchain,
    prefix=hdf5_prefix,
    configure_opts=[],  # left empty to remove --enable-fortran and --enable-cxx
    enable_parallel=True,
    disable_shared=True,
    with_zlib=True,
)
Stage0 += hdf5


# Install NetCDF
def netcdf_download_latest(self):
    """Set download source based on user parameters"""
    pkgname = "netcdf-c"
    tarball = "{0}-{1}.tar.gz".format(pkgname, self._netcdf__version)
    self._netcdf__directory_c = "{0}-{1}".format(pkgname, self._netcdf__version)
    self._netcdf__baseurl_c = "https://downloads.unidata.ucar.edu/netcdf-c/{}".format(
        self._netcdf__version
    )
    self._netcdf__url_c = "{0}/{1}".format(self._netcdf__baseurl_c, tarball)


## Monkey patch building block for download on thea
setattr(bb.netcdf, "_netcdf__download", netcdf_download_latest)

netcdf_prefix = "/usr/local/netcdf"
netcdf_toolchain = hpccm.toolchain(
    CFLAGS="-fPIC",
    CC="{}/bin/h5pcc".format(hdf5_prefix),
)
netcdf = bb.netcdf(
    version="4.9.2",  # tested only with 4.9.2 (latest version as of 28/01/2025)
    toolchain=netcdf_toolchain,
    prefix=netcdf_prefix,
    cxx=False,
    fortran=False,
    disable_shared=True,
    disable_dap=True,
    disable_libxml2=True,
    disable_byterange=True,
)
Stage0 += netcdf
Stage0 += environment(
    variables={
        "PKG_CONFIG_PATH": "{}/lib/pkgconfig:$PKG_CONFIG_PATH".format(netcdf_prefix),
        "CMAKE_PREFIX_PATH": "{}:$CMAKE_PREFIX_PATH".format(netcdf_prefix),
    }
)


################################################################################
Stage0 += comment("step5: start")
Stage0 += comment("Install ExaHyPE")

# Install large files storage for pulling meshes from Git
Stage0 += bb.packages(
    ospackages=[
        "git-lfs",
    ],
)

# Install ExaHyPE with test simulation cases
## Define build commands for Peano with GPU support
peano_workspace = "/root"
peano_branch = "muc/exahype-enclave-tasking"
peano_build = [
    "cmake",
    "-S {}/Peano".format(peano_workspace),
    "-B {}/Peano/build".format(peano_workspace),
    "-DCMAKE_C_COMPILER={}/bin/clang".format(llvm_prefix),
    "-DCMAKE_CXX_COMPILER={}/bin/clang++".format(llvm_prefix),
    "-DCMAKE_CXX_STANDARD=17",  # required when using clang
    "-DCMAKE_BUILD_TYPE=Release",
    "-DENABLE_EXAHYPE=ON",
    "-DENABLE_LOADBALANCING=ON",
    "-DENABLE_BLOCKSTRUCTURED=ON",
    "-DUSE_CCACHE=OFF",
    "-DWITH_NETCDF=ON",
    "-DWITH_MPI=ON",
    "-DWITH_MULTITHREADING=omp",
    "-DWITH_GPU=sycl",
    "-DWITH_USM=ON",
    # "-DWITH_GPU_ARCH=sm_{}".format(config["cuda_arch"]), # Leave commented to use "generic" AdaptiveCpp target
]

## Define build commands for exahype applications
application_bindirs = []

### Elastic point explosion
exahype_elastic_pe_dir = (
    "{}/Peano/applications/exahype2/elastic/point-explosion".format(peano_workspace)
)
exahype_elastic_pe_build = [
    "cd {}".format(exahype_elastic_pe_dir),
    "sed -i 's/min_depth=6/min_depth=8/' point-explosion.py",
    "sed -i 's/number_of_snapshots = 20/number_of_snapshots = 0/' point-explosion.py",
    "python point-explosion.py --stateless",
]
application_bindirs.append(exahype_elastic_pe_dir)

### Euler point explosion
exahype_euler_pe_dir = "{}/Peano/applications/exahype2/euler/point-explosion".format(
    peano_workspace
)
exahype_euler_pe_build = [
    "cd {}".format(exahype_euler_pe_dir),
    "sed -i 's/min_depth=4/min_depth=7/' point-explosion.py",
    "sed -i 's/number_of_snapshots = 20/number_of_snapshots = 0/' point-explosion.py",
    "python point-explosion.py --stateless",
]
application_bindirs.append(exahype_euler_pe_dir)

## Setup required environment variables
exahype_env = {
    "PATH": "{}:$PATH".format(":".join(application_bindirs)),
    "LIBRARY_PATH": "{}/Peano/build/lib:$LIBRARY_PATH".format(peano_workspace),
    "LD_LIBRARY_PATH": "{}/Peano/build/lib$LD_LIBRARY_PATH".format(peano_workspace),
}

## Build peano and exahype applications
Stage0 += shell(
    commands=[
        "mkdir -p {0} && cd {0} && git clone --branch {1} --depth 1 https://gitlab.lrz.de/hpcsoftware/Peano.git Peano".format(
            peano_workspace,
            peano_branch,
        ),
        "sed -i '9,11 N;s/^\\n$/\\n#include <iomanip>\\n/' {}/Peano/src/exahype2/fd/BoundaryConditions.cpp".format(
            peano_workspace
        ),  # fix setprecision error
        " ".join(peano_build),
        "cmake --build {}/Peano/build --parallel".format(peano_workspace),
        "sed -i '8,10 D' {}/Peano/requirements.txt".format(
            peano_workspace
        ),  # remove vtk and co. from requirements.txt
        "python3 -m venv {0}/Peano/codegen && . {0}/Peano/codegen/bin/activate && pip install -e {0}/Peano".format(
            peano_workspace
        ),
        " && ".join(exahype_elastic_pe_build),
        " && ".join(exahype_euler_pe_build),
    ]
)


################################################################################
Stage0 += comment("step6: start")
Stage0 += comment("Generate runtime image")

Stage1 += baseimage(  # noqa: F821
    image="docker.io/{}@{}".format(config["base_image"], config["digest_runtime"]),
    _distro=config["base_os"],
    _arch=config["arch"],
)

# Copy all default runtimes
Stage1 += Stage0.runtime()

# Copy exahype folder
Stage1 += comment("Copy ExaHyPE build files and setup environment")
Stage1 += copy(
    _from="devel",
    files={
        "{0}/Peano".format(peano_workspace): "{0}/Peano".format(peano_workspace),
    },
)
Stage1 += environment(
    variables=exahype_env,
)

# Manually add missing libraries
Stage1 += comment("Libraries missing from CUDA runtime image")
Stage1 += bb.packages(
    ospackages=[
        "libnuma1",
    ]
)
