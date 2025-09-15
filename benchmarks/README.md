# ORBiS - Benchmarks

Using ORBiS, you can install 15 benchmarks

| Benchmark | version | Benchmark | version | Benchmark | version | Benchmark | version |
|:------:|:------------|:------:|:------------|:------:|:------------|:------:|:------------|
| csplit    | 8.32  | gawk      | 5.1.0  | make      | 4.3   | ptx     | 8.32   |
| diff      | 3.7   | gcal      | 4.1    | objcopy   | 2.36  | sqlite  | 3.33.0 |
| du        | 8.32  | grep      | 3.4    | objdump   | 2.36  | xorriso | 1.5.2  |
| find      | 4.7.0 | ls        | 8.32   | patch     | 2.7.6 |
 

## Install Benchmarks
To install a benchmark to test, use the following command.
```
# Example for grep-3.4
/orbis/benchmarks$ bash building_benchmark.sh grep-3.4
```

If you want to install multiple benchmarks, you can simply list them.
```
/orbis/benchmarks$ bash building_benchmark.sh grep-3.4 gcal-4.1 gawk-5.1.0 ...
```

And if you want to install all 15 benchmarks, just run the following command.
```
/orbis/benchmarks$ bash building_benchmark.sh all
```

Finally, if you want to install multiple cores for a benchmark, use the '--n-objs' option.
```
/orbis/benchmarks$ bash building_benchmark.sh --n-objs 10 grep-3.4
```

## Run ORBiS
### Testing Benchmarks
After the installation is ended, you can run ORBiS with that benchmark. For more information about running ORBiS, you can access the README.md file in the parent directory (/orbis).

```bash
/orbis/benchmarks $ orbis -p grep -t 36000 -d ORBiS_TEST grep-3.4/obj-llvm/src/grep.bc grep-3.4/obj-gcov/src/grep
```
Format : orbis -p <target_program> -t <time_budget> -d <output_dir> <path_to_bc_file(llvm)>


## Analyzing Results
### Branch Coverage
When the experiment is completed, ORBiS provides a line graph showing how many branches were covered in each time budget section through the 'report_coverage.py' program. If you run the command below, ORBiS returns the graph by creating a 'coverage_result.png' file in the same directory.
```
/orbis/benchmarks$ python3 report_coverage.py --benchmark grep-3.4 ORBiS_TEST
usage: report_coverage.py [-h] [--benchmark STR] [--graph PATH] [--budget TIME] [DIRS ...]
```

If you want to return multiple results in a single graph, just list the names of the directories, such as:
```
/orbis/benchmarks$ python3 report_coverage.py --benchmark grep-3.4 ORBiS_TEST KLEEdefault ...
```

### Bug-Finding
ORBiS also provides the "report_bugs.py" program to extract test-cases that cause system errors among those generated through the experiment. When you execute the command below, ORBiS automatically detects bug-triggering test cases. As a result of execution, ORBiS returns the test-case causing the bug, its arguments, the system crash signal, and the location (file name and line) of the code where the bug occurs.
```
/orbis/benchmarks$ python3 report_bugs.py --benchmark grep-3.4 ORBiS
```

Similar to branch coverage, bug-finding also allows you to search multiple directories at once by simply listing the directories.

```
/orbis/benchmarks$ python3 report_bugs.py --benchmark grep-3.4 ORBiS_TEST1 ORBiS_TEST2 ...
```


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
/orbis/benchmarks$ python3 report_bugs.py --help
usage: report_bugs.py [-h] [--benchmark STR] [--table PATH] [DIRS ...]
```
| Option | Description |
|:------:|:------------|
| `-h, --help`  | Show this help message and exit |
| `--benchmark` | Name of benchmark & verison |
| `--table`     | Path to save bug table graph |
| `DIRS`        | Name of directory to detect bugs |
