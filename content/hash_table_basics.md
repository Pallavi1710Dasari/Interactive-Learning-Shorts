# Session 21: The Hash Table

## 6.1 How a hash table finds a value without searching

A hash table stores values under keys and finds them without walking the
collection: a hash function takes the key and computes a number from it, and
that number is used directly as an index into an array of buckets. Storing the
value for key "cat" means computing hash("cat"), landing on some index like 2,
and placing the value in bucket 2. Looking it up later means computing
hash("cat") again, going straight to bucket 2, and reading what is there. No
other bucket is ever inspected, which is the whole point: the key tells you
exactly where to look before you look.

## 6.2 Why two different keys can want the same bucket

A hash function can map two different keys to the same index, because the
number of possible keys is far larger than the number of buckets. This is
called a collision, and it is not a bug — with enough keys and a fixed number
of buckets it is mathematically guaranteed to happen eventually. The common
fix is chaining: each bucket holds a small list instead of a single value, so
when "cat" and "dog" both hash to bucket 2, both are stored there, one after
the other. A lookup for "dog" goes straight to bucket 2, the correct bucket in
one step, and only then checks the short list inside it to find "dog" rather
than "cat". That second step is a short walk through a handful of items, not a
walk through the whole table, which is why lookups stay fast even when
collisions happen.
