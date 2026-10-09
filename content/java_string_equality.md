# Session 7: Java Strings and Equality

## 2.1 Why == fails on two equal strings
In Java, a `String` variable does not hold the text itself. It holds a reference,
an address that points to a string object somewhere in memory. The `==` operator
compares those references, not the characters behind them. Two strings built at
run time with the same letters are two separate objects at two different
addresses, so `==` reports false even though they read the same.

```java
String a = new String("hello");
String b = new String("hello");
System.out.println(a == b);       // false: two objects
System.out.println(a.equals(b));  // true: same characters
```

The `equals` method is what compares the contents. It walks both strings
character by character and returns true only when every character matches. This
is why `==` sometimes appears to work in small tests: string literals written
directly in the source are pooled, so two identical literals share one object and
`==` happens to be true. Code that relies on that breaks as soon as a string comes
from user input, a file or a concatenation, because those strings are new objects.

## 2.2 Comparing safely
The safe habit is to always compare text with `equals`, and to call it on the
value that cannot be null. Writing `"yes".equals(answer)` never throws, while
`answer.equals("yes")` throws a NullPointerException when `answer` is null. For
comparisons that should ignore case, `equalsIgnoreCase` does the same walk while
treating upper and lower case letters as equal.
