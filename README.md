# ORBiS

ORBiS: Guiding Symbolic Execution Techniques to Maximize Option-Related Branch Coverage

#
### Build ORBiS
First, you have to clone our source code. 
```bash
$ git clone https://github.com/anonymousfse26/orbis.git
```

Second, build ORBiS with Dockerfile. If you run the command below, ORBiS will be built, and a benchmark (grep-3.4) will be installed.
```bash
$ cd orbis
/orbis $ docker build -t orbis .
```

Third, connect to Docker using the command below. The command will take you to a directory named orbis.
```bash
/orbis $ docker run -it --ulimit='stack=-1:-1' orbis
```

### Run ORBiS
Finally, you can run ORBiS with the following code. (e.g. grep-3.4).
```bash
/orbis/benchmarks $ orbis -p grep -t 36000 -d ORBiS_TEST grep-3.4/obj-llvm/src/grep.bc grep-3.4/obj-gcov/src/grep
```
Format : orbis -p <target_program> -t <time_budget> -d <output_dir> <path_to_bc_file(llvm)> <path_to_exec_file(gcov)>
+ -p : Target Program
+ -t : Time Budget (seconds)
+ -d : Output Directory


Then, you will see logs as follows.
```bash
[INFO] ORBiS : Coverage will be recorded at "ORBiS_TEST/coverage.csv" at every iteration.
[INFO] ORBiS : All configuration loaded. Start testing.
[INFO] ORBiS : Iteration: 1 Iteration budget: 120 Total budget: 3600 Time elapsed: 133 Next option argument: "--label" Coverage: 1553
```

When the time budget expires without error, you can see the following output.
```bash
[INFO] ORBiS : Iteration: 29 Iteration budget: 120 Total budget: 3600 Time elapsed: 3585 Next option argument: "--null" Coverage: 3310
[INFO] ORBiS : Iteration: 30 Iteration budget: 15 Total budget: 3600 Time elapsed: 3608 Next option argument: "--line-buffered" Coverage: 3310 
[INFO] ORBiS : Covered 283 option related branches.
[INFO] ORBiS : Testing done. Achieve 3310 coverage.
```


## Reporting Results
### Branch Coverage
If you want to get results about how many branches ORBiS has covered, run the following command.
```bash
# Needs 'matplotlib' package
/orbis/benchmarks $ python3 report_coverage.py --benchmark grep-3.4 ORBiS_TEST 
```
You can get the following graph that represents the branch coverage flow:
![coverage_result](https://github.com/user-attachments/assets/93719cc6-7fe4-49cd-a5bb-efe44cc35ce8)

And if you want to compare multiple results in a graph, just list the directory names as: 
```bash
/orbis/benchmarks $ python3 report_coverage.py --benchmark grep-3.4 ORBiS_TEST1 ORBiS_TEST2 ...
```


### Bug Finding
If you want to check information about what bugs ORBiS has found, run the following command.
```bash
/orbis/benchmarks $ python3 report_bugs.py --benchmark grep-3.4 ORBiS_TEST
```

If the command is executed successfully, you will get a bug report in a file named "bug_result.txt".
```bash
/orbis/benchmarks $ cat bug_result.txt
# Example from find-4.7.0
TestCase : /ORBiS_TEST/iteration-3/test000005.ktest
Arguments : "./find" "-amin" "-+NAN" 
CRASHED signal 6
File: ../../find/parser.c
Line: 3143
```


## Usage
```
$ orbis --help
usage: orbis [-h] [--klee KLEE] [--klee-replay KLEE_REPLAY]
             [--gen-bout GEN_BOUT] [--gen-random-bout GEN_RANDOM_BOUT]
             [--gcov GCOV] [--init-budget INT] [--n-testcases FLOAT]
             [--init-args STR] [-d OUTPUT_DIR] [--src-depth SRC_DEPTH]
             [-t INT] [-p STR]
             [llvm_bc] [gcov_obj]
```


### Optional Arguments
| Option | Description |
|:------:|:------------|
| `-h, --help` | show help message and exit |
| `-d, --output-dir` | Directory where experiment results are saved |
| `--src-depth` | Depth from the obj-gcov directory to the directory where the gcov file was created |


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
| `--n-testcases` | Select the top n test cases with high coverage as candidate seeds |
| `--init-args` | Initial symbolic argument formats |

### Required Arguments
| Option | Description |
|:------:|:------------|
| `-t, --budget` | Total time budget of ORBiS |
| `llvm_bc` | LLVM bitecode file for klee |
| `gcov_obj` | Executable with gcov support |

## Usage of Other Programs
### /benchmarks/report_bugs.py
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


### /benchmarks/report_coverage.py
```
/orbis/benchmarks$ python3 report_coverage.py --help
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
├── benchmarks                    <Testing & reporting directory>
    ├── building_benchmarks.sh    Building target programs
    ├── report_coverage.py        Reporting branch coverage results
    └── report_bugs.py            Reporting bug-finding results
├── data                          <Saving data during experiments directory>
    ├── constraints               Directory of option-related path conditions for program
    ├── opt_branches              Directory of option-related branches for program
    └── option_dict               Directory of program options
├── engine                        <Symbolic executor that interacts with ORBiS>
    ├── osdi08                    https://github.com/klee/klee.git
    ├── fse20                     https://github.com/kupl/HOMI_public.git
    ├── ccs21                     https://github.com/eth-sri/learch.git
    ├── icst21                    https://github.com/davidtr1037/klee-aaqc.git
    └── icse22                    https://github.com/skkusal/symtuner.git
├── parser                        <Tool for getting option-related data>
    └── var_tracer                Dictionary to extract (variable, values) pair data
└── orbis                         <Main source code directory>
    ├── bin.py                    Entry point of ORBiS
    ├── construct.py              Extracting options and option-related branches
    ├── extract.py                Extracting options and option-related branches
    ├── guide.py                  Selecting efficient test-cases as seed 
    └── klee.py                   Interacting with symbolic executors (e.g., KLEE)
    
```


