# Session 22: The Linked List

## 7.1 How a linked list finds the next item without an index

A linked list stores its values in separate nodes scattered anywhere in
memory, and each node holds two things: the value itself, and a pointer to
the next node in the list. There is no index to jump to a position with —
finding the third item means starting at the node the list calls head,
reading its pointer to reach the second node, and reading that node's
pointer to reach the third. The last node's pointer holds a special value,
often called null, which is how the list states its own end: reaching null
is how a traversal knows there is nothing further to visit.

## 7.2 Why inserting in the middle costs nothing extra

Inserting a new node between two existing ones only touches two pointers: the
new node's pointer is set to point at whatever the node before it used to
point at, and that earlier node's pointer is set to point at the new node
instead. Nothing else in the list moves or gets copied, which is the direct
opposite of an array, where inserting in the middle means shifting every
later element one slot down to make room. A linked list pays for that with
slower access to a specific position, since reaching node 500 still means
walking the 499 pointers before it — there is no shortcut a linked list can
take that an array's index already gives for free.
