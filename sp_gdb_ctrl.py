# GDB extension for sync-profiler


import gdb
import re
import sys


debugMode = False
spModel = None
log = None


def main():
    "entry point of the GDB script"
    global outputFile, debugMode, log
    gdbSettings(debugMode)
    configFile, outFile, userCommand, debugMode, outFormat, spDirName, logLevel = \
        parseCmdLineArgs()
    # TODO: elegant solution to discover other sync-prof's modules
    sys.path += [spDirName]
    import sp_util
    import sp_model
    log = sp_util.setupLogging(logLevel)
    # instantiate the model(outFormat)
    global spModel
    spModel = sp_model.SPModel(outFormat, outFile, log)
    # run the analysis
    installBreakpoints(configFile, userCommand)
    # TODO: weird issue: without it terminal gets corrupt at the end of execution
    gdb.execute('start')
    gdb.execute('run')
    printSummary()
    del spModel # should flush the output file buffers
    gdb.execute('quit')


def parseCmdLineArgs():
    "positional arguments from the driver script"
    def getArg(number):
        "returns string for argument number"
        string= str(gdb.history(number))
        # TODO: does not work for userCommand with ''
        m = re.match('^[\'\"](.*)[\'\"]$', string)
        assert m is not None, 'Expected command line argument for gdb'
        return m.group(1)
    configFile = getArg(1)
    outFile = getArg(2)
    userCommand = getArg(3)
    debug = eval(getArg(4))
    outFormat = getArg(5)
    spDirName = getArg(6)
    logLevel = int(getArg(7))
    return configFile, outFile, userCommand, debug, outFormat, spDirName, logLevel


def gdbSettings(debugMode):
    "disable verbose messages in GDB"
    # TODO: analyze the performance impact of pending breakpoints
    gdb.execute('set breakpoint pending on')
    if not debugMode:
        # avoid verbose outputs from GDB:
        gdb.execute('set pagination off')
        gdb.execute('set verbose off')
        gdb.execute('set complaints 0')
        gdb.execute('set confirm off')


def installBreakpoints(configFile, userCommand):
    "install breakpoints for synchronization function"
    # read synchronization functions from the config file
    with open(configFile, 'r') as confFile:
        for fun in confFile:
            fun = fun.strip()
            # Standard configuration function breakpoints are opaque by default.
            # TODO: upgrade the config file to allow opaque specification.
            SPTraceFunction(fun, opaque=False)
            log.info('installed breakpoint on %s' % fun)
    # user-defined commands
    if userCommand != 'None':
        for c in userCommand.split(';'):
            eval(c)
            log.info('executed user command "%s"' % c)


# TODO: awkward place to print the summary. Perhaps, in spView?
# To outFile?
# TODO: use the logger!?
def printSummary():
    "print hit counts for each sync point"
    print('\nSynchronization point occurences:')
    for bp in gdb.breakpoints():
        # finish breakpoints are not printed
        if type(bp) == SPTraceFunctionFinish:
            continue
        count = bp.syncHits
        name = bp.location if bp.type == gdb.BP_BREAKPOINT else bp.expression
        if count > 0:
            print('{:<30}{:<10}'.format(name, count))


class SPTraceFunction(gdb.Breakpoint):
    "Synchronization function breakpoint sub-class"
    def __init__(self, spec, opaque=False):
        super(SPTraceFunction, self).__init__(spec)
        self.opaque = opaque
        self.syncHits = 0
        self.syncPC = None

    def stop (self):
        "report the start of a sync function"
        # If PC has changed, we ignore this breakpoint.
        # The reason is that in some code (C++11) pthread_mutex_lock() (and
        # perhaps others) get relocated by the loader and even split into two
        # breakpoint PCs. Then we select just one, because the other is jumped to
        # instead of a normal call, which breaks nesting in sync-prof.
        # TODO: this works if the multiple sub-breakpoints live in the same
        # call stack. If it's not the case, we have a problem by selecting
        # a single sub-breakpoint.
        pc = gdb.selected_frame().pc()
        if self.syncPC is None:
            self.syncPC = pc
        elif self.syncPC != pc:
            # loader (?) moved this function and added sub-breakpoints
            log.warning('breakpoint "%s" has multiple PCs: 0x%x and 0x%x' % \
                            (self, self.syncPC, pc))
            return False
        self.syncHits += 1
        thread = gdb.selected_thread().num
        # TODO: adapt to support ARM
        arg1 = get('printf "0x%lx", $rdi')
        arg1 = findSymbol(arg1)
        arg2 = get('printf "0x%lx", $rsi')
        arg2 = findSymbol(arg2)
        name = self.location
        filename, line = findSrcLoc(name)
        backtrace = get('backtrace')
        event = spModel.startEvent(name, 'function', thread, arg1, arg2, None, filename,
                                   line, backtrace, self.opaque)
        # event==None means the model skips this event because it happens
        # during another opaque event
        if event is not None:
            # set a finish breakpoint for this call site
            SPTraceFunctionFinish(event)
        return False


