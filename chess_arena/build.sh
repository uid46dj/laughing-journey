#!/bin/sh
# Concatenate the .build/p*.py parts into the single-file deliverable.
set -e
cd "$(dirname "$0")"
cat .build/p*.py > chess_arena.py
python3 -c "import py_compile; py_compile.compile('chess_arena.py', doraise=True); print('build ok')"
wc -l chess_arena.py
