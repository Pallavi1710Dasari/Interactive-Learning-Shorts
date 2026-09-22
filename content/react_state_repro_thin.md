# React State — Thin Reproduction Material

## 1 What is State in React?
State is data that a React component keeps track of over time. Unlike a
regular variable, state is preserved by React across re-renders of the
component. Each component can have its own state, independent of other
components. State is commonly used for things like form inputs, toggles,
counters, and fetched data.

## 2 Creating State
You create state using the useState hook. It takes an initial value and
returns an array with two elements: the current state value and a function
to update it. For example, `const [count, setCount] = useState(0)` creates a
state variable called count starting at 0, along with a setCount function to
change it. You can call useState multiple times in one component to track
several independent pieces of state.

## 3 What Happens When State Changes?
When you call a state setter function like setCount, React schedules a
re-render of the component. During the re-render, the component function
runs again, and this time useState returns the new value instead of the old
one. React compares the new output to what's currently rendered and updates
only the parts of the DOM that actually changed, which keeps updates fast.
This is why calling setCount(count + 1) inside an onClick handler makes the
number on screen go up.

## 4 Why Do We Need State?
Without state, a component has no way to remember information between
renders — every time it renders, it would start over from scratch. Regular
variables declared inside a component function are recreated on every
render and don't persist, so they can't be used to track something like a
running count or a toggle switch. State solves this by giving components a
way to hold on to values across renders and to update the UI automatically
when those values change.
