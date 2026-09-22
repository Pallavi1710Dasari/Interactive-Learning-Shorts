# Session 7: State in React Components

## 7.1 How a state update triggers a re-render
Calling a state setter does not change the screen directly — it schedules React
to run the component function again. When `setCount` is called inside a click
handler, React does not reach into the DOM and edit a number; it marks the
component as needing to re-render, then calls the component function a second
time from the top. On that second call, `useState` returns the new value instead
of the old one, so the JSX the function returns this time already has the
updated number baked into it. React then compares the new returned JSX against
what is on screen and patches only the parts that changed. This is why a state
update always feels like "the UI updated," when what actually happened is that
the whole function ran again and returned a different description of the UI,
and React reconciled the difference.

```jsx
function Counter() {
  const [count, setCount] = useState(0);
  return <button onClick={() => setCount(count + 1)}>{count}</button>;
}
```

## 7.2 Why changing a plain JavaScript variable does not update the screen
A plain local variable declared inside a component function is recreated from
scratch every time that function runs, and reassigning it has no effect outside
that one function call. If `let count = 0` is declared inside `Counter` and a
click handler runs `count = count + 1`, that assignment changes a number that
lives only for the duration of the current render — nothing observes the
assignment, and nothing tells React a re-render is needed, so the function never
runs again and the number on screen never changes. The very next render throws
the old variable away and creates a brand-new `count` initialized back to 0. The
button's label would freeze at 0 forever, even though the variable is, for a
brief moment, genuinely incremented in memory. Clicking is not the missing
piece — React re-running the component is, and nothing about assigning a plain
variable asks React to do that.

## 7.3 How useState creates and updates state
`useState(initialValue)` returns an array of exactly two things: the current
value, and a setter function used to change it. `const [count, setCount] =
useState(0)` reads as "give me a piece of state starting at 0, called `count`,
and a way to change it called `setCount`." Calling `setCount(5)` does two
things: it tells React to remember 5 as this piece of state's new value for
next time, and it schedules the re-render described in 7.1. Crucially, React
remembers this value ACROSS renders, on React's own side, not inside the
component function — that is what makes it different from a local variable,
which 7.2 showed gets recreated and forgotten every render. Each call to
`useState` in a component is tracked separately and keeps returning that
component's own current value on every subsequent render, until the setter is
called again.

## 7.4 What state actually means in a React component
State is a value that a component is allowed to remember between renders, and
whose change is the one thing that is allowed to make React run that component
again. Every other piece of data inside a component function — a plain
variable, a calculation, a constant — is thrown away and rebuilt from nothing
on every render, exactly as 7.2 showed; state is the deliberate exception,
kept alive by React itself rather than by the function that declares it. That
is the whole reason `useState` exists rather than a normal variable being
enough: a component needs some way to say "this particular value should
survive being torn down and rebuilt, and changing it should trigger the
rebuild." Everything else follows from this one idea — the re-render in 7.1
is what "state changed" is defined to cause, and the persistence in 7.3 is
what "state" is defined to mean, so neither makes sense without this
definition sitting underneath both of them.
