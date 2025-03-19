import os
import re
import sys
import time

import random as rd
import subprocess as sp

from pathlib import Path


class GCov:
    def __init__(self, bin='gcov'):
        self.bin = bin


    def run(self, target, gcdas, folder_depth=1):
        if len(gcdas) == 0:
            return set()

        original_path = Path().absolute()
        target_dir = Path(target).parent
        gcdas = [gcda.absolute() for gcda in gcdas]
        os.chdir(str(target_dir))

        cmd = [str(self.bin), '-b', *list(map(str, gcdas))]
        cmd = ' '.join(cmd)
        _ = sp.run(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True, check=True)

        base = Path()
        for _ in range(folder_depth):
            if "gawk" in str(target) or "make" in str(target) or "sqlite" in str(target):
                pass
            else:
                base = base / '..'

        gcov_pattern = base / '**/*.gcov'
        gcovs = list(Path().glob(str(gcov_pattern)))

        covered = set()
        for gcov in gcovs:
            try:
                with gcov.open(encoding='UTF-8', errors='replace') as f:
                    file_name = f.readline().strip().split(':')[-1]
                    for i, line in enumerate(f):
                        if ('branch' in line) and ('never' not in line) and ('taken 0%' not in line) and (
                                ":" not in line) and ("returned 0% blocks executed 0%" not in line):
                            bid = f'{file_name} {i}'
                            covered.add(bid)
            except:
                pass

        os.chdir(str(original_path))
        return covered


