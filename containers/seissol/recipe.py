#!/usr/bin/env python

import hpccm
import hpccm.building_blocks as bb
from hpccm.primitives import baseimage, environment, shell
import hpccm.primitives

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

# Install build tools (CMake, Git, pkgconf)
Stage0 += bb.cmake(eula=True, version="3.27.8")
Stage0 += bb.packages(ospackages=["git", "pkgconf"])


# Install AdaptiveCPP for SYCL support
# Two dependencies required: LLVM, Boost

## Install LLVM
## Passing _trunk_version="0.1" to force correct toolchain installation from upstream
## repos, which otherwise fails due to incorrect package name specification
llvm = bb.llvm(version="18", upstream=True, toolset=True, _trunk_version="0.1")
Stage0 += llvm

## Install Boost
## Force installation from official archives (see baseurl)
boost = bb.boost(
    version="1.86.0",
    baseurl="https://archives.boost.io/release/1.86.0/source",
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

## Install AdaptiveCpp
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
        "-DACPP_COMPILER_FEATURE_PROFILE=minimal",
        "-DDEFAULT_TARGETS=cuda:sm_{}".format(config["cuda_arch"]),
    ],
    devel_environment=adaptive_cpp_env,
    runtime_environment=adaptive_cpp_env,
)
Stage0 += adaptive_cpp


# Install parallel HDF5
## Monkey patch building block to get latest version
def download_latest(self):
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


setattr(bb.hdf5, "_hdf5__download", download_latest)

## Install building block
hdf5_prefix = "/usr/local/hdf5"
hdf5_toolchain = ompi.toolchain
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
netcdf_prefix = "/usr/local/netcdf"
netcdf_toolchain = ompi.toolchain
netcdf_toolchain.CFLAGS = "-fPIC -I{}/include".format(hdf5_prefix)
netcdf_toolchain.LDFLAGS = "-L{}/lib".format(hdf5_prefix)
netcdf = bb.netcdf(
    version="4.9.2",
    toolchain=netcdf_toolchain,
    prefix=netcdf_prefix,
    cxx=False,
    fortran=False,
    disable_shared=True,
    disable_dap=True,
)
Stage0 += netcdf
Stage0 += environment(
    variables={
        "PKG_CONFIG_PATH": "{}/lib/pkgconfig:$PKG_CONFIG_PATH".format(netcdf_prefix),
        "CMAKE_PREFIX_PATH": "{}:$CMAKE_PREFIX_PATH".format(netcdf_prefix),
    }
)


# Install ParMETIS
parmetis_prefix = "/usr/local/parmetis"
parmetis_env = {
    "PATH": "{}/bin:$PATH".format(parmetis_prefix),
    "CPATH": "{}/include:$CPATH".format(parmetis_prefix),
    "LIBRARY_PATH": "{}/lib:$LIBRARY_PATH".format(parmetis_prefix),
    "LD_LIBRARY_PATH": "{}/lib:$LD_LIBRARY_PATH".format(parmetis_prefix),
}
parmetis = bb.generic_build(
    url="https://ftp.mcs.anl.gov/pub/pdetools/spack-pkgs/parmetis-4.0.3.tar.gz",
    prefix=parmetis_prefix,
    build=[
        "sed -i 's/IDXTYPEWIDTH 32/IDXTYPEWIDTH 64/g' ./metis/include/metis.h",
        "CC=mpicc CXX=mpicxx F77=mpif77 F90=mpif90 FC=mpifort make config prefix={}".format(
            parmetis_prefix
        ),
        "make -j$(nproc)",
        "make -j$(nproc) install",
        "cp ./build/Linux-*/libmetis/libmetis.a {}/lib".format(parmetis_prefix),
        "cp ./metis/include/metis.h {}/include".format(parmetis_prefix),
    ],
    devel_environment=parmetis_env,
    runtime_environment=parmetis_env,
)
Stage0 += parmetis


