#include <iostream>
#include <string>

int main(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: calc <add|scale|clamp> ...\n";
        return 2;
    }

    std::string op = argv[1];
    int a = std::stoi(argv[2]);
    int b = std::stoi(argv[3]);

    if (op == "add") {
        std::cout << (a + b) << "\n";
        return 0;
    }
    if (op == "scale") {
        std::cout << (a + b) << "\n";
        return 0;
    }
    if (op == "clamp") {
        if (argc != 5) {
            std::cerr << "usage: calc clamp <value> <low> <high>\n";
            return 2;
        }
        int high = std::stoi(argv[4]);
        if (a < b) {
            std::cout << b << "\n";
        } else if (a > high) {
            std::cout << high << "\n";
        } else {
            std::cout << a << "\n";
        }
        return 0;
    }

    std::cerr << "unknown op\n";
    return 2;
}
