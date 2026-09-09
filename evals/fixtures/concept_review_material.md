# Eval material: three concept types for a visual-quality review

## 8.1 let versus var: how scoping actually differs
Both `let` and `var` declare a variable, but they answer to different boundaries.
A variable declared with `var` is scoped to the whole function it appears in,
even if it is written deep inside an if-block or a for-loop — the block itself
does not contain it. A variable declared with `let` is scoped to the nearest
enclosing block, so a `let` inside a for-loop's body is invisible the moment
that loop body ends. This is why a classic loop bug appears with `var` and not
with `let`: a `var` loop counter declared inside a for-loop is really one shared
variable for the whole function, so every callback created inside that loop
closes over the same final value. A `let` loop counter creates a fresh binding
for each iteration, so each callback closes over its own value instead.

## 8.2 Why a missing semicolon can break the whole file
A JavaScript parser reads statements one at a time and decides where each one
ends using either an explicit semicolon or a small set of automatic
semicolon-insertion rules. Those rules are not a full safety net: a `return`
statement followed by a newline and then a value on the next line is treated as
`return;` — the parser inserts a semicolon immediately after `return` because
that automatic rule fires on a newline after specific keywords, and the value on
the next line becomes dead, unreachable code that starts a new statement of its
own. The function then returns `undefined` instead of the value the author
intended, and everything that depended on that return value fails, often far
away from the line that actually caused it.

## 8.3 How a queue releases items in the order they arrived
A queue is opened at both ends: new items join at the back, and the only item
that can ever leave is the one at the front. Enqueuing puts an item at the back
and moves the back marker one place further; nothing else in the queue is
touched. Dequeuing removes the item at the front and moves the front marker one
place forward, so the item that has been waiting longest is always the one that
leaves next — first in, first out. If the queue is empty, the front and back
markers point to the same place and there is nothing to dequeue; if the queue is
full, the back marker has nowhere left to advance to and an enqueue fails.
