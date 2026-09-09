## Array Methods

### How does reduce() combine array elements into a single value using an accumulator?

reduce() is the most conceptually demanding of the three methods and understanding the accumulator pattern is central to using it correctly.

Consider an array `[1, 2, 3, 4]` and we want to find the sum.

| Step | Array State | Accumulator Value |
|------|--------------|--------------------|
| 1 | [1, 2, 3, 4] | 1 |
| 2 | [2, 3, 4] | 3 |
| 3 | [3, 4] | 6 |
| 4 | [4] | 10 |

---
