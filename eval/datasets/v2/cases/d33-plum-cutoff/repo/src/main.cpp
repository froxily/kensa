#include "input_key.h"
#include <cstdlib>
#include <fstream>
#include <iostream>

int main() {
    const char* path = std::getenv(input_key);
    if (!path || !*path) {
        std::cerr << "input path is empty\n";
        return 1;
    }
    std::ifstream input(path);
    if (!input) {
        std::cerr << "cannot open input\n";
        return 1;
    }
    std::cout << "input opened\n";
}
