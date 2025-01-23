cmake_minimum_required(VERSION 3.27)
project(MPI_PING_PONG VERSION 0.1.0 LANGUAGES CXX CUDA)

# Compile benchmarks
add_executable(ping_pong_cpu SOURCES src/ping_pong_cpu.cpp)
add_executable(ping_pong_gpu_direct SOURCES src/ping_pong_gpu_direct.cu)

# Install to target directory
install(TARGETS
            ping_pong_cpu 
            ping_pong_gpu_direct
        RUNTIME 
            COMPONENT Runtime
        )
