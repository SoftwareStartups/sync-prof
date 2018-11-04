/// DESC: A simple race with threads that don't fit the usual spawn/join pattern.

/*
The thread lifetimes here look like this (--> = spawn, <--- = join):

main    p     q     r
 |
 +----->|
 |      |
 |      +---->|
 |      |     |
 |      +---------->|
 |            |     |
 |            |<----|
 |            |
 |<-----------|
 |
*/

#include <inttypes.h>
#include <pthread.h>
#include <sched.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

pthread_mutex_t q_spawn_lock = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_t r_spawn_lock = PTHREAD_MUTEX_INITIALIZER;
bool q_started = false;
bool r_started = false;
pthread_t q, r;

const char* s = NULL;

void* run_q(void* ignored)
{
  while (true)
  {
    pthread_mutex_lock(&r_spawn_lock);
    if (r_started)
    {
      pthread_join(r, NULL);
      pthread_mutex_unlock(&r_spawn_lock);
      break;
    }
    else
    {
      pthread_mutex_unlock(&r_spawn_lock);
      sched_yield();
    }
  }
  return NULL;
}

void* run_r(void* ignored)
{
  s = "world"; /* race */
  return NULL;
}

void* run_p(void* ignored)
{
  pthread_mutex_lock(&q_spawn_lock);
  pthread_create(&q, NULL, run_q, NULL);
  q_started = true;
  pthread_mutex_unlock(&q_spawn_lock);

  pthread_mutex_lock(&r_spawn_lock);
  pthread_create(&r, NULL, run_r, NULL);
  r_started = true;
  pthread_mutex_unlock(&r_spawn_lock);
  return NULL;
}

int main(void)
{
  pthread_t p;
  pthread_t q_;
  pthread_create(&p, NULL, run_p, NULL);
  s = "hello"; /* race */
  /* Ugly but safe busy-waiting to get the thread ID of q. */
  while (true)
  {
    pthread_mutex_lock(&q_spawn_lock);
    if (q_started)
    {
      q_ = q;
      pthread_mutex_unlock(&q_spawn_lock);
      break;
    }
    else
    {
      pthread_mutex_unlock(&q_spawn_lock);
      sched_yield();
    }
  }
  pthread_join(q_, NULL);
  printf("%s\n", s);
  return EXIT_SUCCESS;
}
