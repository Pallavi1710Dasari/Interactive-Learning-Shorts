## HTML Void Elements

### What are HTML Void Elements?
- Void elements are HTML elements that do not have any content or end tag.
- **Example**: `<img />`, `<br />`, `<input />`

---

### Example: Favourite Places Section

The Favourite Places section layout breaks down into small parts such as the background container, heading, and card container.

---

### Layout of the Favourite Places Section
The layout consists of several components:
1. **Background Container**
2. **Heading**
3. **Card Container**

---

### Adding Background Container

#### HTML
```html
<div class="favourite-places-bg-container"></div>
```

#### CSS

```css
.favourite-places-bg-container {
  background-image: url('https://assets.ccbp.in/frontend/static-website/tower-bg.png');
  height: 100vh;
  background-size: cover;
}
```

---

### Adding Favourite Places Section Heading

#### HTML

```html
<div class="favourite-places-bg-container">
  <h1 class="favourite-places-heading">
    Favourite Places
  </h1>
</div>
```

#### CSS

```css
.favourite-places-heading {
  color: white;
  font-size: 28px;
  font-family: 'Roboto';
  font-weight: bold;
}
```

---

### Adding Padding to the Favourite Places Section Heading

#### CSS

```css
.favourite-places-heading {
  color: white;
  font-size: 28px;
  font-family: 'Roboto';
  font-weight: bold;
  padding: 24px;
}
```

---

### Adding a Favourite Place Card

#### HTML

```html
<div class="favourite-places-bg-container">
  <h1 class="favourite-places-heading">Favourite Places</h1>
  <div class="favourite-place-card-container">
    <h1 class="favourite-place-card-heading">Taj Mahal</h1>
    <p class="favourite-place-card-description">
      If there was just one symbol to represent all of India, it would be the Taj Mahal.
    </p>
  </div>
</div>
```

#### CSS

```css
.favourite-place-card-container {
  background-color: white;
  border-radius: 8px;
  padding: 16px;
}
.favourite-place-card-heading {
  color: #0f0e46;
  font-family: 'Roboto';
  font-weight: bold;
  font-size: 23px;
}
.favourite-place-card-description {
  font-family: 'Roboto';
  font-size: 13px;
  color: #6c6b70;
}
```

---

### Adding Image to the Favourite Place Card

#### HTML

```html
<div class="favourite-place-card-container">
  <h1 class="favourite-place-card-heading">Taj Mahal</h1>
  <p class="favourite-place-card-description">
    If there was just one symbol to represent all of India, it would be the Taj Mahal.
  </p>
  <img src="https://assets.ccbp.in/frontend/static-website/tajmahal-img.png" />
</div>
```

---

### HTML Images: Syntax and Void Elements

* **HTML Image Element Syntax**:

```html
<img src="IMAGE_URL" />
```

* **Void Elements**: HTML elements like `<img />` are called void elements because they don't require an end tag.

---

## Box Properties

The box model defines the structure of HTML elements, consisting of the following properties:

* **Height**
* **Width**
* **Margin**
* **Padding**
* **Border**

---

### Applying Margin to Card Container

#### CSS

```css
.favourite-place-card-container {
  background-color: white;
  border-radius: 8px;
  padding: 16px;
  margin: 15px;
}
```

---

## HTML Lists

### What are HTML Lists?

Lists in HTML are used to group related pieces of information for easy readability. There are two types of lists:

* **Unordered Lists**
* **Ordered Lists**

### Unordered List

#### Example:

```html
<ul>
  <li>Jallianwala Bagh</li>
  <li>Wagah Border</li>
  <li>Harike Wetland</li>
  <li>Bathinda Fort</li>
</ul>
```

* By default, items in an unordered list are marked with bullets.

#### Styling Unordered Lists

#### CSS

```css
.unordered-list {
  list-style-type: circle;
}
```

* Other list styles:

  * `list-style-type: square;`
  * `list-style-type: disc;`
  * `list-style-type: none;`

---

### Ordered List

#### Example:

```html
<ol>
  <li>Jallianwala Bagh</li>
  <li>Wagah Border</li>
  <li>Harike Wetland</li>
  <li>Bathinda Fort</li>
</ol>
```

* Ordered list items are marked with numbers by default.

#### Styling Ordered Lists

#### CSS

```css
.ordered-list {
  list-style-type: upper-alpha;
}
```

* Other list styles:

  * `list-style-type: lower-roman;`
  * `list-style-type: lower-alpha;`

---