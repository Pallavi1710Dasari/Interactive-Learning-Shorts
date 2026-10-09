# React Props

## What are Props?
Props are values passed from a parent component to a child component. They help us reuse the same component with different data.

## Example

```jsx
function App() {
  return <Welcome name="Asha" />;
}

function Welcome(props) {
  return <h1>Hello, {props.name}</h1>;
}
```

## How It Works

* `App` passes the value `"Asha"` to `Welcome` as a prop called `name`.
* `Welcome` receives it through `props.name`.
* The child shows whatever value its parent sent.

Basic flow: Parent passes data -> Child receives props -> Child renders it.

## Script
A parent component decides what data to send. The child component only reads the props it is given. Change the prop in the parent, and the child shows the new value.
