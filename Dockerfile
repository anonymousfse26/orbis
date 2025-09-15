FROM ubuntu:18.04

ARG BASE_DIR=/root/main
ARG SOURCE_DIR=/root/main/
ARG DEBIAN_FRONTEND=noninteractive

# install requirements
RUN apt-get -y update
RUN apt-get install -y build-essential curl libcap-dev git cmake libncurses5-dev python3-minimal unzip libtcmalloc-minimal4 libgoogle-perftools-dev libsqlite3-dev doxygen gcc-multilib g++-multilib wget

# install python3.9.7
RUN apt-get install -y wget build-essential checkinstall libreadline-gplv2-dev libssl-dev tk-dev libgdbm-dev libc6-dev libbz2-dev libffi-dev zlib1g-dev
WORKDIR /root
RUN wget https://www.python.org/ftp/python/3.9.7/Python-3.9.7.tgz
RUN tar xzf Python-3.9.7.tgz
WORKDIR /root/Python-3.9.7
RUN ./configure --enable-optimizations --enable-shared
RUN make install
ENV LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH


RUN apt-get -y install python3-pip
RUN pip3 install --upgrade pip
RUN pip3 install numpy wllvm scikit-learn
RUN apt-get -y install clang-6.0 llvm-6.0 llvm-6.0-dev llvm-6.0-tools
RUN ln -s /usr/bin/clang-6.0 /usr/bin/clang
RUN ln -s /usr/bin/clang++-6.0 /usr/bin/clang++
RUN ln -s /usr/bin/llvm-config-6.0 /usr/bin/llvm-config
RUN ln -s /usr/bin/llvm-link-6.0 /usr/bin/llvm-link

WORKDIR /root

# Install ORBiS
WORKDIR ${BASE_DIR}
RUN git clone https://github.com/anonymousfse26/orbis.git
WORKDIR ${BASE_DIR}/orbis
RUN python3 setup.py install

# Install stp solver
RUN apt-get -y install cmake bison flex libboost-all-dev python perl minisat
WORKDIR ${BASE_DIR}
RUN git clone https://github.com/stp/stp.git
WORKDIR ${BASE_DIR}/stp
RUN git checkout tags/2.3.3
RUN mkdir build
WORKDIR ${BASE_DIR}/stp/build
RUN cmake ..
RUN make
RUN make install

RUN echo "ulimit -s unlimited" >> /root/.bashrc


# install Klee-uclibc
WORKDIR ${BASE_DIR}/orbis
RUN git clone https://github.com/klee/klee-uclibc.git
WORKDIR ${BASE_DIR}/orbis/klee-uclibc
RUN chmod 777 -R *
RUN ./configure --make-llvm-lib
RUN make -j2

# Install KLEE-2.1
WORKDIR ${BASE_DIR}/orbis
RUN mkdir engine
WORKDIR ${BASE_DIR}/orbis/engine
RUN pip install lit
RUN git clone -b 2.1.x https://github.com/klee/klee.git

## Replace KLEE with modified codes.
RUN mv ${BASE_DIR}/orbis/changed/osdi08/ExecutionState.cpp ${BASE_DIR}/orbis/engine/klee/lib/Core/ExecutionState.cpp
RUN mv ${BASE_DIR}/orbis/changed/osdi08/ExecutionState.h ${BASE_DIR}/orbis/engine/klee/include/klee/ExecutionState.h
RUN mv ${BASE_DIR}/orbis/changed/osdi08/Executor.cpp ${BASE_DIR}/orbis/engine/klee/lib/Core/Executor.cpp
RUN mv ${BASE_DIR}/orbis/changed/osdi08/ExprPPrinter.cpp ${BASE_DIR}/orbis/engine/klee/lib/Expr/ExprPPrinter.cpp
RUN mv ${BASE_DIR}/orbis/changed/osdi08/klee-replay.c ${BASE_DIR}/orbis/engine/klee/tools/klee-replay/klee-replay.c
RUN mv ${BASE_DIR}/orbis/changed/osdi08/main.cpp ${BASE_DIR}/orbis/engine/klee/tools/klee/main.cpp

