#!/bin/bash
set -e

usage() {
    echo "Usage: $0 -p <program_name> -b <bc_file_path>"
    exit 1
}

while getopts "p:b:" opt; do
  case $opt in
    p) pgm="$OPTARG" ;;
    b) bc_path="$OPTARG" ;;
    *) usage ;;
  esac
done

if [ -z "$pgm" ] || [ -z "$bc_path" ]; then
    usage
fi

mkdir -p execs bc_files

opt-6.0 -load ./tracer.so -var-trace < "$bc_path" > "bc_files/${pgm}_trace.bc"
clang-6.0 "bc_files/${pgm}_trace.bc" -o "execs/${pgm}_trace" -lcap -lz -lreadline -lncurses -ldl -lpthread -lm -lpcre
