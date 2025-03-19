import os
import copy

import numpy as np
import random as rd

from sklearn.preprocessing import MinMaxScaler


class Sampler:
    def __init__(self, pgm, running_dir, gcov_path, options, total_br, branches_opt, explore_rate, num_dash):
        self.pgm = pgm
        self.running_dir = running_dir
        self.gcov_path = gcov_path[:gcov_path.rfind("/")]

        self.options = options
        self.explore_rate = explore_rate
        self.total_br = total_br
        self.branches_opt = branches_opt
        self.num_dash = num_dash

        self.oc_flag = 0
        self.covered_branches = {key:set() for key in self.options.keys()}
        self.bro_coverage = {key:[] for key in self.options.keys()}
        self.opt_count = {key:0 for key in self.options.keys()}
        self.uncov_portion = {key:0 for key in self.options.keys()}

        self.have_short = dict()
        for opt, vars in self.options.items():
            for var in vars:
                var = var.strip("'").strip('"')
                if len(var) == 1:
                    self.have_short[opt] = var
        self.short_probability = {key : [[], []] for key in self.have_short.keys()}
        self.changed = {key : None for key in self.have_short.keys()}

        self.prev_opt_arg = list()
        self.bad_count = dict()


    def coverage(self):
        # Measure option-related branch coverage
        branch_lines = dict()
        covered_opt_branch = set()
        new_branches_opt = dict()

        for file_name, lines in self.branches_opt.items():
            if os.path.exists(f"{self.gcov_path}/{file_name}.gcov"):
                if "gcal" in self.pgm:
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
                                            covered_opt_branch.add(f'{file_name} {line_num}')
                                        line_num += 1
                                        if line_num == len(gcov_lines) - 1:
                                            break
                                    break
                            except:
                                pass
        
        branch_lines = {key:value for key, value in branch_lines.items() if len(value) > 0}
        new_total_br = {key:set() for key in self.total_br.keys()}
        for key, values in self.total_br.items():
            for value in values:
                if value in branch_lines.keys():
                    new_total_br[key] = new_total_br[key].union(branch_lines[value])

        return new_total_br, covered_opt_branch, new_branches_opt


    def normalizing(self, data):
        # Function to normalize each feature value used for scoring option arguments
        values = np.array(list(data.values())).reshape(-1, 1)
        scaler = MinMaxScaler()
        normalized_values = scaler.fit_transform(values)
        normalized_data = {key: float(normalized_value) for key, normalized_value in zip(data.keys(), normalized_values)}
        return normalized_data

    
    def change_form(self, opt_list, coverage):
        for key, value in self.changed.items():
            if coverage > 0:
                if value == True:
                    self.short_probability[key][0].append(coverage)
                elif value == False:
                    self.short_probability[key][1].append(coverage)

        self.changed = {key : None for key in self.have_short.keys()}
        original_opt = dict()
        for i in range(len(opt_list)):
            if (opt_list[i] in self.have_short.keys()):
                # When both long and short options are defined
                if (len(self.short_probability[opt_list[i]][0]) + len(self.short_probability[opt_list[i]][1])) < len(self.options):
                    # If a short or long option has not been tried
                    if len(self.short_probability[opt_list[i]][1]) == 0:
                        prob = 0
                    elif len(self.short_probability[opt_list[i]][0]) == 0:
                        prob = 1
                    else:
                        prob = 0.5
                else:
                    # Set probabilities for selecting long/short options based on accumulated data
                    yes_avg = sum(self.short_probability[opt_list[i]][0]) / len(self.short_probability[opt_list[i]][0])
                    no_avg = sum(self.short_probability[opt_list[i]][1]) / len(self.short_probability[opt_list[i]][1])
                    prob = yes_avg / (yes_avg + no_avg)

                # Probabilistically select either the long or short form
                if rd.random() < prob:
                    short = self.have_short[opt_list[i]]
                    self.changed[opt_list[i]] = True
                    opt_form = f'"-{short}"'
                    original_opt[opt_form] = f'{"-" * self.num_dash}{opt_list[i]}'
                    opt_list[i] = opt_form
                else:
                    self.changed[opt_list[i]] = False
                    opt_list[i] = f'"{"-" * self.num_dash}{opt_list[i].strip("-")}"'
            else:
                # Use the long option
                if len(opt_list[i].strip("-")) == 1:
                    opt_list[i] = f'"-{opt_list[i].strip("-")}"'
                else:    
                    opt_list[i] = f'"{"-" * self.num_dash}{opt_list[i].strip("-")}"'
        return opt_list, original_opt


    def select_arguments(self, candidates, weights, k=2):
        selected = []
        for _ in range(k):
            # Probabilistically select arguments Based on weights.
            best = rd.choices(candidates, weights=weights, k=1)[0]
            selected.append(best)
            # Prevent the same argument from being selected multiple times.
            index = candidates.index(best)
            candidates.pop(index)
            weights.pop(index)
        return selected


    def option_argument(self, coverages, portion, elapsed, budget, brancho):
        worst_opts = dict()
        if (portion >= self.explore_rate):
            if (elapsed < budget * 0.5):
                for prev_opt in self.prev_opt_arg:
                    if prev_opt in self.bad_count.keys():
                        self.bad_count[prev_opt] += 1
                    else:
                        self.bad_count[prev_opt] = 1
            try:
                q3 = np.percentile(list(self.bad_count.values()), 75)
            except:
                q3 = 0
            worst_opts = {k: v for k, v in self.bad_count.items() if v > q3 and v >= 10}
        
        not_used = [x for x in self.opt_count.keys() if self.opt_count[x] <= 0]
        if len(not_used) > 0:
            # Try each option as an option argument to accumulate data
            opt_list = rd.sample(not_used, 1)
        else:
            # Score option arguments based on data
            if not self.oc_flag:
                self.oc_flag = 1
            low_count = dict()
            for key, value in self.opt_count.items():
                if value > 0:
                    low_count[key] = round(1 / value, 4)
                else:
                    low_count[key] = value

            bro_score = {key:sum(value) // len(value) for key, value in self.bro_coverage.items()}
            self.uncov_portion = {key:value for key, value in self.uncov_portion.items() if len(set(key.split())) == len(key.split())}
            low_count = {key:value for key, value in low_count.items() if len(set(key.split())) == len(key.split())}
            bro_score = {key:value for key, value in bro_score.items() if len(set(key.split())) == len(key.split())}

            norm_uncov_portion = {key:value for key, value in self.normalizing(self.uncov_portion).items() if (len(key) > 0) and (key != "")}
            norm_opt_covered_branches = self.normalizing(self.opt_covered_branches)
            norm_low_count = self.normalizing(low_count)
            norm_low_count = {key:value for key, value in norm_low_count.items() if len(key) > 0}
            norm_bro_score = self.normalizing(bro_score)
            norm_bro_score = {key:value for key, value in norm_bro_score.items() if len(key) > 0}

            self.uncov_portion = {key:value for key, value in self.uncov_portion.items() if (len(key) > 0) and (key != "")}

            score = {key : (round((norm_uncov_portion[key] + norm_low_count[key] + norm_bro_score[key]) / len(key.split()), 4)) for key in self.uncov_portion.keys() if (len(set(key.split()).intersection(set(worst_opts.keys()))) == 0)}
            score_list = sorted(score.items(), key=lambda item: item[1], reverse=True)

            if rd.random() >= self.explore_rate:
                # Generate an efficient option argument based on data
                opt_list = self.select_arguments(list(score.keys()), list(score.values()))
            else:
                # Generates option argument Randomly.
                opt_list = rd.sample(list(self.uncov_portion.keys()), 2)

        opt_list = " ".join(opt_list)
        opt_list = list(set(opt_list.split()))

        self.prev_opt_arg = copy.deepcopy(opt_list)
        opt_list, original_opt = self.change_form(opt_list, coverages[-1])

        return " ".join(opt_list), original_opt


    def sample(self, coverages, iter_covs, portion, elapsed, budget):
        for prev_opt in self.prev_opt_arg:
            self.covered_branches[prev_opt] = self.covered_branches[prev_opt].union(iter_covs)

        self.opt_covered_branches = {key:len(value) for key, value in self.covered_branches.items()}
        new_total_br, covered_opt_branch, branches_opt = self.coverage()
        total_opt_branch = set()
        for tb in new_total_br.values():
            total_opt_branch = total_opt_branch.union(tb)


        # Updating scoring data from previous execution
        prev_opt_arg = " ".join(self.prev_opt_arg)
        prev_ingr = prev_opt_arg.split()

        for cand in self.bro_coverage.keys():
            opts = set(cand.split())
            if (len(opts) == len(opts.intersection(set(self.prev_opt_arg)))) and (len(opts) > 0):
                self.bro_coverage[cand].append(len(covered_opt_branch))
        
        if (prev_opt_arg not in self.bro_coverage.keys()) and (len(prev_opt_arg) > 0):
            self.bro_coverage[prev_opt_arg] = [len(covered_opt_branch)]

        if prev_opt_arg not in self.opt_count.keys():
            if len(prev_ingr) <= 0:
                pass
            elif len(prev_ingr) <= 1:
                self.opt_count[prev_opt_arg] = 1
            else:
                count_sum = 0
                for ingr in prev_ingr:
                    count_sum += self.opt_count[ingr]
                self.opt_count[prev_opt_arg] = round(count_sum / len(prev_ingr), 2)
        else:
            self.opt_count[prev_opt_arg] += 1
        self.opt_count = {key:value for key, value in self.opt_count.items() if len(key) > 0}

        for cand in self.opt_count.keys():
            if ((cand != prev_opt_arg)):
                self.opt_count[cand] += round(len(set(cand.split()).intersection(set(prev_ingr))) / len(cand.split()), 2)

        if prev_opt_arg not in self.total_br.keys():
            new_brs = set()
            for ingr in prev_ingr:
                new_brs = new_brs.union(new_total_br[ingr])
            self.total_br[prev_opt_arg] = new_brs

        cov_branches = {key: set() for key in self.total_br.keys()}
        uncov_branches = {key: set() for key in self.total_br.keys()}
        for opt, brs in self.total_br.items():
            cov_branches[opt] = brs.intersection(covered_opt_branch)
            uncov_branches[opt] = brs - covered_opt_branch

        for key in self.total_br.keys():
            if key not in self.uncov_portion.keys():
                self.uncov_portion[key] = 0
            if len(self.total_br[key]) > 0:
                self.uncov_portion[key] = round(len(uncov_branches[key]) / len(self.total_br[key]), 4)                

        opt_arg, original_opt = self.option_argument(coverages, portion, elapsed, budget, covered_opt_branch)
        opts = opt_arg.split()
        sym_cmd = ""

        for i in range(len(opts)):
            sym_cmd = sym_cmd + f"-sym-arg {len(opts[i]) - 2} "
        sym_cmd = sym_cmd.strip()
        
        # Making sampled option argument as a seed
        seeding_cmd = f"gen-bout {' '.join(opts)} --bout-file {self.running_dir}/seed_option_arguments/{self.pgm}.ktest"
        if (portion < self.explore_rate):
            seeding_cmd = f"gen-random-bout {self.running_dir}/seed_option_arguments/{self.pgm}.ktest {sym_cmd} --bout-file {self.running_dir}/seed_option_arguments/{self.pgm}.ktest"
        os.system(seeding_cmd)

        return opt_arg, sym_cmd, branches_opt, f"{self.running_dir}/seed_option_arguments/{self.pgm}.ktest"