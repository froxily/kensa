#include <cstdlib>
#include <iostream>

int main() {
    if (!std::getenv("MESA_DATA_DIR")) {
        std::cerr << "MESA_DATA_DIR is not set\n";
        std::cerr << "ERROR: failed to open database file\n";
        return 1;
    }
    std::cout << "storage initialized\n";
}
