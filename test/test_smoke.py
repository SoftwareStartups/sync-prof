# Smoke tests for sync-prof


import pytest
import subprocess
import tempfile
import os
import re
import json


class Prog(object):
    "describes program under test"
    def __init__(self, src, compileOpts, outputType, expectedOutput):
        self.src = src
        self.compileOpts = compileOpts
        self.outputType = outputType
        self.expectedOutput = expectedOutput
    def __str__(self):
        return str(self.src) + ' ' + self.outputType


# description of test cases
# - the first two arguments define the sources and compiler flags
# - the third argument in the constructor defines the type of the output (text or chrome)
# - the last argument lists check conditions
testProgs = [
    Prog(['smoke_test_posix.c'],
         ['-pthread'],
         'text',
         [r'Synchronization point occurences:',
          r'pthread_create\s+2',
          r'pthread_join\s+2',
          r'pthread_exit\s+[23]',
          r'pthread_mutex_lock\s+\d+\s+',
          r'pthread_mutex_unlock\s+\d+\s+',
          r'exit\s+1']),
    Prog(['smoke_test_posix.c'],
         ['-pthread'],
         'chrome',
         [{'name': 'pthread_create', 'cat': 'POSIX threads', 'tid': 1},
          {'name': 'pthread_join', 'cat': 'POSIX threads', 'tid': 1},
          {'name': 'pthread_exit', 'cat': 'POSIX threads'},
          {'name': 'pthread_mutex_lock', 'cat': 'POSIX threads'},
          {'name': 'pthread_mutex_unlock', 'cat': 'POSIX threads'},
          {'name': 'locked by m'},
          {'name': 'lock released', 'cat': 'synchronization flow'},
          {'name': 'thread started'},
          {'name': 'thread finished'},
          {'name': 'exit'}]),
    Prog(['weird_thread_graph.c'],
         ['-pthread'],
         'chrome',
         [{'name': 'thread started', 'cat': 'synchronization flow', 'tid': 1},
          {'name': 'thread started', 'cat': 'synchronization flow', 'tid': 2},
          {'name': 'thread started', 'cat': 'synchronization flow', 'tid': 3},
          {'name': 'thread finished', 'tid': 1},
          {'name': 'thread finished', 'tid': 3},
          ]),
    Prog(['semaphore-workers.c'],
         ['-pthread'],
         'text',
         [r'Synchronization point occurences:',
          r'exit\s+1',
          r'sem_init\s+5',
          r'sem_post\s+\d+\s+',
          r'sem_wait\s+\d+\s+']),
    Prog(['semaphore-workers.c'],
         ['-pthread'],
         'chrome',
         [{'name': 'exit'},
          {'name': 'sem_init'},
          {'name': 'sem_post'},
          {'name': 'sem_wait'},
          {'name': 'semaphore increment'}]),
    Prog(['openmp_matmul.c'],
         ['-fopenmp'],
         'text',
         [r'Synchronization point occurences:',
          r'exit\s+1',
          r'GOMP_parallel_start\s+\d+\s+',
          r'GOMP_parallel_end\s+\d+\s+']),
    Prog(['openmp_matmul.c'],
         ['-fopenmp'],
         'chrome',
         [{'name': 'exit'},
          {'name': 'GOMP_parallel_start'},
          {'name': 'GOMP_parallel_end'}]),
    Prog(['deadlock_mutex.c'],
         ['-pthread'],
         'chrome',
         [{'name': 'barrier reached', 'args': {'barrier': 'b'}},
          {'name': 'Event(s) aborted', 'cat': 'WARNING'},
          {'name': 'locked by m1'},
          {'name': 'locked by m2'},
          {'name': 'pthread_mutex_lock'},
          {'name': 'pthread_mutex_lock'}]),
    Prog(['deadlock_sem.c'],
         ['-pthread'],
         'chrome',
         [{'name': 'barrier reached', 'args': {'barrier': 'b'}},
          {'name': 'Event(s) aborted', 'cat': 'WARNING'},
          {'name': 'sem_wait'},
          {'name': 'sem_wait'}]),
    Prog(['livelock.c'],
         ['-pthread'],
         'chrome',
         [{'name': 'barrier reached', 'args': {'barrier': 'b'}},
          {'name': 'pthread_mutex_lock'},
          {'name': 'pthread_mutex_unlock'},
          {'name': 'Event(s) aborted', 'cat': 'WARNING'}]),
    Prog(['condvar.c'],
         ['-pthread'],
         'chrome',
         [{'name': 'condition satisfied', 'args' : {'condition variable': 'cond_var'}},
          # lock functions: 2x in source code and 2x generated for pthread_cond_wait()
          {'name': 'pthread_mutex_lock'},
          {'name': 'pthread_mutex_unlock'},
          {'name': 'pthread_mutex_lock'},
          {'name': 'pthread_mutex_unlock'},
          {'name': 'barrier reached', 'args' : {'barrier': 'barrier'}}])
]


@pytest.fixture(scope="module", params=testProgs)
def testProg(request):
    return request.param


def test_smoke(testProg):
    "check POSIX thread create, join, mutex_lock and mutex_unlock are traced well"
    fd, tempFileName = tempfile.mkstemp()
    _, tempProfile = tempfile.mkstemp()
    os.close(fd)
    try:
        # compile test program
        cmd = ['cc', '-g', '-o', tempFileName] + testProg.src + testProg.compileOpts
        subprocess.check_call(cmd)
        # test sync-prof's tracing
        timeout = 2 # for deadlock tests
        cmd = ['timeout', '%ds' % timeout,
               '../sync-prof',
               '--debug',
               '--output-format', testProg.outputType,
               '--output', tempProfile,
               tempFileName]
        try:
            gdbOutput = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            assert e.returncode == 124, 'exit code not 124 (timeout)'
            gdbOutput = e.output
        # check there are no Python assertions in GDB's output
        assert not ('Python Exception' in gdbOutput), 'Python exception triggered'
        if testProg.outputType == 'text':
            checkText(testProg.expectedOutput, gdbOutput, tempProfile)
        else:
            assert testProg.outputType == 'chrome'
            checkChrome(testProg.expectedOutput, tempProfile)
    finally:
        os.remove(tempFileName)
        os.remove(tempProfile)


def checkText(expectedOutput, gdbOutput, tempProfile):
    "check text output of sync-prof"
    # check expected syncs are in the output
    for s in expectedOutput:
        m = re.search(s, gdbOutput)
        if m is None:
            print(gdbOutput[-200:])
            assert False, '%s not found in sync profile' % s
    # check there is no nesting beyond 3
    with open(tempProfile, 'r') as f:
        output = f.read()
    fourWaitSyncs = '. ' * 4
    assert not fourWaitSyncs in output, 'More than 3 levels of waiting syncs found'


def checkChrome(expectedOutput, tempProfile):
    "check chrome trace output of sync-prof"
    # check expected syncs are in the output
    with open(tempProfile, 'r') as f:
        jsonOutput = json.load(f)
        eventList = jsonOutput['traceEvents']
        for event in eventList:
            for expEvent in expectedOutput:
                expectedEventMatches = all(i in event.items() for i in expEvent.items())
                if expectedEventMatches:
                    index = expectedOutput.index(expEvent)
                    del expectedOutput[index]
    assert expectedOutput == [], 'Dictionaries %s were not found' % str(expectedOutput)
