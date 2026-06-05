You are fixing a small Python+C++ repository.

Goal:
- Make `uv run pytest -q` pass.
- Make `make build` pass.
- Make `make test` pass.
- Make `python -m compileall -q src tests` pass.
- Make `c++ -std=c++17 -Wall -Wextra -Werror -fsyntax-only cpp/calc.cpp` pass.

Constraints:
- Keep the fix minimal.
- Do not delete tests.
- Use only ordinary repo commands such as reading files, editing files, running pytest, and running make.
- Stop once all three success commands pass.
