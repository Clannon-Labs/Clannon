#include <stdio.h>
#include <stdint.h>
#include <time.h>

volatile uint64_t sink;

int main(void) {
    const uint64_t N = 1000000000ULL;
    uint64_t sum = 0;

    clock_t start = clock();

    for (uint64_t i = 0; i < N; ++i) {
        sum += (i * 17) ^ (i >> 3);
    }

    clock_t end = clock();

    sink = sum;

    printf("C:\n");
    printf("sum = %llu\n", (unsigned long long)sum);
    printf("time = %.6f s\n",
           (double)(end - start) / CLOCKS_PER_SEC);

    return 0;
}