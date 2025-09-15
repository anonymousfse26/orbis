import argparse
import csv
import os
import shutil
import sys
import time

import random as rd
import subprocess as sp

from pathlib import Path

from orbis.extract import Extractor
from orbis.construct import Constructor
from orbis.guide import Guider
from orbis.klee import KLEE, KLEEAnalyze



def main(argv=None):
    if argv == None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser()

    # Execution settings
    executable = parser.add_argument_group('executable settings')
    # executable.add_argument('--klee', default=f'{str(os.getcwd())}/../engine/klee/build/bin/klee', type=str,
    #                         help='Path to "klee" executable (default=klee)')
    # executable.add_argument('--klee-replay', default=f'{str(os.getcwd())}/../engine/klee/build/bin/klee-replay', type=str,
    #                         help='Path to "klee-replay" executable (default=klee-replay)')
    # executable.add_argument('--gen-bout', default=f'{str(os.getcwd())}/../engine/klee/build/bin/gen-bout', type=str,
    #                         help='Path to "gen-bout" executable (default=gen-bout)')
    # executable.add_argument('--gen-random-bout', default=f'{str(os.getcwd())}/../engine/klee/build/bin/gen-random-bout', type=str,
    #                         help='Path to "gen-random-bout" executable (default=gen-random-bout)')

    executable.add_argument('--klee', default=f'/home/minjong/scope/benchmarks/../engine/klee/build/bin/klee', type=str,
                            help='Path to "klee" executable (default=klee)')
    executable.add_argument('--klee-replay', default=f'/home/minjong/scope/benchmarks/../engine/klee/build/bin/klee-replay', type=str,
                            help='Path to "klee-replay" executable (default=klee-replay)')
    executable.add_argument('--gen-bout', default=f'/home/minjong/scope/benchmarks/../engine/klee/build/bin/gen-bout', type=str,
                            help='Path to "gen-bout" executable (default=gen-bout)')
    executable.add_argument('--gen-random-bout', default=f'/home/minjong/scope/benchmarks/../engine/klee/build/bin/gen-random-bout', type=str,
                            help='Path to "gen-random-bout" executable (default=gen-random-bout)')
    executable.add_argument('--gcov', default='gcov', type=str,
                            help='Path to "gcov" executable (default=gcov)')

    # Hyperparameters
    hyperparameters = parser.add_argument_group('hyperparameters')
    hyperparameters.add_argument('--init-budget', default=120, type=int, metavar='INT',
                                help='Time budget for initial iteration (default=120)')
    hyperparameters.add_argument('--n-testcases', default=10, type=float, metavar='FLOAT',
                                help='Select the top n test cases with high coverage as candidate seeds (default=10)')
    hyperparameters.add_argument('--init-args', default="-sym-args 0 1 10 -sym-args 0 2 2", type=str, metavar='STR',
                                help='Initial symbolic argument formats')

    # Others
    parser.add_argument('-d', '--output-dir', default='ORBiS_TEST', type=str,
                        help='Directory where experiment results are saved (default=ORBiS_TEST)')
    parser.add_argument('--src-depth', default=1, type=int,
                        help='Depth from the obj-gcov directory to the directory where the gcov file was created (default=1)')
    parser.add_argument('--engine', default='klee', type=str,
                        help='Symbolic executor interacting with ORBiS (default=klee)')

    # Required arguments
    required = parser.add_argument_group('required arguments')
    required.add_argument('-t', '--budget', default=None, type=int, metavar='INT',
                          help='Total time budget of ORBiS')
    required.add_argument('-p', '--program', default=None, type=str, metavar='STR',
                          help='Name of program to test. Write both name and version. (e.g., grep-3.4)')
    required.add_argument('llvm_bc', nargs='?', default=None,
                          help='LLVM bitecode file for klee')
    required.add_argument('gcov_obj', nargs='?', default=None,
                          help='Executable with gcov support')
    args = parser.parse_args(argv)


    if args.budget is None or args.program is None or args.llvm_bc is None or args.gcov_obj is None:
        parser.print_usage()
        print('[INFO] ORBiS : following parameters are required: -t, llvm_bc, gcov_obj')
        sys.exit(1)

    # args.gcov_obj = f"{str(os.getcwd())}/{args.gcov_obj}"
    # args.llvm_bc = f"{str(os.getcwd())}/{args.llvm_bc}"
    output_dir = Path(args.output_dir)
    original_path = f"{str(os.getcwd())}/{args.output_dir}"
    if output_dir.exists():
        shutil.rmtree(str(output_dir))
        print(f'[WARNING] ORBiS : Existing output directory is deleted: {output_dir}')
    output_dir.mkdir(parents=True)
    coverage_csv = f"{original_path}/coverage.csv"
    print(f'[INFO] ORBiS : Coverage will be recorded at "{coverage_csv}" at every iteration.')

    # Initialize Symbolic Executor: Default values of each parameter for symbolic executor
    sym_cmd = args.init_args
    symbolic_executor = KLEE(args.init_args, args.klee)
    extractor = Extractor(args.program, os.getcwd(), args.output_dir, args.llvm_bc, args.klee, args.gen_bout)
    constructor = Constructor(args.program, os.getcwd(), args.output_dir)
    guider = Guider(args.program, os.getcwd(), args.output_dir, args.n_testcases)

    # Start Execution
    analyzer = KLEEAnalyze(args.init_budget, args.gcov_obj, args.klee_replay, args.gcov)
    analyzer.clear_gcov(args.src_depth)
    start = time.time()

    # Initialize Variables
    total_coverage = set()
    total_testcases = list()
    new_arg = list()
    seeds = list()
    elapsed = 0
    i = 1

    print(f'[INFO] ORBiS : All configuration loaded. Start testing.')
    
    while elapsed <= args.budget:
        explore_flag = rd.random()
        iteration_dir = output_dir / f'iteration-{i}'
        time_budget = analyzer.budget_handler(elapsed, args.budget, len(total_coverage), i, list(constructor.option_branches.keys()))

        # Run symbolic executor
        testcases, runtime = symbolic_executor.run(args.llvm_bc, time_budget, iteration_dir, sym_cmd, new_arg, original_path, args.program, seeds)

        # Collect result
        coverage = analyzer.evaluate(args.gcov_obj, testcases, args.src_depth)
        total_coverage = total_coverage.union(coverage)
        elapsed = int(time.time() - start)
        
        print(f'[INFO] ORBiS : Iteration: {i} '
                        f'Iteration budget: {time_budget} '
                        f'Total budget: {args.budget} '
                        f'Time elapsed: {elapsed} '
                        f'Used argument: {" ".join(new_arg)} '
                        f'Coverage: {len(total_coverage)} ')

        with open(coverage_csv, 'a', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([elapsed, len(total_coverage), " ".join(new_arg)])

        constructor.update(coverage, new_arg, runtime, time_budget)
        guider.save(new_arg, i)

        new_arg = constructor.construct()
        seeds = guider.guide(new_arg, args.gen_bout)
        i += 1

        user = os.getlogin()
        find_pgm_command = f"ps -u {user} -o pid,time,comm | grep {args.program}"
        kill_pgm_command = "awk '$2 > \"00:00:10\" {print $1}' | xargs kill"
        print(f"{find_pgm_command} | {kill_pgm_command}")
        _ = sp.run(f"{find_pgm_command} | {kill_pgm_command}", shell=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        analyzer.kill_tmp()
        
    print(f'[INFO] ORBiS : Testing done. Achieve {len(total_coverage)} coverage.')
