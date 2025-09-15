//===-- klee-replay.c -----------------------------------------------------===//
//
//                     The KLEE Symbolic Virtual Machine
//
// This file is distributed under the University of Illinois Open Source
// License. See LICENSE.TXT for details.
//
//===----------------------------------------------------------------------===//

// Replaced : klee/tools/klee-replay/klee-replay.c

#include "klee-replay.h"
#include "klee/Internal/ADT/KTest.h"

#include <assert.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include <sys/stat.h>
#include <sys/wait.h>

#if defined(__APPLE__) || defined(__FreeBSD__)
#include <signal.h>
#define fgetc_unlocked(x) fgetc (x)
#define fputc_unlocked(x,y) fputc (x,y)
#else
#include <sys/signal.h>
#endif

#ifdef HAVE_SYS_CAPABILITY_H
#include <sys/capability.h>
#endif

/* --- New options --- */
enum insert_pos_e { INSERT_OFF=0, INSERT_BEFORE=1, INSERT_AFTER=2 };

static enum insert_pos_e opt_insert_pos = INSERT_OFF; /* --insert-symfiles-argv */
static int  opt_sym_file_idx = -1;                    /* --sym-file-idx (1-based) */
static int  opt_map_empty_arg_to_file = 0;            /* --map-empty-arg-to-file */
static int  opt_dot_slash_files = 0;                  /* --dot-slash-files */

/* unique codes for long-only options */
enum {
  OPT_INSERT_SYMFILES_ARGV = 256,
  OPT_SYM_FILE_IDX,
  OPT_MAP_EMPTY_ARG_TO_FILE,
  OPT_DOT_SLASH_FILES,
  OPT_EXTRA_ARGV,
  OPT_EXTRA_ARGV_IDX,
  OPT_EXTRA_ARGV_POS,
  OPT_DROP_EMPTY_ARGS
};

static void __emit_error(const char *msg);

static KTest* input;
static unsigned obj_index;

static const char *progname = 0;
static unsigned monitored_pid = 0;
static unsigned monitored_timeout;
static int opt_drop_empty_args = 0;

static char *rootdir = NULL;
static struct option long_options[] = {
  {"create-files-only", required_argument, 0, 'f'},
  {"chroot-to-dir", required_argument, 0, 'r'},
  {"help", no_argument, 0, 'h'},
  {"keep-replay-dir", no_argument, 0, 'k'},
  {"insert-symfiles-argv", required_argument, 0, OPT_INSERT_SYMFILES_ARGV}, 
  {"sym-file-idx",         required_argument, 0, OPT_SYM_FILE_IDX},
  {"map-empty-arg-to-file",no_argument,       0, OPT_MAP_EMPTY_ARG_TO_FILE},
  {"dot-slash-files",      no_argument,       0, OPT_DOT_SLASH_FILES},
  {"extra-argv",      required_argument, 0, OPT_EXTRA_ARGV},      /* repeatable */
  {"extra-argv-idx",  required_argument, 0, OPT_EXTRA_ARGV_IDX},  /* 1-based */
  {"extra-argv-pos",  required_argument, 0, OPT_EXTRA_ARGV_POS},  /* off|before|after */
  {"drop-empty-args",   no_argument,       0, OPT_DROP_EMPTY_ARGS},
  {0, 0, 0, 0},
};

