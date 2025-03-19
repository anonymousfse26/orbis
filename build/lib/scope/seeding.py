import copy
import os
import re
import random as rd
import subprocess as sp


class Seeder:
    def __init__(self, pgm, gcov_path, test_dir, depth, running_dir):
        self.running_dir = running_dir
        self.seed_data = dict()
        self.pgm = pgm
        self.depth = depth
        self.test_dir = test_dir
        self.tc_depths = []
        self.gcov_path = gcov_path[:gcov_path.rfind('/')]
        self.top_k = 10     # n_topk = 10

        self.gcov = gcov_path

    def save_seed(self, template, iteration, branches_opt):
        tc_data = []
        if os.path.exists(f"{self.test_dir}/iteration-{iteration}"):
            ktests = [f"{self.test_dir}/iteration-{iteration}/{f}" for f in os.listdir(f"{self.test_dir}/iteration-{iteration}") if f.endswith(".ktest")]
            for i in range(len(ktests)):
                tc = ktests[i]
                os.chdir(self.gcov_path)
                for _ in range(self.depth):
                    os.system("rm -f *.gcda")
                    os.system("rm -f *.gcov")
                    os.chdir("../")

                cmd = f"klee-replay {self.gcov_path}/{self.pgm} {tc}"
                process = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)

                try:
                    _, stderr = process.communicate(timeout=0.1)
                except sp.TimeoutExpired:
                    pass
                finally:
                    process.kill()
                
                os.chdir(self.gcov_path)
                gcdas = []
                for _ in range(self.depth):
                    gcdas += [os.path.abspath(f_gcda) for f_gcda in os.listdir(os.getcwd()) if f_gcda.endswith(".gcda")]
                    os.chdir("../")

                os.chdir(self.gcov_path)
                branch_datas = []
                for gcda in gcdas:
                    _ = sp.run(["gcov", "-b", gcda], capture_output=True, text=True).stdout
                
                cov = 0
                for file_name, lines in branches_opt.items():
                    if os.path.exists(f"{self.gcov_path}/{file_name}.gcov"):
                        if "gcal" in self.pgm:
                            with open(f"{self.gcov_path}/{file_name}.gcov", "r", encoding='latin-1') as gcov_file:
                                gcov_lines = [l.strip() for l in gcov_file.readlines()]
                        else:
                            with open(f"{self.gcov_path}/{file_name}.gcov", "r") as gcov_file:
                                gcov_lines = [l.strip() for l in gcov_file.readlines()]

                        for line in lines:
                            line_num = int(line)
                            try:
                                if ('branch' in gcov_lines[line_num]) and ('never' not in gcov_lines[line_num]) and ('taken 0%' not in gcov_lines[line_num]):
                                    cov += 1
                            except:
                                pass

                depth_log = tc.replace(".ktest", ".depth")
                try:
                    with open(depth_log, "r") as depth_file:
                        depth = int(depth_file.readline().strip())
                except:
                    depth = 0
                    
                tc_data.append([tc, cov])

            tc_data = sorted(tc_data, key=lambda x: x[1], reverse=True)
            tc_data = tc_data[:self.top_k]
            
            template_list = template.split()
            for temp in template_list:
                if temp in self.seed_data.keys():
                    tmp_seed = self.seed_data[temp] + tc_data
                    tmp_seed = sorted(tmp_seed, key=lambda x: x[1], reverse=True)
                    if len(tmp_seed) >= self.top_k:
                        tmp_seed = tmp_seed[:self.top_k]
                        self.seed_data[temp] = tmp_seed
                    else:
                        self.seed_data[temp] = tmp_seed
                else:
                    self.seed_data[temp] = tc_data
        

    def guide_seed(self, template, template_depths):
        template_list = template.split()
        candidates = copy.deepcopy({key : value for key, value in self.seed_data.items() if key in template_list})
        template_list = [t.strip('"') for t in template.split()]

        for key, values in candidates.items():
            for i in range(len(values)):
                if len(candidates[key][i]) < 4:
                    val = values[i]
                    replay_cmd = " ".join(["klee-replay", f"{self.gcov_path}/{self.pgm}", val[0]])
                    stderr_str = ""
                    
                    try:
                        result = sp.run(replay_cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True, check=True, timeout=1)
                        stderr_str = result.stderr.decode('latin-1')

                    except sp.TimeoutExpired:
                        pass

                    except sp.CalledProcessError as e:
                        pass

                    result_lines = [line for line in stderr_str.split("\n") if "Arguments:" in line]
                    if len(result_lines) > 0:
                        result = re.findall(r'"(.*?)"', result_lines[0])
                        valid = [res for res in result if res in template_depths.keys()]
                        candidates[key][i].append(sum([template_depths[t][0] for t in valid]))    # Valid depths
                        candidates[key][i].append(len(set(template_list).intersection(set(valid))))    # Arg similarity with option configuration
                    else:
                        candidates[key][i].append(-1)
                        candidates[key][i].append(-1)
        best_seed = dict()
        for key, value_list in candidates.items():
            try:
                min_similarity = min(value[-1] for value in value_list if value[-1] > 0)
                minimums = [value for value in value_list if value[-1] == min_similarity]
                best_seed[key] = rd.choice(minimums)
            except:
                pass

        os.chdir(self.running_dir)
        
        return best_seed