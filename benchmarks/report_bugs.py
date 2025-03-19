from argparse import ArgumentParser
import sys
import os


def src_dir(program):
    if ("xorriso" in program) or ("sed" in program):
        idx = program.index("-")
        return program[:idx]

    elif "gawk" in program:
        return None

    else:
        return "src"


def collect_err_files(directories):
    error_index = []
    for file in directories:
        dir_num = 0
        for i in list(os.scandir(file)):
            if 'iteration' in str(i):
                dir_num += 1
        
        os.chdir("./%s" % (file))
        for num in range(dir_num):
            err_files = []
            os.chdir("iteration-%d" % (num + 1))
            testcases = os.listdir("./")
            for tc in testcases:
                if ".err" in tc:
                    err_files.append(tc)
            
            for err_tc in err_files:
                error_index.append("%d-%s" % (num + 1, err_tc))
        
            os.chdir("../")

        os.chdir("../")
    return error_index


def log_err_replays(fd_name, err_file, program, src):
    print("[INFO] ParaSuit : Extracting CRASHED testcases from %s directory" % (fd_name))
    idx_p = program.index("-")
    exec_f = program[:idx_p]

    for rp in err_file:
        if src == None:
            os.chdir("./%s/obj-gcov/" % (program))
        else:
            os.chdir("./%s/obj-gcov/%s/" % (program, src)) 

        hypen = rp.find('-')
        idx = rp.find('.')
        iter = rp[:hypen]
        kfile = rp[hypen+1:idx]

        os.system("rm -rf **/*.gcda")
        os.system("rm -rf **/*.gcov")

        if src == None:
            ktst_path = "../../%s/iteration-%s/%s.ktest" % (fd_name, iter, kfile)
            if os.path.exists("../../%s/errors"):
                os.remove("../../%s/errors")
            if (rp == err_file[0]):
                os.system("klee-replay ./%s %s 2> ../../%s/errors" % (exec_f, ktst_path, fd_name))
            else:
                os.system("klee-replay ./%s %s 2>> ../../%s/errors" % (exec_f, ktst_path, fd_name))
            os.chdir("../../")

        else:
            ktst_path = "../../../%s/iteration-%s/%s.ktest" % (fd_name, iter, kfile)
            if os.path.exists("../../../%s/errors"):
                os.remove("../../../%s/errors")
            if (rp == err_file[0]):
                os.system("klee-replay ./%s %s 2> ../../../%s/errors" % (exec_f, ktst_path, fd_name))
            else:
                os.system("klee-replay ./%s %s 2>> ../../../%s/errors" % (exec_f, ktst_path, fd_name))
            os.chdir("../../../")
    
    return None


def extract_crash_tc(fd_name, table):
    print("[INFO] ParaSuit : Checking crashed testcases from %s directory" % (fd_name))
    with open('./%s/errors' % (fd_name), 'r', encoding='ISO-8859-1') as err_file:
        lines = err_file.read()
        lines = lines.split("KLEE-REPLAY: NOTE: ")
    
    result_file = open("./%s" %(table), 'w', encoding='ISO-8859-1')
    found_bug = dict()

    for l in range(len(lines)):
        if "Test file:" in lines[l]:
            test_file = lines[l]
            idx_tf = test_file.find("/%s" % (fd_name))
            tc_path = test_file[idx_tf:-1]

        elif "Arguments:" in lines[l]:
            arguments = lines[l]
            idx_arg = arguments.find('"')
            args = arguments[idx_arg:-1]

        elif "EXIT STATUS:" in lines[l]:
            if "CRASHED" in lines[l]:
                crashed_sig = lines[l]
                idx_cr_start = crashed_sig.find('CRASHED')
                idx_cr_end = crashed_sig.find('(')
                crash_signal = crashed_sig[idx_cr_start:idx_cr_end - 1]
                
                tc_idx = tc_path.find("test")
                tc_idx_e = tc_path.find(".ktest")
                path_dir = tc_path[:tc_idx]
                path_file = tc_path[tc_idx:tc_idx_e]

                crashed_fd = os.listdir("./%s" % path_dir)
                crashed_file = False
                
                for item in crashed_fd:
                    if (path_file in item) and (".err" in item):
                        crashed_file = item
                        break
                        
                if crashed_file:
                    with open("./%s/%s" % (path_dir, crashed_file), 'r') as final:
                        final_line = final.read()
                        final_list = final_line.split("\n")
                        for fn in final_list:
                            if "File:" in fn:
                                crashed_loc = fn
                            elif "Line:" in fn:
                                crashed_line = fn
                    bug = "%s, %s" % (crashed_loc, crashed_line)
                    if bug not in found_bug.keys():
                        result_file.write("TestCase : %s\n" % tc_path)
                        result_file.write("Arguments : %s\n" % args)
                        result_file.write(crash_signal)
                        result_file.write('\n')
                        result_file.write(crashed_loc)
                        result_file.write('\n')
                        result_file.write(crashed_line)
                        result_file.write('\n')
                        result_file.write('\n')

                        found_bug[bug] = 1
                    
                    else:
                        found_bug[bug] += 1

                else:
                    print("[Warnings] ParaSuit : There is no CRASHED FILE! | File Path :", tc_path)
    return None



def main(*argv):
    parser = ArgumentParser()
    parser.add_argument('directories', nargs='*', type=str, metavar='DIRS',
                        help='directory generated by ParaSuit')
    parser.add_argument('--benchmark', default='-', type=str, metavar='STR',
                        help='directory of target program (e.g., grep-3.4)')
    parser.add_argument('--table', default='bug_result.txt', type=str, metavar='PATH',
                        help='path to save bug table (default=bug_result.txt)')

    args = parser.parse_args(argv)

    src = src_dir(args.benchmark)
    err_files = collect_err_files(args.directories)

    for fd_name in args.directories:
        log_err_replays(fd_name, err_files, args.benchmark, src)
        extract_crash_tc(fd_name, args.table)


    print("[INFO] ParaSuit : The detected bugs were saved in “%s” file." % (args.table))



if __name__ == '__main__':
    main(*sys.argv[1:])
