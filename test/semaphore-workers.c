/// DESC: A complex semaphore pattern with two workers.
/// DESC: This version has no race.

/* What we're testing here specifically is that combining multiple semaphores,
 * some used as mutexes, some used for signalling other threads that they can
 * contnue, will work correctly.
 *
 * This is based on a work pattern we saw in real world project partner code.
 */

#include <inttypes.h>
#include <pthread.h>
#include <semaphore.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#define ITERATIONS 5

uint32_t shared;

sem_t critical_section_sem;

typedef struct worker_data {
  sem_t* start_sem;
  sem_t* done_sem;
  uint32_t offset;
} worker_data;

static void* worker(void* data)
{
  worker_data* wd = (worker_data*) data;
  uint32_t i;
  for (i = 0; i < ITERATIONS; i++)
  {
    uint32_t n;
    sem_wait(wd->start_sem);
    sem_wait(&critical_section_sem);
    /* This variable is never read, but the compiler can't know that since it's exported.
     *
     * The writes to the variable form a detectable race, unless the
     * synchronisation through critical_section_sem works properly.
     */
    shared = wd->offset; /* Write/write race if not properly synchronized. */
    sem_post(&critical_section_sem);
    sem_post(wd->done_sem);
  }
  return NULL;
}

typedef struct runner_data {
  worker_data* wd1, *wd2;
} runner_data;

static void* runner(void* data)
{
  runner_data* rd = (runner_data*) data;
  while (1)
  {
    /* Run the two workers in lockstep. */
    sem_post(rd->wd1->start_sem);
    sem_post(rd->wd2->start_sem);
    sem_wait(rd->wd1->done_sem);
    sem_wait(rd->wd2->done_sem);
  }
  return NULL;
}

int main(void)
{
  sem_t start_sem1, start_sem2, done_sem1, done_sem2;
  sem_init(&start_sem1, 0, 0);
  sem_init(&start_sem2, 0, 0);
  sem_init(&done_sem1, 0, 0);
  sem_init(&done_sem2, 0, 0);
  sem_init(&critical_section_sem, 0, 1);
  worker_data wd1 = { &start_sem1, &done_sem1, 0 };
  worker_data wd2 = { &start_sem2, &done_sem2, 1 };
  runner_data rd = { &wd1, &wd2 };
  pthread_t t_runner, t_worker1, t_worker2;
  pthread_create(&t_worker1, NULL, worker, &wd1);
  pthread_create(&t_worker2, NULL, worker, &wd2);
  pthread_create(&t_runner, NULL, runner, &rd);
  pthread_join(t_worker1, NULL);
  pthread_join(t_worker2, NULL);
  return 0;
}
