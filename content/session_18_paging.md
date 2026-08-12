# Session 18: Paging and Virtual Memory

## 3.1 Why paging exists
Contiguous allocation forces every process to occupy one unbroken block of
physical memory. Over time this produces external fragmentation: enough total
free memory exists, but no single block is large enough. Paging removes the
requirement for contiguity. Physical memory is divided into fixed-size frames
and the logical address space is divided into pages of the same size. Any page
may be placed in any free frame.

## 3.2 Address translation and the page table
A logical address is split into a page number and an offset. The page number
indexes the page table, which stores the frame number holding that page. The
hardware concatenates the frame number with the offset to form the physical
address. Each page table entry also carries a valid bit indicating whether the
page is currently resident in physical memory.

## 3.3 The page fault path
When the MMU reads a page table entry whose valid bit is clear, it raises a page
fault trap to the operating system. The OS locates the page on the backing
store, selects a free frame, issues the disk read, updates the page table entry,
and restarts the instruction that faulted. The faulting process is blocked for
the duration of the disk I/O.

## 3.4 The TLB
Walking the page table on every memory reference would double memory traffic.
The Translation Lookaside Buffer is a small associative cache of recent page to
frame mappings. On a TLB hit the frame number is available without touching the
page table. On a TLB miss the hardware or OS walks the page table and installs
the mapping. Because the TLB caches translations for one address space, a
context switch requires either a TLB flush or address space identifiers.

## 3.5 Internal fragmentation in paging
Paging eliminates external fragmentation but introduces internal fragmentation.
A process whose size is not an exact multiple of the page size wastes space in
its final page. The average waste is half a page per process, which is why very
large page sizes are not automatically better.
