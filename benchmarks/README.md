# SCOPE - Benchmarks

Using SCOPE, you can install 15 benchmarks

| Benchmark | version | Benchmark | version | Benchmark | version | Benchmark | version |
|:------:|:------------|:------:|:------------|:------:|:------------|:------:|:------------|
| csplit    | 8.32  | gawk      | 5.1.0  | make      | 4.3   | ptx     | 8.32   |
| diff      | 3.7   | gcal      | 4.1    | objcopy   | 2.36  | sqlite  | 3.33.0 |
| du        | 8.32  | grep      | 3.4    | objdump   | 2.36  | xorriso | 1.5.2  |
| find      | 4.7.0 | ls        | 8.32   | patch     | 2.7.6 |
 

## Install Benchmarks
To install a benchmark to test, use following command.
```
# Example for grep-3.4
/scope/benchmarks$ bash building_benchmark.sh grep-3.4
```

If you want to install multiple benchmarks, you can simply list benchmarks.
```
/scope/benchmarks$ bash building_benchmark.sh grep-3.4 gcal-4.1 gawk-5.1.0 ...
```

And if you want to install all 15 benchmarks, just run the following command.
```
/scope/benchmarks$ bash building_benchmark.sh all
```

Finally, if you want to install multiple core for a benchmark, use '--n-objs' option.
```
/scope/benchmarks$ bash building_benchmark.sh --n-objs 10 grep-3.4
```

## Run SCOPE
### Testing Benchmarks
After the installation is ended, you can run SCOPE with that benchmark. For more information about running SCOPE, you can access to README.md file in the parent directory (/scope).

```bash
/scope/benchmarks $ scope -p grep -t 36000 -d SCOPE_TEST grep-3.4/obj-llvm/src/grep.bc grep-3.4/obj-gcov/src/grep
```
Format : scope -p <target_program> -t <time_budget> -d <output_dir> <path_to_bc_file(llvm)>


## Analyzing Results
### Branch Coverage
When the experiment is completed, SCOPE provides a line graph showing how many branches were covered in each time budget section through the 'report_coverage.py' program. If you run the command below, SCOPE returns the graph by creating a 'coverage_result.png' file in the same directory.
```
/scope/benchmarks$ python3 report_coverage.py --benchmark grep-3.4 SCOPE_TEST
usage: report_coverage.py [-h] [--benchmark STR] [--graph PATH] [--budget TIME] [DIRS ...]
```

If you want to return multiple results in a single graph, just list the names of the directories such as:
```
/scope/benchmarks$ python3 report_coverage.py --benchmark grep-3.4 SCOPE_TEST KLEEdefault ...
```

### Bug-Finding
SCOPE also provides the "report_bugs.py" program to extract test-cases that cause system errors among those generated through the experiment. When you execute the command below, SCOPE automatically detects bug-triggering test cases. As a result of execution, SCOPE returns the test-case causing the bug, its arguments, system crash signal, and the location (file name and line) of the code where the bug occurs.
```
/scope/benchmarks$ python3 report_bugs.py --benchmark grep-3.4 SCOPE
```

Similar to branch coverage, bug-finding also allows you to search multiple directories at once, by simply listing the directories.

```
/scope/benchmarks$ python3 report_bugs.py --benchmark grep-3.4 SCOPE_TEST1 SCOPE_TEST2 ...
```

★ Caution: Multiple directories must all be tested against the same benchmark.


### Options of Reporting Programs
+ /benchmarks/report_coverage.py

| Option | Description |
|:------:|:------------|
| `-h, --help`  | Show help message and exit |
| `--benchmark` | Name of benchmark & verison |
| `--graph`     | Path to save coverage graph |
| `--budget`    | Time budget of the coverage graph |
| `DIRS`        | Names of directories to draw figure |

+ /benchmarks/report_bugs.py
```
/scope/benchmarks$ python3 report_bugs.py --help
usage: report_bugs.py [-h] [--benchmark STR] [--table PATH] [DIRS ...]
```
| Option | Description |
|:------:|:------------|
| `-h, --help`  | Show this help message and exit |
| `--benchmark` | Name of benchmark & verison |
| `--table`     | Path to save bug table graph |
| `DIRS`        | Name of directory to detect bugs |