static void stop_monitored(int process) {
  fputs("KLEE-REPLAY: NOTE: TIMEOUT: ATTEMPTING GDB EXIT\n", stderr);
  int pid = fork();
  if (pid < 0) {
    fputs("KLEE-REPLAY: ERROR: gdb_exit: fork failed\n", stderr);
  } else if (pid == 0) {
    /* Run gdb in a child process. */
    const char *gdbargs[] = {
      "/usr/bin/gdb",
      "--pid", "",
      "-q",
      "--batch",
      "--eval-command=call exit(1)",
      0,
      0
    };
    char pids[64];
    snprintf(pids, sizeof(pids), "%d", process);

    gdbargs[2] = pids;
    /* Make sure gdb doesn't talk to the user */
    close(0);

    fputs("KLEE-REPLAY: NOTE: RUNNING GDB: ", stderr);
    unsigned i;
    for (i = 0; i != 5; ++i)
      fprintf(stderr, "%s ", gdbargs[i]);
    fputc('\n', stderr);

    execvp(gdbargs[0], (char * const *) gdbargs);
    perror("execvp");
    _exit(66);
  } else {
    /* Parent process, wait for gdb to finish. */
    int res, status;
    do {
      res = waitpid(pid, &status, 0);
    } while (res < 0 && errno == EINTR);

    if (res < 0) {
      perror("waitpid");
      _exit(66);
    }
  }
}

static void int_handler(int signal) {
  fprintf(stderr, "KLEE-REPLAY: NOTE: %s: Received signal %d.  Killing monitored process(es)\n",
          progname, signal);
  if (monitored_pid) {
    stop_monitored(monitored_pid);
    /* Kill the process group of monitored_pid.  Since we called
       setpgrp() for pid, this will not kill us, or any of our
       ancestors */
    kill(-monitored_pid, SIGKILL);
  } else {
    _exit(99);
  }
}

static void timeout_handler(int signal) {
  fprintf(stderr, "KLEE-REPLAY: NOTE: EXIT STATUS: TIMED OUT (%d seconds)\n",
          monitored_timeout);
  if (monitored_pid) {
    stop_monitored(monitored_pid);
    /* Kill the process group of monitored_pid.  Since we called
       setpgrp() for pid, this will not kill us, or any of our
       ancestors */
    kill(-monitored_pid, SIGKILL);
  } else {
    _exit(88);
  }
}

void process_status(int status, time_t elapsed, const char *pfx) {
  if (pfx)
    fprintf(stderr, "KLEE-REPLAY: NOTE: %s: ", pfx);
  if (WIFSIGNALED(status)) {
    fprintf(stderr, "KLEE-REPLAY: NOTE: EXIT STATUS: CRASHED signal %d (%d seconds)\n",
            WTERMSIG(status), (int) elapsed);
    _exit(77);
  } else if (WIFEXITED(status)) {
    int rc = WEXITSTATUS(status);

    char msg[64];
    if (rc == 0) {
      strcpy(msg, "NORMAL");
    } else {
      snprintf(msg, sizeof(msg), "ABNORMAL %d", rc);
    }
    fprintf(stderr, "KLEE-REPLAY: NOTE: EXIT STATUS: %s (%d seconds)\n", msg, (int) elapsed);
    _exit(rc);
  } else {
    fprintf(stderr, "KLEE-REPLAY: NOTE: EXIT STATUS: NONE (%d seconds)\n", (int) elapsed);
    _exit(0);
  }
}

/* This function assumes that executable is a path pointing to some existing
 * binary and rootdir is a path pointing to some directory.
 */
static inline char *strip_root_dir(char *executable, char *rootdir) {
  return executable + strlen(rootdir);
}

