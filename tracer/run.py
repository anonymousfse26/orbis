from argparse import ArgumentParser
from pathlib import Path

import ast
import json
import os
import re
import sys

import subprocess as sp


def get_help_output(program, gcov_obj, num_dash=2, other_type=None):
    options = set()
    only_short = []
    # Determine the appropriate help command based on the program
    if other_type is not None:
        command = [gcov_obj, f'{"-" * num_dash}{other_type}']   # e.g., gcal --usage
    else:
        command = [gcov_obj, f'{"-" * num_dash}help']
    command = ' '.join(command)
    result = sp.run(command, stdout=sp.PIPE, stderr=sp.PIPE, shell=True, check=True)
    text = result.stderr if result.stdout == "" else result.stdout
    text = str(text)

    # Process help output line by line
    help_lines = [line.strip() for line in text.split("\\n")]
    with_short = []
    for line in help_lines:
        line = line.replace("|", " ").replace('=', " ").replace(",", "")
        line = re.sub(r'\[.*?\]', '', line)
        words = line.split()
        words = sorted(words, key=lambda x: x.count('-'), reverse=True)

        for word in words:
            short_pattern = re.compile(r'^(?:-[^-]|[^-]-)$')
            if (word[:num_dash] == "-" * num_dash) or short_pattern.match(word.strip()):
                options.add(word)
    return options


def get_gcovs(running_dir, gcov_obj, src_depth):
    target_parent = gcov_obj[:gcov_obj.rfind("/")]
    target_parent_abs = Path(target_parent).absolute()
    os.chdir(target_parent)
    base = Path()
    for _ in range(src_depth):
        base = base / '..'

    gcda_pattern = base / '**/*.gcda'
    gcdas = list(target_parent_abs.parent.glob(str(gcda_pattern)))
    gcdas = [gcda.absolute() for gcda in gcdas]

    os.chdir(str(target_parent))
    cmd = ["gcov", '-b', *list(map(str, gcdas))]
    cmd = ' '.join(cmd)
    try:
        _ = sp.run(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True, check=True, timeout=0.1)
    except:
        pass
    os.chdir(running_dir)


def get_cmd_log(running_dir, program, start_arg, end_arg, option=""):
    def is_tuple_string(s):
        try:
            return isinstance(ast.literal_eval(s), tuple)
        except (ValueError, SyntaxError):
            return False

    cmd = f"{start_arg} {running_dir}/execs/{program}_trace {option} {end_arg}".strip()
    cmd = [x.strip() for x in cmd.split()]
    try:
        result = sp.run(cmd, stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True, timeout=0.1)
    except sp.TimeoutExpired as e:
        result = sp.CompletedProcess(e.cmd, returncode=None, stdout=e.stdout, stderr=e.stderr)
    except:
        return "ERRORED"
    output_str = result.stdout
    logs = [ast.literal_eval(l) for l in output_str.split('\n') if is_tuple_string(l)]
    logs = [logs for logs in logs if logs[1] != "<unknown>"]
    return set(logs)


