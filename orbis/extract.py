import json
import os
import shutil
import subprocess as sp



class Extractor:
    def __init__(self, pgm, running_dir, test_dir, target, klee_bin, bout_bin):
        with open(f"{running_dir}/../data/option_dict/{pgm}.dict", "r") as option_dict:
            self.options = [line.strip() for line in option_dict.readlines() if line[0] != "#"]
        self.pgm = pgm
        self.running_dir = running_dir
        self.test_dir = f"{running_dir}/{test_dir}"
        if not os.path.exists(f"{running_dir}/../data/constraints/{pgm}.json"):
            print("[INFO] ORBiS : Start extracting each option's cosntraints.")
            self.extract_option_constraints(target, klee_bin, bout_bin)

    
    def extract_option_constraints(self, target, klee_bin, bout_bin, budget=60):
        const_data = dict()
        for option in self.options:
            print(f"[INFO] ORBiS : Extracting cosntraints of option {option}.")
            bout_cmd = f'{bout_bin} "{option}" --bout-file {self.test_dir}/option_seed.ktest'
            os.system(bout_cmd)

            arguments = option.split()
            arg_cmd = ""
            for arg in arguments:
                arg_cmd = f"{arg_cmd} -sym-arg {len(arg)}".lstrip()
            cmd = " ".join([klee_bin, f"-output-dir={self.test_dir}/test", f"-seed-file={self.test_dir}/option_seed.ktest", 
                            "-allow-seed-extension", "-allow-seed-truncation", "-simplify-sym-indices", "-output-module", 
                            "-max-memory=1000", "-only-seed", "-disable-inlining", "-optimize", "-use-forked-solver", 
                            "-use-cex-cache", "-libc=uclibc", "-posix-runtime", f"-seed-time={budget}", "-external-calls=all", 
                            "-only-output-states-covering-new", "-max-sym-array-size=4096", "-max-solver-time=30s", f"-max-time={budget}",
                            "-watchdog", "-max-memory-inhibit=false","-max-static-fork-pct=1", "-max-static-solve-pct=1", "-max-static-cpfork-pct=1", 
                            "-switch-type=internal", "-search=random-path -search=nurs:covnew", "-use-batching-search", "-batch-instructions=10000", 
                            str(target), arg_cmd, "-sym-stdin 8", "-sym-stdout"])
            try:
                result = sp.run(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True, check=True, timeout=int(1.25*budget))

            except sp.TimeoutExpired:
                print('[WARNING] ORBiS : KLEE exceeded the time budget. Iteration terminated.')

            except sp.CalledProcessError as e:
                stderr = e.stderr.decode(errors='replace')
                lastline = stderr.strip().splitlines()[-1]
                if 'KLEE' in lastline and 'kill(9)' in lastline:
                    print(f'[WARNING] ORBiS : KLEE process kill(9)ed. Failed to terminate nicely.')
                else:                
                    print(f'[WARNING] ORBiS : Fail({e.returncode})ed to execute KLEE.')

            constraints = [f"{self.test_dir}/test/{f}" for f in os.listdir(f"{self.test_dir}/test") if f.endswith(".const")]
            option_consts = set()
            for constraint in constraints:
                with open(constraint, "r") as const_f:
                    const_list = [line.strip() for line in const_f.readlines()][0]
                    const_list = eval(const_list)
                option_consts = option_consts.union(set(const_list))
            const_data[option] = list(option_consts)
            shutil.rmtree(f"{self.test_dir}/test")

        with open(f"{self.running_dir}/../data/constraints/{self.pgm}.json", "w", encoding="utf-8") as f:
            json.dump(const_data, f, ensure_ascii=False, indent=4)