static void run_monitored(char *executable, int argc, char **argv) {
  int pid;
  const char *t = getenv("KLEE_REPLAY_TIMEOUT");
  if (!t)
    t = "10000000";
  monitored_timeout = atoi(t);

  if (monitored_timeout==0) {
    fprintf(stderr, "KLEE-REPLAY: ERROR: invalid timeout (%s)\n", t);
    _exit(1);
  }

  /* Kill monitored process(es) on SIGINT and SIGTERM */
  signal(SIGINT, int_handler);
  signal(SIGTERM, int_handler);

  signal(SIGALRM, timeout_handler);
  pid = fork();
  if (pid < 0) {
    perror("fork");
    _exit(66);
  } else if (pid == 0) {
    /* This process actually executes the target program.
     *
     * Create a new process group for pid, and the process tree it may spawn. We
     * do this, because later on we might want to kill pid _and_ all processes
     * spawned by it and its descendants.
     */
#ifndef __FreeBSD__
    setpgrp();
#else
    setpgrp(0, 0);
#endif

    if (!rootdir) {
      if (chdir(replay_dir) != 0) {
        perror("chdir");
        _exit(66);
      }

      execv(executable, argv);
      perror("execv");
      _exit(66);
    }

    fprintf(stderr, "KLEE-REPLAY: NOTE: rootdir: %s\n", rootdir);
    const char *msg;
    if ((msg = "chdir", chdir(rootdir) == 0) &&
      (msg = "chroot", chroot(rootdir) == 0)) {
      msg = "execv";
      executable = strip_root_dir(executable, rootdir);
      argv[0] = strip_root_dir(argv[0], rootdir);
      execv(executable, argv);
    }
    perror(msg);
    _exit(66);
  } else {
    /* Parent process which monitors the child. */
    int res, status;
    time_t start = time(0);
    sigset_t masked;

    sigemptyset(&masked);
    sigaddset(&masked, SIGALRM);

    monitored_pid = pid;
    alarm(monitored_timeout);
    do {
      res = waitpid(pid, &status, 0);
    } while (res < 0 && errno == EINTR);

    if (res < 0) {
      perror("waitpid");
      _exit(66);
    }

    /* Just in case, kill the process group of pid.  Since we called setpgrp()
       for pid, this will not kill us, or any of our ancestors */
    kill(-pid, SIGKILL);
    process_status(status, time(0) - start, 0);
  }
}

#ifdef HAVE_SYS_CAPABILITY_H
/* ensure this process has CAP_SYS_CHROOT capability. */
void ensure_capsyschroot(const char *executable) {
  cap_t caps = cap_get_proc();  // all current capabilities.
  cap_flag_value_t chroot_permitted, chroot_effective;

  if (!caps)
    perror("cap_get_proc");
  /* effective and permitted flags should be set for CAP_SYS_CHROOT. */
  cap_get_flag(caps, CAP_SYS_CHROOT, CAP_PERMITTED, &chroot_permitted);
  cap_get_flag(caps, CAP_SYS_CHROOT, CAP_EFFECTIVE, &chroot_effective);
  if (chroot_permitted != CAP_SET || chroot_effective != CAP_SET) {
    fputs("KLEE-REPLAY: ERROR: chroot: No CAP_SYS_CHROOT capability.\n", stderr);
    exit(1);
  }
  cap_free(caps);
}
#endif

static void usage(void) {
  fprintf(stderr,
    "Usage: %s [option]... <executable> <ktest-file>...\n"
    "   or: %s --create-files-only <ktest-file>\n"
    "\n"
    "-r, --chroot-to-dir=DIR   use chroot jail, requires CAP_SYS_CHROOT\n"
    "-k, --keep-replay-dir     do not delete replay directory\n"
    "-h, --help                display this help and exit\n"
    "\n"
    "--insert-symfiles-argv={off|before|after}\n"
    "                          insert created sym-file names into argv\n"
    "--sym-file-idx=N          insert sym-file names at 1-based argv index N\n"
    "                          (overrides --insert-symfiles-argv)\n"
    "--map-empty-arg-to-file   replace empty argv tokens (\"\") with unused\n"
    "                          sym-file names\n"
    "--dot-slash-files         insert ./A instead of A\n"
    "--extra-argv=TOKEN        append an extra argv token (repeatable)\n"
    "--extra-argv-idx=N        insert extra argv tokens at 1-based index N\n"
    "                          (overrides --extra-argv-pos)\n"
    "--extra-argv-pos={off|before|after}\n"
    "                          where to insert extra argv when idx not given\n"
    "--drop-empty-args         remove empty argv tokens (\"\") from ktest argv\n"
    "\n"
    "Use KLEE_REPLAY_TIMEOUT environment variable to set a timeout (in seconds).\n",
    progname, progname);
  exit(1);
}

int keep_temps = 0;

/* ========= Simple string list ========= */
typedef struct {
  char **v;
  size_t n, cap;
} strlist_t;