WORKDIR ${BASE_DIR}/orbis
RUN curl -OL https://github.com/google/googletest/archive/release-1.7.0.zip
RUN unzip release-1.7.0.zip
WORKDIR ${BASE_DIR}/orbis/engine/klee
RUN echo "export LLVM_COMPILER=clang" >> /root/.bashrc
RUN echo "export WLLVM_COMPILER=clang" >> /root/.bashrc
RUN echo "KLEE_REPLAY_TIMEOUT=1" >> /root/.bashrc
RUN mkdir build
WORKDIR ${BASE_DIR}/orbis/engine/klee/build
RUN cmake -DENABLE_SOLVER_STP=ON -DENABLE_POSIX_RUNTIME=ON -DENABLE_KLEE_UCLIBC=ON -DKLEE_UCLIBC_PATH=${BASE_DIR}/orbis/klee-uclibc -DENABLE_UNIT_TESTS=ON -DGTEST_SRC_DIR=${BASE_DIR}/orbis/googletest-release-1.7.0 -DLLVM_CONFIG_BINARY=/usr/bin/llvm-config-6.0 -DLLVMCC=/usr/bin/clang-6.0 -DLLVMCXX=/usr/bin/clang++-6.0 ${BASE_DIR}/orbis/engine/klee
RUN make
WORKDIR ${BASE_DIR}/orbis/engine/klee
RUN env -i /bin/bash -c '(source testing-env.sh; env > test.env)'
RUN echo "export PATH=$PATH:/root/main/orbis/engine/klee/build/bin" >> /root/.bashrc


## Install HOMI (FSE'20)
WORKDIR ${BASE_DIR}
RUN git clone https://github.com/kupl/HOMI_public.git
RUN cp -r ${BASE_DIR}/HOMI_public/klee ${BASE_DIR}/orbis/engine/homi

## Replace KLEE with modified codes.
WORKDIR ${BASE_DIR}/engine/homi
RUN mv ${BASE_DIR}/orbis/changed/fse20/ExecutionState.cpp ${BASE_DIR}/orbis/engine/homi/lib/Core/ExecutionState.cpp
RUN mv ${BASE_DIR}/orbis/changed/fse20/ExecutionState.h ${BASE_DIR}/orbis/engine/homi/include/klee/ExecutionState.h
RUN mv ${BASE_DIR}/orbis/changed/fse20/Executor.cpp ${BASE_DIR}/orbis/engine/homi/lib/Core/Executor.cpp
RUN mv ${BASE_DIR}/orbis/changed/fse20/ExprPPrinter.cpp ${BASE_DIR}/orbis/engine/homi/lib/Expr/ExprPPrinter.cpp
RUN mv ${BASE_DIR}/orbis/changed/fse20/klee-replay.c ${BASE_DIR}/orbis/engine/homi/tools/klee-replay/klee-replay.c
RUN mv ${BASE_DIR}/orbis/changed/fse20/main.cpp ${BASE_DIR}/orbis/engine/homi/tools/klee/main.cpp
RUN mv ${BASE_DIR}/orbis/changed/fse20/CMakeLists.txt ${BASE_DIR}/orbis/engine/homi/tools/klee-replay/CMakeLists.txt
RUN mv ${BASE_DIR}/orbis/changed/fse20/Executor.h ${BASE_DIR}/orbis/engine/homi/lib/Core/Executor.h
RUN mv ${BASE_DIR}/orbis/changed/fse20/file-creator.c ${BASE_DIR}/orbis/engine/homi/tools/klee-replay/file-creator.c
RUN mv ${BASE_DIR}/orbis/changed/fse20/klee-replay.h ${BASE_DIR}/orbis/engine/homi/tools/klee-replay/klee-replay.h
RUN mkdir build
WORKDIR ${BASE_DIR}/orbis/engine/homi/build
RUN cmake -DENABLE_SOLVER_STP=ON -DENABLE_POSIX_RUNTIME=ON -DENABLE_KLEE_UCLIBC=ON -DKLEE_UCLIBC_PATH=${BASE_DIR}/orbis/klee-uclibc -DENABLE_UNIT_TESTS=ON -DGTEST_SRC_DIR=${BASE_DIR}/orbis/googletest-release-1.7.0 -DLLVM_CONFIG_BINARY=/usr/bin/llvm-config-6.0 -DLLVMCC=/usr/bin/clang-6.0 -DLLVMCXX=/usr/bin/clang++-6.0 ${BASE_DIR}/orbis/engine/homi
RUN make
WORKDIR ${BASE_DIR}/orbis/engine/homi
RUN env -i /bin/bash -c '(source testing-env.sh; env > test.env)'


