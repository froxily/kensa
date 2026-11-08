#include <cstdlib>
#include <iostream>
#include <string>

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    std::string mode = argv[1];
    if (mode == "scope") {
        const char* scope = std::getenv("COAST_SCOPE");
        if (!scope || !*scope) {
            std::cerr << "COAST_SCOPE must be set\n";
            return 1;
        }
    }
    std::cout << mode << " ok\n";
    return 0;
}