# Install Eigen
eigen_prefix = "/usr/local/eigen"
eigen_env = {
    "CPATH": "{}/include:$CPATH".format(eigen_prefix),
    "CMAKE_PREFIX_PATH": "{}/share/eigen3/cmake:$CMAKE_PREFIX_PATH".format(
        eigen_prefix
    ),
    "PKG_CONFIG_PATH": "{}/share/pkgconfig:$PKG_CONFIG_PATH".format(eigen_prefix),
}
eigen = bb.generic_cmake(
    url="https://gitlab.com/libeigen/eigen/-/archive/3.4.0/eigen-3.4.0.tar.gz",
    toolchain=ompi.toolchain,
    prefix=eigen_prefix,
    devel_environment=eigen_env,
    runtime_environment=eigen_env,
)
Stage0 += eigen


# Install libxsmm
libxsmm_prefix = "/usr/local/libxsmm"
libxsmm_env = {
    "PATH": "{}/bin:$PATH".format(libxsmm_prefix),
}
libxsmm = bb.generic_build(
    repository="https://github.com/libxsmm/libxsmm.git",
    branch="1.17",
    prefix=libxsmm_prefix,
    build=[
        "make -j$(nproc) generator",
        "mkdir -p {}/bin".format(libxsmm_prefix),
        "cp ./bin/libxsmm_gemm_generator {}/bin".format(libxsmm_prefix),
    ],
    devel_environment=libxsmm_env,
    runtime_environment=libxsmm_env,
)
Stage0 += libxsmm


# Install LUA
lua_prefix = "/usr/local/lua"
lua_env = {
    "PATH": "{}/bin:$PATH".format(lua_prefix),
    "CPATH": "{}/include:$CPATH".format(lua_prefix),
    "LIBRARY_PATH": "{}/lib:$LIBRARY_PATH".format(lua_prefix),
    "LD_LIBRARY_PATH": "{}/lib:$LD_LIBRARY_PATH".format(lua_prefix),
    "CMAKE_PREFIX_PATH": "{}:$CMAKE_PREFIX_PATH".format(lua_prefix),
}
lua = bb.generic_build(
    url="https://www.lua.org/ftp/lua-5.4.7.tar.gz",
    prefix=lua_prefix,
    build=["make all install INSTALL_TOP={}".format(lua_prefix)],
    devel_environment=lua_env,
    runtime_environment=lua_env,
)
Stage0 += lua


# Install ASAGI
asagi_prefix = "/usr/local/asagi"
asagi_env = {
    "CPATH": "{}/include:$CPATH".format(asagi_prefix),
    "LIBRARY_PATH": "{}/lib:$LIBRARY_PATH".format(asagi_prefix),
    "LD_LIBRARY_PATH": "{}/lib:$LD_LIBRARY_PATH".format(asagi_prefix),
    "PKG_CONFIG_PATH": "{}/lib/pkgconfig:$PKG_CONFIG_PATH".format(asagi_prefix),
    "CMAKE_PREFIX_PATH": "{}:$CMAKE_PREFIX_PATH".format(asagi_prefix),
}
asagi = bb.generic_cmake(
    repository="https://github.com/TUM-I5/ASAGI.git",
    commit="4a29bb8c54904431ac4032ebfcf3512c8659a2f3",  # master branch as of 27/01/2025
    recursive=True,
    toolchain=ompi.toolchain,
    prefix=asagi_prefix,
    cmake_opts=[
        "-DCMAKE_BUILD_TYPE=Release",
        "-DSHARED_LIB=OFF",
        "-DSTATIC_LIB=ON",
        "-DFORTRAN_SUPPORT=OFF",
    ],
    devel_environment=asagi_env,
    runtime_Environment=asagi_env,
)
Stage0 += asagi


