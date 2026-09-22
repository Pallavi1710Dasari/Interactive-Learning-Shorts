# React State — Reproduction Material

## 1 What is State in React?
State is data that a component owns and is allowed to remember between
renders, unlike a plain variable declared inside the component function,
which is thrown away and rebuilt from nothing every time that function runs.
A component asks React to track a piece of state instead of managing the
value itself, and in exchange React guarantees the value survives being torn
down and rebuilt on every render. This is the one property that makes state
different from every other piece of data inside a component: a calculation,
a constant, or a locally declared variable resets on every render, but state
does not, because React itself is the thing remembering it, not the function
body. Nothing about rendering or updating the screen makes sense until this
distinction is in place — a re-render is defined in terms of state changing,
and persistence across renders is defined in terms of state being the thing
that persists, so both ideas assume this one first.

## 2 Creating State
`useState(initialValue)` is the hook that gives a component a piece of state.
It returns an array of exactly two things: the current value, and a setter
function used to change it. `const [count, setCount] = useState(0)` reads as
"give me a piece of state starting at 0, called count, and a way to change it
called setCount." Each call to `useState` inside a component is tracked
separately by React, keyed to its position in that component, so a component
calling `useState` three times gets three independently remembered values.
Calling the setter later does not overwrite the value directly inside the
function the way reassigning a normal variable would; it hands the new value
to React, which stores it and schedules the update described in the next
section.

## 3 What Happens When State Changes?
Calling a state setter does not edit the screen directly — it schedules React
to run the component function again from the top. When `setCount` is called
inside a click handler, React marks the component as needing a re-render,
then calls the component function a second time. On that second call,
`useState` returns the new value instead of the old one, so the JSX the
function returns this time already reflects the updated number. React then
compares the newly returned JSX against what is currently on screen and
patches only the parts that changed, rather than rebuilding the whole page.
This is why a state update always looks like "the UI updated," when what
actually happened is that the whole function ran again and returned a
different description of the UI, which React then reconciled against the old
one.

## 4 Why Do We Need State?
Without state, a component would have no way to remember anything between
renders, and every render would start from the exact same values it started
with the first time — a counter could never count, because the number
displayed would reset to its initial value on every single render instead of
carrying forward the last click. Plain variables cannot fill this role
because they are scoped to one call of the function and vanish the moment
that call ends; only a mechanism that lives outside the function body, on
React's own side, can survive being called again and again. State exists
specifically to solve that problem: it gives a component exactly one thing —
a value React remembers and knows how to update — that plain JavaScript
alone cannot provide inside a function that gets re-invoked on every render.
