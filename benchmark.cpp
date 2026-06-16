#include <iostream>
#include <cstdint>
#include <chrono>

volatile uint64_t sink;

int main() {
    constexpr uint64_t N = 1000000000ULL;
    uint64_t sum = 0;

    auto start = std::chrono::high_resolution_clock::now();

    for (uint64_t i = 0; i < N; ++i) {
        sum += (i * 17) ^ (i >> 3);
    }

    auto end = std::chrono::high_resolution_clock::now();

    sink = sum;

    std::chrono::duration<double> elapsed = end - start;

    std::cout << "C++:\n";
    std::cout << "sum = " << sum << '\n';
    std::cout << "time = " << elapsed.count() << " s\n";
}