## Install Learch (CCS'21)
WORKDIR ${BASE_DIR}
RUN git clone https://github.com/eth-sri/learch.git
RUN cp -r ${BASE_DIR}/learch/klee ${BASE_DIR}/orbis/engine/learch

ENV CPLUS_INCLUDE_PATH=/usr/local/include/python3.9:$CPLUS_INCLUDE_PATH
ENV LIBRARY_PATH=/usr/local/lib:$LIBRARY_PATH
ENV LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH

## Replace KLEE with modified codes.
WORKDIR ${BASE_DIR}/engine/learch
RUN mv ${BASE_DIR}/orbis/changed/ccs21/ExecutionState.cpp ${BASE_DIR}/orbis/engine/learch/lib/Core/ExecutionState.cpp
RUN mv ${BASE_DIR}/orbis/changed/ccs21/ExecutionState.h ${BASE_DIR}/orbis/engine/learch/include/klee/ExecutionState.h
RUN mv ${BASE_DIR}/orbis/changed/ccs21/Executor.cpp ${BASE_DIR}/orbis/engine/learch/lib/Core/Executor.cpp
RUN mv ${BASE_DIR}/orbis/changed/ccs21/ExprPPrinter.cpp ${BASE_DIR}/orbis/engine/learch/lib/Expr/ExprPPrinter.cpp
RUN mv ${BASE_DIR}/orbis/changed/ccs21/klee-replay.c ${BASE_DIR}/orbis/engine/learch/tools/klee-replay/klee-replay.c
RUN mv ${BASE_DIR}/orbis/changed/ccs21/main.cpp ${BASE_DIR}/orbis/engine/learch/tools/klee/main.cpp
RUN mkdir build
WORKDIR ${BASE_DIR}/orbis/engine/learch/build
RUN apt-get update
RUN apt-get install python3-dev
RUN cmake -DENABLE_SOLVER_STP=ON -DENABLE_POSIX_RUNTIME=ON -DENABLE_KLEE_UCLIBC=ON -DKLEE_UCLIBC_PATH=${BASE_DIR}/orbis/klee-uclibc -DENABLE_UNIT_TESTS=ON -DGTEST_SRC_DIR=${BASE_DIR}/orbis/googletest-release-1.7.0 -DLLVM_CONFIG_BINARY=/usr/bin/llvm-config-6.0 -DLLVMCC=/usr/bin/clang-6.0 -DLLVMCXX=/usr/bin/clang++-6.0 -DSQLITE3_INCLUDE_DIR=/usr/include -DSQLITE3_LIBRARY=/usr/lib/x86_64-linux-gnu/libsqlite3.so -DCMAKE_EXE_LINKER_FLAGS="-lsqlite3 -Wl,--no-as-needed" -DCMAKE_BUILD_TYPE=Release -DPYTHON_EXECUTABLE=/usr/local/bin/python3.9 -DPYTHON_INCLUDE_DIR=/usr/local/include/python3.9 -DCMAKE_EXE_LINKER_FLAGS="-lsqlite3 -Wl,--no-as-needed -lpython3.9" -DPYTHON_LIBRARY=/usr/local/lib/libpython3.9.so -DPYTHON_LIBRARIES=/usr/local/lib/libpython3.9.so ${BASE_DIR}/orbis/engine/learch
RUN make
WORKDIR ${BASE_DIR}/orbis/engine/learch
RUN env -i /bin/bash -c '(source testing-env.sh; env > test.env)'


