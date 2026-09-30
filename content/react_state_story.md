# Session 7: State in React Components

## 7.1 Why changing a plain variable does not update the screen

A counter button that uses a plain variable keeps showing 0, no matter how many times it is clicked.
Inside a component, `let count = 0` creates a plain local variable, and a click handler that runs `count = count + 1` does change that number in memory.
But nothing tells React that anything changed, so React does not run the component again.
Because the component does not run again, the screen is never redrawn, and the button keeps showing 0.
A plain variable also cannot survive a redraw: every time the component function runs, the variable is created again from scratch and starts back at 0.
So a plain variable fails in two ways: changing it does not redraw the screen, and a redraw throws its value away.

```jsx
function Counter() {
  let count = 0;
  return <button onClick={() => { count = count + 1; }}>{count}</button>;
}
```

## 7.2 How useState remembers a value and updates the screen

`useState` asks React to keep a value on React's own side, outside the component function.
Because React keeps the value, it survives every time the component function runs again.
`useState` gives back two things: the current value, and a setter function that is the only proper way to change it.
Calling the setter does two things: it tells React to remember the new value, and it tells React to run the component again.
When the component runs again, `useState` hands back the remembered value instead of the starting value.
React then updates only the parts of the screen that changed, so the button now shows the new number.

```jsx
function Counter() {
  const [count, setCount] = useState(0);
  return <button onClick={() => setCount(count + 1)}>{count}</button>;
}
```

## 7.3 What state actually means in a React component

State is a value that React remembers for a component between redraws.
Changing state through its setter is what tells React to redraw that component.
Everything else inside a component function, such as plain variables and calculations, is thrown away and rebuilt on every redraw.
State is the deliberate exception: it is kept alive by React, not by the function that declares it.
That is the whole reason `useState` exists: some values need to be remembered, and changing them needs to update the screen.

## 7.4 useState syntax at a glance

`const [count, setCount] = useState(0)` creates a piece of state named `count` that starts at 0, and a setter named `setCount` that changes it.
The value passed to `useState` is used only as the starting value, the first time the component runs.
Each call to `useState` in a component creates its own separate piece of state.
