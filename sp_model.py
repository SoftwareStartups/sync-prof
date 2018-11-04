# sync-prof's model of synchronization events and their relations


import sys
import sp_view
from sp_util import SPStack


# TODO: remove silly .ev prefixes
class SPSyncEvent(object):
    "captures a single synchronization event"
    def __init__(self, evName, evType, evThread, evArg1, evArg2, evValue, evFilename,
                 evLine, evBacktrace, evOpaque):
        self.evName = evName
        self.evType = evType # function or access
        self.evThread = evThread
        self.evArg1 = evArg1
        self.evArg2 = evArg2
        self.evValue = evValue
        self.evFilename = evFilename
        self.evLine = evLine
        self.evBacktrace = evBacktrace
        self.evOpaque = evOpaque # opaque events do not trace internally
        self.status = 'started'
        self.evNewThread = None # only for clone()
    def __str__(self):
        return '%s %s' % (self.evName, self.evArg1)
    def toString(self):
        return '%s %s thread %d time %d status %s' % \
            (self.evName, self.evArg1, self.evThread, self.startTime, self.status)


class SPModel(object):
    "list of breakpoint stacks pending completion per thread"
    def __init__(self, outFormat, outFile, log):
        # TODO: document this key structure
        self.pendEventDict = {}
        self.time = 0
        self.semPosts = {}
        self.condvarSignals = {}
        self.timeDelta = 1 # synchronization time step
        self.condWaits = ['pthread_cond_wait', 'pthread_cond_timedwait']
        self.View = sp_view.sp_view(outFile, outFormat)
        self.log = log

    def __del__(self):
        self.flushPendEvents()
        del self.View

    def startEvent(self, evName, evType, evThread, evArg1, evArg2, evValue, evFilename,
                   evLine, evBacktrace, evOpaque, generatedEvent=False):
        # TODO: proper implementation for non-nested functions to support complex
        # unstructured control flow with goto, longjmp().
        if not generatedEvent and self.threadOpaque(evThread):
            return None
        event = SPSyncEvent(evName, evType, evThread, evArg1, evArg2, evValue, evFilename,
                            evLine, evBacktrace, evOpaque)
        # TODO: hack to avoid crashing on nested breakpoints with the same argument
        # This case needs a better solution. For now, we ignore an event if its
        event.startTime = self.time
        self.log.debug('startEvent: event=%s' % event.toString())
        self.time += self.timeDelta
        # add new thread if needed
        self.addThreadIfNeeded(event.evThread)
        assert event.evThread in self.pendEventDict, \
            'thread %d not in self.pendEventDict %s' % \
            (event.evThread, self.pendEventDict)
        evList = self.pendEventDict[event.evThread]['events']
        evList.push(event)
        # TODO: assert no duplicates in the all pendEvents lists
        # TODO: more abstract datastruct to ensure the view does not corrupt it
        self.View.timestamp(self.pendEventDict)
        self.generateEvent(event)
        if event.evType == 'access':
            # remove right away, because it is an atomic event
            self.stopEvent(event)
        else:
            event.status = 'waiting'
        # view annotations besides the timestamps
        self.links(event)
        return event # TODO: weird that controller wants it


    def stopEvent(self, event):
        "stop the event and remove it from the waiting stack"
        self.log.debug('stopEvent: event=%s' % event.toString())
        assert event.status != 'finished', 'Event %s must not be finished' % event
        event.status = 'finished'
        event.stopTime = self.time
        self.generateEvent(event)
        self.time += self.timeDelta
        self.View.timestamp(self.pendEventDict)
        # view annotations besides the timestamps
        self.linkThreads(event)
        self.lockBlocks(event)
        self.__dropEvent(event)


    def __dropEvent(self, event):
        "remove the event from the waiting stack"
        threadEvents = self.pendEventDict[event.evThread]['events']
        # TODO: convinience fun: [str(e) for e in threadEvents] or str(self.pendEvents()).
        assert event == threadEvents.top(), \
            'Event %s must be the last element of threadEvents %s' % \
            (event, [str(e) for e in threadEvents])
        threadEvents.pop()

    def abortEvent(self, event):
        "abort the unfinished event and remove it from the waiting stack"
        self.log.info('abortEvent: event=%s' % event)
        # TODO: more robust implementation:
        # flushPendEvents()->stopEvent() may try to stop an event that was at this
        # point marked as finished, when SIGINT is caught by sync-prof. Hence, we
        # need a nice & graceful shutdown mechanism.
        assert event.status != 'aborted', 'Event %s must not be aborted' % event
        event.status = 'aborted'
        event.stopTime = self.time
        self.generateEvent(event)
        self.View.timestamp(self.pendEventDict)
        self.__dropEvent(event)
        # Aborted events did not finish, e.g. due to a deadlock.
        # Hence, such events do not trigger extra view annotations.


    def links(self, event):
        "generate view links between synchronization events"
        semSrcEvNames = ['sem_post']
        semToEvNames = ['sem_wait']
        condvarSrcEvNames = ['pthread_cond_broadcast', 'pthread_cond_signal']
        condvarToEvNames = self.condWaits
        mutexDescr = {'name': 'lock released',
                      'pendEv': ['pthread_mutex_lock'],
                      'argName': 'lock'}
        barrierDescr = {'name': 'barrier reached',
                        'pendEv': ['pthread_barrier_wait'],
                        'argName': 'barrier'}
        pendEventLinkDescs = {'pthread_mutex_unlock': mutexDescr,
                              'pthread_barrier_wait': barrierDescr}
        if event.evName in semSrcEvNames + semToEvNames:
            # semaphores
            self.__link(event,
                        'semaphore increment',
                        'semaphore',
                        semSrcEvNames,
                        semToEvNames,
                        self.semPosts)
        elif event.evName in condvarSrcEvNames + condvarToEvNames:
            # condition variables
            self.__link(event,
                        'condition satisfied',
                        'condition variable',
                        condvarSrcEvNames,
                        condvarToEvNames,
                        self.condvarSignals)
        elif event.evName in pendEventLinkDescs:
            self.__pendEventsLink(event, pendEventLinkDescs[event.evName])

    def linkThreads(self, event):
        "thread create and join links"
        if event.evNewThread is not None:
            newThreadId = event.evNewThread['gdb']
            self.addThreadIfNeeded(newThreadId)
            self.pendEventDict[newThreadId]['pthread_t'] = event.evNewThread['pthread_t']
            self.View.link('synchronization flow',
                           'thread started',
                           event.startTime,
                           event.evThread,
                           self.time, # after increment
                           newThreadId,
                           event.evNewThread)
            # TODO: self.View.mark('thread start'...)?
        elif event.evName == 'pthread_join' and event.status == 'finished':
            # find thread that finished
            threads = [t for t in self.pendEventDict \
                           if self.pendEventDict[t]['pthread_t'] == event.evArg1]
            assert len(threads) == 1, 'Cannot find thread %s to join' % event.evArg1
            thread = threads[0]
            self.View.link('synchronization flow',
                           'thread finished',
                           event.stopTime - self.timeDelta,
                           thread,
                           event.stopTime,
                           event.evThread,
                           {'pthread_t': event.evArg1})
            # TODO: self.View.mark('thread start'...)

    def addThreadIfNeeded(self, thread):
        "add new thread if it's not yet present"
        # TODO: weird to have this function, any better solution?
        if not thread in self.pendEventDict:
            self.pendEventDict[thread] = {'events': SPStack(),
                                          'locks': SPStack(),
                                          'pthread_t': None}

    def __link(self, event, name, arg, srcEvNames, toEvNames, srcEvents):
        "generate links in the view"
        if event.evName in srcEvNames:
            # TODO: FIFO required for each semaphore to support sequencies like:
            #       sem_post, sem_post, sem_wait, sem_wait.
            # sem_wait in progress?
            waitFound = False
            for threadDict in self.pendEventDict.values():
                eventStack = threadDict['events']
                for e in eventStack:
                    if e.evName in toEvNames and e.evArg1 == event.evArg1:
                        waitFound = True # TODO: more elegant code?
                        # indicate (potential) sync flow to the destination
                        extraArgs = {arg: e.evArg1}
                        self.View.link('synchronization flow',
                                       name,
                                       event.startTime,
                                       event.evThread,
                                       self.time, # after increment
                                       e.evThread,
                                       extraArgs)
            if not waitFound:
                # no waiting destination event, so just remember for future
                srcEvents[event.evArg1] = event
        # link to destination events
        elif event.evName in toEvNames:
            if event.evArg1 in srcEvents:
                fromEvent = srcEvents[event.evArg1]
                # link the source event with destination event in the view
                extraArgs = {arg: event.evArg1}
                self.View.link('synchronization flow',
                               name,
                               fromEvent.startTime,
                               fromEvent.evThread,
                               event.startTime,
                               event.evThread,
                               extraArgs)
                srcEvents.pop(event.evArg1, None)

    def __pendEventsLink(self, event, linkDescr):
        "link pending events, such as barriers and locks"
        # TODO: review and revise (written too hastily), add asserts
        for threadDict in self.pendEventDict.values():
            eventStack = threadDict['events']
            if not eventStack.empty():
                pendEvent = eventStack.top()
                if event != pendEvent and \
                        pendEvent.evName in linkDescr['pendEv'] and \
                        event.evArg1 == pendEvent.evArg1:
                    extraArgs = {linkDescr['argName']: event.evArg1}
                    # TODO: rethink when native timing is added
                    stopTime = event.startTime + self.timeDelta
                    self.View.link('synchronization flow',
                                   linkDescr['name'],
                                   event.startTime,
                                   event.evThread,
                                   stopTime,
                                   pendEvent.evThread,
                                   extraArgs)

    def lockBlocks(self, event):
        "find lock-unlock pairs and emit lock blocks in the view"
        # push locks to stacks per thread
        if event.evName in ['pthread_mutex_lock', 'pthread_mutex_trylock']:
            self.pendEventDict[event.evThread]['locks'].push(event)
        # unlocks triggers lock blocks in view
        elif event.evName == 'pthread_mutex_unlock':
            lastLock = self.pendEventDict[event.evThread]['locks'].pop()
            assert lastLock.evThread == event.evThread, 'Lock threads do not match'
            # TODO: in principle the lock-unlocks do not necessarily have to be nicely
            # nested. So, the data structure locks should be more intelligent in
            # matching locks and unlocks than using a simple stack.
            assert lastLock.evArg1 == event.evArg1, \
                'Locks do not match; nesting is broken'
            self.lockBlock(lastLock, event.startTime)


    def lockBlock(self, lockEvent, unlockEvStartTime):
        "emit a lock block"
        extraArgs = {'lock': lockEvent.evArg1}
        name = 'locked by ' + lockEvent.evArg1
        self.View.group('synchronization flow',
                        name,
                        lockEvent.stopTime,
                        lockEvent.evThread,
                        unlockEvStartTime,
                        lockEvent.evThread,
                        extraArgs)


    def generateEvent(self, event):
        "generate new events based on event"
        # condition variable in POSIX imply hidden events"
        if event.evName in self.condWaits:
            if event.status == 'started':
                lockName = event.evArg2
                newEvent = self.startEvent('pthread_mutex_unlock',
                                           'function',
                                           event.evThread,
                                           lockName,
                                           'unknown',
                                           'unknown',
                                           event.evFilename,
                                           event.evLine,
                                           event.evBacktrace,
                                           event.evOpaque,
                                           generatedEvent=True)
                if newEvent is not None:
                    self.stopEvent(newEvent)
            elif event.status == 'finished':
                lockName = event.evArg2
                time = self.time
                # TODO: come up with a more sensible time shift
                self.time -= self.timeDelta
                newEvent = self.startEvent('pthread_mutex_lock',
                                           'function',
                                           event.evThread,
                                           lockName,
                                           'unknown',
                                           'unknown',
                                           event.evFilename,
                                           event.evLine,
                                           event.evBacktrace,
                                           event.evOpaque,
                                           generatedEvent=True)
                self.time = time
                if newEvent is not None:
                    self.stopEvent(newEvent)


    def flushPendEvents(self):
        "force-finish pending events on exit"
        # TODO: workaround for GDB's issue with exit function breakponts
        # which do not trigger the related finish breakpoints. Hence,
        # we artificially inject the finish events for all pending events.
        # TODO: works well for chrome view, for text view it's wrong!
        pendEventPresent = False
        for threadDict in self.pendEventDict.values():
            for event in threadDict['events']:
                self.abortEvent(event)
                if not pendEventPresent:
                    # print only once a warning
                    self.log.warning('Unfinished events at the shutdown')
                pendEventPresent = True
            for lock in threadDict['locks']:
                self.lockBlock(lock, self.time)
        if pendEventPresent:
            self.View.mark('Event(s) aborted', 'WARNING', 'global', self.time, 1)


    def threadOpaque(self, evThread):
        "True if last event in evThread is opaque"
        return evThread in self.pendEventDict and \
            not self.pendEventDict[evThread]['events'].empty() and \
            self.pendEventDict[evThread]['events'].top().evOpaque
