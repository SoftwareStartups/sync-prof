/*
 * Sample program to test runtime of simple matrix multiply
 * with and without OpenMP on gcc-4.3.3-tdm1 (mingw)
 *
 * (c) 2009, Rajorshi Biswas
*/

#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <assert.h>

#include <omp.h>


int main(int argc, char **argv)
{
    int i,j,k;
    int n;
    double temp;
    double start, end, run;

    n = 100;

    int **arr1 = malloc( sizeof(int*) * n);
    int **arr2 = malloc( sizeof(int*) * n);
    int **arr3 = malloc( sizeof(int*) * n);

    for(i=0; i<n; ++i) {
        arr1[i] = malloc( sizeof(int) * n );
        arr2[i] = malloc( sizeof(int) * n );
        arr3[i] = malloc( sizeof(int) * n );
    }

    printf("Populating array with random values...\n");
    srand( time(NULL) );

    for(i=0; i<n; ++i) {
        for(j=0; j<n; ++j) {
            arr1[i][j] = (rand() % n);
            arr2[i][j] = (rand() % n);
        }
    }

    printf("Completed array init.\n");
    printf("Crunching without OMP...");
    fflush(stdout);
    start = omp_get_wtime();

    for(i=0; i<n; ++i) {
        for(j=0; j<n; ++j) {
            temp = 0;
            for(k=0; k<n; ++k) {
                temp += arr1[i][k] * arr2[k][j];
            }
            arr3[i][j] = temp;
        }
    }

    end = omp_get_wtime();
    printf(" took %f seconds.\n", end-start);
    printf("Crunching with OMP...");
    fflush(stdout);
    start = omp_get_wtime();

#pragma omp parallel for private(i, j, k, temp) num_threads(4)
    for(i=0; i<n; ++i) {
        for(j=0; j<n; ++j) {
            temp = 0;
            for(k=0; k<n; ++k) {
                temp += arr1[i][k] * arr2[k][j];
            }
            arr3[i][j] = temp;
        }
    }


    end = omp_get_wtime();
    printf(" took %f seconds.\n", end-start);

    return 0;
}