static void sl_init(strlist_t *s) { s->v=NULL; s->n=0; s->cap=0; }
static void sl_free(strlist_t *s) {
  if (!s) return;
  for (size_t i=0;i<s->n;i++) free(s->v[i]);
  free(s->v);
  s->v=NULL; s->n=0; s->cap=0;
}
static void sl_push(strlist_t *s, const char *z) {
  if (s->n==s->cap) {
    size_t nc = s->cap? s->cap*2 : 8;
    char **nv = (char**)realloc(s->v, nc * sizeof(char*));
    if (!nv) { perror("realloc"); exit(1); }
    s->v = nv; s->cap = nc;
  }
  s->v[s->n++] = strdup(z);
}

/* ========= File copy ========= */
static int copy_file(const char *src, const char *dst) {
  int in = open(src, O_RDONLY);
  if (in < 0) { perror("open(src)"); return -1; }
  int out = open(dst, O_WRONLY|O_CREAT|O_TRUNC, 0644);
  if (out < 0) { perror("open(dst)"); close(in); return -1; }

  char buf[8192];
  ssize_t r;
  while ((r = read(in, buf, sizeof(buf))) > 0) {
    ssize_t w = write(out, buf, (size_t)r);
    if (w != r) { perror("write"); close(in); close(out); return -1; }
  }
  if (r < 0) { perror("read"); }
  close(in); close(out);
  return (r<0) ? -1 : 0;
}

/* ========= Clone sym-files in replay_dir -> /tmp/<dir>, collect absolute paths ========= */
static void clone_symfiles_to_tmp(char out_tmpdir[PATH_MAX], strlist_t *out_paths) {
  sl_init(out_paths);

  char tmpl[] = "/tmp/klee-symfiles-XXXXXX";
  char *tmpdir = mkdtemp(tmpl);
  if (!tmpdir) { perror("mkdtemp"); exit(1); }
  strncpy(out_tmpdir, tmpdir, PATH_MAX);
  out_tmpdir[PATH_MAX-1] = '\0';

  DIR *d = opendir(replay_dir);
  if (!d) { perror("opendir(replay_dir)"); exit(1); }

  struct dirent *ent;
  while ((ent = readdir(d)) != NULL) {
    const char *nm = ent->d_name;
    if (nm[0]=='.') continue;
    if (nm[1] != '\0') continue;
    if (nm[0] < 'A' || nm[0] > 'Z') continue;

    char src[PATH_MAX], dst[PATH_MAX];
    snprintf(src, sizeof(src), "%s/%s", replay_dir, nm);

    struct stat st;
    if (stat(src, &st) != 0) continue;
    if (!S_ISREG(st.st_mode)) continue;

    snprintf(dst, sizeof(dst), "%s/%s", out_tmpdir, nm);
    if (copy_file(src, dst) == 0) {
      sl_push(out_paths, dst);
    }
  }
  closedir(d);
}

/* ========= Rebuild argv with inserted paths ========= */
static void rebuild_argv_with_paths(int *pargc, char ***pargv, const strlist_t *paths) {
  if (!pargc || !pargv || !paths) return;
  if (paths->n == 0) return;

  int argc0 = *pargc;
  char **argv0 = *pargv;

  strlist_t toks; sl_init(&toks);
  for (int i=0;i<argc0;i++) sl_push(&toks, argv0[i]);

  size_t pidx = 0;
  if (opt_map_empty_arg_to_file) {
    for (size_t i=1; i<toks.n && pidx<paths->n; ++i) {
      if (toks.v[i][0] == '\0') {
        free(toks.v[i]);
        toks.v[i] = strdup(paths->v[pidx++]);
      }
    }
  }

  size_t insert_pos;
  if (opt_sym_file_idx >= 1) {
    size_t want = (size_t)opt_sym_file_idx;
    insert_pos = (want > toks.n) ? toks.n : want;
  } else {
    if (opt_insert_pos == INSERT_BEFORE) insert_pos = (toks.n>=1 ? 1 : 0);
    else if (opt_insert_pos == INSERT_AFTER) insert_pos = toks.n;
    else { sl_free(&toks); return; } /* off */
  }

  for (; pidx < paths->n; ++pidx) {
    const char *z = paths->v[pidx];
    sl_push(&toks, "");
    for (size_t j=toks.n-1; j>insert_pos; --j) {
      char *tmp = toks.v[j]; toks.v[j] = toks.v[j-1]; toks.v[j-1] = tmp;
    }
    free(toks.v[insert_pos]);
    toks.v[insert_pos] = strdup(z);
    insert_pos++;
  }

  char **nv = (char**)malloc((toks.n+1)*sizeof(char*));
  if (!nv) { perror("malloc"); exit(1); }
  for (size_t i=0;i<toks.n;i++) nv[i] = strdup(toks.v[i]);
  nv[toks.n] = NULL;

  *pargc = (int)toks.n;
  *pargv = nv;

  sl_free(&toks);
}

