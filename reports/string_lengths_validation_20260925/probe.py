def show(text):
    print(len(text))
    print('[', text, ']', sep='')


items_lengths = 123
items = ['', 'a', 'abc', 'a ', '  ']
for text in items:
    show(text)
print(items_lengths)
for i in range(-len(items), len(items)):
    show(items[i])
for i, text in enumerate(items, start=-2):
    print(i)
    show(text)
alias = items
tail = items[1:]
reverse = items[::-1]
items = ['xy ', '']
show(alias[0])
show(alias[-1])
show(items[0])
for text in tail:
    show(text)
for text in reverse:
    show(text)
for text in ['a7to99.txt', '2cat9.dat  ']:
    show(text)
show(('short ', '')[-1])
