/*
 * POSIX threads program with pthread_create, pthread_mutex_lock, pthread_mutex_unlock
 */
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef NUM_THREADS
#define NUM_THREADS    2
#endif

pthread_mutex_t m;
volatile unsigned shared_var;

void *thread_fun(void *threadid)
{
  long tid = (long)threadid;
  int i;
  for(i = 0; i < 32; i++)
  {
    pthread_mutex_lock(&m);
    fprintf(stderr, "i=%d thread #%ld shared_var=%d\n", i, tid, shared_var++);
    pthread_mutex_unlock(&m);
  }
  pthread_exit(NULL);
}

int main (void)
{
  pthread_t threads[NUM_THREADS];
  int rc;
  long t;

  /* spawn threads */
  for(t = 0; t < NUM_THREADS; t++)
  {
    printf("In main: creating thread %ld\n", t);
    rc = pthread_create(&threads[t], NULL, thread_fun, (void *)t);
    if (rc)
    {
      printf("ERROR; return code from pthread_create() is %d\n", rc);
      exit(-1);
    }
  }

  /* join threads */
  for(t = 0; t < NUM_THREADS; t++)
  {
    rc = pthread_join(threads[t], NULL);
    if (rc)
    {
      printf("ERROR; return code from pthread_create() is %d\n", rc);
      exit(-1);
    }
  }

  return 0;
}
