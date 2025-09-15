import json
import numpy as np
import random as rd

from sklearn.preprocessing import MinMaxScaler



class Constructor:
    def __init__(self, pgm, running_dir, test_dir):
        with open(f"{running_dir}/../data/opt_branches/{pgm}.json", "r") as ob_f:
            self.option_branches = json.load(ob_f)
        self.pgm = pgm
        self.running_dir = running_dir
        self.test_dir = test_dir
        self.uncov_branches = {key : set(value) for key, value in self.option_branches.items()}
        self.selected_count = {key : 0 for key in self.option_branches.keys()}
        self.covered_set_data = {key : set(value) for key, value in self.option_branches.items()}
        self.coverage_data = {key : list() for key, value in self.option_branches.items()}
        self.bad_count = {key : 0 for key in self.option_branches.keys()}
        self.scores = {key : 0.5 for key in self.option_branches.keys()}
        self.ob_scores = self.calculate_branch_score()

        with open(f"{running_dir}/{test_dir}/{pgm}.score", "w") as score_f:
            for key, value in self.scores.items():
                score_f.write(f"{key} {value}\n")
    

    def normalize(self, data):
        # Function to normalize each feature value used for scoring option arguments
        values = np.array(list(data.values())).reshape(-1, 1)
        scaler = MinMaxScaler()
        normalized_values = scaler.fit_transform(values)
        normalized_data = {key: round(float(normalized_value), 4) for key, normalized_value in zip(data.keys(), normalized_values)}
        return normalized_data


    def calculate_branch_score(self):
        ob_count = dict()
        for value in self.option_branches.values():
            for val in value:
                if val in ob_count.keys():
                    ob_count[val] += 1
                else:
                    ob_count[val] = 1
        ob_scores = {key : 1 / value for key, value in ob_count.items()}
        norm_ob_scores = self.normalize(ob_scores)
        return norm_ob_scores


    def score(self):
        # 1. Weighted OB scores (WOB score)
        wob_data = dict()
        for key, value in self.uncov_branches.items():
            score = 0
            for val in value:
                score += self.ob_scores[val]
            wob_data[key] = score
        norm_wob_data = self.normalize(wob_data)

        # 2. Branch coverages (BC score)
        bcs_data = {key : len(value) for key, value in self.covered_set_data.items()}
        norm_bcs_data = self.normalize(bcs_data)
        bc_data = {key : sum(value) / (len(value) + 0.001) for key, value in self.coverage_data.items()}
        norm_bc_data = self.normalize(bc_data)
        total_bc_data = {key : norm_bcs_data[key] + norm_bc_data[key] for key in self.covered_set_data.keys()}
        norm_total_bc_data = self.normalize(total_bc_data)
        

        # 3. Less selected option (LSO score)
        lso_data = {key : 1 / value for key, value in self.selected_count.items()}
        norm_lso_data = self.normalize(lso_data)

        # # 4. Errored option (EO score)
        # eo_data = {key : 1 / (value + 0.001) for key, value in self.selected_count.items()}
        # norm_eo_data = self.normalize(eo_data)

        # # 5. Length of option (LO score)
        # lo_data = {key : 1 / (len(key.split())) for key in self.selected_count.keys()}
        # norm_lo_data = self.normalize(lo_data)

        # 6. Calculate total score for each option
        # total_score = {key : lub_data[key] + wob_data[key] + lso_data[key] + eo_data[key] + lo_data[key] for key in lub_data.keys()}
        total_score = {key : norm_wob_data[key] + norm_total_bc_data[key] + norm_lso_data[key] * 3 for key in wob_data.keys()}
        norm_total_score = self.normalize(total_score)
        return norm_total_score


    def select(self, data, bad_options, k=2):
        data = {key : value for key, value in data.items() if key not in bad_options}
        candidates = list(data.keys())
        weights = list(data.values())
        selected = []
        for _ in range(k):
            # Probabilistically select arguments Based on weights.
            best = rd.choices(candidates, weights=weights, k=1)[0]
            selected.append(best)
            # Prevent the same argument from being selected multiple times.
            index = candidates.index(best)
            candidates.pop(index)
            weights.pop(index)

        scores = {key : data[key] for key in self.option_branches.keys() if (key not in selected) and (key in data.keys())}
        with open(f"{self.running_dir}/{self.test_dir}/{self.pgm}.score", "w") as score_f:
            for key, value in scores.items():
                score_f.write(f"{key} {value}\n")
        return selected


    def filter(self):
        try:
            q3 = np.percentile(list(self.bad_count.values()), 75)
        except:
            q3 = 0
        bad_options = {k: v for k, v in self.bad_count.items() if v > q3 and v >= 10}
        if len(bad_options) >= 1:
            return list(bad_options.keys())
        else:
            return list()


    def construct(self):
        unselected = [key for key, value in self.selected_count.items() if not value]
        if len(unselected) > 0:
            sampled = [rd.choice(unselected)]
        else:
            scores = self.score()
            bad_options = self.filter()
            sampled = self.select(scores, bad_options)
        new_argument = " ".join(sampled)
        sampled_filter = list()
        for key in self.option_branches.keys():
            if (f" {key}" in new_argument) or (f"{key} " in new_argument) or (key == new_argument):
                sampled_filter.append(key)

        return sampled_filter
            

    def update(self, covered, options, runtime, budget):
        # Update uncovered branch sets
        for key, value in self.uncov_branches.items():
            self.uncov_branches[key] = value - covered

        # Update errored iteration    
        for option in options:
            if (len(covered) <= 0) or (runtime < budget):
                self.bad_count[option] += 1
        
        # Update option counts and coverage data
        options_tmp = " ".join(options).split()
        for key in self.selected_count.keys():
            key_set = set(key.split())
            intersected = key_set.intersection(set(options_tmp))
            if len(intersected) == len(key_set):
                self.covered_set_data[key] = self.covered_set_data[key].union(covered)
                self.coverage_data[key].append(len(covered))
            self.selected_count[key] += len(intersected) / len(key_set)
        print(self.selected_count)
        
        # Make data for newly generated option configuration
        new_option = " ".join(options)
        if (len(new_option.strip()) > 0) and (new_option not in self.uncov_branches.keys()):
            new_uncov_set = set()
            new_covered_set = set()
            new_coverage_list = list()
            counts = list()
            bad_counts = list()
            for option in options:
                new_uncov_set = new_uncov_set.union(self.uncov_branches[option])
                new_covered_set = new_covered_set.union(self.covered_set_data[option])
                new_coverage_list = new_coverage_list + (self.coverage_data[option])
                counts.append(self.selected_count[option])
                bad_counts.append(self.bad_count[option])
            self.uncov_branches[new_option] = new_uncov_set
            self.selected_count[new_option] = sum(counts) / len(counts)
            self.bad_count[new_option] = sum(bad_counts) / len(bad_counts)
            self.covered_set_data[new_option] = new_covered_set
            self.coverage_data[new_option] = new_coverage_list
