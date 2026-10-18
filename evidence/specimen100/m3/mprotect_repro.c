#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <sys/mman.h>
#include <errno.h>
#include <unistd.h>
#define END 1162261467ULL
int main(void){
  size_t res = (size_t)END*4u;
  void* m = mmap(NULL, res, PROT_NONE, MAP_NORESERVE|MAP_PRIVATE|MAP_ANON, -1, 0);
  if (m == MAP_FAILED){ perror("mmap"); return 1; }
  printf("reserved %zu bytes at %p\n", res, m);
  errno = 0; int r = mprotect(m, 81920, PROT_READ|PROT_WRITE);
  printf("mprotect(81920): r=%d errno=%d (%s)\n", r, errno, r ? strerror(errno) : "ok");
  errno = 0; r = mprotect(m, 4096, PROT_READ|PROT_WRITE);
  printf("mprotect(4096): r=%d errno=%d (%s)\n", r, errno, r ? strerror(errno) : "ok");
  return 0;
}