## Install AAQC (ICST'21)
WORKDIR ${BASE_DIR}
RUN git clone https://github.com/davidtr1037/klee-aaqc.git 
RUN cp -r ${BASE_DIR}/learch/klee ${BASE_DIR}/orbis/engine/aaqc

## Replace KLEE with modified codes.
WORKDIR ${BASE_DIR}/engine/aaqc
RUN mv ${BASE_DIR}/orbis/changed/icst21/ExecutionState.cpp ${BASE_DIR}/orbis/engine/aaqc/lib/Core/ExecutionState.cpp
RUN mv ${BASE_DIR}/orbis/changed/icst21/ExecutionState.h ${BASE_DIR}/orbis/engine/aaqc/include/klee/ExecutionState.h
RUN mv ${BASE_DIR}/orbis/changed/icst21/Executor.cpp ${BASE_DIR}/orbis/engine/aaqc/lib/Core/Executor.cpp
RUN mv ${BASE_DIR}/orbis/changed/icst21/ExprPPrinter.cpp ${BASE_DIR}/orbis/engine/aaqc/lib/Expr/ExprPPrinter.cpp
RUN mv ${BASE_DIR}/orbis/changed/icst21/klee-replay.c ${BASE_DIR}/orbis/engine/aaqc/tools/klee-replay/klee-replay.c
RUN mv ${BASE_DIR}/orbis/changed/icst21/main.cpp ${BASE_DIR}/orbis/engine/aaqc/tools/klee/main.cpp
RUN mv ${BASE_DIR}/orbis/changed/icst21/klee-replay.h ${BASE_DIR}/orbis/engine/aaqc/tools/klee-replay/klee-replay.h
RUN mkdir build
WORKDIR ${BASE_DIR}/orbis/engine/aaqc/build
RUN cmake -DENABLE_SOLVER_STP=ON -DENABLE_POSIX_RUNTIME=ON -DENABLE_KLEE_UCLIBC=ON -DKLEE_UCLIBC_PATH=${BASE_DIR}/orbis/klee-uclibc -DENABLE_UNIT_TESTS=ON -DGTEST_SRC_DIR=${BASE_DIR}/orbis/googletest-release-1.7.0 -DLLVM_CONFIG_BINARY=/usr/bin/llvm-config-6.0 -DLLVMCC=/usr/bin/clang-6.0 -DLLVMCXX=/usr/bin/clang++-6.0 -DSQLITE3_INCLUDE_DIR=/usr/include -DSQLITE3_LIBRARY=/usr/lib/x86_64-linux-gnu/libsqlite3.so -DCMAKE_EXE_LINKER_FLAGS="-lsqlite3 -Wl,--no-as-needed -lpython3.9" -DCMAKE_BUILD_TYPE=Release -DPYTHON_EXECUTABLE=/usr/local/bin/python3.9 -DPYTHON_INCLUDE_DIR=/usr/local/include/python3.9 -DPYTHON_LIBRARY=/usr/local/lib/libpython3.9.so ${BASE_DIR}/orbis/engine/learch
RUN make
WORKDIR ${BASE_DIR}/orbis/engine/learch
RUN env -i /bin/bash -c '(source testing-env.sh; env > test.env)'

WORKDIR ${BASE_DIR}/orbis/engine
RUN chmod 777 -R *


## Install Symtuner (ICSE'22)
WORKDIR ${BASE_DIR}/orbis/changed/icse22
RUN python3 setup.py install

# Install Benchmarks (e.g. grep-3.4)
WORKDIR ${BASE_DIR}/orbis/benchmarks
RUN bash building_benchmark.sh grep-3.4

# Initiating Starting Directory
WORKDIR ${BASE_DIR}/orbis/benchmarks
