import os
import glob
import time

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
    def __init__(self, init_args, bin='klee'):
        self.init_args = init_args
        self.bin = bin

    def run(self, target, budget, dir_path, sym_args, arguments, test_dir, pgm, seeds, **kwargs):
        target = Path(target).absolute()
        original_path = Path().absolute()
        output_dir = Path(dir_path).absolute()
        dir_path = f"{str(original_path)}/{dir_path}"
        os.chdir(str(target.parent))

        if len(arguments) > 0:
            sym_args = ""
            whole_argument = " ".join(arguments).split()
            for arg in whole_argument:
                sym_args = f"{sym_args} -sym-arg {len(arg)}".lstrip()

        if len(seeds) > 0:
            seed_cmd = ""
            for seed in seeds:
                seed_cmd = f"{seed_cmd} -seed-file={seed}".lstrip()
            cmd = " ".join([self.bin, seed_cmd, "-allow-seed-extension", "-allow-seed-truncation", f"-seed-time={budget // 4}",  f"-arg-score-file={test_dir}/{pgm}.score",
                            f"-output-dir={dir_path}", "-simplify-sym-indices", "-output-module", "-max-memory=1000", "-only-output-states-covering-new" 
                            "-disable-inlining", "-optimize", "-use-forked-solver", "-use-cex-cache", "-libc=uclibc", "-posix-runtime",
                            "-external-calls=all", "-max-sym-array-size=4096", "-max-solver-time=30s", f"-max-time={budget}", 
                            "-watchdog", "-max-memory-inhibit=false","-max-static-fork-pct=1", "-max-static-solve-pct=1", "-max-static-cpfork-pct=1", "-switch-type=internal", 
                            "-search=random-path -search=nurs:covnew", "-use-batching-search", "-batch-instructions=10000", 
                            str(target), " ".join(arguments), sym_args, "-sym-files 1 8", "-sym-stdin 8", "-sym-stdout"])
        else:
            cmd = " ".join([self.bin, f"-output-dir={dir_path}", "-simplify-sym-indices", "-output-module", "-max-memory=1000", f"-arg-score-file={test_dir}/{pgm}.score",
                            "-disable-inlining", "-optimize", "-use-forked-solver", "-use-cex-cache", "-libc=uclibc", "-posix-runtime", "-only-output-states-covering-new", 
                            "-external-calls=all", "-max-sym-array-size=4096", "-max-solver-time=30s", f"-max-time={budget}", 
                            "-watchdog", "-max-memory-inhibit=false","-max-static-fork-pct=1", "-max-static-solve-pct=1", "-max-static-cpfork-pct=1", "-switch-type=internal", 
                            "-search=random-path -search=nurs:covnew", "-use-batching-search", "-batch-instructions=10000", 
                            str(target), " ".join(arguments), sym_args, "-sym-files 1 8", "-sym-stdin 8", "-sym-stdout"])
        start = time.time()
        needs_bash = any(sym in cmd for sym in ("<(", ">(", "$(", "|", ">", "<", "`"))
        if needs_bash:
            try:
                result = sp.run(["/bin/bash", "-lc", cmd], stdout=sp.PIPE, stderr=sp.PIPE, check=True, timeout=int(1.25 * budget))
            except sp.TimeoutExpired:
                print('[WARNING] SCOPE : KLEE exceeded the time budget. Iteration terminated.')
            except sp.CalledProcessError as e:
                stderr = e.stderr.decode(errors='replace')
                lastline = stderr.strip().splitlines()[-1]
                if 'KLEE' in lastline and 'kill(9)' in lastline:
                    print(f'[WARNING] SCOPE : KLEE process kill(9)ed. Failed to terminate nicely.')
                else:                
                    print(f'[WARNING] SCOPE : Fail({e.returncode})ed to execute KLEE.')
        else:
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
        elapsed = int(time.time() - start)
        testcases = list(output_dir.glob('*.ktest'))
        testcases = [tc.absolute() for tc in testcases]

        os.chdir(str(original_path))

        return testcases, elapsed


class KLEEReplay:
    def __init__(self, bin='klee-replay'):
        self.bin = bin

    def run(self, target, testcases, error_type=None, folder_depth=1):
        errors = set()
        target = Path(target).absolute()
        original_path = Path().absolute()
        for testcase in testcases:
            testcase = Path(testcase).absolute()
            os.chdir(str(target.parent))
            cmds = []
            # cmds.append([str(self.bin), str(target), str(testcase), "--insert-symfiles-argv=after", "--drop-empty-args"])
            # cmds.append([str(self.bin), str(target), str(testcase), "--insert-symfiles-argv=before", "--drop-empty-args"])
            # cmds.append([str(self.bin), str(target), str(testcase), "--insert-symfiles-argv=after"])
            # cmds.append([str(self.bin), str(target), str(testcase), "--insert-symfiles-argv=before"])
            cmds.append([str(self.bin), str(target), str(testcase)])

            for cmd in cmds:
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

    def evaluate(self, target, testcases, folder_depth=1):
        base = Path(target).parent
        # Run symbolic executor
        for _ in range(folder_depth):
            base = base / '..'
        cmd = ['rm', '-f', str(base / '**/*.gcda'), str(base / '**/*.gcov')]
        cmd = ' '.join(cmd)
        _ = sp.run(cmd, shell=True, check=True)
        # Replay test-cases generated by the symbolic executor
        gcdas = self.klee_replay.run(target, testcases, folder_depth=folder_depth)
        # Extract the set of branches covered by the generated test-cases
        branches = self.gcov.run(target, gcdas, folder_depth=folder_depth)
        return branches


    def budget_handler(self, elapsed, total_budget, coverage, iteration, options):
        if iteration % len(options) == len(options) - 1:
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

    
    def kill_tmp(self, mypass="1234"):
        target_dir = "/tmp"
        patterns = [
            "klee-replay-[0-9A-Za-z]*",
            "gcal[0-9A-Za-z]*",
            "klee-symfiles-[0-9A-Za-z]*",
            "pyright-[0-9A-Za-z]*",
        ]

        paths = []
        for pat in patterns:
            paths.extend(glob.glob(os.path.join(target_dir, pat)))

        if paths:
            for path in paths:
                sp.run(["sudo", "-S", "rm", "-rf", path], input=mypass + "\n", universal_newlines=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL, check=True)
                # sp.run(["rm", "-rf", *paths], input=mypass + "\n", universal_newlines=True)
