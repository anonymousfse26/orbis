from itertools import chain
from tree_sitter import Language, Parser

import copy
import clang.cindex
import json
import os
import re
import warnings
import subprocess as sp



class Extractor:
    def __init__(self, pgm, gcov_path, config, num_dash, running_dir):
        # Build the tree-sitter library
        ts_dir = f"{running_dir}/../parser/tree-sitter-c"
        os.makedirs(f'{ts_dir}/build', exist_ok=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            Language.build_library(
                f'{ts_dir}/build/my-languages.so',
                [ts_dir]
            )

            # Load the built library
            library_path = os.path.abspath(f'{ts_dir}/build/my-languages.so')
            self.language = Language(library_path, 'c')

        # Initialize the parser
        self.parser = Parser()
        self.parser.set_language(self.language)

        # Initialize variables for option extraction
        self.pgm = pgm
        self.gcov_path = gcov_path[:gcov_path.rfind('/')]
        self.num_dash = num_dash
        self.running_dir = running_dir

        if os.path.exists(f"{running_dir}/seed_option_arguments/{self.pgm}.bout"):
            os.remove(f"{running_dir}/seed_option_arguments/{self.pgm}.bout")
        with open(config, 'r') as config_json:
            pgm_config = json.load(config_json)[pgm]
            version = pgm_config["version"]
            src_dir = pgm_config["src_dir"]
        if pgm in ["gawk", "find"]:
            self.help_type = 1
        else:
            self.help_type = 0
        self.src_path = f"{running_dir}/{version}/{src_dir}"
        self.std_functions = []
        self.src_codes = dict()

        clang.cindex.Config.set_library_file('/usr/lib/x86_64-linux-gnu/libclang-6.0.so')
        if ("coreutils" in gcov_path) or ("binutils" in gcov_path):
            c_files = [f"{self.src_path}/{f}" for f in os.listdir(self.src_path) if f.endswith('.c') and pgm in f]
        else:
            c_files = [f"{self.src_path}/{f}" for f in os.listdir(self.src_path) if f.endswith('.c')]

        self.std_functions = list(set(self.std_functions + self.get_standard_functions(c_files)))
        for c_f in c_files:
            try:
                with open(c_f, "r") as src_file:
                    self.src_codes[c_f] = str(src_file.read())
            except:
                with open(c_f, "r", encoding="latin-1") as src_file:
                    self.src_codes[c_f] = str(src_file.read())


    def get_standard_functions(self, c_files):
        """
        Extract all standard functions included in the given C files.
        - parameters
            * c_files: C source file paths to analyze (type: list)
        - return
            * Unique standard function names found in the C files (type: list)
        """
        functions = []
        for c_file in c_files:
            index = clang.cindex.Index.create()
            # Parse the C file with standard library includes
            tu = index.parse(c_file, args=['-std=c99', '-I/usr/include', '-I/usr/include/x86_64-linux-gnu'])
            for child in tu.cursor.get_children():
                if child.kind == clang.cindex.CursorKind.FUNCTION_DECL:
                    functions.append(child.spelling)
        return list(set(functions))


    def get_help_output(self):
        """
        Extract option information from the help output of the target program.
        - return
            * Options that include both short and long forms (type: list)
            * Long options and associated short options (type: dictionary)
            * Short options that do not have corresponding long options (type: list)
        """
        options = dict()
        only_short = []
        # Determine the appropriate help command based on the program
        if self.pgm in ["gcal"]:
            command = [f"{self.gcov_path}/{self.pgm}", '--usage']
            result = sp.run(command, stdout=sp.PIPE, stderr=sp.PIPE, encoding="latin-1")
        else:
            command = [f"{self.gcov_path}/{self.pgm}", '--help']
            result = sp.run(command, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
        text = result.stderr if result.stdout == "" else result.stdout

        # Process help output line by line
        help_lines = [line.strip() for line in text.split("\n")]
        with_short = []
        for line in help_lines:
            line = line.replace("|", " ").replace('=', " ").replace(",", "")
            line = re.sub(r'\[.*?\]', '', line)
            words = line.split()
            words = sorted(words, key=lambda x: x.count('-'), reverse=True)
            if len(words) >= 1:
                # Identify options based on the number of dashes
                if not self.help_type:
                    if (words[0][:self.num_dash] == "-" * self.num_dash):
                        if words[0] not in options.keys():
                            options[words[0]] = []
                else:
                    for word in words:
                        if (word[:self.num_dash] == "-" * self.num_dash):
                            if word not in options.keys():
                                options[word] = []
            for word in words:
                if (word[0] == "-") and (len(word) >= 2):
                    # Match valid option patterns
                    if not self.help_type:
                        if bool(re.fullmatch(r'--?[a-zA-Z][a-zA-Z0-9\-_]*', word)):
                            with_short.append(word)
                            try:
                                if word not in options.keys():
                                    options[words[0]].append(word)
                            except:
                                only_short.append(word)
                        else:
                            break
                    else:
                        if bool(re.fullmatch(rf'-{{{self.num_dash}}}[a-zA-Z][a-zA-Z0-9\-_]*', word)):
                            with_short.append(word)
                            try:
                                if word not in options.keys():
                                    options[words[0]].append(word)
                            except:
                                only_short.append(word)
        # Remove short options that are already associated with long options
        for value in options.values():
            for val in value:
                if val in only_short:
                    only_short.remove(val)

        options = {key.strip('-') : value for key, value in options.items() if (not (re.search(r'[^\w\s\-]', key))) and (len(key.strip('-')) > 0)}
        if self.num_dash == 1:
            options = {key : [v for v in value if len(v.strip('-')) > 1] for key, value in options.items() if len(key) > 1}

        return list(set(with_short)), options, only_short


    def extract_variables(self, code_snippet, extract_depth):
        """
        Extract all variables from the code snippet.
        - parameters
            * code_snippet: C code to analyze (type : string)
            * extract_depth: Depth of option-related objects (type : integer)
        - return
            * Variable names (type : set)
        """
        # Initialize
        tree = self.parser.parse(code_snippet.encode('utf-8'))
        root_node = tree.root_node
        variables = list()

        # Extract variables
        def extract_identifiers(node, extract_depth):
            variable_name = code_snippet[node.start_byte:node.end_byte]
            # Extract variable names
            if node.type == 'identifier':
                variable_name = code_snippet[node.start_byte:node.end_byte]
                variables.append(variable_name)
            if node.type == "char_literal":
                variable_name = code_snippet[node.start_byte:node.end_byte]
                if (self.num_dash >= 2) and (extract_depth == 0):
                    variables.append(variable_name)
            # Explore child nodes
            for child in node.children:
                extract_identifiers(child, extract_depth)
            
        # Start exploration from the root node
        extract_identifiers(root_node, extract_depth)
        return variables


    def extract_condition_lines_for_variable(self, code_snippet, target_variable):
        """
        Extract line numbers of conditional statements where a specific variable is used, within those statements.
        - parameters
            * code_snippet: C code to analyze (type: string)
            * target_variable: The variable name that must be included in the condition (type: string)
        - return
            * Line numbers where the target variable appears in conditions (type: list)
            * Extracted conditional statements (type: string)
            * Function definitions where the target variable is used (type: string)
        """
        # Initialize
        tree = self.parser.parse(code_snippet.encode('utf-8'))
        condition_lines = []
        condition_codes = []
        function_codes = []

        def extract_conditions(node, code, condition_lines):
            """
            Extract conditional statement nodes and add them to the list.
            - parameters
                * node: The current node being explored (type: tree-sitter node)
                * code: The source code text (type: bytes)
                * condition_lines: A list to store line numbers of conditional statements (type: list)
            """
            if node.type in {'if_statement', 'while_statement', 'for_statement', 'switch_statement', 'case_statement'}:
                start_line = node.start_point[0] + 1
                if start_line not in condition_lines:
                    condition_lines.append(start_line)
                    code_snippet = code[node.start_byte:node.end_byte].decode('utf-8')
                    condition_codes.append(code_snippet)
            # Explore child nodes
            for child in node.children:
                extract_conditions(child, code, condition_lines)

        def is_element_in_condition(node, code, target_variable):
            """
            Check if the target variable appears inside a conditional statement.
            - parameters
                * node: The current node being examined (type: tree-sitter node)
                * code: The source code text (type: bytes)
                * target_variable: The variable name to search for (type: string)
            - return
                * Whether the variable is found within the condition (type: bool)
            """
            if node.type in {'identifier', 'string_literal', 'char_literal'}:
                element_name = code[node.start_byte:node.end_byte].decode('utf-8')
                if (target_variable == element_name):
                    return True
            # Check function names when encountering function definition nodes
            elif node.type == 'function_definition':
                function_name_node = node.child_by_field_name('declarator')
                if function_name_node:
                    function_name = code[function_name_node.start_byte:function_name_node.end_byte].decode('utf-8')
                    if function_name == target_variable:
                        return True
            # Explore child nodes
            for child in node.children:
                if is_element_in_condition(child, code, target_variable):
                    return True
            return False
        
        def find_conditions_with_variable(node, code, target_variable, condition_lines, condition_codes):
            """
            Find conditional statements where a specific variable is used and extract those conditions.
            - parameters
                * node: The current node being traversed (type: tree-sitter node)
                * code: The source code text (type: bytes)
                * target_variable: The variable name to search for in conditions (type: string)
                * condition_lines: A list to store the line numbers of conditions where the variable is used (type: list)
                * condition_codes: A list to store the extracted conditional statement code snippets (type: list)
            """
            # Add the line number of the conditional statement
            if node.type in {'if_statement', 'while_statement', 'for_statement', 'switch_statement'}:
                condition_node = self._find_condition_node(node)
                if condition_node and is_element_in_condition(condition_node, code, target_variable):
                    start_line = node.start_point[0] + 1
                    if start_line not in condition_lines:
                        condition_lines.append(start_line)
                        code_snippet = code[node.start_byte:node.end_byte].decode('utf-8')
                        condition_codes.append(code_snippet)
                    extract_conditions(node, code, condition_lines)
            # Extract conditions from case statements
            elif node.type == 'case_statement':
                value_node = node.child_by_field_name('value')
                if value_node and is_element_in_condition(value_node, code, target_variable):
                    start_line = node.start_point[0] + 1
                    if start_line not in condition_lines:
                        condition_lines.append(start_line)
                        code_snippet = code[node.start_byte:node.end_byte].decode('utf-8')
                        condition_codes.append(code_snippet)
                    extract_conditions(node, code, condition_lines)
            # Explore child nodes
            for child in node.children:
                find_conditions_with_variable(child, code, target_variable, condition_lines, condition_codes)

        def find_function_calls_with_variable(node, code, target_variable, function_codes):
            """
            Traverse the given node to find function definitions and store their code 
            if the function name matches the target variable.
            - parameters
                * node: The current node being traversed (type: tree-sitter node)
                * code: The source code text (type: bytes)
                * target_variable: The function name to search for (type: string)
                * function_codes: A list to store the code of matching function definitions (type: list)
            """
            if node.type == 'function_definition':
                # Check if the function definition's name matches the target variable
                declarator_node = node.child_by_field_name('declarator')
                if declarator_node:
                    # Find the identifier node within the declarator
                    identifier_node = self._find_identifier_node(declarator_node)
                    if identifier_node:
                        function_name = code[identifier_node.start_byte:identifier_node.end_byte].decode('utf-8')
                        if (target_variable == function_name):
                            code_snippet = code[node.start_byte:node.end_byte].decode('utf-8')
                            function_codes.append(code_snippet)
            # Explore child nodes
            for child in node.children:
                find_function_calls_with_variable(child, code, target_variable, function_codes)

        # Traverse the syntax tree to find conditional statements
        root_node = tree.root_node
        find_conditions_with_variable(root_node, code_snippet.encode('utf-8'), target_variable, condition_lines, condition_codes)
        find_function_calls_with_variable(root_node, code_snippet.encode('utf-8'), target_variable, function_codes)
        return condition_lines, "\n".join(condition_codes), "\n".join(function_codes)


    def _find_condition_node(self, node):
        """
        Find the node containing the condition expression of a conditional statement.
        Returns the condition node for if, while, for, and switch statements.
        - parameters
            * node: The current node being explored (type: tree-sitter node)
        - return
            * The condition node if found, otherwise None (type: tree-sitter node or None)
        """
        if node.type == 'if_statement':
            return node.child_by_field_name('condition')
        elif node.type == 'while_statement':
            return node.child_by_field_name('condition')
        elif node.type == 'for_statement':
            return node.child_by_field_name('condition')
        elif node.type == 'switch_statement':
            return node.child_by_field_name('condition')
        return None

    def _find_identifier_node(self, node):
        """
        Find the identifier node within the given node.
        - parameters
            * node: The current node being explored (type: tree-sitter node)
        - return
            * The identifier node if found, otherwise None (type: tree-sitter node or None)
        """
        if node.type == 'identifier':
            return node
        for child in node.children:
            result = self._find_identifier_node(child)
            if result:
                return result
        return None

    def extract_blocks_with_target(self, code, target):
        """
        Extract code blocks that contain the target string.
        - parameters
            * code: The source code to analyze (type: string)
            * target: The target string to search for in code blocks (type: string)
        - return
            * A string containing extracted code blocks where the target is found (type: string)
        """
        # Parse the code
        tree = self.parser.parse(code.encode('utf-8'))
        root_node = tree.root_node
        extracted_blocks = []

        # Find specific blocks containing the target
        def find_blocks_with_target(node, target):
            blocks = []
            # Check if the current node contains the target
            if target in node.text.decode('utf-8'):
                blocks.append(node)
            # Recursively search child nodes
            for child in node.children:
                blocks.extend(find_blocks_with_target(child, target))
            return blocks

        # Extract blocks
        target_nodes = find_blocks_with_target(root_node, target)
        for node in target_nodes:
            if node.type == "if_statement":
                body_node = node.child_by_field_name("consequence")
                if body_node:
                    start_byte = node.start_byte
                    end_byte = body_node.end_byte
                    extracted_blocks.append(code[start_byte:end_byte])
            elif (node.type == "initializer_list") and (not any(child.type == "initializer_list" for child in node.children)):
                start_byte = node.start_byte
                end_byte = node.end_byte
                if (code[start_byte:end_byte][0] != "{"):
                    start_byte = start_byte - 4
                extracted_blocks.append(code[start_byte:end_byte])
            elif (node.type == "call_expression"):
                start_byte = node.start_byte
                end_byte = node.end_byte
                extracted_blocks.append(code[start_byte:end_byte])
        extracted_blocks = [b for b in extracted_blocks if target in b]
        return "\n".join(extracted_blocks)


    def extract(self, depth):
        """
        Extract option-related branches from source code.
        - return
            * options: option names and lists of associated variables (type: dictionary)
            * option_lines: option names and sets of file-line number pairs indicating where the options appear in conditions (type: dictionary)
            * branches_opt: C source filenames and sets of line numbers containing option-related branches (type: dictionary)
        """
        # Extract option information from the help output
        with_short, options, only_short = self.get_help_output()
        searching = {key : [f"'{key}'", f'"{key}"', f"'{'-' * self.num_dash}{key}'", f'"{"-" * self.num_dash}{key}"'] for key in options.keys()}
        
        # Initialize
        option_lines = {key : [] for key in options.keys()}
        option_codes = {key : "" for key in options.keys()}
        total_vars = list()
        
        # Extract option-defining blocks for each option
        for opt in options.keys():
            related_codes = ""
            for s in searching[opt]:
                for cfile, code in self.src_codes.items():
                    block = self.extract_blocks_with_target(code, s)
                    if len(block.strip()) > 0:
                        related_codes = "\n".join([related_codes, block.strip()])
            option_codes[opt] = option_codes[opt] + '\n' + related_codes
            
        # Perform unique variable extraction refinement for n_opt_depth times
        for count in range(depth):
            not_var = self.var_filter(option_codes, count).union(set(self.std_functions))
            for key, value in option_codes.items():
                # Extract variables from the option-related code
                variables = self.extract_variables(value, count) + re.findall(r"'[a-zA-Z0-9]'", value) + re.findall(r'"[a-zA-Z0-9]"', value)
                # Filter extracted variables
                if self.num_dash <= 1:
                    variables = [var for var in set(variables) - not_var if len(var.strip("'").strip('"')) > 1]
                else:
                    variables = [var for var in set(variables) - not_var]
                total_vars = total_vars + variables
                # Store extracted option-related variables
                if count == 0:
                    options[key] = list(set(options[key] + variables))
                # Extract conditional statements where the variable is used
                for var in variables:
                    for c_f in self.src_codes.keys():
                        file_name = c_f[c_f.rfind('/') + 1 :]
                        src_code = self.src_codes[c_f]
                        condition_lines, condition_codes, function_codes = self.extract_condition_lines_for_variable(src_code, var)
                        option_lines[key] = set(list(option_lines[key]) + [f"{file_name} {line}" for line in condition_lines])
                        option_codes[key] = option_codes[key] + condition_codes + function_codes
            # Update collected line information (ensuring uniqueness)
            tmp = list(set(chain.from_iterable(option_lines.values())))
            all_lines = list(set(chain.from_iterable(option_lines.values())))

        # Save extracted option-related branches as data
        option_lines = {key : list(value) for key, value in option_lines.items()}
        result = {"options" : options, "total_br" : option_lines}
        with open(f'{self.running_dir}/../data/opt_branches/{self.pgm}.json', 'w') as json_file:
            json.dump(result, json_file, indent=2)

        # Map option-related branches to source files
        branches_opt = {key : set() for key in os.listdir(self.src_path) if key.endswith(".c")}
        for value in option_lines.values():
            for v in value:
                lst = v.split()
                branches_opt[lst[0]].add(lst[1])
        
        return options, {key : set(value) for key, value in option_lines.items()}, branches_opt


    def var_filter(self, option_codes, extract_depth):
        """
        Filter out non-variable names based on predefined criteria and heuristics.
        - parameters
            * option_codes: A dictionary where keys are option names and values are code snippets (type: dict)
            * extract_depth: The extraction depth level for variable filtering (type: int)
        - return
            * A set of non-option-related variables to be filtered out (type: set)
        """
        wildcards = ["GLobal", "BUF_LEN"]   # Add variables to manually remove from option-related variables.
        var_count = dict()

        # Count occurrences of extracted variables
        for key, value in option_codes.items():
            variables = self.extract_variables(value, extract_depth)
            for v in variables:
                if v not in var_count.keys():
                    var_count[v] = 1
                else:
                    var_count[v] += 1
        
        # Filter variables based on occurrence
        if self.num_dash <= 1:
            if not self.help_type:
                not_var = {key for key, v in var_count.items() if (v > 2) or (len(key.strip('"').strip("'")) == 1) or (len(key) <= 2) or (all(not c.isalnum() and not c.isspace() for c in key)) or ("_" not in key)}
            else:
                not_var = {key for key, v in var_count.items() if (v > 2) or (len(key.strip('"').strip("'")) == 1) or (len(key) <= 2) or (all(not c.isalnum() and not c.isspace() for c in key))}
        else:
            not_var = {key for key, v in var_count.items() if (v > 2) or (len(key) <= 2) or (all(not c.isalnum() and not c.isspace() for c in key))}
        return not_var.union(set(wildcards))
    
    def with_short(self, options):
        """
        Generate a list of formatted option strings, including short and long options.
        - parameters
            * options: A dictionary where keys are option names and values are associated variables (type: dict)
        - return
            * opt_list: A list of formatted options, including short and long forms (type: list)
        """
        shorts = []
        for opt, vars in options.items():
            for var in vars:
                var = var.strip("'").strip('"')
                if len(var) == 1:
                    shorts.append(var)

        opt_list = list([k.strip("-") for k in options.keys()]) + shorts
        for i in range(len(opt_list)):
            opt = opt_list[i]
            if len(opt) == 1:
                opt_list[i] = f'"-{opt}"'
            else:
                opt_list[i] = f'"{"-" * self.num_dash}{opt}"'
        return opt_list