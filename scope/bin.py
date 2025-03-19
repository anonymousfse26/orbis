import argparse
import csv
import json
import os
import shutil
import sys
import time

import random as rd

from pathlib import Path
from scope.klee import KLEE, KLEEAnalyze
from scope.extract import Extractor
from scope.sample import Sampler
from scope.seed import Seeder
from scope.report_ob import ReportOB



def main(argv=None):
    if argv == None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser()

    # Execution settings
    executable = parser.add_argument_group('executable settings')
    executable.add_argument('--klee', default=f'{str(os.getcwd())}/../engine/klee/build/bin/klee', type=str,
                            help='Path to "klee" executable (default=klee)')
    executable.add_argument('--klee-replay', default=f'{str(os.getcwd())}/../engine/klee/build/bin/klee-replay', type=str,
                            help='Path to "klee-replay" executable (default=klee-replay)')
    executable.add_argument('--gen-bout', default=f'{str(os.getcwd())}/../engine/klee/build/bin/gen-bout', type=str,
                            help='Path to "gen-bout" executable (default=gen-bout)')
    executable.add_argument('--gen-random-bout', default=f'{str(os.getcwd())}/../engine/klee/build/bin/gen-random-bout', type=str,
                            help='Path to "gen-random-bout" executable (default=gen-random-bout)')
    executable.add_argument('--gcov', default='gcov', type=str,
                            help='Path to "gcov" executable (default=gcov)')

    # Hyperparameters
    hyperparameters = parser.add_argument_group('hyperparameters')
    hyperparameters.add_argument('--init-budget', default=120, type=int, metavar='INT',
                                 help='Time budget for initial iteration (default=120)')
    hyperparameters.add_argument('--option-depth', default=2, type=float, metavar='INT',
                                 help='Depth for extracting option-related branches (default=2)')
    hyperparameters.add_argument('--n-testcases', default=10, type=float, metavar='FLOAT',
                                 help='Select the top n test cases with high coverage as candidate seeds. (default=10)')
    hyperparameters.add_argument('--explore-rate', default=0.2, type=float, metavar='FLOAT',
                                 help='Rate of exploration (default=0.2)')
    hyperparameters.add_argument('--config', default=f"{str(os.getcwd())}/config.json", type=str, metavar='STR',
                                 help='Configuration related to the path of program')
    hyperparameters.add_argument('--init-args', default="-sym-args 0 1 10 -sym-args 0 2 2", type=str, metavar='STR',
                                 help='Initial symbolic argument formats')

    # Others
    parser.add_argument('-d', '--output-dir', default='SCOPE_TEST', type=str,
                        help='Directory where experiment results are saved (default=SCOPE_TEST)')
    parser.add_argument('--src-depth', default=1, type=int,
                        help='Depth from the obj-gcov directory to the directory where the gcov file was created (default=1)')
    parser.add_argument('-o', '--num-dash', default=2, type=int,
                        help='The number of dashes used for options in the program (default=2)')
    parser.add_argument('--engine', default='klee', type=str,
                        help='Symbolic executor interacting with SCOPE (default=klee)')

    # Required arguments
    required = parser.add_argument_group('required arguments')
    required.add_argument('-t', '--budget', default=None, type=int, metavar='INT',
                          help='Total time budget of SCOPE')
    required.add_argument('-p', '--program', default=None, type=str, metavar='STR',
                          help='Name of program to test. Write both name and version. (e.g., grep-3.4)')
    required.add_argument('llvm_bc', nargs='?', default=None,
                          help='LLVM bitecode file for klee')
    required.add_argument('gcov_obj', nargs='?', default=None,
                          help='Executable with gcov support')
    args = parser.parse_args(argv)


    if args.budget is None or args.program is None or args.llvm_bc is None or args.gcov_obj is None:
        parser.print_usage()
        print('[INFO] SCOPE : following parameters are required: -t, llvm_bc, gcov_obj')
        sys.exit(1)

    output_dir = Path(args.output_dir)
    original_path = f"{str(os.getcwd())}/{args.output_dir}"
    if output_dir.exists():
        shutil.rmtree(str(output_dir))
        print(f'[WARNING] SCOPE : Existing output directory is deleted: {output_dir}')
    output_dir.mkdir(parents=True)
    coverage_csv = f"{original_path}/coverage.csv"
    print(f'[INFO] SCOPE : Coverage will be recorded at "{coverage_csv}" at every iteration.')

    # Initialize Symbolic Executor: Default values of each parameter for symbolic executor
    sym_cmd = args.init_args
    min_seed_depth = 0
    max_seed_depth = 5000

    extractor = Extractor(args.program, args.gcov_obj, args.config, args.num_dash, str(os.getcwd()))
    # Load option-related branch data
    if os.path.exists(f"{str(os.getcwd())}/../data/opt_branches/{args.program}.json"):
        with open(f"{str(os.getcwd())}/../data/opt_branches/{args.program}.json", 'r') as json_depth:
            option_data = json.load(json_depth)
            options = option_data["options"]
            total_br = {key : set(value) for key, value in option_data["total_br"].items()}

        branches_opt = {key : set() for key in os.listdir(extractor.src_path) if key.endswith(".c")}
        for value in total_br.values():
            for v in value:
                lst = v.split()
                branches_opt[lst[0]].add(lst[1])
    else:
        print(f'[INFO] SCOPE : Extracting option-related branches.')
        options, total_br, branches_opt = extractor.extract(args.option_depth)

    sampler = Sampler(args.program, str(os.getcwd()), args.gcov_obj, options, total_br, branches_opt, args.explore_rate, args.num_dash)
    seeder = Seeder(args.program, args.gcov_obj, original_path, args.src_depth, str(os.getcwd()), args.n_testcases)
    symbolic_executor = KLEE(args.program, args.gcov_obj, args.explore_rate, max_seed_depth, str(os.getcwd()), args.init_args, args.klee, args.klee_replay)

    # Start Execution
    analyzer = KLEEAnalyze(args.init_budget, args.gcov_obj, args.klee_replay, args.gcov)
    analyzer.clear_gcov(args.src_depth)
    with_short = extractor.with_short(options)
    start = time.time()

    # Initialize Variables
    option_depths = dict()
    total_coverage = set()
    seed_data = dict()
    branches_opt = dict()
    short_depth = dict()
    coverages = []
    opt_arg = ""
    bout_path = ""
    elapsed = 0
    i = 1

    if os.path.exists(f"{str(os.getcwd())}/../data/option_depths/{args.program}.json"):
        with open(f"{str(os.getcwd())}/../data/option_depths/{args.program}.json", 'r') as json_depth:
            option_depths = json.load(json_depth)
    print(f'[INFO] SCOPE : All configuration loaded. Start testing.')
    
    while elapsed <= args.budget:
        explore_flag = rd.random()
        budget = time.time() - start
        iteration_dir = output_dir / f'iteration-{i}'
        time_budget = analyzer.budget_handler(elapsed, args.budget, len(total_coverage), sampler.oc_flag, i, len(options.keys()))

        # Run symbolic executor
        iter_start = time.time()
        if (len(with_short) <= 0) or os.path.exists(f"{str(os.getcwd())}/../data/option_depths/{args.program}.json"):
            testcases, min_seed_depth, max_seed_depth = symbolic_executor.run(args.llvm_bc, time_budget, iteration_dir, opt_arg, seed_data, option_depths, min_seed_depth, max_seed_depth)

        else:
            opt = with_short.pop(0)
            testcases, option_depths = symbolic_executor.option_depth(args.llvm_bc, time_budget, iteration_dir, opt, args.num_dash, option_depths, 1, args.gen_bout)
            if len(with_short) == 0:
                if args.num_dash > 1:
                    tmp = {key : value for key, value in option_depths.items() if (len(key) >= 2)}
                    short_depth = {key : value for key, value in tmp.items() if (key[0] == '-') and (key[1] != "-")}
                    opt = min(short_depth, key=short_depth.get)
                testcases, option_depths = symbolic_executor.option_depth(args.llvm_bc, time_budget, iteration_dir, f'"{opt}"', args.num_dash, option_depths, 0, args.gen_bout)
                long_depth = {key : value for key, value in option_depths.items() if ('-' * args.num_dash in key) and (key not in short_depth.keys())}
                if len(long_depth) > 0:
                    opt = min(long_depth, key=long_depth.get)
                    testcases, option_depths = symbolic_executor.option_depth(args.llvm_bc, time_budget, iteration_dir, f'"{opt}"', args.num_dash, option_depths, 0, args.gen_bout)

                with open(f"{str(os.getcwd())}/../data/option_depths/{args.program}.json", 'w') as json_depth:
                    json.dump(option_depths, json_depth, indent=4)
            start = time.time()

        # Collect result
        coverage = analyzer.evaluate(args.gcov_obj, testcases, bout_path, args.src_depth)
        total_coverage = total_coverage.union(coverage)
        elapsed = int(time.time() - start)
        
        if (len(with_short) <= 0) or os.path.exists(f"{str(os.getcwd())}/../data/option_depths/{args.program}.json"):
            coverages.append(len(coverage))
            if explore_flag >= args.explore_rate:
                seeder.save_seed(opt_arg, i, branches_opt, args.klee_replay, args.gcov)            
                opt_arg, sym_cmd, branches_opt, bout_path = sampler.sample(coverages, coverage, explore_flag, int(time.time() - iter_start), time_budget)
                seed_data = seeder.guide_seed(opt_arg, option_depths, args.klee_replay)
            else:
                opt_arg, sym_cmd, branches_opt, bout_path = sampler.sample(coverages, coverage, explore_flag, int(time.time() - iter_start), time_budget)

            print(f'[INFO] SCOPE : Iteration: {i} '
                            f'Iteration budget: {time_budget} '
                            f'Total budget: {args.budget} '
                            f'Time elapsed: {elapsed} '
                            f'Next option argument: {opt_arg} '
                            f'Coverage: {len(total_coverage)} ')
            with open(coverage_csv, 'a', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([elapsed, len(total_coverage), opt_arg])
            
            if explore_flag >= args.explore_rate:
                sym_cmd = f"{opt_arg} {sym_cmd}"
            i += 1
        else:
            os.system(f"rm -rf {iteration_dir}")

    report = ReportOB(args.program, args.gcov_obj, args.src_depth, original_path, args.num_dash, extractor, analyzer, args.klee_replay, args.gcov)
    print(f'[INFO] SCOPE : Testing done. Achieve {len(total_coverage)} coverage.')
