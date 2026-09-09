# Eval material: a root with several distinct dependents

## 7.1 What the operating system kernel depends on
The kernel does not run alone. It depends on the scheduler to decide which
process runs next on the CPU, and it separately depends on the device driver
layer to actually move bytes to and from hardware such as a disk or a network
card. These are two distinct dependencies, not two parts of one larger piece —
the scheduler never touches hardware I/O, and the driver layer never decides
which process gets CPU time. Because the two are independent of each other, the
kernel could in principle use a completely different scheduling algorithm
without changing a single line of the driver layer, and it could swap in a new
driver without the scheduler ever noticing. That independence has a real
consequence: if the driver layer fails to initialize a piece of hardware at
boot, the scheduler is completely unaffected, and the kernel can still schedule
every other process normally. The failure is contained to whatever depended on
that one driver, not to the kernel's ability to run processes at all.
