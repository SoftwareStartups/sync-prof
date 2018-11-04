/*
 * Deadlock with semaphores.
 */
#include <pthread.h>
#include <semaphore.h>
#include <stdio.h>
#include <stdlib.h>

sem_t sem1, sem2;
pthread_barrier_t b;
volatile unsigned shared_var;

void *thread_fun1(void *threadid)
{
  long tid = (long)threadid;
  pthread_barrier_wait(&b);
  sem_wait(&sem1); // deadlock
  fprintf(stderr, "thread #%ld shared_var=%d\n", tid, shared_var++);
  sem_post(&sem2);
  pthread_exit(NULL);
}

void *thread_fun2(void *threadid)
{
  long tid = (long)threadid;
  pthread_barrier_wait(&b);
  sem_wait(&sem2); // deadlock
  fprintf(stderr, "thread #%ld shared_var=%d\n", tid, shared_var++);
  sem_post(&sem1);
  pthread_exit(NULL);
}

int main (void)
{
  pthread_t thread1, thread2;

  pthread_barrier_init(&b, NULL, 2);
  sem_init(&sem1, 0, 0);
  sem_init(&sem2, 0, 0);

  pthread_create(&thread1, NULL, thread_fun1, (void *)0);
  pthread_create(&thread2, NULL, thread_fun2, (void *)1);

  pthread_join(thread1, NULL);
  pthread_join(thread1, NULL);

  return 0;
}
