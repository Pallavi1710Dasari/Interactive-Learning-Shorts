# Session 20: The Stack

## 5.1 How push and pop work
A stack stores items in the order they arrive and removes them in the reverse
order, which is why it is called last-in-first-out. It exposes exactly two
operations that change it: push adds an item on top, and pop removes the item on
top. The stack tracks its own height with an index conventionally called top,
which starts at -1 when the stack is empty because no slot is occupied yet.
Pushing A sets top to 0, pushing B sets top to 1, and pushing C sets top to 2, so
top is always the index of the item that would come off next. Calling pop when top
is 2 returns C and leaves top at 1, and the value of B is untouched underneath. It
is tempting to picture pop as reaching into the middle for the item you want, but
no operation can address anything except the top slot, which is the whole
constraint the structure is built on.

## 5.2 Why the top index matters
Every stack operation is fast because both push and pop only ever touch one slot,
the one top points at, and neither has to walk the other items. Push increments
top and writes; pop reads and decrements top. That is why both are described as
constant time regardless of how many items the stack already holds. The index is
also the only thing that distinguishes an empty stack from a full one: top of -1
means empty and there is nothing to pop, and top equal to the last slot means full
and there is nowhere to push. A pop on an empty stack is called underflow and a
push on a full one is called overflow, and both are errors the caller has to handle
rather than states the stack can resolve for itself.
