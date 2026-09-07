# Eval material: code present, objective varies

## 6.1 How a stack grows and shrinks
A stack keeps items in arrival order and removes them in reverse, so the last item
pushed is the first one popped. Pushing places a new item on top of the items
already there, and popping takes the top item away and leaves the rest untouched.
Only the top position is ever reachable, which is the constraint that makes the
structure useful. A typical implementation looks like this:

```python
def push(self, item):
    self.items.append(item)

def pop(self):
    return self.items.pop()
```

The code is short because the behaviour is simple: one list, and both operations
acting on its end. Pushing A then B then C leaves C on top, so the next pop
returns C and leaves B reachable underneath.

## 6.2 Reading a font-family declaration
A CSS declaration is written as a property, a colon, a value, and a semicolon, in
that order. In the declaration below, `font-family` is the property and
`"Roboto", sans-serif` is the value:

```css
p {
  font-family: "Roboto", sans-serif;
}
```

The value here is a list of two entries separated by a comma, and the browser tries
them left to right, using the first one it has. The quotation marks are required
around a family name containing a space, and the semicolon terminates the
declaration so another one can follow it inside the same block.
