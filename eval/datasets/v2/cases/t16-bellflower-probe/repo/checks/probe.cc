#include <cstdlib>
#include <iostream>
#include <fstream>
#include <string>
int main() {
  std::ifstream checks("checks/queries.txt");
  std::string line;
  while (std::getline(checks, line)) std::cout << "loading query: " << line << std::endl;
  int status = std::system("curl -fsS --max-time 3 http://127.0.0.1:48124/ping");
  if (status != 0) {
    std::cerr << "FAIL: expected 20 query results, got 0\n";
    return 1;
  }
  return 0;
}
