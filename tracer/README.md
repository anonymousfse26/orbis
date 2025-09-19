# ORBiS - Tracer

To extract option-related data, you can use the tracer we shared.
 

## Build Tracer
To build the tracer, use the following command.
```
/orbis/tracer$ c++ -fPIC -shared tracer.cpp -o tracer.so $(llvm-config-6.0 --cxxflags) -O2 $(llvm-config-6.0 --ldflags --libs core irreader analysis transformutils support)
```

Then, you will see the 'tracer.so' file in the same directory.

Now, you can make the traceable execution file of the target program (e.g., ls-8.32).

```
/orbis/tracer$ chmod +x build_pgm.sh
/orbis/tracer$ ./build_pgm.sh -p ls -b ../benchmarks/coreutils-8.32/obj-llvm/src/ls.bc
```

By running this command, the traceable execution file is generated in the directory: '/tracer/execs'. 

Using this execution file, the result will be as followed:
```
/orbis/tracer/execs$ ./ls_trace
("main", "argc", 1, "../benchmarks/coreutils-8.32/obj-llvm/../src/ls.c")
("initialize_exit_failure", "status", 2, "../benchmarks/coreutils-8.32/obj-llvm/../src/system.h")
("initialize_exit_failure", "exit_failure", 2, "../benchmarks/coreutils-8.32/obj-llvm/../src/system.h")
...
```
which is the set of tuples that are constructed with (function, variable, value, and path).

Finally, by running run.py, option-related branches are extracted, and ORBiS ultimately generates a JSON file. The roles of each option are as follows.

+ --program : The target program for extracting option-related branches (Default : None)
+ --start-arg : The arguments that is placed before the execution program to generate a valid argument (Default : None)
+ --end-arg : The arguments that is placed after the execution program to generate a valid argument (Default : None)
+ --src-depth : The depth from the directory where gcov is built to the directory where the execution file is defined (Default : 1)
+ gcov_obj : The path of the execution file that generates the .gcda files


For example, in the case of ls-8.32, you can extract the option-related branches by executing the following command.

```
/orbis/tracer$ python3 run.py -p ls ../benchmarks/coreutils-8.32/obj-gcov1/src/ls
```
