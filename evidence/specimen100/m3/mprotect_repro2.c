#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <sys/mman.h>
#include <errno.h>
#include <unistd.h>
#define END 1162261467ULL
int main(void){
  long ps = sysconf(_SC_PAGESIZE);
  size_t res = (size_t)END*4u;
  void* m = mmap(NULL, res, PROT_NONE, MAP_NORESERVE|MAP_PRIVATE|MAP_ANON, -1, 0);
  if (m == MAP_FAILED){ perror("mmap"); return 1; }
  printf("reserved %zu bytes at %p (page=%ld)\n", res, m, ps);
  errno=0; int r = mprotect(m, 81920, PROT_READ|PROT_WRITE);
  printf("seq1 mprotect(81920 @+0): r=%d errno=%d (%s)\n", r, errno, r?strerror(errno):"ok");
  volatile uint32_t* w = (uint32_t*)m; for (int i=0;i<20480;i++) w[i]=(uint32_t)i;
  printf("touch 81920 bytes: ok w[20479]=%u\n", w[20479]);
  size_t offs[] = {81920, 1<<20, 40ULL<<20, 1ULL<<30, res-(size_t)ps};
  const char* nm[] = {"+81920", "+1MB", "+40MB", "+1GB", "+end-page"};
  for (int i=0;i<5;i++){
    void* a = (char*)m + offs[i];
    errno=0; r = mprotect(a, (size_t)ps, PROT_READ|PROT_WRITE);
    printf("seq2 mprotect(%s): r=%d errno=%d (%s)\n", nm[i], r, errno, r?strerror(errno):"ok");
  }
  void* t = (char*)m + (2ULL<<20);
  errno=0; void* rr = mmap(t, 1<<20, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANON|MAP_FIXED, -1, 0);
  printf("seq3 mmap MAP_FIXED 1MB @+2MB: r=%p errno=%d (%s)\n", rr, errno, rr==MAP_FAILED?strerror(errno):"ok");
  return 0;
}
