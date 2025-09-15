'''Module that defines console script entries

This module that defines consol script entries. This module includes console script entry
for SymTuner for KLEE.
'''

from pathlib import Path
import argparse
import json
import os
import shutil
import sys

import subprocess as sp

from symtuner.klee import KLEE
from symtuner.klee import KLEESymTuner
from symtuner.logger import get_logger
from symtuner.symtuner import TimeBudgetHandler

from scope.extract import Extractor
from scope.sample import Sampler
from scope.guide import Guider


def main(argv=None):
    '''Main entry for console script for SymTuner for KLEE

    Main entry for consol script for SymTuner for KLEE.

    Args:
        argv: A list of arguments. By default, use the system arguments except for
            the first element.
    '''

    if argv == None:
        argv = sys.argv[1:]

    # Commandline argument parser
    parser = argparse.ArgumentParser()

    # Executable settings
    executable = parser.add_argument_group('executable settings')
    executable.add_argument('--klee', default=f'{str(os.getcwd())}/../engine/klee/build/bin/klee', type=str,
                            help='Path to "klee" executable (default=klee)')
    executable.add_argument('--klee-replay', default=f'{str(os.getcwd())}/../engine/klee/build/bin/klee-replay', type=str,
                            help='Path to "klee-replay" executable (default=klee-replay)')
    executable.add_argument('--gen-bout', default=f'{str(os.getcwd())}/../engine/klee/build/bin/gen-bout', type=str,
                            help='Path to "gen-bout" executable (default=gen-bout)')
    executable.add_argument('--gcov', default='gcov', type=str,
                            help='Path to "gcov" executable (default=gcov)')

    # Hyperparameters
    hyperparameters = parser.add_argument_group('hyperparameters')
    hyperparameters.add_argument('-s', '--search-space', default=None, type=str, metavar='JSON',
                                 help='Json file defining parameter search space')
    hyperparameters.add_argument('--exploit-portion', default=0.7, type=float, metavar='FLOAT',
                                 help='Portion of exploitation in SymTuner (default=0.7)')
    hyperparameters.add_argument('--step', default=20, type=int, metavar='INT',
                                 help='The number of symbolic execution runs before increasing small budget (default=20)')
    hyperparameters.add_argument('--minimum-time-portion', default=0.005, type=float, metavar='FLOAT',
                                 help='Minimum portion for one iteration (default=0.005)')
    hyperparameters.add_argument('--increase-ratio', default=2, type=float, metavar='FLOAT',
                                 help='A number that is multiplied to increase small budget. (default=2)')
    hyperparameters.add_argument('--minimum-time-budget', default=120, type=int, metavar='INT',
                                 help='Minimum time budget to perform symbolic execution (default=30)')
    hyperparameters.add_argument('--exploration-steps', default=20, type=int, metavar='INT',
                                 help='The number of symbolic execution runs that SymTuner focuses only on exploration (default=20)')

    # Others
    parser.add_argument('-d', '--output-dir', default='symtuner-out', type=str,
                        help='Directory to store the generated files (default=symtuner-out)')
    parser.add_argument('--generate-search-space-json', action='store_true',
                        help='Generate the json file defining parameter spaces used in our ICSE\'22 paper')
    parser.add_argument('--debug', action='store_true',
                        help='Log the debug messages')
    parser.add_argument('--gcov-depth', default=1, type=int,
                        help='Depth to search for gcda and gcov files from gcov_obj to calculate code coverage (default=1)')

    # Required arguments
    required = parser.add_argument_group('required arguments')
    required.add_argument('-t', '--budget', default=None, type=int, metavar='INT',
                          help='Total time budget in seconds')
    required.add_argument('-p', '--program', default=None, type=str, metavar='STR',
                          help='Name of program to test. Write both name and version. (e.g., grep-3.4)')
    required.add_argument('llvm_bc', nargs='?', default=None,
                          help='LLVM bitecode file for klee')
    required.add_argument('gcov_obj', nargs='?', default=None,
                          help='Executable with gcov support')
    args = parser.parse_args(argv)


    if args.debug:
        get_logger().setLevel('DEBUG')

    if args.generate_search_space_json:
        space_json = KLEESymTuner.get_default_space_json()
        with Path('example-space.json').open('w') as stream:
            json.dump(space_json, stream, indent=4)
            get_logger().info('Example space configuration json is generated: example-space.json')
        sys.exit(0)

    if args.llvm_bc is None or args.gcov_obj is None or args.budget is None:
        parser.print_usage()
        print('following parameters are required: -t, llvm_bc, gcov_obj')
        sys.exit(1)

    output_dir = Path(args.output_dir)
    if output_dir.exists():
        shutil.rmtree(str(output_dir))
        get_logger().warning('Existing output directory is deleted: '
                             f'{output_dir}')
    output_dir.mkdir(parents=True)
    coverage_csv = output_dir / 'coverage.csv'
    coverage_csv.touch()
    get_logger().info(
        f'Coverage will be recoreded at "{coverage_csv}" at every iteration.')
    found_bugs_txt = output_dir / 'found_bugs.txt'
    found_bugs_txt.touch()
    get_logger().info(
        f'Found bugs will be recoreded at "{found_bugs_txt}" at every iteration.')

    # Initialize Symbolic Executor
    symbolic_executor = KLEE(args.klee)

    # Initialize ORBiS
    extractor = Extractor(args.program, os.getcwd(), args.output_dir, args.llvm_bc, args.klee, args.gen_bout)
    sampler = Sampler(args.program, os.getcwd(), args.output_dir)
    guider = Guider(args.program, os.getcwd(), args.output_dir, 10)

    new_arg = list()
    total_coverage = set()
    seeds = list()


    # Initialize SymTuner
    symtuner = KLEESymTuner(args.klee_replay, args.gcov, 10,
                            args.search_space, args.exploit_portion)
    evaluation_argument = {'folder_depth': args.gcov_depth}

    # Do until timeout
    get_logger().info('All configuration loaded. Start testing.')
    time_budget_handler = TimeBudgetHandler(args.budget, args.minimum_time_portion,
                                            args.step, args.increase_ratio,
                                            args.minimum_time_budget)
    for i, time_budget in enumerate(time_budget_handler):

        iteration_dir = output_dir / f'iteration-{i}'

        # Sample parameters
        policy = 'explore' if i < args.exploration_steps else None
        parameters = symtuner.sample(policy=policy)

        # Run symbolic executor
        parameters[symbolic_executor.get_time_parameter()] = time_budget
        parameters['-output-dir'] = str(iteration_dir)
        testcases, runtime = symbolic_executor.run(args.llvm_bc, parameters, seeds, new_arg, f"/home/minjong/symtuner/benchmarks/{args.output_dir}", args.program, time_budget)

        # Collect result
        symtuner.add(args.gcov_obj, parameters, testcases, evaluation_argument)

        elapsed = time_budget_handler.elapsed
        coverage, bugs = symtuner.get_coverage_and_bugs()
        print(len(coverage))
        get_logger().info(f'Iteration: {i + 1} '
                          f'Time budget: {time_budget} '
                          f'Time elapsed: {elapsed} '
                          f'Coverage: {len(coverage)} '
                          f'Bugs: {len(bugs)}')
        with coverage_csv.open('a') as stream:
            stream.write(f'{elapsed}, {len(coverage)}\n')
        with found_bugs_txt.open('w') as stream:
            stream.writelines((f'Testcase: {Path(symtuner.get_testcase_causing_bug(bug)).absolute()} '
                               f'Bug: {bug}\n' for bug in bugs))
        
        sampler.update(coverage, new_arg, runtime, time_budget)
        guider.save(new_arg, i)

        new_arg = sampler.sample()
        seeds = guider.guide(new_arg, args.gen_bout)

        find_pgm_command = f"ps -u minjong -o pid,time,comm | grep {args.program}"
        kill_pgm_command = "awk '$2 > \"00:00:10\" {print $1}' | xargs kill"
        _ = sp.run(f"{find_pgm_command} | {kill_pgm_command}", shell=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        symtuner.kill_tmp()

    coverage, bugs = symtuner.get_coverage_and_bugs()
    get_logger().info(f'SymTuner done. Achieve {len(coverage)} coverage '
                      f'and found {len(bugs)} bugs.')