class KLEE:
    def __init__(self, pgm, gcov_path, explore_rate, max_seed_depth, running_dir, init_args, bin='klee', replay_bin='klee-replay'):
        self.pgm = pgm
        self.init_max_depth = max_seed_depth
        self.init_args = init_args
        self.gcov_path = gcov_path
        self.explore_rate = explore_rate
        self.running_dir = running_dir
        self.bin = bin
        self.replay_bin = replay_bin
        self.time = []

        if os.path.exists(f"{running_dir}/seed_option_arguments/{self.pgm}.bout"):
            os.remove(f"{running_dir}/seed_option_arguments/{self.pgm}.bout")


    def seeding(self, target, budget, dir_path, opt_arg, seed_data, option_depths, min_seed_depth, max_seed_depth):
        opt_list = opt_arg.split()
        seed_list, seed_cmd, seed_depth, tmp = [], [], [], []
        best_seed = 0
        thresholds = []

        def count_dashes(s):
            count = 0
            for char in s:
                if char == '-':
                    count += 1
                else:
                    break
            return count

        tc_seeds, tc_seed_depths = [], []
        for opt in opt_list:
            refined = opt.strip('"')
            if refined in option_depths.keys():
                seed_depth.append(max(option_depths[refined]))
            
            if opt in seed_data.keys():
                if (seed_data[opt][0] not in seed_list):
                    seed_cmd.append(f"-seed-file={seed_data[opt][0]}")
                    tc_seeds.append(seed_data[opt][0])
                    tc_seed_depths.append(seed_data[opt][2])
                    seed_list.append(seed_data[opt][0])

        if (len(seed_depth) > 0) and (sum(seed_depth) > 0):
            if len(opt_list) <= 1:
                min_seed_depth = 0
                max_seed_depth = self.init_max_depth

            else:
                if rd.random() > self.explore_rate:
                    tmp = [abs(s) for s in seed_depth if abs(s) > 0]
                    if len(tmp) <= 1:
                        min_seed_depth = 0
                        max_seed_depth = self.init_max_depth
                    else:
                        min_seed_depth = option_depths['-' * count_dashes(opt_list[0].strip('"'))][0]
                        max_seed_depth = max(tc_seed_depths + [sum(tmp)])
                else:
                    min_seed_depth = 0
                    max_seed_depth = self.init_max_depth

        if os.path.exists(f"{self.running_dir}/seed_option_arguments/{self.pgm}.ktest"):
            seed_cmd.insert(0, f"-seed-file={self.running_dir}/seed_option_arguments/{self.pgm}.ktest")

        if len(seed_cmd) > 0:
            analyze_opts = f"{self.bin} -allow-seed-extension -allow-seed-truncation {' '.join(seed_cmd)} -seed-time={max(40, budget // 5)}s"
            if len(seed_depth) > 0:
                sym_cmd = " ".join([f"-sym-arg {len(t) - 2}" for t in opt_list])
                sym_cmd = f'{" ".join(opt_list)} {sym_cmd}'
            else:
                sym_cmd = self.init_args
        else:
            analyze_opts = f"{self.bin}"
            sym_cmd = self.init_args

        return analyze_opts, min_seed_depth, max_seed_depth, sym_cmd


    def option_depth(self, target, budget, dir_path, option, num_dash, depth_data, flag, gen_bout="gen-bout"):
        target = Path(target).absolute()
        original_path = Path().absolute()
        output_dir = Path(dir_path).absolute()
        dir_path = f"{str(original_path)}/{dir_path}"
        os.chdir(str(target.parent))

        seeding_cmd = f"{gen_bout} {option} --bout-file {self.running_dir}/seed_option_arguments/{self.pgm}.ktest"
        os.system(seeding_cmd)
        start = time.time()
        cmd = " ".join([f"{self.bin}", f"-seed-file={self.running_dir}/seed_option_arguments/{self.pgm}.ktest", f"-output-dir={dir_path}", "-only-seed", 
                            "-simplify-sym-indices", "-write-depth-info", "-output-module", "-max-memory=1000", 
                            "-disable-inlining", "-optimize", "-libc=uclibc", "-posix-runtime", "-seed-time=360s",
                            "-external-calls=all", "-max-sym-array-size=4096",
                            "-max-time=360", "-watchdog", "-max-memory-inhibit=false", "-switch-type=internal", "-use-batching-search", "-batch-instructions=10000", 
                            str(target), f"-sym-arg {len(option) - 2}"])
        try:
            result = sp.run(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True, check=True, timeout=int(1.25*budget))
        except sp.TimeoutExpired:
            print('[WARNING] SCOPE : KLEE exceeded the time budget. Iteration terminated.')
        except sp.CalledProcessError as e:
            stderr = e.stderr.decode(errors='replace')
            lastline = stderr.strip().splitlines()[-1]
            if 'KLEE' in lastline and 'kill(9)' in lastline:
                print(f'[WARNING] SCOPE : KLEE process kill(9)ed. Failed to terminate nicely.')
            else:                
                print(f'[WARNING] SCOPE : Fail({e.returncode})ed to execute KLEE.')

        option = option.strip('"').strip("'")
        self.time.append(round(time.time() - start, 4))
        depth_files = [f"{output_dir}/{f}" for f in os.listdir(output_dir) if f.endswith(".depth")]
        halted = dict()
        for df in depth_files:
            with open(df, "r") as depth_f:
                depth = depth_f.readline().strip()
                try:
                    halted[df.replace(".depth", ".ktest")] = int(depth)
                except:
                    pass
        
        if len(halted) > 0:
            halted = dict(sorted(halted.items(), key=lambda item: item[1]))
            depth_data[option] = [max(list(halted.values()))]
            for key, value in halted.items():
                replay_cmd = " ".join([self.replay_bin, self.gcov_path, key])
                stderr_str = ""
                
                try:
                    result = sp.run(replay_cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True, check=True, timeout=1)
                    stderr_str = result.stderr.decode('latin-1')
                except sp.TimeoutExpired:
                    pass
                except sp.CalledProcessError as e:
                    stderr = e.stderr.decode(errors='replace')
                    lastline = stderr.strip().splitlines()[-1]
                    if 'KLEE' in lastline and 'kill(9)' in lastline:
                        print(f'[WARNING] SCOPE : KLEE process kill(9)ed. Failed to terminate nicely.')
                    else:                
                        print(f'[WARNING] SCOPE : Fail({e.returncode})ed to execute KLEE.')

                result_lines = [line for line in stderr_str.split("\n") if "Arguments:" in line]
                if len(result_lines) > 0:
                    result = re.findall(r'"(.*?)"', result_lines[0])[1]
                    result = result.strip()
                    if len(result.strip()) > 0:
                        if (result[0] == "-"):
                            if ("-" not in depth_data.keys()):
                                depth_data["-"] = [value]
                            elif (depth_data["-"][0] > value):
                                depth_data["-"] = [value]
                    if (len(result.strip()) > 1) and (num_dash > 1):
                        if (result[0] == "-") and (result[1] == "-"):
                            if ("-" * num_dash not in depth_data.keys()):
                                depth_data["-" * num_dash] = [value]
                            elif (depth_data["-" * num_dash][0] > value):
                                depth_data["-" * num_dash] = [value]
        else:            
            depth_data[option] = [0]

        os.system(f"rm -f {self.running_dir}/seed_option_arguments/{self.pgm}.ktest")
        testcases = list(output_dir.glob('*.ktest'))
        testcases = [tc.absolute() for tc in testcases] + [Path(f"{self.running_dir}/seed_option_arguments/{self.pgm}.ktest").absolute()]
        os.chdir(str(original_path))

        return testcases, depth_data


    def run(self, target, budget, dir_path, opt_arg, seed_data, option_depths, min_seed_depth, max_seed_depth, **kwargs):
        target = Path(target).absolute()
        original_path = Path().absolute()
        output_dir = Path(dir_path).absolute()
        dir_path = f"{str(original_path)}/{dir_path}"
        os.chdir(str(target.parent))

        analyze_opts, min_seed_depth, max_seed_depth, sym_args = self.seeding(target, budget, dir_path, opt_arg, seed_data, option_depths, min_seed_depth, max_seed_depth)
        cmd = " ".join([analyze_opts, "-write-depth-info", f"-min-seed-depth={min_seed_depth}", f"-max-seed-depth={max_seed_depth}", f"-output-dir={dir_path}", "-simplify-sym-indices", "-write-cvcs", "-write-cov", "-output-module", "-max-memory=1000", 
                                "-disable-inlining", "-optimize", "-use-forked-solver", "-use-cex-cache", "-libc=uclibc", "-posix-runtime",
                                "-external-calls=all", "-only-output-states-covering-new", "-max-sym-array-size=4096", "-max-solver-time=30s", f"-max-time={budget}", 
                                "-watchdog", "-max-memory-inhibit=false","-max-static-fork-pct=1", "-max-static-solve-pct=1", "-max-static-cpfork-pct=1", "-switch-type=internal", 
                                "-search=random-path -search=nurs:covnew", "-use-batching-search", "-batch-instructions=10000", 
                                str(target), sym_args, "-sym-files 1 8", "-sym-stdin 8", "-sym-stdout"])
        try:
            result = sp.run(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True, check=True, timeout=int(1.25*budget))

        except sp.TimeoutExpired:
            print('[WARNING] SCOPE : KLEE exceeded the time budget. Iteration terminated.')

        except sp.CalledProcessError as e:
            stderr = e.stderr.decode(errors='replace')
            lastline = stderr.strip().splitlines()[-1]
            if 'KLEE' in lastline and 'kill(9)' in lastline:
                print(f'[WARNING] SCOPE : KLEE process kill(9)ed. Failed to terminate nicely.')
            else:                
                print(f'[WARNING] SCOPE : Fail({e.returncode})ed to execute KLEE.')

        testcases = list(output_dir.glob('*.ktest'))
        testcases = [tc.absolute() for tc in testcases]

        os.chdir(str(original_path))

        return testcases, min_seed_depth, max_seed_depth


