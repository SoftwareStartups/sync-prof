/*
 * Deadlock with POSIX mutexes.
 */
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>

pthread_mutex_t m1, m2;
pthread_barrier_t b;
volatile unsigned shared_var;

void *thread_fun1(void *threadid)
{
  long tid = (long)threadid;
  pthread_mutex_lock(&m1);
  pthread_barrier_wait(&b);
  pthread_mutex_lock(&m2); // deadlock
  fprintf(stderr, "thread #%ld shared_var=%d\n", tid, shared_var++);
  pthread_mutex_unlock(&m2);
  pthread_mutex_unlock(&m1);
  pthread_exit(NULL);
}

void *thread_fun2(void *threadid)
{
  long tid = (long)threadid;
  pthread_mutex_lock(&m2);
  pthread_barrier_wait(&b);
  pthread_mutex_lock(&m1); // deadlock
  fprintf(stderr, "thread #%ld shared_var=%d\n", tid, shared_var++);
  pthread_mutex_unlock(&m1);
  pthread_mutex_unlock(&m2);
  pthread_exit(NULL);
}

int main (void)
{
  pthread_t thread1, thread2;

  pthread_barrier_init(&b, NULL, 2);

  pthread_create(&thread1, NULL, thread_fun1, (void *)0);
  pthread_create(&thread2, NULL, thread_fun2, (void *)1);

  pthread_join(thread1, NULL);
  pthread_join(thread1, NULL);

  return 0;
}
