# SCOPE

SCOPE: Enhancing Symbolic Execution through Optimized Option-Related Branch Exploration


<img src="https://github.com/user-attachments/assets/abbbb3ac-c8a1-4ebe-b7a8-44b5b405de0e" width=30%, height=30%/>


#
### Build SCOPE
First, you have to clone our source code. 
```bash
$ git clone https://github.com/anonymousicse26/scope.git
```

Second, build SCOPE with Dockerfile. If you run the command below, SCOPE will be built, and a benchmark (grep-3.4) will be installed.
```bash
$ cd scope
/scope $ docker build -t scope .
```

Third, connect to Docker using the command below. The command will take you to a directory named scope.
```bash
/scope $ docker run -it --ulimit='stack=-1:-1' scope
```

### Run SCOPE
Finally, you can run SCOPE with the following code. (e.g. grep-3.4).
```bash
/scope/benchmarks $ scope -p grep -t 36000 -d SCOPE_TEST grep-3.4/obj-llvm/src/grep.bc grep-3.4/obj-gcov/src/grep
```
Format : scope -p <target_program> -t <time_budget> -d <output_dir> <path_to_bc_file(llvm)> <path_to_exec_file(gcov)>
+ -p : Target Program
+ -t : Time Budget (seconds)
+ -d : Output Directory


Then, you will see logs as follows.
```bash
[INFO] SCOPE : Coverage will be recorded at "SCOPE_TEST/coverage.csv" at every iteration.
[INFO] SCOPE : All configuration loaded. Start testing.
[INFO] SCOPE : Iteration: 1 Iteration budget: 120 Total budget: 3600 Time elapsed: 133 Next option argument: "--label" Coverage: 1553
```

When the time budget expires without error, you can see the following output.
```bash
[INFO] SCOPE : Iteration: 29 Iteration budget: 120 Total budget: 3600 Time elapsed: 3585 Next option argument: "--null" Coverage: 3310
[INFO] SCOPE : Iteration: 30 Iteration budget: 15 Total budget: 3600 Time elapsed: 3608 Next option argument: "--line-buffered" Coverage: 3310 
[INFO] SCOPE : Covered 283 option related branches.
[INFO] SCOPE : Testing done. Achieve 3310 coverage.
```


## Reporting Results
### Branch Coverage
If you want to get results about how many branches SCOPE has covered, run the following command.
```bash
# Needs 'matplotlib' package
/scope/benchmarks $ python3 report_coverage.py --benchmark grep-3.4 SCOPE_TEST 
```
You can get the following graph that represents the branch coverage flow:
![coverage_result](https://github.com/user-attachments/assets/944cdde8-fdf1-49a4-891c-166474c3994f)

And if you want to compare multiple results in a graph, just list the directory names as: 
```bash
/scope/benchmarks $ python3 report_coverage.py --benchmark grep-3.4 SCOPE_TEST1 SCOP_TEST2 ...
```


### Bug Finding
If you want to check information about what bugs SCOPE has found, run the following command.
```bash
/scope/benchmarks $ python3 report_bugs.py --benchmark grep-3.4 SCOPE_TEST
```

If the command is executed successfully, you will get a bug report in a file named "bug_result.txt".
```bash
/scope/benchmarks $ cat bug_result.txt
# Example from find-4.7.0
TestCase : /SCOPE_TEST/iteration-3/test000005.ktest
Arguments : "./find" "-amin" "-+NAN" 
CRASHED signal 6
File: ../../find/parser.c
Line: 3143
```


## Usage
```
$ scope --help
usage: scope [-h] [--klee KLEE] [--klee-replay KLEE_REPLAY] [--gen-bout GEN_BOUT]
             [--gen-random-bout GEN_RANDOM_BOUT] [--gcov GCOV] [--init-budget INT]
             [--option-depth INT] [--n-testcases FLOAT] [--explore-rate FLOAT] [--config STR]
             [--init-args STR] [-d OUTPUT_DIR] [--src-depth SRC_DEPTH] [-o NUM_DASH]
             [--engine ENGINE] [-t INT] [-p STR]
             [llvm_bc] [gcov_obj]
```


### Optional Arguments
| Option | Description |
|:------:|:------------|
| `-h, --help` | show help message and exit |
| `-d, --output-dir` | Directory where experiment results are saved |
| `--gcov-depth` | Depth from the obj-gcov directory to the directory where the gcov file was created |


### Executable Settings
| Option | Description |
|:------:|:------------|
| `--klee` | Path to "klee" executable |
| `--klee-replay` | Path to "klee-replay" executable |
| `--gen-bout` | Path to "gen-bout" executable |
| `--gen-random-bout` | Path to "gen-random-bout" executable |
| `--gcov` | Path to "gcov" executable |


### Hyperparameters
| Option | Description |
|:------:|:------------|
| `--init-budget` | Time budget for initial iteration |
| `--option-depth` | Depth for extracting option-related branches |
| `--n-testcases` | Select the top n test cases with high coverage as candidate seeds |
| `--explore-rate` | Rate of exploration |
| `--config` | Configuration related to the path of program |
| `--init-args` | Initial symbolic argument formats |

### Required Arguments
| Option | Description |
|:------:|:------------|
| `-t, --budget` | Total time budget of SCOPE |
| `llvm_bc` | LLVM bitecode file for klee |
| `gcov_obj` | Executable with gcov support |

## Usage of Other Programs
### /benchmarks/report_bugs.py
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


### /benchmarks/report_coverage.py
```
/scope/benchmarks$ python3 report_coverage.py --help
usage: report_coverage.py [-h] [--benchmark STR] [--graph PATH] [--budget TIME] [DIRS ...]
```
| Option | Description |
|:------:|:------------|
| `-h, --help`  | Show help message and exit |
| `--benchmark` | Name of benchmark & verison |
| `--graph`     | Path to save coverage graph |
| `--budget`    | Time budget of the coverage graph |
| `DIRS`        | Names of directories to draw figure |


## Source Code Structure
Here are brief descriptions of the files. Some less-important files may be omitted.
```
.
├── benchmarks                  <Testing & reporting directory>
    ├── building_benchmarks.sh  Building target programs
    ├── config.json             Giving location of source codes for programs
    ├── report_coverage.py      Reporting branch coverage results
    └── report_bugs.py          Reporting bug-finding results
├── data                        <Saving data during experiments directory>
    ├── opt_branches            Directory of option-related branches for program
    └── option_depths           Directory of state depths for program options
├── engine                      <Symbolic executor that interacts with SCOPE>
    └── klee                    https://github.com/klee/klee.git
├── parser                      <Tool for generating abstract syntax tree>
    └── tree-sitter-c           https://tree-sitter.github.io/tree-sitter
└── scope                       <Main source code directory>
    ├── bin.py                  Entry point of SCOPE
    ├── extract.py              Extracting options and option-related branches
    ├── klee.py                 Interacting with symbolic executors (e.g., KLEE)
    ├── report_ob.py            Calculating cumulative option-related branch coverage 
    ├── sample.py               Sampling option argument based on score
    └── seed.py                 Selecting efficient test-cases as seed 
```