class KLEEReplay:
    def __init__(self, bin='klee-replay'):
        self.bin = bin

    def run(self, target, testcases, bout_path, error_type=None, folder_depth=1):
        errors = set()
        target = Path(target).absolute()
        original_path = Path().absolute()
        for testcase in testcases:
            testcase = Path(testcase).absolute()
            os.chdir(str(target.parent))

            cmd = [str(self.bin), str(target), str(testcase)]
            cmd = ' '.join(cmd)
            process = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)

            try:
                _, stderr = process.communicate(timeout=0.1)
            except sp.TimeoutExpired:
                print(f'[WARNING] SCOPE : KLEE replay timeout: {testcase}')
            finally:
                process.kill()

        base = Path()
        for _ in range(folder_depth):
            base = base / '..'
        gcda_pattern = base / '**/*.gcda'
        gcdas = list(target.parent.glob(str(gcda_pattern)))
        gcdas = [gcda.absolute() for gcda in gcdas]

        os.chdir(str(original_path))
        return gcdas


class KLEEAnalyze:
    def __init__(self, init_budget, gcov_path, klee_replay=None, gcov=None):
        if klee_replay is None:
            klee_replay = KLEEReplay()
        elif isinstance(klee_replay, str):
            klee_replay = KLEEReplay(klee_replay)
        self.klee_replay = klee_replay
        if gcov is None:
            gcov = GCov()
        elif isinstance(gcov, str):
            gcov = GCov(gcov)
        self.gcov = gcov
        self.gcov_path = gcov_path[:gcov_path.rfind('/')]
        self.budget = init_budget

    def evaluate(self, target, testcases, bout_path, folder_depth=1):
        base = Path(target).parent
        # Run symbolic executor
        for _ in range(folder_depth):
            base = base / '..'
        cmd = ['rm', '-f', str(base / '**/*.gcda'), str(base / '**/*.gcov')]
        cmd = ' '.join(cmd)
        _ = sp.run(cmd, shell=True, check=True)
        # Replay test-cases generated by the symbolic executor
        gcdas = self.klee_replay.run(target, testcases, bout_path,
                                             folder_depth=folder_depth)
        # Extract the set of branches covered by the generated test-cases
        branches = self.gcov.run(target, gcdas, folder_depth=folder_depth)
        return branches


    def budget_handler(self, elapsed, total_budget, coverage, flag, iteration, n_options):
        if (flag) and (iteration % n_options == n_options - 1):
            # Increase the budget to explore more diverse paths
            self.budget = self.budget * 2
            
        if ((total_budget - elapsed) >= self.budget):
            return self.budget
        else:
            # Adjust the budget to the remaining time if the iteration budget exceeds the remaining time
            return total_budget - elapsed

    def find_all(self, path, ends):
        # Search for files in the current directory and all sub-directories
        found = []
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith(f'.{ends}'):
                    found.append(os.path.join(root, file))
        return found

    def clear_gcov(self, depth):
        # Initialize ".gcda" and ".gcov" files
        g_path = self.gcov_path
        for _ in range(depth):
            g_path = g_path[:g_path.rfind('/')]
        gcdas = self.find_all(g_path, "gcda")
        gcovs = self.find_all(g_path, "gcov")
        for gcda in gcdas:
            os.system(f"rm -f {gcda}")
        for gcov in gcovs:
            os.system(f"rm -f {gcov}")