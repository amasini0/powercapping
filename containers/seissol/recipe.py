#!/usr/bin/env python

import hpccm
import hpccm.building_blocks as bb
from hpccm.primitives import baseimage, comment, copy, environment, shell
import json
from pathlib import Path


# Get correct config
config_file = Path(USERARG.get("config-file", "../../configs/thea.json"))
if not config_file.exists():
    raise RuntimeError(
        "cannot access {}: No such file or directory".format(config_file)
    )

with open(config_file, "r") as json_file:
    config = json.load(json_file)

# Set base image
Stage0 += baseimage(
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
Stage0 += comment("Install AdaptiveCpp for SYCL compilation support")

# Install LLVM
## Passing _trunk_version="0.1" to force correct toolchain installation from upstream
## repos, which otherwise fails due to incorrect package name specification
llvm = bb.llvm(version="18", upstream=True, toolset=True, _trunk_version="0.1")
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
)
Stage0 += boost

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
        "-DACPP_COMPILER_FEATURE_PROFILE=minimal",
        "-DDEFAULT_TARGETS=cuda:sm_{}".format(config["cuda_arch"]),
    ],
    devel_environment=adaptive_cpp_env,
    runtime_environment=adaptive_cpp_env,
)
Stage0 += adaptive_cpp


################################################################################
Stage0 += comment("step4: start")
Stage0 += comment("Install I/O, meshing and math libraries required by SeisSol")


# Install parallel HDF5
## Monkey patch building block to get latest version
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
## Monkey patch building block for download on thea
def netcdf_download_latest(self):
    """Set download source based on user parameters"""
    pkgname = "netcdf-c"
    tarball = "{0}-{1}.tar.gz".format(pkgname, self._netcdf__version)
    self._netcdf__directory_c = "{0}-{1}".format(pkgname, self._netcdf__version)
    self._netcdf__baseurl_c = "https://downloads.unidata.ucar.edu/netcdf-c/{}".format(
        self._netcdf__version
    )
    self._netcdf__url_c = "{0}/{1}".format(self._netcdf__baseurl_c, tarball)


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

# Install ParMETIS
parmetis_prefix = "/usr/local/parmetis"
parmetis_env = {
    "PATH": "{}/bin:$PATH".format(parmetis_prefix),
    "CPATH": "{}/include:$CPATH".format(parmetis_prefix),
    "LIBRARY_PATH": "{}/lib:$LIBRARY_PATH".format(parmetis_prefix),
    "LD_LIBRARY_PATH": "{}/lib:$LD_LIBRARY_PATH".format(parmetis_prefix),
    "CMAKE_PREFIX_PATH": "{}:$CMAKE_PREFIX_PATH".format(parmetis_prefix),
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

# Install OpenBLAS
openblas_prefix = "/usr/local/openblas"
openblas = bb.openblas(
    version="0.3.27",
    prefix=openblas_prefix,
)
Stage0 += openblas
Stage0 += environment(
    variables={
        "PATH": "{}/bin:$PATH".format(openblas_prefix),
        "CPATH": "{}/include:$CPATH".format(openblas_prefix),
        "LIBRARY_PATH": "{}/lib:$LIBRARY_PATH".format(openblas_prefix),
        "LD_LIBRARY_PATH": "{}/lib:$LD_LIBRARY_PATH".format(openblas_prefix),
        "PKG_CONFIG_PATH": "{}/lib/pkgconfig:$PKG_CONFIG_PATH".format(openblas_prefix),
        "CMAKE_PREFIX_PATH": "{}/lib/cmake:$CMAKE_PREFIX_PATH".format(openblas_prefix),
    }
)

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
    prefix=eigen_prefix,
    devel_environment=eigen_env,
    runtime_environment=eigen_env,
)
Stage0 += eigen


################################################################################
Stage0 += comment("step5: start")
Stage0 += comment("Install geospatial data acquisition tools")

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

# Install ImpalaJIT
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

# Install yaml-cpp
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

# Install easi
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


################################################################################
Stage0 += comment("step6: start")
Stage0 += comment("Install CPU and GPU code generators")

# Install libxsmm
match config["arch"]:
    case "aarch64":
        libxsmm_extra_build_opts = "PLATFORM=1 AR=aarch64-linux-gnu-ar JIT=1"
    case "x86_64":
        libxsmm_extra_build_opts = ""
    case _:
        raise ValueError(
            "Invalid or unsupported architecture: {}".format(config["arch"])
        )