static void rebuild_argv_with_extras(int *pargc, char ***pargv,
                                     const strlist_t *extras,
                                     int extra_idx, enum insert_pos_e extra_pos) {
  if (!pargc || !pargv || !extras) return;
  if (extras->n == 0) return;

  int argc0 = *pargc;
  char **argv0 = *pargv;

  /* copy argv into a growable list */
  strlist_t toks; sl_init(&toks);
  for (int i=0;i<argc0;i++) sl_push(&toks, argv0[i]);

  /* decide insertion point */
  size_t insert_pos;
  if (extra_idx >= 1) {
    size_t want = (size_t)extra_idx; /* 1-based: 1 == after argv[0] */
    insert_pos = (want > toks.n) ? toks.n : want;
  } else {
    if (extra_pos == INSERT_BEFORE) insert_pos = (toks.n>=1 ? 1 : 0);
    else if (extra_pos == INSERT_AFTER) insert_pos = toks.n;
    else { sl_free(&toks); return; } /* off */
  }

  /* insert tokens in order */
  for (size_t p=0; p<extras->n; ++p) {
    const char *z = extras->v[p];
    sl_push(&toks, ""); /* grow by one */
    for (size_t j=toks.n-1; j>insert_pos; --j) {
      char *tmp = toks.v[j]; toks.v[j] = toks.v[j-1]; toks.v[j-1] = tmp;
    }
    free(toks.v[insert_pos]);
    toks.v[insert_pos] = strdup(z);
    insert_pos++;
  }

  /* build new char** argv */
  char **nv = (char**)malloc((toks.n+1)*sizeof(char*));
  if (!nv) { perror("malloc"); exit(1); }
  for (size_t i=0;i<toks.n;i++) nv[i] = strdup(toks.v[i]);
  nv[toks.n] = NULL;

  *pargc = (int)toks.n;
  *pargv = nv;
  sl_free(&toks);
}

/* ========= Drop empty argv tokens (except argv[0]) ========= */
static void rebuild_argv_drop_empty(int *pargc, char ***pargv) {
  if (!pargc || !pargv) return;
  int argc0 = *pargc;
  char **argv0 = *pargv;
  if (argc0 <= 1) return;

  strlist_t toks; sl_init(&toks);
  sl_push(&toks, argv0[0]);

  for (int i = 1; i < argc0; ++i) {
    const char *s = argv0[i];
    if (!s) continue;
    if (s[0] == '\0') continue;
    sl_push(&toks, s);
  }

  char **nv = (char**)malloc((toks.n + 1) * sizeof(char*));
  if (!nv) { perror("malloc"); exit(1); }
  for (size_t i=0;i<toks.n;i++) nv[i] = strdup(toks.v[i]);
  nv[toks.n] = NULL;

  *pargc = (int)toks.n;
  *pargv = nv;
  sl_free(&toks);
}



