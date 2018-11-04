/// DESC: Simplest read/write with proper synchronization using a condition variable.

#include <inttypes.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

int32_t a = 0;
int32_t b;

pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
pthread_cond_t cond_var = PTHREAD_COND_INITIALIZER;
pthread_barrier_t barrier;

void* run_p(void* ignored)
{
  pthread_barrier_wait(&barrier);
  pthread_mutex_lock(&lock);
  a = 4;
  pthread_cond_signal(&cond_var);
  pthread_mutex_unlock(&lock);
  return NULL;
}

void* run_q(void* ignored)
{
  pthread_mutex_lock(&lock);
  pthread_barrier_wait(&barrier);
  while (a == 0)
  {
    pthread_cond_wait(&cond_var, &lock);
  }
  pthread_mutex_unlock(&lock);
  b = a;
  return NULL;
}

int main(void)
{
  pthread_t p, q;
  pthread_barrier_init(&barrier, NULL, 2);
  pthread_create(&p, NULL, run_p, NULL);
  pthread_create(&q, NULL, run_q, NULL);
  pthread_join(p, NULL);
  pthread_join(q, NULL);
  printf("a = %"PRIi32", b = %"PRIi32"\n", a, b);
  return EXIT_SUCCESS;
}