def extract_function_block(file_path, func_name):
    if not os.path.exists(file_path):
        return None, None

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        code = f.read()

    name_escaped = re.escape(func_name)

    pat = (
        r"\b" + name_escaped + r"\b"
        r"\s*\([^;{]*\)"
        r"(?:[^;{]*)\{"
    )

    m = re.search(pat, code, re.MULTILINE | re.DOTALL)
    if not m:
        return None, None

    brace_index = code.find("{", m.end() - 1)
    if brace_index == -1:
        return None, None

    start_line_no = code[:m.start()].count("\n") + 1

    depth = 0
    end_index = None
    for i in range(brace_index, len(code)):
        ch = code[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_index = i
                break

    if end_index is None:
        return None, None

    return code[m.start():end_index + 1], start_line_no


def extract_condition_lines(func_code, var_name, value, func_start_line_no):
    def value_patterns(val):
        pats = {str(val)}
        try:
            ival = int(val)
            pats.add(hex(ival))
            if ival == 0:
                pats.add("0")
            else:
                pats.add("0" + oct(ival)[2:])
        except Exception:
            pass
        return [re.escape(p) for p in pats]

    val_pats = "|".join(value_patterns(value))
    var_pat = re.escape(var_name)
    op_pats = r"==|!=|>=|<=|>|<"

    cond_header = re.compile(r"^\s*(if|while|for)\b.*", re.MULTILINE)
    comp_regex = re.compile(
        rf"\b({var_pat}\s*(?:{op_pats})\s*(?:{val_pats})|(?:{val_pats})\s*(?:{op_pats})\s*{var_pat})\b"
    )

    switch_header = re.compile(rf"^\s*switch\s*\(\s*{var_pat}\s*\)", re.MULTILINE)
    case_regex = re.compile(rf"^\s*case\s+(?:{val_pats})\s*:", re.MULTILINE)

    results = []
    lines = func_code.splitlines()

    for lineno, line in enumerate(lines, start=0):
        abs_lineno = func_start_line_no + lineno
        if cond_header.match(line) and comp_regex.search(line):
            results.append((abs_lineno, line.strip()))
        if switch_header.match(line):
            results.append((abs_lineno, line.strip()))
        if case_regex.match(line):
            results.append((abs_lineno, line.strip()))

    return results



def main(*argv):
    parser = ArgumentParser()
    parser.add_argument('-p', '--program', default=None, type=str, metavar='STR',
                        help='The target program for extracting option-related branches (Default : None)')
    parser.add_argument('-s', '--start-arg', default="", type=str, metavar='STR',
                        help='The arguments that is placed before the execution program to generate a valid argument (Default : None)')
    parser.add_argument('-e', '--end-arg', default="", type=str, metavar='STR',
                        help='The arguments that is placed after the execution program to generate a valid argument (Default : None)')
    parser.add_argument('-d', '--src-depth', default=1, type=int, metavar='INT',
                        help='The depth from the directory where gcov is built to the directory where the execution file is defined (Default : 1)')
    parser.add_argument('gcov_obj', nargs='?', default=None,
                        help='The path of the execution file that generates the .gcda files')

    args = parser.parse_args(argv)

    running_dir = os.getcwd()
    target_parent = args.gcov_obj[:args.gcov_obj.rfind("/")]
    opt_branches = dict()

    options = get_help_output(args.program, args.gcov_obj)
    get_gcovs(os.getcwd(), args.gcov_obj, args.src_depth)

    if os.path.exists(f"../data/option_dict/{args.program}.dict"):
        with open(f"../data/option_dict/{args.program}.dict", "r") as dict_file:
            options = [l.strip() for l in dict_file.readlines()]
            options = [opt for opt in options if opt[0] != "#"]

    errored = []
    default_logs = get_cmd_log(os.getcwd(), args.program, args.start_arg, args.end_arg)
    for option in options:
        logs = get_cmd_log(os.getcwd(), args.program, args.start_arg, args.end_arg, option)
        if logs == "ERRORED":
            errored.append(option)
            continue
            
        branches = set()
        for log in logs:
            func_code, start_line = extract_function_block(log[-1], log[0])
            if func_code is None:
                continue

            cond_lines = extract_condition_lines(func_code, log[1], log[2], start_line)
            if len(cond_lines) > 0:
                rel_file = log[-1][log[-1].rfind("../") + 3:]
                rel_path = f"{'../' * (args.src_depth + 1)}{rel_file}"
                gcov_file = f"{target_parent}/{rel_file[rel_file.rfind('/') + 1:]}.gcov"
                try:
                    with open(gcov_file, "r") as gcov_f:
                        lines = [l.strip() for l in gcov_f.readlines()]
                    for cond_line in cond_lines:
                        flag = 0
                        for i, line in enumerate(lines):
                            l_data = [d.strip() for d in line.split(":")]
                            if len(l_data) >= 2:
                                if l_data[1] == str(cond_line[0]):
                                    flag = 1
                            if flag:
                                if ('branch' in line) and (":" not in line) and ("returned 0% blocks executed 0%" not in line):
                                    branches.add(f"{rel_path} {i}")
                                else:
                                    if len(l_data) > 1:
                                        if (l_data[1].isdigit()) and (not l_data[1] == str(cond_line[0])):
                                            break
                except:
                    pass
            opt_branches[option] = list(branches)

    options = [opt for opt in options if opt not in errored]

    with open(f"../data/option_dict/{args.program}.dict", "w", encoding="utf-8") as f:
        for opt in options:
            f.write(opt + "\n")

    with open(f"../data/opt_branches/{args.program}.json", "w", encoding="utf-8") as f:
        json.dump(opt_branches, f, ensure_ascii=False, indent=4)

if __name__ == '__main__':
    main(*sys.argv[1:])
