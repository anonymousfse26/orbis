import json
import os
import subprocess as sp


class ReportOB:
    def __init__(self, pgm, gcov_path, src_depth, output_dir, num_dash, extractor, analyzer, replay_bin="klee-replay", gcov_bin="gcov"):
        self.pgm = pgm
        self.gcov_path = gcov_path[:gcov_path.rfind('/')]
        self.src_depth = src_depth
        self.output_dir = output_dir
        self.final_calculation(extractor, analyzer, replay_bin, gcov_bin)

    def coverage(self, total_br, branches_opt):
        branch_lines = dict()
        cov_branch_opt = set()
        new_branches_opt = dict()

        if self.pgm in ["objcopy", "readelf", "objdump"]:
            branches_opt = {key : value for key, value in branches_opt.items() if self.pgm in key}

        for file_name, lines in branches_opt.items():
            if os.path.exists(f"{self.gcov_path}/{file_name}.gcov"):
                if self.pgm in ["gcal"]:
                    with open(f"{self.gcov_path}/{file_name}.gcov", "r", encoding='latin-1') as gcov_file:
                        gcov_lines = [l.strip() for l in gcov_file.readlines()]
                else:
                    with open(f"{self.gcov_path}/{file_name}.gcov", "r") as gcov_file:
                        gcov_lines = [l.strip() for l in gcov_file.readlines()]

                lines = sorted([int(l) for l in lines])
                for line in lines:
                    branch_lines[f"{file_name} {line}"] = set()
                    for g_line in gcov_lines:
                        content = [l.strip() for l in g_line.split(":")]
                        if len(content) >= 2:
                            try:
                                if line == int(content[1]):
                                    line_num = gcov_lines.index(g_line) + 1
                                    while (('branch' in gcov_lines[line_num]) and (":" not in gcov_lines[line_num]) and ("returned 0% blocks executed 0%" not in gcov_lines[line_num])):
                                        branch_lines[f"{file_name} {line}"].add(f"{file_name} {line_num}")
                                        if file_name not in new_branches_opt.keys():
                                            new_branches_opt[file_name] = [str(line_num)]
                                        else:
                                            new_branches_opt[file_name].append(str(line_num))
                                        if ('never' not in gcov_lines[line_num]) and ('taken 0%' not in gcov_lines[line_num]):
                                            cov_branch_opt.add(f'{file_name} {line_num}')
                                        line_num += 1
                                        if line_num == len(gcov_lines) - 1:
                                            break
                                    break
                                
                            except:
                                pass
        branch_lines = {key:value for key, value in branch_lines.items() if len(value) > 0}
        new_total_br = {key:set() for key in total_br.keys()}
        for key, values in total_br.items():
            for value in values:
                if value in branch_lines.keys():
                    new_total_br[key] = new_total_br[key].union(branch_lines[value])
        return new_total_br, cov_branch_opt.union(set(total_br.keys())), new_branches_opt


    def final_calculation(self, extractor, analyzer, replay_bin, gcov_bin):
        analyzer.clear_gcov(self.src_depth)
        iters = [f"{self.output_dir}/{d}" for d in os.listdir(self.output_dir) if d.startswith("iteration")]

        tcs = []
        for it in iters:
            tcs = tcs + [f"{it}/{f}" for f in os.listdir(it) if f.endswith(".ktest")]
            for tc in tcs:
                cmd = [replay_bin, f"{self.gcov_path}/{self.pgm}", str(tc)]
                cmd = ' '.join(cmd)
                process = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
                try:
                    _, stderr = process.communicate(timeout=0.1)
                except sp.TimeoutExpired:
                    pass
                finally:
                    process.kill()
                    
        src_dir = self.gcov_path
        for _ in range(self.src_depth):
            src_dir = src_dir[:src_dir.rfind('/')]

        gcdas = analyzer.find_all(src_dir, "gcda")

        root_dir = os.getcwd()
        os.chdir(self.gcov_path)
        for gcda in gcdas:
            cmd = [gcov_bin, "-b", str(gcda)]
            cmd = ' '.join(cmd)
            process = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
            try:
                _, stderr = process.communicate(timeout=0.1)
            except sp.TimeoutExpired:
                pass
            finally:
                process.kill()
        gcovs = analyzer.find_all(src_dir, "gcov")
        os.chdir(root_dir)

        if os.path.exists(f"{os.getcwd()}/../data/opt_branches/{self.pgm}.json"):
            with open(f"{os.getcwd()}/../data/opt_branches/{self.pgm}.json", 'r') as json_depth:
                option_data = json.load(json_depth)
                options = option_data["options"]
                total_br = {key : set(value) for key, value in option_data["total_br"].items()}
            branches_opt = {key : set() for key in os.listdir(extractor.src_path) if key.endswith(".c")}
            for value in total_br.values():
                for v in value:
                    lst = v.split()
                    branches_opt[lst[0]].add(lst[1])
            new_total_br, cov_branch_opt, new_branches_opt = self.coverage(total_br, branches_opt)
            union_set = set()
            for s in new_total_br.values():
                union_set = union_set.union(s)
            print(f"[INFO] SCOPE : Covered {len(cov_branch_opt)} option related branches.")