class SPTraceFunctionFinish(gdb.FinishBreakpoint):
    "Finish breakpoint for synchronization functions"
    def __init__(self, event):
        # create a new breakpoint for the return address
        super(SPTraceFunctionFinish, self).__init__()
        # remember the parent breakpoint
        self.parent = event
        log.debug('new finish breakpoint %s for event %s' % (self, event.toString()))
    def stop(self):
        "report the end of the parent breakpoint"
        # set new thread ID in the clone event for the model
        if self.parent.evName == 'clone':
            self.__setNewThread(self.parent)
        spModel.stopEvent(self.parent)
        return False
    def __setNewThread(self, event):
        "set newThread to specify parent-child thread relationship"
        osThreadId = get('printf "%d", $rax') # aka LWP
        # TODO: more elegant solution. If called only once
        # I get a [New thread...] message first. Perhaps, I have to
        # disable progress in other threads with "set scheduler..."?
        findResult = get('thread find (LWP %s)' % osThreadId)
        findResult = get('thread find (LWP %s)' % osThreadId)
        assert not findResult.startswith('No threads match'), \
            'Could not determine new thread ID'
        # gdb> thread find (LWP 2134)
        # Thread 2 has target id 'Thread 0x7ffff77fd700 (LWP 2134)'
        findResult = findResult.split()
        event.evNewThread = {'gdb': int(findResult[1]),
                             'pthread_t': findResult[6]}
    def out_of_scope(self):
        "envoked when GDB can not hit the finish breakpoint"
        log.warning('breakpoint %s out of scope' % self)
        # self.stop() # did not work for whatever reason


class SPTraceAccess(gdb.Breakpoint):
    "Watchpoint for accesses to user-defined locations"
    def __init__(self, accessSpec):
        # TODO: wp_class=gdb.WP_READ has no effect; type=gdb.BP_*_WATCHPOINT
        # are not accepted by GDB 7.7 on Ubuntu 14.04
        super(SPTraceAccess, self).__init__(accessSpec,
                                            type=gdb.BP_WATCHPOINT,
                                            wp_class=gdb.WP_ACCESS)
        self.syncHits = 0
        self.syncThread = None
        self.syncName = None

    def stop (self):
        "report the access"
        # TODO: find out read/write and value using: Symbol.value()
        self.syncHits += 1
        value = str(gdb.selected_frame().read_var(self.expression))
        self.syncThread = gdb.selected_thread().num
        self.syncName = 'ACCESS %s' % self.expression
        # TODO: find out the current source location and line
        filename = line = '?'
        backtrace = get('backtrace')
        event = spModel.startEvent(self.syncName,
                                   'access',
                                   self.syncThread,
                                   None,
                                   value,
                                   filename,
                                   line,
                                   backtrace,
                                   False)
        return False


def findSrcLoc(location):
    "return source filename and line for an access"
    symbol, _guard = gdb.lookup_symbol(location)
    if symbol is None:
        filename = line = '?'
    else:
        filename = symbol.symtab.fullname()
        # gdb 7.4 does not always have the line attribute:
        line = symbol.line if hasattr(symbol, 'line') else '?'
    return filename, line


# TODO: rewrite using Python API
def findSymbol(address):
    "find the symbol associated with address"
    gdbStr  = get('info symbol ' + address)
    if gdbStr.startswith('No symbol matches '):
        return address
    else:
        return gdbStr.split()[0]


# TODO: via Python API?
def symbolExists(symbol):
    "return True if symbol exists in the loaded program"
    try:
        get('whatis ' + symbol)
        return True
    except gdb.error:
        return False


def get(string, element=None):
    "helper function to return element from GDB output string"
    s = gdb.execute(string, to_string=True)
    if element is None:
        return s
    else:
        return s.split()[element]


# run the script, handle errors
try:
    main()
except Exception as e:
    log.error('sync-prof encountered an unexpected exception:')
    import traceback
    traceback.print_exc()
    if debugMode:
        import pdb
        pdb.post_mortem()