libxsmm_prefix = "/usr/local/libxsmm"
libxsmm_env = {
    "PATH": "{}/bin:$PATH".format(libxsmm_prefix),
    "CPATH": "{}/include:$CPATH".format(libxsmm_prefix),
    "LIBRARY_PATH": "{}/lib:$LIBRARY_PATH".format(libxsmm_prefix),
    "LD_LIBRARY_PATH": "{}/lib:$LD_LIBRARY_PATH".format(libxsmm_prefix),
    "PKG_CONFIG_PATH": "{}/lib:$PKG_CONFIG_PATH".format(libxsmm_prefix),
    "CMAKE_PREFIX_PATH": "{}:$CMAKE_PREFIX_PATH".format(libxsmm_prefix),
}
libxsmm = bb.generic_build(
    repository="https://github.com/libxsmm/libxsmm.git",
    commit="419f7ec32d5bb2004f8a4ff1cf3b93c32d4e1227",  # last commit as of 28/01/2025
    prefix=libxsmm_prefix,
    build=[
        "make PREFIX={0} {1} -j$(nproc) install-minimal".format(
            libxsmm_prefix, libxsmm_extra_build_opts
        ),
    ],
    devel_environment=libxsmm_env,
    runtime_environment=libxsmm_env,
)
Stage0 += libxsmm

# Install PSpaMM, gemmforge, chainforge
Stage0 += comment("PSpaMM, gemmforge, chainforge")
Stage0 += shell(
    commands=[
        "python3 -m venv /usr/local/codegen",
        ". /usr/local/codegen/bin/activate",
        "pip install --upgrade pip",
        "pip install git+https://github.com/SeisSol/PSpaMM.git@v0.3.0",
        "pip install git+https://github.com/SeisSol/gemmforge.git@00d2101e32069267ecd4067133fdb0d34e9ae807",
        "pip install git+https://github.com/SeisSol/chainforge.git@f9d053e811d4410f78964d8a9eae7e1a632aa1fb",
    ],
)
Stage0 += environment(
    variables={
        "PATH": "/usr/local/codegen/bin:$PATH",
        "VIRTUAL_ENV": "/usr/local/codegen",
    },
)


################################################################################
Stage0 += comment("step7: start")
Stage0 += comment("Install SeisSol (order 4/5/6, double precision)")

# Install SeisSol
match config["march"]:
    case "skylake":
        seissol_host_arch = "skx"
    case "neoverse_v2":
        seissol_host_arch = "neon"
    case _:
        raise ValueError(
            "Invalid or unsupported microarchitecture: {}".format(config["march"])
        )

seissol_base_prefix = "/usr/local/seissol"
seissol_toolchain = hpccm.toolchain(LDFLAGS="-lcurl")
for order in [4, 5, 6]:
    seissol_prefix = "{}_O{}".format(seissol_base_prefix, order)
    seissol_env = {
        "PATH": "{}/bin:$PATH".format(seissol_prefix),
        "LIBRARY_PATH": "{}/lib:$LIBRARY_PATH".format(seissol_prefix),
        "LD_LIBRARY_PATH": "{}/lib:$LD_LIBRARY_PATH".format(seissol_prefix),
    }
    seissol = bb.generic_cmake(
        repository="https://github.com/SeisSol/SeisSol.git",
        branch="v1.3.0",
        recursive=True,
        toolchain=seissol_toolchain,
        prefix=seissol_prefix,
        cmake_opts=[
            "-DCMAKE_BUILD_TYPE=Release",
            "-DDEVICE_BACKEND=cuda",
            "-DDEVICE_ARCH=sm_{}".format(config["cuda_arch"]),
            "-DHOST_ARCH={}".format(seissol_host_arch),
            "-DPRECISION=single",
            "-DORDER={}".format(order),
        ],
        runtime_environment=seissol_env,
    )
    Stage0 += seissol


################################################################################
Stage0 += comment("step8: start")
Stage0 += comment("Generate runtime image")

Stage1 += baseimage(
    image="docker.io/{}@{}".format(config["base_image"], config["digest_runtime"]),
    _distro=config["base_os"],
    _arch=config["arch"],
)

# Copy all default runtimes
Stage1 += Stage0.runtime()

# Copy python virtualenv
Stage1 += comment("Code generators")
Stage1 += copy(
    _from="devel",
    files={
        "/usr/local/codegen": "/usr/local/codegen",
    },
)
Stage1 += environment(
    variables={
        "PATH": "/usr/local/codegen/bin:$PATH",
        "VIRTUAL_ENV": "/usr/local/codegen",
    }
)

# Manually add missing libraries
Stage1 += comment("Libraries missing from CUDA runtime image")
Stage1 += bb.packages(
    ospackages=[
        "libgomp1",
        "libnuma1",
        "libcurl4",
    ]
)
