# Session 19: CSS Specificity and the Cascade

## 4.1 How the browser scores a selector
When two rules set the same property on the same element, the browser does not
simply take the last one it read. It first scores each selector for specificity,
and the higher score wins regardless of order. The score has three components,
counted independently: the number of id selectors, the number of class,
attribute and pseudo-class selectors, and the number of type and pseudo-element
selectors. A selector written `#nav .item a` therefore scores 1 id, 1 class and
1 type, which is conventionally written 1,1,1. A selector written `.item .link a`
scores 0,2,1. The components are compared left to right and the first difference
decides the winner, so 1,0,0 beats 0,2,1 even though the second selector names
more parts. This is why adding another class to a rule cannot make it override
a rule that uses an id.

## 4.2 When specificity ties
Specificity decides most conflicts, but two selectors can score identically. A
rule written `.card .title` and a rule written `.panel .title` both score 0,2,0.
When the scores are equal the browser falls back to document order and applies
whichever rule it read last, which means the position of the rule in the
stylesheet matters only after a tie. A stylesheet loaded later in the document
therefore overrides an earlier one for equally specific rules, and two rules in
the same file are decided by which appears further down. This ordering rule is
the one most developers actually rely on day to day, because most stylesheets are
written almost entirely in classes, and equally specific class rules are exactly
the case where order decides.

## 4.3 The inline style and the important flag
Two things sit outside the three-component score. A style written directly on the
element, as in `style="color: red"`, is more specific than any selector in any
stylesheet, because it is attached to the one element rather than matched to it.
Above even that sits a declaration marked `!important`, which wins against
everything including an inline style, and is compared only against other
important declarations. It is tempting to read `!important` as a very large
specificity score, but it is not part of the score at all: it moves the
declaration into a separate layer that is resolved first. That distinction
matters because two important declarations are then settled by the ordinary
specificity rules between themselves, which surprises people who expect the
first important rule to stand.
