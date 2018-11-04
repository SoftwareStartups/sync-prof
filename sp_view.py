# -*- coding: utf-8 -*-


"""
Printers for the sync-prof events
"""


import json


def sp_view(outFile, outFormat):
    "View factory"
    if outFormat == 'text':
        return SPViewText(outFile)
    else:
        return SPViewChrome(outFile)


class SPView(object):
    "synchronization profile printer"
    def __init__(self, outFileName):
        self.outFileName = outFileName
        self.outFile = open(outFileName, 'w')
    def __del__(self):
        "print summary of synchronization events"
        self.outFile.flush()
        self.outFile.close()
    def link(self, category, name, startTime, startThread, stopTime, stopThread, args):
        pass
    def group(self, category, name, startTime, startThread, stopTime, stopThread, args):
        pass
    def mark(self, name, category, scope, time, thread):
        pass


class SPViewText(SPView):
    "synchronization profile text printer"
    def __init__(self, outFileName):
        self.indent = 40
        super(SPViewText, self).__init__(outFileName)
    def timestamp(self, pendEvents):
        syncString = ''
        threadsSorted = sorted([t for t in pendEvents])
        for thread in threadsSorted:
            eventStack = pendEvents[thread]['events']
            numThreadEvents = eventStack.size()
            # TODO: refactor to simplify
            if numThreadEvents == 0: # empty thread stack
                s = ''
            else:
                topEvent = eventStack.top()
                if topEvent.status == 'aborted':
                    # do not print event
                    # TODO: is it reasonable only for the end of profile or
                    # can it be used elsewhere? Is it then a good solution?
                    return
                # TODO: more abstract way of checking the status?
                elif topEvent.status == 'started': # just started event
                    if numThreadEvents == 1:
                        oldWaitingBPs = ''
                    else:
                        # 2 or more events on the thread's stack
                        oldWaitingBPs =  '│ ' * (numThreadEvents - 2) + '├─'
                    s = oldWaitingBPs + str(topEvent)
                elif topEvent.status == 'finished': # just finished
                    s = '│ ' * (numThreadEvents - 1)
                elif topEvent.status == 'waiting': # waiting:
                    s = '│ ' * numThreadEvents
                else:
                    assert False, 'unknown event status %s of event %s' % \
                        (topEvent.status, topEvent)
            # grow the indentation if necessary
            sWidth = len(s.decode('utf-8'))
            emptyColumns = self.indent - sWidth
            if emptyColumns <= 0:
                # extend the width of each thread column including a slack of 5
                self.indent += -emptyColumns + 5
                emptyColumns = self.indent - sWidth
            # Note, that ljust() works on byte strings and gives surprising results
            # on UTF-8 encoded strings.
            s = s + ' ' * emptyColumns
            syncString += s
        self.outFile.write(syncString + '\n')

    def mark(self, name, category, scope, time, thread):
        markStr = '%s: %s (scope %s, thread %s)' % (category,
                                                    name,
                                                    scope,
                                                    thread)
        self.outFile.write(markStr + '\n')


class SPViewChrome(SPView):
    "synchronization profile printer in the JSON format for Chrome's trace viewer"
    def __init__(self, outFileName):
        self.events = []
        self.jsonSliceId = 0
        super(SPViewChrome, self).__init__(outFileName)

    def __del__(self):
        # TODO: refactor for streaming instead of growing memory
        # and flushing all at once at the end
        self.events = {'traceEvents': self.events}
        json.dump(self.events, open(self.outFileName, 'w'))
        super(SPViewChrome, self).__del__()

    def timestamp(self, pendEvents):
        for threadDict in pendEvents.values():
            eventStack = threadDict['events']
            if not eventStack.empty():
                event = eventStack.top()
                if event.status in ['finished', 'aborted']:
                    args = {'argument1' : event.evArg1,
                            'argument2' : event.evArg2,
                            'value' : event.evValue,
                            'source' : event.evFilename,
                            'line' : event.evLine,
                            'stacktrace' : event.evBacktrace}
                    if event.evType == 'access':
                        category = 'access'
                    else:
                        # function breakpoint:
                        # TODO: move to sp.conf
                        if 'GOMP_' in event.evName:
                            category = 'OpenMP'
                        elif 'pthread_' in event.evName:
                            category = 'POSIX threads'
                        elif 'sem_' in event.evName:
                            category = 'POSIX semaphores'
                        else:
                            category = 'unknown'
                    self.events += self.jsonSlice(category,
                                                  event.evThread,
                                                  event.evThread,
                                                  event.evName,
                                                  event.startTime,
                                                  event.stopTime,
                                                  args)

    def link(self, category, name, startTime, startThread, stopTime, stopThread, args):
        "arrow in the timeline"
        self.events += self.jsonSlice(category,
                                      startThread,
                                      stopThread,
                                      name,
                                      startTime,
                                      stopTime,
                                      args,
                                      depSlice=True)

    def group(self, category, name, startTime, startThread, stopTime, stopThread, args):
        "slices for designating groups of elementary slices"
        self.events += self.jsonSlice(category,
                                      startThread,
                                      stopThread,
                                      name,
                                      startTime,
                                      stopTime,
                                      args)

    def mark(self, name, category, scope, time, thread):
        "print instant event in the timeline"
        scope = {'global': 'g', 'process': 'p', 'thread': 't'}[scope]
        self.jsonSliceId += 1
        self.events += [self.event(name, category, thread, 'I', time, {}, scope)]

    def jsonSlice(self,
                  category,
                  threadStart,
                  threadEnd,
                  name,
                  start,
                  stop,
                  args,
                  depSlice=False):
        "return a string of a JSON slice for the trace viewer"
        self.jsonSliceId += 1
        assert stop >= start, 'stop (%d) must be after start (%d)' % (start, stop)
        if depSlice:
            return [self.event(name, category, threadStart, 's', start, args),
                    self.event(name, category, threadEnd, 'f', stop, {})]
        else:
            assert threadStart == threadEnd, \
                'starting thread %d is not equal finish thread %d' % \
                (threadStart, threadEnd)
            return [self.event(name, category, threadStart, 'B', start, args),
                    self.event(name, category, threadEnd, 'E', stop, {})]

    def event(self, name, category, thread, phase, ts, args, scope=None):
        # Note, that having 'args' entry is mandatory for flow events!
        e = {'cat': category, 'name': name, 'pid': 1, 'tid': thread, 'ph': phase,
             'id': self.jsonSliceId, 'ts': ts, 'args': args}
        if scope is not None:
            e['s'] = scope
        return e
