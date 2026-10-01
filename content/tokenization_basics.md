# Session 4: Tokenization

## 1.1 How AI reads your text

A language model cannot read letters or words. It only reads numbers, so before
a model sees anything you type, your words must become numbers. This first step
is called tokenization, and a tokenizer is the tool that does it. Take one short
sentence, "Tokenization matters." It is just two words, and we will follow it
all the way to the numbers the model reads.

The tokenizer works in four steps. First it cuts the sentence into pieces at
spaces and punctuation. Then it checks each piece against its word shelf, the
fixed list of pieces the model knows; a word that is not on the shelf is built
from smaller pieces that are. Next it adds two special tokens, one at the front
and one at the end. Finally it swaps each token for a number, the token's ID on
the shelf. The sections below look at each step in turn.

## 1.2 Cutting the sentence

The tokenizer first cuts the sentence at spaces and punctuation. The full stop
becomes its own piece, so "Tokenization matters." becomes three pieces:
"Tokenization", "matters" and ".".

## 1.3 The word shelf

Every model has a fixed list of word pieces it knows, called its vocabulary.
Think of it as a shelf of pieces. Our model knows about 1.2 lakh pieces.
Common words are kept whole on the shelf, and rare words are built from smaller
pieces. "Matters" is on the shelf, but "Tokenization" is not, so the tokenizer
builds it from pieces that are. It starts at the front of the word and takes the
longest piece that fits: "Token" is not on the shelf, "Tok" is not, "To" is.
From what is left, "ken" is on the shelf, and then "ization". So "Tokenization"
becomes "To", plus "ken", plus "ization". The pieces "ken" and "ization" get a
double hash in front, written "##ken" and "##ization", which means "joined to
the piece before". The two words are now five tokens.

## 1.4 Two special tokens

Next the tokenizer adds two special tokens. [CLS] goes at the front and [SEP]
goes at the end. The model learns to gather a summary of the whole sentence
into [CLS], and [SEP] marks where a sentence stops. The two words are now seven
tokens.

## 1.5 From tokens to IDs

Every piece on the shelf has a fixed ID, like a roll number in class. For
example, [CLS] is 101 and [SEP] is 102. The tokenizer swaps each token for its
ID, so our sentence becomes 101, 11469, 11862, 19988, 50807, 119, 102. The
number has no meaning by itself; it only points to a row of the shelf.

## 1.6 Why tokens matter

Different models cut the same text differently, and both cost and limits are
counted in tokens. So always count tokens with your own model's tokenizer.