int main(int argc, char** argv) {
  int prg_argc;
  char ** prg_argv;

  progname = argv[0];
  strlist_t extra_argv; sl_init(&extra_argv);
  int extra_idx = -1;
  enum insert_pos_e extra_pos = INSERT_OFF;

  if (argc < 3)
    usage();

  int c, opt_index;
  while ((c = getopt_long(argc, argv, "f:r:k", long_options, &opt_index)) != -1) {
    switch (c) {
    case 'f': {
      /* Special case hack for only creating files and not actually executing
       * the program. */
      if (argc != 3)
        usage();

      char *input_fname = optarg;

      input = kTest_fromFile(input_fname);
      if (!input) {
        fprintf(stderr, "KLEE-REPLAY: ERROR: input file %s not valid.\n", input_fname);
        exit(1);
      }

      prg_argc = input->numArgs;
      prg_argv = input->args;
      prg_argv[0] = argv[1];
      klee_init_env(&prg_argc, &prg_argv);

      replay_create_files(&__exe_fs);
      char tmp_symdir[PATH_MAX] = {0};
      strlist_t sym_paths; sl_init(&sym_paths);

      clone_symfiles_to_tmp(tmp_symdir, &sym_paths);

      int new_argc = prg_argc;
      char **new_argv = prg_argv;
      rebuild_argv_with_paths(&new_argc, &new_argv, &sym_paths);

      if (opt_drop_empty_args) {
        int argc1 = new_argc;
        char **argv1 = new_argv;
        rebuild_argv_drop_empty(&new_argc, &new_argv);
        if (new_argv != argv1) {
          for (int i=0;i<argc1;i++) free(argv1[i]);
          free(argv1);
        }
      }

      {
        int argc1 = new_argc;
        char **argv1 = new_argv;
        rebuild_argv_with_extras(&new_argc, &new_argv, &extra_argv, extra_idx, extra_pos);
        if (new_argv != argv1) {
          for (int i=0;i<argc1;i++) free(argv1[i]);
          free(argv1);
        }
      }

      fprintf(stderr, "KLEE-REPLAY: NOTE: Using argv: ");
      for (int i=0;i<new_argc;i++) fprintf(stderr, "\"%s\" ", new_argv[i]);
      fputc('\n', stderr);
      

      return 0;
    }

    case 'r':
      rootdir = optarg;
      break;

    case 'k':
      keep_temps = 1;
      break;

    case OPT_INSERT_SYMFILES_ARGV: {
      if (strcmp(optarg, "off")==0)      opt_insert_pos = INSERT_OFF;
      else if (strcmp(optarg, "before")==0) opt_insert_pos = INSERT_BEFORE;
      else if (strcmp(optarg, "after")==0)  opt_insert_pos = INSERT_AFTER;
      else {
        fprintf(stderr, "KLEE-REPLAY: ERROR: invalid value for --insert-symfiles-argv: %s\n", optarg);
        exit(1);
      }
      break;
    }

    case OPT_SYM_FILE_IDX: {
      opt_sym_file_idx = atoi(optarg);
      if (opt_sym_file_idx < 1) {
        fprintf(stderr, "KLEE-REPLAY: ERROR: --sym-file-idx must be >= 1 (got %d)\n", opt_sym_file_idx);
        exit(1);
      }
      break;
    }

    case OPT_MAP_EMPTY_ARG_TO_FILE:
      opt_map_empty_arg_to_file = 1;
      break;

    case OPT_DOT_SLASH_FILES:
      opt_dot_slash_files = 1;
      break;
    
    case OPT_EXTRA_ARGV:
      sl_push(&extra_argv, optarg);
      break;

    case OPT_EXTRA_ARGV_IDX:
      extra_idx = atoi(optarg);
      if (extra_idx < 1) {
        fprintf(stderr, "KLEE-REPLAY: ERROR: --extra-argv-idx must be >= 1 (got %d)\n", extra_idx);
        exit(1);
      }
      break;

    case OPT_EXTRA_ARGV_POS:
      if      (strcmp(optarg,"off")==0)    extra_pos = INSERT_OFF;
      else if (strcmp(optarg,"before")==0) extra_pos = INSERT_BEFORE;
      else if (strcmp(optarg,"after")==0)  extra_pos = INSERT_AFTER;
      else {
        fprintf(stderr, "KLEE-REPLAY: ERROR: invalid --extra-argv-pos: %s\n", optarg);
        exit(1);
      }
      break;
    case OPT_DROP_EMPTY_ARGS:
      opt_drop_empty_args = 1;
      break;
    }
  }

  // Executable needs to be converted to an absolute path, as klee-replay calls
  // chdir just before executing it
  char executable[PATH_MAX];
  if (!realpath(argv[optind], executable)) {
    snprintf(executable, PATH_MAX, "KLEE-REPLAY: ERROR: executable %s:",
             argv[optind]);
    perror(executable);
    exit(1);
  }
  /* Normal execution path ... */

  /* make sure this process has the CAP_SYS_CHROOT capability, if possible. */
#ifdef HAVE_SYS_CAPABILITY_H
  if (rootdir)
    ensure_capsyschroot(progname);
#endif

  /* rootdir should be a prefix of executable's path. */
  if (rootdir && strstr(executable, rootdir) != executable) {
    fputs("KLEE-REPLAY: ERROR: chroot: root dir should be a parent dir of executable.\n", stderr);
    exit(1);
  }

  int idx = 0;
  for (idx = optind + 1; idx != argc; ++idx) {
    char* input_fname = argv[idx];
    unsigned i;

    input = kTest_fromFile(input_fname);
    if (!input) {
      fprintf(stderr, "KLEE-REPLAY: ERROR: input file %s not valid.\n",
              input_fname);
      exit(1);
    }

    obj_index = 0;
    prg_argc = input->numArgs;
    prg_argv = input->args;
    prg_argv[0] = argv[optind];
    klee_init_env(&prg_argc, &prg_argv);
    if (idx > 2)
      fputc('\n', stderr);
    fprintf(stderr, "KLEE-REPLAY: NOTE: Test file: %s\n"
                    "KLEE-REPLAY: NOTE: Arguments: ", input_fname);
    for (i=0; i != (unsigned) prg_argc; ++i) {
      char *s = prg_argv[i];
      if (s[0]=='A' && s[1] && !s[2]) s[1] = '\0';
      fprintf(stderr, "\"%s\" ", prg_argv[i]);
    }
    fputc('\n', stderr);

    /* Create the input files, pipes, etc. */
    replay_create_files(&__exe_fs);
    char tmp_symdir[PATH_MAX] = {0};
    strlist_t sym_paths; sl_init(&sym_paths);

    clone_symfiles_to_tmp(tmp_symdir, &sym_paths);

    int new_argc = prg_argc;
    char **new_argv = prg_argv;
    rebuild_argv_with_paths(&new_argc, &new_argv, &sym_paths);

    if (opt_drop_empty_args) {
      int argc1 = new_argc;
      char **argv1 = new_argv;
      rebuild_argv_drop_empty(&new_argc, &new_argv);
      if (new_argv != argv1) {
        for (int i=0;i<argc1;i++) free(argv1[i]);
        free(argv1);
      }
    }
    
    {
      int argc1 = new_argc;
      char **argv1 = new_argv;
      rebuild_argv_with_extras(&new_argc, &new_argv, &extra_argv, extra_idx, extra_pos);
      if (new_argv != argv1) {
        for (int i=0;i<argc1;i++) free(argv1[i]);
        free(argv1);
      }
    }

    {
      fprintf(stderr, "KLEE-REPLAY: NOTE: Using argv: ");
      for (int i=0;i<new_argc;i++) fprintf(stderr, "\"%s\" ", new_argv[i]);
      fputc('\n', stderr);
    }

    /* Run the test case machinery in a subprocess, eventually this parent
       process should be a script or something which shells out to the actual
       execution tool. */
    int pid = fork();
    if (pid < 0) {
      perror("fork");
      _exit(66);
    } else if (pid == 0) {
      /* Run the executable */
      run_monitored(executable, new_argc, new_argv);
      _exit(0);
    } else {
      /* Wait for the executable to finish. */
      int res, status;

      do {
        res = waitpid(pid, &status, 0);
      } while (res < 0 && errno == EINTR);

      // Delete all files in the replay directory
      replay_delete_files();

      if (!keep_temps && tmp_symdir[0]) {
        DIR *dd = opendir(tmp_symdir);
        if (dd) {
          struct dirent *e2;
          char pbuf[PATH_MAX];
          while ((e2 = readdir(dd)) != NULL) {
            if (e2->d_name[0]=='.') continue;
            snprintf(pbuf, sizeof(pbuf), "%s/%s", tmp_symdir, e2->d_name);
            unlink(pbuf);
          }
          closedir(dd);
          rmdir(tmp_symdir);
        }
      }
      if (new_argv != prg_argv) {
        for (int i=0;i<new_argc;i++) free(new_argv[i]);
        free(new_argv);
      }
      sl_free(&sym_paths);

      if (res < 0) {
        perror("waitpid");
        _exit(66);
      }
    }
  }

  sl_free(&extra_argv);
  return 0;
}

