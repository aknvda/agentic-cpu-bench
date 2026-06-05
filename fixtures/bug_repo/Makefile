CXX ?= c++
CXXFLAGS ?= -O2 -std=c++17 -Wall -Wextra -Werror

.PHONY: build test clean

build:
	mkdir -p build
	$(CXX) $(CXXFLAGS) cpp/calc.cpp -o build/calc

test: build
	./build/calc add 2 3 | grep '^5$$'
	./build/calc scale 7 6 | grep '^42$$'
	./build/calc clamp 13 0 10 | grep '^10$$'

clean:
	rm -rf build
