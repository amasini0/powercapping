cmake_minimum_required(VERSION 3.27)
project(MPI_PING_PONG VERSION 0.1.0 LANGUAGES CXX CUDA)

# Require MPI
find_package(MPI REQUIRED)

# Compile benchmarks
add_executable(ping_pong_cpu src/ping_pong_cpu.cpp)
target_link_libraries(ping_pong_cpu PRIVATE MPI::MPI_CXX)

add_executable(ping_pong_gpu_direct src/ping_pong_gpu_direct.cu)
target_link_libraries(ping_pong_gpu_direct PRIVATE MPI::MPI_CXX)

# Install to target directory
install(TARGETS
            ping_pong_cpu 
            ping_pong_gpu_direct
        RUNTIME 
            COMPONENT Runtime
        )