/* KLEE functions */

int __fputc_unlocked(int c, FILE *f) {
  return fputc_unlocked(c, f);
}

int __fgetc_unlocked(FILE *f) {
  return fgetc_unlocked(f);
}

int klee_get_errno() {
  return errno;
}

void klee_warning(char *name) {
  fprintf(stderr, "KLEE-REPLAY: klee_warning: %s\n", name);
}

void klee_warning_once(char *name) {
  fprintf(stderr, "KLEE-REPLAY: klee_warning_once: %s\n", name);
}

unsigned klee_assume(uintptr_t x) {
  if (!x) {
    fputs("KLEE-REPLAY: klee_assume(0)!\n", stderr);
  }
  return 0;
}

unsigned klee_is_symbolic(uintptr_t x) {
  return 0;
}

void klee_prefer_cex(void *buffer, uintptr_t condition) {
  ;
}

void klee_posix_prefer_cex(void *buffer, uintptr_t condition) {
  ;
}

void klee_make_symbolic(void *addr, size_t nbytes, const char *name) {
  /* XXX remove model version code once new tests gen'd */
  if (obj_index >= input->numObjects) {
    if (strcmp("model_version", name) == 0) {
      assert(nbytes == 4);
      *((int*) addr) = 0;
    } else {
      __emit_error("ran out of appropriate inputs");
    }
  } else {
    KTestObject *boo = &input->objects[obj_index];

    if (strcmp("model_version", name) == 0 &&
        strcmp("model_version", boo->name) != 0) {
      assert(nbytes == 4);
      *((int*) addr) = 0;
    } else {
      if (boo->numBytes != nbytes) {
        fprintf(stderr, "KLEE-REPLAY: ERROR: make_symbolic mismatch, different sizes: "
           "%d in input file, %lu in code\n", boo->numBytes, (unsigned long)nbytes);
        exit(1);
      } else {
        memcpy(addr, boo->bytes, nbytes);
        obj_index++;
      }
    }
  }
}

/* Redefined here so that we can check the value read. */
int klee_range(int start, int end, const char* name) {
  int r;

  if (start >= end) {
    fputs("KLEE-REPLAY: ERROR: klee_range: invalid range\n", stderr);
    exit(1);
  }

  if (start+1 == end)
    return start;
  else {
    klee_make_symbolic(&r, sizeof r, name);

    if (r < start || r >= end) {
      fprintf(stderr, "KLEE-REPLAY: ERROR: klee_range(%d, %d, %s) returned invalid result: %d\n",
        start, end, name, r);
      exit(1);
    }

    return r;
  }
}

void klee_report_error(const char *file, int line,
                       const char *message, const char *suffix) {
  __emit_error(message);
}

void klee_mark_global(void *object) {
  ;
}

/*** HELPER FUNCTIONS ***/

static void __emit_error(const char *msg) {
  fprintf(stderr, "KLEE-REPLAY: ERROR: %s\n", msg);
  exit(1);
}
