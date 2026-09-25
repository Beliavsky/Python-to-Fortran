def choose(mode):
    text = ''
    if mode == 0:
        return None
    if mode == 1:
        text = None
    elif mode == 2:
        text = 'None'
    elif mode == 3:
        text = 'abc  '
    return text


for mode in range(5):
    value = choose(mode)
    alias = value
    print(mode, value, alias)
    print('[', value, ']', sep='')
    print(value is None, value is not None, None == alias, alias != None)
    if value is not None:
        print(len(value))
