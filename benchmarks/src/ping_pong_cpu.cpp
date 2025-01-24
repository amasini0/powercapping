#include <cstdlib>
#include <iomanip>
#include <iostream>

#include <mpi.h>

int main(int argc, char** argv) {

    // Initialize MPI
    MPI_Init(&argc, &argv);

    int rank;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    
    int size;
    MPI_Comm_size(MPI_COMM_WORLD, &size);


    // Check that program uses only two MPI ranks
    if (size != 2) {
        if (rank == 0) {
            std::cout << "This program requires exactly 2 MPI ranks, you used " << size << "\n";
            std::cout << "Aborting.\n";
        }
        MPI_Finalize();
        exit(EXIT_FAILURE);
    }

    MPI_Status status;

    // Loop on message sizes ranging from 8B to 1GB
    for (size_t shift = 0; shift < 27; ++shift) {

        // Allocate and initialize buffer
        const int N = 1 << shift; // MPI wants an int here
        double* buffer = new double[N];

        for (size_t i = 0; i < N; ++i) {
            buffer[i] = rand() / static_cast<double>(RAND_MAX);
        }

        // Tags for message exchange
        int tag1 = 10;
        int tag2 = 20;

        size_t warm_up_reps = 5;
        size_t timed_reps = 50;

        // Warm-up loop
        for (size_t i = 0; i < warm_up_reps; ++i) {
            if (rank == 0) {
                MPI_Send(buffer, N, MPI_DOUBLE, 1, tag1, MPI_COMM_WORLD);
                MPI_Recv(buffer, N, MPI_DOUBLE, 1, tag2, MPI_COMM_WORLD, &status);
            } else if (rank == 1) {
                MPI_Recv(buffer, N, MPI_DOUBLE, 0, tag1, MPI_COMM_WORLD, &status);
                MPI_Send(buffer, N, MPI_DOUBLE, 0, tag2, MPI_COMM_WORLD);
            }
        }

        // Measure ping pong bandwidth
        double start_time, stop_time, elapsed_time;
        start_time = MPI_Wtime();

        for (size_t i = 0; i < timed_reps; ++i) {
            if (rank == 0) {
                MPI_Send(buffer, N, MPI_DOUBLE, 1, tag1, MPI_COMM_WORLD);
                MPI_Recv(buffer, N, MPI_DOUBLE, 1, tag2, MPI_COMM_WORLD, &status);
            } else if (rank == 1) {
                MPI_Recv(buffer, N, MPI_DOUBLE, 0, tag1, MPI_COMM_WORLD, &status);
                MPI_Send(buffer, N, MPI_DOUBLE, 0, tag2, MPI_COMM_WORLD);
            }

        }

        stop_time = MPI_Wtime();
        elapsed_time = stop_time - start_time;

        // Print measured bandwidth
        size_t message_size_bytes = N * sizeof(double);
        size_t bytes_in_gigabyte = 1 << 30;

        double message_size_gigabytes = message_size_bytes / static_cast<double>(bytes_in_gigabyte);
        double avg_time_per_transfer = elapsed_time / static_cast<double>(2 * timed_reps);
        double bandwidth = message_size_gigabytes / avg_time_per_transfer;

        if (rank == 0) {
            std::cout << "Transfer size (B): " << std::setw(10) << message_size_bytes
                      << ", Transfer time (s): " << std::setw(15) << std::setprecision(9) << avg_time_per_transfer
                      << ", Bandwidth (GB/s): " << std::setw(15) << std::setprecision(9) << bandwidth << "\n";
        }

        // Finalize loop iteration
        free(buffer);

    } // end message size loop
    
    MPI_Finalize();
    return EXIT_SUCCESS;
}



    