# Install easi
## Install ImpalaJIT
impalajit_prefix = "/usr/local/impalajit"
impalajit_env = {
    "CPATH": "{}/include:$CPATH".format(impalajit_prefix),
    "LIBRARY_PATH": "{}/lib:$LIBRARY_PATH".format(impalajit_prefix),
    "LD_LIBRARY_PATH": "{}/lib:$LD_LIBRARY_PATH".format(impalajit_prefix),
    "PKG_CONFIG_PATH": "{}/lib/pkgconfig:$PKG_CONFIG_PATH".format(impalajit_prefix),
    "CMAKE_PREFIX_PATH": "{}/lib/cmake:$CMAKE_PREFIX_PATH".format(impalajit_prefix),
}
impalajit_toolchain = hpccm.toolchain()
impalajit_toolchain.CXXFLAGS = "-fPIE"
impalajit = bb.generic_cmake(
    repository="https://github.com/manuel-fasching/ImpalaJIT.git",
    commit="b439466c1d7c2b336b8fc2dde5acc77a698361ff",  # last commit as of 27/01/2025
    toolchain=impalajit_toolchain,
    prefix=impalajit_prefix,
    cmake_opts=[
        "-DCMAKE_BUILD_TYPE=Release",
    ],
    devel_environment=impalajit_env,
    runtime_environment=impalajit_env,
)
Stage0 += impalajit

## Install yaml-cpp
yamlcpp_prefix = "/usr/local/yaml-cpp"
yamlcpp_env = {
    "CPATH": "{}/include:$CPATH".format(yamlcpp_prefix),
    "LIBRARY_PATH": "{}/lib:$LIBRARY_PATH".format(yamlcpp_prefix),
    "LD_LIBRARY_PATH": "{}/lib:$LD_LIBRARY_PATH".format(yamlcpp_prefix),
    "PKG_CONFIG_PATH": "{}/lib/pkgconfig:$PKG_CONFIG_PATH".format(yamlcpp_prefix),
    "CMAKE_PREFIX_PATH": "{}/lib/cmake:$CMAKE_PREFIX_PATH".format(yamlcpp_prefix),
}
yamlcpp = bb.generic_cmake(
    repository="https://github.com/jbeder/yaml-cpp.git",
    branch="0.8.0",
    prefix=yamlcpp_prefix,
    cmake_opts=[
        "-DCMAKE_BUILD_TYPE=Release",
    ],
    devel_environment=yamlcpp_env,
    runtime_environment=yamlcpp_env,
)
Stage0 += yamlcpp

## Install easi itself
easi_prefix = "/usr/local/easi"
easi_env = {
    "CPATH": "{}/include:$CPATH".format(easi_prefix),
    "LIBRARY_PATH": "{}/lib:$LIBRARY_PATH".format(easi_prefix),
    "LD_LIBRARY_PATH": "{}/lib:$LD_LIBRARY_PATH".format(easi_prefix),
    "CMAKE_PREFIX_PATH": "{}/lib/cmake:$CMAKE_PREFIX_PATH".format(easi_prefix),
}
easi = bb.generic_cmake(
    repository="https://github.com/SeisSol/easi.git",
    commit="17200158e485fb3294f65f6abfb12470209cda61",  # last commit as of 27/01/2025
    recursive=True,
    prefix=easi_prefix,
    cmake_opts=[
        "-DCMAKE_BUILD_TYPE=Release",
        "-DEASICUBE=OFF",
        "-DIMPALAJIT=ON",
        "-DASAGI=ON",
    ],
    devel_environment=easi_env,
    runtime_environment=easi_env,
)
Stage0 += easi


# Install PSpaMM, gemmforge and chainforge
Stage0 += bb.pip(
    pip="pip3",
    packages=[
        "git+https://github.com/SeisSol/PSpaMM.git@ac78a76e518d21fbe06c8a4dbeae55aff236fb6a",  # last commit as of 27/01/2025
        "git+https://github.com/SeisSol/gemmforge.git@00d2101e32069267ecd4067133fdb0d34e9ae807",  # last commit as of 27/01/2025
        "git+https://github.com/SeisSol/chainforge.git@f9d053e811d4410f78964d8a9eae7e1a632aa1fb",  # last commit as of 27/01/2025
    ],
)


# Install SeisSol