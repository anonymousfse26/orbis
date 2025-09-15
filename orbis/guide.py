import copy
import json
import os
import re



class Guider:
    def __init__(self, pgm, running_dir, test_dir, n_testcases):
        self.running_dir = running_dir
        self.test_dir = f"{running_dir}/{test_dir}"
        self.n_testcases = n_testcases
        self.option_constraints = dict()

        with open(f"{running_dir}/../data/constraints/{pgm}.json", "r") as const_f:
            constraints = {key : set(value) for key, value in json.load(const_f).items()}
            for key, value in constraints.items():
                self.option_constraints[key] = {re.sub(r'\barg\d+\b', 'arg', s) for s in value}
        self.all_constraints = set().union(*self.option_constraints.values())
        self.seed_data = {key : list() for key in self.option_constraints.keys()}


    def save(self, arguments, iteration):
        if os.path.exists(f"{self.test_dir}/iteration-{iteration}"):
            tc_data = list()
            # Collect all .ktest files from the iteration directory
            constraints = [f"{self.test_dir}/iteration-{iteration}/{f}" for f in os.listdir(f"{self.test_dir}/iteration-{iteration}") if f.endswith(".const")]
            for constraint in constraints:
                with open(constraint, "r") as const_f:
                    const_list = [line.strip() for line in const_f.readlines()][0]
                    const_list = eval(const_list)
                const_list = [re.sub(r'\barg\d+\b', 'arg', s) for s in const_list]
                testcase = constraint.replace(".const", ".ktest")
                tc_data.append([testcase, set(const_list)])
            tc_data = sorted(tc_data, key=lambda x: len(x[1]), reverse=True)
            tc_data = tc_data[:self.n_testcases]
            
            # Store top-k seed data based on option argument
            for tmp in arguments:
                tmp_seed = self.seed_data[tmp] + tc_data
                tmp_seed = sorted(tmp_seed, key=lambda x: len(x[1]), reverse=True)
                if len(tmp_seed) >= self.n_testcases:
                    tmp_seed = tmp_seed[:self.n_testcases]
                    self.seed_data[tmp] = tmp_seed
                else:
                    self.seed_data[tmp] = tmp_seed
            new_arg = " ".join(arguments)
            if new_arg not in self.seed_data.keys():
                self.seed_data[new_arg] = tc_data
            if new_arg not in self.option_constraints.keys():
                tmp_set = set()
                for tmp in arguments:
                    tmp_set = tmp_set.union(self.option_constraints[tmp])
                self.option_constraints[new_arg] = tmp_set
        

    def guide(self, arguments, bout_bin):
        # Extract argument-related constraints
        opt_related_consts = set()
        for argument in arguments:
            if argument in self.option_constraints.keys():
                opt_related_consts = opt_related_consts.union(self.option_constraints[argument])

        # Make concrete seed with sampled arguments
        arguments_str = " ".join(arguments)
        bout_cmd = f'{bout_bin} "{arguments_str}" --bout-file {self.test_dir}/option_seed.ktest'
        os.system(bout_cmd)

        # Extract individual options from the option argument
        candidates = copy.deepcopy({key : value for key, value in self.seed_data.items() if key in arguments})

        # Select the best seed for each option based on argument similarity
        seeds = list()
        for key, values in candidates.items():
            seed = ""
            if len(values) > 0:
                max_len = max(len(sc) for _, sc in values)
                longest_cases = [(tc, sc) for tc, sc in values if len(sc) == max_len]
                if len(longest_cases) == 1:
                    seed = longest_cases[0][0]
                elif len(longest_cases) > 1:
                    max_difference = 0
                    for (tc, sc) in longest_cases:
                        set_diff = len(set(sc) - opt_related_consts)
                        if set_diff > max_difference:
                            max_difference = set_diff
                            seed = tc
                if len(seed) > 0:
                    seeds.append(seed)
        seeds.append(f"{self.test_dir}/option_seed.ktest")
        
        return list(set(seeds))